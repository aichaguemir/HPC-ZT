import httpx
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_CLIENT_ID
from app.db.session import get_db
from app.db.models import User, AuditLog
from app.core.logging import logger

# ── OAuth2 scheme ──────────────────────────────────────────────────────────
# tokenUrl points to Keycloak's token endpoint
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
)

# ── Public key cache ───────────────────────────────────────────────────────
_jwks_cache: Optional[dict] = None


async def get_keycloak_public_keys() -> dict:
    """
    Fetch Keycloak's public keys (JWKS).
    Cached after first fetch — public keys rarely change.
    """
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10)
        response.raise_for_status()
        _jwks_cache = response.json()
        logger.info("Keycloak public keys fetched and cached")
        return _jwks_cache


def extract_role(payload: dict) -> str:
    """
    Extract the user's HPC role from the JWT payload.
    Uses realm_access.roles — standard Keycloak claim.
    Falls back to 'student' if no matching role found.
    """
    valid_roles = {"student", "researcher", "admin"}

    # Primary: realm_access.roles (standard Keycloak)
    realm_roles = payload.get("realm_access", {}).get("roles", [])
    for role in realm_roles:
        if role in valid_roles:
            return role

    # Fallback: custom "role" claim (her mapper)
    custom_roles = payload.get("role", [])
    if isinstance(custom_roles, list):
        for role in custom_roles:
            if role in valid_roles:
                return role

    return "student"  # default — least privilege


# ── Main dependency ────────────────────────────────────────────────────────

async def get_current_user(
    token: str          = Depends(oauth2_scheme),
    db:    AsyncSession = Depends(get_db)
) -> User:

    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Step 1 — verify JWT signature using Keycloak's public key
    try:
        jwks    = await get_keycloak_public_keys()
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False},  # flexible audience check
        )
        keycloak_id: str = payload.get("sub")
        if keycloak_id is None:
            raise credentials_exception

    except ExpiredSignatureError:
        raise HTTPException(401, "Token has expired")
    except JWTError:
        raise credentials_exception

    # Step 2 — extract user info from token
    username  = payload.get("preferred_username", keycloak_id)
    email     = payload.get("email", f"{username}@unknown.com")
    user_role = extract_role(payload)

    # Step 3 — look up or auto-create user in your DB
    result = await db.execute(
        select(User).where(User.keycloak_id == keycloak_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        # First login — auto-create with role from Keycloak
        user = User(
            keycloak_id = keycloak_id,
            username    = username,
            email       = email,
            role        = user_role,
        )
        db.add(user)
        await db.flush()

        log = AuditLog(
            user_id = user.user_id,
            action  = "register",
            detail  = {"username": username, "source": "keycloak",
                       "role": user_role}
        )
        db.add(log)
        await db.commit()
        await db.refresh(user)
        logger.info(f"New user auto-created from Keycloak: {username} ({user_role})")

    else:
        # Sync role if it changed in Keycloak
        if user.role != user_role:
            old_role   = user.role
            user.role  = user_role
            log = AuditLog(
                user_id = user.user_id,
                action  = "role_change",
                detail  = {"old_role": old_role, "new_role": user_role,
                           "source": "keycloak_sync"}
            )
            db.add(log)
            await db.commit()
            logger.info(f"Role synced for {username}: {old_role} → {user_role}")

    # Step 4 — check account is active
    if not user.is_active:
        raise HTTPException(403, "Account is disabled")

    return user
