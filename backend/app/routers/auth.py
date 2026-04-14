from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr

from app.core.auth import get_current_user, get_current_user_and_token, require_admin
from app.core.keycloak_admin import create_keycloak_user
from app.core.audit_chain import write_audit_entry
from app.core.config import KEYCLOAK_URL, KEYCLOAK_REALM
from app.db.session import get_db
from app.db.models import User
from app.schemas.users import UserResponse
import pyotp, qrcode, io, base64

router = APIRouter(prefix="/auth", tags=["auth"])

VALID_ROLES = {"student", "researcher"}


class RegisterRequest(BaseModel):
    username:       str
    email:          EmailStr
    password:       str
    requested_role: str = "student"
    first_name:     str = ""
    last_name:      str = ""


class TOTPConfirmRequest(BaseModel):
    code: str


class TOTPVerifyRequest(BaseModel):
    code: str


# ── Register ───────────────────────────────────────────────────────────────

@router.post("/register", status_code=202)
async def register(
    body:    RegisterRequest,
    request: Request,
    db:      AsyncSession = Depends(get_db)
):
    if body.requested_role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role. Choose: {', '.join(VALID_ROLES)}")

    existing = await db.execute(
        select(User).where(User.username == body.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Username already registered")

    try:
        keycloak_id = await create_keycloak_user(
            username   = body.username,
            email      = body.email,
            password   = body.password,
            first_name = body.first_name or body.username,
            last_name  = body.last_name or "User",
            enabled    = True,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    new_user = User(
        keycloak_id    = keycloak_id,
        username       = body.username,
        email          = body.email,
        role           = "student",
        requested_role = body.requested_role,
        is_approved    = False,
        is_active      = True,
        totp_enabled   = False,
    )
    db.add(new_user)
    await db.flush()

    await write_audit_entry(
        db         = db,
        action     = "register",
        result     = "success",
        user_id    = new_user.user_id,
        ip_address = request.client.host if request.client else None,
        detail     = {
            "username":       body.username,
            "email":          body.email,
            "requested_role": body.requested_role,
            "status":         "pending",
        }
    )
    await db.commit()

    return {
        "message":        "Registration successful. Awaiting admin approval.",
        "username":       body.username,
        "requested_role": body.requested_role,
    }


# ── Admin: approve user ────────────────────────────────────────────────────

@router.post("/admin/approve/{user_id}")
async def approve_user(
    user_id: str,
    request: Request,
    db:      AsyncSession = Depends(get_db),
    admin:   User         = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.user_id == user_id))
    target = result.scalar_one_or_none()

    if target is None:
        raise HTTPException(404, "User not found")
    if target.is_approved:
        raise HTTPException(400, "User is already approved")

    # Generate temp secret now — totp_enabled stays False until user confirms
    secret = pyotp.random_base32()
    target.temp_totp_secret = secret
    target.totp_enabled     = False
    target.is_approved      = True

    if target.requested_role and target.requested_role != target.role:
        target.role = target.requested_role

    await write_audit_entry(
        db         = db,
        action     = "role_change",
        result     = "success",
        user_id    = target.user_id,
        ip_address = request.client.host if request.client else None,
        detail     = {
            "approved_by":       admin.username,
            "new_role":          target.role,
            "totp_secret_ready": True,
            "totp_active":       False,
            "note":              "User must scan QR and confirm before TOTP activates",
        }
    )
    await db.commit()

    return {
        "message":     f"User '{target.username}' approved.",
        "role":        target.role,
        "totp_status": "pending_user_setup",
        "next_step":   "User must complete TOTP setup on first login.",
    }


# ── Me ─────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


# ── Logout ─────────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(
    request:      Request,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    await write_audit_entry(
        db         = db,
        action     = "logout",
        result     = "success",
        user_id    = current_user.user_id,
        ip_address = request.client.host if request.client else None,
        detail     = {"username": current_user.username}
    )
    await db.commit()

    return {
        "message": "Logged out successfully.",
        "keycloak_logout_url": (
            f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
            f"/protocol/openid-connect/logout"
        )
    }


# ── TOTP Setup — Step 1: Show QR ───────────────────────────────────────────

@router.get("/totp/setup")
async def get_totp_setup(
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    if current_user.totp_enabled and current_user.totp_secret:
        return {"already_configured": True}

    # Safety net — regenerate if missing (e.g. legacy account)
    if not current_user.temp_totp_secret:
        current_user.temp_totp_secret = pyotp.random_base32()
        await db.commit()
        await db.refresh(current_user)

    totp = pyotp.TOTP(current_user.temp_totp_secret)
    uri  = totp.provisioning_uri(
        name        = current_user.email,
        issuer_name = "HPC-Gateway"
    )
    img    = qrcode.make(uri)
    buf    = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return {
        "already_configured": False,
        "qr_code": f"data:image/png;base64,{qr_b64}",
        "secret":  current_user.temp_totp_secret,
        "instructions": (
            "1. Open Google Authenticator. "
            "2. Scan the QR code or enter the secret manually. "
            "3. POST {\"code\": \"123456\"} to /auth/totp/confirm-setup."
        ),
    }


# ── TOTP Setup — Step 2: Confirm scan ─────────────────────────────────────
# FIX: body is JSON, not a query param.
# Before: POST /totp/confirm-setup?code=123456  → 422 Unprocessable Entity
# After:  POST /totp/confirm-setup
#         Content-Type: application/json
#         {"code": "123456"}              → 200 OK

@router.post("/totp/confirm-setup")
async def confirm_totp_setup(
    body:         TOTPConfirmRequest,   # ← JSON body, NOT a query param
    request:      Request,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    if not current_user.temp_totp_secret:
        raise HTTPException(
            400,
            "No pending TOTP setup found. Call GET /auth/totp/setup first."
        )

    if current_user.totp_enabled:
        raise HTTPException(400, "Authenticator is already configured.")

    totp = pyotp.TOTP(current_user.temp_totp_secret)
    if not totp.verify(body.code, valid_window=1):
        await write_audit_entry(
            db         = db,
            action     = "login",
            result     = "totp_setup_failed",
            user_id    = current_user.user_id,
            ip_address = request.client.host if request.client else None,
            detail     = {"reason": "invalid_code_during_setup"}
        )
        await db.commit()
        raise HTTPException(
            401,
            "Invalid code. Make sure your phone's time is correct and try again."
        )

    # ✅ Verified — promote temp → permanent and activate
    current_user.totp_secret      = current_user.temp_totp_secret
    current_user.temp_totp_secret = None
    current_user.totp_enabled     = True

    await write_audit_entry(
        db         = db,
        action     = "login",
        result     = "totp_setup_confirmed",
        user_id    = current_user.user_id,
        ip_address = request.client.host if request.client else None,
        detail     = {"method": "totp_setup", "status": "activated"}
    )
    await db.commit()

    return {
        "message": (
            "Authenticator successfully configured. "
            "Two-factor authentication is now active on your account."
        )
    }


# ── TOTP Verify — step-up MFA for risky job submissions ───────────────────
# FIX: use get_current_user_and_token so we have the token to look up
#      the session and stamp totp_verified_at on it.

@router.post("/totp/verify")
async def verify_totp(
    body:                  TOTPVerifyRequest,
    request:               Request,
    current_user_and_token = Depends(get_current_user_and_token),  # ← FIXED
    db:                    AsyncSession = Depends(get_db),
):
    current_user, token = current_user_and_token

    if not current_user.totp_enabled or not current_user.totp_secret:
        raise HTTPException(
            400,
            "Authenticator not configured. "
            "Please complete setup at /auth/totp/setup first."
        )

    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(401, "Invalid code. Check your authenticator app.")

    # Stamp the session so jobs.py knows MFA was recently verified
    from app.core.carta import get_or_create_session, mark_ip_verified
    session = await get_or_create_session(current_user, token, request, db)
    session.totp_verified_at = datetime.now(timezone.utc)  # ← stamps the session

    ip = request.client.host if request.client else "unknown"
    await mark_ip_verified(current_user.user_id, ip, db)

    await write_audit_entry(
        db         = db,
        action     = "login",
        result     = "mfa_verified",
        user_id    = current_user.user_id,
        ip_address = ip,
        detail     = {"mfa_method": "totp", "ip_verified": ip}
    )
    await db.commit()

    return {
        "verified": True,
        "message":  "MFA verified. IP registered as trusted.",
    }
