from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.modules.job_failure.schema import (
    JobFailureCheckRequest,
    JobFailureCheckResponse,
)
from src.modules.job_failure.service import JobFailureService
from src.utils.auth import get_current_user
from src.utils.database import db

router = APIRouter()


@router.post("/check", response_model=JobFailureCheckResponse)
def check_job_failures(
    request: JobFailureCheckRequest,
    db: Session = Depends(db),
    current_user=Depends(get_current_user),
):
    """
    Check for failed Informatica jobs and notify stakeholders.
    """
    try:
        service = JobFailureService(db)
        return service.check_and_notify(request)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
