from fastapi import FastAPI
app = FastAPI(title="HPC Portal API")

@app.get("/")
def root():
    return {"message": "HPC Portal is running!", "status": "ok"}

@app.get("/api/status")
def status():
    return {"api": "online", "version": "1.0"}

@app.get("/api/jobs")
def jobs():
    return {"jobs": [], "message": "Job list endpoint"}
