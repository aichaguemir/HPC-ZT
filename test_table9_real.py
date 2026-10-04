#!/usr/bin/env python3
"""
Table 9 tests against YOUR REAL audit_chain.py (imported unmodified).
Put this file next to audit_chain.py and run:  python3 test_table9_real.py

Only the environment is faked:
  - app.db.models.AuditLog  -> SQLAlchemy model with the fields audit_chain.py uses (in-memory SQLite)
  - app.core.logging.logger -> std logging
  - Rekor HTTP             -> in-process mock (httpx.MockTransport); set REAL_REKOR=1 to use the real server
Every scenario gets a fresh DB, fresh anchor/ref files, fresh mock log.
Attacker actions are done directly on the DB / files, exactly like an attacker with that access would.
"""
import asyncio, base64, hashlib, json, os, sys, tempfile, types, uuid as uuidlib, logging
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
TMP = tempfile.mkdtemp(prefix="t9_")

# ── env must be set BEFORE import (module reads it at import time) ─────────
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
_k = ec.generate_private_key(ec.SECP256R1())
os.environ["AUDIT_CHAIN_SECRET"] = "ab" * 32
os.environ["REKOR_SIGNING_KEY_PEM"] = _k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
os.environ["REKOR_PUBLIC_KEY_PEM"] = _k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
os.environ["AUDIT_ANCHOR_INTERVAL"] = "10"

# ── stub the two app.* imports ─────────────────────────────────────────────
from sqlalchemy import Column, Integer, String, JSON, TypeDecorator, DateTime, select, update
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

class TZDateTime(TypeDecorator):
    """SQLite drops tzinfo; PostgreSQL timestamptz keeps it. Emulate PostgreSQL so hashes recompute identically."""
    impl = DateTime; cache_ok = True
    def process_bind_param(self, v, d): return v.astimezone(timezone.utc).replace(tzinfo=None) if v else v
    def process_result_value(self, v, d): return v.replace(tzinfo=timezone.utc) if v else v

Base = declarative_base()
class AuditLog(Base):
    __tablename__ = "audit_log"
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String); job_id = Column(String); action = Column(String)
    result = Column(String); ip_address = Column(String); detail = Column(JSON)
    chain_hash = Column(String); prev_hash = Column(String)
    timestamp = Column(TZDateTime)

for name in ("app", "app.db", "app.db.models", "app.core", "app.core.logging"):
    sys.modules[name] = types.ModuleType(name)
sys.modules["app.db.models"].AuditLog = AuditLog
sys.modules["app.core.logging"].logger = logging.getLogger("audit"); logging.getLogger("audit").setLevel(logging.CRITICAL)

import httpx
import audit_chain as ac                      # <-- YOUR FILE, unmodified

# ── Rekor mock (append-only; attacker cannot touch it) ─────────────────────
class MockRekor:
    def __init__(self): self.entries = {}; self.reachable = True; self.counter = 1472400000
    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.reachable: raise httpx.ConnectError("network unreachable")
        if request.method == "POST":
            payload = json.loads(request.content)
            u = uuidlib.uuid4().hex * 2; self.counter += 1
            self.entries[u] = {"body": base64.b64encode(json.dumps(payload).encode()).decode(),
                               "integratedTime": 1778238502, "logIndex": self.counter}
            return httpx.Response(201, json={u: self.entries[u]})
        u = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json={u: self.entries[u]}) if u in self.entries else httpx.Response(404)

REAL = os.environ.get("REAL_REKOR") == "1"
_RealClient = httpx.AsyncClient
rekor = None
def install_mock():
    global rekor; rekor = MockRekor()
    if not REAL:
        ac.httpx = types.SimpleNamespace(AsyncClient=lambda **kw: _RealClient(transport=httpx.MockTransport(rekor.handler), **kw),
                                         TimeoutException=httpx.TimeoutException)

# ── fresh world per scenario ───────────────────────────────────────────────
async def fresh_world(n_entries=280):
    d = tempfile.mkdtemp(dir=TMP)
    ac.ANCHOR_FILE = os.path.join(d, "audit_anchors.jsonl"); ac.REKOR_REF_FILE = os.path.join(d, "rekor_refs.jsonl")
    install_mock()
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as c: await c.run_sync(Base.metadata.create_all)
    S = async_sessionmaker(eng, expire_on_commit=False)
    async with S() as db:
        for i in range(n_entries):
            await ac.write_audit_entry(db, action=f"act{i}", user_id=f"u{i%7}", detail={"n": i}); await db.commit()
    return S

async def add_entries(S, n, start):
    async with S() as db:
        for i in range(start, start + n):
            await ac.write_audit_entry(db, action=f"post{i}", user_id="u", detail={"n": i}); await db.commit()

def classify(res):
    c, a, r = res["chain_check"], res["anchor_check"], res["rekor_check"]
    chain = "alarm" if not c["valid"] else ("pass (mixed)" if c.get("chain_mode") == "mixed" else "pass")
    anchors = "alarm" if not a["valid"] else "pass"
    db_chk = res.get("rekor_db_check")
    if r["valid"] and (db_chk is None or db_chk["valid"]): rek = "pass"
    elif r["valid"]: rek = "mismatch (vs DB)"
    else:
        reasons = " ".join(b["reason"] for b in r["broken"])
        rek = "fail (network error)" if "could not fetch" in reasons else "mismatch"
    return chain, anchors, rek

async def run_verify(S, stop_on_chain_alarm=False):
    async with S() as db:
        res = await ac.verify_full(db)
    out = list(classify(res))
    if stop_on_chain_alarm and out[0] == "alarm": out[1] = out[2] = "n/r"
    res["_overall"] = res["valid"]
    return out, res

# ── attacker primitives ────────────────────────────────────────────────────
async def rewrite_tail_with_K(S, n):
    async with S() as db:
        rows = (await db.execute(select(AuditLog).order_by(AuditLog.timestamp.asc()))).scalars().all()
        start = len(rows) - n; prev = rows[start - 1].chain_hash
        for r in rows[start:]:
            d = dict(r.detail or {}); d["forged"] = True
            h = ac.compute_hash(prev, r.timestamp, r.user_id, r.action, r.result, d)   # attacker holds K
            await db.execute(update(AuditLog).where(AuditLog.log_id == r.log_id).values(detail=d, prev_hash=prev, chain_hash=h))
            prev = h
        await db.commit()
    return start

async def rewrite_tail_legacy_no_K(S, from_pos, count=None):
    async with S() as db:
        rows = (await db.execute(select(AuditLog).order_by(AuditLog.timestamp.asc()))).scalars().all()
        prev = rows[from_pos - 1].chain_hash if from_pos else ac.get_genesis_hash_legacy()
        for r in rows[from_pos:(from_pos + count) if count else None]:
            d = dict(r.detail or {}); d["forged"] = True
            h = ac.compute_hash_legacy(prev, r.timestamp, r.user_id, r.action, r.result, d)   # NO K needed
            await db.execute(update(AuditLog).where(AuditLog.log_id == r.log_id).values(detail=d, prev_hash=prev, chain_hash=h))
            prev = h
        await db.commit()
    return from_pos

async def recompute_local_anchors_with_K(S, start_pos, rewrite_refs=False):
    async with S() as db:
        rows = (await db.execute(select(AuditLog).order_by(AuditLog.timestamp.asc()))).scalars().all()
    anchors = ac.read_anchors(); new_hash = {}
    for a in anchors:
        if a["entry_count"] > start_pos:
            a["latest_hash"] = rows[a["entry_count"] - 1].chain_hash
            content = {k: a[k] for k in ("entry_count", "latest_hash", "anchor_time", "system", "interval")}
            import hmac as _h
            old = a["anchor_hash"]
            a["anchor_hash"] = _h.new(ac._CHAIN_SECRET, json.dumps(content, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
            new_hash[old] = a["anchor_hash"]
    with open(ac.ANCHOR_FILE, "w") as f:
        for a in anchors: f.write(json.dumps(a) + "\n")
    if rewrite_refs:
        refs = ac.read_rekor_refs()
        for r in refs:
            if r["anchor_hash"] in new_hash:
                r["anchor_hash"] = new_hash[r["anchor_hash"]]; r["artifact_sha256"] = hashlib.sha256(r["anchor_hash"].encode()).hexdigest()
        with open(ac.REKOR_REF_FILE, "w") as f:
            for r in refs: f.write(json.dumps(r) + "\n")

# ── scenarios ──────────────────────────────────────────────────────────────
async def main():
    rows = []
    def rec(name, out, note=""): rows.append((name, *out, note))

    S = await fresh_world(); out, res = await run_verify(S)
    rec("Baseline (no attack)", out, f"overall valid={res['valid']}; {res['anchor_check']['anchors_checked']} anchors, {res['rekor_check']['refs_checked']} Rekor refs, {res['chain_check']['entries_checked']} entries")

    S = await fresh_world()
    async with S() as db:
        await db.execute(update(AuditLog).where(AuditLog.log_id == 138).values(detail={"n": 137, "tampered": True})); await db.commit()
    out, res = await run_verify(S, stop_on_chain_alarm=True)
    rec("SQL field modification", out, f"chain: {res['chain_check'].get('reason')} at log_id {res['chain_check'].get('broken_at')}")

    S = await fresh_world(); st = await rewrite_tail_with_K(S, 20); await recompute_local_anchors_with_K(S, st, rewrite_refs=False)
    out, res = await run_verify(S)
    rec("Key theft + rewrite 20 entries, refs file untouched", out, f"overall valid={res['valid']} | attacker rewrote DB chain + local anchors")

    S = await fresh_world(); st = await rewrite_tail_with_K(S, 20); await recompute_local_anchors_with_K(S, st, rewrite_refs=True)
    out, res = await run_verify(S)
    rec("Key theft + rewrite 20 entries, refs file ALSO rewritten", out, f"overall valid={res['valid']} | attacker also edited rekor_refs.jsonl")

    S = await fresh_world(); rekor.reachable = False
    out, res = await run_verify(S)
    rec("Rekor unreachable at verification", out, "")

    S = await fresh_world(); await add_entries(S, 5, 280); await rewrite_tail_legacy_no_K(S, 280, 5)
    out, res = await run_verify(S)
    rec("Legacy-mode rewrite AFTER last anchor, no K", out, f"overall valid={res['valid']} | chain_mode={res['chain_check'].get('chain_mode')}, tamper_resistant={res['chain_check'].get('tamper_resistant')}")

    S = await fresh_world(); await rewrite_tail_legacy_no_K(S, 260, 20)
    out, res = await run_verify(S)
    rec("[extra] Legacy-mode rewrite of entries 261-280 (inside anchored region), no K", out, "anchors:" + ("; ".join(b["reason"].split(" —")[0] for b in res["anchor_check"].get("broken_anchors", [])[:1]) or "-"))

    S = await fresh_world(); await rewrite_tail_legacy_no_K(S, 0, None)
    out, res = await run_verify(S)
    rec("[extra] Legacy-mode rewrite of WHOLE chain, no K", out, f"chain_mode={res['chain_check'].get('chain_mode')}")

    S = await fresh_world(); st = await rewrite_tail_with_K(S, 20)       # K thief rewrites DB but NOT anchors file
    out, res = await run_verify(S)
    rec("[extra] Key theft, DB rewritten but anchors file not touched", out, "")


    print("\nauditing module:", ac.__file__, "| has verify_rekor_vs_db:", hasattr(ac, "verify_rekor_vs_db"))
    print(f"\n{'Scenario':80s} {'Local chain':14s} {'Local anchors':14s} Rekor        notes")
    print("-" * 150)
    for n, c, a, r, note in rows: print(f"{n:80s} {c:14s} {a:14s} {r:12s} {note}")
    json.dump([dict(zip(("scenario", "local_chain", "local_anchors", "rekor", "note"), r)) for r in rows],
              open(os.path.join(HERE, "table9_real_results.json"), "w"), indent=2)

asyncio.run(main())
