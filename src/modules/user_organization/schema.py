import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class UserOrganizationCreate(BaseModel):
    user_id: UUID
    organization_id: UUID
    role: str = "member"  # 'admin', 'member', 'viewer'
    is_active: bool = True


class UserOrganizationUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserOrganizationResponse(BaseModel):
    id: UUID
    user_id: UUID
    organization_id: UUID
    role: str
    is_active: bool
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class UserOrganizationListResponse(BaseModel):
    user_organizations: list[UserOrganizationResponse]
    total: int
    page: int
    limit: int


class UserOrganizationMappingRequest(BaseModel):
    organization_ids: list[UUID]
    role: str = "member"
    is_active: bool = True


class UserOrganizationMappingResponse(BaseModel):
    user_id: UUID
    organizations: list[UserOrganizationResponse]
    total: int
