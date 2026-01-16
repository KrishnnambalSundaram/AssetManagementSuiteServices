import logging
from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy.orm import Session, joinedload

from src.models.job import Job
from src.models.job_execution import JobExecution
from src.modules.job_monitoring.schema import (ExecutionDetailResponse,
                                               JobMonitoringDetailResponse,
                                               JobMonitoringResponse,
                                               JobMonitoringRequest)
from src.utils.notify import send_email_with_attachment

logger = logging.getLogger(__name__)


class JobMonitoringService:
    def __init__(self, db: Session):
        self.db = db

    def monitor_job(self, request: JobMonitoringRequest) -> JobMonitoringResponse:
        job = self.db.query(Job).filter(Job.title == request.job_name).first()
        
        if not job:
            raise ValueError(f"Job with name '{request.job_name}' not found")
        
        executions = (
            self.db.query(JobExecution)
            .filter(JobExecution.job_id == job.id)
            .order_by(JobExecution.started_at.desc())
            .all()
        )
        
        job_detail = self._build_job_detail(job)
        execution_details = [self._build_execution_detail(e) for e in executions]
        
        email_subject = f"Job Monitoring Report: {request.job_name}"
        email_body = self._build_email_body(job_detail, execution_details)
        
        logger.info(f"Sending monitoring report for job '{request.job_name}' to {request.email_recipients}")
        send_email_with_attachment(
            job_id=str(job.id),
            subject=email_subject,
            body=email_body,
            attachment_path=None
        )
        
        return JobMonitoringResponse(
            message=f"Job monitoring report sent successfully",
            job_name=request.job_name,
            execution_count=len(executions),
            sent_to=request.email_recipients,
            timestamp=datetime.now()
        )

    def get_job_details_by_name(self, job_name: str) -> Optional[JobMonitoringDetailResponse]:
        job = (
            self.db.query(Job)
            .options(joinedload(Job.template), joinedload(Job.organization))
            .filter(Job.title == job_name)
            .first()
        )
        
        if not job:
            return None
        
        return self._build_job_detail(job)

    def get_job_executions_by_name(self, job_name: str, limit: int = 10) -> list[ExecutionDetailResponse]:
        job = self.db.query(Job).filter(Job.title == job_name).first()
        
        if not job:
            return []
        
        executions = (
            self.db.query(JobExecution)
            .filter(JobExecution.job_id == job.id)
            .order_by(JobExecution.started_at.desc())
            .limit(limit)
            .all()
        )
        
        return [self._build_execution_detail(e) for e in executions]

    def _build_job_detail(self, job: Job) -> JobMonitoringDetailResponse:
        job_dict = {
            "id": job.id,
            "title": job.title,
            "status": job.status,
            "trigger_type": job.trigger_type,
            "template": {
                "id": job.template.id,
                "title": job.template.title,
                "script_type": job.template.script_type,
                "script_path": job.template.script_path
            } if job.template else None,
            "organization": {
                "id": job.organization.id,
                "name": job.organization.name
            } if job.organization else None,
            "created_at": job.created_at,
            "updated_at": job.updated_at
        }
        return JobMonitoringDetailResponse(**job_dict)

    def _build_execution_detail(self, execution: JobExecution) -> ExecutionDetailResponse:
        return ExecutionDetailResponse.model_validate(execution)

    def _build_email_body(self, job_detail: JobMonitoringDetailResponse, executions: list[ExecutionDetailResponse]) -> str:
        body = f"""
<h2>Job Monitoring Report</h2>
<h3>Job Details</h3>
<table border="1" cellpadding="5" style="border-collapse: collapse;">
<tr><td><strong>Title:</strong></td><td>{job_detail.title}</td></tr>
<tr><td><strong>Status:</strong></td><td>{job_detail.status}</td></tr>
<tr><td><strong>Trigger Type:</strong></td><td>{job_detail.trigger_type}</td></tr>
<tr><td><strong>Created At:</strong></td><td>{job_detail.created_at.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
"""
        
        if job_detail.template:
            body += f"""<tr><td><strong>Template:</strong></td><td>{job_detail.template.get('title')} ({job_detail.template.get('script_type')})</td></tr>"""
        
        if job_detail.organization:
            body += f"""<tr><td><strong>Organization:</strong></td><td>{job_detail.organization.get('name')}</td></tr>"""
        
        body += "</table>"
        
        if executions:
            body += f"""
<h3>Recent Executions (Last {len(executions)})</h3>
<table border="1" cellpadding="5" style="border-collapse: collapse;">
<tr>
    <th>Execution ID</th>
    <th>Status</th>
    <th>Started At</th>
    <th>Completed At</th>
    <th>Retry Count</th>
    <th>Error Message</th>
</tr>
"""
            for exec in executions:
                completed = exec.completed_at.strftime('%Y-%m-%d %H:%M:%S') if exec.completed_at else 'N/A'
                error = exec.error_message if exec.error_message else 'None'
                body += f"""
<tr>
    <td>{str(exec.id)[:8]}...</td>
    <td>{exec.status}</td>
    <td>{exec.started_at.strftime('%Y-%m-%d %H:%M:%S')}</td>
    <td>{completed}</td>
    <td>{exec.retry_count}</td>
    <td>{error}</td>
</tr>
"""
            body += "</table>"
        
        body += f"""
<br>
<p><em>Report generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</em></p>
"""
        
        return body
