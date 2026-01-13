from sqlalchemy import Boolean, Column, String
from sqlalchemy.orm import relationship

from src.utils.database import BaseSchema


class User(BaseSchema):
    __tablename__ = "users"

    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)

    # Relationships
    job_templates = relationship("JobTemplate", back_populates="created_by_user")
    jobs = relationship("Job", back_populates="created_by_user")
    
    # Many-to-many relationship with organizations
    user_organizations = relationship("UserOrganization", back_populates="user", cascade="all, delete-orphan")
    organizations = relationship("Organization", secondary="user_organizations", viewonly=True)
