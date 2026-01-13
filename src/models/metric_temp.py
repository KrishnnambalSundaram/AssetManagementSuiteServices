from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.utils.database import BaseSchema


class MetricTemp(BaseSchema):
    __tablename__ = "metric_temp"

    internal_job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    export_job_id = Column(String(255), nullable=True)
    frequency = Column(String(20), nullable=False)  # 'daily', 'weekly', 'monthly'
    change_threshold = Column(Numeric(10, 2), nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), default="pending")  # 'pending', 'processing', 'completed', 'failed'

    # Relationships
    job = relationship("Job", backref="metric_temp_jobs")

