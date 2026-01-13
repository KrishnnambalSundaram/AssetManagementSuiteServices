import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
# flake8: noqa: E402
from src.models.job import Job
from src.models.job_execution import JobExecution
from src.models.organization import Organization
from src.utils.database import engine
from src.utils.informatica import InformaticaUtils
from src.utils.notify import export_to_excel, send_email_with_attachment

logger = logging.getLogger(__name__)


class InformaticaDelayedJobsManager:

    # Job execution
    job_id: str
    execution_id: str
    job: Optional[Job]

    # Informatica credentials
    domain_url: Optional[str]
    username: str
    password: str
    organization_identifier: str

    # Job parameters
    duration_threshold: int
    delayed_jobs: List[Dict[str, Any]]

    def __init__(
        self, job_id: str, execution_id: str
    ) -> None:

        # Job execution
        self.job_id = job_id
        self.execution_id = execution_id
        self.job: Optional[Job] = None

        # Informatica credentials
        self.domain_url: Optional[str] = None
        self.username: str = ""
        self.password: str = ""
        self.organization_identifier: str = ""

        # Job parameters
        self.duration_threshold: int = 600 # 10 minutes
        self.delayed_jobs: List[Dict[str, Any]] = []
        self.get_config(job_id)

    def get_config(self, job_id: str) -> bool:
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            self.job = db.query(Job).filter(Job.id == job_id).first()
            if not self.job:
                raise Exception(f"Job {job_id} not found")
            logger.info(f"Job {job_id} found, organization: {self.job.organization_id}")
            organization = db.query(Organization).filter(Organization.id == self.job.organization_id).first()
            if not organization:
                raise Exception(f"Organization {self.job.organization_id} not found")
            self.domain_url = organization.domain
            self.username = organization.username
            self.password = organization.password
            self.organization_identifier = organization.identifier
            self.duration_threshold = self.job.parameters.get("duration_threshold", 10) * 60
            return True
        except Exception as e:
            logger.error(f"Error getting config: {e}")
            return False
        finally:
            db.close()

    def update_job_execution(
        self,
        execution_id: str,
        status: str,
        result: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            execution = (
                db.query(JobExecution).filter(JobExecution.id == execution_id).first()
            )
            execution.status = status
            execution.completed_at = datetime.now(timezone.utc)
            if error_message:
                execution.error_message = error_message
            if result:
                execution.result = result
            db.commit()
            db.refresh(execution)
            return True
        except Exception as e:
            logger.error(f"Error updating job execution: {e}")
            return False
        finally:
            db.close()

    def get_delayed_jobs(self) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch job logs directly from Informatica API using InformaticaUtils
        and filter for delayed jobs without persisting job log data.
        """
        try:
            informatica_service = InformaticaUtils()
            informatica_service.set_credentials(
                username=self.username,
                password=self.password,
                domain_url=self.domain_url,
            )

            if not informatica_service.login(
                self.username, self.password, self.domain_url
            ):
                logger.error("Failed to login to Informatica")
                return None

            logger.info("Successfully logged in to Informatica")

            job_logs_response = informatica_service.get_job_logs(
                self.organization_identifier
            )

            if not job_logs_response:
                logger.error(
                    "Failed to fetch job logs from Informatica or no logs returned"
                )
                return None

            logger.info(
                f"Successfully fetched {len(job_logs_response)} job logs from Informatica API"
            )

            job_logs = []
            for log in job_logs_response:
                log_dict = log.model_dump() if hasattr(log, "model_dump") else dict(log)
                job_logs.append(log_dict)

            delayed_jobs = [job for job in job_logs if self.is_job_delayed(job)]
            logger.info(
                f"Found {len(delayed_jobs)} delayed jobs (threshold: {self.duration_threshold} seconds)"
            )
            return delayed_jobs

        except Exception as e:
            logger.error(f"Error fetching job logs: {e}")
            return None

    def is_job_delayed(self, job: Dict[str, Any]) -> bool:
        """
        Check if a job is delayed based on duration threshold
        """
        try:
            # Calculate duration from start and end times
            # Try UTC times first, then fall back to regular times
            start_time = job.get("start_time_utc") or job.get("start_time")
            end_time = job.get("end_time_utc") or job.get("end_time")
            
            if not start_time or not end_time:
                return False

            # Convert string timestamps to datetime if needed
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            if isinstance(end_time, str):
                end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            
            # Calculate duration in seconds
            duration = (end_time - start_time).total_seconds()
            
            # Consider jobs as delayed if they took longer than threshold
            if duration > self.duration_threshold:
                job_name = job.get('object_name', job.get('id', 'Unknown'))
                logger.info(f"Job {job_name}: Duration {duration:.2f}s exceeds threshold {self.duration_threshold}s")
                return True
            
            return False

        except Exception as e:
            logger.error(f"Error checking if job is delayed: {e}")
            return False

    def process_delayed_jobs(self) -> None:
        """
        Main process to identify and report delayed jobs
        """
        logger.info(f"Starting delayed jobs processing (threshold: {self.duration_threshold} seconds)")

        try:
            # Validate that job and config were loaded successfully
            if not self.job:
                raise Exception(f"Job {self.job_id} not found or failed to load configuration")

            # Get delayed jobs by fetching fresh data from Informatica API
            delayed_jobs = self.get_delayed_jobs()
            if delayed_jobs is None:
                self.export_and_notify()
                logger.error("Failed to fetch job logs. Exiting.")
                raise Exception("Failed to fetch job logs from Informatica")

            self.delayed_jobs = delayed_jobs

            # Export to Excel and send email using generic utils
            self.export_and_notify()
            
            # Convert datetime objects to strings for JSON serialization
            def convert_datetime_to_iso(value):
                if isinstance(value, datetime):
                    return value.isoformat()
                return value
            
            self.update_job_execution(
                self.execution_id,
                "completed",
                {
                    "delayed_jobs_count": len(self.delayed_jobs),
                    "duration_threshold": self.duration_threshold,
                    "delayed_jobs": [
                        {
                            "id": job.get("id"),
                            "name": job.get("object_name", "Unknown"),
                            "type": job.get("type"),
                            "run_id": job.get("run_id"),
                            "start_time": convert_datetime_to_iso(job.get("start_time")),
                            "end_time": convert_datetime_to_iso(job.get("end_time")),
                            "start_time_utc": convert_datetime_to_iso(job.get("start_time_utc")),
                            "end_time_utc": convert_datetime_to_iso(job.get("end_time_utc")),
                            "state": job.get("state"),
                            "ui_state": job.get("ui_state"),
                            "started_by": job.get("started_by"),
                            "run_context_type": job.get("run_context_type"),
                            "error_msg": job.get("error_msg"),
                            "failed_source_rows": job.get("failed_source_rows"),
                            "success_source_rows": job.get("success_source_rows"),
                            "failed_target_rows": job.get("failed_target_rows"),
                            "success_target_rows": job.get("success_target_rows"),
                            "total_success_rows": job.get("total_success_rows"),
                            "total_failed_rows": job.get("total_failed_rows"),
                        }
                        for job in self.delayed_jobs
                    ],
                },
            )
        except Exception as e:
            logger.error(f"Error processing delayed jobs: {e}")
            self.update_job_execution(self.execution_id, "failed", error_message=str(e))
            raise Exception(f"Error processing delayed jobs: {e}")

    def export_and_notify(self) -> None:
        try:
            jobs_to_export = self.delayed_jobs
            
            if not jobs_to_export or len(jobs_to_export) == 0:
                # Send email indicating no delayed jobs found
                subject = "[Informatica] Delayed Jobs Report - No Data Found"
                body = f"""No delayed jobs were found matching the current parameters.

                Summary:
                - Total delayed jobs: 0
                - Duration threshold: {round(self.duration_threshold / 60, 0)} minutes
                - Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                
                This means all jobs are running within the expected time limits."""
                
                send_email_with_attachment(self.job.id, subject, body, None)
                logger.info("No delayed jobs found. Email notification sent indicating no data.")
                return

            # Export to Excel with new activity log structure fields
            headers = [
                "id",
                "type",
                "object_id",
                "object_name",
                "run_id",
                "start_time",
                "end_time",
                "start_time_utc",
                "end_time_utc",
                "state",
                "ui_state",
                "failed_source_rows",
                "success_source_rows",
                "failed_target_rows",
                "success_target_rows",
                "started_by",
                "run_context_type",
                "agent_id",
                "runtime_environment_id",
                "error_msg",
                "stop_on_error",
                "has_stop_on_error_record",
                "is_stopped",
                "context_external_id",
                "total_success_rows",
                "total_failed_rows"
            ]
            headersLabel = [
                "ID",
                "Type",
                "Object ID",
                "Object Name",
                "Run ID",
                "Start Time",
                "End Time",
                "Start Time UTC",
                "End Time UTC",
                "State",
                "UI State",
                "Failed Source Rows",
                "Success Source Rows",
                "Failed Target Rows",
                "Success Target Rows",
                "Started By",
                "Run Context Type",
                "Agent ID",
                "Runtime Environment ID",
                "Error Message",
                "Stop On Error",
                "Has Stop On Error Record",
                "Is Stopped",
                "Context External ID",
                "Total Success Rows",
                "Total Failed Rows"
            ]
            filename = f"delayed_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            export_to_excel(jobs_to_export, filename, headers, headersLabel)

            # Send email with attachment
            subject = "[Informatica] Delayed Jobs Report"
            body = f"""Please find attached the list of delayed jobs.

                Summary:
                - Total delayed jobs: {len(jobs_to_export)}
                - Duration threshold: {round(self.duration_threshold / 60, 0)} minutes
                - Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
                
            send_email_with_attachment(self.job.id, subject, body, filename)
            
            logger.info(f"Successfully exported {len(jobs_to_export)} delayed jobs to {filename}")
            logger.info(f"Email notification sent for job run {self.job.id}")
            
        except Exception as e:
            logger.error(f"Error exporting and notifying: {e}")
            return
        finally:
            if 'filename' in locals() and os.path.exists(filename):
                os.remove(filename)
                logger.info(f"Cleaned up temporary file: {filename}")


def main() -> Dict[str, int]:
    parser = argparse.ArgumentParser(description="Process Informatica delayed jobs")
    parser.add_argument("--job_id", type=str, help="Job ID to process")
    parser.add_argument("--execution_id", type=str, help="Execution ID to process")
    args, unknown = parser.parse_known_args()  # unknown will skip any extra arguments

    try:
        manager = InformaticaDelayedJobsManager(args.job_id, args.execution_id)
        manager.process_delayed_jobs()
        return {
           "message": "Delayed jobs processed successfully"
        }
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        # Try to update job execution if possible (in case process_delayed_jobs didn't catch it)
        try:
            Session = sessionmaker(bind=engine)
            db = Session()
            try:
                execution = (
                    db.query(JobExecution).filter(JobExecution.id == args.execution_id).first()
                )
                if execution and execution.status != "failed":
                    execution.status = "failed"
                    execution.completed_at = datetime.now(timezone.utc)
                    execution.error_message = f"Fatal error: {str(e)}"
                    db.commit()
            finally:
                db.close()
        except Exception as update_error:
            logger.error(f"Failed to update job execution: {update_error}")
        raise


if __name__ == "__main__":
    main()
