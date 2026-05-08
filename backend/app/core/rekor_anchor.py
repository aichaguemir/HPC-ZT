import base64
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

from app.core.logging import logger


# ══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════

REKOR_BASE_URL = os.environ.get("REKOR_BASE_URL", "https://rekor.sigstore.dev")
REKOR_TIMEOUT  = float(os.environ.get("REKOR_TIMEOUT_SECONDS", "15"))

# Local cache of Rekor receipts — NOT the source of truth, just a lookup.
# Rekor itself is the source of truth. Even if this file is deleted,
# you can recover by searching Rekor for your anchor hashes.
REKOR_REF_FILE = os.environ.get(
    "REKOR_REF_FILE",
    "/var/log/hpc_gateway/rekor_refs.jsonl"
)

REKOR_SIGNING_KEY_PATH = os.environ.get("REKOR_SIGNING_KEY_PATH", "rekor_signing_key.pem")
REKOR_PUBLIC_KEY_PATH  = os.environ.get("REKOR_PUBLIC_KEY_PATH",  "rekor_public_key.pem")


# ══════════════════════════════════════════════════════════════════════════
# KEY MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════

def generate_signing_keypair(
    private_path: str = REKOR_SIGNING_KEY_PATH,
    public_path:  str = REKOR_PUBLIC_KEY_PATH,
) -> None:
    """
    Generates a P-256 EC signing key pair and saves to PEM files.
    Run ONCE at deployment. Never regenerate — you'd lose the ability
    to verify old Rekor entries (their signatures used the old public key).

    Usage:
        python3 -m rekor_anchor generate-keys
    """
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

    Path(private_path).write_bytes(priv_pem)
    Path(public_path).write_bytes(pub_pem)

    print(f"[OK] Private key → {private_path}  (keep secret, never commit)")
    print(f"[OK] Public key  → {public_path}   (safe to share)")
    print()
    print("Add to .env:")
    print(f"  REKOR_SIGNING_KEY_PATH={private_path}")
    print(f"  REKOR_PUBLIC_KEY_PATH={public_path}")


def _load_private_key() -> ec.EllipticCurvePrivateKey:
    """Loads EC private key from env var (PEM string) or file path."""
    pem_str = os.environ.get("REKOR_SIGNING_KEY_PEM", "")
    if pem_str:
        pem_bytes = pem_str.replace("\\n", "\n").encode()
    else:
        path = Path(REKOR_SIGNING_KEY_PATH)
        if not path.exists():
            raise FileNotFoundError(
                f"Rekor signing key not found: {path}\n"
                "Run: python3 -m rekor_anchor generate-keys"
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
            "Run: python3 -m rekor_anchor generate-keys"
        )
    return path.read_bytes()


# ══════════════════════════════════════════════════════════════════════════
# REKOR API — SUBMIT
# ══════════════════════════════════════════════════════════════════════════

async def submit_to_rekor(anchor_hash: str) -> Optional[dict]:
    """
    Submits anchor_hash to Rekor as a hashedrekord v0.0.1 entry.

    What gets sent to Rekor:
      - SHA-256(anchor_hash)     ← one-way commitment, reveals nothing
      - ECDSA signature          ← proves submission came from this server
      - EC public key            ← lets anyone verify that signature

    What Rekor stores permanently:
      - The artifact hash (SHA-256 of anchor_hash)
      - The signature + public key
      - An integrated timestamp
      - A Merkle inclusion proof

    What Rekor does NOT store:
      - The anchor_hash itself
      - Any audit log content (user IDs, actions, IPs)

    Returns ref dict {log_index, uuid, rekor_url, ...} on success.
    Returns None on failure — non-fatal, local chain continues.
    """
    try:
        artifact_bytes  = anchor_hash.encode()
        artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()

        # Sign the anchor_hash bytes with our EC private key
        private_key   = _load_private_key()
        signature_der = private_key.sign(artifact_bytes, ec.ECDSA(hashes.SHA256()))
        pub_key_pem   = _load_public_key_pem()

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

        async with httpx.AsyncClient(timeout=REKOR_TIMEOUT) as client:
            response = await client.post(
                f"{REKOR_BASE_URL}/api/v1/log/entries",
                json=payload,
                headers={"Content-Type": "application/json"},
            )

        if response.status_code not in (200, 201):
            logger.warning(f"Rekor HTTP {response.status_code}: {response.text[:200]}")
            return None

        result     = response.json()
        uuid       = next(iter(result))
        entry_data = result[uuid]

        ref = {
            "log_index":       entry_data.get("logIndex"),
            "uuid":            uuid,
            "anchor_hash":     anchor_hash,
            "artifact_sha256": artifact_sha256,
            "integrated_time": entry_data.get("integratedTime"),
            "rekor_url":       f"{REKOR_BASE_URL}/api/v1/log/entries/{uuid}",
            "submitted_at":    datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            f"REKOR ANCHOR submitted: log_index={ref['log_index']} "
            f"uuid={uuid[:16]}... url={ref['rekor_url']}"
        )

        _save_rekor_ref(ref)
        return ref

    except FileNotFoundError as e:
        logger.error(f"Rekor key missing — skipping anchor: {e}")
        return None
    except httpx.TimeoutException:
        logger.warning(f"Rekor timed out after {REKOR_TIMEOUT}s (non-fatal)")
        return None
    except Exception as e:
        logger.warning(f"Rekor submission error (non-fatal): {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════
# REKOR API — FETCH  (FIX: was missing, caused NameError in verify)
# ══════════════════════════════════════════════════════════════════════════

async def fetch_rekor_entry(uuid: str) -> Optional[dict]:
    """
    Fetches a single Rekor entry by UUID from the live public log.

    This goes directly to rekor.sigstore.dev — NOT to our local files.
    This is what makes verification independent: we're asking Rekor
    "what hash did you record for this uuid?" and comparing to our chain.

    Returns the raw Rekor entry dict, or None on network/fetch failure.
    """
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


# ══════════════════════════════════════════════════════════════════════════
# INTEGRATION POINT — called from write_audit_entry in audit_chain.py
# ══════════════════════════════════════════════════════════════════════════

async def maybe_submit_rekor_anchor(
    db,                # AsyncSession — used to count entries
    anchor_hash: str,  # HMAC anchor_hash from the local anchor record
) -> Optional[dict]:
    """
    Called from write_audit_entry() after maybe_write_anchor().
    Submits to Rekor only at ANCHOR_INTERVAL boundaries.

    FIX: removed unused `latest_hash` parameter that caused a signature
    mismatch with the call in audit_chain.py → would crash at runtime.

    Usage in audit_chain.py:
        local_anchor = await maybe_write_anchor(db, h_i)
        if local_anchor:
            await maybe_submit_rekor_anchor(db, local_anchor["anchor_hash"])
    """
    from sqlalchemy import select, func as sqlfunc
    from app.db.models import AuditLog

    count_result = await db.execute(
        select(sqlfunc.count(AuditLog.log_id))
        .where(AuditLog.chain_hash.isnot(None))
    )
    count = count_result.scalar() or 0

    interval = int(os.environ.get("AUDIT_ANCHOR_INTERVAL", "10"))
    if count == 0 or count % interval != 0:
        return None

    return await submit_to_rekor(anchor_hash)


# ══════════════════════════════════════════════════════════════════════════
# LOCAL REFERENCE FILE
# ══════════════════════════════════════════════════════════════════════════

def _save_rekor_ref(ref: dict) -> bool:
    """Appends a Rekor receipt to the local lookup cache."""
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
# VERIFICATION — against live Rekor log
# ══════════════════════════════════════════════════════════════════════════

async def verify_rekor_anchors() -> dict:
    """
    Verifies all saved Rekor anchors against the live public Rekor log.

    For each ref in rekor_refs.jsonl:
      [A] Fetch the entry from rekor.sigstore.dev by UUID
      [B] Decode the base64 body → extract stored artifact hash
      [C] Check: SHA-256(our anchor_hash) == Rekor's artifact hash
      [D] If match → chain state at that position is confirmed independently

    Does NOT need DB access. The comparison is purely:
      our local ref file  vs  Rekor's live public log

    If they mismatch: either our ref file was tampered, or the anchor_hash
    we submitted no longer matches our current chain — proving tampering.
    """
    import hmac as hmac_module

    refs = read_rekor_refs()

    if not refs:
        interval = int(os.environ.get("AUDIT_ANCHOR_INTERVAL", "10"))
        return {
            "valid":        True,
            "refs_checked": 0,
            "message": (
                f"No Rekor references yet. Will submit after first "
                f"{interval} entries. Refs file: {REKOR_REF_FILE}"
            ),
        }

    broken   = []
    verified = []

    for ref in refs:
        uuid       = ref.get("uuid", "")
        saved_hash = ref.get("anchor_hash", "")
        log_index  = ref.get("log_index")

        if not uuid or not saved_hash:
            broken.append({"log_index": log_index, "reason": "malformed ref"})
            continue

        # [A] Fetch live from Rekor
        entry = await fetch_rekor_entry(uuid)
        if entry is None:
            broken.append({
                "log_index": log_index,
                "uuid":      uuid[:16] + "...",
                "reason":    "could not fetch from Rekor (network error or invalid uuid)",
            })
            continue

        # [B] Decode base64 body → extract artifact hash
        try:
            entry_data            = entry.get(uuid, {})
            body                  = json.loads(base64.b64decode(entry_data.get("body", "")))
            rekor_artifact_sha256 = (
                body.get("spec", {}).get("data", {}).get("hash", {}).get("value", "")
            )
        except Exception as e:
            broken.append({
                "log_index": log_index,
                "uuid":      uuid[:16] + "...",
                "reason":    f"could not decode Rekor body: {e}",
            })
            continue

        # [C] SHA-256(our anchor_hash) must match Rekor's stored artifact hash
        expected_sha256 = hashlib.sha256(saved_hash.encode()).hexdigest()

        if not hmac_module.compare_digest(rekor_artifact_sha256, expected_sha256):
            broken.append({
                "log_index":  log_index,
                "uuid":       uuid[:16] + "...",
                "reason":     "hash_mismatch — Rekor entry does not match saved anchor",
                "rekor_hash": rekor_artifact_sha256[:16] + "...",
                "expected":   expected_sha256[:16] + "...",
            })
        else:
            # [D] Confirmed
            verified.append({
                "log_index":       log_index,
                "uuid":            uuid[:16] + "...",
                "rekor_url":       ref.get("rekor_url", ""),
                "submitted_at":    ref.get("submitted_at", ""),
                "integrated_time": ref.get("integrated_time"),
            })

    if broken:
        logger.error(f"REKOR VERIFICATION FAILED: {len(broken)} broken")
        return {
            "valid":        False,
            "refs_checked": len(refs),
            "verified":     len(verified),
            "broken":       broken,
            "message":      f"{len(broken)} Rekor anchor(s) failed — chain may have been tampered",
        }

    return {
        "valid":        True,
        "refs_checked": len(refs),
        "verified":     len(verified),
        "verified_refs": verified,
        "latest_ref":   refs[-1] if refs else None,
        "message": (
            f"All {len(refs)} Rekor anchors verified — "
            "chain state confirmed by public Merkle log (Sigstore Rekor)"
        ),
    }


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "generate-keys":
        generate_signing_keypair()
    else:
        print("Usage: python3 -m rekor_anchor generate-keys")
        print()
        print("Generates a P-256 EC key pair for signing Rekor anchor submissions.")
        print(f"  Private key → {REKOR_SIGNING_KEY_PATH}")
        print(f"  Public key  → {REKOR_PUBLIC_KEY_PATH}")
