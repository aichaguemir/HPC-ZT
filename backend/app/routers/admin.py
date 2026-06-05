from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.auth import get_current_user, require_admin
from app.core.keycloak_admin import (
    assign_keycloak_role, remove_keycloak_role,
    delete_keycloak_user, disable_keycloak_user,
    get_admin_token,
)
from app.core.audit_chain import write_audit_entry, verify_chain
from app.core.carta import get_known_ips
from app.db.session import get_db
from app.db.models import User, AuditLog, UserKnownIP, Job
from app.services.ssh import run_ssh_async
from app.core.config import LSF_PATH, KEYCLOAK_URL, KEYCLOAK_REALM
from app.core.logging import logger
from app.core.audit_chain import verify_chain, verify_anchors, verify_full

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
                "document_url":   f"/uploads/{u.document_path}" if u.document_path else None, 
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

    role_to_assign = user.requested_role or "student"
    await assign_keycloak_role(user.keycloak_id, role_to_assign)

    user.is_approved = True
    user.role        = role_to_assign
    user.email_otp_verified = False 

    await write_audit_entry(
        db         = db,
        action     = "role_change",
        result     = "success",
        user_id    = current_user.user_id,
        ip_address = request.client.host if request.client else None,
        detail     = {
            "target_user":  user.username,
            "action":       "approved",
            "role_granted": role_to_assign,
            "approved_by":  current_user.username,
        }
    )
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

    await delete_keycloak_user(user.keycloak_id)

    await write_audit_entry(
        db         = db,
        action     = "role_change",
        result     = "success",
        user_id    = current_user.user_id,
        ip_address = request.client.host if request.client else None,
        detail     = {
            "target_user": user.username,
            "action":      "rejected",
            "rejected_by": current_user.username,
        }
    )

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

    await disable_keycloak_user(user.keycloak_id)
    user.is_active = False

    await write_audit_entry(
        db         = db,
        action     = "role_change",
        result     = "success",
        user_id    = current_user.user_id,
        ip_address = request.client.host if request.client else None,
        detail     = {
            "target_user":    user.username,
            "action":         "deactivated",
            "deactivated_by": current_user.username,
        }
    )
    await db.commit()

    logger.info(f"User deactivated: {user.username} by {current_user.username}")
    return {"message": f"User {user.username} deactivated"}


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

    token = await get_admin_token()
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.put(
            f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users/{user.keycloak_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True},
            
        )
        response.raise_for_status()

    user.is_active = True

    await write_audit_entry(
        db         = db,
        action     = "role_change",
        result     = "success",
        user_id    = current_user.user_id,
        ip_address = request.client.host if request.client else None,
        detail     = {
            "target_user":    user.username,
            "action":         "reactivated",
            "reactivated_by": current_user.username,
        }
    )
    await db.commit()

    logger.info(f"User reactivated: {user.username} by {current_user.username}")
    return {"message": f"User {user.username} reactivated successfully"}


# ── Revoke approval ────────────────────────────────────────────────────────

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

    if user.role in ("student", "researcher", "admin"):
        await remove_keycloak_role(user.keycloak_id, user.role)

    user.is_approved = False
    user.role        = "student"

    await write_audit_entry(
        db         = db,
        action     = "role_change",
        result     = "success",
        user_id    = current_user.user_id,
        ip_address = request.client.host if request.client else None,
        detail     = {
            "target_user": user.username,
            "action":      "revoked",
            "revoked_by":  current_user.username,
        }
    )
    await db.commit()

    logger.info(f"User revoked: {user.username} by {current_user.username}")
    return {"message": f"User {user.username} access revoked. Status set to pending."}


# ── Change role ────────────────────────────────────────────────────────────

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

    if body.new_role == "admin":
        existing_admin = await db.execute(
            select(User)
            .where(User.role == "admin")
            .where(User.user_id != user_id)
        )
        if existing_admin.scalar_one_or_none():
            raise HTTPException(400,
                "System already has an admin. "
                "Revoke existing admin first.")

    old_role = user.role
    if old_role in valid_roles:
        await remove_keycloak_role(user.keycloak_id, old_role)
    await assign_keycloak_role(user.keycloak_id, body.new_role)
    user.role = body.new_role

    await write_audit_entry(
        db         = db,
        action     = "role_change",
        result     = "success",
        user_id    = current_user.user_id,
        ip_address = request.client.host if request.client else None,
        detail     = {
            "target_user": user.username,
            "old_role":    old_role,
            "new_role":    body.new_role,
            "changed_by":  current_user.username,
        }
    )
    await db.commit()

    logger.info(f"Role: {user.username} {old_role}→{body.new_role} by {current_user.username}")
    return {"message": f"Role changed from {old_role} to {body.new_role}"}


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
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 6:
            nodes.append({
                "host":        parts[0],
                "status":      parts[1],
                "max_cpus":    parts[3],   # MAX
                "running_jobs": parts[5],  # RUN
                "total_jobs":  parts[4],   # NJOBS (includes suspended)
                "utilization": f"{int(parts[5])/int(parts[3])*100:.0f}%" 
                               if parts[3] != "0" else "0%"
})
    return {"nodes": nodes}


# ── User known IPs ─────────────────────────────────────────────────────────

@router.get("/users/{user_id}/ips")
async def get_user_ips(
    user_id:      str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
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



# ── Audit logs ─────────────────────────────────────────────────────────────

@router.get("/audit/logs")
async def get_audit_logs(
    limit:        int          = 50,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    result = await db.execute(
        select(AuditLog, User.username)
        .outerjoin(User, AuditLog.user_id == User.user_id)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
    )
    rows = result.all()
    return {
        "logs": [
            {
                "log_id":     str(l.log_id),
                "action":     l.action,
                "result":     l.result,
                "username":   username or "deleted_user",  # ← name not ID
                "user_id":    str(l.user_id) if l.user_id else None,
                "job_id":     l.job_id,
                "ip_address": l.ip_address,
                "detail":     l.detail,
                "chain_hash": l.chain_hash[:16] + "..." if l.chain_hash else None,
                "timestamp":  str(l.timestamp),
            }
            for l, username in rows
        ]
    }
    


# ── Flagged jobs ───────────────────────────────────────────────────────────

@router.get("/jobs/flagged")
async def list_flagged_jobs(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    result = await db.execute(
        select(Job, User.username)
        .join(User, Job.user_id == User.user_id)
        .where(Job.is_flagged == True)
        .order_by(Job.flagged_at.desc())
    )
    rows = result.all()

    return {
        "total": len(rows),
        "flagged_jobs": [
            {
                "job_id":       job.job_id,
                "username":     username,
                "queue":        job.queue,
                "cores":        job.cores,
                "memory":       job.memory,
                "status":       job.status,
                "flag_reason":  job.flag_reason,
                "flagged_at":   str(job.flagged_at),
                "submitted_at": str(job.submitted_at),
            }
            for job, username in rows
        ],
    }
     
     




# ── Add these three endpoints to admin.py ─────────────────────────────────

@router.get("/audit/verify")
async def audit_verify_chain(
    db:    AsyncSession = Depends(get_db),
    admin: User         = Depends(require_admin),
):
    """
    Verify local HMAC chain integrity.
    Property 1 (detection) + Property 2 (resistance).
    """
    return await verify_chain(db)


@router.get("/audit/verify/anchors")
async def audit_verify_anchors(
    db:    AsyncSession = Depends(get_db),
    admin: User         = Depends(require_admin),
):
    """
    Verify external anchor consistency.
    Property 3 (external independence).
    Checks that current chain hashes match anchor file records.
    """
    return await verify_anchors(db)


@router.get("/audit/verify/full")
async def audit_verify_full(
    db:    AsyncSession = Depends(get_db),
    admin: User         = Depends(require_admin),
):
    """
    Complete audit integrity verification.
    Checks all three properties simultaneously:
      - Tamper detection    (HMAC chain)
      - Tamper resistance   (HMAC secret required)
      - External independence (anchor file consistency)

    Use this for the paper demo.
    """
    return await verify_full(db)
     
