import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles 
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.routers import jobs
from app.routers import auth as auth_router
from app.routers import admin as admin_router
from app.db.session import engine, AsyncSessionLocal
from app.db.models import Base, Policy, PolicyQueue, Job
from app.services.ssh import run_ssh_async
from app.core.config import LSF_PATH
from app.core.logging import logger
from fastapi.middleware.cors import CORSMiddleware
from app.routers import messages as messages_router

# ══════════════════════════════════════════════════════════════
# BACKGROUND TASK — Job Status Sync (FIXED)
# ══════════════════════════════════════════════════════════════

async def sync_job_statuses():
    """
    Runs every 5 minutes:
    - Syncs job status with LSF
    - Cleans pending jobs
    - Expires stuck jobs
    """
    await asyncio.sleep(10)

    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Job).where(Job.status.in_(["PEND", "RUN"]))
                )
                active_jobs = result.scalars().all()

                if not active_jobs:
                    await asyncio.sleep(300)
                    continue

                now = datetime.now(timezone.utc)

                # ① CLEAN pending_ jobs FIRST
                for job in active_jobs:
                    if job.job_id.startswith("pending_"):
                        age = now - job.submitted_at
                        if age > timedelta(minutes=10):
                            job.status = "EXIT"
                            job.finished_at = now
                            logger.warning(f"Pending job expired: {job.job_id}")

                await db.commit()

                # ② Prepare real LSF jobs
                real_jobs = [
                    j for j in active_jobs
                    if not j.job_id.startswith("pending_")
                ]

                if not real_jobs:
                    await asyncio.sleep(300)
                    continue

                job_ids_str = " ".join(j.job_id for j in real_jobs)

                # ③ Query LSF
                lsf_result = await run_ssh_async(
                    f"{LSF_PATH}/bjobs {job_ids_str} 2>/dev/null || true"
                )

                # ④ Parse safely
                status_map = {}
                lines = lsf_result.strip().splitlines()
                if len(lines) >= 2:
                    for line in lines[1:]:
                        parts = line.split()
                        if len(parts) >= 3:
                            status_map[parts[0]] = parts[2]

                # ⑤ Update jobs
                updated = 0
                for job in real_jobs:
                    age = now - job.submitted_at
                    if job.status in ("PEND", "RUN") and age > timedelta(hours=2):
                        job.status = "EXIT"
                        job.finished_at = now
                        updated += 1
                        logger.warning(f"Job force-expired: {job.job_id}")
                        continue

                    lsf_status = status_map.get(job.job_id)
                    if lsf_status:
                        if job.status != lsf_status:
                            job.status = lsf_status
                            updated += 1
                        if lsf_status in ("DONE", "EXIT"):
                            job.finished_at = now
                    else:
                        if age > timedelta(minutes=30):
                            job.status = "DONE"
                            job.finished_at = now
                            updated += 1
                            logger.info(f"Job auto-completed: {job.job_id}")

                # ⑥ Commit
                await db.commit()
                logger.info(
                    f"Job sync | total={len(active_jobs)} updated={updated} "
                    f"time={now.isoformat()}"
                )

        except Exception as e:
            logger.error(f"Job sync error: {e}", exc_info=True)

        await asyncio.sleep(300)


# ══════════════════════════════════════════════════════════════
# LIFESPAN
# ══════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── DB INIT ───────────────────────────────────────────────
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ── Seed policies ─────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(Policy))
        if existing.scalars().first() is None:
            policies = [
                Policy(role="student", max_cores_per_job=4, max_memory_mb=4096,
                       max_wall_time_hours=4, max_concurrent_jobs=2,
                       max_file_size_mb=5, max_jobs_per_day=5),
                Policy(role="researcher", max_cores_per_job=16, max_memory_mb=31900,
                       max_wall_time_hours=24, max_concurrent_jobs=5,
                       max_file_size_mb=10),
                Policy(role="admin", max_cores_per_job=16, max_memory_mb=31900,
                       max_wall_time_hours=24, max_concurrent_jobs=20,
                       max_file_size_mb=50),
            ]

            for p in policies:
                db.add(p)

            await db.flush()

            queue_map = {
                "student": ["low_priority"],
                "researcher": ["low_priority", "medium_priority", "high_priority"],
                "admin": ["low_priority", "medium_priority", "high_priority"],
            }

            for p in policies:
                for q in queue_map[p.role]:
                    db.add(PolicyQueue(policy_id=p.policy_id, queue_name=q))

            await db.commit()
            logger.info("Policies seeded")

    # ── Start background worker ───────────────────────────────
    task = asyncio.create_task(sync_job_statuses())
    logger.info("Background sync started")

    yield

    # ── Shutdown ─────────────────────────────────────────────
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Background task stopped")


# ══════════════════════════════════════════════════════════════
# APP
# ══════════════════════════════════════════════════════════════

app = FastAPI(
    title="HPC Job Gateway",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "https://localhost",
        "http://127.0.0.1",
        "https://127.0.0.1"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files (Uploads) ───────────────────────────────────
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ── Routers ──────────────────────────────────────────────────
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(admin_router.router, prefix="/api/v1")
app.include_router(messages_router.router, prefix="/api/v1")


# ── Health check ──────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "hpc-backend",
        "version": "1.0.0"
    }
