from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel


class JobNotificationCreate(BaseModel):
    job_id: UUID
    notification_type: str
    trigger_on: str
    configuration: dict
    is_active: bool = True

    class Config:
        arbitrary_types_allowed = True


class JobNotificationUpdate(BaseModel):
    job_id: Optional[UUID] = None
    notification_type: Optional[str] = None
    trigger_on: Optional[str] = None
    configuration: Optional[dict] = None
    is_active: Optional[bool] = None

    class Config:
        arbitrary_types_allowed = True


class JobNotificationResponse(BaseModel):
    id: UUID
    job_id: Optional[UUID] = None
    notification_type: str
    trigger_on: str
    configuration: dict
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class JobNotificationListResponse(BaseModel):
    notifications: List[JobNotificationResponse]
    total: int
    page: int
    limit: int

    class Config:
        arbitrary_types_allowed = True
