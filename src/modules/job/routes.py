from typing import List, Optional
from datetime import datetime
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.modules.job.schema import (JobCreate, JobListResponse, JobResponse,
                                    JobUpdate)
from src.modules.job.service import JobService
from src.modules.job_notification.schema import (JobNotificationCreate,
                                                 JobNotificationUpdate)
from src.modules.job_notification.service import JobNotificationService
from src.utils.auth import get_current_user
from src.utils.database import db
from src.utils.scheduler import scheduler

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/jobs", tags=["jobs"], dependencies=[Depends(get_current_user)]
)


@router.get("/", response_model=JobListResponse)
async def get_jobs(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    # Regex search on title
    title_search: Optional[str] = Query(None, description="Regex search on job title"),
    # Single and array filters
    template_id: Optional[List[str]] = Query(None, description="Filter by template ID(s)"),
    organization_id: Optional[List[str]] = Query(None, description="Filter by organization ID(s)"),
    status: Optional[List[str]] = Query(None, description="Filter by status (running, completed, failed, etc.)"),
    trigger_type: Optional[List[str]] = Query(None, description="Filter by trigger type (manual, frequency, cron)"),
    frequency_unit: Optional[List[str]] = Query(None, description="Filter by frequency unit"),
    # Numeric/date filters with operator pattern
    frequency_interval_operator: Optional[str] = Query(None, description="Operator for frequency_interval filter (lt, gt, lte, gte, eq, ne)"),
    frequency_interval_value: Optional[int] = Query(None, description="Value for frequency_interval filter"),
    frequency_count_operator: Optional[str] = Query(None, description="Operator for frequency_count filter (lt, gt, lte, gte, eq, ne)"),
    frequency_count_value: Optional[int] = Query(None, description="Value for frequency_count filter"),
    frequency_end_time_operator: Optional[str] = Query(None, description="Operator for frequency_end_time filter (lt, gt, lte, gte, eq, ne)"),
    frequency_end_time_value: Optional[datetime] = Query(None, description="Value for frequency_end_time filter"),
    timeout_seconds_operator: Optional[str] = Query(None, description="Operator for timeout_seconds filter (lt, gt, lte, gte, eq, ne)"),
    timeout_seconds_value: Optional[int] = Query(None, description="Value for timeout_seconds filter"),
    max_retries_operator: Optional[str] = Query(None, description="Operator for max_retries filter (lt, gt, lte, gte, eq, ne)"),
    max_retries_value: Optional[int] = Query(None, description="Value for max_retries filter"),
    db: Session = Depends(db),
):
    """Get all jobs with pagination and filters"""
    try:
        job_service = JobService(db)
        return job_service.get_jobs(
            skip=skip, 
            limit=limit,
            title_search=title_search,
            template_id=template_id,
            organization_id=organization_id,
            status=status,
            trigger_type=trigger_type,
            frequency_unit=frequency_unit,
            frequency_interval_operator=frequency_interval_operator,
            frequency_interval_value=frequency_interval_value,
            frequency_count_operator=frequency_count_operator,
            frequency_count_value=frequency_count_value,
            frequency_end_time_operator=frequency_end_time_operator,
            frequency_end_time_value=frequency_end_time_value,
            timeout_seconds_operator=timeout_seconds_operator,
            timeout_seconds_value=timeout_seconds_value,
            max_retries_operator=max_retries_operator,
            max_retries_value=max_retries_value
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: Session = Depends(db)):
    """Get a specific job by ID"""
    try:
        job_service = JobService(db)
        job = job_service.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=JobResponse)
async def create_job(
    job: JobCreate = Body(...),
    emailIds: List[str] = Body(..., embed=True),
    db: Session = Depends(db),
):
    """Create a new job"""
    logger.info(f"Received job creation request - Title: {job.title}")
    logger.info(f"Job details: template_id={job.template_id}, organization_id={job.organization_id}")
    logger.info(f"Email IDs: {emailIds}")
    logger.info(f"Full job data: {job.model_dump()}")
    
    try:
        logger.info("Creating JobService instance...")
        job_service = JobService(db)
        
        logger.info("Calling create_job service method...")
        job_response = job_service.create_job(job)
        logger.info(f"Job created successfully with ID: {job_response.id}")
        
        logger.info("Creating job notification...")
        job_notification_service = JobNotificationService(db)
        notification_data = {
            "job_id": str(job_response.id),
            "notification_type": "email",
            "trigger_on": job.trigger_on or "both",
            "configuration": {"emails": emailIds},
        }
        logger.info(f"Notification data: {notification_data}")
        
        job_notification_service.create_job_notification(
            JobNotificationCreate(**notification_data)
        )
        logger.info("Job notification created successfully")
        
        # Schedule the job immediately if it's a scheduled job (cron/frequency) with status "running"
        if job_response.trigger_type in ["cron", "frequency"] and job_response.status == "running":
            logger.info(f"Scheduling job {job_response.id} immediately after creation")
            # Get the full job object from database to pass to scheduler
            from src.models.job import Job
            db_job = db.query(Job).filter(Job.id == job_response.id).first()
            if db_job:
                await scheduler.schedule_job(db_job)
                logger.info(f"Job {job_response.id} scheduled successfully")
        
        logger.info("Job creation process completed successfully")
        return job_response
    except ValueError as e:
        logger.error(f"ValueError in create_job endpoint: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in create_job endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: str,
    job: JobUpdate = Body(...),
    emailIds: List[str] = Body(..., embed=True),
    db: Session = Depends(db),
):
    """Update a job and its notification emails"""
    try:
        job_service = JobService(db)
        updated_job = job_service.update_job(job_id, job)
        if not updated_job:
            raise HTTPException(status_code=404, detail="Job not found")
        # Update or create notification
        if emailIds:
            job_notification_service = JobNotificationService(db)
            notifications = job_notification_service.get_notifications_by_job(job_id)
            notification_data = {
                "job_id": updated_job.id,
                "notification_type": "email",
                "trigger_on": getattr(job, "trigger_on", None) or "both",
                "configuration": {"emails": emailIds},
            }
            if notifications:
                # Update the first notification (or all, if needed)
                job_notification_service.update_job_notification(
                    str(notifications[0].id), JobNotificationUpdate(**notification_data)
                )
            else:
                job_notification_service.create_job_notification(
                    JobNotificationCreate(**notification_data)
                )

        # Update scheduler: reschedule if it's a scheduled job with status "running", or remove if not
        # Get the full job object from database to pass to scheduler
        from src.models.job import Job
        db_job = db.query(Job).filter(Job.id == updated_job.id).first()
        if db_job:
            # Always call update_job which will handle scheduling/removal based on trigger_type and status
            logger.info(f"Updating scheduler for job {updated_job.id} (trigger_type: {updated_job.trigger_type}, status: {updated_job.status})")
            await scheduler.update_job(db_job)
            logger.info(f"Job {updated_job.id} scheduler updated successfully")

        return updated_job
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{job_id}")
async def delete_job(job_id: str, db: Session = Depends(db)):
    """Delete a job"""
    try:
        job_service = JobService(db)
        success = job_service.delete_job(job_id)
        if not success:
            raise HTTPException(status_code=404, detail="Job not found")

        # Remove from scheduler
        await scheduler.remove_job(job_id)

        return {"message": "Job deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/run")
async def run_job_manually(job_id: str, db: Session = Depends(db)):
    """Manually trigger a job execution"""
    try:
        job_service = JobService(db)
        job = job_service.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Run the job manually
        await scheduler.run_job_manually(job_id)

        return {"message": f"Job {job_id} execution started"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduled/list")
async def get_scheduled_jobs():
    """Get all currently scheduled jobs"""
    try:
        scheduled_jobs = scheduler.get_scheduled_jobs()
        return {"scheduled_jobs": scheduled_jobs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
