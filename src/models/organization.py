from sqlalchemy import JSON, Boolean, Column, String, Text
from sqlalchemy.orm import relationship

from src.utils.database import BaseSchema


class Organization(BaseSchema):
    __tablename__ = "organizations"

    name = Column(String(100), nullable=False, index=True)
    description = Column(Text)
    domain = Column(String(100), index=True)
    identifier = Column(String(100), index=True)
    is_active = Column(Boolean, default=True)
    username = Column(String(100), index=True)
    password = Column(String(100))
    environment = Column(String(100))
    configuration = Column(JSON)
    
    # Relationships
    job_templates = relationship("JobTemplate", back_populates="organization")
    jobs = relationship("Job", back_populates="organization")
    
    # Many-to-many relationship with users
    user_organizations = relationship("UserOrganization", back_populates="organization", cascade="all, delete-orphan")
    users = relationship("User", secondary="user_organizations", viewonly=True)
    
    # One-to-many relationship with job logs
    job_logs = relationship("InformaticaJobLogs", back_populates="organization") 