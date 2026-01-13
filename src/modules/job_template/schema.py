import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from src.modules.user.schema import UserResponse


class JobTemplateCreate(BaseModel):
    title: str
    description: Optional[str] = None
    script_type: str = "predefined"
    script_content: Optional[str] = None
    script_path: Optional[str] = None
    parameters_schema: Optional[dict] = None
    is_active: bool = True
    organization_id: Optional[UUID] = None

    class Config:
        arbitrary_types_allowed = True


class JobTemplateUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    script_type: Optional[str] = None
    script_content: Optional[str] = None
    script_path: Optional[str] = None
    parameters_schema: Optional[dict] = None
    is_active: Optional[bool] = None
    organization_id: Optional[UUID] = None

    class Config:
        arbitrary_types_allowed = True


class JobTemplateResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    script_type: str
    script_content: Optional[str] = None
    script_path: Optional[str] = None
    parameters_schema: Optional[dict] = None
    is_active: bool
    created_by: Optional[UUID] = None
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class JobTemplateListResponse(BaseModel):
    job_templates: list[JobTemplateResponse]
    total: int
    page: int
    limit: int


class JobTemplateDetailResponse(BaseModel):
    job_template: JobTemplateResponse
    created_by: Optional[UserResponse] = None
