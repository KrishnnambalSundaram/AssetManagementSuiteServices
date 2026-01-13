from typing import Optional, List
from datetime import datetime
import uuid
from sqlalchemy.orm import Session, joinedload
from src.models.job import Job
from src.models.job_execution import JobExecution
from src.modules.job_execution.schema import JobExecutionResponse, JobExecutionListResponse, JobSummaryResponse


class JobExecutionService:
    def __init__(self, db: Session):
        self.db = db

    def get_executions_by_job(self, job_id: str, limit: int = 5, page: int = 1) -> list[JobExecutionResponse]:
        """Get the last N executions for a specific job"""
        executions = (
            self.db.query(JobExecution)
            .options(joinedload(JobExecution.job))
            .filter(JobExecution.job_id == job_id)
            .order_by(JobExecution.started_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        
        execution_responses = []
        for execution in executions:
            execution_response = JobExecutionResponse.model_validate(execution)
            if execution.job:
                execution_response.job = JobSummaryResponse.model_validate(execution.job)
            execution_responses.append(execution_response)
        
        return execution_responses

    def get_executions(
        self, 
        page: int = 1, 
        limit: int = 100,
        organization_id: Optional[List[str]] = None,
        job_id: Optional[List[str]] = None,
        status: Optional[List[str]] = None,
        started_at_operator: Optional[str] = None,
        started_at_value: Optional[datetime] = None,
        completed_at_operator: Optional[str] = None,
        completed_at_value: Optional[datetime] = None,
        retry_count_operator: Optional[str] = None,
        retry_count_value: Optional[int] = None
    ) -> JobExecutionListResponse:
        """Get all executions with pagination and filters"""
        query = self.db.query(JobExecution).options(joinedload(JobExecution.job))
        
        # Apply organization filter (requires join)
        if organization_id:
            org_uuids = []
            for oid in organization_id:
                try:
                    org_uuids.append(uuid.UUID(oid))
                except ValueError:
                    pass
            if org_uuids:
                query = query.join(Job).filter(Job.organization_id.in_(org_uuids))
        
        # Apply job_id filter
        if job_id:
            job_uuids = []
            for jid in job_id:
                try:
                    job_uuids.append(uuid.UUID(jid))
                except ValueError:
                    pass
            if job_uuids:
                query = query.filter(JobExecution.job_id.in_(job_uuids))
        
        # Apply status filter
        if status:
            query = query.filter(JobExecution.status.in_(status))
        
        # Apply date filters with operator pattern
        if started_at_operator and started_at_value:
            if started_at_operator == 'lt':
                query = query.filter(JobExecution.started_at < started_at_value)
            elif started_at_operator == 'gt':
                query = query.filter(JobExecution.started_at > started_at_value)
            elif started_at_operator == 'lte':
                query = query.filter(JobExecution.started_at <= started_at_value)
            elif started_at_operator == 'gte':
                query = query.filter(JobExecution.started_at >= started_at_value)
            elif started_at_operator == 'eq':
                query = query.filter(JobExecution.started_at == started_at_value)
            elif started_at_operator == 'ne':
                query = query.filter(JobExecution.started_at != started_at_value)
        
        if completed_at_operator and completed_at_value:
            if completed_at_operator == 'lt':
                query = query.filter(JobExecution.completed_at < completed_at_value)
            elif completed_at_operator == 'gt':
                query = query.filter(JobExecution.completed_at > completed_at_value)
            elif completed_at_operator == 'lte':
                query = query.filter(JobExecution.completed_at <= completed_at_value)
            elif completed_at_operator == 'gte':
                query = query.filter(JobExecution.completed_at >= completed_at_value)
            elif completed_at_operator == 'eq':
                query = query.filter(JobExecution.completed_at == completed_at_value)
            elif completed_at_operator == 'ne':
                query = query.filter(JobExecution.completed_at != completed_at_value)
        
        # Apply numeric filters with operator pattern
        if retry_count_operator and retry_count_value is not None:
            if retry_count_operator == 'lt':
                query = query.filter(JobExecution.retry_count < retry_count_value)
            elif retry_count_operator == 'gt':
                query = query.filter(JobExecution.retry_count > retry_count_value)
            elif retry_count_operator == 'lte':
                query = query.filter(JobExecution.retry_count <= retry_count_value)
            elif retry_count_operator == 'gte':
                query = query.filter(JobExecution.retry_count >= retry_count_value)
            elif retry_count_operator == 'eq':
                query = query.filter(JobExecution.retry_count == retry_count_value)
            elif retry_count_operator == 'ne':
                query = query.filter(JobExecution.retry_count != retry_count_value)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply ordering and pagination
        executions = (
            query.order_by(JobExecution.started_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        
        execution_responses = []
        for execution in executions:
            execution_response = JobExecutionResponse.model_validate(execution)
            if execution.job:
                execution_response.job = JobSummaryResponse.model_validate(execution.job)
            execution_responses.append(execution_response)
        
        return JobExecutionListResponse(
            executions=execution_responses, total=total, page=page, limit=limit
        )

    def get_execution(self, execution_id: str) -> Optional[JobExecutionResponse]:
        """Get a specific execution by ID"""

        try:
            execution_uuid = uuid.UUID(execution_id)
        except Exception:
            execution_uuid = execution_id
            
        execution = (
            self.db.query(JobExecution)
            .options(joinedload(JobExecution.job))
            .filter(JobExecution.id == execution_uuid)
            .first()
        )
        
        if not execution:
            return None
            
        execution_response = JobExecutionResponse.model_validate(execution)
        if execution.job:
            execution_response.job = JobSummaryResponse.model_validate(execution.job)
        
        return execution_response 