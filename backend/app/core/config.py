import os
from dotenv import load_dotenv

load_dotenv()

# ==============================
# SSH CONFIG
# ==============================
SSH_HOST       = os.getenv("SSH_HOST")
SSH_USER       = os.getenv("SSH_USER")
SSH_PASSWORD   = os.getenv("SSH_PASSWORD")
LSF_PATH       = os.getenv("LSF_PATH")
REMOTE_JOB_DIR = os.getenv("REMOTE_JOB_DIR")

SMTP_USER: str = os.getenv("SMTP_USER", "")
SMTP_PASS: str = os.getenv("SMTP_PASS", "")
# ==============================
# DATABASE
# ==============================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./hpc_gateway.db"
)

# ==============================
# AUTH / JWT
# ==============================
SECRET_KEY                  = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# ==============================
# KEYCLOAK (filled in when integrated)
# ==============================
KEYCLOAK_URL           = os.getenv("KEYCLOAK_URL", "")
KEYCLOAK_REALM         = os.getenv("KEYCLOAK_REALM", "")
KEYCLOAK_CLIENT_ID     = os.getenv("KEYCLOAK_CLIENT_ID", "")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "")




SMTP_HOST: str = os.getenv("SMTP_HOST", "mail.univ-sba.dz")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_FROM: str = os.getenv("SMTP_FROM", "hpc-portal@univ-sba.dz")
# ==============================
# JOB LIMITS (fallback — real limits come from policies table)
# ==============================
MAX_WALL_TIME_HOURS   = 24
MIN_WALL_TIME_MINUTES = 1
MAX_CORES_PER_JOB     = 16
MAX_CORES_TOTAL       = 352
MAX_MEMORY_MB         = 31900
MIN_MEMORY_MB         = 100
MAX_JOBS_PER_USER     = 5
MAX_FILE_SIZE         = 10 * 1024 * 1024  # 10MB

VALID_QUEUES = ["low_priority", "medium_priority", "high_priority"]

# ==============================
# SECURITY — ALLOWLIST MODEL
# ==============================

# Only these modules are permitted in user scripts
ALLOWED_MODULES = {
    # Scientific computing
    "numpy", "scipy", "pandas", "matplotlib",
    "sklearn", "tensorflow", "torch", "keras",
    "statsmodels", "sympy", "numba", "cupy",
    "seaborn", "plotly", "bokeh",

    # Data I/O
    "h5py", "netCDF4", "zarr", "xarray",
    "PIL", "cv2", "imageio", "tifffile",

    # Standard library — safe subset
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

    # Parallel computing (HPC relevant)
    "multiprocessing", "concurrent", "threading",
    "mpi4py",
}

# These are always blocked regardless of import
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
