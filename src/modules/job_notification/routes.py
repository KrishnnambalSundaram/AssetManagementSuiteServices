from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.modules.job_notification.schema import (JobNotificationCreate,
                                                 JobNotificationResponse,
                                                 JobNotificationUpdate,
                                                 JobNotificationListResponse)
from src.modules.job_notification.service import JobNotificationService
from src.utils.auth import get_current_user
from src.utils.database import db

router = APIRouter(
    prefix="/job-notifications",
    tags=["job-notifications"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/", response_model=JobNotificationListResponse)
async def get_job_notifications(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    db: Session = Depends(db),
):
    """Get job notifications with pagination"""
    try:
        notification_service = JobNotificationService(db)
        return notification_service.get_job_notifications(skip=skip, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/job/{job_id}", response_model=List[JobNotificationResponse])
async def get_notifications_by_job(
    job_id: str, db: Session = Depends(db)
):
    """Get all notifications for a specific job"""
    try:
        notification_service = JobNotificationService(db)
        return notification_service.get_notifications_by_job(job_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{notification_id}", response_model=JobNotificationResponse)
async def get_job_notification(notification_id: str, db: Session = Depends(db)):
    """Get a specific job notification by ID"""
    try:
        notification_service = JobNotificationService(db)
        notification = notification_service.get_job_notification(notification_id)
        if not notification:
            raise HTTPException(status_code=404, detail="Job notification not found")
        return notification
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=JobNotificationResponse)
async def create_job_notification(
    notification: JobNotificationCreate, db: Session = Depends(db)
):
    """Create a new job notification"""
    try:
        notification_service = JobNotificationService(db)
        return notification_service.create_job_notification(notification)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{notification_id}", response_model=JobNotificationResponse)
async def update_job_notification(
    notification_id: str, notification: JobNotificationUpdate, db: Session = Depends(db)
):
    """Update a job notification"""
    try:
        notification_service = JobNotificationService(db)
        updated_notification = notification_service.update_job_notification(
            notification_id, notification
        )
        if not updated_notification:
            raise HTTPException(status_code=404, detail="Job notification not found")
        return updated_notification
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{notification_id}")
async def delete_job_notification(notification_id: str, db: Session = Depends(db)):
    """Delete a job notification"""
    try:
        notification_service = JobNotificationService(db)
        success = notification_service.delete_job_notification(notification_id)
        if not success:
            raise HTTPException(status_code=404, detail="Job notification not found")
        return {"message": "Job notification deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{notification_id}/toggle", response_model=JobNotificationResponse)
async def toggle_notification_status(notification_id: str, db: Session = Depends(db)):
    """Toggle the active status of a job notification"""
    try:
        notification_service = JobNotificationService(db)
        notification = notification_service.toggle_notification_status(notification_id)
        if not notification:
            raise HTTPException(status_code=404, detail="Job notification not found")
        return notification
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
