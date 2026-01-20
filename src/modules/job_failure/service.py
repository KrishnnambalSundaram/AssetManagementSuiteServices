import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import and_
from sqlalchemy.orm import Session

from src.models.informatica_jobs_logs import InformaticaJobLogs
from src.models.organization import Organization
from src.modules.job_failure.schema import (
    FailedJobDetail,
    JobFailureCheckRequest,
    JobFailureCheckResponse,
)
from src.utils.notify import send_email_with_attachment

logger = logging.getLogger(__name__)


class JobFailureService:
    def __init__(self, db: Session):
        self.db = db

    def _get_organization(self, organization_id: uuid.UUID) -> Organization:
        org = self.db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            raise ValueError(f"Organization with ID {organization_id} not found")
        return org

    def check_and_notify(self, request: JobFailureCheckRequest) -> JobFailureCheckResponse:
        logger.info(f"Checking for failed jobs for organization {request.organization_id}")
        
        organization = self._get_organization(request.organization_id)
        
        # Calculate time threshold
        time_threshold = datetime.now(timezone.utc) - timedelta(hours=request.time_window_hours)
        
        # Query for failed jobs
        # Assuming state=3 indicates failure based on typical Informatica status codes
        # Also checking for error_msg presence as a fallback or additional indicator
        failed_logs = (
            self.db.query(InformaticaJobLogs)
            .filter(InformaticaJobLogs.organization_id == request.organization_id)
            .filter(InformaticaJobLogs.start_time >= time_threshold)
            .filter(
                and_(
                   InformaticaJobLogs.state == 3  # Failed state
                )
            )
            .order_by(InformaticaJobLogs.start_time.desc())
            .all()
        )
        
        failed_job_details: List[FailedJobDetail] = []
        for log in failed_logs:
            failed_job_details.append(
                FailedJobDetail(
                    job_name=log.object_name or "Unknown Job",
                    run_id=str(log.run_id),
                    start_time=log.start_time,
                    error_message=log.error_msg,
                    failed_rows=log.failed_source_rows + log.failed_target_rows if log.failed_source_rows is not None and log.failed_target_rows is not None else 0,
                    state=log.state
                )
            )
            
        if failed_job_details:
            self._send_failure_notification(organization, failed_job_details, request.email_recipients, request.time_window_hours)
            
        return JobFailureCheckResponse(
            message=f"Job failure check completed. Found {len(failed_job_details)} failed jobs.",
            organization_id=request.organization_id,
            failed_jobs_count=len(failed_job_details),
            failed_jobs=failed_job_details,
            checked_at=datetime.now(timezone.utc)
        )

    def _send_failure_notification(self, organization: Organization, failed_jobs: List[FailedJobDetail], email_recipients: List[str], time_window_hours: int) -> None:
        subject = f"Job Failure Alert: {organization.name} - {len(failed_jobs)} Failed Jobs"
        body = self._build_failure_email_body(organization, failed_jobs, time_window_hours)
        
        logger.info(f"Sending failure notification for {len(failed_jobs)} jobs to {email_recipients}")
        send_email_with_attachment(
            job_id="failure-alert",
            subject=subject,
            body=body,
            attachment_path=None,  # No attachment for now
            custom_recipients=email_recipients
        )

    def _build_failure_email_body(self, organization: Organization, failed_jobs: List[FailedJobDetail], time_window_hours: int) -> str:
        body = f"""
        <h2>Job Failure Alert - {organization.name}</h2>
        <p>The following Informatica jobs have failed in the last {time_window_hours} hours:</p>
        <table border="1" cellpadding="5" style="border-collapse: collapse;">
        <tr>
            <th>Job Name</th>
            <th>Run ID</th>
            <th>Start Time</th>
            <th>Error Message</th>
            <th>Failed Rows</th>
        </tr>
        """
        for job in failed_jobs:
            start_time_str = job.start_time.strftime('%Y-%m-%d %H:%M:%S') if job.start_time else 'N/A'
            error_msg = job.error_message or "No error message captured"
            body += f"""
            <tr>
                <td>{job.job_name}</td>
                <td>{job.run_id}</td>
                <td>{start_time_str}</td>
                <td>{error_msg}</td>
                <td>{job.failed_rows}</td>
            </tr>
            """
        body += f"""
        </table>
        <p><strong>Total Failed Jobs:</strong> {len(failed_jobs)}</p>
        <br>
        <p><em>Report generated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</em></p>
        """
        return body
