from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class JobSkipCheckRequest(BaseModel):
    organization_id: str
    email_recipients: list[str]
    time_window_hours: int = 24


class JobSkipCheckResponse(BaseModel):
    message: str
    organization_id: str
    missed_jobs_count: int
    checked_at: datetime


class MissedJobDetail(BaseModel):
    job_name: str
    object_id: str
    last_run_time: Optional[datetime] = None
    expected_run_time: Optional[datetime] = None
    skip_reason: str


class JobSkipDetailResponse(BaseModel):
    missed_jobs: list[MissedJobDetail]
    total_jobs_checked: int
    report_generated_at: datetime
