from fastapi import FastAPI
from app.routers import jobs

app = FastAPI(
    title="HPC Job Gateway",
    description="REST API for submitting and managing LSF jobs on HPC clusters",
    version="1.0.0"
)

# ==============================
# ROUTERS
# ==============================
app.include_router(jobs.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
