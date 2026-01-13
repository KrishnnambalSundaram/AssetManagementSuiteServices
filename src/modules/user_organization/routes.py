from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID

from src.modules.user_organization.schema import (
    UserOrganizationCreate,
    UserOrganizationUpdate,
    UserOrganizationResponse,
    UserOrganizationListResponse,
    UserOrganizationMappingRequest,
    UserOrganizationMappingResponse,
)
from src.modules.user_organization.service import UserOrganizationService
from src.utils.auth import get_current_user
from src.utils.database import db

router = APIRouter(
    prefix="/user-organizations",
    tags=["user-organizations"],
    dependencies=[Depends(get_current_user)]
)


@router.post("/", response_model=UserOrganizationResponse)
async def create_user_organization(
    user_org: UserOrganizationCreate,
    db: Session = Depends(db)
):
    """Create a new user-organization mapping"""
    try:
        user_org_service = UserOrganizationService(db)
        return user_org_service.create_user_organization(user_org)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{user_id}", response_model=UserOrganizationListResponse)
async def get_user_organizations(
    user_id: UUID,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    db: Session = Depends(db)
):
    """Get all organizations for a specific user"""
    try:
        user_org_service = UserOrganizationService(db)
        return user_org_service.get_user_organizations(user_id, skip=skip, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/organization/{organization_id}", response_model=UserOrganizationListResponse)
async def get_organization_users(
    organization_id: UUID,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    db: Session = Depends(db)
):
    """Get all users for a specific organization"""
    try:
        user_org_service = UserOrganizationService(db)
        return user_org_service.get_organization_users(organization_id, skip=skip, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{mapping_id}", response_model=UserOrganizationResponse)
async def update_user_organization(
    mapping_id: UUID,
    user_org_update: UserOrganizationUpdate,
    db: Session = Depends(db)
):
    """Update a user-organization mapping"""
    try:
        user_org_service = UserOrganizationService(db)
        updated_mapping = user_org_service.update_user_organization(mapping_id, user_org_update)
        if not updated_mapping:
            raise HTTPException(status_code=404, detail="User-organization mapping not found")
        return updated_mapping
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{mapping_id}")
async def delete_user_organization(mapping_id: UUID, db: Session = Depends(db)):
    """Delete a user-organization mapping"""
    try:
        user_org_service = UserOrganizationService(db)
        success = user_org_service.delete_user_organization(mapping_id)
        if not success:
            raise HTTPException(status_code=404, detail="User-organization mapping not found")
        return {"message": "User-organization mapping deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/user/{user_id}/map", response_model=UserOrganizationMappingResponse)
async def map_user_to_organizations(
    user_id: UUID,
    mapping_request: UserOrganizationMappingRequest,
    db: Session = Depends(db)
):
    """Map a user to multiple organizations"""
    try:
        user_org_service = UserOrganizationService(db)
        user_organizations = user_org_service.map_user_to_organizations(user_id, mapping_request)
        return {
            "user_id": user_id,
            "organizations": user_organizations,
            "total": len(user_organizations)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check-access/{user_id}/{organization_id}", response_model=UserOrganizationResponse)
async def check_user_organization_access(
    user_id: UUID,
    organization_id: UUID,
    db: Session = Depends(db)
):
    """Check if a user has access to an organization"""
    try:
        user_org_service = UserOrganizationService(db)
        mapping = user_org_service.check_user_organization_access(user_id, organization_id)
        if not mapping:
            raise HTTPException(status_code=404, detail="User does not have access to this organization")
        return mapping
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
