import math
import cmath
import hashlib
import base64
import json
import os
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import Request

from app.db.models import Job, AuditLog, User, Policy, UserKnownIP, Session
from app.core.logging import logger
from app.services.ssh import run_ssh_async
from app.core.config import LSF_PATH
from app.core.utils import get_client_ip


# ══════════════════════════════════════════════════════════════════════════
# SIGNAL WEIGHTS — normalized, sum used as denominator
# ══════════════════════════════════════════════════════════════════════════

SIGNAL_WEIGHTS = {
    "R1_baseline": 0.13,
    "R2_device":   0.10,
    "R3_geo":      0.18,
    "R4_temporal": 0.04,
    "R5_rate":     0.13,
    "R7_cred":     0.35,  
    "S2_velocity": 0.07,
}

# Total weight — used for normalization denominator
TOTAL_WEIGHT = sum(SIGNAL_WEIGHTS.values())   


# ══════════════════════════════════════════════════════════════════════════
# COMBO MULTIPLIERS — multiplicative
# ══════════════════════════════════════════════════════════════════════════

COMBO_MULTIPLIERS = {
    ("R3_geo",    "R7_cred"):     1.50,  # foreign location + failed logins
    ("R2_device", "R7_cred"):     1.45,  # new device + failed logins → account takeover
    ("R3_geo",    "R2_device"):   1.35,  # foreign location + new device → remote attacker
    ("R5_rate",   "S2_velocity"): 1.30,  # high rate + regular timing → bot confirmed
    ("R4_temporal","R5_rate"):    1.25,  # off-hours + high rate → automated attack
    ("R2_device", "R5_rate"):     1.20,  # new device + high rate → scripted attack
    ("R1_baseline","R2_device"):  1.15,  # huge job + new device → resource abuse
    ("R3_geo",    "R5_rate"):     1.30,  # foreign + high rate → remote scripted attack 
    ("R1_baseline" , "R7_cred"): 1.45 ,  # huge job + failed logins → account takeover
}


# ══════════════════════════════════════════════════════════════════════════
# DECISION THRESHOLDS — empirically calibrated
# ══════════════════════════════════════════════════════════════════════════

THRESHOLD_FLAG  = 0.13   # τ₁: ρ ≥ 0.20 → flag
THRESHOLD_MFA   = 0.40   # τ₂: ρ ≥ 0.40 → MFA required
THRESHOLD_BLOCK = 0.80   # τ₃: ρ ≥ 0.80 → block unconditionally

# EMA "clean request" threshold — requests below this are treated as
# low-noise and trigger decay rather than the standard EMA update.
# Using a threshold (vs strict == 0.0) handles the common case where
# background signal noise produces small non-zero scores (~0.02–0.05)
# for genuinely benign requests.
THRESHOLD_CLEAN = THRESHOLD_FLAG   # ρ_req < 0.20 → decay branch


# ══════════════════════════════════════════════════════════════════════════
# SESSION EMA PARAMETERS
# ══════════════════════════════════════════════════════════════════════════

EMA_ALPHA    = 0.3   # learning rate
EMA_GAMMA    = 0.9   # decay factor


# ══════════════════════════════════════════════════════════════════════════
# SIGNAL-SPECIFIC CONSTANTS
# ══════════════════════════════════════════════════════════════════════════

# R1 — behavioral baseline
BASELINE_MIN_HISTORY     = 5      # minimum jobs to compute personal baseline
BASELINE_SPIKE_THRESHOLD = 3.0    # 3× personal average triggers full signal

# R4 — temporal (personal baseline)
TEMPORAL_MIN_HISTORY     = 10     # minimum jobs to compute hour distribution
TEMPORAL_SIGMA_THRESHOLD = 2.0    # deviations from personal mean to trigger

# R5 — rate anomaly
RATE_THRESHOLDS = {
    "student":    5,
    "researcher": 8,
    "admin":      10,
}

# R7 — credential risk (raised from > 0 to > 2)

R7_FAILED_LOGIN_THRESHOLD = 2

# S2 — velocity pattern
VELOCITY_MIN_SAMPLES  = 4      # minimum submissions to compute CV
VELOCITY_CV_THRESHOLD = 0.1    # below this → automated pattern

# R3 — geolocation
EXPECTED_COUNTRY_CODE        = "DZ"   # Algeria — update for your deployment
IMPOSSIBLE_TRAVEL_SPEED_KMH  = 900    # commercial flight speed
GEOIP_DB_PATH                = "/etc/geoip/GeoLite2-City.mmdb"

# GeoIP availability flag — set at import time, avoids per-request stat()
_GEOIP_AVAILABLE: bool = os.path.isfile(GEOIP_DB_PATH)


# ══════════════════════════════════════════════════════════════════════════
# STARTUP CHECKS
# ══════════════════════════════════════════════════════════════════════════

def _check_startup_dependencies() -> None:
    """
    Warn at import time about missing optional dependencies that silently
    disable entire signal subsystems. Called once at module load.
    """
    if not _GEOIP_AVAILABLE:
        logger.warning(
            f"CARTA: GeoIP database not found at {GEOIP_DB_PATH}. "
            f"R3_geo (geolocation anomaly) is DISABLED for all requests. "
            f"Download GeoLite2-City.mmdb from maxmind.com and place it at "
            f"{GEOIP_DB_PATH} to enable country and impossible-travel detection."
        )
    try:
        import geoip2  # noqa: F401
    except ImportError:
        logger.warning(
            "CARTA: geoip2 package not installed. "
            "R3_geo is DISABLED. Run: pip install geoip2"
        )

_check_startup_dependencies()


# ══════════════════════════════════════════════════════════════════════════
# CLUSTER LOAD — for 2D policy axis λ, NOT a CARTA signal
# ══════════════════════════════════════════════════════════════════════════

_cluster_cache: dict = {"value": 0.0, "updated": None}


async def get_cluster_utilization() -> float:

    global _cluster_cache
    now = datetime.now(timezone.utc)

    if (_cluster_cache["updated"] is None or
            now - _cluster_cache["updated"] > timedelta(minutes=5)):
        try:
            result  = await run_ssh_async(f"{LSF_PATH}/bhosts")
            lines   = result.strip().splitlines()
            total   = 0
            running = 0
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 6:
                    try:
                        max_c = int(parts[3])
                        run_c = int(parts[5])
                        if parts[1] == "ok" and max_c > 1:
                            total   += max_c
                            running += run_c
                    except (ValueError, IndexError):
                        continue
            utilization = (running / total) if total > 0 else 0.0
            _cluster_cache["value"]   = round(utilization, 3)
            _cluster_cache["updated"] = now
            logger.debug(f"Cluster λ={utilization:.1%} ({running}/{total} cores)")
        except Exception as e:
            logger.warning(f"Could not fetch cluster load: {e}")

    return _cluster_cache["value"]


# ══════════════════════════════════════════════════════════════════════════
# 2D POLICY FUNCTION Π(ρ, λ)
# ══════════════════════════════════════════════════════════════════════════

# Severity ordering for formal property verification (P1, P2).
# Higher integer = more restrictive enforcement action.
ACTION_SEVERITY: dict[str, int] = {
    "allow":    0,
    "flag":     1,
    "mfa":      2,
    "throttle": 3,
    "restrict": 4,
    "block":    5,
    "isolate":  6,
}


@dataclass
class PolicyDecision:

    action:       str
    risk_tier:    str
    load_tier:    str
    resource_cap: float
    mfa_required: bool
    admin_alert:  bool
    reason:       str


def compute_2d_policy(
    risk_score:   float,   # ρ ∈ [0,1] from CARTA session score
    cluster_load: float,   # λ ∈ [0,1] from bhosts
) -> PolicyDecision:
    """
    Π(ρ,λ) — formally specified 2D admission control policy.

    Separates security concern (ρ) from scheduling context (λ).
    This resolves the architectural problem of mixing security signals
    with resource management signals (formerly R8).

    Formal properties verified against ACTION_SEVERITY ordering:
      P1: ρ₁>ρ₂ → severity(Π(ρ₁,λ)) ≥ severity(Π(ρ₂,λ))  [monotone in risk]
      P2: λ₁>λ₂ → severity(Π(ρ,λ₁)) ≥ severity(Π(ρ,λ₂))  [monotone in load]
      P3: ρ≥0.8 → action ∈ {block,isolate}                  [critical invariant]
      P4: ρ<0.2 ∧ λ<0.85 → action = allow                  [low risk guarantee]

    P1 verification (reading down each load column):
      low col:      allow(0) → flag(1) → mfa(2) → block(5)      ✓ non-decreasing
      medium col:   allow(0) → flag(1) → restrict(4) → block(5)  ✓ non-decreasing
      high col:     allow(0) → mfa(2) → restrict(4) → block(5)   ✓ non-decreasing
      critical col: flag(1) → throttle(3) → block(5) → isolate(6) ✓ non-decreasing

    P2 verification (reading across each risk row):
      low row:      allow(0) → allow(0) → allow(0) → flag(1)     ✓ non-decreasing
      medium row:   flag(1) → flag(1) → mfa(2) → throttle(3)     ✓ non-decreasing
      high row:     mfa(2) → restrict(4) → restrict(4) → block(5) ✓ non-decreasing
      critical row: block(5) → block(5) → block(5) → isolate(6)  ✓ non-decreasing
    """
    # Classify risk tier using calibrated thresholds
    if risk_score < THRESHOLD_FLAG:
        risk_tier = "low"
    elif risk_score < THRESHOLD_MFA:
        risk_tier = "medium"
    elif risk_score < THRESHOLD_BLOCK:
        risk_tier = "high"
    else:
        risk_tier = "critical"

    # Classify load tier
    if cluster_load < 0.40:
        load_tier = "low"
    elif cluster_load < 0.70:
        load_tier = "medium"
    elif cluster_load < 0.85:
        load_tier = "high"
    else:
        load_tier = "critical"

    # Policy matrix Π[risk][load] = (action, resource_cap, mfa, alert)
    #
    # Severity integers (from ACTION_SEVERITY) annotated inline for P1/P2 audit.
    # P4 note: low×critical → flag(1) not allow(0) by design — cluster at capacity
    # warrants a log entry even for low-risk users. P4 is stated as λ<0.85
    # (i.e. λ < critical threshold), which holds: low×{low,medium,high} = allow.
    MATRIX = {
        "low": {
            "low":      ("allow",    1.0,  False, False),   # sev 0
            "medium":   ("allow",    1.0,  False, False),   # sev 0
            "high":     ("allow",    1.0,  False, False),   # sev 0
            "critical": ("flag",     1.0,  False, False),   # sev 1  ← λ≥0.85 only
        },
        "medium": {
            "low":      ("flag",     1.0,  False, False),   # sev 1
            "medium":   ("flag",     1.0,  False, False),   # sev 1
            "high":     ("mfa",      1.0,  True,  False),   # sev 2
            "critical": ("throttle", 0.75, True,  False),   # sev 3
        },
        "high": {
            "low":      ("mfa",      1.0,  True,  False),   # sev 2
            "medium":   ("restrict", 0.5,  True,  False),   # sev 4
            "high":     ("restrict", 0.5,  True,  False),   # sev 4
            "critical": ("block",    0.0,  False, True),    # sev 5
        },
        "critical": {
            "low":      ("block",    0.0,  False, True),    # sev 5  P3: always block
            "medium":   ("block",    0.0,  False, True),    # sev 5
            "high":     ("block",    0.0,  False, True),    # sev 5
            "critical": ("isolate",  0.0,  False, True),    # sev 6  revoke session
        },
    }

    action, resource_cap, mfa_required, admin_alert = MATRIX[risk_tier][load_tier]

    return PolicyDecision(
        action       = action,
        risk_tier    = risk_tier,
        load_tier    = load_tier,
        resource_cap = resource_cap,
        mfa_required = mfa_required,
        admin_alert  = admin_alert,
        reason       = (
            f"ρ={risk_score:.3f} ({risk_tier}) × "
            f"λ={cluster_load:.1%} ({load_tier}) → {action}"
        ),
    )


# ══════════════════════════════════════════════════════════════════════════
# IP / DEVICE REGISTRY
# ══════════════════════════════════════════════════════════════════════════

async def is_known_ip(user_id: str, ip: str, db: AsyncSession) -> bool:
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
    await register_ip(user_id, ip, db, verified=True)
    logger.info(f"IP verified after MFA: user={user_id} ip={ip}")


async def get_known_ips(user_id: str, db: AsyncSession) -> list[str]:
    result = await db.execute(
        select(UserKnownIP.ip_address)
        .where(UserKnownIP.user_id  == user_id)
        .where(UserKnownIP.verified == True)
    )
    return [row[0] for row in result.fetchall()]


# ══════════════════════════════════════════════════════════════════════════
# SESSION MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════

async def get_or_create_session(
    user:    User,
    token:   str,
    request: Request,
    db:      AsyncSession,
) -> Session:
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


async def get_session_score(session: Session) -> float:
    """
    Returns the current risk score for this specific session object.

    FIX (was: get_previous_session_score by user_id + created_at ORDER):
    The original query fetched the most recently *created* session row for
    the user. With multiple concurrent sessions (e.g. two browser tabs),
    this could return a different session's risk_score than the one being
    updated, fragmenting the EMA chain across sessions.

    We now read directly from the session object already loaded by
    get_or_create_session, which is the correct single-session EMA state.
    The caller passes the live session; no additional DB query needed.
    """
    return float(session.risk_score or 0.0)


# ══════════════════════════════════════════════════════════════════════════
# GEOLOCATION HELPERS
# ══════════════════════════════════════════════════════════════════════════

def get_geo_info(ip: str) -> dict:
    """
    Returns {country, city, lat, lon} for an IP address.
    Returns {} silently if geoip2 not installed or DB not found.
    R3 returns 0 if this function fails — never a hard dependency.

    Install: pip install geoip2
    DB:      download GeoLite2-City.mmdb from maxmind.com (free)
             place at /etc/geoip/GeoLite2-City.mmdb
    """
    if not _GEOIP_AVAILABLE:
        return {}
    try:
        import geoip2.database
        with geoip2.database.Reader(GEOIP_DB_PATH) as reader:
            r = reader.city(ip)
            return {
                "country": r.country.iso_code or "",
                "city":    r.city.name or "",
                "lat":     float(r.location.latitude  or 0),
                "lon":     float(r.location.longitude or 0),
            }
    except Exception:
        return {}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance in km using the Haversine formula.
    Used for impossible travel detection in R3.

    FIX: clamp intermediate value `a` to [0, 1] before sqrt calls.
    Floating-point arithmetic can produce a slightly negative value of `a`
    when the two coordinates are nearly identical (same city block), causing
    math.sqrt(a) to raise ValueError. The clamp has no effect on real distances.
    """
    R  = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a  = (math.sin(Δφ/2)**2 +
          math.cos(φ1) * math.cos(φ2) * math.sin(Δλ/2)**2)
    a  = max(0.0, min(1.0, a))   # clamp: guards against float rounding near 0 or 1
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def compute_device_fingerprint(request: Request) -> tuple[str, dict]:
    """
    Extracts device fingerprint from X-Device-Fingerprint header.
    Returns (fingerprint_hash, raw_data).

    Fingerprint uses stable attributes only:
      platform + timezone + language + hardwareConcurrency + maxTouchPoints
    These persist across sessions unlike IP addresses, handling:
      - DHCP reassignment (IP changes, fingerprint stable)
      - VPN usage (IP changes, fingerprint stable)
      - Docker networking (IP changes, fingerprint stable)

    Security note: this header is fully attacker-controlled and is not
    cryptographically verified. It functions as a probabilistic hint, not
    a proof of device identity. A sophisticated attacker who knows a
    legitimate user's fingerprint hash can spoof it. The signal is designed
    to catch opportunistic attackers and automated tools, not targeted
    impersonation. Treat R2_device as soft evidence accordingly.
    """
    raw = request.headers.get("X-Device-Fingerprint", "")
    if not raw:
        return "", {}
    try:
        data     = json.loads(base64.b64decode(raw).decode())
        platform = str(data.get("platform", ""))
        tz       = str(data.get("timezone", ""))
        language = str(data.get("language", ""))
        cores    = str(data.get("hardwareConcurrency", "0"))
        touch    = str(data.get("maxTouchPoints", "0"))
        stable   = f"{platform}:{tz}:{language}:{cores}:{touch}"
        fp_hash  = hashlib.sha256(stable.encode()).hexdigest()[:24]
        return fp_hash, data
    except Exception:
        return "", {}


# ══════════════════════════════════════════════════════════════════════════
# LAYER 1 — SIGNAL COLLECTION
# Each signal sᵢ ∈ [0.0, 1.0]
# 0.0 = signal did not fire
# 0.5 = partial evidence
# 1.0 = full evidence
# ══════════════════════════════════════════════════════════════════════════

async def collect_signals(
    job:     Job,
    user:    User,
    policy:  Policy,
    db:      AsyncSession,
    request: Request,
) -> dict[str, float]:
    """
    Collects normalized risk signals for this job submission.
    Returns {signal_name: value} where value ∈ [0.0, 1.0].
    """
    signals: dict[str, float] = {
        "R1_baseline": 0.0,
        "R2_device":   0.0,
        "R3_geo":      0.0,
        "R4_temporal": 0.0,
        "R5_rate":     0.0,
        "R7_cred":     0.0,
        "S2_velocity": 0.0,
    }
    now = datetime.now(timezone.utc)
    ip  = get_client_ip(request)
    


    # ── R1: Behavioral Baseline Deviation ─────────────────────────────────
    # sᵢ ∈ {0.0, 0.5, 1.0} based on deviation from personal history.
    # Personal baseline is more precise than fixed thresholds:
    # a researcher who always uses 16 cores scores 0 (normal for them).
    # A student who normally uses 2 cores suddenly requesting 12 scores 1.0.
    history_res = await db.execute(
        select(Job.cores, Job.memory)
        .where(Job.user_id == user.user_id)
        .where(Job.status  != "EXIT")
        .order_by(Job.submitted_at.desc())
        .limit(20)
    )
    past = history_res.fetchall()

    if len(past) >= BASELINE_MIN_HISTORY:
        avg_c = sum(r[0] for r in past) / len(past)
        avg_m = sum(r[1] for r in past) / len(past)
        cr = job.cores  / avg_c if avg_c > 0 else 1.0
        mr = job.memory / avg_m if avg_m > 0 else 1.0

        if cr >= BASELINE_SPIKE_THRESHOLD or mr >= BASELINE_SPIKE_THRESHOLD:
            signals["R1_baseline"] = 1.0    # 3× personal average
        elif cr >= 2.0 or mr >= 2.0:
            signals["R1_baseline"] = 0.5    # 2× personal average
        else:
            signals["R1_baseline"] = 0.0
    else:
        # Not enough history — conservative fallback
        if job.cores > policy.max_cores_per_job * 0.75:
            signals["R1_baseline"] = 0.5
        else:
            signals["R1_baseline"] = 0.0

    # ── R2: Device Fingerprint Anomaly ────────────────────────────────────
    # sᵢ ∈ [0.0, 1.0] scaled by what is suspicious about the new device.
    # Unlike IP-based detection, stable across DHCP/VPN/Docker.
    # Timezone mismatch is the strongest sub-signal: an attacker from
    # a different country cannot easily fake their timezone.
    #
    # API clients (no X-Device-Fingerprint header) receive R2_device = 0.0.
    # This is intentional: scripted HPC submission is a legitimate workflow.
    # Consequence: R2-dependent combo bonuses cannot fire for pure API clients.
    # Compensating signals R5 (rate) and S2 (velocity) remain active.
    fingerprint, fp_data = compute_device_fingerprint(request)

    if not fingerprint:
        signals["R2_device"] = 0.0
    else:
        try:
            from app.db.models import UserKnownDevice
            known_res    = await db.execute(
                select(UserKnownDevice)
                .where(UserKnownDevice.user_id == user.user_id)
            )
            known_devices = known_res.scalars().all()
            known_fps     = {d.fingerprint for d in known_devices}

            if fingerprint in known_fps:
                signals["R2_device"] = 0.0   # fully recognized
            else:
                tz_mismatch = (
                    fp_data.get("timezone", "") != "" and
                    fp_data.get("timezone", "") not in {
                        "Africa/Algiers", "Europe/Paris", "UTC"
                    }
                )
                if tz_mismatch and not known_devices:
                    signals["R2_device"] = 1.0   # new device + wrong TZ
                elif tz_mismatch:
                    signals["R2_device"] = 0.7   # known user, wrong TZ
                elif not known_devices:
                    signals["R2_device"] = 0.5   # very first device
                else:
                    signals["R2_device"] = 0.3   # new device, known user

                # Register as unverified — verified only after MFA
                try:
                    touch = fp_data.get("maxTouchPoints", 0)
                    db.add(UserKnownDevice(
                        user_id     = user.user_id,
                        fingerprint = fingerprint,
                        device_type = "mobile" if touch > 0 else "desktop",
                        platform    = fp_data.get("platform", ""),
                        timezone    = fp_data.get("timezone", ""),
                        verified    = False,
                    ))
                    await db.commit()
                except Exception:
                    pass

        except ImportError:
            # UserKnownDevice not migrated yet — fall back to IP registry
            known = await is_known_ip(user.user_id, ip, db)
            signals["R2_device"] = 0.0 if known else 0.5
            if not known:
                await register_ip(user.user_id, ip, db, verified=False)

    # ── R3: Geolocation Anomaly ───────────────────────────────────────────
  
    geo_now = get_geo_info(ip)

    if not geo_now:
        signals["R3_geo"] = 0.0   # graceful degradation
    else:
        country_now   = geo_now.get("country", "")
        country_score = 0.0

        # R3a: unexpected country
        if country_now and country_now != EXPECTED_COUNTRY_CODE:
            country_score = 1.0
            logger.warning(
                f"R3: Unexpected country {country_now} "
                f"user={user.username} ip={ip}"
            )

        # R3b: impossible travel
        travel_score = 0.0
        prev_res = await db.execute(
            select(AuditLog.ip_address, AuditLog.timestamp)
            .where(AuditLog.user_id == user.user_id)
            .where(AuditLog.action  == "login")
            .where(AuditLog.result  == "success")
            .where(AuditLog.ip_address.isnot(None))
            .order_by(AuditLog.timestamp.desc())
            .limit(1)
        )
        prev_login = prev_res.fetchone()

        if prev_login:
            prev_ip   = prev_login[0]
            prev_time = prev_login[1]
            geo_prev  = get_geo_info(prev_ip)

            if (geo_prev and
                    geo_now.get("lat") and geo_prev.get("lat") and
                    prev_ip != ip):
                dist_km    = haversine_km(
                    geo_prev["lat"], geo_prev["lon"],
                    geo_now["lat"],  geo_now["lon"],
                )
                time_h = (
                    now - prev_time.replace(tzinfo=timezone.utc)
                ).total_seconds() / 3600

                if time_h > 0 and dist_km > 100:
                    speed = dist_km / time_h
                    if speed > IMPOSSIBLE_TRAVEL_SPEED_KMH:
                        travel_score = 1.0
                        logger.warning(
                            f"R3: Impossible travel "
                            f"user={user.username} "
                            f"dist={dist_km:.0f}km "
                            f"time={time_h:.2f}h "
                            f"speed={speed:.0f}km/h"
                        )

        signals["R3_geo"] = max(country_score, travel_score)

    # ── R4: Temporal Anomaly (personal hour baseline) ─────────────────────
    # Compare submission hour to user's OWN historical distribution.
    # Uses circular statistics to handle the 23→0 midnight wrap correctly.
    # Falls back to fixed off-hours window if < TEMPORAL_MIN_HISTORY jobs.
    #
    # Circular mean and std dev:
    #   Convert hours to unit circle angles: θ = 2π·h/24
    #   Mean angle: μ = arg(Σ e^(iθ_k))
    #   Circular std dev: σ_c = sqrt(-2·ln|R̄|) where R̄ = mean resultant length
    hour_res = await db.execute(
        select(Job.submitted_at)
        .where(Job.user_id == user.user_id)
        .order_by(Job.submitted_at.desc())
        .limit(50)
    )
    past_times = [r[0] for r in hour_res.fetchall()]

    if len(past_times) >= TEMPORAL_MIN_HISTORY:
        past_hours = [t.hour for t in past_times]
        # Compute circular mean and std dev
        angles     = [cmath.exp(1j * 2 * math.pi * h / 24) for h in past_hours]
        mean_vec   = sum(angles) / len(angles)
        R_bar      = abs(mean_vec)   # mean resultant length
        mean_h     = (cmath.phase(mean_vec) * 24 / (2 * math.pi)) % 24

        # Circular std dev in hours (add small epsilon to avoid log(0))
        circ_std = (
            math.sqrt(-2 * math.log(max(R_bar, 1e-10))) * 24 / (2 * math.pi)
        )
        effective_std = max(circ_std, 2.0)   # floor at 2h prevents over-sensitivity

        # Circular distance — handles midnight wrap
        curr_h = now.hour
        diff   = min(abs(curr_h - mean_h), 24 - abs(curr_h - mean_h))

        if diff > TEMPORAL_SIGMA_THRESHOLD * effective_std:
            signals["R4_temporal"] = 1.0
        elif diff > effective_std:
            signals["R4_temporal"] = 0.5
        else:
            signals["R4_temporal"] = 0.0
    else:
        # Fallback: fixed off-hours window
        signals["R4_temporal"] = (
            1.0 if (now.hour < 6 or now.hour >= 22) else 0.0
        )

    # ── R5: Rate Anomaly ──────────────────────────────────────────────────
    # Exceeds role-based submission rate threshold per 60 seconds.
    # Thresholds: student=2, researcher=5, admin=10
    threshold   = RATE_THRESHOLDS.get(user.role, 2)
    rate_res    = await db.execute(
        select(func.count(Job.job_id))
        .where(Job.user_id     == user.user_id)
        .where(Job.submitted_at >= now - timedelta(seconds=60))
    )
    count = rate_res.scalar()
    if count >= threshold * 2:
        signals["R5_rate"] = 1.0   # 2× threshold — clearly anomalous
    elif count >= threshold:
        signals["R5_rate"] = 0.7   # at threshold — suspicious
    else:
        signals["R5_rate"] = 0.0
        
        
    # ── R7: Credential Risk ───────────────────────────────────────────────

        
    fail_res = await db.execute(
        select(func.count(AuditLog.log_id))
        .where(AuditLog.user_id   == user.user_id)
        .where(AuditLog.action    == "login_failed")
        .where(AuditLog.timestamp >= now - timedelta(minutes=10))
    )
    fail_count = fail_res.scalar()

    if fail_count > 4:
        signals["R7_cred"] = 1.0
    elif fail_count > R7_FAILED_LOGIN_THRESHOLD:
        signals["R7_cred"] = 0.7
    else:
         signals["R7_cred"] = 0.0    

        
        

    # ── S2: Submission Velocity Pattern ───────────────────────────────────
    # Coefficient of variation (CV = σ/μ) of inter-submission intervals.
    # Human users: variable timing, CV > 0.3
    # Automated scripts: regular timing, CV < 0.1
    # Technique adapted from web bot detection literature.
    vel_res = await db.execute(
        select(Job.submitted_at)
        .where(Job.user_id     == user.user_id)
        .where(Job.submitted_at >= now - timedelta(minutes=10))
        .order_by(Job.submitted_at.asc())
    )
    times = [r[0] for r in vel_res.fetchall()]

    if len(times) >= VELOCITY_MIN_SAMPLES:
        intervals = [
            (times[i+1] - times[i]).total_seconds()
            for i in range(len(times) - 1)
        ]
        avg_i = sum(intervals) / len(intervals)
        if avg_i > 0:
            variance = sum((x - avg_i)**2 for x in intervals) / len(intervals)
            cv       = math.sqrt(variance) / avg_i
            if cv < VELOCITY_CV_THRESHOLD:
                signals["S2_velocity"] = 1.0   # clearly automated
            elif cv < 0.2:
                signals["S2_velocity"] = 0.5   # borderline
            else:
                signals["S2_velocity"] = 0.0
        else:
            signals["S2_velocity"] = 1.0   # zero interval = simultaneous = automated
    else:
        signals["S2_velocity"] = 0.0
        
        
        
    
    logger.info(
    f"SIGNALS DEBUG user={user.username}: "
    f"R1={signals['R1_baseline']:.2f} "
    f"R2={signals['R2_device']:.2f} "
    f"R3={signals['R3_geo']:.2f} "
    f"R4={signals['R4_temporal']:.2f} "
    f"R5={signals['R5_rate']:.2f} "
    f"R7={signals['R7_cred']:.2f} "
    f"S2={signals['S2_velocity']:.2f} "
    f"fail_count={fail_count}"
    ) 

    return signals


# ══════════════════════════════════════════════════════════════════════════
# LAYER 2 — REQUEST SCORING
# ══════════════════════════════════════════════════════════════════════════

def compute_request_score(signals: dict[str, float]) -> tuple[float, list[str]]:
    """
    Normalized weighted sum — PROVABLY BOUNDED in [0,1].

    ρ_req = Σ(wᵢ · sᵢ) / Σ(wᵢ)

    where sᵢ ∈ [0,1] and wᵢ > 0 for all i.

    This guarantees ρ_req ∈ [0,1] regardless of how many signals fire.
    Contrast with the old additive approach where signals could sum > 100.
    """
    weighted_sum = sum(
        SIGNAL_WEIGHTS.get(sig, 0.0) * val
        for sig, val in signals.items()
    )
    score          = weighted_sum / TOTAL_WEIGHT   # ∈ [0, 1]
    active_signals = [s for s, v in signals.items() if v > 0]
    return round(score, 4), active_signals


def apply_combo_multipliers(
    base_score:     float,
    active_signals: list[str],
) -> tuple[float, list[str]]:
    """
    Multiplicative combo bonuses — PROVABLY BOUNDED in [0,1].

    Formula: final = 1 - (1 - base)^M
    where M = product of all active combo multipliers

    Mathematical proof of boundedness:
      base ∈ [0,1] → (1-base) ∈ [0,1] → (1-base)^M ∈ [0,1] for any M≥1
      → 1 - (1-base)^M ∈ [0,1] ∎

    Multiple combos compound: M = m₁ × m₂ × ... (not additive)
    This preserves the bound while reflecting severity of combined patterns.
    """
    M                = 1.0
    combos_triggered = []

    for (sig_a, sig_b), factor in COMBO_MULTIPLIERS.items():
        if sig_a in active_signals and sig_b in active_signals:
            M *= factor
            combos_triggered.append(
                f"COMBO:{sig_a}+{sig_b}(×{factor})"
            )

    if M == 1.0:
        return base_score, []

    # Bounded transformation (min() guard is redundant by proof but kept
    # as a defensive check against future floating-point edge cases)
    final = 1.0 - (1.0 - base_score) ** M
    return round(min(final, 1.0), 4), combos_triggered


# ══════════════════════════════════════════════════════════════════════════
# LAYER 3 — SESSION MEMORY (EMA)
# ══════════════════════════════════════════════════════════════════════════

def compute_session_score(
    current:  float,   # ρ_req from this request ∈ [0,1]
    previous: float,   # ρ_session from current session ∈ [0,1]
    alpha:    float = EMA_ALPHA,
    gamma:    float = EMA_GAMMA,
) -> float:

    if current < THRESHOLD_CLEAN:
        # Clean / low-noise request — apply decay
        result = gamma * previous
    elif current >= previous:
        # Risk increasing — EMA weights current request
        result = alpha * current + (1 - alpha) * previous
    else:
        # Risk decreasing — take max of EMA and decayed previous
        # Prevents score from collapsing on one lower-risk request
        ema     = alpha * current + (1 - alpha) * previous
        decayed = gamma * previous
        result  = max(ema, decayed)

    return round(min(max(result, 0.0), 1.0), 4)


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
    content: Optional[str] = None,
) -> dict:
    
    # Layer 1 — collect normalized signals
    signals = await collect_signals(job, user, policy, db, request)

    # Layer 2 — compute bounded request score
    base_score, active_signals = compute_request_score(signals)
    request_score, combos      = apply_combo_multipliers(base_score, active_signals)

    # Layer 3 — EMA session score with memory
    # FIX: read previous score from the current session object directly,
    # not from a DB query ordered by created_at. The old query could return
    # a different session's score when multiple concurrent sessions exist.
    previous_score = await get_session_score(session)
    session_score  = compute_session_score(
        current  = request_score,
        previous = previous_score,
    )

    # Update session record
    session.risk_score = session_score
    session.peak_risk  = max(session.peak_risk or 0, session_score)
    await db.commit()

    # Layer 4 — 2D policy decision
    # Use the higher of request_score and session_score for policy enforcement.
    # The EMA session score smooths gradual drift but must not dampen a sudden
    # high-risk spike (e.g. R7 firing with 5 failed logins on an otherwise clean
    # session). Without this, a user with previous_score=0.0 who triggers R7=1.0
    # produces session_score≈0.08 via EMA → wrongly falls into "low" tier → allow.
    # Taking the max ensures the worst observed signal in this request is enforced.
    cluster_load = await get_cluster_utilization()
    policy_score = max(request_score, session_score) 
    if signals.get("R7_cred", 0.0) == 1.0:
        policy_score = max(policy_score, THRESHOLD_MFA)
    decision     = compute_2d_policy(policy_score, cluster_load)

    # Build result — scores exposed as both [0,1] and [0,100] for display
    all_signals = active_signals + combos

    # Map 2D action to legacy names for jobs.py compatibility
    legacy_map = {
        "allow":    "allow",
        "flag":     "flag_only",
        "mfa":      "flag_and_mfa",
        "restrict": "flag_and_mfa",
        "throttle": "flag_and_mfa",
        "block":    "block",
        "isolate":  "block",
    }

    result = {
        # Normalized scores [0,1] — for formal model and paper
        "request_score_norm": request_score,
        "session_score_norm": session_score,
        "policy_score_norm":  policy_score,   # max(request, session) — drives decision
        # Display scores [0,100] — for API responses and dashboard
        "request_score":      round(request_score * 100),
        "session_score":      round(session_score * 100),
        # Context
        "cluster_load":       cluster_load,
        "signals":            all_signals,
        "signal_values":      {k: round(v, 3) for k, v in signals.items()},
        # Decision
        "action": {
            "action":        legacy_map[decision.action],
            "policy_action": decision.action,
            "mfa_needed":    decision.mfa_required,
            "flagged":       decision.action not in ("allow",),
            "level":         decision.risk_tier,
            "resource_cap":  decision.resource_cap,
            "admin_alert":   decision.admin_alert,
        },
        "flagged":      decision.action not in ("allow",),
        "mfa_needed":   decision.mfa_required,
        "level":        decision.risk_tier,
        "resource_cap": decision.resource_cap,
        "reason":       decision.reason,
    }

    if result["flagged"]:
        logger.warning(
            f"CARTA: user={user.username} "
            f"ρ_req={request_score:.3f} "
            f"ρ_session={session_score:.3f} "
            f"λ={cluster_load:.1%} "
            f"action={decision.action} "
            f"signals={all_signals}"
        )
    else:
        logger.info(
            f"CARTA: user={user.username} "
            f"ρ_req={request_score:.3f} "
            f"ρ_session={session_score:.3f} "
            f"ρ_policy={policy_score:.3f} "
            f"λ={cluster_load:.1%} → allow"
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
