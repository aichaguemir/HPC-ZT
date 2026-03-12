import os
from dotenv import load_dotenv

load_dotenv()

# ==============================
# SSH CONFIG
# ==============================
SSH_HOST     = os.getenv("SSH_HOST")
SSH_USER     = os.getenv("SSH_USER")
SSH_PASSWORD = os.getenv("SSH_PASSWORD")
LSF_PATH     = os.getenv("LSF_PATH")
REMOTE_JOB_DIR = os.getenv("REMOTE_JOB_DIR")

# ==============================
# JOB LIMITS
# ==============================
MAX_WALL_TIME_HOURS   = 24
MIN_WALL_TIME_MINUTES = 1
MAX_CORES_PER_JOB     = 16      # one node = 16 cores max
MAX_CORES_TOTAL       = 352     # 22 nodes × 16 cores
MAX_MEMORY_MB         = 31900   # 31.9GB per node
MIN_MEMORY_MB         = 100
MAX_JOBS_PER_USER     = 5
MAX_FILE_SIZE         = 10 * 1024 * 1024  # 10MB

VALID_QUEUES = ["low_priority", "medium_priority", "high_priority"]

# ==============================
# SECURITY CONSTANTS
# ==============================
FORBIDDEN_MODULES = {
    "os", "subprocess", "shutil", "sys",
    "socket", "requests", "urllib",
    "importlib", "builtins", "ctypes"
}

FORBIDDEN_FUNCTIONS = {
    "eval", "exec", "compile", "open",
    "__import__", "input", "vars", "dir",
    "globals", "locals", "getattr", "setattr",
    "delattr", "hasattr"
}

FORBIDDEN_ATTRIBUTES = {
    "__import__", "__builtins__", "__globals__",
    "__locals__", "__code__", "__closure__",
    "__bases__", "__subclasses__", "__mro__",
    "__dict__", "__loader__", "__spec__"
}
