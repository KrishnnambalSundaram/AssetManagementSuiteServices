# app/models/job.py
from sqlalchemy import (JSON, UUID, CheckConstraint, Column, DateTime,
                        ForeignKey, Integer, String)
from sqlalchemy.orm import relationship

from src.models.base import BaseSchema


class Job(BaseSchema):
    __tablename__ = "jobs"

    title = Column(String(100), nullable=False)
    template_id = Column(UUID(as_uuid=True), ForeignKey("job_templates.id"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))

    # Job parameters
    parameters = Column(JSON, default={})

    # Status
    status = Column(String(20), default="running")

    # Trigger configuration
    trigger_type = Column(String(20), nullable=False)

    # Frequency trigger
    frequency_interval = Column(Integer)
    frequency_unit = Column(String(10))
    frequency_count = Column(Integer)
    frequency_end_time = Column(DateTime(timezone=True))

    # Cron trigger
    cron_expression = Column(String(100))

    # Execution tracking
    timeout_seconds = Column(Integer, default=300)
    max_retries = Column(Integer, default=3)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "trigger_type IN ('manual', 'frequency', 'cron')", name="valid_trigger_type"
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'paused')",
            name="valid_status",
        ),
        CheckConstraint(
            "frequency_unit IN ('seconds', 'minutes', 'hours', 'days', 'weeks', 'months', 'years') OR frequency_unit IS NULL",
            name="valid_frequency_unit",
        ),
    )

    # Relationships
    template = relationship("JobTemplate", back_populates="jobs")
    created_by_user = relationship("User", back_populates="jobs")
    organization = relationship("Organization", back_populates="jobs")
    executions = relationship(
        "JobExecution", back_populates="job", cascade="all, delete-orphan"
    )
    notifications = relationship(
        "JobNotification", back_populates="job", cascade="all, delete-orphan"
    )
