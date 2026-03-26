import threading
from typing import Dict

# In-memory job store — replace with DB later
# Maps job_id (or "pending_uuid") -> unique_id
job_store: Dict[str, str] = {}
job_store_lock = threading.Lock()
