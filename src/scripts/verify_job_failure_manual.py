import logging
import uuid
import sys
import os
from datetime import datetime, timedelta, timezone

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from src.utils.database import engine, Base
from sqlalchemy.orm import sessionmaker
from src.models.informatica_jobs_logs import InformaticaJobLogs
from src.models.informatica_job_runs import InformaticaJobRuns
from src.models.organization import Organization
from src.modules.job_failure.service import JobFailureService
from src.modules.job_failure.schema import JobFailureCheckRequest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_job_failure_check():
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # 1. Setup Data
        logger.info("Setting up test data...")
        
        # Get or create an organization
        org = db.query(Organization).first()
        if not org:
            logger.error("No organization found. Please create one first.")
            return

        # Create a dummy failed job log
        run_id = 999999
        object_id = str(uuid.uuid4())
        
        # Create parent job run first (referenced by foreign key)
        job_run = InformaticaJobRuns(
            organization_id=org.id,
            status="failed",
            sync_perfomed_at=datetime.now(timezone.utc)
        )
        db.add(job_run)
        db.commit()
        db.refresh(job_run)
        
        failed_log = InformaticaJobLogs(
            job_run_id=job_run.id,
            organization_id=org.id,
            object_name="TEST_FAILED_JOB_AGENT",
            run_id=run_id,
            object_id=object_id,
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            state=3, # Failed state
            error_msg="This is a test error message for verification",
            failed_source_rows=10,
            failed_target_rows=5
        )
        db.add(failed_log)
        db.commit()
        logger.info(f"Created failed job log: {failed_log.object_name} (Run ID: {run_id})")
        
        # 2. Trigger Check
        logger.info("Triggering Job Failure Check...")
        service = JobFailureService(db)
        request = JobFailureCheckRequest(
            organization_id=org.id,
            email_recipients=["test@example.com"],
            time_window_hours=24
        )
        
        response = service.check_and_notify(request)
        
        # 3. Verify Output
        logger.info(f"Check completed. Found {response.failed_jobs_count} failed jobs.")
        
        found = False
        for job in response.failed_jobs:
            logger.info(f"Found Job: {job.job_name}, Error: {job.error_message}")
            if job.job_name == "TEST_FAILED_JOB_AGENT":
                found = True
        
        if found:
            logger.info("SUCCESS: Test job was identified correctly!")
        else:
            logger.error("FAILURE: Test job was NOT identified.")
            
        # 4. Clean up
        logger.info("Cleaning up test data...")
        db.delete(failed_log)
        db.delete(job_run)
        db.commit()
        
    except Exception as e:
        logger.error(f"Error during verification: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    verify_job_failure_check()
