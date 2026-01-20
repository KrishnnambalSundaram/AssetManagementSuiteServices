import logging
from datetime import datetime, timedelta, timezone
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
                                       MissedJobDetail,
                                       InformaticaScheduleResponse,
                                       InformaticaSchedule)
from src.utils.notify import send_email_with_attachment
from src.utils.informatica import InformaticaUtils

logger = logging.getLogger(__name__)


class JobSkipService:
    def __init__(self, db: Session):
        self.db = db

    def get_organization(self, org_id_or_identifier: str) -> Organization:
        """Get organization by UUID ID or String Identifier"""
        # Try as UUID
        try:
            org_uuid = uuid.UUID(org_id_or_identifier)
            org = self.db.query(Organization).filter(Organization.id == org_uuid).first()
            if org:
                return org
        except ValueError:
            pass
        
        # Try as Identifier
        org = self.db.query(Organization).filter(Organization.identifier == org_id_or_identifier).first()
        if org:
            return org
            
        raise ValueError(f"Organization with ID or Identifier '{org_id_or_identifier}' not found")


    def get_informatica_schedules(self, organization_id: str) -> InformaticaScheduleResponse:
        """Fetch all enabled schedules from Informatica API for an organization"""
        org = self.get_organization(organization_id)


        informatica_service = InformaticaUtils()
        informatica_service.set_credentials(
            username=org.username,
            password=org.password,
            domain_url=org.domain,
        )

        if not informatica_service.login(org.username, org.password, org.domain):
            raise Exception("Failed to login to Informatica")

        schedules = informatica_service.get_schedules(query_params={"q": "status=='enabled'"})
        if not schedules:
            return InformaticaScheduleResponse(
                message="No schedules found for organization",
                organization_id=organization_id,
                schedules_count=0,
                schedules=[],
                fetched_at=datetime.now()
            )

        logger.info(f"fetched {len(schedules)} schedules from Informatica")
        schedule_objects = [InformaticaSchedule(**schedule) for schedule in schedules]

        return InformaticaScheduleResponse(
            message=f"fetched {len(schedule_objects)} schedules from Informatica",
            organization_id=organization_id,
            schedules_count=len(schedule_objects),
            schedules=schedule_objects,
            fetched_at=datetime.now()
        )

    def check_job_skips(self, request: JobSkipCheckRequest) -> JobSkipCheckResponse:
        logger.info(f"Checking job skips for organization {request.organization_id}")

        org = self.get_organization(request.organization_id)

        informatica_schedules = self._fetch_informatica_schedules(org)
        # Determine time window
        hours = request.time_window_hours
        if hours is None and request.time_period:
            if request.time_period == "hourly":
                hours = 1
            elif request.time_period == "daily":
                hours = 24
            elif request.time_period == "weekly":
                hours = 168
            elif request.time_period == "monthly":
                hours = 720
        
        if hours is None:
            hours = 24  # Default fallback

        skipped_jobs = self._identify_skipped_jobs(
            organization_id=org.id,
            informatica_schedules=informatica_schedules,
            time_window_hours=hours,
            use_custom_mapping=request.use_custom_mapping,
            custom_mapping_field=request.custom_mapping_field
        )

        if skipped_jobs:
            self._send_skip_notification(org, skipped_jobs, request.email_recipients)

        return JobSkipCheckResponse(
            message=f"Job skip check completed. Found {len(skipped_jobs)} skipped jobs.",
            organization_id=request.organization_id,
            missed_jobs_count=len(skipped_jobs),
            checked_at=datetime.now()
        )

    def _fetch_informatica_schedules(self, organization: Organization) -> list:
        """Fetch enabled schedules from Informatica API"""
        informatica_service = InformaticaUtils()
        informatica_service.set_credentials(
            username=organization.username,
            password=organization.password,
            domain_url=organization.domain,
        )

        if not informatica_service.login(organization.username, organization.password, organization.domain):
            raise Exception("Failed to login to Informatica")

        schedules = informatica_service.get_schedules(query_params={"q": "status=='enabled'"})
        if not schedules:
            return []

        logger.info(f"fetched {len(schedules)} schedules from Informatica")
        return schedules

    def _identify_skipped_jobs(self, organization_id: uuid.UUID, informatica_schedules, time_window_hours: int, use_custom_mapping: bool = False, custom_mapping_field: str = None) -> list:
        missed_jobs = []

        time_threshold = datetime.now(timezone.utc) - timedelta(hours=time_window_hours)

        local_jobs = (
            self.db.query(Job)
            .filter(Job.organization_id == organization_id)
            .filter(Job.status == "running")
            .all()
        )

        logger.info(f"found {len(local_jobs)} local jobs and {len(informatica_schedules)} informatica schedules")

        schedule_job_map = self._map_schedules_to_jobs(informatica_schedules, local_jobs, use_custom_mapping, custom_mapping_field)

        schedules_to_check = informatica_schedules if informatica_schedules else []

        for schedule in schedules_to_check:
            job = schedule_job_map.get(schedule.get("name"))
            if not job:
                continue

            last_execution = (
                self.db.query(JobExecution)
                .filter(JobExecution.job_id == job.id)
                .order_by(JobExecution.started_at.desc())
                .first()
            )

            expected_run, skip_reason = self._check_expected_run_against_schedule(schedule, last_execution, time_threshold)

            if expected_run and skip_reason:
                missed_jobs.append(MissedJobDetail(
                    job_name=job.title,
                    object_id=str(job.id),
                    last_run_time=last_execution.started_at if last_execution else None,
                    expected_run_time=expected_run,
                    skip_reason=skip_reason
                ))

        return missed_jobs

    def _map_schedules_to_jobs(self, schedules, jobs, use_custom_mapping: bool, custom_mapping_field: str) -> dict:
        schedule_job_map = {}

        for schedule in schedules:
            schedule_name = schedule.get("name")
            schedule_id = schedule.get("id")
            schedule_federated_id = schedule.get("scheduleFederatedId")

            matching_job = None

            if use_custom_mapping and custom_mapping_field:
                for job in jobs:
                    job_config = job.parameters or {}
                    job_description = job.description or ""

                    if job_config.get(custom_mapping_field) in [schedule_name, schedule_id, schedule_federated_id] or job_description in [schedule_name, schedule_id, schedule_federated_id]:
                        matching_job = job
                        break
            else:
                for job in jobs:
                    if job.title == schedule_name:
                        matching_job = job
                        break

            if matching_job:
                schedule_job_map[schedule_name] = matching_job
                logger.debug(f"mapped schedule '{schedule_name}' to job '{matching_job.title}'")

        return schedule_job_map

    def _check_expected_run_against_schedule(self, schedule, last_execution, time_threshold) -> tuple:
        now = datetime.now(timezone.utc)

        schedule_status = schedule.get("status")

        if schedule_status != "enabled":
            return None, None

        if not last_execution:
            create_time = self._parse_informatica_datetime(schedule.get("createTime"))
            if create_time and create_time < time_threshold:
                return now, "Schedule has never been executed since creation"
            return None, None

        last_run = last_execution.started_at

        schedule_interval = schedule.get("interval")

        if schedule_interval == "Minutely":
            frequency = schedule.get("frequency", 5)
            expected_next_run = last_run + timedelta(minutes=frequency)
            if expected_next_run < now:
                return expected_next_run, f"missed minutely schedule (every {frequency} minutes)"

        elif schedule_interval == "Hourly":
            frequency = schedule.get("frequency", 1)
            expected_next_run = last_run + timedelta(hours=frequency)
            if expected_next_run < now:
                return expected_next_run, f"missed hourly schedule (every {frequency} hours)"

        elif schedule_interval == "Daily":
            expected_next_run = last_run + timedelta(days=1)
            if expected_next_run < now and last_run < time_threshold:
                return expected_next_run, "missed daily schedule"

        elif schedule_interval == "Weekly":
            expected_next_run = last_run + timedelta(weeks=1)
            if expected_next_run < now and last_run < time_threshold:
                return expected_next_run, "missed weekly schedule"

        elif schedule_interval == "Biweekly":
            expected_next_run = last_run + timedelta(weeks=2)
            if expected_next_run < now and last_run < time_threshold:
                return expected_next_run, "missed biweekly schedule"

        elif schedule_interval == "Monthly":
            expected_next_run = last_run + timedelta(days=30)
            if expected_next_run < now and last_run < time_threshold:
                return expected_next_run, "missed monthly schedule"

        return None, None

    def _parse_informatica_datetime(self, dt_str) -> Optional[datetime]:
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception as e:
            logger.warning(f"failed to parse datetime '{dt_str}': {e}")
            return None

    def _send_skip_notification(self, organization, missed_jobs, email_recipients) -> None:
        subject = f"Job Skip Alert: {organization.name} - {len(missed_jobs)} Missed Jobs"
        body = self._build_skip_email_body(organization, missed_jobs)

        logger.info(f"sending skip notification for {len(missed_jobs)} jobs to {email_recipients}")
        send_email_with_attachment(
            job_id="skip-alert",
            subject=subject,
            body=body,
            attachment_path="",
            custom_recipients=email_recipients
        )

    def _build_skip_email_body(self, organization, missed_jobs) -> str:
        body = f"""
<h2>Job Skip Alert - {organization.name}</h2>
<p>The following Informatica schedules have missed their expected execution time:</p>
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
