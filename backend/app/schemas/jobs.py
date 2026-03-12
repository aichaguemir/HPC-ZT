from pydantic import BaseModel
from enum import Enum


class JobStatus(str, Enum):
    PEND    = "PEND"
    RUN     = "RUN"
    DONE    = "DONE"
    EXIT    = "EXIT"
    UNKNOWN = "UNKNOWN"


class JobResponse(BaseModel):
    job_id:      str
    status:      str
    output_file: str
    error_file:  str
    wall_time:   str


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
