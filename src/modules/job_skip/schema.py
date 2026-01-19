from datetime import datetime
from typing import Optional, Any, Dict
from uuid import UUID

from pydantic import BaseModel


class JobSkipCheckRequest(BaseModel):
    organization_id: str
    email_recipients: list[str]
    time_window_hours: int = 24
    use_custom_mapping: bool = False
    custom_mapping_field: Optional[str] = None


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


class InformaticaSchedule(BaseModel):
    id: str
    scheduleFederatedId: str
    name: str
    status: str
    description: Optional[str] = None
    interval: str
    frequency: Optional[int] = None
    startTime: Optional[datetime] = None
    endTime: Optional[datetime] = None
    timeZoneId: Optional[str] = None
    mon: bool = False
    tue: bool = False
    wed: bool = False
    thu: bool = False
    fri: bool = False
    sat: bool = False
    sun: bool = False


class InformaticaScheduleResponse(BaseModel):
    message: str
    organization_id: str
    schedules_count: int
    schedules: list[InformaticaSchedule]
    fetched_at: datetime
