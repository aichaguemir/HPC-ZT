from pydantic import BaseModel
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator
from app.core.config import (
    MAX_CORES_PER_JOB, MAX_MEMORY_MB, MIN_MEMORY_MB,
    MAX_WALL_TIME_HOURS, MIN_WALL_TIME_MINUTES, VALID_QUEUES
)


class JobStatus(str, Enum):
    PEND    = "PEND"
    RUN     = "RUN"
    DONE    = "DONE"
    EXIT    = "EXIT"
    UNKNOWN = "UNKNOWN"


class JobResponse(BaseModel):
    job_id:          str
    status:          str
    output_file:     str
    error_file:      str
    wall_time:       str
    script_filename: str    
    cores:           int    
    memory:          int    
    queue:           str   


class JobStatusResponse(BaseModel):
    job_id:    str
    status:    str
    queue:     str
    cores:     str


class JobCancelResponse(BaseModel):
    job_id:  str
    message: str
    result:  str


class JobOutputResponse(BaseModel):
    job_id:  str
    output:  str


class JobErrorResponse(BaseModel):
    job_id: str
    error:  str
    
class JobSubmitParams(BaseModel):
    cores:             int = Field(..., gt=0,          le=MAX_CORES_PER_JOB,
                           description=f"CPU cores 1-{MAX_CORES_PER_JOB}")
    memory:            int = Field(..., ge=MIN_MEMORY_MB, le=MAX_MEMORY_MB,
                           description=f"Memory MB {MIN_MEMORY_MB}-{MAX_MEMORY_MB}")
    queue:             str = Field(...,
                           description=f"One of: {', '.join(VALID_QUEUES)}")
    wall_time_hours:   int = Field(..., ge=0, le=MAX_WALL_TIME_HOURS)
    wall_time_minutes: int = Field(..., ge=0, le=59)

    @field_validator('queue')
    @classmethod
    def queue_must_be_valid(cls, v):
        if v.strip().lower() not in VALID_QUEUES:
            raise ValueError(
                f"Invalid queue! Valid queues: {', '.join(VALID_QUEUES)}"
            )
        return v.strip().lower()

    @model_validator(mode='after')
    def validate_wall_time_total(self):
        total = self.wall_time_hours * 60 + self.wall_time_minutes
        if total < MIN_WALL_TIME_MINUTES:
            raise ValueError("Minimum wall time is 1 minute!")
        if total > MAX_WALL_TIME_HOURS * 60:
            raise ValueError(
                f"Maximum wall time is {MAX_WALL_TIME_HOURS} hours!"
            )
        return self
    
