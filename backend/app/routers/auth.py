import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.core.auth import (
    hash_password, verify_password,
    create_access_token, get_current_user
)
from app.db.session import get_db
from app.db.models import User, Session, AuditLog
from app.schemas.users import UserCreate, UserResponse, TokenResponse, LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Register ───────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    user_in: UserCreate,
    request: Request,
    db:      AsyncSession = Depends(get_db)
):
    existing = await db.execute(
        select(User).where(User.username == user_in.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Username already registered")

    existing = await db.execute(
        select(User).where(User.email == user_in.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    new_user = User(
        username        = user_in.username,
        email           = user_in.email,
        hashed_password = hash_password(user_in.password),
        keycloak_id     = f"local_{user_in.username}",
        role            = "student",
    )
    db.add(new_user)
    await db.flush()

    log = AuditLog(
        user_id    = new_user.user_id,
        action     = "register",
        ip_address = request.client.host if request.client else None,
        detail     = {"username": user_in.username, "email": user_in.email}
    )
    db.add(log)
    await db.commit()
    await db.refresh(new_user)

    return UserResponse.model_validate(new_user)


# ── Login ──────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    request:    Request,
    login_data: LoginRequest,
    db:         AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.username == login_data.username)
    )
    user = result.scalar_one_or_none()

    if user and user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(423, "Account temporarily locked. Try again later.")

    if not user or not verify_password(login_data.password, user.hashed_password):
        if user:
            user.failed_attempts += 1
            if user.failed_attempts >= 5:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
            log = AuditLog(
                user_id    = user.user_id,
                action     = "login_failed",
                ip_address = request.client.host if request.client else None,
                detail     = {"failed_attempts": user.failed_attempts}
            )
            db.add(log)
            await db.commit()
        raise HTTPException(401, "Invalid username or password")

    user.failed_attempts = 0
    user.locked_until    = None
    user.last_login      = datetime.now(timezone.utc)

    token      = create_access_token({"sub": user.user_id})
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    session = Session(
        user_id     = user.user_id,
        token_hash  = token_hash,
        ip_address  = request.client.host if request.client else None,
        device_info = {"user_agent": request.headers.get("user-agent", "unknown")},
        expires_at  = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    db.add(session)

    log = AuditLog(
        user_id    = user.user_id,
        action     = "login",
        ip_address = request.client.host if request.client else None,
        detail     = {"username": user.username}
    )
    db.add(log)
    await db.commit()

    return TokenResponse(access_token=token)


# ── Me ─────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user)
):
    return UserResponse.model_validate(current_user)
