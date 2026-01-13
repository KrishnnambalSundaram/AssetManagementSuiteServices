import uuid

from sqlalchemy import (JSON, UUID, CheckConstraint, Column, DateTime,
                        ForeignKey, Integer, String, Text)
from sqlalchemy.orm import relationship

from src.utils.database import Base


class JobExecution(Base):
    __tablename__ = "job_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"))

    # Execution details
    status = Column(String(20), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True))

    # Results and logs
    result = Column(JSON)
    error_message = Column(Text)

    # Retry information
    retry_count = Column(Integer, default=0)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'timeout', 'cancelled')",
            name="valid_execution_status",
        ),
    )

    # Relationships
    job = relationship("Job", back_populates="executions")
