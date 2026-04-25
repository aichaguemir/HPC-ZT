import re
import uuid
import os
import tempfile
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.core.config import LSF_PATH, REMOTE_JOB_DIR, KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_CLIENT_ID
from app.core.logging import logger
from app.core.auth import get_current_user, oauth2_scheme, get_current_user_and_token
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
from app.core.audit_chain import write_audit_entry
from app.core.dynamic_allocation import get_cluster_state, get_allocation_options

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


# ══════════════════════════════════════════════════════════════════════════
# SUBMIT
# ══════════════════════════════════════════════════════════════════════════

@router.post("/submit", response_model=JobResponse)
async def submit_job(
    file:              UploadFile   = File(...),
    cores:             int          = Form(...),
    memory:            int          = Form(...),
    queue:             str          = Form(...),
    wall_time_hours:   int          = Form(...),
    wall_time_minutes: int          = Form(...),
    job_type:          str          = Form("serial"),
    chunks:            Optional[int]= Form(None),
    cores_per_chunk:   Optional[int]= Form(None),
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

    # ⑨ Validate parallel job parameters
    if job_type == "parallel":
        if current_user.role == "student":
            raise HTTPException(400,
                "Parallel jobs require researcher or admin role")
        if not chunks or chunks < 2:
            raise HTTPException(400, "Parallel jobs require chunks >= 2")
        if not cores_per_chunk or cores_per_chunk < 1:
            raise HTTPException(400, "Parallel jobs require cores_per_chunk >= 1")
        if chunks * cores_per_chunk > policy.max_cores_per_job:
            raise HTTPException(400,
                f"Total cores ({chunks * cores_per_chunk}) exceeds "
                f"policy limit ({policy.max_cores_per_job}) for {current_user.role} role.")
        if cores_per_chunk > 16:
            raise HTTPException(400,
                "cores_per_chunk cannot exceed 16 (node capacity)")

    # ⑩ Insert pending job
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

    # ⑪ CARTA risk evaluation
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

    logger.info(
        f"CARTA: user={current_user.username} "
        f"score={carta_result['session_score']} "
        f"action={carta_result['action']['action']} "
        f"signals={carta_result['signals']}"
    )

    # ⑫ Block if critical risk
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

    # ⑬ MFA required if high risk
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

    # ⑭ Write files, transfer, submit to LSF
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
                    job_type        = job_type,
                    chunks          = chunks,
                    cores_per_chunk = cores_per_chunk,
                ))

            await transfer_files(
                local_script, local_lsf, local_sandbox,
                unique_id, current_user.username
            )

            safe_path   = REMOTE_JOB_DIR.rstrip('/')
            user_dir    = f"{safe_path}/{current_user.username}"
            job_workdir = f"{user_dir}/job_{unique_id}"

            # Create job directory BEFORE bsub so LSF writes output there
            await run_ssh_async(
                f"mkdir -p {job_workdir} && "
                f"chmod 700 {job_workdir} && "
                f"chmod 700 {user_dir}"
            )

            result = await run_ssh_async(
                f"{LSF_PATH}/bsub < {safe_path}/job_{unique_id}.lsf"
            )

            # Clean up LSF file from cluster
            await run_ssh_async(
                f"rm -f {safe_path}/job_{unique_id}.lsf"
            )

            match = re.search(r"Job <(\d+)>", result)
            if not match:
                raise HTTPException(500, detail=f"Job submission failed: {result}")

            job_id = match.group(1)

            # Update DB with real LSF job ID
            pending_job.job_id = job_id
            await db.commit()

            # ⑮ Audit chain entry
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
                    "job_type":      job_type,
                    "chunks":        chunks,
                    "cores_per_chunk": cores_per_chunk,
                    "carta_score":   carta_result["session_score"],
                    "carta_signals": carta_result["signals"],
                    "carta_level":   carta_result["level"],
                }
            )
            await db.commit()

            logger.info(
                f"Job submitted: job_id={job_id} "
                f"user={current_user.username} "
                f"type={job_type} "
                f"cores={params.cores} queue={params.queue}"
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


# ══════════════════════════════════════════════════════════════════════════
# STATUS
# ══════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════
# OUTPUT
# ══════════════════════════════════════════════════════════════════════════

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

    user_result = await db.execute(
        select(User).where(User.user_id == job.user_id)
    )
    job_user    = user_result.scalar_one_or_none()
    job_workdir = f"{REMOTE_JOB_DIR}/{job_user.username}/job_{job.unique_id}"

    # ── Try serial output first ────────────────────────────────
    serial_cmd = (
        f"test -f {job_workdir}/output_{job.unique_id}.log "
        f"&& tail -n 500 {job_workdir}/output_{job.unique_id}.log "
        f"|| echo 'NOT_FOUND'"
    )
    serial_out = await run_ssh_async(serial_cmd)

    if serial_out.strip() != "NOT_FOUND":
        output = serial_out
    else:
        # ── Try parallel chunk outputs ─────────────────────────
        # Collect output_{uuid}_1.log, _2.log, etc.
        chunk_cmd = (
            f"ls {job_workdir}/output_{job.unique_id}_*.log "
            f"2>/dev/null | sort -t_ -k1 -V"
        )
        chunk_files = await run_ssh_async(chunk_cmd)

        if not chunk_files.strip():
            return JobOutputResponse(
                job_id=job_id,
                output="Output not available yet. Job may still be running."
            )

        # Read each chunk file and combine
        combined = []
        for chunk_file in chunk_files.strip().splitlines():
            chunk_file = chunk_file.strip()
            if not chunk_file:
                continue
            # Extract chunk index from filename
            idx = chunk_file.split("_")[-1].replace(".log", "")
            content = await run_ssh_async(
                f"tail -n 200 {chunk_file} 2>/dev/null || echo ''"
            )
            # Strip LSF header boilerplate, keep only actual output
            marker = "The output (if any) follows:"
            if marker in content:
                content = content.split(marker, 1)[1].strip()
            if content.strip():
                combined.append(f"=== Chunk {idx} ===\n{content.strip()}")

        if not combined:
            return JobOutputResponse(
                job_id=job_id,
                output="No output produced by any chunk."
            )
        output = "\n\n".join(combined)

    # Strip LSF boilerplate from serial output
    marker = "The output (if any) follows:"
    if marker in output:
        output = output.split(marker, 1)[1].strip()

    log = AuditLog(
        user_id = current_user.user_id,
        job_id  = job_id,
        action  = "view_output"
    )
    db.add(log)
    await db.commit()

    return JobOutputResponse(job_id=job_id, output=output)
# ══════════════════════════════════════════════════════════════════════════
# ERROR LOG
# ══════════════════════════════════════════════════════════════════════════

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
    job_workdir = f"{REMOTE_JOB_DIR}/{job_user.username}/job_{job.unique_id}"

    # For parallel jobs, collect all chunk errors
    check_cmd = (
        f"ls {job_workdir}/error_{job.unique_id}_*.log 2>/dev/null && "
        f"cat {job_workdir}/error_{job.unique_id}_*.log || "
        f"test -f {job_workdir}/error_{job.unique_id}.log && "
        f"tail -n 500 {job_workdir}/error_{job.unique_id}.log || "
        f"echo 'ERROR_NOT_READY'"
    )

    error = await run_ssh_async(check_cmd)

    if error == "ERROR_NOT_READY":
        return JobErrorResponse(job_id=job_id, error="Error log not created yet.")

    await write_audit_entry(
        db         = db,
        action     = "view_error",
        result     = "success",
        user_id    = current_user.user_id,
        job_id     = job_id,
    )
    await db.commit()

    return JobErrorResponse(job_id=job_id, error=error)


# ══════════════════════════════════════════════════════════════════════════
# CANCEL
# ══════════════════════════════════════════════════════════════════════════

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

    lsf_result       = await run_ssh_async(f"{LSF_PATH}/bkill {job_id}")
    job.status       = "EXIT"
    job.cancelled_by = current_user.user_id
    job.finished_at  = datetime.now(timezone.utc)

    await write_audit_entry(
        db         = db,
        action     = "job_cancel",
        result     = "success",
        user_id    = current_user.user_id,
        job_id     = job_id,
        detail     = {"cancelled_by": current_user.username}
    )
    await db.commit()

    logger.info(f"Job cancelled: job_id={job_id}, by={current_user.username}")
    return JobCancelResponse(job_id=job_id, message="Job cancelled", result=lsf_result)


# ══════════════════════════════════════════════════════════════════════════
# LIST
# ══════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════
# CLUSTER STATE + ALLOCATION OPTIONS
# ══════════════════════════════════════════════════════════════════════════

@router.get("/cluster/state")
async def cluster_state(
    current_user: User = Depends(get_current_user),
):
    """Returns current cluster utilization and node status."""
    state = await get_cluster_state()
    return {
        "utilization":  f"{state['utilization']*100:.0f}%",
        "total_cores":  state["total_cores"],
        "free_cores":   state["free_cores"],
        "active_nodes": state["active_nodes"],
        "total_nodes":  state["total_nodes"],
        "nodes": [
            {
                "host":        n["host"],
                "free_cores":  n["free_cores"],
                "utilization": f"{n['utilization']*100:.0f}%",
                "available":   n["available"],
            }
            for n in state["nodes"] if n["available"]
        ]
    }


@router.post("/options")
async def allocation_options(
    cores:        int,
    memory:       int,
    job_type:     str  = "serial",
    current_user: User = Depends(get_current_user),
):
    """Returns allocation options based on current cluster state."""
    return await get_allocation_options(
        requested_cores  = cores,
        requested_memory = memory,
        role             = current_user.role,
        job_type         = job_type,
    )
