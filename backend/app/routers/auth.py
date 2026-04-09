from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr

from app.core.auth import get_current_user
from app.core.keycloak_admin import create_keycloak_user
from app.core.audit_chain import write_audit_entry
from app.core.config import KEYCLOAK_URL, KEYCLOAK_REALM
from app.db.session import get_db
from app.db.models import User
from app.schemas.users import UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

VALID_ROLES = {"student", "researcher"}


class RegisterRequest(BaseModel):
    username:       str
    email:          EmailStr
    password:       str
    requested_role: str = "student"
    first_name:     str = ""
    last_name:      str = ""


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

    # ── Audit chain entry ──────────────────────────────────────────────────
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
            "status":         "pending"
        }
    )
    await db.commit()

    return {
        "message":        "Registration successful. Awaiting admin approval.",
        "username":       body.username,
        "requested_role": body.requested_role,
    }


# ── Me ─────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user)
):
    return UserResponse.model_validate(current_user)


# ── Logout ─────────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(
    request:      Request,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    # ── Audit chain entry ──────────────────────────────────────────────────
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
