from fastapi import APIRouter, Depends
from app.core.auth import get_current_user
from app.db.models import User
from app.schemas.users import UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Me (protected) ─────────────────────────────────────────────────────────
# Register and Login are handled by Keycloak — not by this API

@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user)
):
    return UserResponse.model_validate(current_user)
