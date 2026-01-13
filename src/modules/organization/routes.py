from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.modules.organization.schema import (OrganizationCreate,
                                             OrganizationListResponse,
                                             OrganizationResponse,
                                             OrganizationUpdate)
from src.modules.organization.service import OrganizationService
from src.utils.auth import get_current_user
from src.utils.database import db

router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
    dependencies=[Depends(get_current_user)]
)


@router.get("/", response_model=OrganizationListResponse)
async def get_organizations(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    # Regex search (searches name, description, identifier, domain, username)
    search: Optional[str] = Query(None, description="Regex search across name, description, identifier, domain, username"),
    # Single and array filters
    domain: Optional[List[str]] = Query(None, description="Filter by domain(s)"),
    identifier: Optional[List[str]] = Query(None, description="Filter by identifier(s)"),
    username: Optional[List[str]] = Query(None, description="Filter by username(s)"),
    environment: Optional[List[str]] = Query(None, description="Filter by environment(s)"),
    # Boolean filter
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(db),
):
    """Get all organizations with pagination and filters"""
    try:
        organization_service = OrganizationService(db)
        return organization_service.get_organizations(
            skip=skip, 
            limit=limit,
            search=search,
            domain=domain,
            identifier=identifier,
            username=username,
            environment=environment,
            is_active=is_active
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(organization_id: str, db: Session = Depends(db)):
    """Get a specific organization by ID"""
    try:
        organization_service = OrganizationService(db)
        organization = organization_service.get_organization(organization_id)
        if not organization:
            raise HTTPException(status_code=404, detail="Organization not found")
        return organization
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=OrganizationResponse)
async def create_organization(organization: OrganizationCreate, db: Session = Depends(db)):
    """Create a new organization"""
    try:
        organization_service = OrganizationService(db)
        return organization_service.create_organization(organization)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{organization_id}", response_model=OrganizationResponse)
async def update_organization(
    organization_id: str, organization: OrganizationUpdate, db: Session = Depends(db)
):
    """Update an organization"""
    try:
        organization_service = OrganizationService(db)
        updated_organization = organization_service.update_organization(organization_id, organization)
        if not updated_organization:
            raise HTTPException(status_code=404, detail="Organization not found")
        return updated_organization
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{organization_id}")
async def delete_organization(organization_id: str, db: Session = Depends(db)):
    """Delete an organization"""
    try:
        organization_service = OrganizationService(db)
        success = organization_service.delete_organization(organization_id)
        if not success:
            raise HTTPException(status_code=404, detail="Organization not found")
        return {"message": "Organization deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check-identifier/{identifier}")
async def check_organization_by_identifier(identifier: str, db: Session = Depends(db)):
    """Check if an organization exists by provider identifier"""
    try:
        organization_service = OrganizationService(db)
        exists = organization_service.check_organization_exists_by_identifier(identifier)
        return {"exists": exists, "identifier": identifier}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-identifier/{identifier}", response_model=OrganizationResponse)
async def get_organization_by_identifier(identifier: str, db: Session = Depends(db)):
    """Get an organization by provider identifier"""
    try:
        organization_service = OrganizationService(db)
        organization = organization_service.get_organization_by_identifier_response(identifier)
        if not organization:
            raise HTTPException(status_code=404, detail="Organization not found")
        return organization
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
