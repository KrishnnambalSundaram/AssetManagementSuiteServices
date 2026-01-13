import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class OrganizationCreate(BaseModel):
    name: str
    description: Optional[str] = None
    domain: str
    configuration: Optional[dict] = None
    identifier: str
    username: str
    password: str
    environment: str
    is_active: bool = True


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    domain: Optional[str] = None
    is_active: Optional[bool] = None
    configuration: Optional[dict] = None
    identifier: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    environment: Optional[str] = None


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    configuration: Optional[dict] = None
    username: Optional[str] = None
    password: Optional[str] = None
    environment: Optional[str] = None
    identifier: Optional[str] = None
    domain: str
    is_active: bool
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class OrganizationListResponse(BaseModel):
    organizations: list[OrganizationResponse]
    total: int
    page: int
    limit: int


class OrganizationDetailResponse(BaseModel):
    organization: OrganizationResponse
    created_by: Optional[str] = None
    updated_by: Optional[str] = None 