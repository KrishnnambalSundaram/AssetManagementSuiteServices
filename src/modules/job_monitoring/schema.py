from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class JobMonitoringRequest(BaseModel):
    job_name: str
    email_recipients: list[str]


class JobMonitoringResponse(BaseModel):
    message: str
    job_name: str
    execution_count: int
    sent_to: list[str]
    timestamp: datetime


class JobMonitoringDetailResponse(BaseModel):
    id: UUID
    title: str
    status: str
    trigger_type: str
    template: Optional[dict] = None
    organization: Optional[dict] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ExecutionDetailResponse(BaseModel):
    id: UUID
    job_id: UUID
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[dict] = None
    error_message: Optional[str] = None
    retry_count: int
