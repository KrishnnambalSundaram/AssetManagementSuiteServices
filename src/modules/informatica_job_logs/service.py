from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from src.models.informatica_job_runs import InformaticaJobRuns
from src.models.organization import Organization
from src.modules.informatica_job_logs.schema import InformaticaJobLogsResponse, InformaticaJobRunsResponse, InformaticaJobRunsListResponse
from src.models.informatica_jobs_logs import InformaticaJobLogs
from src.utils.informatica import InformaticaUtils
import logging

logger = logging.getLogger(__name__)


class InformaticaJobLogsService:
    def __init__(self, db: Session):
        self.db = db

    def create_job_run(self, organization_id: str) -> InformaticaJobRunsResponse:
        """Create a new job run and execute it"""
        job_run = None
        try:
            # Create job run with initial status
            job_run = InformaticaJobRuns(
                organization_id=organization_id,
                status="running",
                sync_perfomed_at=datetime.now(timezone.utc)
            )
            self.db.add(job_run)
            self.db.commit()
            self.db.refresh(job_run)
            
            logger.info(f"Created job run {job_run.id} with status 'running'")
            
            # Execute the job and wait for completion
            logger.info(f"Starting Informatica job execution for run {job_run.id}")
            success = self._run_informatica_job(job_run.id, organization_id)
            
            # Update status based on execution result - only after job completes
            logger.info(f"Job execution completed. Success: {success}")
            job_run.status = "completed" if success else "failed"
            job_run.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(job_run)
            
            logger.info(f"Updated job run {job_run.id} status to '{job_run.status}'")
            return InformaticaJobRunsResponse.model_validate(job_run)
            
        except Exception as e:
            logger.error(f"Error in job run execution: {e}")
            # Update job run status to failed if there was an error
            if job_run:
                job_run.status = "failed"
                job_run.completed_at = datetime.now(timezone.utc)
                job_run.error_message = str(e)
                self.db.commit()
                self.db.refresh(job_run)
                logger.error(f"Updated job run {job_run.id} status to 'failed' due to error")
                return InformaticaJobRunsResponse.model_validate(job_run)
            else:
                raise

    def get_job_run_by_id(self, job_run_id: str) -> Optional[InformaticaJobRunsResponse]:
        """Get a specific job run by ID"""
        job_run = (
            self.db.query(InformaticaJobRuns)
            .filter(InformaticaJobRuns.id == job_run_id)
            .first()
        )
        return InformaticaJobRunsResponse.model_validate(job_run) if job_run else None

    def get_last_job_run(self, organization_id: Optional[str] = None) -> Optional[InformaticaJobRunsResponse]:
        """Get the last job run for a specific job"""
        query = self.db.query(InformaticaJobRuns)
        if organization_id:
            query = query.filter(InformaticaJobRuns.organization_id == organization_id)
        job_run = query.order_by(InformaticaJobRuns.sync_perfomed_at.desc()).first()
        return InformaticaJobRunsResponse.model_validate(job_run) if job_run else None

    def get_job_logs(self, job_run_id: str) -> list[InformaticaJobLogsResponse]:
        """Get the job logs for a specific job run"""
        logs = (
            self.db.query(InformaticaJobLogs)
            .filter(InformaticaJobLogs.job_run_id == job_run_id)
            .order_by(InformaticaJobLogs.start_time.desc())
            .all()
        )
        return [InformaticaJobLogsResponse.model_validate(log) for log in logs]

    def get_job_runs(self, limit: int = 5, page: int = 1, organization_id: Optional[str] = None) -> InformaticaJobRunsListResponse:
        """Get the job runs with pagination"""
        query = self.db.query(InformaticaJobRuns)
        if organization_id:
            query = query.filter(InformaticaJobRuns.organization_id == organization_id)
        
        job_runs = (
            query
            .order_by(InformaticaJobRuns.sync_perfomed_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        
        total_query = self.db.query(InformaticaJobRuns)
        if organization_id:
            total_query = total_query.filter(InformaticaJobRuns.organization_id == organization_id)
        total = total_query.count()
        
        job_run_responses = [InformaticaJobRunsResponse.model_validate(job_run) for job_run in job_runs]
        return InformaticaJobRunsListResponse(
            job_runs=job_run_responses,
            total=total,
            page=page,
            limit=limit
        )

    def _run_informatica_job(self, job_run_id: str, organization_id: str) -> bool:
        """Run the informatica job and return success status - this method must complete fully"""
        logger.info(f"Starting _run_informatica_job for run {job_run_id}")
        
        try:
            # Get organization details
            organization = self.db.query(Organization).filter(Organization.id == organization_id).first()
            if not organization:
                logger.error(f"Organization {organization_id} not found")
                return False
            
            logger.info(f"Found organization: {organization.name}")
            
            # Initialize Informatica service
            informatica_service = InformaticaUtils()
            informatica_service.set_credentials(
                username=organization.username, 
                password=organization.password, 
                domain_url=organization.domain,
            )
            
            logger.info("Attempting to login to Informatica...")
            # Login to Informatica
            if not informatica_service.login(organization.username, organization.password, organization.domain):
                logger.error("Failed to login to Informatica")
                return False
            
            logger.info("Successfully logged in to Informatica")
            
            # Fetch job logs - this is the main operation that must complete
            logger.info(f"Fetching job logs for organization: {organization_id}")
            job_logs = informatica_service.get_job_logs(organization.identifier)
            if job_logs is None:
                logger.error("Failed to fetch job logs from Informatica")
                return False
            
            logger.info(f"Successfully fetched {len(job_logs)} job logs")
            
            # Store logs in database - handle individual record failures gracefully
            successful_inserts = 0
            failed_inserts = 0
            
            for log in job_logs:
                try:
                    # Add job_run_id and organization_id to the log data
                    log_data = log.model_dump() if hasattr(log, 'model_dump') else dict(log)
                    log_data['job_run_id'] = job_run_id
                    log_data['organization_id'] = organization_id
                    
                    # Check if record with same object_id, run_id, and organization_id already exists
                    existing_log = self.db.query(InformaticaJobLogs).filter(
                        InformaticaJobLogs.object_id == log_data.get('object_id'),
                        InformaticaJobLogs.run_id == log_data.get('run_id'),
                        InformaticaJobLogs.organization_id == organization_id
                    ).first()
                    
                    if existing_log:
                        # Update existing record with new data
                        for key, value in log_data.items():
                            if hasattr(existing_log, key) and value is not None:
                                setattr(existing_log, key, value)
                        logger.info(f"Updated existing log record for object_id={log_data.get('object_id')}, run_id={log_data.get('run_id')}")
                        successful_inserts += 1
                    else:
                        # Create new record
                        job_log = InformaticaJobLogs(**log_data)
                        self.db.add(job_log)
                        successful_inserts += 1
                    
                    # Commit each record individually to avoid batch failures
                    self.db.commit()
                    
                except Exception as e:
                    failed_inserts += 1
                    logger.error(f"Error processing job log (object_id={log_data.get('object_id')}, run_id={log_data.get('run_id')}): {e}")
                    # Rollback only the current transaction, not the entire batch
                    self.db.rollback()
                    continue
            
            logger.info(f"Successfully stored {successful_inserts} job logs, {failed_inserts} failed")
            
            logger.info(f"_run_informatica_job completed successfully for run {job_run_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error in _run_informatica_job for run {job_run_id}: {e}")
            return False
