#!/usr/bin/env python3
"""
HPC-ZT Security Layer Latency Benchmark — N=500 with confidence intervals.

Extends Test/benchmark_security.py with:
  - configurable N (default 500)
  - warmup phase
  - 95% CI on mean (normal approx)
  - 95% CI on median (bootstrap, 10k resamples)
  - IQR, P90, P95, P99
  - Markdown table for direct paste into the manuscript
  - CSV + JSON artifacts

Run:
  python3 Test/benchmark_security_n500.py --n 500
"""

import argparse
import ast
import csv
import json
import os
import random
import statistics
import time
import uuid
from datetime import datetime
from typing import Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Config (same as benchmark_security.py) ────────────────────────────────
KEYCLOAK_URL = "https://localhost:8443"
API_URL      = "https://localhost:8000"
REALM        = "HPC-Project"
CLIENT_ID    = "hpc-backend"
USERNAME     = "aichaguemir"
PASSWORD = os.environ.get("PORTAL_TEST_PASSWORD")
if not PASSWORD:
    raise RuntimeError(
        "PORTAL_TEST_PASSWORD not set. Export it, or add it to backend/.env -- "
        "this is the login password for the portal test account."
    )

ALLOWED_MODULES = {
    "numpy", "scipy", "pandas", "matplotlib", "sklearn", "tensorflow",
    "torch", "keras", "statsmodels", "sympy", "numba", "cupy", "seaborn",
    "plotly", "bokeh", "h5py", "netCDF4", "zarr", "xarray", "PIL", "cv2",
    "imageio", "tifffile", "math", "cmath", "decimal", "fractions",
    "random", "statistics", "itertools", "functools", "operator",
    "collections", "heapq", "bisect", "array", "string", "re", "json",
    "csv", "struct", "pathlib", "datetime", "time", "calendar", "typing",
    "dataclasses", "abc", "enum", "copy", "pprint", "reprlib", "warnings",
    "logging", "traceback", "argparse", "textwrap", "io", "contextlib",
    "multiprocessing", "concurrent", "threading", "mpi4py",
}

FORBIDDEN_FUNCTIONS = {
    "eval", "exec", "compile", "__import__", "vars", "dir",
    "globals", "locals", "getattr", "setattr", "delattr", "hasattr",
}
FORBIDDEN_ATTRIBUTES = {
    "__import__", "__builtins__", "__globals__", "__locals__", "__code__",
    "__closure__", "__bases__", "__subclasses__", "__mro__", "__loader__",
    "__spec__",
}

SCRIPTS = {
    "simple": "import math\nimport time\nresult = math.sqrt(42)\nprint(f'Result: {result}')\n",
    "complex": (
        "import numpy as np\nimport scipy\nimport pandas as pd\nimport math\n"
        "import time\nimport statistics\nimport itertools\nimport functools\n"
        "import collections\nimport re\nimport json\nimport csv\n"
        "data = np.random.rand(100, 100)\n"
        "result = np.linalg.norm(data)\n"
        "stats = {'mean': float(np.mean(data)), 'std': float(np.std(data)),"
        " 'max': float(np.max(data)), 'min': float(np.min(data))}\n"
        "print(json.dumps(stats, indent=2))\n"
        "for i in range(50):\n"
        "    chunk = data[i, :]\n"
        "    print(f'Row {i}: norm={np.linalg.norm(chunk):.4f}')\n"
    ),
    "malicious": (
        "import os\nimport subprocess\n"
        "eval(\"print('hacked')\")\n"
        "__import__('os').system('rm -rf /')\n"
    ),
}


# ── Security functions (same as benchmark_security.py) ────────────────────
def ast_security_scan(code: str):
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return True, f"SyntaxError: {e}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split('.')[0] not in ALLOWED_MODULES:
                    return True, f"Forbidden module: {alias.name}"
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split('.')[0] not in ALLOWED_MODULES:
                return True, f"Forbidden module: {node.module}"
        if isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRIBUTES or node.attr in FORBIDDEN_FUNCTIONS:
                return True, f"Forbidden attribute: {node.attr}"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_FUNCTIONS:
                return True, f"Forbidden function: {node.func.id}"
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for forbidden in FORBIDDEN_ATTRIBUTES:
                if forbidden in node.value:
                    return True, f"Forbidden string pattern: {forbidden}"
    return False, "clean"


def ast_scan_timed(code: str) -> float:
    t0 = time.perf_counter()
    ast_security_scan(code)
    t1 = time.perf_counter()
    return (t1 - t0) * 1000.0


def generate_sandbox_wrapper(unique_id: str) -> str:
    # Inline copy — replace with real import if you prefer
    return (
        "import builtins as _b\n"
        "import os as _os\n"
        "ALLOWED_MODULES = {'math','numpy','scipy','pandas','mpi4py'}\n"
        "def _safe_import(name, *args, **kwargs):\n"
        "    top = name.split('.')[0]\n"
        "    if top not in ALLOWED_MODULES:\n"
        "        raise ImportError(f\"Module '{top}' is not permitted\")\n"
        "    return _original_import(name, *args, **kwargs)\n"
        "_original_import = _b.__import__\n"
        f"_chunk_id = int(_os.environ.get('LSB_JOBINDEX', '1'))\n"
        f"_total_chunks = int(_os.environ.get('LSB_JOBINDEX_END', '1'))\n"
        f"with open('/home/gaichaa/jobs/script_{unique_id}.py', 'r') as _f:\n"
        "    _src = _f.read()\n"
        "_code = compile(_src, 'user_script', 'exec')\n"
        "exec(_code, {'__builtins__': {'__import__': _safe_import}})\n"
    )


def generate_sandbox_timed() -> float:
    t0 = time.perf_counter()
    generate_sandbox_wrapper(str(uuid.uuid4()))
    t1 = time.perf_counter()
    return (t1 - t0) * 1000.0


def generate_lsf(unique_id: str) -> str:
    return (
        "#!/bin/bash\n"
        f"#BSUB -J job_{unique_id}\n"
        "#BSUB -q low_priority\n#BSUB -n 2\n"
        "#BSUB -R 'rusage[mem=512] span[hosts=1]'\n"
        "#BSUB -M 512\n#BSUB -W 00:30\n"
        f"#BSUB -o /home/gaichaa/jobs/output_{unique_id}_%I.log\n"
        f"#BSUB -e /home/gaichaa/jobs/error_{unique_id}_%I.log\n"
        f"cd /home/gaichaa/jobs/job_{unique_id}\n"
        "ulimit -f 1048576\nulimit -t 3600\nulimit -u 64\nulimit -n 256\n"
        f"/home/mfahci/anaconda3/bin/python3 /home/gaichaa/jobs/sandbox_{unique_id}.py\n"
    )


def generate_lsf_timed() -> float:
    t0 = time.perf_counter()
    generate_lsf(str(uuid.uuid4()))
    t1 = time.perf_counter()
    return (t1 - t0) * 1000.0


def get_token() -> str:
    r = requests.post(
        f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": CLIENT_ID,
              "username": USERNAME, "password": PASSWORD},
        verify=False, timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def validate_jwt_timed(token: str) -> float:
    t0 = time.perf_counter()
    requests.get(
        f"{API_URL}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        verify=False, timeout=10,
    )
    t1 = time.perf_counter()
    return (t1 - t0) * 1000.0


# ── Statistics ────────────────────────────────────────────────────────────
def bootstrap_ci_median(values, n_boot=10000, alpha=0.05):
    """Return (lo, hi) 95% CI on the median via nonparametric bootstrap."""
    n = len(values)
    medians = []
    for _ in range(n_boot):
        sample = [values[random.randrange(n)] for _ in range(n)]
        medians.append(statistics.median(sample))
    medians.sort()
    lo = medians[int(alpha / 2 * n_boot)]
    hi = medians[int((1 - alpha / 2) * n_boot)]
    return lo, hi


def summarize(values):
    n = len(values)
    m = statistics.mean(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    ci_lo = m - 1.96 * sd / (n ** 0.5)
    ci_hi = m + 1.96 * sd / (n ** 0.5)
    med = statistics.median(values)
    med_ci_lo, med_ci_hi = bootstrap_ci_median(values)
    q1 = statistics.quantiles(values, n=4)[0] if n >= 4 else med
    q3 = statistics.quantiles(values, n=4)[2] if n >= 4 else med
    srt = sorted(values)
    def pct(p):
        idx = min(int(p * n), n - 1)
        return srt[idx]
    return {
        "n":          n,
        "mean":       round(m, 4),
        "mean_ci_lo": round(ci_lo, 4),
        "mean_ci_hi": round(ci_hi, 4),
        "median":     round(med, 4),
        "median_ci_lo": round(med_ci_lo, 4),
        "median_ci_hi": round(med_ci_hi, 4),
        "std":        round(sd, 4),
        "q1":         round(q1, 4),
        "q3":         round(q3, 4),
        "p90":        round(pct(0.90), 4),
        "p95":        round(pct(0.95), 4),
        "p99":        round(pct(0.99), 4),
        "min":        round(min(values), 4),
        "max":        round(max(values), 4),
    }


# ── Main ──────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500, help="iterations per phase")
    ap.add_argument("--warmup", type=int, default=20)
    args = ap.parse_args()

    N = args.n
    W = args.warmup
    print(f"HPC-ZT Security Benchmark — N={N}, warmup={W}")
    print(f"Started: {datetime.now().isoformat()}\n")

    all_raw = {}

    # Phase 1: JWT round-trip
    print(f"[1/4] JWT validation via /api/v1/auth/me  (warmup {W}, measure {N})")
    token = get_token()
    for i in range(W):
        validate_jwt_timed(token)
    jwt_times = []
    for i in range(N):
        if i % 100 == 0 and i > 0:
            token = get_token()
        jwt_times.append(validate_jwt_timed(token))
        if (i + 1) % 100 == 0:
            print(f"   {i+1}/{N}")
    all_raw["jwt_validation"] = jwt_times

    # Phase 2: AST scanner
    print(f"\n[2/4] AST scanner — complex and malicious  (N={N})")
    for label in ["complex", "malicious"]:
        for _ in range(W):
            ast_scan_timed(SCRIPTS[label])
        times = [ast_scan_timed(SCRIPTS[label]) for _ in range(N)]
        all_raw[f"ast_{label}"] = times
        print(f"   ast_{label}: mean={statistics.mean(times):.4f} ms")

    # Phase 3: sandbox generation
    print(f"\n[3/4] Sandbox wrapper generation  (N={N})")
    for _ in range(W):
        generate_sandbox_timed()
    sandbox_times = [generate_sandbox_timed() for _ in range(N)]
    all_raw["sandbox_gen"] = sandbox_times
    print(f"   sandbox_gen: mean={statistics.mean(sandbox_times):.4f} ms")

    # Phase 4: LSF generation
    print(f"\n[4/4] LSF script generation  (N={N})")
    for _ in range(W):
        generate_lsf_timed()
    lsf_times = [generate_lsf_timed() for _ in range(N)]
    all_raw["lsf_gen"] = lsf_times
    print(f"   lsf_gen: mean={statistics.mean(lsf_times):.4f} ms")

    # Summaries
    summary = {k: summarize(v) for k, v in all_raw.items()}

    # Total worst-case overhead (upper CI bound)
    total_mean = (summary["jwt_validation"]["mean"]
                  + summary["ast_complex"]["mean"]
                  + summary["sandbox_gen"]["mean"]
                  + summary["lsf_gen"]["mean"])
    total_ci_hi = (summary["jwt_validation"]["mean_ci_hi"]
                   + summary["ast_complex"]["mean_ci_hi"]
                   + summary["sandbox_gen"]["mean_ci_hi"]
                   + summary["lsf_gen"]["mean_ci_hi"])

    # Artifacts
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = f"benchmark_security_n{N}_{ts}.json"
    csv_path  = f"benchmark_security_n{N}_{ts}.csv"

    with open(json_path, "w") as f:
        json.dump({"n": N, "warmup": W, "summary": summary,
                   "total_mean_ms": round(total_mean, 4),
                   "total_ci_hi_ms": round(total_ci_hi, 4),
                   "raw": all_raw}, f, indent=2)

    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["component", "n", "mean", "mean_ci_lo", "mean_ci_hi",
                    "median", "median_ci_lo", "median_ci_hi",
                    "std", "q1", "q3", "p90", "p95", "p99", "min", "max"])
        for k, s in summary.items():
            w.writerow([k, s["n"], s["mean"], s["mean_ci_lo"], s["mean_ci_hi"],
                        s["median"], s["median_ci_lo"], s["median_ci_hi"],
                        s["std"], s["q1"], s["q3"], s["p90"], s["p95"],
                        s["p99"], s["min"], s["max"]])

    # Markdown table for the manuscript
    print("\n\n=== MARKDOWN TABLE FOR §9.2 ===\n")
    print("| Component | N | Mean | 95% CI (mean) | Median [IQR] | P95 | P99 |")
    print("|---|---|---|---|---|---|---|")
    def row(label, key):
        s = summary[key]
        return (f"| {label} | {s['n']} | {s['mean']:.2f} ms | "
                f"[{s['mean_ci_lo']:.2f}, {s['mean_ci_hi']:.2f}] | "
                f"{s['median']:.2f} [{s['q1']:.2f}, {s['q3']:.2f}] | "
                f"{s['p95']:.2f} | {s['p99']:.2f} |")
    print(row("JWT validation (HTTP+Keycloak)",  "jwt_validation"))
    print(row("AST scan — malicious (early exit)", "ast_malicious"))
    print(row("AST scan — complex (worst case)", "ast_complex"))
    print(row("Sandbox + LSF script gen",         "sandbox_gen"))
    print()
    print(f"Total worst-case security overhead: {total_mean:.2f} ms "
          f"(upper 95% bound {total_ci_hi:.2f} ms)")

    print(f"\nWrote {json_path}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
