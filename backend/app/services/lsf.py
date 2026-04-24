from app.core.config import REMOTE_JOB_DIR


def generate_sandbox_wrapper(unique_id: str) -> str:
    return f"""import builtins as _b

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
    _code = compile(_f.read(), 'user_script', 'exec')
    exec(_code, {{'__builtins__': allowed_builtins}})
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
    total_secs  = (wall_time_hours * 3600) + (wall_time_minutes * 60) + 60
    user_dir    = f"{REMOTE_JOB_DIR}/{username}"
    job_workdir = f"{user_dir}/job_{unique_id}"

    script = f"""#!/bin/bash
#BSUB -J job_{unique_id}
#BSUB -q {queue}
#BSUB -n {cores}
#BSUB -R "rusage[mem={memory}] span[hosts=1]"
#BSUB -M {memory}
#BSUB -W {wall_time}
#BSUB -o {job_workdir}/output_{unique_id}.log
#BSUB -e {job_workdir}/error_{unique_id}.log

cd {job_workdir}

ulimit -f 1048576
ulimit -t {total_secs}
ulimit -u 64
ulimit -n 256
ulimit -v 33554432

python3 {REMOTE_JOB_DIR}/sandbox_{unique_id}.py

rm -f {REMOTE_JOB_DIR}/sandbox_{unique_id}.py
rm -f {REMOTE_JOB_DIR}/script_{unique_id}.py
"""
    return script
