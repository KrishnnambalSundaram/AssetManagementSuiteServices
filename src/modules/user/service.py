import uuid
from typing import Optional, List
from uuid import UUID

from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.organization import Organization
from src.models.user_organization import UserOrganization
from src.modules.user.schema import (UserCreate, UserListResponse, UserResponse,
                                     UserUpdate, UserWithOrganizationsDetailResponse, UserOrganizationDetail)
from src.modules.user_organization.schema import UserOrganizationMappingRequest

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    def __init__(self, db: Session):
        self.db = db

    def get_users(
        self, skip: int = 0, limit: int = 100
    ) -> UserListResponse:
        """Get all users with pagination"""
        users = self.db.query(User).offset(skip).limit(limit).all()
        total = self.db.query(User).count()

        user_responses = []
        for user in users:
            user_response = UserResponse.model_validate(user)
            user_responses.append(user_response)

        return UserListResponse(
            users=user_responses,
            total=total,
            page=skip // limit + 1,
            limit=limit,
        )

    def get_user(self, user_id: str) -> Optional[UserWithOrganizationsDetailResponse]:
        """Get a specific user by ID with organizations"""
        try:
            try:
                user_uuid = uuid.UUID(user_id)
            except Exception:
                user_uuid = user_id
            
            # Query user with joined organizations
            user = (
                self.db.query(User)
                .outerjoin(UserOrganization, User.id == UserOrganization.user_id)
                .outerjoin(Organization, UserOrganization.organization_id == Organization.id)
                .filter(User.id == user_uuid)
                .first()
            )
            
            if user:
                # Get user organizations separately for better control
                user_organizations = (
                    self.db.query(UserOrganization, Organization)
                    .join(Organization, UserOrganization.organization_id == Organization.id)
                    .filter(
                        UserOrganization.user_id == user_uuid,
                        UserOrganization.is_active == True
                    )
                    .all()
                )
                
                # Create organization details
                organizations_data = []
                for user_org, org in user_organizations:
                    org_detail = UserOrganizationDetail(
                        id=str(user_org.id),
                        organization_id=str(org.id),
                        organization_name=org.name,
                        organization_domain=org.domain,
                        organization_identifier=org.identifier,
                        role=user_org.role,
                        is_active=user_org.is_active,
                        created_at=user_org.created_at,
                        updated_at=user_org.updated_at
                    )
                    organizations_data.append(org_detail)
                
                # Create user response with organizations
                user_response = UserWithOrganizationsDetailResponse(
                    id=user.id,
                    username=user.username,
                    email=user.email,
                    is_active=user.is_active,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                    organizations=organizations_data
                )
                
                return user_response
            return None
        except ValueError:
            return None

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email (for authentication)"""
        return self.db.query(User).filter(User.email == email).first()

    def create_user(
        self, user: UserCreate, created_by_user_id: Optional[str] = None
    ) -> UserResponse:
        """Create a new user"""
        try:
            # Hash the password
            hashed_password = pwd_context.hash(user.password)

            db_user = User(
                username=user.username,
                email=user.email,
                password_hash=hashed_password,
                is_active=user.is_active,
            )

            self.db.add(db_user)
            self.db.commit()
            self.db.refresh(db_user)
            return UserResponse.model_validate(db_user)
        except IntegrityError:
            self.db.rollback()
            raise ValueError("User with this username or email already exists")

    def update_user(
        self, user_id: str, user: UserUpdate
    ) -> Optional[UserResponse]:
        """Update a user"""
        try:
            try:
                user_uuid = uuid.UUID(user_id)
            except Exception:
                user_uuid = user_id
            
            db_user = self.db.query(User).filter(User.id == user_uuid).first()

            if not db_user:
                return None

            # Update fields if provided
            if user.username is not None:
                db_user.username = user.username
            if user.email is not None:
                db_user.email = user.email
            if user.password is not None:
                db_user.password_hash = pwd_context.hash(user.password)
            if user.is_active is not None:
                db_user.is_active = user.is_active

            try:
                self.db.commit()
                self.db.refresh(db_user)
                return UserResponse.model_validate(db_user)
            except IntegrityError:
                self.db.rollback()
                raise ValueError("User with this username or email already exists")

        except ValueError:
            return None

    def delete_user(self, user_id: str) -> bool:
        """Delete a user"""
        try:
            try:
                user_uuid = uuid.UUID(user_id)
            except Exception:
                user_uuid = user_id
            
            db_user = self.db.query(User).filter(User.id == user_uuid).first()

            if not db_user:
                return False

            self.db.delete(db_user)
            self.db.commit()
            return True

        except ValueError:
            return False

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)

    def get_user_organizations(self, user_id: str, skip: int = 0, limit: int = 100) -> dict:
        """Get all organizations for a user"""
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            return {"user_organizations": [], "total": 0, "page": 1, "limit": limit}

        query = self.db.query(UserOrganization).filter(
            UserOrganization.user_id == user_uuid
        )
        
        total = query.count()
        user_organizations = query.offset(skip).limit(limit).all()
        
        return {
            "user_organizations": user_organizations,
            "total": total,
            "page": skip // limit + 1,
            "limit": limit
        }

    def map_user_to_organizations(self, user_id: str, mapping_request: UserOrganizationMappingRequest) -> List[UserOrganization]:
        """Map a user to multiple organizations"""
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise ValueError("Invalid user ID")

        # Check if user exists
        user = self.db.query(User).filter(User.id == user_uuid).first()
        if not user:
            raise ValueError("User not found")

        # Remove existing mappings for this user
        self.db.query(UserOrganization).filter(UserOrganization.user_id == user_uuid).delete()

        # Create new mappings
        user_organizations = []
        for org_id in mapping_request.organization_ids:
            user_org = UserOrganization(
                user_id=user_uuid,
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
