import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
# flake8: noqa: E402
from src.models.informatica_job_runs import InformaticaJobRuns
from src.models.informatica_jobs_logs import InformaticaJobLogs
from src.models.job import Job
from src.models.job_execution import JobExecution
from src.models.organization import Organization
from src.utils.database import engine
from src.utils.informatica import InformaticaUtils
from src.utils.notify import send_email_with_attachment

logger = logging.getLogger(__name__)


class InformaticaIncrementalLogSyncManager:
    job_id: str
    execution_id: str
    job: Optional[Job]

    domain_url: Optional[str]
    username: str
    password: str
    organization_identifier: str

    synced_logs: List[Dict[str, Any]]

    def __init__(self, job_id: str, execution_id: str) -> None:
        self.job_id = job_id
        self.execution_id = execution_id
        self.job: Optional[Job] = None

        self.domain_url: Optional[str] = None
        self.username: str = ""
        self.password: str = ""
        self.organization_identifier: str = ""

        self.synced_logs: List[Dict[str, Any]] = []
        self.get_config(job_id)

    def get_config(self, job_id: str) -> bool:
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            self.job = db.query(Job).filter(Job.id == job_id).first()
            if not self.job:
                raise Exception(f"Job {job_id} not found")

            logger.info(
                f"Job {job_id} found, organization: {self.job.organization_id}"
            )
            organization = (
                db.query(Organization)
                .filter(Organization.id == self.job.organization_id)
                .first()
            )
            if not organization:
                raise Exception(
                    f"Organization {self.job.organization_id} not found"
                )
            self.domain_url = organization.domain
            self.username = organization.username
            self.password = organization.password
            self.organization_identifier = organization.identifier
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

    def fetch_and_store_job_logs(self) -> Dict[str, Any]:
        Session = sessionmaker(bind=engine)
        db = Session()
        job_run = None
        try:
            job_run = InformaticaJobRuns(
                organization_id=str(self.job.organization_id),
                status="running",
                sync_perfomed_at=datetime.now(timezone.utc),
            )
            db.add(job_run)
            db.commit()
            db.refresh(job_run)
            logger.info(
                f"Created job run {job_run.id} for incremental log synchronization"
            )

            informatica_service = InformaticaUtils()
            informatica_service.set_credentials(
                username=self.username,
                password=self.password,
                domain_url=self.domain_url,
            )

            if not informatica_service.login(
                self.username, self.password, self.domain_url
            ):
                raise Exception("Failed to login to Informatica")

            job_logs_response = informatica_service.get_job_logs(
                self.organization_identifier
            )
            if not job_logs_response:
                raise Exception(
                    "Failed to fetch job logs from Informatica or no logs returned"
                )

            job_logs = []
            for log in job_logs_response:
                log_dict = log.model_dump() if hasattr(log, "model_dump") else dict(log)
                job_logs.append(log_dict)

            storage_result = self._store_job_logs_in_db(db, job_logs, job_run.id)
            self.synced_logs = job_logs

            job_run.status = "completed"
            job_run.completed_at = datetime.now(timezone.utc)
            db.commit()

            return {
                "job_run_id": job_run.id,
                "fetched_logs": len(job_logs),
                "stored_logs": storage_result.get("stored", 0),
                "duplicates": storage_result.get("duplicates", 0),
                "errors": storage_result.get("errors", 0),
            }
        except Exception as e:
            logger.error(f"Error during log synchronization: {e}")
            if job_run:
                job_run.status = "failed"
                job_run.completed_at = datetime.now(timezone.utc)
                job_run.error_message = str(e)
                db.commit()
            raise
        finally:
            db.close()

    def _store_job_logs_in_db(
        self, db, job_logs: List[Dict[str, Any]], job_run_id: str
    ) -> Dict[str, int]:
        logger.info(
            f"Storing {len(job_logs)} job logs in database for job_run_id: {job_run_id}"
        )
        stored_count = 0
        duplicate_count = 0
        error_count = 0

        for i, log in enumerate(job_logs):
            try:
                log_data = log.copy()
                log_data["job_run_id"] = job_run_id
                log_data["organization_id"] = self.job.organization_id

                job_log = InformaticaJobLogs(**log_data)
                db.add(job_log)
                db.commit()
                stored_count += 1

            except IntegrityError:
                db.rollback()
                duplicate_count += 1
                logger.warning(
                    f"Duplicate log skipped at index {i + 1} for organization {self.job.organization_id}"
                )
            except Exception as e:
                db.rollback()
                error_count += 1
                logger.error(f"Error storing job log {i + 1}: {e}")

        return {
            "processed": stored_count + duplicate_count + error_count,
            "stored": stored_count,
            "duplicates": duplicate_count,
            "errors": error_count,
        }

    def send_sync_email(self, summary: Dict[str, Any]) -> None:
        total_logs = summary.get("fetched_logs", 0)
        stored_logs = summary.get("stored_logs", 0)
        duplicates = summary.get("duplicates", 0)
        errors = summary.get("errors", 0)

        subject = "[Informatica] Incremental Job Logs Sync"
        body = f"""Incremental job log synchronization has completed.

        Summary:
        - Total logs fetched: {total_logs}
        - Logs stored: {stored_logs}
        - Duplicate skips: {duplicates}
        - Errors: {errors}
        - Job run ID: {summary.get("job_run_id")}
        - Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        send_email_with_attachment(self.job.id, subject, body, None)
        logger.info("Incremental sync notification email sent.")

    def process_incremental_sync(self) -> None:
        logger.info("Starting incremental log synchronization process")
        try:
            if not self.job:
                raise Exception(
                    f"Job {self.job_id} not found or failed to load configuration"
                )

            summary = self.fetch_and_store_job_logs()
            self.send_sync_email(summary)

            result_payload = {
                "synced_job_run_id": summary.get("job_run_id"),
                "fetched_logs": summary.get("fetched_logs"),
                "stored_logs": summary.get("stored_logs"),
                "duplicates": summary.get("duplicates"),
                "errors": summary.get("errors"),
                "synced_at": datetime.now(timezone.utc).isoformat(),
            }

            self.update_job_execution(
                self.execution_id,
                "completed",
                result_payload,
            )
        except Exception as e:
            logger.error(f"Error processing incremental sync: {e}")
            self.update_job_execution(
                self.execution_id, "failed", error_message=str(e)
            )
            raise


def main() -> Dict[str, str]:
    parser = argparse.ArgumentParser(
        description="Process Informatica incremental log sync"
    )
    parser.add_argument("--job_id", type=str, help="Job ID to process")
    parser.add_argument("--execution_id", type=str, help="Execution ID to process")
    args, _ = parser.parse_known_args()

    try:
        manager = InformaticaIncrementalLogSyncManager(
            args.job_id, args.execution_id
        )
        manager.process_incremental_sync()
        return {"message": "Incremental log sync processed successfully"}
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        try:
            Session = sessionmaker(bind=engine)
            db = Session()
            try:
                execution = (
                    db.query(JobExecution)
                    .filter(JobExecution.id == args.execution_id)
                    .first()
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


