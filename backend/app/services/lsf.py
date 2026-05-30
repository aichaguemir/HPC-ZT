from app.core.config import REMOTE_JOB_DIR
from typing import Optional

PYTHON_BIN        = "/home/mfahci/anaconda3/bin/python3"
PLATFORM_MPI_INIT = "/opt/ibm/platform_mpi/pmpi.sh"

# Nodes excluded from compute allocation (admin / broken nodes)
EXCLUDED_NODES = ["hpcadmin2", "hpcadmin1", "compute012", "compute022"]


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

SAFE_NAMES = {{
    'print', 'len', 'range', 'enumerate', 'zip',
    'map', 'filter', 'sorted', 'reversed', 'sum',
    'min', 'max', 'abs', 'round', 'int', 'float',
    'str', 'bool', 'list', 'dict', 'set', 'tuple',
    'bytes', 'bytearray', 'memoryview',
    'type', 'isinstance', 'issubclass',
    'hasattr', 'getattr', 'setattr',
    'iter', 'next', 'callable', 'repr',
    'staticmethod', 'classmethod', 'property',
    'super', 'object',
    'id', 'hash', 'hex', 'oct', 'bin',
    'chr', 'ord', 'format', 'vars',
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

def _safe_import(name, *args, **kwargs):
    top = name.split('.')[0]
    if name.startswith('_') or top.startswith('_'):
        return _original_import(name, *args, **kwargs)
    if top not in ALLOWED_MODULES:
        raise ImportError(f"Module '{{top}}' is not permitted")
    return _original_import(name, *args, **kwargs)

_original_import = _b.__import__

allowed_builtins = {{}}
for _name in SAFE_NAMES:
    if hasattr(_b, _name):
        allowed_builtins[_name] = getattr(_b, _name)

allowed_builtins['__import__'] = _safe_import
allowed_builtins['__build_class__'] = _b.__build_class__

with open('{REMOTE_JOB_DIR}/script_{unique_id}.py', 'r') as _f:
    _src = _f.read()

_code = compile(_src, 'user_script', 'exec')
exec(_code, {{'__builtins__': allowed_builtins}})
"""


def generate_lsf(
    unique_id:         str,
    username:          str,
    cores:             int,
    memory:            int,
    queue:             str,
    wall_time_hours:   int,
    wall_time_minutes: int,
    job_type:          str           = "serial",
    target_node:       Optional[str] = None,
    # MPI-specific
    mpi_processes:     Optional[int] = None,
    mpi_ptile:         Optional[int] = None,
) -> str:
    """
    Generates LSF batch script for two job types:

    serial   — single node, one or multiple cores, span[hosts=1]
                cores=1  → single-core serial job
                cores>1  → shared-memory multicore job (OpenMP / multiprocessing)

    mpi      — multi-node MPI via IBM Platform MPI, span[ptile=mpi_ptile]
                mpi_processes = total MPI ranks
                mpi_ptile     = ranks per node (must divide mpi_processes evenly)
    """
    queue       = queue.strip().lower()
    wall_time   = f"{wall_time_hours:02d}:{wall_time_minutes:02d}"
    total_secs  = (wall_time_hours * 3600) + (wall_time_minutes * 60) + 60
    user_dir    = f"{REMOTE_JOB_DIR}/{username}"
    job_workdir = f"{user_dir}/job_{unique_id}"

    # ── MPI: multi-node ────────────────────────────────────────────────────
    if job_type == "mpi":
        if not mpi_processes or not mpi_ptile:
            raise ValueError("MPI jobs require mpi_processes and mpi_ptile")

        nodes_needed    = mpi_processes // mpi_ptile
        node_exclusions = " && ".join(f"hname!={n}" for n in EXCLUDED_NODES)
        resource_req    = (
            f'select[{node_exclusions} && status==ok] '
            f'span[ptile={mpi_ptile}]'
        )

        return f"""#!/bin/bash
# MPI job: {mpi_processes} ranks across {nodes_needed} nodes ({mpi_ptile} ranks/node)

#BSUB -J job_{unique_id}
#BSUB -q {queue}
#BSUB -n {mpi_processes}
#BSUB -R "{resource_req}"
#BSUB -M {memory}
#BSUB -W {wall_time}
#BSUB -o {job_workdir}/output_{unique_id}.log
#BSUB -e {job_workdir}/error_{unique_id}.log

cd {job_workdir}

# ── Platform MPI environment ──────────────────────────────────────────
source {PLATFORM_MPI_INIT}
export LD_LIBRARY_PATH=/opt/ibm/platform_mpi/lib/linux_amd64:$LD_LIBRARY_PATH

# ── Disable nested threading (pure MPI mode) ─────────────────────────
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

# ── Build hostfile from LSF allocation ───────────────────────────────
MPI_HOSTS="{job_workdir}/hosts_{unique_id}_$LSB_JOBID"
cat $LSB_DJOB_HOSTFILE > $MPI_HOSTS

# ── Per-rank ulimits ──────────────────────────────────────────────────
ulimit -f 1048576
ulimit -u 128
ulimit -n 512

# ── Launch: each rank runs the sandbox wrapper ────────────────────────
mpirun -TCP -np $LSB_DJOB_NUMPROC -hostfile $MPI_HOSTS \\
    {PYTHON_BIN} {REMOTE_JOB_DIR}/sandbox_{unique_id}.py

# ── Cleanup ───────────────────────────────────────────────────────────
rm -f $MPI_HOSTS
rm -f {REMOTE_JOB_DIR}/sandbox_{unique_id}.py
rm -f {REMOTE_JOB_DIR}/script_{unique_id}.py
"""

    # ── Serial / multicore: single node ───────────────────────────────────
    job_comment = (
        f"# Multicore job: {cores} cores on single node"
        if cores > 1 else
        "# Serial job: 1 core"
    )
    node_flag = f'#BSUB -m "{target_node}"' if target_node else ""

    return f"""#!/bin/bash
{job_comment}

#BSUB -J job_{unique_id}
#BSUB -q {queue}
#BSUB -n {cores}
#BSUB -R "rusage[mem={memory}] span[hosts=1]"
#BSUB -M {memory}
#BSUB -W {wall_time}
#BSUB -o {job_workdir}/output_{unique_id}.log
#BSUB -e {job_workdir}/error_{unique_id}.log
{node_flag}

cd {job_workdir}

ulimit -f 1048576
ulimit -t {total_secs}
ulimit -u 64
ulimit -n 256
ulimit -v 33554432

{PYTHON_BIN} {REMOTE_JOB_DIR}/sandbox_{unique_id}.py

rm -f {REMOTE_JOB_DIR}/sandbox_{unique_id}.py
rm -f {REMOTE_JOB_DIR}/script_{unique_id}.py
"""
