import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES
from app.db.session import get_db
from app.db.models import User, Session

# ── Crypto setup ───────────────────────────────────────────────────────────
pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
ALGORITHM     = "HS256"


# ── Password helpers ───────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ────────────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire    = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ── Dependency: get current user ───────────────────────────────────────────

async def get_current_user(
    token: str        = Depends(oauth2_scheme),
    db:    AsyncSession = Depends(get_db)
) -> User:

    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Step 1 — decode JWT
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Step 2 — check session is not revoked
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    result     = await db.execute(
        select(Session).where(Session.token_hash == token_hash)
    )
    session = result.scalar_one_or_none()

    if session is None:
        raise credentials_exception
    if session.revoked_at is not None:
        raise HTTPException(401, "Session has been revoked")
    if session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(401, "Session has expired")

    # Step 3 — load user
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(403, "Account is disabled")
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(423, "Account temporarily locked")

    return user
