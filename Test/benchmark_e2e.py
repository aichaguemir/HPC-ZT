import os
#!/usr/bin/env python3
"""
End-to-End Latency Benchmark — Secure HPC Job Portal
Measures: Auth → MFA → Job Submit → Job Complete (DONE/EXIT)
"""

import time
import json
import statistics
import requests
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Config ─────────────────────────────────────────────────────────────────
KEYCLOAK_URL   = "https://localhost:8443"
API_URL        = "https://localhost:8000"
REALM          = "HPC-Project"
CLIENT_ID      = "hpc-backend"
USERNAME       = "aichaguemir"
PASSWORD       = os.environ.get("PORTAL_TEST_PASSWORD")
if not PASSWORD:
    raise RuntimeError("PORTAL_TEST_PASSWORD env var not set (see backend/.env.example)")
ITERATIONS     = 50
JOB_POLL_INTERVAL = 2   # seconds between status checks
JOB_TIMEOUT       = 300 # max seconds to wait for job completion

# ── Test script ────────────────────────────────────────────────────────────
TEST_SCRIPT = b"""import math
import time
result = sum(math.sqrt(i) for i in range(1000))
print(f"Result: {result:.4f}")
print("Benchmark job complete.")
"""

# ── Helpers ────────────────────────────────────────────────────────────────

def get_token() -> tuple[str, float]:
    t0 = time.perf_counter()
    r = requests.post(
        f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
        data={
            "grant_type":    "password",
            "client_id":     CLIENT_ID,
            "username":      USERNAME,
            "password":      PASSWORD,
        },
        verify=False, timeout=10
    )
    t1 = time.perf_counter()
    r.raise_for_status()
    return r.json()["access_token"], round((t1 - t0) * 1000, 2)


def send_otp(token: str) -> float:
    t0 = time.perf_counter()
    r = requests.post(
        f"{API_URL}/api/v1/auth/mfa/send-code",
        headers={"Authorization": f"Bearer {token}"},
        verify=False, timeout=10
    )
    t1 = time.perf_counter()
    r.raise_for_status()
    return round((t1 - t0) * 1000, 2)


def get_otp_from_mailhog() -> str:
    """Fetch latest OTP code from Mailhog."""
    time.sleep(1)  # give mailhog a moment
    r = requests.get("http://localhost:8025/api/v2/messages", timeout=5)
    messages = r.json()["items"]
    if not messages:
        raise Exception("No email found in Mailhog!")
    # Latest message body
    body = messages[0]["Content"]["Body"]
    # Extract 6-digit code
    import re
    match = re.search(r'\b(\d{6})\b', body)
    if not match:
        raise Exception("Could not extract OTP from email body")
    return match.group(1)


def verify_otp(token: str, code: str) -> float:
    t0 = time.perf_counter()
    r = requests.post(
        f"{API_URL}/api/v1/auth/mfa/verify-code",
        headers={
            "Authorization":  f"Bearer {token}",
            "Content-Type":   "application/json",
        },
        json={"code": code},
        verify=False, timeout=10
    )
    t1 = time.perf_counter()
    r.raise_for_status()
    return round((t1 - t0) * 1000, 2)


def submit_job(token: str) -> tuple[str, float]:
    t0 = time.perf_counter()
    r = requests.post(
        f"{API_URL}/api/v1/jobs/submit",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("bench_job.py", TEST_SCRIPT, "text/plain")},
        data={
            "queue":            "low_priority",
            "cores":            "1",
            "memory":           "256",
            "wall_time_hours":  "0",
            "wall_time_minutes": "10",
        },
        verify=False, timeout=30
    )
    t1 = time.perf_counter()
    r.raise_for_status()
    job_id = r.json()["job_id"]
    return job_id, round((t1 - t0) * 1000, 2)


def wait_for_completion(token: str, job_id: str) -> tuple[str, float]:
    t0 = time.perf_counter()
    deadline = time.time() + JOB_TIMEOUT
    while time.time() < deadline:
        r = requests.get(
            f"{API_URL}/api/v1/jobs/{job_id}/status",
            headers={"Authorization": f"Bearer {token}"},
            verify=False, timeout=10
        )
        status = r.json().get("status", "UNKNOWN")
        if status in ("DONE", "EXIT"):
            t1 = time.perf_counter()
            return status, round((t1 - t0) * 1000, 2)
        time.sleep(JOB_POLL_INTERVAL)
    return "TIMEOUT", round((time.time() - t0) * 1000, 2)


def print_stats(label: str, values: list[float]):
    print(f"\n  {label}:")
    print(f"    Min:    {min(values):.1f} ms")
    print(f"    Max:    {max(values):.1f} ms")
    print(f"    Mean:   {statistics.mean(values):.1f} ms")
    print(f"    Median: {statistics.median(values):.1f} ms")
    print(f"    StdDev: {statistics.stdev(values):.1f} ms")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print(f"{'='*60}")
    print(f"  End-to-End Latency Benchmark")
    print(f"  Iterations : {ITERATIONS}")
    print(f"  Started    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    results = []

    for i in range(1, ITERATIONS + 1):
        print(f"[{i:02d}/{ITERATIONS}] Running...", end=" ", flush=True)
        row = {"iteration": i}

        try:
            # 1 — Auth
            token, t_auth = get_token()
            row["t_auth_ms"] = t_auth

            # 2 — Send OTP
            t_send = send_otp(token)
            row["t_mfa_send_ms"] = t_send

            # 3 — Get code from Mailhog
            code = get_otp_from_mailhog()

            # 4 — Verify OTP
            t_verify = verify_otp(token, code)
            row["t_mfa_verify_ms"] = t_verify

            # 5 — Submit job
            job_id, t_submit = submit_job(token)
            row["job_id"]       = job_id
            row["t_submit_ms"]  = t_submit

            # 6 — Wait for completion
            status, t_complete = wait_for_completion(token, job_id)
            row["status"]       = status
            row["t_complete_ms"] = t_complete

            # Total
            row["t_total_ms"] = round(
                t_auth + t_send + t_verify + t_submit + t_complete, 2
            )
            row["error"] = None

            print(f"job={job_id} status={status} "
                  f"total={row['t_total_ms']:.0f}ms ✓")

        except Exception as e:
            row["error"] = str(e)
            print(f"FAILED — {e}")

        results.append(row)
        if i < ITERATIONS:
            time.sleep(3)

    # ── Summary ───────────────────────────────────────────────────────────
    successful = [r for r in results if r["error"] is None]
    failed     = [r for r in results if r["error"] is not None]

    print(f"\n{'='*60}")
    print(f"  RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"  Successful : {len(successful)}/{ITERATIONS}")
    print(f"  Failed     : {len(failed)}/{ITERATIONS}")

    if successful:
        print_stats("Auth latency",       [r["t_auth_ms"]     for r in successful])
        print_stats("MFA send latency",   [r["t_mfa_send_ms"] for r in successful])
        print_stats("MFA verify latency", [r["t_mfa_verify_ms"] for r in successful])
        print_stats("Job submit latency", [r["t_submit_ms"]   for r in successful])
        print_stats("Job completion time",[r["t_complete_ms"] for r in successful])
        print_stats("TOTAL e2e latency",  [r["t_total_ms"]    for r in successful])

    # ── Save raw results ──────────────────────────────────────────────────
    output_file = f"benchmark_e2e_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Raw results saved to: {output_file}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
