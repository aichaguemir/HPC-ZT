from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.routers import jobs
from app.routers import auth as auth_router
from app.db.session import engine, AsyncSessionLocal
from app.db.models import Base, Policy, PolicyQueue
from app.core.logging import logger
from sqlalchemy import select


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed policies if empty
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(Policy))
        if existing.scalars().first() is None:
            policies = [
                Policy(role="student",    max_cores_per_job=4,
                       max_memory_mb=4096,  max_wall_time_hours=4,
                       max_concurrent_jobs=2, max_file_size_mb=5,
                       max_jobs_per_day=5),
                Policy(role="researcher", max_cores_per_job=16,
                       max_memory_mb=31900, max_wall_time_hours=24,
                       max_concurrent_jobs=5, max_file_size_mb=10),
                Policy(role="admin",      max_cores_per_job=16,
                       max_memory_mb=31900, max_wall_time_hours=24,
                       max_concurrent_jobs=20, max_file_size_mb=50),
            ]
            for p in policies:
                db.add(p)
            await db.flush()

            queue_map = {
                "student":    ["low_priority"],
                "researcher": ["low_priority", "medium_priority", "high_priority"],
                "admin":      ["low_priority", "medium_priority", "high_priority"],
            }
            for p in policies:
                for q in queue_map[p.role]:
                    db.add(PolicyQueue(policy_id=p.policy_id, queue_name=q))

            await db.commit()
            logger.info("Policies seeded successfully")

    logger.info("Application startup complete")
    yield
    logger.info("Application shutting down")


app = FastAPI(
    title="HPC Job Gateway",
    description="Secure REST API for submitting jobs to LSF HPC clusters",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(jobs.router,        prefix="/api/v1")
app.include_router(auth_router.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
