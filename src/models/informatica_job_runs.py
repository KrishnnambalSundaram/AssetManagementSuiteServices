import uuid
from sqlalchemy import Column, DateTime, String, Text, func
from sqlalchemy.orm import relationship

from src.utils.database import Base, BaseSchema


class InformaticaJobRuns(Base):
    __tablename__ = "informatica_job_runs"

    id = Column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(100), nullable=False, index=True)
    status = Column(String(100), nullable=False, index=True)
    sync_perfomed_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    #relationships
    logs = relationship("InformaticaJobLogs", back_populates="job_run", cascade="all, delete-orphan")