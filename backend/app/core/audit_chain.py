"""
Cryptographic Audit Chain
H_0 = SHA-256(CHAIN_SEED)
H_i = SHA-256(H_{i-1} || timestamp_i || user_i || action_i || result_i || detail_i)

Provides tamper-evident audit logging.
Any modification to a past entry breaks the chain from that point forward.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import AuditLog
from app.core.logging import logger

# Genesis seed
CHAIN_SEED = "HPC-GATEWAY-ZTA-AUDIT-CHAIN-V1"


async def get_last_hash(db: AsyncSession) -> str:
    """
    Returns chain_hash of the most recent audit entry.
    If no entries exist, returns H_0 = SHA-256(CHAIN_SEED).
    """
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.chain_hash.isnot(None))
        .order_by(AuditLog.timestamp.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()

    if last is None:
        return hashlib.sha256(CHAIN_SEED.encode()).hexdigest()

    return last.chain_hash


def compute_hash(
    prev_hash: str,
    timestamp: datetime,
    user_id:   str,
    action:    str,
    result:    str,
    detail:    dict,
) -> str:
    """
    H_i = SHA-256(H_{i-1} || timestamp || user_id || action || result || detail)
    Uses canonical JSON for reproducibility.
    """
    content = json.dumps({
        "prev_hash": prev_hash,
        "timestamp": timestamp.isoformat(),
        "user_id":   user_id or "anonymous",
        "action":    action,
        "result":    result or "success",
        "detail":    detail or {},
    }, sort_keys=True, separators=(',', ':'))

    return hashlib.sha256(content.encode()).hexdigest()


async def write_audit_entry(
    db:         AsyncSession,
    action:     str,
    result:     str                = "success",
    user_id:    Optional[str]      = None,
    job_id:     Optional[str]      = None,
    ip_address: Optional[str]      = None,
    detail:     Optional[dict]     = None,
) -> AuditLog:
    """
    Write a cryptographically chained audit log entry.
    Replaces all direct db.add(AuditLog(...)) calls.

    Usage:
        await write_audit_entry(
            db         = db,
            action     = "job_submit",
            result     = "success",
            user_id    = current_user.user_id,
            job_id     = job_id,
            ip_address = request.client.host,
            detail     = {"cores": 4, "queue": "low_priority"}
        )
        await db.commit()
    """
    now       = datetime.now(timezone.utc)
    prev_hash = await get_last_hash(db)

    h_i = compute_hash(
        prev_hash = prev_hash,
        timestamp = now,
        user_id   = user_id or "anonymous",
        action    = action,
        result    = result or "success",
        detail    = detail or {},
    )

    entry = AuditLog(
        user_id    = user_id,
        job_id     = job_id,
        action     = action,
        result     = result,
        ip_address = ip_address,
        detail     = detail,
        chain_hash = h_i,
        prev_hash  = prev_hash,
        timestamp  = now,
    )
    db.add(entry)
    logger.debug(f"Audit chain: action={action} H_i={h_i[:16]}...")
    return entry


async def verify_chain(db: AsyncSession) -> dict:
    """
    Verifies the full audit chain integrity.
    Recomputes every hash and checks it matches what was stored.

    Returns:
        {"valid": True, "entries_checked": N}
        or
        {"valid": False, "broken_at": log_id, "reason": "..."}
    """
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.chain_hash.isnot(None))
        .order_by(AuditLog.timestamp.asc())
    )
    entries = result.scalars().all()

    if not entries:
        return {
            "valid":           True,
            "entries_checked": 0,
            "message":         "No chained entries yet"
        }

    expected_prev = hashlib.sha256(CHAIN_SEED.encode()).hexdigest()

    for entry in entries:
        # Check prev_hash links correctly
        if entry.prev_hash != expected_prev:
            logger.error(
                f"AUDIT CHAIN BROKEN at log_id={entry.log_id} "
                f"prev_hash mismatch"
            )
            return {
                "valid":      False,
                "broken_at":  str(entry.log_id),
                "timestamp":  str(entry.timestamp),
                "action":     entry.action,
                "reason":     "prev_hash_mismatch",
            }

        # Recompute H_i and verify
        expected_hash = compute_hash(
            prev_hash = entry.prev_hash,
            timestamp = entry.timestamp,
            user_id   = entry.user_id or "anonymous",
            action    = entry.action,
            result    = entry.result or "success",
            detail    = entry.detail or {},
        )

        if expected_hash != entry.chain_hash:
            logger.error(
                f"AUDIT CHAIN TAMPERED at log_id={entry.log_id}"
            )
            return {
                "valid":      False,
                "broken_at":  str(entry.log_id),
                "timestamp":  str(entry.timestamp),
                "action":     entry.action,
                "reason":     "hash_mismatch — entry was modified",
            }

        expected_prev = entry.chain_hash

    return {
        "valid":           True,
        "entries_checked": len(entries),
        "latest_hash":     entries[-1].chain_hash[:16] + "...",
        "message":         "Audit chain integrity verified"
    }
