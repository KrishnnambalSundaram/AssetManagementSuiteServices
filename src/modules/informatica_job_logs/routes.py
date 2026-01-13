from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session
from typing import Optional

from src.modules.informatica_job_logs.service import InformaticaJobLogsService
from src.modules.informatica_job_logs.schema import InformaticaJobLogsResponse, InformaticaJobRunsCreateRequest, InformaticaJobRunsListResponse, InformaticaJobRunsResponse
from src.utils.auth import get_current_user
from src.utils.database import db

router = APIRouter(
    prefix="/job-runs",
    tags=["job-runs"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/", response_model=InformaticaJobRunsListResponse)
async def get_job_runs(
    db: Session = Depends(db),
    limit: int = Query(10, ge=1, le=100, description="Number of job runs to return"),
    page: int = Query(1, ge=1, description="Page number"),
    organization_id: Optional[str] = Query(None, description="Filter by organization ID"),
):
    """Get the job runs with pagination"""
    logs_service = InformaticaJobLogsService(db)
    job_runs = logs_service.get_job_runs(limit=limit, page=page, organization_id=organization_id)
    return job_runs

@router.post("/", response_model=InformaticaJobRunsResponse)
async def create_job_run(
    db: Session = Depends(db),
    request: InformaticaJobRunsCreateRequest = Body(...),
):
    """Create a new job run"""
    logs_service = InformaticaJobLogsService(db)
    job_run = logs_service.create_job_run(request.organization_id)
    return job_run

@router.get("/latest-sync", response_model=InformaticaJobRunsResponse)
async def get_last_job_run(
    db: Session = Depends(db),
    organization_id: Optional[str] = Query(None, description="Filter by organization ID"),
):
    """Get the last job run"""
    try:
        logs_service = InformaticaJobLogsService(db)
        job_run = logs_service.get_last_job_run(organization_id=organization_id)
        if not job_run:
            raise HTTPException(status_code=404, detail="No job runs found")
        return job_run
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{job_run_id}", response_model=InformaticaJobRunsResponse)
async def get_job_run_by_id(
    db: Session = Depends(db),
    job_run_id: str = Path(..., description="The ID of the job run to retrieve"),
):
    """Get a specific job run by ID"""
    logs_service = InformaticaJobLogsService(db)
    job_run = logs_service.get_job_run_by_id(job_run_id)
    if not job_run:
        raise HTTPException(status_code=404, detail="Job run not found")
    return job_run
