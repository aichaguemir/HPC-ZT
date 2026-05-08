#!/usr/bin/env python3
"""
Security Layer Latency Benchmark — Secure HPC Job Portal
Measures: JWT Validation, AST Scanning, Sandbox Generation, LSF Generation
All functions are self-contained — no app imports needed.
"""

import time
import ast
import json
import uuid
import statistics
import requests
import urllib3
from datetime import datetime
from typing import Optional

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Config ─────────────────────────────────────────────────────────────────
KEYCLOAK_URL = "https://localhost:8443"
API_URL      = "https://localhost:8000"
REALM        = "HPC-Project"
CLIENT_ID    = "hpc-backend"
USERNAME     = "aichaguemir"
PASSWORD     = "***REMOVED***"
ITERATIONS   = 100

# ── Security config (copied from config.py) ────────────────────────────────
ALLOWED_MODULES = {
    "numpy", "scipy", "pandas", "matplotlib",
    "sklearn", "tensorflow", "torch", "keras",
    "statsmodels", "sympy", "numba", "cupy",
    "seaborn", "plotly", "bokeh",
    "h5py", "netCDF4", "zarr", "xarray",
    "PIL", "cv2", "imageio", "tifffile",
    "math", "cmath", "decimal", "fractions",
    "random", "statistics",
    "itertools", "functools", "operator",
    "collections", "heapq", "bisect", "array",
    "string", "re", "json", "csv", "struct",
    "pathlib", "datetime", "time", "calendar",
    "typing", "dataclasses", "abc",
    "enum", "copy", "pprint", "reprlib",
    "warnings", "logging", "traceback",
    "argparse", "textwrap",
    "io", "contextlib",
    "multiprocessing", "concurrent", "threading",
    "mpi4py",
}

FORBIDDEN_FUNCTIONS = {
    "eval", "exec", "compile",
    "__import__", "vars", "dir",
    "globals", "locals", "getattr", "setattr",
    "delattr", "hasattr",
}

FORBIDDEN_ATTRIBUTES = {
    "__import__", "__builtins__", "__globals__",
    "__locals__", "__code__", "__closure__",
    "__bases__", "__subclasses__", "__mro__",
    "__loader__", "__spec__",
}

MAX_FILE_SIZE    = 10 * 1024 * 1024
REMOTE_JOB_DIR   = "/home/gaichaa/jobs"
PYTHON_BIN       = "/home/mfahci/anaconda3/bin/python3"

# ── Test scripts ───────────────────────────────────────────────────────────
SCRIPTS = {
    "simple": """import math
import time
result = math.sqrt(42)
print(f"Result: {result}")
""",
    "medium": """import numpy as np
import math
import time
import statistics

data = [math.sqrt(i) for i in range(100)]
mean = statistics.mean(data)
arr  = np.array(data)
std  = np.std(arr)
print(f"Mean: {mean:.4f}, Std: {std:.4f}")
for i in range(10):
    time.sleep(0.001)
    print(f"Step {i}: {arr[i]:.4f}")
""",
    "complex": """import numpy as np
import scipy
import pandas as pd
import math
import time
import statistics
import itertools
import functools
import collections
import re
import json
import csv

data = np.random.rand(100, 100)
result = np.linalg.norm(data)
stats = {
    'mean': float(np.mean(data)),
    'std':  float(np.std(data)),
    'max':  float(np.max(data)),
    'min':  float(np.min(data)),
}
print(json.dumps(stats, indent=2))
for i in range(50):
    chunk = data[i, :]
    print(f"Row {i}: norm={np.linalg.norm(chunk):.4f}")
""",
    "malicious": """import os
import subprocess
eval("print('hacked')")
__import__('os').system('rm -rf /')
""",
}


# ── AST Scanner (copied from validators/script.py) ─────────────────────────

def ast_security_scan(code: str) -> tuple[bool, str]:
    """Returns (blocked, reason)"""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return True, f"SyntaxError: {e}"

    for node in ast.walk(tree):
        # ① Import allowlist
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level = alias.name.split('.')[0]
                if top_level not in ALLOWED_MODULES:
                    return True, f"Forbidden module: {alias.name}"

        # ② From-import allowlist
        if isinstance(node, ast.ImportFrom):
            if node.module:
                top_level = node.module.split('.')[0]
                if top_level not in ALLOWED_MODULES:
                    return True, f"Forbidden module: {node.module}"

        # ③ Forbidden attributes
        if isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRIBUTES or node.attr in FORBIDDEN_FUNCTIONS:
                return True, f"Forbidden attribute: {node.attr}"

        # ④ Forbidden function calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_FUNCTIONS:
                    return True, f"Forbidden function: {node.func.id}"

        # ⑤ Forbidden string patterns
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                for forbidden in FORBIDDEN_ATTRIBUTES:
                    if forbidden in node.value:
                        return True, f"Forbidden string pattern: {forbidden}"

    return False, "clean"


def ast_scan_timed(code: str) -> tuple[bool, str, float]:
    t0 = time.perf_counter()
    blocked, reason = ast_security_scan(code)
    t1 = time.perf_counter()
    return blocked, reason, round((t1 - t0) * 1000, 4)


# ── Sandbox Generator (copied from services/lsf.py) ────────────────────────

def generate_sandbox_wrapper(unique_id: str) -> str:
    return f"""import builtins as _b
import os as _os
ALLOWED_MODULES = {{
    'math', 'cmath', 'decimal', 'fractions', 'random', 'statistics',
    'itertools', 'functools', 'operator', 'collections', 'heapq',
    'bisect', 'array', 'string', 're', 'json', 'csv', 'struct',
    'pathlib', 'datetime', 'time', 'calendar', 'typing', 'dataclasses',
    'abc', 'enum', 'copy', 'pprint', 'reprlib', 'warnings', 'logging',
    'traceback', 'argparse', 'textwrap', 'io', 'contextlib',
    'numpy', 'scipy', 'pandas', 'matplotlib', 'sklearn', 'tensorflow',
    'torch', 'keras', 'statsmodels', 'sympy', 'numba', 'seaborn',
    'plotly', 'bokeh', 'h5py', 'zarr', 'xarray', 'PIL', 'cv2',
    'imageio', 'tifffile', 'multiprocessing', 'concurrent', 'threading',
    'mpi4py',
}}
def _safe_import(name, *args, **kwargs):
    top = name.split('.')[0]
    if top not in ALLOWED_MODULES:
        raise ImportError(f"Module '{{top}}' is not permitted")
    return _original_import(name, *args, **kwargs)
_original_import = _b.__import__
_chunk_id     = int(_os.environ.get('LSB_JOBINDEX', '1'))
_total_chunks = int(_os.environ.get('LSB_JOBINDEX_END', '1'))
with open('{REMOTE_JOB_DIR}/script_{unique_id}.py', 'r') as _f:
    _src = _f.read()
_src = _src.replace('__CHUNK_ID__',     str(_chunk_id))
_src = _src.replace('__TOTAL_CHUNKS__', str(_total_chunks))
_code = compile(_src, 'user_script', 'exec')
exec(_code, {{'__builtins__': {{'__import__': _safe_import}}}})
"""


def generate_sandbox_timed(unique_id: str) -> float:
    t0 = time.perf_counter()
    _ = generate_sandbox_wrapper(unique_id)
    t1 = time.perf_counter()
    return round((t1 - t0) * 1000, 4)


# ── LSF Generator (copied from services/lsf.py) ────────────────────────────

def generate_lsf(
    unique_id:         str,
    username:          str,
    cores:             int,
    memory:            int,
    queue:             str,
    wall_time_hours:   int,
    wall_time_minutes: int,
    job_type:          str           = "serial",
    chunks:            Optional[int] = None,
    cores_per_chunk:   Optional[int] = None,
    target_node:       Optional[str] = None,
) -> str:
    queue      = queue.strip().lower()
    wall_time  = f"{wall_time_hours:02d}:{wall_time_minutes:02d}"
    total_secs = (wall_time_hours * 3600) + (wall_time_minutes * 60) + 60
    user_dir   = f"{REMOTE_JOB_DIR}/{username}"
    job_workdir= f"{user_dir}/job_{unique_id}"
    node_flag  = f'#BSUB -m "{target_node}"' if target_node else ""

    if job_type == "parallel" and chunks and chunks > 1:
        bsub_n       = chunks * cores_per_chunk
        resource_req = f'rusage[mem={memory}] span[ptile={cores_per_chunk}]'
        job_name     = f'job_{unique_id}[1-{chunks}]'
        extra_env    = f"export LSB_JOBINDEX_END={chunks}"
    else:
        bsub_n       = cores
        resource_req = f'rusage[mem={memory}] span[hosts=1]'
        job_name     = f'job_{unique_id}'
        extra_env    = ""

    return f"""#!/bin/bash
#BSUB -J {job_name}
#BSUB -q {queue}
#BSUB -n {bsub_n}
#BSUB -R "{resource_req}"
#BSUB -M {memory}
#BSUB -W {wall_time}
#BSUB -o {job_workdir}/output_{unique_id}_%I.log
#BSUB -e {job_workdir}/error_{unique_id}_%I.log
{node_flag}
cd {job_workdir}
ulimit -f 1048576
ulimit -t {total_secs}
ulimit -u 64
ulimit -n 256
{extra_env}
{PYTHON_BIN} {REMOTE_JOB_DIR}/sandbox_{unique_id}.py
rm -f {REMOTE_JOB_DIR}/sandbox_{unique_id}.py
rm -f {REMOTE_JOB_DIR}/script_{unique_id}.py
"""


def generate_lsf_timed(unique_id: str) -> float:
    t0 = time.perf_counter()
    _ = generate_lsf(
        unique_id=unique_id, username="bench_user",
        cores=2, memory=512, queue="low_priority",
        wall_time_hours=0, wall_time_minutes=30,
    )
    t1 = time.perf_counter()
    return round((t1 - t0) * 1000, 4)


# ── JWT Validation ─────────────────────────────────────────────────────────

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


def validate_jwt_timed(token: str) -> float:
    t0 = time.perf_counter()
    r = requests.get(
        f"{API_URL}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        verify=False, timeout=10
    )
    t1 = time.perf_counter()
    return round((t1 - t0) * 1000, 2)


# ── Stats printer ──────────────────────────────────────────────────────────

def print_stats(label: str, values: list[float], unit: str = "ms"):
    print(f"\n  {label}:")
    print(f"    Min    : {min(values):.4f} {unit}")
    print(f"    Max    : {max(values):.4f} {unit}")
    print(f"    Mean   : {statistics.mean(values):.4f} {unit}")
    print(f"    Median : {statistics.median(values):.4f} {unit}")
    print(f"    StdDev : {statistics.stdev(values):.4f} {unit}")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print(f"{'='*60}")
    print(f"  Security Layer Latency Benchmark")
    print(f"  Iterations : {ITERATIONS}")
    print(f"  Started    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    results = {}

    # ── Phase 1: JWT Validation ───────────────────────────────────────────
    print("[ Phase 1 ] JWT Validation...")
    token = get_token()
    jwt_times = []
    for i in range(ITERATIONS):
        if i % 20 == 0 and i > 0:
            token = get_token()
        t = validate_jwt_timed(token)
        jwt_times.append(t)
        print(f"  [{i+1:03d}/{ITERATIONS}] {t:.1f}ms", end="\r")
    results["jwt_validation"] = jwt_times
    print(f"  Done — mean={statistics.mean(jwt_times):.1f}ms" + " "*20)

    # ── Phase 2: AST Scanner ──────────────────────────────────────────────
    print("\n[ Phase 2 ] AST Security Scanner...")
    for script_type, code in SCRIPTS.items():
        times = []
        print(f"  Scanning '{script_type}' ({ITERATIONS}x)...", end=" ")
        for _ in range(ITERATIONS):
            blocked, reason, t = ast_scan_timed(code)
            times.append(t)
        results[f"ast_{script_type}"] = times
        expected = (script_type == "malicious")
        print(f"mean={statistics.mean(times):.4f}ms  "
              f"blocked={blocked} {'✓' if blocked == expected else '✗'}")

    # ── Phase 3: Sandbox Generation ───────────────────────────────────────
    print("\n[ Phase 3 ] Sandbox Wrapper Generation...")
    sandbox_times = []
    for i in range(ITERATIONS):
        t = generate_sandbox_timed(str(uuid.uuid4()))
        sandbox_times.append(t)
        print(f"  [{i+1:03d}/{ITERATIONS}] {t:.4f}ms", end="\r")
    results["sandbox_gen"] = sandbox_times
    print(f"  Done — mean={statistics.mean(sandbox_times):.4f}ms" + " "*20)

    # ── Phase 4: LSF Script Generation ───────────────────────────────────
    print("\n[ Phase 4 ] LSF Script Generation...")
    lsf_times = []
    for i in range(ITERATIONS):
        t = generate_lsf_timed(str(uuid.uuid4()))
        lsf_times.append(t)
        print(f"  [{i+1:03d}/{ITERATIONS}] {t:.4f}ms", end="\r")
    results["lsf_gen"] = lsf_times
    print(f"  Done — mean={statistics.mean(lsf_times):.4f}ms" + " "*20)

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  RESULTS SUMMARY")
    print(f"{'='*60}")

    print("\n── Phase 1: JWT Validation ─────────────────────────────")
    print_stats("JWT validation (network round-trip)", results["jwt_validation"])

    print("\n── Phase 2: AST Security Scanner ───────────────────────")
    for stype in ["simple", "medium", "complex", "malicious"]:
        print_stats(f"{stype.capitalize()} script scan", results[f"ast_{stype}"])

    print("\n── Phase 3: Sandbox Wrapper Generation ─────────────────")
    print_stats("Sandbox generation", results["sandbox_gen"])

    print("\n── Phase 4: LSF Script Generation ──────────────────────")
    print_stats("LSF script generation", results["lsf_gen"])

    # ── Total security overhead ───────────────────────────────────────────
    jwt_mean     = statistics.mean(results["jwt_validation"])
    ast_mean     = statistics.mean(results["ast_complex"])   # worst case
    sandbox_mean = statistics.mean(results["sandbox_gen"])
    lsf_mean     = statistics.mean(results["lsf_gen"])
    total        = jwt_mean + ast_mean + sandbox_mean + lsf_mean

    print(f"\n── Total Security Overhead (worst case) ────────────────")
    print(f"  JWT validation  : {jwt_mean:.4f} ms")
    print(f"  AST scan        : {ast_mean:.4f} ms  (complex script)")
    print(f"  Sandbox gen     : {sandbox_mean:.4f} ms")
    print(f"  LSF gen         : {lsf_mean:.4f} ms")
    print(f"  ─────────────────────────────────────")
    print(f"  TOTAL OVERHEAD  : {total:.4f} ms")

    # ── Save ──────────────────────────────────────────────────────────────
    output = f"benchmark_security_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Raw results saved to: {output}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
