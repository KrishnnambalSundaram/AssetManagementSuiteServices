import datetime
import json
from uuid import UUID
from typing import Optional, List, Union

from pydantic import BaseModel, field_validator


class InformaticaJobRunsCreateRequest(BaseModel):
    organization_id: str


class TransformationLogEntry(BaseModel):
    id: Optional[str] = None
    tx_name: Optional[str] = None
    tx_type: Optional[str] = None
    success_rows: Optional[int] = None
    failed_rows: Optional[int] = None
    tx_instance_name: Optional[str] = None
    affected_rows: Optional[int] = None


class ActivityLogEntry(BaseModel):
    id: Optional[str] = None
    informatica_id: Optional[str] = None
    type: Optional[str] = None
    object_id: Optional[str] = None
    object_name: Optional[str] = None
    run_id: Optional[int] = None
    agent_id: Optional[str] = None
    runtime_environment_id: Optional[str] = None
    start_time: Optional[datetime.datetime] = None
    end_time: Optional[datetime.datetime] = None
    start_time_utc: Optional[datetime.datetime] = None
    end_time_utc: Optional[datetime.datetime] = None
    state: Optional[int] = None
    ui_state: Optional[int] = None
    failed_source_rows: Optional[int] = None
    success_source_rows: Optional[int] = None
    failed_target_rows: Optional[int] = None
    success_target_rows: Optional[int] = None
    error_msg: Optional[str] = None
    started_by: Optional[str] = None
    run_context_type: Optional[str] = None
    entries: Optional[List['ActivityLogEntry']] = []
    sub_task_entries: Optional[List['ActivityLogEntry']] = []
    log_entry_item_attrs: Optional[dict] = None
    session_variables: Optional[dict] = None
    total_success_rows: Optional[int] = None
    total_failed_rows: Optional[int] = None
    stop_on_error: Optional[bool] = None
    has_stop_on_error_record: Optional[bool] = None
    context_external_id: Optional[str] = None
    is_stopped: Optional[bool] = None
    transformation_entries: Optional[List[TransformationLogEntry]] = []


# Update forward reference
ActivityLogEntry.model_rebuild()


class InformaticaJobLogsResponse(BaseModel):
    id: Optional[str] = None
    job_run_id: Optional[UUID] = None
    
    # Core activity log entry fields
    informatica_id: Optional[str] = None
    type: Optional[str] = None
    object_id: Optional[str] = None
    object_name: Optional[str] = None
    run_id: Optional[int] = None
    
    # Timestamps
    start_time: Optional[datetime.datetime] = None
    end_time: Optional[datetime.datetime] = None
    start_time_utc: Optional[datetime.datetime] = None
    end_time_utc: Optional[datetime.datetime] = None
    
    # State and status
    state: Optional[int] = None
    ui_state: Optional[int] = None
    
    # Row processing statistics
    failed_source_rows: Optional[int] = None
    success_source_rows: Optional[int] = None
    failed_target_rows: Optional[int] = None
    success_target_rows: Optional[int] = None
    
    # Execution context
    started_by: Optional[str] = None
    run_context_type: Optional[str] = None
    
    # Agent and runtime information
    agent_id: Optional[str] = None
    runtime_environment_id: Optional[str] = None
    
    # Error handling
    error_msg: Optional[str] = None
    stop_on_error: Optional[bool] = None
    has_stop_on_error_record: Optional[bool] = None
    is_stopped: Optional[bool] = None
    
    # Context and external references
    context_external_id: Optional[str] = None
    
    # Additional metadata
    total_success_rows: Optional[int] = None
    total_failed_rows: Optional[int] = None
    
    # Nested data structures
    entries: Optional[List[ActivityLogEntry]] = []
    sub_task_entries: Optional[List[ActivityLogEntry]] = []
    transformation_entries: Optional[List[TransformationLogEntry]] = []
    log_entry_item_attrs: Optional[dict] = None
    session_variables: Optional[dict] = None
    
    # Session log data (text response from sessionLog endpoint)
    log_data: Optional[str] = None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class InformaticaJobRunsResponse(BaseModel):
    id: str
    organization_id: str
    status: str
    sync_perfomed_at: datetime.datetime
    completed_at: Optional[datetime.datetime] = None
    error_message: Optional[str] = None
    logs: Optional[List[InformaticaJobLogsResponse]] = []

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class InformaticaJobRunsListResponse(BaseModel):
    job_runs: List[InformaticaJobRunsResponse]
    total: int
    page: int
    limit: int 