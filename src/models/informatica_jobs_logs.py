import uuid
from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.types import UUID

from src.utils.database import Base, BaseSchema


class InformaticaJobLogs(Base):
    __tablename__ = "informatica_jobs_logs"
    __table_args__ = (
        UniqueConstraint('object_id', 'run_id', 'organization_id', name='uq_informatica_jobs_logs_object_run_org'),
    )

    id = Column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_run_id = Column(String(100), ForeignKey("informatica_job_runs.id"), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Core activity log entry fields
    informatica_id = Column(String(150), nullable=True, index=True)
    type = Column(String(100), nullable=True, index=True)  # e.g., "MTT_TEST"
    object_id = Column(String(100), nullable=True, index=True)
    object_name = Column(String(100), nullable=True, index=True)
    run_id = Column(Integer, nullable=True, index=True)
    
    # Timestamps
    start_time = Column(DateTime, nullable=True, index=True)
    end_time = Column(DateTime, nullable=True, index=True)
    start_time_utc = Column(DateTime, nullable=True, index=True)
    end_time_utc = Column(DateTime, nullable=True, index=True)
    
    # State and status
    state = Column(Integer, nullable=True, index=True)
    ui_state = Column(Integer, nullable=True, index=True)
    
    # Row processing statistics
    failed_source_rows = Column(Integer, nullable=True, default=0)
    success_source_rows = Column(Integer, nullable=True, default=0)
    failed_target_rows = Column(Integer, nullable=True, default=0)
    success_target_rows = Column(Integer, nullable=True, default=0)
    
    # Execution context
    started_by = Column(String(255), nullable=True, index=True)
    run_context_type = Column(String(100), nullable=True, index=True)
    
    # Agent and runtime information
    agent_id = Column(String(100), nullable=True, index=True)
    runtime_environment_id = Column(String(100), nullable=True, index=True)
    
    # Error handling
    error_msg = Column(Text, nullable=True)
    stop_on_error = Column(Boolean, nullable=True, default=False)
    has_stop_on_error_record = Column(Boolean, nullable=True, default=False)
    is_stopped = Column(Boolean, nullable=True, default=False)
    
    # Context and external references
    context_external_id = Column(String(100), nullable=True, index=True)
    
    # Additional metadata
    total_success_rows = Column(Integer, nullable=True, default=0)
    total_failed_rows = Column(Integer, nullable=True, default=0)
    
    # Nested data structures
    entries = Column(JSON, nullable=True)  # Nested activity log entries
    sub_task_entries = Column(JSON, nullable=True)  # Sub-task entries
    transformation_entries = Column(JSON, nullable=True)  # Transformation log entries
    log_entry_item_attrs = Column(JSON, nullable=True)  # Log entry item attributes
    session_variables = Column(JSON, nullable=True)  # Session variables
    log_data = Column(Text, nullable=True)

    # Relationships
    job_run = relationship("InformaticaJobRuns", back_populates="logs")
    organization = relationship("Organization", back_populates="job_logs")

