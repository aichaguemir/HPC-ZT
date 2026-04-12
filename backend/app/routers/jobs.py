import re
import uuid
import os
import tempfile
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.config import LSF_PATH, REMOTE_JOB_DIR
from app.core.logging import logger
from app.core.auth import get_current_user
from app.db.session import get_db
from app.db.models import Job, Policy, PolicyQueue, AuditLog, User
from app.schemas.jobs import (
    JobResponse, JobStatus, JobStatusResponse,
    JobCancelResponse, JobOutputResponse, JobErrorResponse,
    JobSubmitParams,
)
from app.validators.script import validate_script
from app.services.ssh import run_ssh_async, transfer_files
from app.services.lsf import generate_lsf, generate_sandbox_wrapper
from app.core.carta import run_carta, apply_carta_result, get_or_create_session
from app.core.auth import oauth2_scheme,get_current_user_and_token 
from sqlalchemy import update
from app.core.audit_chain import write_audit_entry
from app.core.config import KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_CLIENT_ID


router = APIRouter(prefix="/jobs", tags=["jobs"])


# ── Helper: load policy for user ───────────────────────────────────────────

async def get_policy(user: User, db: AsyncSession) -> Policy:
    result = await db.execute(
        select(Policy).where(Policy.role == user.role)
    )
    policy = result.scalar_one_or_none()
    if policy is None:
        raise HTTPException(503, "Policy not configured for your role. Contact admin.")
    return policy

# ==============================
# SUBMIT
# ==============================
@router.post("/submit", response_model=JobResponse)
async def submit_job(
    file:              UploadFile   = File(...),
    cores:             int          = Form(...),
    memory:            int          = Form(...),
    queue:             str          = Form(...),
    wall_time_hours:   int          = Form(...),
    wall_time_minutes: int          = Form(...),
    request:           Request      = None,
    db:                AsyncSession = Depends(get_db),
    current_user_and_token          = Depends(get_current_user_and_token),
):
    current_user, token = current_user_and_token
 
    # ① Auto-expire stuck jobs first
    await db.execute(
        update(Job)
        .where(Job.user_id == current_user.user_id)
        .where(Job.status.in_(["PEND", "RUN"]))
        .where(Job.submitted_at < datetime.now(timezone.utc) - timedelta(hours=2))
        .values(status="EXIT", finished_at=datetime.now(timezone.utc))
    )
    await db.commit()
 
    # ② Read and validate file
    content = await file.read()
    validate_script(file, content)
 
    # ③ Load policy
    policy = await get_policy(current_user, db)
 
    # ④ Validate parameters against policy
    try:
        params = JobSubmitParams(
            cores=cores, memory=memory, queue=queue,
            wall_time_hours=wall_time_hours,
            wall_time_minutes=wall_time_minutes,
            policy=policy,
        )
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
 
    # ⑤ Check queue allowed for role
    allowed_queues = {pq.queue_name for pq in policy.allowed_queues}
    if params.queue not in allowed_queues:
        raise HTTPException(400,
            detail=f"Queue '{params.queue}' not permitted. "
                   f"Allowed: {', '.join(allowed_queues)}")
 
    # ⑥ Check concurrent job quota
    active_result = await db.execute(
        select(func.count(Job.job_id))
        .where(Job.user_id == current_user.user_id)
        .where(Job.status.in_(["PEND", "RUN"]))
    )
    if active_result.scalar() >= policy.max_concurrent_jobs:
        raise HTTPException(429,
            detail=f"Maximum {policy.max_concurrent_jobs} concurrent jobs for your role.")
 
    # ⑦ Check daily quota
    if policy.max_jobs_per_day:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0)
        daily_result = await db.execute(
            select(func.count(Job.job_id))
            .where(Job.user_id == current_user.user_id)
            .where(Job.submitted_at >= today_start)
        )
        if daily_result.scalar() >= policy.max_jobs_per_day:
            raise HTTPException(429,
                detail=f"Daily job limit of {policy.max_jobs_per_day} reached.")
 
    # ⑧ Per-minute rate limit (role-aware, user-based)
    RATE_LIMITS = {"student": 5, "researcher": 20, "admin": 60}
    rate_limit  = RATE_LIMITS.get(current_user.role, 5)
    one_min_ago = datetime.now(timezone.utc) - timedelta(seconds=60)
    recent_result = await db.execute(
        select(func.count(Job.job_id))
        .where(Job.user_id     == current_user.user_id)
        .where(Job.submitted_at >= one_min_ago)
    )
    if recent_result.scalar() >= rate_limit:
        raise HTTPException(429,
            detail=f"Rate limit exceeded. Max {rate_limit} submissions/minute "
                   f"for {current_user.role} role.")
 
    # ⑨ Insert pending job
    unique_id   = str(uuid.uuid4())
    pending_job = Job(
        job_id                     = f"pending_{unique_id}",
        unique_id                  = unique_id,
        user_id                    = current_user.user_id,
        status                     = "PEND",
        queue                      = params.queue,
        cores                      = params.cores,
        memory                     = params.memory,
        wall_time                  = f"{params.wall_time_hours:02d}:{params.wall_time_minutes:02d}",
        script_filename            = file.filename,
        output_file                = f"output_{unique_id}.log",
        error_file                 = f"error_{unique_id}.log",
        policy_id_at_submission    = policy.policy_id,
        policy_role_at_submission  = current_user.role,
        cores_limit_at_submission  = policy.max_cores_per_job,
        memory_limit_at_submission = policy.max_memory_mb,
    )
    db.add(pending_job)
    await db.flush()
 
    # ⑩ CARTA risk evaluation
    session      = await get_or_create_session(current_user, token, request, db)
    carta_result = await run_carta(
        job     = pending_job,
        user    = current_user,
        policy  = policy,
        db      = db,
        request = request,
        session = session,
    )
    await apply_carta_result(pending_job, carta_result, db)
    logger.info(f"CARTA DEBUG: request={carta_result['request_score']} session={carta_result['session_score']} action={carta_result['action']['action']}      signals={carta_result['signals']}") 
    if carta_result["action"]["action"] == "block":
        await db.delete(pending_job)
        await db.commit()
        await write_audit_entry(
            db         = db,
            action     = "job_submit",
            result     = "blocked",
            user_id    = current_user.user_id,
            ip_address = request.client.host if request and request.client else None,
            detail     = {
                "reason":      "critical_risk",
                "carta_score": carta_result["session_score"],
                "signals":     carta_result["signals"],
            }
        )
        await db.commit()
        raise HTTPException(403, detail={
            "message":    "Job blocked — risk score too high",
            "risk_score": carta_result["session_score"],
            "signals":    carta_result["signals"],
        })
 
    # ⑫ MFA required if high risk
    if carta_result["action"]["action"] == "flag_and_mfa":
        await db.delete(pending_job)
        await db.commit()
        await write_audit_entry(
            db         = db,
            action     = "job_submit",
            result     = "mfa_required",
            user_id    = current_user.user_id,
            ip_address = request.client.host if request and request.client else None,
            detail     = {
                "reason":      "high_risk",
                "carta_score": carta_result["session_score"],
                "signals":     carta_result["signals"],
            }
        )
        await db.commit()
        raise HTTPException(403, detail={
            "status":     "mfa_required",
            "risk_score": carta_result["session_score"],
            "signals":    carta_result["signals"],
            "message":    "Step-up authentication required. Complete MFA and resubmit.",
            "reauth_url": (
                f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
                f"/protocol/openid-connect/auth"
                f"?client_id={KEYCLOAK_CLIENT_ID}"
                f"&response_type=code&scope=openid&acr_values=gold"
            )
        })
 
    # ⑬ Write files, transfer, submit to LSF
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
                    unique_id, current_user.username,
                    params.cores, params.memory, params.queue,
                    params.wall_time_hours, params.wall_time_minutes,
                ))
 
            await transfer_files(local_script, local_lsf, local_sandbox, unique_id)
 
            safe_path = REMOTE_JOB_DIR if REMOTE_JOB_DIR.startswith('/') else f"/{REMOTE_JOB_DIR}"
            safe_path = safe_path.rstrip('/')
 
            result = await run_ssh_async(
                f"{LSF_PATH}/bsub < {safe_path}/job_{unique_id}.lsf"
            )
 
            match = re.search(r"Job <(\d+)>", result)
            if not match:
                raise HTTPException(500, detail=f"Job submission failed: {result}")
 
            job_id = match.group(1)
 
            # Update DB with real LSF job ID
            pending_job.job_id = job_id
            await db.commit()
 
            # ⑭ Audit chain entry
            await write_audit_entry(
                db         = db,
                action     = "job_submit",
                result     = "success",
                user_id    = current_user.user_id,
                job_id     = job_id,
                ip_address = request.client.host if request and request.client else None,
                detail     = {
                    "cores":         params.cores,
                    "memory":        params.memory,
                    "queue":         params.queue,
                    "script":        file.filename,
                    "carta_score":   carta_result["session_score"],
                    "carta_signals": carta_result["signals"],
                    "carta_level":   carta_result["level"],
                }
            )
            await db.commit()
 
            logger.info(
                f"Job submitted: job_id={job_id} "
                f"user={current_user.username} "
                f"cores={params.cores} queue={params.queue} "
                f"carta_score={carta_result['session_score']}"
            )
 
            return JobResponse(
                job_id          = job_id,
                status          = JobStatus.PEND.value,
                output_file     = f"output_{unique_id}.log",
                error_file      = f"error_{unique_id}.log",
                wall_time       = f"{params.wall_time_hours:02d}:{params.wall_time_minutes:02d}",
                script_filename = file.filename,
                cores           = params.cores,
                memory          = params.memory,
                queue           = params.queue,
            )
 
        except Exception:
            await db.delete(pending_job)
            await db.commit()
            raise

# ==============================
# STATUS
# ==============================

@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id:       str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    result = await db.execute(
        select(Job)
        .where(Job.job_id == job_id)
        .where(Job.user_id == current_user.user_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "Job not found")

    lsf_result = await run_ssh_async(f"{LSF_PATH}/bjobs {job_id}")
    lines      = lsf_result.strip().splitlines()

    if len(lines) < 2 or "not found" in lsf_result.lower():
        return JobStatusResponse(job_id=job_id, status="UNKNOWN", queue="N/A", cores="N/A")

    parts = lines[1].split()
    if len(parts) < 4:
        return JobStatusResponse(job_id=job_id, status="UNKNOWN", queue="N/A", cores="N/A")

    job.status = parts[2]
    await db.commit()

    return JobStatusResponse(
        job_id=parts[0], status=parts[2], queue=parts[3], cores="N/A"
    )


# ==============================
# OUTPUT
# ==============================

@router.get("/{job_id}/output", response_model=JobOutputResponse)
async def get_job_output(
    job_id:       str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    result = await db.execute(
        select(Job)
        .where(Job.job_id == job_id)
        .where(Job.user_id == current_user.user_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "Job not found")

    user_result = await db.execute(select(User).where(User.user_id == job.user_id))
    job_user    = user_result.scalar_one_or_none()
    job_workdir = f"{REMOTE_JOB_DIR}/users/{job_user.username}/job_{job.unique_id}"

    check_cmd = (
        f"test -f {job_workdir}/output_{job.unique_id}.log "
        f"&& tail -n 500 {job_workdir}/output_{job.unique_id}.log "
        f"|| echo 'OUTPUT_NOT_READY'"
    )

    output = await run_ssh_async(check_cmd)

    if output == "OUTPUT_NOT_READY":
        return JobOutputResponse(
            job_id=job_id,
            output="Job output not available yet. Job may still be running."
        )

    marker = "The output (if any) follows:"
    if marker in output:
        output = output.split(marker, 1)[1].strip()

    log = AuditLog(user_id=current_user.user_id, job_id=job_id, action="view_output")
    db.add(log)
    await db.commit()

    return JobOutputResponse(job_id=job_id, output=output)


# ==============================
# ERROR LOG
# ==============================

@router.get("/{job_id}/error", response_model=JobErrorResponse)
async def get_job_error(
    job_id:       str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    result = await db.execute(
        select(Job)
        .where(Job.job_id == job_id)
        .where(Job.user_id == current_user.user_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "Job not found")

    user_result = await db.execute(select(User).where(User.user_id == job.user_id))
    job_user    = user_result.scalar_one_or_none()
    job_workdir = f"{REMOTE_JOB_DIR}/users/{job_user.username}/job_{job.unique_id}"

    check_cmd = (
        f"test -f {job_workdir}/error_{job.unique_id}.log "
        f"&& tail -n 500 {job_workdir}/error_{job.unique_id}.log "
        f"|| echo 'ERROR_NOT_READY'"
    )

    error = await run_ssh_async(check_cmd)

    if error == "ERROR_NOT_READY":
        return JobErrorResponse(job_id=job_id, error="Error log not created yet.")

    log = AuditLog(user_id=current_user.user_id, job_id=job_id, action="view_error")
    db.add(log)
    await db.commit()

    return JobErrorResponse(job_id=job_id, error=error)


# ==============================
# CANCEL
# ==============================

@router.delete("/{job_id}/cancel", response_model=JobCancelResponse)
async def cancel_job(
    job_id:       str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    result = await db.execute(
        select(Job)
        .where(Job.job_id == job_id)
        .where(Job.user_id == current_user.user_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "Job not found")

    lsf_result   = await run_ssh_async(f"{LSF_PATH}/bkill {job_id}")
    job.status       = "EXIT"
    job.cancelled_by = current_user.user_id
    job.finished_at  = datetime.now(timezone.utc)

    log = AuditLog(
        user_id = current_user.user_id,
        job_id  = job_id,
        action  = "job_cancel",
        detail  = {"cancelled_by": current_user.username}
    )
    db.add(log)
    await db.commit()

    logger.info(f"Job cancelled: job_id={job_id}, by={current_user.username}")
    return JobCancelResponse(job_id=job_id, message="Job cancelled", result=lsf_result)


# ==============================
# LIST
# ==============================

@router.get("/")
async def list_jobs(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    result = await db.execute(
        select(Job)
        .where(Job.user_id == current_user.user_id)
        .order_by(Job.submitted_at.desc())
    )
    jobs = result.scalars().all()
    if not jobs:
        return {"jobs": []}
    return {
        "jobs": [
            {
                "job_id":    j.job_id,
                "status":    j.status,
                "queue":     j.queue,
                "cores":     j.cores,
                "memory":    j.memory,
                "submitted": str(j.submitted_at),
            }
            for j in jobs
        ]
    }
