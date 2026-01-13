import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    is_active: bool = True


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    is_active: bool
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class UserWithOrganizationsResponse(BaseModel):
    id: UUID
    username: str
    email: str
    is_active: bool
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None
    organizations: Optional[list] = None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class UserOrganizationDetail(BaseModel):
    id: str
    organization_id: str
    organization_name: str
    organization_domain: str
    organization_identifier: str
    role: str
    is_active: bool
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class UserWithOrganizationsDetailResponse(BaseModel):
    id: UUID
    username: str
    email: str
    is_active: bool
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None
    organizations: list[UserOrganizationDetail]

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
    page: int
    limit: int


class UserDetailResponse(BaseModel):
    user: UserResponse
    created_by: Optional[UserResponse] = None
    updated_by: Optional[UserResponse] = None
