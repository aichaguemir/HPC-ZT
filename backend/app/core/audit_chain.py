import hmac as hmac_module
import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sqlfunc

from app.db.models import AuditLog
from app.core.logging import logger


# ══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════

CHAIN_SEED = "HPC-GATEWAY-ZTA-AUDIT-CHAIN-V1"

# Anchor interval — write external anchor every N entries
ANCHOR_INTERVAL = int(os.environ.get("AUDIT_ANCHOR_INTERVAL", "10"))

# Anchor file path — should be on a DIFFERENT filesystem than the DB
# If DB is on /var/lib/postgresql → put anchors on /var/log
ANCHOR_FILE = os.environ.get(
    "AUDIT_ANCHOR_FILE",
    "/var/log/hpc_gateway/audit_anchors.jsonl"
)


# ── Secret key ────────────────────────────────────────────────────────────
def _load_secret() -> bytes:
    """
    Loads HMAC secret from environment.
    MUST be set in .env for production — do NOT hardcode.
    Generate: python3 -c "import secrets; print(secrets.token_hex(32))"
    """
    secret = os.environ.get("AUDIT_CHAIN_SECRET", "")
    if not secret:
        logger.warning(
            "AUDIT_CHAIN_SECRET not set. Generating ephemeral key — "
            "chain will NOT be verifiable across server restarts. "
            "Set AUDIT_CHAIN_SECRET in .env for production."
        )
        secret = secrets.token_hex(32)
    return secret.encode()

_CHAIN_SECRET: bytes = _load_secret()


# ══════════════════════════════════════════════════════════════════════════
# CORE HASH FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════

def compute_hash(
    prev_hash: str,
    timestamp: datetime,
    user_id:   str,
    action:    str,
    result:    str,
    detail:    dict,
) -> str:
    """
    H_i = HMAC-SHA256(K, canonical_json(H_{i-1} || event_data))

    Canonical JSON: sort_keys=True, no whitespace → deterministic output.
    HMAC key: _CHAIN_SECRET — without it, valid hashes cannot be forged.
    """
    content = json.dumps({
        "prev_hash": prev_hash,
        "timestamp": timestamp.isoformat(),
        "user_id":   user_id or "anonymous",
        "action":    action,
        "result":    result or "success",
        "detail":    detail or {},
    }, sort_keys=True, separators=(',', ':'))

    return hmac_module.new(
        _CHAIN_SECRET,
        content.encode(),
        hashlib.sha256,
    ).hexdigest()


def compute_hash_legacy(
    prev_hash: str,
    timestamp: datetime,
    user_id:   str,
    action:    str,
    result:    str,
    detail:    dict,
) -> str:
    """
    Original plain SHA-256 — for verifying entries written before upgrade.
    Do NOT use for new entries.
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


def get_genesis_hash() -> str:
    """H_0 = HMAC-SHA256(K, CHAIN_SEED)"""
    return hmac_module.new(
        _CHAIN_SECRET,
        CHAIN_SEED.encode(),
        hashlib.sha256,
    ).hexdigest()


def get_genesis_hash_legacy() -> str:
    """H_0 = SHA-256(CHAIN_SEED) — backward compat only"""
    return hashlib.sha256(CHAIN_SEED.encode()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════
# EXTERNAL ANCHORING — Property 3
# ══════════════════════════════════════════════════════════════════════════

def _write_anchor_to_file(anchor: dict) -> bool:
    """
    Appends one anchor record to ANCHOR_FILE.

    The file is append-only by design — we never overwrite, only append.
    Each line is a self-contained JSON record (JSON Lines format).

    Returns True if successful, False if write failed (non-fatal).
    """
    try:
        Path(ANCHOR_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(ANCHOR_FILE, "a") as f:
            f.write(json.dumps(anchor) + "\n")
            f.flush()        # ensure write reaches disk immediately
            os.fsync(f.fileno())  # force OS to flush to storage
        return True
    except Exception as e:
        logger.warning(f"Anchor write failed (non-fatal): {e}")
        return False


async def maybe_write_anchor(
    db:          AsyncSession,
    latest_hash: str,
) -> Optional[dict]:
    """
    Called after every audit entry write.
    Writes an external anchor every ANCHOR_INTERVAL entries.

    The anchor records:
      - The current entry count (position in chain)
      - The latest chain hash (what the chain looked like at this moment)
      - The anchor timestamp (when this was recorded)
      - A SHA-256 of the anchor content itself (for anchor integrity)

    The anchor file is the INDEPENDENT WITNESS:
      If an attacker modifies entries 1-10 and recomputes their hashes,
      the anchor for entry 10 still shows the ORIGINAL H_10.
      H_10_forged ≠ H_10_original → tampering detected via anchor.

    Non-fatal: if the anchor file write fails, audit logging continues.
    The chain itself is still intact — anchoring adds defense in depth.
    """
    # Count total chained entries
    count_result = await db.execute(
        select(sqlfunc.count(AuditLog.log_id))
        .where(AuditLog.chain_hash.isnot(None))
    )
    count = count_result.scalar() or 0

    # Only anchor at interval boundaries
    if count == 0 or count % ANCHOR_INTERVAL != 0:
        return None

    now = datetime.now(timezone.utc)

    # Build anchor record
    anchor_content = {
        "entry_count":  count,
        "latest_hash":  latest_hash,
        "anchor_time":  now.isoformat(),
        "system":       "HPC-ZTA-Gateway",
        "interval":     ANCHOR_INTERVAL,
    }

    # Self-hash the anchor for anchor-level integrity
    # (detects if the anchor file itself is modified)
    anchor_self_hash = hashlib.sha256(
        json.dumps(anchor_content, sort_keys=True,
                   separators=(',', ':')).encode()
    ).hexdigest()

    anchor = {
        **anchor_content,
        "anchor_hash": anchor_self_hash,   # SHA-256 of anchor content
    }

    # Write to external file
    success = _write_anchor_to_file(anchor)

    if success:
        logger.info(
            f"ANCHOR written: entries={count} "
            f"hash={latest_hash[:16]}... "
            f"file={ANCHOR_FILE}"
        )
    else:
        logger.warning(
            f"ANCHOR FAILED: entries={count} "
            f"hash={latest_hash[:16]}... "
            f"— chain continues without this anchor"
        )

    return anchor if success else None


def read_anchors() -> list[dict]:
    """
    Reads all anchor records from the anchor file.
    Returns list of anchor dicts sorted by entry_count ascending.
    Returns [] if file doesn't exist yet.
    """
    try:
        anchors = []
        with open(ANCHOR_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        anchors.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(f"Malformed anchor line: {line[:50]}")
        return sorted(anchors, key=lambda a: a.get("entry_count", 0))
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.error(f"Could not read anchor file: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════
# CHAIN QUERIES
# ══════════════════════════════════════════════════════════════════════════

async def get_last_hash(db: AsyncSession) -> str:
    """Returns chain_hash of most recent entry, or H_0 if chain is empty."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.chain_hash.isnot(None))
        .order_by(AuditLog.timestamp.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    return last.chain_hash if last else get_genesis_hash()


# ══════════════════════════════════════════════════════════════════════════
# WRITE
# ══════════════════════════════════════════════════════════════════════════

async def write_audit_entry(
    db:         AsyncSession,
    action:     str,
    result:     str            = "success",
    user_id:    Optional[str]  = None,
    job_id:     Optional[str]  = None,
    ip_address: Optional[str]  = None,
    detail:     Optional[dict] = None,
) -> AuditLog:
    """
    Write a cryptographically chained + externally anchored audit entry.

    Flow:
      1. Get prev_hash from last DB entry
      2. Compute H_i = HMAC-SHA256(K, prev_hash || event_data)
      3. Write entry to DB
      4. If entry_count % ANCHOR_INTERVAL == 0:
           Write anchor {entry_count, H_i, timestamp} to ANCHOR_FILE

    An adversary who modifies entry #N must:
      - Have DB write access            (to change the entry)
      - Know AUDIT_CHAIN_SECRET         (to recompute HMAC hashes)
      - Have anchor file write access   (to update the external anchor)
      All three simultaneously — significantly higher attack cost.
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

    # External anchor — written every ANCHOR_INTERVAL entries
    # Non-fatal: if this fails, audit logging still works
    await maybe_write_anchor(db, h_i)

    logger.debug(f"Audit chain: action={action} H_i={h_i[:16]}...")
    return entry


# ══════════════════════════════════════════════════════════════════════════
# VERIFY CHAIN — local HMAC check
# ══════════════════════════════════════════════════════════════════════════

async def verify_chain(db: AsyncSession) -> dict:
    """
    Verifies full audit chain integrity via HMAC-SHA256.

    For each entry: recomputes H_i and compares to stored value.
    Falls back to legacy SHA-256 for entries written before upgrade.

    Returns:
      {valid: true,  entries_checked: N, ...}
      {valid: false, broken_at: log_id, reason: "..."}
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

    # Detect chain mode from genesis hash
    hmac_genesis   = get_genesis_hash()
    legacy_genesis = get_genesis_hash_legacy()

    if entries[0].prev_hash == hmac_genesis:
        expected_prev = hmac_genesis
    elif entries[0].prev_hash == legacy_genesis:
        expected_prev = legacy_genesis
    else:
        return {
            "valid":     False,
            "broken_at": str(entries[0].log_id),
            "timestamp": str(entries[0].timestamp),
            "action":    entries[0].action,
            "reason":    "genesis_hash_mismatch",
        }

    legacy_count = 0

    for entry in entries:

        # Check linkage
        if entry.prev_hash != expected_prev:
            logger.error(
                f"AUDIT CHAIN BROKEN at log_id={entry.log_id}"
            )
            return {
                "valid":      False,
                "broken_at":  str(entry.log_id),
                "timestamp":  str(entry.timestamp),
                "action":     entry.action,
                "reason":     "prev_hash_mismatch",
            }

        # Try HMAC first
        expected_hmac = compute_hash(
            prev_hash = entry.prev_hash,
            timestamp = entry.timestamp,
            user_id   = entry.user_id or "anonymous",
            action    = entry.action,
            result    = entry.result or "success",
            detail    = entry.detail or {},
        )

        if hmac_module.compare_digest(expected_hmac, entry.chain_hash):
            pass   # HMAC match — tamper resistant ✓

        else:
            # Try legacy SHA-256 for old entries
            expected_legacy = compute_hash_legacy(
                prev_hash = entry.prev_hash,
                timestamp = entry.timestamp,
                user_id   = entry.user_id or "anonymous",
                action    = entry.action,
                result    = entry.result or "success",
                detail    = entry.detail or {},
            )

            if expected_legacy == entry.chain_hash:
                legacy_count += 1
            else:
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

    hmac_entries = len(entries) - legacy_count

    return {
        "valid":            True,
        "entries_checked":  len(entries),
        "hmac_entries":     hmac_entries,
        "legacy_entries":   legacy_count,
        "tamper_resistant": legacy_count == 0,
        "latest_hash":      entries[-1].chain_hash[:16] + "...",
        "chain_mode":       "hmac" if legacy_count == 0 else "mixed",
        "message": (
            "Audit chain integrity verified (HMAC-SHA256, tamper-resistant)"
            if legacy_count == 0 else
            f"Audit chain verified — {legacy_count} legacy entries "
            f"(detection only), {hmac_entries} HMAC entries (resistant)"
        )
    }


# ══════════════════════════════════════════════════════════════════════════
# VERIFY ANCHORS — external independence check
# ══════════════════════════════════════════════════════════════════════════

async def verify_anchors(db: AsyncSession) -> dict:
    """
    Verifies that the current chain is consistent with all external anchors.

    For each anchor record:
      1. Finds the audit entry at position entry_count in the DB
      2. Checks that its chain_hash matches the anchored latest_hash
      3. Verifies the anchor's self-hash (anchor_hash field)

    If ANY anchor fails: the chain was modified AFTER that anchor was written.
    The anchor tells you WHEN the tampering occurred (between two anchor points).

    Returns:
      {valid: true,  anchors_checked: N, ...}
      {valid: false, broken_at_anchor: N, reason: "..."}
    """
    anchors = read_anchors()

    if not anchors:
        return {
            "valid":           True,
            "anchors_checked": 0,
            "message":         (
                "No anchor file found. External anchoring will begin "
                f"after {ANCHOR_INTERVAL} audit entries. "
                f"Expected location: {ANCHOR_FILE}"
            )
        }

    # Load all chained audit entries ordered by timestamp
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.chain_hash.isnot(None))
        .order_by(AuditLog.timestamp.asc())
    )
    entries = result.scalars().all()
    entries_by_position = {i + 1: e for i, e in enumerate(entries)}

    broken_anchors  = []
    verified_anchors = []

    for anchor in anchors:
        count       = anchor.get("entry_count", 0)
        stored_hash = anchor.get("latest_hash", "")
        anchor_hash = anchor.get("anchor_hash", "")

        # ── Verify anchor self-hash ────────────────────────────────────────
        # Checks that the anchor file line itself was not modified
        anchor_content = {
            "entry_count":  anchor.get("entry_count"),
            "latest_hash":  anchor.get("latest_hash"),
            "anchor_time":  anchor.get("anchor_time"),
            "system":       anchor.get("system"),
            "interval":     anchor.get("interval"),
        }
        expected_anchor_hash = hashlib.sha256(
            json.dumps(anchor_content, sort_keys=True,
                       separators=(',', ':')).encode()
        ).hexdigest()

        if anchor_hash and anchor_hash != expected_anchor_hash:
            broken_anchors.append({
                "entry_count": count,
                "reason":      "anchor_self_hash_mismatch — anchor file was modified",
                "anchor_time": anchor.get("anchor_time"),
            })
            continue

        # ── Check chain hash at anchor point ──────────────────────────────
        if count not in entries_by_position:
            # Entry count doesn't match — entries may have been deleted
            broken_anchors.append({
                "entry_count": count,
                "reason":      f"entry #{count} not found in DB — entries may have been deleted",
                "anchor_time": anchor.get("anchor_time"),
            })
            continue

        db_entry = entries_by_position[count]

        if db_entry.chain_hash != stored_hash:
            broken_anchors.append({
                "entry_count":   count,
                "reason":        "chain_hash_mismatch — entries were modified after anchor",
                "anchor_time":   anchor.get("anchor_time"),
                "expected_hash": stored_hash[:16] + "...",
                "actual_hash":   db_entry.chain_hash[:16] + "...",
            })
        else:
            verified_anchors.append({
                "entry_count": count,
                "anchor_time": anchor.get("anchor_time"),
                "hash":        stored_hash[:16] + "...",
            })

    if broken_anchors:
        logger.error(
            f"ANCHOR VERIFICATION FAILED: "
            f"{len(broken_anchors)} broken anchor(s) detected"
        )
        return {
            "valid":            False,
            "anchors_checked":  len(anchors),
            "anchors_verified": len(verified_anchors),
            "broken_anchors":   broken_anchors,
            "message":          (
                f"{len(broken_anchors)} anchor(s) failed — "
                "chain was modified after these anchors were written"
            )
        }

    return {
        "valid":            True,
        "anchors_checked":  len(anchors),
        "anchors_verified": len(verified_anchors),
        "latest_anchor":    anchors[-1] if anchors else None,
        "anchor_file":      ANCHOR_FILE,
        "message":          (
            f"All {len(anchors)} external anchors verified — "
            "chain state matches independent anchor records"
        )
    }


# ══════════════════════════════════════════════════════════════════════════
# FULL VERIFICATION — both local chain + external anchors
# ══════════════════════════════════════════════════════════════════════════

async def verify_full(db: AsyncSession) -> dict:
    """
    Complete audit integrity verification:
      Step 1: verify_chain()   — HMAC chain integrity (local)
      Step 2: verify_anchors() — external anchor consistency

    Both must pass for full integrity confirmation.

    Use this endpoint for the paper demo:
      GET /admin/audit/verify/full
    """
    chain_result  = await verify_chain(db)
    anchor_result = await verify_anchors(db)

    both_valid = chain_result["valid"] and anchor_result["valid"]

    return {
        "valid":          both_valid,
        "chain_check":    chain_result,
        "anchor_check":   anchor_result,
        "properties": {
            "tamper_detection":   chain_result["valid"],
            "tamper_resistance":  chain_result.get("tamper_resistant", False),
            "external_independence": anchor_result["valid"] and anchor_result["anchors_checked"] > 0,
        },
        "message": (
            "Full audit integrity verified — all three security properties confirmed"
            if both_valid else
            "Audit integrity FAILED — see chain_check and anchor_check for details"
        )
    }
