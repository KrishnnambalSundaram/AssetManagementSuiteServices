import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
# flake8: noqa: E402
from src.models.organization import Organization
from src.modules.informatica_job_logs.service import InformaticaJobLogsService
from src.utils.database import engine
from src.utils.informatica import InformaticaUtils
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


class InformaticaPaginatedJobLogsManager:

    # Organization and credentials
    organization_id: str
    domain_url: Optional[str]
    username: str
    password: str
    organization_identifier: str

    # Pagination parameters
    page_size: int
    max_pages: int
    all_job_logs: List[Dict[str, Any]]

    def __init__(
        self, organization_id: str, page_size: int = 1000, max_pages: int = 100
    ) -> None:

        # Organization
        self.organization_id = organization_id
        self.domain_url: Optional[str] = None
        self.username: str = ""
        self.password: str = ""
        self.organization_identifier: str = ""

        # Pagination parameters
        self.page_size = page_size
        self.max_pages = max_pages
        self.all_job_logs: List[Dict[str, Any]] = []
        self.get_organization_config(organization_id)

    def get_organization_config(self, organization_id: str) -> bool:
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            organization = db.query(Organization).filter(Organization.id == organization_id).first()
            if not organization:
                raise Exception(f"Organization {organization_id} not found")
            print(f"Organization {organization_id} found: {organization.name}")
            self.domain_url = organization.domain
            self.username = organization.username
            self.password = organization.password
            self.organization_identifier = organization.identifier
            return True
        except Exception as e:
            logger.error(f"Error getting organization config: {e}")
            return False
        finally:
            db.close()

    def get_paginated_job_logs(self) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch job logs from Informatica API with pagination support
        Recursively calls API until no more records are available
        """
        try:
            # Create database session
            Session = sessionmaker(bind=engine)
            db = Session()
            
            try:
                # Create a job run record manually (without fetching data)
                from src.models.informatica_job_runs import InformaticaJobRuns
                
                job_run = InformaticaJobRuns(
                    organization_id=self.organization_id,
                    status="running",
                    sync_perfomed_at=datetime.now(timezone.utc)
                )
                db.add(job_run)
                db.commit()
                db.refresh(job_run)
                
                print(f"Created job run {job_run.id} for paginated data fetch")
                
                # Initialize Informatica service for paginated fetching
                informatica_service = InformaticaUtils()
                informatica_service.set_credentials(
                    username=self.username,
                    password=self.password,
                    domain_url=self.domain_url,
                )
                
                # Login to Informatica
                if not informatica_service.login(self.username, self.password, self.domain_url):
                    logger.error("Failed to login to Informatica")
                    return None
                
                print("Successfully logged in to Informatica")
                
                # Fetch all job logs with pagination
                all_logs = self._fetch_all_job_logs_paginated(informatica_service)
                
                if all_logs is None:
                    logger.error("Failed to fetch paginated job logs")
                    return None
                
                print(f"Successfully fetched {len(all_logs)} job logs across all pages")
                
                # Store logs in database
                self._store_job_logs_in_db(db, all_logs, job_run.id)
                
                # Update job run status to completed
                job_run.status = "completed"
                job_run.completed_at = datetime.now(timezone.utc)
                db.commit()
                
                return all_logs
                
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error fetching paginated job logs: {e}")
            return None

    def _fetch_all_job_logs_paginated(self, informatica_service: InformaticaUtils) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch all job logs using pagination
        """
        all_logs = []
        page = 1
        total_fetched = 0
        
        print(f"Starting paginated fetch with page size: {self.page_size}")
        
        while page <= self.max_pages:
            print(f"Fetching page {page}...")
            
            # Fetch current page
            page_logs = self._fetch_job_logs_page(informatica_service, page, self.page_size)
            
            if page_logs is None:
                logger.error(f"Failed to fetch page {page}")
                break
                
            if len(page_logs) == 0:
                print(f"No more records found on page {page}. Stopping pagination.")
                break
                
            all_logs.extend(page_logs)
            total_fetched += len(page_logs)
            print(f"Page {page}: Fetched {len(page_logs)} records (Total: {total_fetched})")
            
            # If we got fewer records than page size, we've reached the end
            if len(page_logs) < self.page_size:
                print(f"Received {len(page_logs)} records (less than page size {self.page_size}). End of data.")
                break
                
            page += 1
        
        print(f"Pagination complete. Total records fetched: {total_fetched} across {page-1} pages")
        return all_logs

    def _fetch_job_logs_page(self, informatica_service: InformaticaUtils, page: int, page_size: int) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch a single page of job logs from Informatica API
        """
        if not informatica_service.session_id or not informatica_service.base_url:
            logger.error("Not logged in. Please login first.")
            return None

        # Calculate offset for pagination
        offset = (page - 1) * page_size
        
        logs_url = f"{informatica_service.base_url}/api/v2/activity/activityLog?rowLimit={page_size}&rowOffset={offset}"
        headers = {
            "Content-Type": "application/json",
            "icSessionId": informatica_service.session_id,
        }

        try:
            print(f"Fetching page {page} (offset: {offset}, limit: {page_size})")
            response = informatica_service._make_request(logs_url, headers)
            
            if response is None:
                return None
                
            logs_data = response.json()
            print(f"Page {page}: Retrieved {len(logs_data)} job logs")
            
            # Convert to our format
            job_logs = []
            for log in logs_data:
                try:
                    # Transform the data to match our schema
                    transformed_log = {
                        "informatica_id": log.get("id"),
                        "type": log.get("type"),
                        "object_id": log.get("objectId"),
                        "object_name": log.get("objectName"),
                        "run_id": log.get("runId"),
                        "start_time": log.get("startTime"),
                        "end_time": log.get("endTime"),
                        "start_time_utc": log.get("startTimeUtc"),
                        "end_time_utc": log.get("endTimeUtc"),
                        "state": log.get("state"),
                        "ui_state": log.get("UIState"),
                        "failed_source_rows": log.get("failedSourceRows"),
                        "success_source_rows": log.get("successSourceRows"),
                        "failed_target_rows": log.get("failedTargetRows"),
                        "success_target_rows": log.get("successTargetRows"),
                        "started_by": log.get("startedBy"),
                        "run_context_type": log.get("runContextType"),
                        "entries": log.get("entries", []),
                        "sub_task_entries": log.get("subTaskEntries", []),
                        "transformation_entries": log.get("transformationEntries", []),
                        "log_entry_item_attrs": log.get("logEntryItemAttrs"),
                        "session_variables": log.get("sessionVariables"),
                        "total_success_rows": log.get("totalSuccessRows"),
                        "total_failed_rows": log.get("totalFailedRows"),
                        "stop_on_error": log.get("stopOnError"),
                        "has_stop_on_error_record": log.get("hasStopOnErrorRecord"),
                        "is_stopped": log.get("isStopped"),
                        "error_msg": log.get("errorMsg"),
                        "agent_id": log.get("agentId"),
                        "runtime_environment_id": log.get("runtimeEnvironmentId"),
                        "context_external_id": log.get("contextExternalId")
                    }
                    
                    job_logs.append(transformed_log)
                except Exception as e:
                    logger.error(f"Error parsing job log: {e}")
                    continue
            
            return job_logs

        except Exception as e:
            logger.error(f"Error fetching job logs page {page}: {e}")
            return None

    def _store_job_logs_in_db(self, db, job_logs: List[Dict[str, Any]], job_run_id: str) -> None:
        """
        Store job logs in database
        """
        try:
            from src.models.informatica_jobs_logs import InformaticaJobLogs
            
            print(f"DEBUG: Starting to store {len(job_logs)} job logs for job_run_id: {job_run_id}")
            print(f"DEBUG: Organization ID: {self.organization_id}")
            
            storage_logs = []
            processed_count = 0
            error_count = 0
            
            for i, log in enumerate(job_logs):
                try:
                    # Add job_run_id and organization_id to the log data
                    log_data = log.copy()
                    log_data['job_run_id'] = job_run_id
                    log_data['organization_id'] = self.organization_id
                    
                    print(f"DEBUG: Processing log {i+1}/{len(job_logs)}: object_id={log_data.get('object_id')}, run_id={log_data.get('run_id')}")
                    
                    job_log = InformaticaJobLogs(**log_data)
                    storage_logs.append(job_log)
                    processed_count += 1
                    
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error processing job log {i+1}: {e}")
                    print(f"DEBUG: Error processing log {i+1}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            print(f"DEBUG: Processed {processed_count} logs successfully, {error_count} errors")
            print(f"DEBUG: About to store {len(storage_logs)} logs in database")
            
            # Commit all logs to database
            if storage_logs:
                try:
                    db.add_all(storage_logs)
                    db.commit()
                    print(f"✅ Successfully stored {len(storage_logs)} job logs in database")
                    
                    # Verify storage by counting records
                    stored_count = db.query(InformaticaJobLogs).filter(
                        InformaticaJobLogs.job_run_id == job_run_id
                    ).count()
                    print(f"DEBUG: Verification - {stored_count} records found in database for job_run_id {job_run_id}")
                    
                except Exception as e:
                    logger.error(f"Error committing job logs to database: {e}")
                    print(f"DEBUG: Error committing to database: {e}")
                    import traceback
                    traceback.print_exc()
                    db.rollback()
                    raise
            else:
                print("❌ No job logs to store (all failed processing)")
                
        except Exception as e:
            logger.error(f"Error storing job logs: {e}")
            print(f"DEBUG: Error in _store_job_logs_in_db: {e}")
            import traceback
            traceback.print_exc()
            raise

    def process_paginated_job_logs(self) -> None:
        """
        Main process to fetch all job logs using pagination
        """
        print(f"Starting paginated job logs processing (page size: {self.page_size}, max pages: {self.max_pages})")
        print(f"Organization ID: {self.organization_id}")
        print(f"Organization Identifier: {self.organization_identifier}")

        try:
            # Get all job logs using pagination
            print("DEBUG: Calling get_paginated_job_logs()...")
            all_job_logs = self.get_paginated_job_logs()
            
            if all_job_logs is None:
                logger.error("Failed to fetch job logs. Exiting.")
                print("DEBUG: get_paginated_job_logs() returned None")
                return

            self.all_job_logs = all_job_logs
            print(f"✅ Successfully processed {len(self.all_job_logs)} job logs")
            
            # Print summary
            print(f"\n=== PAGINATION SUMMARY ===")
            print(f"Total records fetched: {len(self.all_job_logs)}")
            print(f"Page size: {self.page_size}")
            print(f"Organization: {self.organization_identifier}")
            
            # Show sample of first few records
            if self.all_job_logs:
                print(f"\n=== SAMPLE RECORDS (first 3) ===")
                for i, job in enumerate(self.all_job_logs[:3]):
                    print(f"Record {i+1}: {job.get('object_name', 'Unknown')} - {job.get('type')} - {job.get('state')}")
            else:
                print("❌ No job logs in all_job_logs list")
                    
        except Exception as e:
            logger.error(f"Error processing paginated job logs: {e}")
            print(f"DEBUG: Exception in process_paginated_job_logs: {e}")
            import traceback
            traceback.print_exc()
            return

def main() -> Dict[str, int]:
    parser = argparse.ArgumentParser(description="Process Informatica job logs with pagination")
    parser.add_argument("--organization_id", type=str, required=True, help="Organization ID to process")
    parser.add_argument("--page_size", type=int, default=1000, help="Number of records per page (default: 1000)")
    parser.add_argument("--max_pages", type=int, default=100, help="Maximum pages to fetch (default: 100)")
    args, unknown = parser.parse_known_args()  # unknown will skip any extra arguments

    manager = InformaticaPaginatedJobLogsManager(
        organization_id=args.organization_id,
        page_size=args.page_size,
        max_pages=args.max_pages
    )
    manager.process_paginated_job_logs()
    return {
       "message": "Paginated job logs processed successfully"
    }


if __name__ == "__main__":
    main()
