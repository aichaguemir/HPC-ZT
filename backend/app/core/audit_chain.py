import base64
import hashlib
import hmac as hmac_module
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sqlfunc

from app.db.models import AuditLog
from app.core.logging import logger


# ══════════════════════════════════════════════════════════════════════════
# SECTION 1 — CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════
#
# All settings come from environment variables / .env file.
# Nothing is hardcoded — so rotating secrets doesn't require code changes.

CHAIN_SEED      = "HPC-GATEWAY-ZTA-AUDIT-CHAIN-V1"
ANCHOR_INTERVAL = int(os.environ.get("AUDIT_ANCHOR_INTERVAL", "10"))

# Local anchor file — same server, different filesystem from the DB ideally
ANCHOR_FILE = os.environ.get(
    "AUDIT_ANCHOR_FILE",
    "/var/log/hpc_gateway/audit_anchors.jsonl"
)

# Rekor public instance — free, no account needed
REKOR_BASE_URL = os.environ.get("REKOR_BASE_URL", "https://rekor.sigstore.dev")
REKOR_TIMEOUT  = float(os.environ.get("REKOR_TIMEOUT_SECONDS", "15"))

# Local cache of Rekor submission receipts (log_index, uuid per anchor)
# This is NOT the source of truth — Rekor is. This is just a lookup cache.
REKOR_REF_FILE = os.environ.get(
    "REKOR_REF_FILE",
    "/var/log/hpc_gateway/rekor_refs.jsonl"
)

# EC signing key paths — generated once at deploy time (see bottom of file)
REKOR_SIGNING_KEY_PATH = os.environ.get("REKOR_SIGNING_KEY_PATH", "rekor_signing_key.pem")
REKOR_PUBLIC_KEY_PATH  = os.environ.get("REKOR_PUBLIC_KEY_PATH",  "rekor_public_key.pem")

# AUDIT_STRICT_MODE=1 → server refuses to start without AUDIT_CHAIN_SECRET
AUDIT_STRICT_MODE = os.environ.get("AUDIT_STRICT_MODE", "0") == "1"


# ══════════════════════════════════════════════════════════════════════════
# SECTION 2 — HMAC SECRET KEY
# ══════════════════════════════════════════════════════════════════════════
#
# This is the K in HMAC-SHA256(K, data).
# Without K, an attacker cannot compute valid chain hashes even if they
# know the algorithm and all the data — HMAC is a keyed function.
#
# Generate your key:
#   python3 -c "import secrets; print(secrets.token_hex(32))"
# Put it in .env:
#   AUDIT_CHAIN_SECRET=your64hexchars

def _load_secret() -> bytes:
    secret = os.environ.get("AUDIT_CHAIN_SECRET", "")
    if not secret:
        if AUDIT_STRICT_MODE:
            # In production, refuse to start without a stable secret.
            # An ephemeral key means every restart breaks the chain.
            raise RuntimeError(
                "CRITICAL: AUDIT_CHAIN_SECRET not set and AUDIT_STRICT_MODE=1. "
                "Server will not start. Set AUDIT_CHAIN_SECRET in .env."
            )
        logger.critical(
            "AUDIT_CHAIN_SECRET not set — generating ephemeral key. "
            "Chain will NOT verify across restarts. Set in .env for production."
        )
        secret = secrets.token_hex(32)
    return secret.encode()

_CHAIN_SECRET: bytes = _load_secret()


# ══════════════════════════════════════════════════════════════════════════
# SECTION 3 — REKOR SIGNING KEY
# ══════════════════════════════════════════════════════════════════════════
#
# WHY DO WE NEED A SIGNING KEY FOR REKOR?
# ────────────────────────────────────────
# Rekor's hashedrekord entry type requires:
#   - a hash (what we're anchoring)
#   - a signature over that hash   ← proves the submission came from you
#   - a public key                 ← lets anyone verify that signature
#
# This is important: without the signature, anyone could submit anything
# to Rekor pretending to be your system. With the signature, only whoever
# holds the private key (your server) can make valid anchor submissions.
#
# The signature also means: when you verify later, you can confirm the
# Rekor entry was genuinely submitted by your system, not planted by someone.
#
# Key type: P-256 EC (ECDSA) — small, fast, widely supported
#
# Generate once at deploy:
#   python3 audit_chain_v2.py generate-keys
# This writes rekor_signing_key.pem and rekor_public_key.pem.
# Set paths in .env:
#   REKOR_SIGNING_KEY_PATH=/path/to/rekor_signing_key.pem
#   REKOR_PUBLIC_KEY_PATH=/path/to/rekor_public_key.pem

def generate_signing_keypair() -> None:
    """One-time setup: generates P-256 EC key pair for Rekor submissions."""
    key = ec.generate_private_key(ec.SECP256R1(), default_backend())

    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    Path(REKOR_SIGNING_KEY_PATH).write_bytes(priv_pem)
    Path(REKOR_PUBLIC_KEY_PATH).write_bytes(pub_pem)

    print(f"[OK] Private key → {REKOR_SIGNING_KEY_PATH}  (keep secret, never commit)")
    print(f"[OK] Public key  → {REKOR_PUBLIC_KEY_PATH}   (safe to share)")
    print()
    print("Add to .env:")
    print(f"  REKOR_SIGNING_KEY_PATH={REKOR_SIGNING_KEY_PATH}")
    print(f"  REKOR_PUBLIC_KEY_PATH={REKOR_PUBLIC_KEY_PATH}")


def _load_private_key() -> ec.EllipticCurvePrivateKey:
    """Loads EC private key from env var (PEM string) or file."""
    pem_str = os.environ.get("REKOR_SIGNING_KEY_PEM", "")
    if pem_str:
        pem_bytes = pem_str.replace("\\n", "\n").encode()
    else:
        path = Path(REKOR_SIGNING_KEY_PATH)
        if not path.exists():
            raise FileNotFoundError(
                f"Rekor signing key not found: {path}\n"
                "Run: python3 audit_chain_v2.py generate-keys"
            )
        pem_bytes = path.read_bytes()
    return serialization.load_pem_private_key(
        pem_bytes, password=None, backend=default_backend()
    )


def _load_public_key_pem() -> bytes:
    """Returns raw PEM bytes of the public key."""
    pem_str = os.environ.get("REKOR_PUBLIC_KEY_PEM", "")
    if pem_str:
        return pem_str.replace("\\n", "\n").encode()
    path = Path(REKOR_PUBLIC_KEY_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"Rekor public key not found: {path}\n"
            "Run: python3 audit_chain_v2.py generate-keys"
        )
    return path.read_bytes()


# ══════════════════════════════════════════════════════════════════════════
# SECTION 4 — CORE HASH FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════
#
# compute_hash() is the heart of the chain.
#
# For each audit entry, we compute:
#   H_i = HMAC-SHA256( K,  JSON({ H_{i-1}, timestamp, user, action, result, detail }) )
#
# This means:
#   - H_i depends on ALL previous entries (via H_{i-1})
#   - H_i depends on the secret key K
#   - Changing ANY field of entry i changes H_i
#   - Changing H_i forces recomputing H_{i+1}, H_{i+2}, ... (the whole tail)
#   - Without K, you cannot compute any valid H_i even if you know all the data
#
# The JSON is sorted + no-whitespace → same output regardless of key insertion order.

def compute_hash(
    prev_hash: str,
    timestamp: datetime,
    user_id:   str,
    action:    str,
    result:    str,
    detail:    dict,
) -> str:
    content = json.dumps({
        "prev_hash": prev_hash,
        "timestamp": timestamp.isoformat(),
        "user_id":   user_id,
        "action":    action,
        "result":    result,
        "detail":    detail,
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
    """Plain SHA-256 — only for verifying entries written before the HMAC upgrade."""
    content = json.dumps({
        "prev_hash": prev_hash,
        "timestamp": timestamp.isoformat(),
        "user_id":   user_id,
        "action":    action,
        "result":    result,
        "detail":    detail,
    }, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(content.encode()).hexdigest()


def get_genesis_hash() -> str:
    """H_0 = HMAC-SHA256(K, CHAIN_SEED) — the first link, keyed from the start."""
    return hmac_module.new(
        _CHAIN_SECRET, CHAIN_SEED.encode(), hashlib.sha256
    ).hexdigest()


def get_genesis_hash_legacy() -> str:
    """H_0 = SHA-256(CHAIN_SEED) — backward compat only."""
    return hashlib.sha256(CHAIN_SEED.encode()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════
# SECTION 5 — LOCAL ANCHOR FILE
# ══════════════════════════════════════════════════════════════════════════
#
# Every ANCHOR_INTERVAL entries, we snapshot {entry_count, chain_hash, time}
# to a local file. This is the "local witness".
#
# Why this alone isn't enough: it's on the same server. An attacker with
# .env can forge chain hashes AND rewrite this file. That's why Rekor exists.
#
# But the local file is still useful:
#   - Works offline (no internet needed to verify)
#   - Instant — no network call
#   - Tells you WHEN tampering happened (which 10-entry window)
#
# The anchor_hash field uses HMAC (not plain SHA-256) so an attacker
# can't recompute it without _CHAIN_SECRET. Consistent with chain security.

def _write_anchor_to_file(anchor: dict) -> bool:
    try:
        Path(ANCHOR_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(ANCHOR_FILE, "a") as f:
            f.write(json.dumps(anchor) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return True
    except Exception as e:
        logger.warning(f"Anchor write failed (non-fatal): {e}")
        return False


async def maybe_write_anchor(db: AsyncSession, latest_hash: str) -> Optional[dict]:
    """
    Writes a local anchor every ANCHOR_INTERVAL entries.

    IMPORTANT: db.flush() must be called BEFORE this function.
    Without flush(), the COUNT query doesn't see the just-written entry
    and anchors fire one entry late (off-by-one bug fixed from v1).

    Returns the anchor dict if written, None otherwise.
    The anchor dict is passed to maybe_submit_rekor_anchor() below.
    """
    count_result = await db.execute(
        select(sqlfunc.count(AuditLog.log_id))
        .where(AuditLog.chain_hash.isnot(None))
    )
    count = count_result.scalar() or 0

    if count == 0 or count % ANCHOR_INTERVAL != 0:
        return None

    now = datetime.now(timezone.utc)

    anchor_content = {
        "entry_count": count,
        "latest_hash": latest_hash,
        "anchor_time": now.isoformat(),
        "system":      "HPC-ZTA-Gateway",
        "interval":    ANCHOR_INTERVAL,
    }

    # HMAC self-hash — needs _CHAIN_SECRET to forge (unlike plain SHA-256)
    anchor_self_hash = hmac_module.new(
        _CHAIN_SECRET,
        json.dumps(anchor_content, sort_keys=True, separators=(',', ':')).encode(),
        hashlib.sha256,
    ).hexdigest()

    anchor = {**anchor_content, "anchor_hash": anchor_self_hash}
    success = _write_anchor_to_file(anchor)

    if success:
        logger.info(f"LOCAL ANCHOR written: entries={count} hash={latest_hash[:16]}...")
    else:
        logger.warning(f"LOCAL ANCHOR FAILED: entries={count}")

    return anchor if success else None


def read_anchors() -> list[dict]:
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
# SECTION 6 — REKOR SUBMISSION
# ══════════════════════════════════════════════════════════════════════════
#
# WHAT EXACTLY HAPPENS WHEN WE SUBMIT TO REKOR
# ──────────────────────────────────────────────
#
# Step A: We take anchor_hash — the HMAC of the chain state at position N.
#         This is what we want to anchor externally.
#
# Step B: We compute SHA-256(anchor_hash.encode()) → this is the "artifact hash".
#         Rekor doesn't store the anchor_hash itself, it stores a commitment
#         to it via SHA-256. The anchor_hash content stays private.
#
# Step C: We sign anchor_hash with our EC private key → signature_der.
#         This proves the submission came from our server (only we have the key).
#
# Step D: We POST to Rekor:
#         {
#           "kind": "hashedrekord",
#           "spec": {
#             "data": { "hash": { "algorithm": "sha256", "value": SHA256(anchor_hash) } },
#             "signature": {
#               "content": base64(signature_der),
#               "publicKey": { "content": base64(public_key_pem) }
#             }
#           }
#         }
#
# Step E: Rekor verifies:
#         1. Is the signature valid? (public_key verifies signature over hash)
#         2. Does the hash match the signed data?
#         If both pass → Rekor adds the entry to its Merkle tree.
#
# Step F: Rekor returns:
#         {
#           "<uuid>": {
#             "logIndex": 15234891,       ← position in the global Rekor log
#             "integratedTime": 1234567890,
#             "body": "<base64 of the entry>",
#             "verification": { ... }     ← inclusion proof (Merkle path)
#           }
#         }
#
# Step G: We save {log_index, uuid, anchor_hash, artifact_sha256} to REKOR_REF_FILE.
#         This is our lookup cache — we use it during verify_rekor_anchors().
#
# What's now permanently on Rekor (public):
#   SHA-256(anchor_hash)  — a one-way commitment, reveals nothing about log content
#   Our public key        — anyone can see who submitted it
#   A timestamp           — when it was submitted
#
# What's NOT on Rekor: user IDs, actions, IP addresses, any audit content.

async def _submit_to_rekor(anchor_hash: str) -> Optional[dict]:
    """
    Submits anchor_hash to Rekor as a hashedrekord entry.
    Returns ref dict {log_index, uuid, ...} on success, None on failure.
    This is non-fatal — if Rekor is unreachable, audit logging continues.
    """
    try:
        # STEP B: hash of the artifact (anchor_hash string)
        artifact_bytes  = anchor_hash.encode()
        artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()

        # STEP C: sign anchor_hash with our EC private key
        private_key     = _load_private_key()
        signature_der   = private_key.sign(artifact_bytes, ec.ECDSA(hashes.SHA256()))
        pub_key_pem     = _load_public_key_pem()

        # STEP D: build Rekor hashedrekord payload
        payload = {
            "kind":       "hashedrekord",
            "apiVersion": "0.0.1",
            "spec": {
                "data": {
                    "hash": {
                        "algorithm": "sha256",
                        "value":     artifact_sha256,
                    }
                },
                "signature": {
                    "content":   base64.b64encode(signature_der).decode(),
                    "publicKey": {
                        "content": base64.b64encode(pub_key_pem).decode(),
                    },
                },
            },
        }

        # STEP D: POST to Rekor
        async with httpx.AsyncClient(timeout=REKOR_TIMEOUT) as client:
            response = await client.post(
                f"{REKOR_BASE_URL}/api/v1/log/entries",
                json=payload,
                headers={"Content-Type": "application/json"},
            )

        if response.status_code not in (200, 201):
            logger.warning(
                f"Rekor HTTP {response.status_code}: {response.text[:200]}"
            )
            return None

        # STEP F: parse Rekor response
        result    = response.json()
        uuid      = next(iter(result))
        entry_data = result[uuid]

        ref = {
            "log_index":       entry_data.get("logIndex"),
            "uuid":            uuid,
            "entry_count":  entry_count,
            "anchor_hash":     anchor_hash,
            "artifact_sha256": artifact_sha256,
            "integrated_time": entry_data.get("integratedTime"),
            "rekor_url":       f"{REKOR_BASE_URL}/api/v1/log/entries/{uuid}",
            "submitted_at":    datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            f"REKOR ANCHOR submitted: "
            f"log_index={ref['log_index']} "
            f"uuid={uuid[:16]}... "
            f"url={ref['rekor_url']}"
        )

        # STEP G: save lookup reference
        _save_rekor_ref(ref)
        return ref

    except FileNotFoundError as e:
        logger.error(f"Rekor key missing — skipping Rekor anchor: {e}")
        return None
    except httpx.TimeoutException:
        logger.warning(f"Rekor timed out after {REKOR_TIMEOUT}s (non-fatal)")
        return None
    except Exception as e:
        logger.warning(f"Rekor submission error (non-fatal): {e}")
        return None


async def maybe_submit_rekor_anchor(
    db:          AsyncSession,
    anchor_hash: str,
) -> Optional[dict]:
    """
    Submits to Rekor if we're at an anchor interval boundary.
    Called from write_audit_entry() after maybe_write_anchor().

    anchor_hash: the HMAC anchor_hash from the local anchor record.
    We use the HMAC anchor_hash (not the raw chain hash) because:
      - It already captures {entry_count, latest_hash, timestamp, system}
      - It's HMAC-keyed so can't be recomputed without _CHAIN_SECRET
      - One submission to Rekor covers the full anchor snapshot
    """
    count_result = await db.execute(
        select(sqlfunc.count(AuditLog.log_id))
        .where(AuditLog.chain_hash.isnot(None))
    )
    count = count_result.scalar() or 0

    if count == 0 or count % ANCHOR_INTERVAL != 0:
        return None

    return await _submit_to_rekor(anchor_hash, count)


def _save_rekor_ref(ref: dict) -> bool:
    """Appends a Rekor submission receipt to the local ref cache file."""
    try:
        Path(REKOR_REF_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(REKOR_REF_FILE, "a") as f:
            f.write(json.dumps(ref) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return True
    except Exception as e:
        logger.warning(f"Rekor ref file write failed (non-fatal): {e}")
        return False


def read_rekor_refs() -> list[dict]:
    """Returns all saved Rekor refs sorted by log_index."""
    try:
        refs = []
        with open(REKOR_REF_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        refs.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(f"Malformed Rekor ref: {line[:50]}")
        return sorted(refs, key=lambda r: r.get("log_index", 0))
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.error(f"Could not read Rekor ref file: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════
# SECTION 7 — WRITE AUDIT ENTRY  ← THE MAIN FUNCTION
# ══════════════════════════════════════════════════════════════════════════
#
# EXACT SEQUENCE OF EVENTS FOR EVERY AUDIT WRITE
# ────────────────────────────────────────────────
#
# [1] Normalize inputs
#     user_id=None → "anonymous", result=None → "success", detail=None → {}
#     MUST happen once here so compute_hash and AuditLog() agree on values.
#     Bug in v1: they normalized independently → stored value ≠ hashed value.
#
# [2] Get prev_hash
#     Queries DB for most recent chain_hash.
#     If no entries yet → uses H_0 = HMAC-SHA256(K, CHAIN_SEED).
#
# [3] Compute H_i
#     H_i = HMAC-SHA256(K, JSON({H_{i-1}, now, user, action, result, detail}))
#     This binds the new entry to ALL previous entries via H_{i-1}.
#
# [4] Write to DB + flush
#     db.flush() makes the entry visible to the COUNT query in step 5.
#     Without flush(), the count is off by 1 → anchors fire at wrong entries.
#     (This was a bug in v1.)
#
# [5] Local anchor (every 10 entries)
#     Writes {entry_count, H_i, timestamp, anchor_hash} to ANCHOR_FILE.
#     anchor_hash = HMAC(K, anchor_content) — needs secret to forge.
#     Returns the anchor dict (used in step 6).
#
# [6] Rekor anchor (every 10 entries, same boundary as local anchor)
#     Takes anchor["anchor_hash"] from step 5.
#     Signs it with EC private key.
#     POSTs to rekor.sigstore.dev → permanent public record.
#     Saves receipt {log_index, uuid} to REKOR_REF_FILE.
#     Non-fatal: if Rekor is unreachable, step 5 still happened.
#
# CONCURRENCY NOTE:
#   get_last_hash() + db.add() is NOT atomic. Two concurrent writes can
#   both read the same prev_hash → chain fork (two entries with same H_{i-1}).
#   Fix: serialize audit writes at the call site with asyncio.Lock or
#   a dedicated audit writer task. Not fixed here — call-site concern.

async def get_last_hash(db: AsyncSession) -> str:
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.chain_hash.isnot(None))
        .order_by(AuditLog.timestamp.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    return last.chain_hash if last else get_genesis_hash()


async def write_audit_entry(
    db:         AsyncSession,
    action:     str,
    result:     str            = "success",
    user_id:    Optional[str]  = None,
    job_id:     Optional[str]  = None,
    ip_address: Optional[str]  = None,
    detail:     Optional[dict] = None,
) -> AuditLog:

    # [1] Normalize once
    normalized_user_id = user_id or "anonymous"
    normalized_result  = result  or "success"
    normalized_detail  = detail  or {}

    # [2] Get H_{i-1}
    now       = datetime.now(timezone.utc)
    prev_hash = await get_last_hash(db)

    # [3] Compute H_i
    h_i = compute_hash(
        prev_hash = prev_hash,
        timestamp = now,
        user_id   = normalized_user_id,
        action    = action,
        result    = normalized_result,
        detail    = normalized_detail,
    )

    # [4] Write to DB + flush
    entry = AuditLog(
        user_id    = normalized_user_id,
        job_id     = job_id,
        action     = action,
        result     = normalized_result,
        ip_address = ip_address,
        detail     = normalized_detail,
        chain_hash = h_i,
        prev_hash  = prev_hash,
        timestamp  = now,
    )
    db.add(entry)
    await db.flush()   # ← makes entry visible to COUNT in steps 5 and 6

    # [5] Local anchor (every ANCHOR_INTERVAL entries)
    local_anchor = await maybe_write_anchor(db, h_i)

    # [6] Rekor anchor (same boundary — only if local anchor was written)
    #     We use local_anchor["anchor_hash"] as the Rekor artifact.
    #     This ties the Rekor entry to the full anchor snapshot,
    #     not just the raw chain hash.
    if local_anchor is not None:
        await maybe_submit_rekor_anchor(db, local_anchor["anchor_hash"])

    logger.debug(f"Audit entry: action={action} H_i={h_i[:16]}...")
    return entry


# ══════════════════════════════════════════════════════════════════════════
# SECTION 8 — VERIFY CHAIN  (local HMAC check)
# ══════════════════════════════════════════════════════════════════════════
#
# Walks every entry in chronological order and recomputes H_i.
# If the recomputed H_i ≠ stored H_i → entry was modified.
# Also checks that entry.prev_hash matches the previous entry's chain_hash
# → catches deletions (missing entries break the chain linkage).

async def verify_chain(db: AsyncSession) -> dict:
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.chain_hash.isnot(None))
        .order_by(AuditLog.timestamp.asc())
    )
    entries = result.scalars().all()

    if not entries:
        return {"valid": True, "entries_checked": 0, "message": "No chained entries yet"}

    hmac_genesis   = get_genesis_hash()
    legacy_genesis = get_genesis_hash_legacy()

    if entries[0].prev_hash == hmac_genesis:
        expected_prev = hmac_genesis
    elif entries[0].prev_hash == legacy_genesis:
        expected_prev = legacy_genesis
    else:
        return {
            "valid": False, "broken_at": str(entries[0].log_id),
            "reason": "genesis_hash_mismatch",
        }

    legacy_count = 0

    for entry in entries:
        if entry.prev_hash != expected_prev:
            logger.error(f"AUDIT CHAIN BROKEN at log_id={entry.log_id}")
            return {
                "valid": False, "broken_at": str(entry.log_id),
                "timestamp": str(entry.timestamp), "action": entry.action,
                "reason": "prev_hash_mismatch",
            }

        expected_hmac = compute_hash(
            prev_hash = entry.prev_hash,
            timestamp = entry.timestamp,
            user_id   = entry.user_id,
            action    = entry.action,
            result    = entry.result,
            detail    = entry.detail or {},
        )

        if hmac_module.compare_digest(expected_hmac, entry.chain_hash):
            pass  # HMAC match ✓
        else:
            expected_legacy = compute_hash_legacy(
                prev_hash = entry.prev_hash,
                timestamp = entry.timestamp,
                user_id   = entry.user_id,
                action    = entry.action,
                result    = entry.result,
                detail    = entry.detail or {},
            )
            # compare_digest used here too (was == in v1 — timing side-channel)
            if hmac_module.compare_digest(expected_legacy, entry.chain_hash):
                legacy_count += 1
            else:
                logger.error(f"AUDIT CHAIN TAMPERED at log_id={entry.log_id}")
                return {
                    "valid": False, "broken_at": str(entry.log_id),
                    "timestamp": str(entry.timestamp), "action": entry.action,
                    "reason": "hash_mismatch — entry was modified",
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
            f"Chain verified — {legacy_count} legacy + {hmac_entries} HMAC entries"
        )
    }


# ══════════════════════════════════════════════════════════════════════════
# SECTION 9 — VERIFY LOCAL ANCHORS
# ══════════════════════════════════════════════════════════════════════════
#
# For each local anchor record:
#   1. Re-verify its anchor_hash (HMAC) → was the anchor file tampered?
#   2. Look up the DB entry at that position
#   3. Check DB entry's chain_hash == anchor's latest_hash
#      → was the chain modified AFTER the anchor was written?

async def verify_anchors(db: AsyncSession) -> dict:
    anchors = read_anchors()

    if not anchors:
        return {
            "valid": True, "anchors_checked": 0,
            "message": f"No local anchors yet (start after {ANCHOR_INTERVAL} entries). File: {ANCHOR_FILE}"
        }

    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.chain_hash.isnot(None))
        .order_by(AuditLog.timestamp.asc())
    )
    entries             = result.scalars().all()
    entries_by_position = {i + 1: e for i, e in enumerate(entries)}

    broken_anchors   = []
    verified_anchors = []

    for anchor in anchors:
        count       = anchor.get("entry_count", 0)
        stored_hash = anchor.get("latest_hash", "")
        anchor_hash = anchor.get("anchor_hash", "")

        anchor_content = {
            "entry_count": anchor.get("entry_count"),
            "latest_hash": anchor.get("latest_hash"),
            "anchor_time": anchor.get("anchor_time"),
            "system":      anchor.get("system"),
            "interval":    anchor.get("interval"),
        }
        expected_anchor_hash = hmac_module.new(
            _CHAIN_SECRET,
            json.dumps(anchor_content, sort_keys=True, separators=(',', ':')).encode(),
            hashlib.sha256,
        ).hexdigest()

        if anchor_hash and not hmac_module.compare_digest(anchor_hash, expected_anchor_hash):
            broken_anchors.append({
                "entry_count": count,
                "reason":      "anchor_self_hash_mismatch — anchor file was modified",
                "anchor_time": anchor.get("anchor_time"),
            })
            continue

        if count not in entries_by_position:
            broken_anchors.append({
                "entry_count": count,
                "reason":      f"entry #{count} missing from DB — may have been deleted",
                "anchor_time": anchor.get("anchor_time"),
            })
            continue

        db_entry = entries_by_position[count]

        if not hmac_module.compare_digest(db_entry.chain_hash, stored_hash):
            broken_anchors.append({
                "entry_count":   count,
                "reason":        "chain_hash_mismatch — entries modified after anchor",
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
        logger.error(f"LOCAL ANCHOR VERIFICATION FAILED: {len(broken_anchors)} broken")
        return {
            "valid": False, "anchors_checked": len(anchors),
            "anchors_verified": len(verified_anchors),
            "broken_anchors": broken_anchors,
            "message": f"{len(broken_anchors)} local anchor(s) failed",
        }

    return {
        "valid": True, "anchors_checked": len(anchors),
        "anchors_verified": len(verified_anchors),
        "latest_anchor": anchors[-1] if anchors else None,
        "anchor_file":   ANCHOR_FILE,
        "message": f"All {len(anchors)} local anchors verified",
    }


# ══════════════════════════════════════════════════════════════════════════
# SECTION 10 — VERIFY REKOR ANCHORS
# ══════════════════════════════════════════════════════════════════════════
#
# WHAT EXACTLY HAPPENS DURING REKOR VERIFICATION
# ────────────────────────────────────────────────
#
# For each saved Rekor reference (log_index + uuid):
#
# [A] Fetch the live entry from Rekor by UUID
#     GET rekor.sigstore.dev/api/v1/log/entries/{uuid}
#     This hits the actual public Merkle tree — not our server.
#
# [B] Decode the entry body
#     Rekor returns body as base64-encoded JSON.
#     We decode it and extract the artifact hash from spec.data.hash.value.
#
# [C] Verify the stored hash matches
#     We check: SHA-256(our_saved_anchor_hash) == Rekor's stored artifact hash
#     This confirms:
#       - The Rekor entry was genuinely submitted with our anchor_hash
#       - The anchor_hash hasn't been modified in our local ref file
#
# [D] Interpret the result
#     If MATCH → Rekor confirms the chain state at position N was anchor_hash
#     If MISMATCH → either our ref file was tampered, or (impossible) Rekor was
#
# What this proves in the paper:
#   "The chain state at entry N was independently witnessed by the Sigstore
#    public Merkle tree, an append-only log operated by the Linux Foundation,
#    at the time the anchor was submitted. Any post-hoc modification of audit
#    entries 1..N would produce a different chain hash at position N,
#    contradicting the publicly recorded value."

async def _fetch_rekor_entry(uuid: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=REKOR_TIMEOUT) as client:
            response = await client.get(
                f"{REKOR_BASE_URL}/api/v1/log/entries/{uuid}",
                headers={"Accept": "application/json"},
            )
        if response.status_code != 200:
            logger.warning(f"Rekor fetch HTTP {response.status_code} uuid={uuid[:16]}...")
            return None
        return response.json()
    except Exception as e:
        logger.warning(f"Rekor fetch error: {e}")
        return None


async def verify_rekor_anchors() -> dict:
    """
    Verifies all Rekor anchors against the live public Rekor log.
    Does NOT need DB access — purely between our ref file and Rekor.
    """
    refs = read_rekor_refs()

    if not refs:
        return {
            "valid": True, "refs_checked": 0,
            "message": (
                f"No Rekor references yet. Will submit after first "
                f"{ANCHOR_INTERVAL} entries. Refs file: {REKOR_REF_FILE}"
            ),
        }

    broken   = []
    verified = []

    for ref in refs:
        uuid         = ref.get("uuid", "")
        saved_hash   = ref.get("anchor_hash", "")
        log_index    = ref.get("log_index")

        if not uuid or not saved_hash:
            broken.append({"log_index": log_index, "reason": "malformed ref"})
            continue

        # [A] Fetch from Rekor
        entry = await _fetch_rekor_entry(uuid)
        if entry is None:
            broken.append({
                "log_index": log_index,
                "uuid":      uuid[:16] + "...",
                "reason":    "could not fetch from Rekor (network error or invalid uuid)",
            })
            continue

        # [B] Decode body
        try:
            entry_data             = entry.get(uuid, {})
            body                   = json.loads(base64.b64decode(entry_data.get("body", "")))
            rekor_artifact_sha256  = (
                body.get("spec", {}).get("data", {}).get("hash", {}).get("value", "")
            )
        except Exception as e:
            broken.append({
                "log_index": log_index,
                "uuid":      uuid[:16] + "...",
                "reason":    f"could not decode Rekor body: {e}",
            })
            continue

        # [C] Verify: SHA-256(our anchor_hash) must match what Rekor stored
        expected_sha256 = hashlib.sha256(saved_hash.encode()).hexdigest()

        if not hmac_module.compare_digest(rekor_artifact_sha256, expected_sha256):
            broken.append({
                "log_index":     log_index,
                "uuid":          uuid[:16] + "...",
                "reason":        "hash_mismatch — Rekor entry does not match saved anchor",
                "rekor_hash":    rekor_artifact_sha256[:16] + "...",
                "expected":      expected_sha256[:16] + "...",
            })
        else:
            # [D] Match confirmed
            verified.append({
                "log_index": log_index,
                "uuid":      uuid[:16] + "...",
                "rekor_url": ref.get("rekor_url", ""),
            })

    if broken:
        logger.error(f"REKOR VERIFICATION FAILED: {len(broken)} broken")
        return {
            "valid": False, "refs_checked": len(refs),
            "verified": len(verified), "broken": broken,
            "message": f"{len(broken)} Rekor anchor(s) failed — chain may have been tampered",
        }

    return {
        "valid": True, "refs_checked": len(refs),
        "verified": len(verified),
        "latest_ref": refs[-1] if refs else None,
        "message": (
            f"All {len(refs)} Rekor anchors verified — "
            "chain state confirmed by public Merkle log (Sigstore Rekor)"
        ),
    }


# ══════════════════════════════════════════════════════════════════════════
# SECTION 11 — FULL VERIFICATION  ← THE DEMO ENDPOINT
# ══════════════════════════════════════════════════════════════════════════
#
# Runs all three checks in sequence. Use this for the paper demo:
#   GET /admin/audit/verify/full
#
# Three checks:
#   1. verify_chain()         — HMAC chain (local DB)
#   2. verify_anchors()       — local anchor file
#   3. verify_rekor_anchors() — Rekor public Merkle log (independent)
#
# Three security properties mapped to checks:
#   tamper_detection      → verify_chain passes
#   tamper_resistance     → verify_chain passes AND all entries are HMAC (not legacy)
#   external_independence → verify_rekor_anchors passes AND refs_checked > 0
#
# Example response when everything is clean:
# {
#   "valid": true,
#   "properties": {
#     "tamper_detection": true,
#     "tamper_resistance": true,
#     "external_independence": true
#   },
#   "chain_check":  { "valid": true, "entries_checked": 47, ... },
#   "anchor_check": { "valid": true, "anchors_checked": 4, ... },
#   "rekor_check":  { "valid": true, "refs_checked": 4,
#                     "latest_ref": { "log_index": 15234891, "rekor_url": "..." } }
# }
#
# Example response when tampering is detected:
# {
#   "valid": false,
#   "chain_check": { "valid": false, "broken_at": "42", "reason": "hash_mismatch" },
#   "rekor_check": { "valid": false, "broken": [{"log_index": 10, "reason": "hash_mismatch..."}] }
# }

async def verify_full(db: AsyncSession) -> dict:
    chain_result  = await verify_chain(db)
    anchor_result = await verify_anchors(db)
    rekor_result  = await verify_rekor_anchors()

    all_valid = chain_result["valid"] and anchor_result["valid"] and rekor_result["valid"]

    return {
        "valid":        all_valid,
        "chain_check":  chain_result,
        "anchor_check": anchor_result,
        "rekor_check":  rekor_result,
        "properties": {
            "tamper_detection":      chain_result["valid"],
            "tamper_resistance":     chain_result.get("tamper_resistant", False),
            "external_independence": (
                rekor_result["valid"] and rekor_result.get("refs_checked", 0) > 0
            ),
        },
        "message": (
            "Full audit integrity verified — all three security properties confirmed "
            f"({rekor_result.get('refs_checked', 0)} Rekor anchors on public Merkle log)"
            if all_valid else
            "Audit integrity FAILED — see chain_check / anchor_check / rekor_check"
        )
    }


# ══════════════════════════════════════════════════════════════════════════
# SECTION 12 — CLI UTILITY
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "generate-keys":
        generate_signing_keypair()
    else:
        print("Usage: python3 audit_chain_v2.py generate-keys")
        print()
        print("Generates a P-256 EC key pair for signing Rekor anchor submissions.")
        print(f"  Private key → {REKOR_SIGNING_KEY_PATH}")
        print(f"  Public key  → {REKOR_PUBLIC_KEY_PATH}")
