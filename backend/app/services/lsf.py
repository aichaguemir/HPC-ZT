from app.core.config import REMOTE_JOB_DIR


def generate_sandbox_wrapper(unique_id: str) -> str:
    return f"""import builtins as _b
import sys as _sys

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

_original_import  = _b.__import__
_b.__import__     = _safe_import

SAFE = {{
    'print', 'len', 'range', 'enumerate', 'zip',
    'map', 'filter', 'sorted', 'reversed', 'sum',
    'min', 'max', 'abs', 'round', 'int', 'float',
    'str', 'bool', 'list', 'dict', 'set', 'tuple',
    'bytes', 'bytearray', 'memoryview',
    'type', 'isinstance', 'issubclass', 'open',
    'hasattr', 'getattr', 'setattr',
    'iter', 'next', 'callable', 'repr',
    'staticmethod', 'classmethod', 'property',
    'super', 'object',
    'id', 'hash', 'hex', 'oct', 'bin',
    'chr', 'ord',
    'format', 'vars',
    'True', 'False', 'None',
    'NotImplemented', 'Ellipsis',
    'Exception', 'ValueError', 'TypeError', 'ImportError',
    'KeyError', 'IndexError', 'StopIteration',
    'ArithmeticError', 'RuntimeError', 'OSError',
    'AttributeError', 'NameError', 'ZeroDivisionError',
    'FileNotFoundError', 'PermissionError',
    'GeneratorExit', 'SystemExit', 'KeyboardInterrupt',
    'Warning', 'UserWarning', 'DeprecationWarning',
    '__import__', '__name__', '__doc__',
    '__package__', '__spec__', '__loader__', '__builtins__',
    '__build_class__',
}}

_delattr = delattr
_open    = open
_compile = compile
_exec    = exec

for _n in list(vars(_b).keys()):
    if _n not in SAFE:
        try:
            _delattr(_b, _n)
        except AttributeError:
            pass

with _open('{REMOTE_JOB_DIR}/script_{unique_id}.py', 'r') as _f:
    _exec(_compile(_f.read(), 'user_script', 'exec'))
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
