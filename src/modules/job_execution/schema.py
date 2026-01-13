import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class JobSummaryResponse(BaseModel):
    id: UUID
    title: str
    status: str
    trigger_type: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class JobExecutionResponse(BaseModel):
    id: UUID
    job_id: UUID
    status: str
    started_at: datetime.datetime
    completed_at: Optional[datetime.datetime] = None
    result: Optional[dict] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    job: Optional[JobSummaryResponse] = None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class JobExecutionListResponse(BaseModel):
    executions: list[JobExecutionResponse]
    total: int
    page: int
    limit: int 