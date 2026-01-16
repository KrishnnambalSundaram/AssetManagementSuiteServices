import logging
from datetime import datetime, timedelta
from typing import Optional
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from src.models.job import Job
from src.models.job_execution import JobExecution
from src.models.informatica_jobs_logs import InformaticaJobLogs
from src.models.organization import Organization
from src.modules.job_skip.schema import (JobSkipCheckRequest,
                                       JobSkipCheckResponse,
                                       JobSkipDetailResponse,
                                       MissedJobDetail)
from src.utils.notify import send_email_with_attachment

logger = logging.getLogger(__name__)


class JobSkipService:
    def __init__(self, db: Session):
        self.db = db

    def check_job_skips(self, request: JobSkipCheckRequest) -> JobSkipCheckResponse:
        logger.info(f"Checking job skips for organization {request.organization_id}")
        
        org = self.db.query(Organization).filter(Organization.id == uuid.UUID(request.organization_id)).first()
        if not org:
            raise ValueError(f"Organization with ID {request.organization_id} not found")
        
        try:
            org_uuid = uuid.UUID(request.organization_id)
        except ValueError:
            raise ValueError(f"Invalid organization ID format: {request.organization_id}")
        
        skipped_jobs = self._identify_skipped_jobs(org_uuid, request.time_window_hours)
        
        if skipped_jobs:
            self._send_skip_notification(org, skipped_jobs, request.email_recipients)
        
        return JobSkipCheckResponse(
            message=f"Job skip check completed. Found {len(skipped_jobs)} skipped jobs.",
            organization_id=request.organization_id,
            missed_jobs_count=len(skipped_jobs),
            checked_at=datetime.now()
        )

    def _identify_skipped_jobs(self, organization_id: uuid.UUID, time_window_hours: int) -> list[MissedJobDetail]:
        missed_jobs = []
        
        time_threshold = datetime.now() - timedelta(hours=time_window_hours)
        
        jobs = (
            self.db.query(Job)
            .filter(Job.organization_id == organization_id)
            .filter(Job.status == "running")
            .filter(Job.trigger_type.in_(["frequency", "cron"]))
            .all()
        )
        
        logger.info(f"Found {len(jobs)} active scheduled jobs to check")
        
        for job in jobs:
            last_execution = (
                self.db.query(JobExecution)
                .join(Job)
                .filter(Job.id == job.id)
                .order_by(JobExecution.started_at.desc())
                .first()
            )
            
            expected_run, skip_reason = self._check_expected_run(job, last_execution, time_threshold)
            
            if expected_run and skip_reason:
                missed_jobs.append(MissedJobDetail(
                    job_name=job.title,
                    object_id=str(job.id),
                    last_run_time=last_execution.started_at if last_execution else None,
                    expected_run_time=expected_run,
                    skip_reason=skip_reason
                ))
        
        return missed_jobs

    def _check_expected_run(self, job: Job, last_execution: Optional[JobExecution], time_threshold: datetime) -> tuple[Optional[datetime], Optional[str]]:
        now = datetime.now()
        
        if not last_execution:
            if job.created_at < time_threshold:
                return now, "Job has never run since creation"
            return None, None
        
        last_run = last_execution.started_at
        time_since_last_run = now - last_run
        
        if job.trigger_type == "frequency":
            if not job.frequency_interval or not job.frequency_unit:
                return None, None
            
            interval_seconds = self._get_interval_seconds(job.frequency_interval, job.frequency_unit)
            expected_next_run = last_run + timedelta(seconds=interval_seconds)
            
            if expected_next_run < now and last_run < time_threshold:
                return expected_next_run, f"Missed scheduled run (every {job.frequency_interval} {job.frequency_unit})"
        
        elif job.trigger_type == "cron":
            if not job.cron_expression:
                return None, None
            
            expected_next_run = self._get_next_cron_run(job.cron_expression, last_run)
            
            if expected_next_run and expected_next_run < now and last_run < time_threshold:
                return expected_next_run, f"Missed cron scheduled run ({job.cron_expression})"
        
        return None, None

    def _get_interval_seconds(self, interval: int, unit: str) -> int:
        unit_multipliers = {
            "seconds": 1,
            "minutes": 60,
            "hours": 3600,
            "days": 86400,
            "weeks": 604800,
        }
        return interval * unit_multipliers.get(unit, 1)

    def _get_next_cron_run(self, cron_expression: str, last_run: datetime) -> Optional[datetime]:
        try:
            from croniter import croniter
            cron = croniter(cron_expression, last_run)
            return cron.get_next(datetime)
        except Exception as e:
            logger.warning(f"Error parsing cron expression '{cron_expression}': {e}")
            return None

    def _send_skip_notification(self, organization: Organization, missed_jobs: list[MissedJobDetail], email_recipients: list[str]) -> None:
        subject = f"Job Skip Alert: {organization.name} - {len(missed_jobs)} Missed Jobs"
        body = self._build_skip_email_body(organization, missed_jobs)
        
        logger.info(f"Sending skip notification for {len(missed_jobs)} jobs to {email_recipients}")
        send_email_with_attachment(
            job_id="skip-alert",
            subject=subject,
            body=body,
            attachment_path="",
            custom_recipients=email_recipients
        )

    def _build_skip_email_body(self, organization: Organization, missed_jobs: list[MissedJobDetail]) -> str:
        body = f"""
<h2>Job Skip Alert - {organization.name}</h2>
<p>The following scheduled jobs have missed their expected execution time:</p>
<table border="1" cellpadding="5" style="border-collapse: collapse;">
<tr>
    <th>Job Name</th>
    <th>Last Run Time</th>
    <th>Expected Run Time</th>
    <th>Skip Reason</th>
</tr>
"""
        for job in missed_jobs:
            last_run = job.last_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.last_run_time else 'Never'
            expected = job.expected_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.expected_run_time else 'N/A'
            
            body += f"""
<tr>
    <td>{job.job_name}</td>
    <td>{last_run}</td>
    <td>{expected}</td>
    <td>{job.skip_reason}</td>
</tr>
"""
        
        body += f"""
</table>
<p><strong>Total Missed Jobs:</strong> {len(missed_jobs)}</p>
<br>
<p><em>Report generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</em></p>
"""
        return body

from src.models.job_execution import JobExecution
