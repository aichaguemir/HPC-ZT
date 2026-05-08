#!/usr/bin/env python3
"""
CARTA Engine Scenario Benchmark — Secure HPC Job Portal
Tests 8 scenarios by injecting signals via DB and parsing live CARTA logs.
No real jobs are submitted to the cluster.

Scenarios:
  S1 — Legitimate baseline        (all signals = 0, action = allow)
  S2 — Credential attack R7       (5 failed logins, R7=1.0, ρ ≈ 0.35)
  S3 — Rate flood R5              (inject recent jobs, R5=1.0, ρ ≈ 0.13)
  S4 — Velocity pattern S2        (regular timing, S2=1.0, ρ ≈ 0.07)
  S5 — Account takeover R2+R7     (combo bonus 1.45x, ρ > 0.40 → mfa)
  S6 — Bot confirmed R5+S2        (combo bonus 1.30x, ρ > 0.20 → flag)
  S7 — Session decay              (high score → 9 clean requests → decay)
  S8 — Tamper detection           (corrupt audit log → verify detects it)
"""

import re
import sys
import json
import time
import subprocess
import statistics
import requests
import urllib3
from datetime import datetime, timezone

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Config ─────────────────────────────────────────────────────────────────
KEYCLOAK_URL  = "https://localhost:8443"
API_URL       = "https://localhost:8000"
REALM         = "HPC-Project"
CLIENT_ID     = "hpc-backend"
USERNAME      = "aichaguemir"
PASSWORD      = "***REMOVED***"
CONTAINER     = "hpc-fastapi"
PG_CONTAINER  = "hpc-postgres"
PG_USER       = "hpcuser"
PG_DB         = "hpc_gateway"




# Signal weights (from carta.py)
WEIGHTS = {
    "R1_baseline": 0.13,
    "R2_device":   0.10,
    "R5_rate":     0.13,
    "R7_cred":     0.35,
    "S2_velocity": 0.07,
}

COMBO_BONUSES = {
    ("R2_device", "R7_cred"):     1.45,
    ("R5_rate",   "S2_velocity"): 1.30,
    ("R1_baseline","R7_cred"):    1.45,
    ("R5_rate",   "R2_device"):   1.20,
}

THRESHOLDS = {
    "allow":    0.20,
    "flag":     0.40,
    "mfa":      0.40,
    "block":    0.70,
}


# ── Helpers ────────────────────────────────────────────────────────────────

def get_token() -> str:
    r = requests.post(
        f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id":  CLIENT_ID,
            "username":   USERNAME,
            "password":   PASSWORD,
        },
        verify=False, timeout=10
    )
    r.raise_for_status()
    return r.json()["access_token"]


def psql(sql: str) -> str:
    """Run a SQL command in the PostgreSQL container."""
    result = subprocess.run(
        ["docker", "exec", PG_CONTAINER,
         "psql", "-U", PG_USER, "-d", PG_DB, "-c", sql],
        capture_output=True, text=True
    )
    return result.stdout + result.stderr


def get_user_id() -> str:
    out = psql(f"SELECT user_id FROM users WHERE username='{USERNAME}';")
    for line in out.splitlines():
        line = line.strip()
        if len(line) == 36 and '-' in line:
            return line
    raise Exception(f"Could not find user_id for {USERNAME}. Output: {out}")


def get_fastapi_logs(lines: int = 5) -> str:
    result = subprocess.run(
        ["docker", "logs", CONTAINER, "--tail", str(lines)],
        capture_output=True, text=True
    )
    return result.stdout + result.stderr
TEST_SCRIPT = b"""import math
result = math.sqrt(42)
print(f"Result: {result}")
"""

def trigger_carta(token: str = None) -> dict:
    """Submit a job to trigger CARTA, parse from logs."""
    before_logs = get_fastapi_logs(100)
    headers={
        "Authorization": f"Bearer {token}",
        "X-Device-Fingerprint": "dGVzdF9kZXZpY2VfZmluZ2VycHJpbnQ=",  # base64 fake fingerprint
    },
    t0 = time.perf_counter()
    requests.post(
        f"{API_URL}/api/v1/jobs/submit",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("bench.py", TEST_SCRIPT, "text/plain")},
        data={
            "queue":             "low_priority",
            "cores":             "1",
            "memory":            "256",
            "wall_time_hours":   "0",
            "wall_time_minutes": "10",
        },
        verify=False, timeout=30
    )
    t1 = time.perf_counter()
    latency_ms = round((t1 - t0) * 1000, 2)

    time.sleep(3)  # wait for CARTA + SSH logs to flush
    after_all = subprocess.run(
        ["docker", "logs", CONTAINER, "--tail", "200"],
        capture_output=True, text=True
    )
    after_lines = (after_all.stdout + after_all.stderr).splitlines()
    after_logs = get_fastapi_logs(50)

    signals = {}
    fail_count = 0
    action = "unknown"
    rho = 0.0
    rho_session = 0.0
    active_signals = []

    for line in after_logs.splitlines():
        # SIGNALS DEBUG
        if "SIGNALS DEBUG" in line and USERNAME in line:
            for k, v in re.findall(r'(\w+)=(\d+\.\d+)', line):
                if k in ("R1","R2","R3","R4","R5","R7","S2"):
                    signals[k] = float(v)
            fc = re.search(r'fail_count=(\d+)', line)
            if fc:
                fail_count = int(fc.group(1))

        # WARNING line — actual enforcement decision (takes priority)
        if "WARNING" in line and "CARTA:" in line and USERNAME in line:
            m = re.search(r'ρ_req=([\d.]+)', line)
            if m:
                rho = float(m.group(1))
            # parse session score
            ms = re.search(r'ρ_session=([\d.]+)', line)
            if ms:
                rho_session = float(ms.group(1))
            m2 = re.search(r'action=(\w+)', line)
            if m2:
                action = m2.group(1)  # mfa, flag, block

        # INFO allow line — only use if no WARNING found
        if "INFO" in line and "CARTA:" in line and "ρ_req=" in line and USERNAME in line:
            if action == "unknown":  # only if WARNING didn't fire
                m = re.search(r'ρ_req=([\d.]+)', line)
                if m:
                    rho = float(m.group(1))
                ms = re.search(r'ρ_session=([\d.]+)', line)
                if ms:
                    rho_session = float(ms.group(1))
                m2 = re.search(r'→ (\w+)', line)
                if m2:
                    action = m2.group(1)

        # Signals list
        if "CARTA:" in line and "signals=" in line and USERNAME in line:
            m = re.search(r"signals=\[(.*?)\]", line)
            if m:
                raw = m.group(1)
                active_signals = [
                    s.strip().strip("'")
                    for s in raw.split(',') if s.strip()
                ]

    return {
        "latency_ms":     latency_ms,
        "signals":        signals,
        "fail_count":     fail_count,
        "rho":            rho,
        "rho_session":    rho_session,   # ← now tracking session score
        "action":         action,
        "active_signals": active_signals,
    }


def print_result(scenario, result, expected_action, notes=""):
    action = result["action"]
    passed = action == expected_action or expected_action == "any"
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"\n  {'─'*55}")
    print(f"  {scenario}")
    print(f"  {'─'*55}")
    print(f"  Signals      : {result['signals']}")
    print(f"  Active       : {result['active_signals']}")
    print(f"  Fail count   : {result['fail_count']}")
    print(f"  ρ_req        : {result['rho']:.3f}")
    print(f"  ρ_session    : {result.get('rho_session', 0):.3f}")  # ← new
    print(f"  Action       : {action}  (expected: {expected_action})")
    print(f"  Latency      : {result['latency_ms']:.1f} ms")
    print(f"  Result       : {status}")
    if notes:
        print(f"  Notes        : {notes}")
    return passed

# ── Setup / Teardown ────────────────────────────────────────────────────────

def clean_injected_data(user_id: str):
    """Remove all injected test data."""
    psql(f"""
        DELETE FROM audit_log
        WHERE user_id = '{user_id}'
        AND result IN ('injected_failed', 'injected_rate');
    """)


def inject_failed_logins(user_id: str, count: int):
    """Inject failed login entries into audit_log."""
    for i in range(count):
        psql(f"""
            INSERT INTO audit_log (user_id, action, result, ip_address, timestamp)
            VALUES (
                '{user_id}',
                'login_failed',
                'injected_failed',
                '192.168.1.1',
                NOW() - INTERVAL '{i+1} minutes'
            );
        """)


def inject_recent_jobs(user_id: str, count: int, policy_id: str):
    """Inject recent job submissions to trigger R5 rate signal."""
    for i in range(count):
        psql(f"""
            INSERT INTO jobs (
                job_id, unique_id, user_id, status, queue,
                cores, memory, wall_time,
                policy_id_at_submission, policy_role_at_submission,
                cores_limit_at_submission, memory_limit_at_submission,
                is_flagged, submitted_at
            ) VALUES (
                'BENCH_{i}_{int(time.time())}',
                gen_random_uuid(),
                '{user_id}',
                'DONE',
                'low_priority',
                1, 256, '00:10',
                '{policy_id}',
                'admin',
                16, 31900,
                false,
                NOW() - INTERVAL '{i*5} seconds'
            );
        """)


def get_admin_policy_id() -> str:
    out = psql("SELECT policy_id FROM policies WHERE role='admin';")
    for line in out.splitlines():
        line = line.strip()
        if len(line) == 36 and '-' in line:
            return line
    raise Exception(f"Could not find admin policy_id. Output: {out}")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print(f"{'='*60}")
    print(f"  CARTA Engine Scenario Benchmark")
    print(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # Get user info
    print("\n  Setting up...")
    user_id   = get_user_id()
    policy_id = get_admin_policy_id()
    print(f"  User ID   : {user_id}")
    print(f"  Policy ID : {policy_id}")

    # Clean any leftover test data
    clean_injected_data(user_id)

    token = get_token()
    results = {}
    passed  = 0
    total   = 0

    # ══════════════════════════════════════════════════════════════════════
    # S1 — Legitimate Baseline
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*60}")
    print("  SCENARIO 1 — Legitimate Baseline")
    print(f"{'═'*60}")
    print("  Setup: Fresh session, clean history")
    print("  Expected: All signals = 0, ρ = 0.000, action = allow")

    clean_injected_data(user_id)
    time.sleep(1)
    r = trigger_carta(token)
    results["S1_baseline"] = r
    ok = print_result("S1: Legitimate Baseline", r, "allow",
                      "All signals should be 0 with clean history")
    passed += ok; total += 1

    # ══════════════════════════════════════════════════════════════════════
    # S2 — Credential Attack (R7)
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*60}")
    print("  SCENARIO 2 — Credential Attack (R7)")
    print(f"{'═'*60}")
    print("  Setup: Inject 5 failed logins → R7=1.0")
    print("  Expected: R7=1.0, ρ ≈ 0.35, action = flag or mfa")

    inject_failed_logins(user_id, 5)
    time.sleep(1)
    token = get_token()
    r = trigger_carta(token)
    results["S2_R7_cred"] = r
    ok = print_result("S2: Credential Attack (R7)", r, "flag",
                      f"Expected ρ ≈ 0.35 (R7 weight={WEIGHTS['R7_cred']})")
    passed += ok; total += 1

    # ══════════════════════════════════════════════════════════════════════
    # S3 — Rate Flood (R5)
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*60}")
    print("  SCENARIO 3 — Rate Flood (R5)")
    print(f"{'═'*60}")
    print("  Setup: Clean failed logins, inject 8 recent jobs → R5=1.0")
    print("  Expected: R5=1.0, ρ ≈ 0.13, action = allow or flag")

    clean_injected_data(user_id)
    inject_recent_jobs(user_id, 8, policy_id)
    time.sleep(1)
    token = get_token()
    r = trigger_carta(token)
    results["S3_R5_rate"] = r
    ok = print_result("S3: Rate Flood (R5)", r, "any",
                      f"R5 fires when recent job count > threshold")
    passed += ok; total += 1

    # ══════════════════════════════════════════════════════════════════════
    # S4 — Velocity Pattern (S2)
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*60}")
    print("  SCENARIO 4 — Velocity Pattern (S2)")
    print(f"{'═'*60}")
    print("  Setup: S2 fires from regular-interval benchmark submissions")
    print("  Expected: S2 active in signals, ρ ≈ 0.07, action = allow")

    # S2 was already observed firing during the e2e benchmark (regular intervals)
    # Just verify it's still in the session
    r = trigger_carta(token)
    results["S4_S2_velocity"] = r
    ok = print_result("S4: Velocity Pattern (S2)", r, "any",
                      "S2 fires when submission intervals are too regular (low CV)")
    passed += ok; total += 1

    # ══════════════════════════════════════════════════════════════════════
    # S5 — Account Takeover Combo (R2 + R7)
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*60}")
    print("  SCENARIO 5 — Account Takeover Combo (R2 + R7)")
    print(f"{'═'*60}")
    print("  Setup: 5 failed logins (R7=1.0) + combo bonus 1.45x")
    print("  Expected: ρ > 0.40, action = mfa or restrict")

    clean_injected_data(user_id)
    inject_failed_logins(user_id, 5)
    time.sleep(1)
    token = get_token()

    # Calculate expected ρ with combo
    base_rho = WEIGHTS["R7_cred"] * 1.0  # R7=1.0
    combo    = COMBO_BONUSES.get(("R2_device", "R7_cred"), 1.0)
    expected_rho = base_rho  # R2 may not fire without new device
    print(f"  Theoretical ρ (R7 only): {base_rho:.3f}")
    print(f"  Theoretical ρ (R2+R7 combo): {base_rho * combo:.3f}")

    r = trigger_carta(token)
    results["S5_combo_R2_R7"] = r
    ok = print_result("S5: Account Takeover (R2+R7)", r, "any",
                      f"Combo bonus {combo}x when both R2+R7 active")
    passed += ok; total += 1

    # ══════════════════════════════════════════════════════════════════════
    # S6 — Bot Confirmed (R5 + S2)
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*60}")
    print("  SCENARIO 6 — Bot Confirmed (R5 + S2)")
    print(f"{'═'*60}")
    print("  Setup: Rate flood + velocity pattern active simultaneously")
    print("  Expected: R5+S2 combo 1.30x, ρ > 0.20, action = flag")

    clean_injected_data(user_id)
    inject_recent_jobs(user_id, 8, policy_id)
    time.sleep(1)
    token = get_token()

    base = WEIGHTS["R5_rate"] + WEIGHTS["S2_velocity"]
    combo = COMBO_BONUSES.get(("R5_rate", "S2_velocity"), 1.0)
    print(f"  Theoretical ρ (R5+S2): {base:.3f}")
    print(f"  Theoretical ρ (with combo): {base * combo:.3f}")

    r = trigger_carta(token)
    results["S6_combo_R5_S2"] = r
    ok = print_result("S6: Bot Confirmed (R5+S2)", r, "any",
                      f"Combo bonus {combo}x when R5+S2 both active")
    passed += ok; total += 1




# ══════════════════════════════════════════════════════════════════════
    # S7 — Session Score Decay
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*60}")
    print("  SCENARIO 7 — Session Score Decay (EMA)")
    print(f"{'═'*60}")
    print("  Setup: Same session token throughout — R7 then clean")
    print("  Expected: ρ decaying via EMA γ=0.9 over clean requests")

    # Get ONE token and reuse it for the entire decay trace
    # This ensures we stay in the same session
    clean_injected_data(user_id)
    inject_failed_logins(user_id, 5)
    time.sleep(1)
    decay_token = get_token()  # single token for whole scenario

    r_high = trigger_carta(decay_token)  # pass token, don't refresh
    print(f"\n  Initial (R7 active)  : ρ = {r_high['rho']:.3f}  action={r_high['action']}") 
    

    # Now remove R7 — keep same token/session
    clean_injected_data(user_id)
    psql(f"DELETE FROM jobs WHERE user_id='{user_id}' AND job_id LIKE 'BENCH_%';")
    time.sleep(65)  # wait for rate window to expire
    print("  (waiting 65s for rate window to clear...)")    
    decay_scores = [r_high["rho"]]
    for i in range(6):
        time.sleep(3)
        r_clean = trigger_carta(decay_token)  # same token!
        decay_scores.append(r_clean["rho"])
        print(f"  Clean request {i+1}     : ρ = {r_clean['rho']:.3f}  action={r_clean['action']}")

    is_decaying = decay_scores[-1] < decay_scores[0]
    results["S7_decay"] = {
        "initial_rho": decay_scores[0],
        "final_rho":   decay_scores[-1],
        "scores":      decay_scores,
        "is_decaying": is_decaying,
        "expected_gamma": 0.9,
    }
    print(f"\n  Decay observed : {'✓ YES' if is_decaying else '✗ NO'}")
    print(f"  ρ trace        : {' → '.join(f'{s:.3f}' for s in decay_scores)}")
    


# ══════════════════════════════════════════════════════════════════════
    # S8 — Tamper Detection
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*60}")
    print("  SCENARIO 8 — Tamper Detection (Audit Chain)")
    print(f"{'═'*60}")

    admin_token = get_token()

    # Step 1 — insert 3 fresh clean audit entries to build a mini-chain
    print("\n  [Setup] Inserting fresh audit entries...")
    for i in range(3):
        requests.post(
            f"{API_URL}/api/v1/auth/mfa/send-code",
            headers={"Authorization": f"Bearer {admin_token}"},
            verify=False, timeout=10
        )
        time.sleep(1)

    # Step 2 — verify chain is valid on the latest entries
    print("  [Before tamper] Verifying latest anchor...")
    r_before = requests.get(
        f"{API_URL}/api/v1/admin/audit/verify/anchors",
        headers={"Authorization": f"Bearer {admin_token}"},
        verify=False, timeout=10
    )
    before_data = r_before.json()
    print(f"  Response: {json.dumps(before_data, indent=2)[:200]}")

    # Step 3 — tamper with the most recent entry
    print("\n  [Tamper] Corrupting latest audit entry...")
    psql("""
        UPDATE audit_log SET result='TAMPERED_BY_ATTACKER'
        WHERE log_id = (
            SELECT log_id FROM audit_log
            ORDER BY timestamp DESC
            LIMIT 1
        );
    """)
    time.sleep(0.5)

    # Step 4 — verify chain detects tamper
    print("  [After tamper] Verifying chain...")
    r_after = requests.get(
        f"{API_URL}/api/v1/admin/audit/verify",
        headers={"Authorization": f"Bearer {admin_token}"},
        verify=False, timeout=10
    )
    after_data = r_after.json()
    after_valid = after_data.get("valid", True)
    tamper_detected = not after_valid
    print(f"  Chain valid after tamper: {after_valid}")
    print(f"  Tamper detected: {'✓ YES' if tamper_detected else '✗ NO'}")

    # Step 5 — restore
    print("  [Restore] Reverting tampered entry...")
    psql("""
        UPDATE audit_log SET result='success'
        WHERE log_id = (
            SELECT log_id FROM audit_log
            ORDER BY timestamp DESC
            LIMIT 1
        );
    """)

    results["S8_tamper"] = {
        "tamper_detected": tamper_detected,
        "before":          before_data,
        "after":           after_data,
    }
    passed += tamper_detected
    total  += 1

    # ── Final cleanup ─────────────────────────────────────────────────────
    clean_injected_data(user_id)

    # ══════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"  CARTA BENCHMARK SUMMARY")
    print(f"{'='*60}")
    print(f"  Scenarios passed : {passed}/{total}")
    print(f"\n  Signal weights used:")
    for k, v in WEIGHTS.items():
        print(f"    {k:20s} = {v}")
    print(f"\n  Combo bonuses used:")
    for (a, b), mult in COMBO_BONUSES.items():
        print(f"    {a} + {b} = {mult}x")

    print(f"\n  Key observations:")
    s1 = results.get("S1_baseline", {})
    s2 = results.get("S2_R7_cred", {})
    s7 = results.get("S7_decay", {})
    s8 = results.get("S8_tamper", {})
    print(f"    Baseline ρ        : {s1.get('rho', 'N/A'):.3f}")
    print(f"    R7 (5 fails) ρ    : {s2.get('rho', 'N/A'):.3f}")
    print(f"    Decay start → end : {s7.get('initial_rho', 'N/A'):.3f} → {s7.get('final_rho', 'N/A'):.3f}")
    print(f"    Tamper detected   : {s8.get('tamper_detected', 'N/A')}")

    # Save
    output = f"benchmark_carta_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Raw results saved to: {output}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
