import datetime
from typing import Optional, Union
from uuid import UUID

from pydantic import BaseModel

from src.modules.organization.schema import OrganizationResponse
from src.modules.job_notification.schema import JobNotificationResponse
from src.modules.job_template.schema import JobTemplateResponse
from src.modules.user.schema import UserResponse
from src.modules.job_execution.schema import JobExecutionResponse


class JobCreate(BaseModel):
    title: str
    template_id: Union[UUID, str]
    parameters: dict = {}
    status: str = "running"
    trigger_type: str = "manual"
    frequency_interval: Optional[int] = None
    frequency_unit: Optional[str] = None
    frequency_count: Optional[int] = None
    frequency_end_time: Optional[datetime.datetime] = None
    cron_expression: Optional[str] = None
    timeout_seconds: Optional[int] = None
    max_retries: Optional[int] = None
    organization_id: UUID
    trigger_on: Optional[str] = 'both'

    class Config:
        arbitrary_types_allowed = True


class JobUpdate(BaseModel):
    title: Optional[str] = None
    parameters: Optional[dict] = None
    status: Optional[str] = None
    trigger_type: Optional[str] = None
    frequency_interval: Optional[int] = None
    frequency_unit: Optional[str] = None
    frequency_count: Optional[int] = None
    frequency_end_time: Optional[datetime.datetime] = None
    cron_expression: Optional[str] = None
    timeout_seconds: Optional[int] = None
    max_retries: Optional[int] = None
    trigger_on: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True


class JobResponse(BaseModel):
    id: UUID
    title: str
    template_id: UUID
    organization_id: Optional[UUID] = None
    parameters: dict
    status: str
    trigger_type: str
    frequency_interval: Optional[int] = None
    frequency_unit: Optional[str] = None
    frequency_count: Optional[int] = None
    frequency_end_time: Optional[datetime.datetime] = None
    cron_expression: Optional[str] = None
    timeout_seconds: Optional[int] = None
    max_retries: Optional[int] = None
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None
    template: Optional[JobTemplateResponse] = None
    notifications: Optional[list[JobNotificationResponse]] = None
    organization: Optional[OrganizationResponse] = None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    page: int
    limit: int


class JobDetailResponse(BaseModel):
    job: JobResponse
    template: Optional[JobTemplateResponse] = None
    created_by: Optional[UserResponse] = None
    updated_by: Optional[UserResponse] = None
