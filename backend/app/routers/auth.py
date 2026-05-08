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






















import secrets
from app.core.email_otp import send_otp, verify_otp

class EmailOTPRequest(BaseModel):
    code: str


# ── Email OTP — Send code ──────────────────────────────────────────────────

@router.post("/mfa/send-code")
async def send_mfa_code(
    request:      Request,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    await send_otp(current_user, db)
    return {
        "message": f"Verification code sent to {current_user.email}. "
                   f"Check Mailhog at http://localhost:8025",
        "expires_in_minutes": 10,
    }


# ── Email OTP — Verify code ────────────────────────────────────────────────

@router.post("/mfa/verify-code")
async def verify_mfa_code(
    body:                   EmailOTPRequest,
    request:                Request,
    current_user_and_token  = Depends(get_current_user_and_token),
    db:                     AsyncSession = Depends(get_db),
):
    current_user, token = current_user_and_token

    if not verify_otp(current_user, body.code):
        await write_audit_entry(
            db         = db,
            action     = "login",
            result     = "mfa_failed",
            user_id    = current_user.user_id,
            ip_address = request.client.host if request.client else None,
            detail     = {"reason": "invalid_or_expired_otp"}
        )
        await db.commit()
        raise HTTPException(401, "Invalid or expired code. Request a new one.")

    # Clear the code after use
    current_user.email_otp_code       = None
    current_user.email_otp_expires_at = None
    current_user.email_otp_verified   = True

    # Stamp the session
    from app.core.carta import get_or_create_session, mark_ip_verified
    session = await get_or_create_session(current_user, token, request, db)
    session.totp_verified_at = datetime.now(timezone.utc)

    ip = request.client.host if request.client else "unknown"
    await mark_ip_verified(current_user.user_id, ip, db)

    await write_audit_entry(
        db         = db,
        action     = "login",
        result     = "mfa_verified",
        user_id    = current_user.user_id,
        ip_address = ip,
        detail     = {"mfa_method": "email_otp", "ip_verified": ip}
    )
    await db.commit()

    return {
        "verified": True,
        "message":  "MFA verified. You can now proceed.",
    }
