from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum
from typing import Any


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
    job_id: str
    status: str
    queue:  str
    cores:  str


class JobCancelResponse(BaseModel):
    job_id:  str
    message: str
    result:  str


class JobOutputResponse(BaseModel):
    job_id: str
    output: str


class JobErrorResponse(BaseModel):
    job_id: str
    error:  str


class JobSubmitParams(BaseModel):
    cores:             int
    memory:            int
    queue:             str
    wall_time_hours:   int
    wall_time_minutes: int
    policy:            Any = None  # Policy object from DB

    @model_validator(mode='after')
    def validate_against_policy(self):
        p = self.policy
        if p is None:
            return self

        if self.cores <= 0:
            raise ValueError("Cores must be greater than 0")
        if self.cores > p.max_cores_per_job:
            raise ValueError(f"Max {p.max_cores_per_job} cores for your role")

        if self.memory < 100:
            raise ValueError("Minimum memory is 100MB")
        if self.memory > p.max_memory_mb:
            raise ValueError(f"Max {p.max_memory_mb}MB for your role")

        total_minutes = self.wall_time_hours * 60 + self.wall_time_minutes
        if total_minutes < 1:
            raise ValueError("Minimum wall time is 1 minute")
        if total_minutes > p.max_wall_time_hours * 60:
            raise ValueError(f"Max wall time is {p.max_wall_time_hours}h for your role")

        if self.wall_time_minutes < 0 or self.wall_time_minutes > 59:
            raise ValueError("Wall time minutes must be 0-59")

        return self
