from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from src.modules.job_monitoring.schema import (ExecutionDetailResponse,JobMonitoringDetailResponse,JobMonitoringRequest,JobMonitoringResponse)
from src.modules.job_monitoring.service import JobMonitoringService
from src.utils.auth import get_current_user
from src.utils.database import db

router = APIRouter(prefix="/job-monitoring",tags=["job-monitoring"],dependencies=[Depends(get_current_user)])


@router.post("/monitor", response_model=JobMonitoringResponse)
async def monitor_job(request: JobMonitoringRequest = Body(...),db_session: Session = Depends(db)
):
    monitor_job_with_email_recipients(request, db_session)
    return JobMonitoringResponse(
        message=f"Job monitoring report sent successfully",
        job_name=request.job_name,
        execution_count=0,
        sent_to=request.email_recipients,
        timestamp=datetime.now()
    )


@router.get("/job/{job_name}", response_model=JobMonitoringDetailResponse)
async def get_job_details(job_name: str,db_session: Session = Depends(db)
):
    try:
        service = JobMonitoringService(db_session)
        job_detail = service.get_job_details_by_name(job_name)
        if not job_detail:
            raise HTTPException(status_code=404, detail=f"Job '{job_name}' not found")
        return job_detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/{job_name}", response_model=list[ExecutionDetailResponse])
async def get_job_executions(job_name: str,limit: int = 10,db_session: Session = Depends(db)
):
    try:
        service = JobMonitoringService(db_session)
        return service.get_job_executions_by_name(job_name, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def monitor_job_with_email_recipients(request: JobMonitoringRequest, db_session: Session) -> JobMonitoringResponse:
    service = JobMonitoringService(db_session)
    try:
        return service.monitor_job(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from datetime import datetime
