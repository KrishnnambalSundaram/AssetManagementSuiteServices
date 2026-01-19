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
    time_window_hours: int = Query(24, ge=1, le=168, description="Time window in hours to check for missed jobs"),
    db_session: Session = Depends(db)
):
    """Get missed jobs for an organization without sending notification"""
    try:
        from src.modules.job_skip.schema import MissedJobDetail
        import uuid
        
        service = JobSkipService(db_session)
        
        try:
            org_uuid = uuid.UUID(organization_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid organization ID format: {organization_id}")
        
        org = service.db.query(Organization).filter(Organization.id == org_uuid).first()
        
        informatica_schedules = service._fetch_informatica_schedules(org)
        
        missed_jobs = service._identify_skipped_jobs(
            org_uuid, 
            informatica_schedules=informatica_schedules,
            time_window_hours=time_window_hours
        )
        
        return JobSkipDetailResponse(
            missed_jobs=missed_jobs,
            total_jobs_checked=len(db_session.query(Job).filter(Job.organization_id == org_uuid).all()),
            report_generated_at=datetime.now()
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
