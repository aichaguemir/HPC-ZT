#!/bin/bash
# ══════════════════════════════════════════════════════════════════
#  HPC-ZT  —  MPI Job Submission Test
#  Usage: bash test_mpi_submit.sh
# ══════════════════════════════════════════════════════════════════

KEYCLOAK="https://localhost:8443"   # Keycloak direct
API="https://localhost/api/v1"         # Nginx → FastAPI

REALM="HPC-Project"
CLIENT="hpc-backend"
USER="aichaguemir"
PASS="***REMOVED***"

# ── 1. Login ───────────────────────────────────────────────────────
echo "==> Authenticating..."
TOKEN=$(curl -sk -X POST \
  "${KEYCLOAK}/realms/${REALM}/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=${CLIENT}&username=${USER}&password=${PASS}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

if [ -z "$TOKEN" ]; then
  echo "ERROR: Could not obtain token."
  exit 1
fi
echo "Token: ${TOKEN:0:30}..."

# ── 2. Cluster state ───────────────────────────────────────────────
echo ""
echo "==> Cluster state..."
curl -sk "${API}/jobs/cluster/state" \
  -H "Authorization: Bearer ${TOKEN}" | python3 -m json.tool

# ── 3. Allocation options ──────────────────────────────────────────
echo ""
echo "==> Allocation options for 32 MPI ranks, ptile=16..."
curl -sk -X POST "${API}/jobs/options?cores=32&memory=4096&job_type=mpi&mpi_ptile=16" \
  -H "Authorization: Bearer ${TOKEN}" | python3 -m json.tool

# ── 4. Write MPI test script ───────────────────────────────────────
cat > /tmp/mpi_hello.py << 'PYEOF2'
from mpi4py import MPI
import time

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()

result = sum(range(rank * 1000, (rank + 1) * 1000))
all_results = comm.gather(result, root=0)

if rank == 0:
    total = sum(all_results)
    print("=" * 50)
    print(f"  MPI Hello from HPC-ZT Gateway!")
    print(f"  Ranks   : {size}")
    print(f"  Total   : {total}")
    print(f"  Status  : SUCCESS")
    print("=" * 50)
PYEOF2

# ── 5. Submit MPI job ──────────────────────────────────────────────
echo ""
echo "==> Submitting MPI job (32 ranks, 2 nodes x 16, queue_web)..."
RESPONSE=$(curl -sk -X POST "${API}/jobs/submit" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "file=@/tmp/mpi_hello.py" \
  -F "cores=32" \
  -F "memory=4096" \
  -F "queue=queue_web" \
  -F "wall_time_hours=0" \
  -F "wall_time_minutes=10" \
  -F "job_type=mpi" \
  -F "mpi_processes=32" \
  -F "mpi_ptile=16")

echo "$RESPONSE" | python3 -m json.tool

JOB_ID=$(echo "$RESPONSE" | python3 -c \
  "import sys,json; print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null)

if [ -z "$JOB_ID" ]; then
  echo "ERROR: No job_id in response. Submission failed."
  exit 1
fi
echo ""
echo "==> Job submitted: job_id=${JOB_ID}"

# ── 6. Poll status ─────────────────────────────────────────────────
echo ""
echo "==> Polling status every 5s..."
for i in $(seq 1 24); do
  STATUS=$(curl -sk "${API}/jobs/${JOB_ID}/status" \
    -H "Authorization: Bearer ${TOKEN}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
  echo "  [$(date +%H:%M:%S)] status=${STATUS}"
  if [[ "$STATUS" == "DONE" || "$STATUS" == "EXIT" ]]; then
    break
  fi
  sleep 5
done

# ── 7. Output ──────────────────────────────────────────────────────
echo ""
echo "==> Output:"
curl -sk "${API}/jobs/${JOB_ID}/output" \
  -H "Authorization: Bearer ${TOKEN}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('output','(empty)'))"

# ── 8. Error log ───────────────────────────────────────────────────
echo ""
echo "==> Error log:"
curl -sk "${API}/jobs/${JOB_ID}/error" \
  -H "Authorization: Bearer ${TOKEN}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','(empty)'))"
