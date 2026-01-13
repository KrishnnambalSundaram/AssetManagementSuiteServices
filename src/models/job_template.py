from sqlalchemy import JSON, UUID, Boolean, Column, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from src.utils.database import BaseSchema


class JobTemplate(BaseSchema):
    __tablename__ = "job_templates"

    title = Column(String(100), nullable=False)
    description = Column(Text)
    script_type = Column(String(20), default="predefined")
    script_content = Column(Text)
    script_path = Column(String(255))
    parameters_schema = Column(JSON)
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))

    # Relationships
    created_by_user = relationship("User", back_populates="job_templates")
    organization = relationship("Organization", back_populates="job_templates")
    jobs = relationship("Job", back_populates="template")
