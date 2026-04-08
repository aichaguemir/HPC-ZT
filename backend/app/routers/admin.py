from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional

from app.core.auth import get_current_user, require_admin
from app.core.keycloak_admin import (
    assign_keycloak_role, remove_keycloak_role,
    delete_keycloak_user, disable_keycloak_user
)
from app.core.carta import get_known_ips
from app.db.session import get_db
from app.db.models import User, AuditLog
from app.services.ssh import run_ssh_async
from app.core.config import LSF_PATH
from app.core.logging import logger
import httpx
from app.core.config import KEYCLOAK_URL, KEYCLOAK_REALM
from app.core.logging import logger
router = APIRouter(prefix="/admin", tags=["admin"])


class RoleChangeRequest(BaseModel):
    new_role: str


# ── List all users ─────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users  = result.scalars().all()
    return {
        "users": [
            {
                "user_id":        u.user_id,
                "username":       u.username,
                "email":          u.email,
                "role":           u.role,
                "requested_role": u.requested_role,
                "is_approved":    u.is_approved,
                "is_active":      u.is_active,
                "created_at":     str(u.created_at),
                "last_login":     str(u.last_login) if u.last_login else None,
            }
            for u in users
        ]
    }


# ── List pending users ─────────────────────────────────────────────────────

@router.get("/users/pending")
async def list_pending(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    result = await db.execute(
        select(User)
        .where(User.is_approved == False)
        .order_by(User.created_at.asc())
    )
    users = result.scalars().all()
    return {
        "pending": [
            {
                "user_id":        u.user_id,
                "username":       u.username,
                "email":          u.email,
                "requested_role": u.requested_role,
                "created_at":     str(u.created_at),
            }
            for u in users
        ]
    }


# ── Approve user ───────────────────────────────────────────────────────────

@router.post("/users/{user_id}/approve")
async def approve_user(
    user_id:      str,
    request:      Request,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.user_id == user_id))
    user   = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")
    if user.is_approved:
        raise HTTPException(400, "User already approved")

    # Assign requested role in Keycloak
    role_to_assign = user.requested_role or "student"
    await assign_keycloak_role(user.keycloak_id, role_to_assign)

    # Update DB
    user.is_approved = True
    user.role        = role_to_assign

    log = AuditLog(
        user_id    = current_user.user_id,
        action     = "role_change",
        ip_address = request.client.host if request.client else None,
        detail     = {
            "target_user":  user.username,
            "action":       "approved",
            "role_granted": role_to_assign,
            "approved_by":  current_user.username,
        }
    )
    db.add(log)
    await db.commit()

    logger.info(f"User approved: {user.username} as {role_to_assign} by {current_user.username}")
    return {"message": f"User {user.username} approved as {role_to_assign}"}


# ── Reject user ────────────────────────────────────────────────────────────

@router.post("/users/{user_id}/reject")
async def reject_user(
    user_id:      str,
    request:      Request,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.user_id == user_id))
    user   = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")

    # Delete from Keycloak
    await delete_keycloak_user(user.keycloak_id)

    # Log before deleting
    log = AuditLog(
        user_id    = current_user.user_id,
        action     = "role_change",
        ip_address = request.client.host if request.client else None,
        detail     = {
            "target_user": user.username,
            "action":      "rejected",
            "rejected_by": current_user.username,
        }
    )
    db.add(log)

    # Delete from DB
    await db.delete(user)
    await db.commit()

    logger.info(f"User rejected: {user.username} by {current_user.username}")
    return {"message": f"User {user.username} rejected and removed"}


# ── Deactivate user ────────────────────────────────────────────────────────

@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id:      str,
    request:      Request,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.user_id == user_id))
    user   = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")
    if user.user_id == current_user.user_id:
        raise HTTPException(400, "Cannot deactivate yourself")

    # Disable in Keycloak
    await disable_keycloak_user(user.keycloak_id)

    # Disable in DB
    user.is_active = False

    log = AuditLog(
        user_id    = current_user.user_id,
        action     = "role_change",
        ip_address = request.client.host if request.client else None,
        detail     = {
            "target_user":    user.username,
            "action":         "deactivated",
            "deactivated_by": current_user.username,
        }
    )
    db.add(log)
    await db.commit()

    logger.info(f"User deactivated: {user.username} by {current_user.username}")
    return {"message": f"User {user.username} deactivated"}


# ── HPC Node status ────────────────────────────────────────────────────────

@router.get("/nodes")
async def get_nodes(
    current_user: User = Depends(require_admin),
):
    result = await run_ssh_async(f"{LSF_PATH}/bhosts")
    lines  = result.strip().splitlines()

    if len(lines) < 2:
        return {"nodes": []}

    nodes = []
    for line in lines[1:]:   # skip header
        parts = line.split()
        if len(parts) >= 6:
            nodes.append({
                "host":    parts[0],
                "status":  parts[1],
                "cpus":    parts[3],
                "running": parts[4],
                "max":     parts[5],
            })

    return {"nodes": nodes}
    
    


# ── Reactivate user ────────────────────────────────────────────────────────
 
@router.post("/users/{user_id}/reactivate")
async def reactivate_user(
    user_id:      str,
    request:      Request,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.user_id == user_id))
    user   = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")
    if user.is_active:
        raise HTTPException(400, "User is already active")
 
    # Re-enable in Keycloak
    token = await get_admin_token()
    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users/{user.keycloak_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True}
        )
        response.raise_for_status()
 
    # Re-enable in DB
    user.is_active = True
 
    log = AuditLog(
        user_id    = current_user.user_id,
        action     = "role_change",
        ip_address = request.client.host if request.client else None,
        detail     = {
            "target_user":    user.username,
            "action":         "reactivated",
            "reactivated_by": current_user.username,
        }
    )
    db.add(log)
    await db.commit()
 
    logger.info(f"User reactivated: {user.username} by {current_user.username}")
    return {"message": f"User {user.username} reactivated successfully"}
 
 
# ── Revoke approval (back to pending) ─────────────────────────────────────
 
@router.post("/users/{user_id}/revoke")
async def revoke_user(
    user_id:      str,
    request:      Request,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.user_id == user_id))
    user   = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")
    if user.user_id == current_user.user_id:
        raise HTTPException(400, "Cannot revoke yourself")
    if not user.is_approved:
        raise HTTPException(400, "User is already pending")
 
    # Remove role from Keycloak
    if user.role in ("student", "researcher", "admin"):
        await remove_keycloak_role(user.keycloak_id, user.role)
 
    # Set back to pending in DB
    user.is_approved = False
    user.role        = "student"  # minimum role
 
    log = AuditLog(
        user_id    = current_user.user_id,
        action     = "role_change",
        ip_address = request.client.host if request.client else None,
        detail     = {
            "target_user": user.username,
            "action":      "revoked",
            "revoked_by":  current_user.username,
        }
    )
    db.add(log)
    await db.commit()
 
    logger.info(f"User revoked: {user.username} by {current_user.username}")
    return {"message": f"User {user.username} access revoked. Status set to pending."}
 
 
# ── REPLACE your existing change_role with this version ───────────────────
# (adds single-admin enforcement)
 
@router.put("/users/{user_id}/role")
async def change_role(
    user_id:      str,
    body:         RoleChangeRequest,
    request:      Request,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    valid_roles = {"student", "researcher", "admin"}
    if body.new_role not in valid_roles:
        raise HTTPException(400, f"Invalid role. Choose: {', '.join(valid_roles)}")
 
    result = await db.execute(select(User).where(User.user_id == user_id))
    user   = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")
 
    # ── Single admin enforcement ───────────────────────────────────────────
    if body.new_role == "admin":
        existing_admin_result = await db.execute(
            select(User)
            .where(User.role == "admin")
            .where(User.user_id != user_id)
        )
        if existing_admin_result.scalar_one_or_none():
            raise HTTPException(
                400,
                "System already has an admin. "
                "Revoke the existing admin's role first before assigning a new one."
            )
 
    old_role = user.role
 
    # Remove old role, assign new in Keycloak
    if old_role in valid_roles:
        await remove_keycloak_role(user.keycloak_id, old_role)
    await assign_keycloak_role(user.keycloak_id, body.new_role)
 
    # Update DB
    user.role = body.new_role
 
    log = AuditLog(
        user_id    = current_user.user_id,
        action     = "role_change",
        ip_address = request.client.host if request.client else None,
        detail     = {
            "target_user": user.username,
            "old_role":    old_role,
            "new_role":    body.new_role,
            "changed_by":  current_user.username,
        }
    )
    db.add(log)
    await db.commit()
 
    logger.info(f"Role: {user.username} {old_role}→{body.new_role} by {current_user.username}")
    return {"message": f"Role changed from {old_role} to {body.new_role}"}
    


@router.get("/users/{user_id}/ips")
async def get_user_ips(
    user_id:      str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    ips = await get_known_ips(user_id, db)
    return {"user_id": user_id, "known_ips": ips}
    
    
@router.get("/users/{user_id}/ips")
async def get_user_ips(
    user_id:      str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    from app.db.models import UserKnownIP
    result = await db.execute(
        select(UserKnownIP)
        .where(UserKnownIP.user_id == user_id)
        .order_by(UserKnownIP.last_seen.desc())
    )
    ips = result.scalars().all()
    return {
        "ips": [
            {
                "ip":         i.ip_address,
                "verified":   i.verified,
                "first_seen": str(i.first_seen),
                "last_seen":  str(i.last_seen),
            }
            for i in ips
        ]
    }    
    
 

