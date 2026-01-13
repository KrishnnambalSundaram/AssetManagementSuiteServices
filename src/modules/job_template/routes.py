from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.modules.job_template.schema import (JobTemplateCreate,
                                             JobTemplateListResponse,
                                             JobTemplateResponse,
                                             JobTemplateUpdate)
from src.modules.job_template.service import JobTemplateService
from src.utils.auth import get_current_user
from src.utils.database import db
from src.utils.constants import PREDEFINED_SCRIPTS

router = APIRouter(
    prefix="/job-templates",
    tags=["job-templates"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/", response_model=JobTemplateListResponse)
async def get_job_templates(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    # Regex search (searches title, description, script_type, script_content, script_path)
    search: Optional[str] = Query(None, description="Regex search across title, description, script_type, script_content, script_path"),
    # Single and array filters
    organization_id: Optional[List[str]] = Query(None, description="Filter by organization ID(s)"),
    script_type: Optional[List[str]] = Query(None, description="Filter by script type(s)"),
    # Boolean filter
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(db),
):
    """Get all job templates with pagination and filters"""
    try:
        template_service = JobTemplateService(db)
        return template_service.get_job_templates(
            skip=skip, 
            limit=limit,
            search=search,
            organization_id=organization_id,
            script_type=script_type,
            is_active=is_active
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predefined-scripts", response_model=list)
async def get_predefined_scripts():
    """Return a list of predefined scripts"""
    return PREDEFINED_SCRIPTS


@router.get("/{job_template_id}", response_model=JobTemplateResponse)
async def get_job_template(job_template_id: str, db: Session = Depends(db)):
    """Get a specific job template by ID"""
    try:
        template_service = JobTemplateService(db)
        template = template_service.get_job_template(job_template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Job template not found")
        return template
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=JobTemplateResponse)
async def create_job_template(
    job_template: JobTemplateCreate, db: Session = Depends(db)
):
    """Create a new job template"""
    try:
        template_service = JobTemplateService(db)
        return template_service.create_job_template(job_template)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{job_template_id}", response_model=JobTemplateResponse)
async def update_job_template(
    job_template_id: str, job_template: JobTemplateUpdate, db: Session = Depends(db)
):
    """Update a job template"""
    try:
        template_service = JobTemplateService(db)
        updated_template = template_service.update_job_template(
            job_template_id, job_template
        )
        if not updated_template:
            raise HTTPException(status_code=404, detail="Job template not found")
        return updated_template
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{job_template_id}")
async def delete_job_template(job_template_id: str, db: Session = Depends(db)):
    """Delete a job template"""
    try:
        template_service = JobTemplateService(db)
        success = template_service.delete_job_template(job_template_id)
        if not success:
            raise HTTPException(status_code=404, detail="Job template not found")
        return {"message": "Job template deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
