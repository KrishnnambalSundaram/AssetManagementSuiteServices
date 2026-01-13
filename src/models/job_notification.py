from sqlalchemy import (JSON, UUID, Boolean, CheckConstraint, Column,
                        ForeignKey, String)
from sqlalchemy.orm import relationship

from src.models.base import BaseSchema


class JobNotification(BaseSchema):
    __tablename__ = "job_notifications"

    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"))
    notification_type = Column(String(20), nullable=False)
    trigger_on = Column(String(20), nullable=False)
    configuration = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "notification_type IN ('email', 'webhook', 'slack')",
            name="valid_notification_type",
        ),
        CheckConstraint(
            "trigger_on IN ('success', 'failure', 'both')", name="valid_trigger_on"
        ),
    )

    # Relationships
    job = relationship("Job", back_populates="notifications")
