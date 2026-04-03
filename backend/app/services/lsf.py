from app.core.config import REMOTE_JOB_DIR


def generate_sandbox_wrapper(unique_id: str) -> str:
    return f"""
import builtins as _b

SAFE = {{
    'print', 'len', 'range', 'enumerate', 'zip',
    'map', 'filter', 'sorted', 'reversed', 'sum',
    'min', 'max', 'abs', 'round', 'int', 'float',
    'str', 'bool', 'list', 'dict', 'set', 'tuple',
    '__import__'
}}

safe_builtins = {{k: getattr(_b, k) for k in SAFE if hasattr(_b, k)}}

exec(open('script_{unique_id}.py').read(), {{
    "__builtins__": safe_builtins
}})
"""

def generate_lsf(
    unique_id:         str,
    username:          str,
    cores:             int,
    memory:            int,
    queue:             str,
    wall_time_hours:   int,
    wall_time_minutes: int
) -> str:
    queue       = queue.strip().lower()
    wall_time   = f"{wall_time_hours:02d}:{wall_time_minutes:02d}"
    total_secs  = (wall_time_hours * 3600) + (wall_time_minutes * 60)
    user_dir    = f"{REMOTE_JOB_DIR}/users/{username}"
    job_workdir = f"{user_dir}/job_{unique_id}"

    return f"""#!/bin/bash
#BSUB -J job_{unique_id}
#BSUB -q {queue}
#BSUB -n {cores}
#BSUB -R "rusage[mem={memory}]"
#BSUB -M {memory}
#BSUB -W {wall_time}
#BSUB -o {job_workdir}/output_{unique_id}.log
#BSUB -e {job_workdir}/error_{unique_id}.log

# ── Per-user directory ─────────────────────────────────────────
mkdir -p {user_dir}
chmod 700 {user_dir}

# ── Per-job isolated working directory ────────────────────────
mkdir -p {job_workdir}
chmod 700 {job_workdir}
cd {job_workdir}

# ── Resource limits ────────────────────────────────────────────
ulimit -f 1048576
ulimit -t {total_secs}
ulimit -u 64
ulimit -n 256
ulimit -v 33554432

# ── Execute via sandbox ────────────────────────────────────────
python3 {REMOTE_JOB_DIR}/sandbox_{unique_id}.py
"""
