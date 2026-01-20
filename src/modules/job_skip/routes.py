from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session

from src.modules.job_skip.schema import (JobSkipCheckRequest,
                                       JobSkipCheckResponse,
                                       JobSkipDetailResponse,
                                       InformaticaScheduleResponse)
from src.modules.job_skip.service import JobSkipService
from src.utils.auth import get_current_user
from src.utils.database import db
from src.models.job import Job
from src.models.organization import Organization

router = APIRouter(
    prefix="/job-skip",
    tags=["job-skip"],
    dependencies=[Depends(get_current_user)]
)


@router.get("/informatica-schedules/{organization_id}", response_model=InformaticaScheduleResponse)
async def get_informatica_schedules(
    organization_id: str,
    db_session: Session = Depends(db)
):
    """Fetch all enabled schedules from Informatica API for an organization"""
    try:
        service = JobSkipService(db_session)
        return service.get_informatica_schedules(organization_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check", response_model=JobSkipCheckResponse)
async def check_job_skips(
    request: JobSkipCheckRequest = Body(...),
    db_session: Session = Depends(db)
):
    """Check for skipped jobs and send notification if any are found"""
    try:
        service = JobSkipService(db_session)
        return service.check_job_skips(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/organization/{organization_id}/missed", response_model=JobSkipDetailResponse)
async def get_missed_jobs(
    organization_id: str,
    time_period: Optional[str] = Query(None, description="Time period to check: hourly, daily, weekly, monthly"),
    time_window_hours: Optional[int] = Query(None, ge=1, le=720, description="Custom time window in hours"),
    db_session: Session = Depends(db)
):
    """Get missed jobs for an organization without sending notification"""
    try:
        from src.modules.job_skip.schema import MissedJobDetail
        import uuid
        
        service = JobSkipService(db_session)
        
        org = service.get_organization(organization_id)
        
        informatica_schedules = service._fetch_informatica_schedules(org)
        
        # Determine time window
        hours = time_window_hours
        if hours is None and time_period:
            if time_period.lower() == "hourly":
                hours = 1
            elif time_period.lower() == "daily":
                hours = 24
            elif time_period.lower() == "weekly":
                hours = 168
            elif time_period.lower() == "monthly":
                hours = 720
        
        if hours is None:
            hours = 24  # Default fallback

        missed_jobs = service._identify_skipped_jobs(
            org.id, 
            informatica_schedules=informatica_schedules,
            time_window_hours=hours
        )
        
        return JobSkipDetailResponse(
            missed_jobs=missed_jobs,
            total_jobs_checked=len(db_session.query(Job).filter(Job.organization_id == org.id).all()),
            report_generated_at=datetime.now()
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
