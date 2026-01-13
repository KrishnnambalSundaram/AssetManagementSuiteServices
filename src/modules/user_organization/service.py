from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from src.models.user_organization import UserOrganization
from src.models.user import User
from src.models.organization import Organization
from src.modules.user_organization.schema import (
    UserOrganizationCreate,
    UserOrganizationUpdate,
    UserOrganizationMappingRequest,
)


class UserOrganizationService:
    def __init__(self, db: Session):
        self.db = db

    def create_user_organization(self, user_org: UserOrganizationCreate) -> UserOrganization:
        """Create a new user-organization mapping"""
        # Check if user and organization exist
        user = self.db.query(User).filter(User.id == user_org.user_id).first()
        if not user:
            raise ValueError("User not found")

        organization = self.db.query(Organization).filter(Organization.id == user_org.organization_id).first()
        if not organization:
            raise ValueError("Organization not found")

        # Check if mapping already exists
        existing_mapping = self.db.query(UserOrganization).filter(
            and_(
                UserOrganization.user_id == user_org.user_id,
                UserOrganization.organization_id == user_org.organization_id
            )
        ).first()

        if existing_mapping:
            raise ValueError("User-organization mapping already exists")

        # Create new mapping
        db_user_org = UserOrganization(
            user_id=user_org.user_id,
            organization_id=user_org.organization_id,
            role=user_org.role,
            is_active=user_org.is_active
        )
        self.db.add(db_user_org)
        self.db.commit()
        self.db.refresh(db_user_org)
        return db_user_org

    def get_user_organizations(self, user_id: UUID, skip: int = 0, limit: int = 100) -> dict:
        """Get all organizations for a user"""
        query = self.db.query(UserOrganization).filter(
            and_(
                UserOrganization.user_id == user_id,
                UserOrganization.is_active == True
            )
        )
        
        total = query.count()
        user_organizations = query.offset(skip).limit(limit).all()
        
        return {
            "user_organizations": user_organizations,
            "total": total,
            "page": skip // limit + 1,
            "limit": limit
        }

    def get_organization_users(self, organization_id: UUID, skip: int = 0, limit: int = 100) -> dict:
        """Get all users for an organization"""
        query = self.db.query(UserOrganization).filter(
            and_(
                UserOrganization.organization_id == organization_id,
                UserOrganization.is_active == True
            )
        )
        
        total = query.count()
        user_organizations = query.offset(skip).limit(limit).all()
        
        return {
            "user_organizations": user_organizations,
            "total": total,
            "page": skip // limit + 1,
            "limit": limit
        }

    def update_user_organization(self, mapping_id: UUID, user_org_update: UserOrganizationUpdate) -> Optional[UserOrganization]:
        """Update a user-organization mapping"""
        user_org = self.db.query(UserOrganization).filter(UserOrganization.id == mapping_id).first()
        if not user_org:
            return None

        if user_org_update.role is not None:
            user_org.role = user_org_update.role
        if user_org_update.is_active is not None:
            user_org.is_active = user_org_update.is_active

        self.db.commit()
        self.db.refresh(user_org)
        return user_org

    def delete_user_organization(self, mapping_id: UUID) -> bool:
        """Delete a user-organization mapping"""
        user_org = self.db.query(UserOrganization).filter(UserOrganization.id == mapping_id).first()
        if not user_org:
            return False

        self.db.delete(user_org)
        self.db.commit()
        return True

    def map_user_to_organizations(self, user_id: UUID, mapping_request: UserOrganizationMappingRequest) -> List[UserOrganization]:
        """Map a user to multiple organizations"""
        # Check if user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")

        # Check if all organizations exist
        organizations = self.db.query(Organization).filter(
            Organization.id.in_(mapping_request.organization_ids)
        ).all()
        
        if len(organizations) != len(mapping_request.organization_ids):
            raise ValueError("One or more organizations not found")

        # Remove existing mappings for this user
        self.db.query(UserOrganization).filter(UserOrganization.user_id == user_id).delete()

        # Create new mappings
        user_organizations = []
        for org_id in mapping_request.organization_ids:
            user_org = UserOrganization(
                user_id=user_id,
                organization_id=org_id,
                role=mapping_request.role,
                is_active=mapping_request.is_active
            )
            self.db.add(user_org)
            user_organizations.append(user_org)

        self.db.commit()
        
        # Refresh all created objects
        for user_org in user_organizations:
            self.db.refresh(user_org)
            
        return user_organizations

    def get_user_organization_mapping(self, user_id: UUID) -> Optional[UserOrganization]:
        """Get a specific user-organization mapping"""
        return self.db.query(UserOrganization).filter(
            and_(
                UserOrganization.user_id == user_id,
                UserOrganization.is_active == True
            )
        ).first()

    def check_user_organization_access(self, user_id: UUID, organization_id: UUID) -> Optional[UserOrganization]:
        """Check if a user has access to an organization"""
        return self.db.query(UserOrganization).filter(
            and_(
                UserOrganization.user_id == user_id,
                UserOrganization.organization_id == organization_id,
                UserOrganization.is_active == True
            )
        ).first()
