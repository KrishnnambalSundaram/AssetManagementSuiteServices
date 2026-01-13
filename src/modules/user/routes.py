from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID

from src.modules.user.schema import (UserCreate, UserListResponse,
                                     UserResponse, UserUpdate, UserWithOrganizationsDetailResponse)
from src.modules.user.service import UserService
from src.modules.user_organization.schema import UserOrganizationMappingRequest, UserOrganizationMappingResponse
from src.utils.auth import create_access_token, get_current_user
from src.utils.database import db

protected_router = APIRouter(
    prefix="/users", tags=["users"], dependencies=[Depends(get_current_user)]
)

public_router = APIRouter(prefix="/users", tags=["users"])


@protected_router.get("/", response_model=UserListResponse)
async def get_users(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    db: Session = Depends(db),
):
    """Get all users with pagination"""
    try:
        user_service = UserService(db)
        return user_service.get_users(skip=skip, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@protected_router.get("/me", response_model=UserWithOrganizationsDetailResponse)
async def get_current_user_profile(current_user=Depends(get_current_user), db: Session = Depends(db)):
    """Get current user's profile with organizations"""
    try:
        user_service = UserService(db)
        user = user_service.get_user(str(current_user.id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@protected_router.get("/{user_id}", response_model=UserWithOrganizationsDetailResponse)
async def get_user(user_id: str, db: Session = Depends(db)):
    """Get a specific user by ID with organizations"""
    try:
        user_service = UserService(db)
        user = user_service.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@public_router.post("/", response_model=UserResponse)
async def create_user(user: UserCreate, db: Session = Depends(db)):
    """Create a new user"""
    try:
        user_service = UserService(db)
        return user_service.create_user(user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@protected_router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, user: UserUpdate, db: Session = Depends(db)):
    """Update a user"""
    try:
        user_service = UserService(db)
        updated_user = user_service.update_user(user_id, user)
        if not updated_user:
            raise HTTPException(status_code=404, detail="User not found")
        return updated_user
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@protected_router.delete("/{user_id}")
async def delete_user(user_id: str, db: Session = Depends(db)):
    """Delete a user"""
    try:
        user_service = UserService(db)
        success = user_service.delete_user(user_id)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        return {"message": "User deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@public_router.post("/login")
async def login_user(
    email: str = Body(..., embed=True),
    password: str = Body(..., embed=True),
    db: Session = Depends(db),
):
    """Authenticate user and return JWT token if credentials are valid"""
    try:
        user_service = UserService(db)
        user = user_service.get_user_by_email(email)
        if not user or not user_service.verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        access_token = create_access_token(
            {"user_id": str(user.id), "email": user.email}
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@protected_router.get("/{user_id}/organizations")
async def get_user_organizations(
    user_id: str,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    db: Session = Depends(db)
):
    """Get all organizations for a specific user"""
    try:
        user_service = UserService(db)
        return user_service.get_user_organizations(user_id, skip=skip, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@protected_router.post("/{user_id}/organizations/map", response_model=UserOrganizationMappingResponse)
async def map_user_to_organizations(
    user_id: str,
    mapping_request: UserOrganizationMappingRequest,
    db: Session = Depends(db)
):
    """Map a user to multiple organizations"""
    try:
        user_service = UserService(db)
        user_organizations = user_service.map_user_to_organizations(user_id, mapping_request)
        return {
            "user_id": UUID(user_id),
            "organizations": user_organizations,
            "total": len(user_organizations)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
