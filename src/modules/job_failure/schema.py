from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class JobFailureCheckRequest(BaseModel):
    organization_id: UUID
    email_recipients: List[str]
    time_window_hours: Optional[int] = 24


class FailedJobDetail(BaseModel):
    job_name: str
    run_id: str
    start_time: datetime
    error_message: Optional[str] = None
    failed_rows: Optional[int] = 0
    state: Optional[int] = None


class JobFailureCheckResponse(BaseModel):
    message: str
    organization_id: UUID
    failed_jobs_count: int
    failed_jobs: List[FailedJobDetail]
    checked_at: datetime
