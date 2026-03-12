import re
import uuid
import os
import tempfile

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from app.core.config import (
    LSF_PATH,
    REMOTE_JOB_DIR,
    MAX_JOBS_PER_USER,
)
from app.core.store    import job_store, job_store_lock
from app.core.logging  import logger
from app.schemas.jobs import (
    JobResponse, JobStatus, JobStatusResponse,
    JobCancelResponse, JobOutputResponse, JobErrorResponse,
    JobSubmitParams,   
)
from app.validators.script import validate_script
from app.services.ssh  import run_ssh_async, transfer_files
from app.services.lsf  import generate_lsf, generate_sandbox_wrapper

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.get("/") 
async def list_jobs():
    tracked_ids = [
        jid for jid in job_store.keys()
        if not jid.startswith("pending_")
    ]
    if not tracked_ids:
        return {"jobs": []}

    id_list = " ".join(tracked_ids)

    # LSF 9.1 compatible:
    result = await run_ssh_async(f"{LSF_PATH}/bjobs {id_list}")
    return {"jobs": result} 
# ==============================
# SUBMIT
# ==============================

@router.post("/submit", response_model=JobResponse)
async def submit_job(
    file:              UploadFile = File(...),
    cores:             int        = Form(...),
    memory:            int        = Form(...),
    queue:             str        = Form(...),
    wall_time_hours:   int        = Form(...),
    wall_time_minutes: int        = Form(...)
):
    # --- Read file ---
    content = await file.read()

    # --- Validate script ---
    validate_script(file, content)

    # --- Validate parameters via Pydantic ---
    try:
        params = JobSubmitParams(
            cores=cores,
            memory=memory,
            queue=queue,
            wall_time_hours=wall_time_hours,
            wall_time_minutes=wall_time_minutes
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # --- Reserve job slot (TOCTOU-safe) ---
    with job_store_lock:
        if len(job_store) >= MAX_JOBS_PER_USER:
            raise HTTPException(
                status_code=429,
                detail=f"Maximum {MAX_JOBS_PER_USER} jobs allowed!"
            )
        unique_id = str(uuid.uuid4())
        job_store[f"pending_{unique_id}"] = unique_id

    # --- Write, transfer, submit ---
    with tempfile.TemporaryDirectory() as tmpdir:
        local_script  = os.path.join(tmpdir, f"script_{unique_id}.py")
        local_lsf     = os.path.join(tmpdir, f"job_{unique_id}.lsf")
        local_sandbox = os.path.join(tmpdir, f"sandbox_{unique_id}.py")

        try:
            with open(local_script, "wb") as f:
                f.write(content)

            with open(local_sandbox, "w") as f:
                f.write(generate_sandbox_wrapper(unique_id))

            with open(local_lsf, "w") as f:
                f.write(generate_lsf(
                    unique_id,
                    params.cores,           # ← params
                    params.memory,          # ← params
                    params.queue,           # ← params
                    params.wall_time_hours, # ← params
                    params.wall_time_minutes# ← params
                ))

            await transfer_files(local_script, local_lsf, local_sandbox, unique_id)

            result = await run_ssh_async(
                f"{LSF_PATH}/bsub < {REMOTE_JOB_DIR}/job_{unique_id}.lsf"
            )

            match = re.search(r"Job <(\d+)>", result)
            if not match:
                raise HTTPException(
                    status_code=500,
                    detail=f"Job submission failed: {result}"
                )

            job_id = match.group(1)

            with job_store_lock:
                job_store.pop(f"pending_{unique_id}", None)
                job_store[job_id] = unique_id

            logger.info(
                f"Job submitted: job_id={job_id}, uuid={unique_id}, "
                f"cores={params.cores}, memory={params.memory}, "  # ← params
                f"queue={params.queue}, file={file.filename}"       # ← params
            )

            return JobResponse(
                job_id=job_id,
                status=JobStatus.PEND.value,
                output_file=f"output_{unique_id}.log",
                error_file=f"error_{unique_id}.log",
                wall_time=f"{params.wall_time_hours:02d}:{params.wall_time_minutes:02d}",
                script_filename=file.filename,  # ← NEW
                cores=params.cores,             # ← NEW
                memory=params.memory,           # ← NEW
                queue=params.queue              # ← NEW
            )

        except Exception:
            with job_store_lock:
                job_store.pop(f"pending_{unique_id}", None)
            raise



# ==============================

@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")

    # LSF 9.1 compatible — no -noheader, no -o flag
    result = await run_ssh_async(f"{LSF_PATH}/bjobs {job_id}")

    lines = result.strip().splitlines()

    # Job not found on cluster
    if len(lines) < 2 or "not found" in result.lower():
        return JobStatusResponse(
            job_id=job_id,
            status="UNKNOWN",
            queue="N/A",
            cores="N/A"
        )

    # Skip header line (line 0), parse data line (line 1)
    parts = lines[1].split()
    if len(parts) < 4:
        return JobStatusResponse(
            job_id=job_id,
            status="UNKNOWN",
            queue="N/A",
            cores="N/A"
        )

    return JobStatusResponse(
        job_id=parts[0],   # JOBID
        status=parts[2],   # STAT
        queue=parts[3],    # QUEUE
        cores="N/A"        # LSF 9.1 bjobs doesn't show cores in default output
    )

# ==============================
# OUTPUT
# ==============================

@router.get("/{job_id}/output", response_model=JobOutputResponse)
async def get_job_output(job_id: str):
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")

    unique_id = job_store[job_id]
    check_cmd = (
        f"test -f {REMOTE_JOB_DIR}/output_{unique_id}.log "
        f"&& tail -n 500 {REMOTE_JOB_DIR}/output_{unique_id}.log "
        f"|| echo 'OUTPUT_NOT_READY'"
    )

    logger.info(f"Fetching output: job_id={job_id}, uuid={unique_id}")
    result = await run_ssh_async(check_cmd)

    if result == "OUTPUT_NOT_READY":
        return JobOutputResponse(
            job_id=job_id,
            output="Job output not available yet. Job may still be running."
        )

    marker = "The output (if any) follows:"
    if marker in result:
        result = result.split(marker, 1)[1].strip()

    return JobOutputResponse(job_id=job_id, output=result)


# ==============================
# ERROR LOG
# ==============================

@router.get("/{job_id}/error", response_model=JobErrorResponse)
async def get_job_error(job_id: str):
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")

    unique_id = job_store[job_id]
    check_cmd = (
        f"test -f {REMOTE_JOB_DIR}/error_{unique_id}.log "
        f"&& tail -n 500 {REMOTE_JOB_DIR}/error_{unique_id}.log "
        f"|| echo 'NO_ERROR_LOG'"
    )

    result = await run_ssh_async(check_cmd)

    if result == "NO_ERROR_LOG":
        return JobErrorResponse(job_id=job_id, error="Error log not created yet.")

    return JobErrorResponse(job_id=job_id, error=result)


# ==============================
# CANCEL
# ==============================

@router.delete("/{job_id}/cancel", response_model=JobCancelResponse)
async def cancel_job(job_id: str):
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")

    result = await run_ssh_async(f"{LSF_PATH}/bkill {job_id}")

    with job_store_lock:
        job_store.pop(job_id, None)

    logger.info(f"Job cancelled: job_id={job_id}")
    return JobCancelResponse(job_id=job_id, message="Job cancelled", result=result)


# ==============================
# LIST
# ==============================

