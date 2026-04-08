"""
CARTA — Continuous Adaptive Risk and Trust Assessment Engine
Complete implementation with:
  - Per-request signal collection (R1, R2, R4, R5, R7, R8)
  - Attack pattern correlation bonuses
  - Session-based risk accumulation
  - Risk decay on verified clean behavior

Architecture (3 layers):
  Layer 1: Signal Collection  → what happened?
  Layer 2: Risk Scoring       → how dangerous is it?
  Layer 3: Action Engine      → what do we do about it?
"""
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from fastapi import Request

from app.db.models import Job, AuditLog, User, Policy, UserKnownIP, Session
from app.core.logging import logger
from app.services.ssh import run_ssh_async
from app.core.config import LSF_PATH, KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_CLIENT_ID
from app.core.utils import get_client_ip


# ══════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════

RISK_FLAG_THRESHOLD = 40      # ρ ≥ 40 → flag + MFA
CLUSTER_THRESHOLD   = 85.0    # % cluster load

# Signal weights
WEIGHTS = {
    "R1_cores":    20,
    "R1_memory":   20,
    "R1_walltime": 20,
    "R2_location": 30,
    "R4_temporal": 20,
    "R5_rate":     25,
    "R7_cred":     15,
    "R8_cluster":  20,
}

# Attack pattern combo bonuses
# Triggered when BOTH signals are active in same request
COMBO_BONUSES = {
    ("R2_location", "R7_cred"):  40,   # new IP + failed logins → account takeover
    ("R4_temporal", "R5_rate"):  25,   # off-hours + high rate → automated attack
    ("R2_location", "R5_rate"):  20,   # new IP + high rate → scripted attack
    ("R1_cores",    "R2_location"): 15, # heavy job from new IP → resource abuse
}

# Rate limits per role (jobs per 60 seconds)
RATE_THRESHOLDS = {
    "student":    2,
    "researcher": 5,
    "admin":      10,
}

# Resource hard limits for anomaly detection
RESOURCE_MAX_CORES    = 16
RESOURCE_MAX_MEMORY   = 64000   # MB
RESOURCE_MAX_WALLTIME = 48      # hours

# Session scoring weights
ALPHA        = 0.6   # weight for peak score
BETA         = 0.4   # weight for average score
DECAY_FACTOR = 0.9   # per clean request decay


# ══════════════════════════════════════════════════════════════════════════
# CLUSTER LOAD CACHE
# ══════════════════════════════════════════════════════════════════════════

_cluster_cache: dict = {"value": 0.0, "updated": None}


async def get_cluster_utilization() -> float:
    """Cached cluster CPU utilization. Refreshes every 5 minutes."""
    global _cluster_cache
    now = datetime.now(timezone.utc)

    if (_cluster_cache["updated"] is None or
            now - _cluster_cache["updated"] > timedelta(minutes=5)):
        try:
            result = await run_ssh_async(f"{LSF_PATH}/bhosts")
            lines  = result.strip().splitlines()
            total  = 0
            running = 0
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        total   += int(parts[3])
                        running += int(parts[4])
                    except (ValueError, IndexError):
                        continue
            _cluster_cache["value"]   = (running / total * 100) if total > 0 else 0.0
            _cluster_cache["updated"] = now
        except Exception as e:
            logger.warning(f"Could not fetch cluster load: {e}")

    return _cluster_cache["value"]


# ══════════════════════════════════════════════════════════════════════════
# IP REGISTRY
# ══════════════════════════════════════════════════════════════════════════

async def is_known_ip(user_id: str, ip: str, db: AsyncSession) -> bool:
    """Check if IP is in user's verified registry."""
    result = await db.execute(
        select(UserKnownIP)
        .where(UserKnownIP.user_id    == user_id)
        .where(UserKnownIP.ip_address == ip)
        .where(UserKnownIP.verified   == True)
    )
    return result.scalar_one_or_none() is not None


async def register_ip(
    user_id:  str,
    ip:       str,
    db:       AsyncSession,
    verified: bool = False,
) -> None:
    """Add/update IP in user's registry."""
    existing = await db.execute(
        select(UserKnownIP)
        .where(UserKnownIP.user_id    == user_id)
        .where(UserKnownIP.ip_address == ip)
    )
    entry = existing.scalar_one_or_none()

    if entry:
        entry.last_seen = datetime.now(timezone.utc)
        if verified:
            entry.verified = True
    else:
        db.add(UserKnownIP(
            user_id    = user_id,
            ip_address = ip,
            verified   = verified,
        ))
    await db.commit()


async def mark_ip_verified(user_id: str, ip: str, db: AsyncSession) -> None:
    """Call after MFA success — marks IP as trusted."""
    await register_ip(user_id, ip, db, verified=True)
    logger.info(f"IP verified after MFA: user={user_id} ip={ip}")


# ══════════════════════════════════════════════════════════════════════════
# SESSION MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════

async def get_or_create_session(
    user:    User,
    token:   str,
    request: Request,
    db:      AsyncSession,
) -> Session:
    """Gets existing session or creates one on first authenticated request."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    result = await db.execute(
        select(Session).where(Session.token_hash == token_hash)
    )
    session = result.scalar_one_or_none()

    if session is None:
        session = Session(
            user_id    = user.user_id,
            token_hash = token_hash,
            ip_address = get_client_ip(request),
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=300),
            risk_score = 0,
            peak_risk  = 0,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

    return session


async def get_session_history(
    user_id: str,
    db:      AsyncSession,
) -> dict:
    """
    Fetches last 5 minutes of session risk history for this user.
    Returns max, avg, and previous scores for session scoring formula.
    """
    five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)

    result = await db.execute(
        select(
            func.max(Session.risk_score).label("max_score"),
            func.avg(Session.risk_score).label("avg_score"),
        )
        .where(Session.user_id    == user_id)
        .where(Session.created_at >= five_min_ago)
    )
    row = result.fetchone()

    # Get previous session score for memory component
    prev_result = await db.execute(
        select(Session.risk_score)
        .where(Session.user_id == user_id)
        .order_by(Session.created_at.desc())
        .limit(1)
    )
    prev_row = prev_result.fetchone()

    return {
        "max_recent_score":      row.max_score or 0,
        "avg_recent_score":      float(row.avg_score or 0),
        "previous_session_score": float(prev_row[0] if prev_row else 0),
    }


# ══════════════════════════════════════════════════════════════════════════
# LAYER 1 — SIGNAL COLLECTION
# ══════════════════════════════════════════════════════════════════════════

async def collect_signals(
    job:     Job,
    user:    User,
    policy:  Policy,
    db:      AsyncSession,
    request: Request,
) -> dict:
    """Collects all risk signals. Returns {signal_name: score_contribution}"""
    signals = {}
    now = datetime.now(timezone.utc)
    ip  = get_client_ip(request)

    # ── R1: Resource Anomaly ───────────────────────────────────────────────
    try:
        wall_hours = int(job.wall_time.split(':')[0])
    except (ValueError, AttributeError, IndexError):
        wall_hours = 0
 
    signals["R1_cores"]    = WEIGHTS["R1_cores"]    if job.cores > RESOURCE_MAX_CORES    else 0
    signals["R1_memory"]   = WEIGHTS["R1_memory"]   if job.memory > RESOURCE_MAX_MEMORY  else 0
    signals["R1_walltime"] = WEIGHTS["R1_walltime"] if wall_hours > RESOURCE_MAX_WALLTIME else 0

    # ── R2: Location Anomaly (verified IP registry) ────────────────────────
    known = await is_known_ip(user.user_id, ip, db)
    if not known:
        verified_ips_result = await db.execute(
            select(func.count(UserKnownIP.id))
            .where(UserKnownIP.user_id  == user.user_id)
            .where(UserKnownIP.verified == True)
        )
        has_known_ips = verified_ips_result.scalar() > 0
        signals["R2_location"] = WEIGHTS["R2_location"] if has_known_ips else WEIGHTS["R2_location"] // 2
        await register_ip(user.user_id, ip, db, verified=False)
    else:
        signals["R2_location"] = 0
        await register_ip(user.user_id, ip, db, verified=True)

    # ── R4: Temporal Anomaly ───────────────────────────────────────────────
    signals["R4_temporal"] = WEIGHTS["R4_temporal"] if (now.hour < 6 or now.hour >= 22) else 0

    # ── R5: Rate Anomaly ───────────────────────────────────────────────────
    threshold = RATE_THRESHOLDS.get(user.role, 2)
    rate_result = await db.execute(
        select(func.count(Job.job_id))
        .where(Job.user_id     == user.user_id)
        .where(Job.submitted_at >= now - timedelta(seconds=60))
    )
    signals["R5_rate"] = WEIGHTS["R5_rate"] if rate_result.scalar() >= threshold else 0

    # ── R7: Credential Risk ────────────────────────────────────────────────
    if user.failed_attempts > 0:
        fail_result = await db.execute(
            select(func.count(AuditLog.log_id))
            .where(AuditLog.user_id   == user.user_id)
            .where(AuditLog.action    == "login_failed")
            .where(AuditLog.timestamp >= now - timedelta(minutes=10))
        )
        signals["R7_cred"] = WEIGHTS["R7_cred"] if fail_result.scalar() > 0 else 0
    else:
        signals["R7_cred"] = 0

    # ── R8: Cluster Load ───────────────────────────────────────────────────
    utilization = await get_cluster_utilization()
    signals["R8_cluster"] = WEIGHTS["R8_cluster"] if utilization > CLUSTER_THRESHOLD else 0

    return signals


# ══════════════════════════════════════════════════════════════════════════
# LAYER 2 — RISK SCORING
# ══════════════════════════════════════════════════════════════════════════

def compute_base_score(signals: dict) -> tuple[int, list[str]]:
    """Pure function. Sums active signals."""
    score          = 0
    active_signals = []
    for name, contribution in signals.items():
        if contribution > 0:
            score += contribution
            active_signals.append(name)
    return min(score, 100), active_signals


def apply_combo_bonuses(
    base_score:     int,
    active_signals: list[str],
) -> tuple[int, list[str]]:
    """Pure function. Applies attack pattern correlation bonuses."""
    bonus_total      = 0
    combos_triggered = []
    for (sig_a, sig_b), bonus in COMBO_BONUSES.items():
        if sig_a in active_signals and sig_b in active_signals:
            bonus_total += bonus
            combos_triggered.append(f"COMBO:{sig_a}+{sig_b}(+{bonus})")
    return min(base_score + bonus_total, 100), combos_triggered


def compute_session_score(
    current_request_score:  int,
    max_recent_score:       int,
    avg_recent_score:       float,
    previous_session_score: float = 0.0,
) -> int:
    """
    YOUR formula — hybrid session scoring with memory and decay.
    Step 1: base = max(peak, avg*1.5)         ← peak awareness
    Step 2: session = max(base, previous)     ← memory
    Step 3: decay if clean request            ← trust earned
    Step 4: clamp to 100
    """
    # Step 1 — hybrid of peak and sustained behavior
    base_score = max(
        max_recent_score,
        avg_recent_score * 1.5
    )

    # Step 2 — memory of previous session
    session_score = max(base_score, previous_session_score)

    # Step 3 — decay ONLY on clean behavior (current score = 0)
    if current_request_score == 0:
        session_score *= DECAY_FACTOR

    # Step 4 — clamp
    return int(min(session_score, 100))


# ══════════════════════════════════════════════════════════════════════════
# LAYER 3 — ACTION ENGINE
# ══════════════════════════════════════════════════════════════════════════

def decide_action(session_score: int) -> dict:
    """Pure function. Decides action based on session risk score."""
    if session_score >= 80:
        return {
            "action":     "block",
            "mfa_needed": True,
            "flagged":    True,
            "level":      "critical",
        }
    elif session_score >= RISK_FLAG_THRESHOLD:
        return {
            "action":     "flag_and_mfa",
            "mfa_needed": True,
            "flagged":    True,
            "level":      "high",
        }
    elif session_score >= 20:
        return {
            "action":     "flag_only",
            "mfa_needed": False,
            "flagged":    True,
            "level":      "medium",
        }
    else:
        return {
            "action":     "allow",
            "mfa_needed": False,
            "flagged":    False,
            "level":      "low",
        }


# ══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════

async def run_carta(
    job:     Job,
    user:    User,
    policy:  Policy,
    db:      AsyncSession,
    request: Request,
    session: Session,
) -> dict:
    """
    Complete CARTA evaluation for one job submission.
    Returns full risk assessment with action decision.
    """
    # Layer 1 — collect signals
    signals = await collect_signals(job, user, policy, db, request)

    # Layer 2 — compute score
    base_score, active_signals = compute_base_score(signals)
    request_score, combos      = apply_combo_bonuses(base_score, active_signals)

    # Get session history for session scoring
    history = await get_session_history(user.user_id, db)
    session_score = compute_session_score(
        current_request_score  = request_score,
        max_recent_score       = history["max_recent_score"],
        avg_recent_score       = history["avg_recent_score"],
        previous_session_score = history["previous_session_score"],
    )

    # Update session with new risk scores
    session.risk_score = session_score
    session.peak_risk  = max(session.peak_risk or 0, session_score)
    await db.commit()

    # Layer 3 — decide action
    action = decide_action(session_score)

    all_signals = active_signals + combos

    result = {
        "request_score": request_score,
        "session_score": session_score,
        "signals":       all_signals,
        "action":        action,
        "flagged":       action["flagged"],
        "mfa_needed":    action["mfa_needed"],
        "level":         action["level"],
    }

    if action["flagged"]:
        logger.warning(
            f"CARTA: user={user.username} "
            f"ρ_req={request_score} ρ_session={session_score} "
            f"level={action['level']} signals={all_signals}"
        )

    return result


async def apply_carta_result(
    job:    Job,
    result: dict,
    db:     AsyncSession,
) -> None:
    """Applies CARTA result to job record in DB."""
    if result["flagged"]:
        job.is_flagged  = True
        job.flag_reason = " | ".join(result["signals"])
        job.flagged_at  = datetime.now(timezone.utc)
        await db.commit()
