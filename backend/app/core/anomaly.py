"""
CARTA Anomaly Detection Engine
Computes risk score ρ for each job submission.
ρ ≥ θ (threshold) → flag job + trigger MFA step-up

Risk Signals:
  R1 — Resource Anomaly    cpu/mem/walltime exceeds safe limits
  R2 — Location Anomaly    IP not seen in last 30 days
  R4 — Temporal Anomaly    submission outside 06:00-22:00
  R5 — Rate Anomaly        too many submissions per 60 seconds
  R7 — Credential Risk     recent failed login attempts
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import Request

from app.db.models import Job, AuditLog, User, Policy
from app.core.logging import logger


# ── Thresholds ─────────────────────────────────────────────────────────────

RESOURCE_MAX_CORES    = 16      # cores
RESOURCE_MAX_MEMORY   = 64000   # MB (64GB)
RESOURCE_MAX_WALLTIME = 48      # hours

RATE_THRESHOLDS = {
    "student":    2,    # max submissions per 60 seconds
    "researcher": 5,
    "admin":      10,
}

# ρ ≥ this → flag job + require MFA step-up
RISK_FLAG_THRESHOLD = 40

# Score weights per signal
WEIGHTS = {
    "R1_cores":    20,
    "R1_memory":   20,
    "R1_walltime": 20,
    "R2_location": 30,
    "R4_temporal": 20,
    "R5_rate":     25,
    "R7_cred":     15,
}


# ── Main scorer ────────────────────────────────────────────────────────────

async def compute_anomaly_score(
    job:     Job,
    user:    User,
    policy:  Policy,
    db:      AsyncSession,
    request: Request,
) -> dict:
    """
    Computes risk score ρ for this job submission.
    Returns score, signals detected, and whether MFA is needed.
    """
    score   = 0
    signals = []
    now     = datetime.now(timezone.utc)
    ip      = request.client.host if request and request.client else "unknown"

    # ── R1: Resource Anomaly ───────────────────────────────────────────────
    # Flags jobs that request excessive resources beyond safe operational limits
    wall_hours = int(job.wall_time.split(':')[0])

    if job.cores > RESOURCE_MAX_CORES:
        score += WEIGHTS["R1_cores"]
        signals.append(f"R1:cores={job.cores}>{RESOURCE_MAX_CORES}")

    if job.memory > RESOURCE_MAX_MEMORY:
        score += WEIGHTS["R1_memory"]
        signals.append(f"R1:memory={job.memory}MB>{RESOURCE_MAX_MEMORY}MB")

    if wall_hours > RESOURCE_MAX_WALLTIME:
        score += WEIGHTS["R1_walltime"]
        signals.append(f"R1:walltime={wall_hours}h>{RESOURCE_MAX_WALLTIME}h")

    # ── R2: Location Anomaly ───────────────────────────────────────────────
    # Flags submissions from IP addresses not seen in the last 30 days
    known_ips_result = await db.execute(
        select(AuditLog.ip_address)
        .where(AuditLog.user_id == user.user_id)
        .where(AuditLog.action == "login")
        .where(AuditLog.timestamp >= now - timedelta(days=30))
        .distinct()
    )
    known_ips = {row[0] for row in known_ips_result.fetchall() if row[0]}

    if known_ips and ip not in known_ips:
        score += WEIGHTS["R2_location"]
        signals.append(f"R2:new_ip={ip}")
    elif not known_ips:
        # No login history at all — first time user
        score += WEIGHTS["R2_location"] // 2
        signals.append("R2:no_login_history")

    # ── R4: Temporal Anomaly ───────────────────────────────────────────────
    # Flags submissions outside normal working hours (06:00 - 22:00 UTC)
    if now.hour < 6 or now.hour >= 22:
        score += WEIGHTS["R4_temporal"]
        signals.append(f"R4:off_hours={now.hour:02d}:00_UTC")

    # ── R5: Rate Anomaly ───────────────────────────────────────────────────
    # Flags users submitting too many jobs per 60 seconds for their role
    threshold = RATE_THRESHOLDS.get(user.role, 2)

    rate_result = await db.execute(
        select(func.count(Job.job_id))
        .where(Job.user_id == user.user_id)
        .where(Job.submitted_at >= now - timedelta(seconds=60))
    )
    recent_count = rate_result.scalar()

    if recent_count >= threshold:
        score += WEIGHTS["R5_rate"]
        signals.append(
            f"R5:rate={recent_count}jobs/60s>threshold({threshold})"
        )

    # ── R7: Credential Risk ────────────────────────────────────────────────
    # Flags users with recent failed login attempts (last 10 minutes)
    if user.failed_attempts > 0:
        recent_fails = await db.execute(
            select(func.count(AuditLog.log_id))
            .where(AuditLog.user_id == user.user_id)
            .where(AuditLog.action == "login_failed")
            .where(AuditLog.timestamp >= now - timedelta(minutes=10))
        )
        if recent_fails.scalar() > 0:
            score += WEIGHTS["R7_cred"]
            signals.append(
                f"R7:failed_attempts={user.failed_attempts}_in_last_10min"
            )

    # ── Final result ───────────────────────────────────────────────────────
    final_score = min(score, 100)
    flagged     = final_score >= RISK_FLAG_THRESHOLD
    mfa_needed  = flagged

    return {
        "score":      final_score,
        "signals":    signals,
        "flagged":    flagged,
        "mfa_needed": mfa_needed,
        "threshold":  RISK_FLAG_THRESHOLD,
    }


async def apply_anomaly_result(
    job:    Job,
    result: dict,
    db:     AsyncSession,
) -> None:
    """
    Applies the anomaly detection result to the job record.
    Flags it in DB if score exceeds threshold.
    """
    if result["flagged"]:
        job.is_flagged  = True
        job.flag_reason = " | ".join(result["signals"])
        job.flagged_at  = datetime.now(timezone.utc)
        await db.commit()

        logger.warning(
            f"ANOMALY DETECTED: job={job.job_id} "
            f"score={result['score']}/{result['threshold']} "
            f"signals={result['signals']}"
        )
