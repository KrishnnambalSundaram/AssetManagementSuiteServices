from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.utils.database import BaseSchema


class MeterUsage(BaseSchema):
    __tablename__ = "meter_usage"

    org_id = Column(String(255), nullable=False)
    meter_id = Column(String(255), nullable=False)
    meter_name = Column(String(255), nullable=True)
    usage_date = Column(DateTime(timezone=True), nullable=False)
    billing_period_start = Column(DateTime(timezone=True), nullable=True)
    billing_period_end = Column(DateTime(timezone=True), nullable=True)
    meter_usage = Column(Numeric(20, 10), nullable=True)
    ipu = Column(Numeric(20, 10), nullable=True)
    scalar = Column(String(100), nullable=True)
    metric_category = Column(String(100), nullable=True)
    org_name = Column(String(255), nullable=True)
    org_type = Column(String(100), nullable=True)
    ipu_rate = Column(Numeric(20, 10), nullable=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("metric_temp.id"), nullable=True)

    # Relationships
    metric_temp = relationship("MetricTemp", backref="meter_usages")

    # Uniqueness constraint on (meter_id, usage_date)
    __table_args__ = (
        UniqueConstraint('meter_id', 'usage_date', name='uq_meter_usage_meter_date'),
    )

