from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.modules.job_execution.schema import JobExecutionListResponse, JobExecutionResponse
from src.modules.job_execution.service import JobExecutionService
from src.utils.auth import get_current_user
from src.utils.database import db

router = APIRouter(
    prefix="/job-executions",
    tags=["job-executions"],
    dependencies=[Depends(get_current_user)]
)


@router.get("", response_model=JobExecutionListResponse)
async def get_executions(
    limit: int = Query(10, ge=1, le=100, description="Number of executions to return"),
    page: int = Query(1, ge=1, description="Page number"),
    # Single and array filters
    organization_id: Optional[List[str]] = Query(None, description="Filter by organization ID(s) (requires join)"),
    job_id: Optional[List[str]] = Query(None, description="Filter by job ID(s)"),
    status: Optional[List[str]] = Query(None, description="Filter by status (running, completed, failed, timeout, cancelled)"),
    # Date filters with operator pattern
    started_at_operator: Optional[str] = Query(None, description="Operator for started_at filter (lt, gt, lte, gte, eq, ne)"),
    started_at_value: Optional[datetime] = Query(None, description="Value for started_at filter"),
    completed_at_operator: Optional[str] = Query(None, description="Operator for completed_at filter (lt, gt, lte, gte, eq, ne)"),
    completed_at_value: Optional[datetime] = Query(None, description="Value for completed_at filter"),
    # Numeric filters with operator pattern
    retry_count_operator: Optional[str] = Query(None, description="Operator for retry_count filter (lt, gt, lte, gte, eq, ne)"),
    retry_count_value: Optional[int] = Query(None, description="Value for retry_count filter"),
    db: Session = Depends(db),
):
    """Get all executions with pagination and filters"""
    try:
        execution_service = JobExecutionService(db)
        return execution_service.get_executions(
            limit=limit, 
            page=page,
            organization_id=organization_id,
            job_id=job_id,
            status=status,
            started_at_operator=started_at_operator,
            started_at_value=started_at_value,
            completed_at_operator=completed_at_operator,
            completed_at_value=completed_at_value,
            retry_count_operator=retry_count_operator,
            retry_count_value=retry_count_value
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/job/{job_id}", response_model=list[JobExecutionResponse])
async def get_executions_by_job(
    job_id: str,
    limit: int = Query(10, ge=1, le=100, description="Number of executions to return"),
    page: int = Query(1, ge=1, description="Page number"),
    db: Session = Depends(db),
):
    """Get executions for a specific job with pagination"""
    try:
        execution_service = JobExecutionService(db)
        return execution_service.get_executions_by_job(job_id, limit=limit, page=page)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{execution_id}", response_model=JobExecutionResponse)
async def get_execution(
    execution_id: str,
    db: Session = Depends(db),
):
    """Get a specific job execution by ID"""
    try:
        execution_service = JobExecutionService(db)
        execution = execution_service.get_execution(execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Job execution not found")
        return execution
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


