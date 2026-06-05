import httpx
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import KEYCLOAK_URL, KEYCLOAK_REALM
from app.db.session import get_db
from app.db.models import User, AuditLog
from app.core.logging import logger
from app.core.carta import get_or_create_session, register_ip

from app.core.audit_chain import write_audit_entry


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
)

_jwks_cache: Optional[dict] = None

MFA_SETUP_ALLOWED_PATHS = {
    "/auth/mfa/send-code",
    "/auth/mfa/verify-code",
    "/auth/me",
    "/auth/logout",
    "/messages/send",          
    "/messages/my-conversation",
}


async def get_keycloak_public_keys() -> dict:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.get(url, timeout=10)
        response.raise_for_status()
        _jwks_cache = response.json()
        logger.info("Keycloak public keys fetched and cached")
        return _jwks_cache


def extract_role(payload: dict) -> str:
    valid_roles = {"student", "researcher", "admin"}
    realm_roles = payload.get("realm_access", {}).get("roles", [])
    for role in realm_roles:
        if role in valid_roles:
            return role
    custom_roles = payload.get("role", [])
    if isinstance(custom_roles, list):
        for role in custom_roles:
            if role in valid_roles:
                return role
    return "student"


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:

    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Step 1 — verify JWT
    try:
        jwks = await get_keycloak_public_keys()
        payload = jwt.decode(
            token, jwks, algorithms=["RS256"],
            options={"verify_aud": False},
        )
        keycloak_id: str = payload.get("sub")
        if keycloak_id is None:
            raise credentials_exception
    except ExpiredSignatureError:
        raise HTTPException(401, "Token has expired")
    except JWTError:
        raise credentials_exception

    # Step 2 — extract info
    username = payload.get("preferred_username", keycloak_id)
    email = payload.get("email", f"{username}@unknown.com")
    user_role = extract_role(payload)

    # Step 3 — look up or create user
    result = await db.execute(
        select(User).where(User.keycloak_id == keycloak_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            keycloak_id=keycloak_id,
            username=username,
            email=email,
            role=user_role,
            requested_role=user_role,
            is_approved=False,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        await write_audit_entry(
            db=db,
            action="register",
            result="success",
            user_id=str(user.user_id),
            detail={"username": username, "source": "keycloak"},
        )

        await db.commit()
        await db.refresh(user)
        logger.info(f"New user from Keycloak: {username} ({user_role})")

    else:
        if user.role != user_role:
            old_role = user.role
            user.role = user_role

            await write_audit_entry(
                db=db,
                action="role_change",
                result="success",
                user_id=str(user.user_id),
                detail={
                    "old_role": old_role,
                    "new_role": user_role,
                    "source": "keycloak_sync",
                },
            )

            await db.commit()

    # Step 4 — check account status
    if not user.is_active:
        raise HTTPException(403, "Account is disabled")

    if not user.is_approved:
        raise HTTPException(403,
            "Account pending admin approval. "
            "Please wait for an administrator to approve your registration.")

    # Step 5 — Email OTP gate
    if user.role != "admin":
        if not user.email_otp_verified:
            # تحقق من أن المستخدم لديه جلسة MFA نشطة
            from app.core.carta import get_or_create_session
            session = await get_or_create_session(user, token, request, db)
            
            if session.totp_verified_at:
                # تم التحقق من MFA في هذه الجلسة
                pass
            else:
                path = request.url.path.rstrip("/")
                allowed = any(path.endswith(p) for p in MFA_SETUP_ALLOWED_PATHS)
                if not allowed:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "code": "mfa_required",
                            "message": (
                                "You must verify your identity before continuing. "
                                "POST to /auth/mfa/send-code to receive a code by email, "
                                "then verify it at /auth/mfa/verify-code."
                            ),
                            "send_url": "/auth/mfa/send-code",
                            "verify_url": "/auth/mfa/verify-code",
                        }
                    )
        else:
            # إذا كان email_otp_verified = True، تحقق من الجلسة
            from app.core.carta import get_or_create_session
            session = await get_or_create_session(user, token, request, db)
            
            if not session.totp_verified_at:
                path = request.url.path.rstrip("/")
                allowed = any(path.endswith(p) for p in MFA_SETUP_ALLOWED_PATHS)
                if not allowed:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "code": "mfa_required",
                            "message": (
                                "You must verify your identity before continuing. "
                                "POST to /auth/mfa/send-code to receive a code by email, "
                                "then verify it at /auth/mfa/verify-code."
                            ),
                            "send_url": "/auth/mfa/send-code",
                            "verify_url": "/auth/mfa/verify-code",
                        }
                    )

    # Step 6 — Register IP on every authenticated request
    if request and request.client:
        await register_ip(
            user_id=user.user_id,
            ip=request.client.host,
            db=db,
            verified=False,
        )

    return user


async def get_current_user_and_token(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request, token, db)
    return user, token


async def require_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return current_user
    
    
async def get_current_user_basic(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Like get_current_user but allows unapproved users — for messaging only."""
    payload = await decode_token(token)
    user_id = payload.get("sub") or payload.get("user_id")
    
    result = await db.execute(select(User).where(User.keycloak_id == user_id))
    user = result.scalar_one_or_none()
    
    if user is None or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    
    return user
