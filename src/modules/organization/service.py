import asyncio
import logging
import uuid
from typing import Optional, List

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.modules.organization.schema import (OrganizationCreate,
                                             OrganizationListResponse,
                                             OrganizationResponse,
                                             OrganizationUpdate)
from src.utils.organization_handlers import OrganizationHandlers

logger = logging.getLogger(__name__)


class OrganizationService:
    def __init__(self, db: Session):
        self.db = db

    def get_organizations(
        self, 
        skip: int = 0, 
        limit: int = 100,
        search: Optional[str] = None,
        domain: Optional[List[str]] = None,
        identifier: Optional[List[str]] = None,
        username: Optional[List[str]] = None,
        environment: Optional[List[str]] = None,
        is_active: Optional[bool] = None
    ) -> OrganizationListResponse:
        """Get all organizations with pagination and filters"""
        query = self.db.query(Organization)
        
        # Apply regex search across multiple fields
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Organization.name.ilike(search_pattern),
                    Organization.description.ilike(search_pattern),
                    Organization.identifier.ilike(search_pattern),
                    Organization.domain.ilike(search_pattern),
                    Organization.username.ilike(search_pattern)
                )
            )
        
        # Apply array filters
        if domain:
            query = query.filter(Organization.domain.in_(domain))
        if identifier:
            query = query.filter(Organization.identifier.in_(identifier))
        if username:
            query = query.filter(Organization.username.in_(username))
        if environment:
            query = query.filter(Organization.environment.in_(environment))
        
        # Apply boolean filter
        if is_active is not None:
            query = query.filter(Organization.is_active == is_active)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        organizations = query.offset(skip).limit(limit).all()

        organization_responses = [OrganizationResponse.model_validate(org) for org in organizations]
        return OrganizationListResponse(
            organizations=organization_responses,
            total=total,
            page=skip // limit + 1,
            limit=limit,
        )

    def get_organization(self, organization_id: str) -> Optional[OrganizationResponse]:
        """Get a specific organization by ID"""
        try:
            try:
                org_uuid = uuid.UUID(organization_id)
            except Exception:
                org_uuid = organization_id
            
            organization = (
                self.db.query(Organization)
                .filter(Organization.id == org_uuid)
                .first()
            )
            if organization:
                return OrganizationResponse.model_validate(organization)
            return None
        except ValueError:
            return None

    def get_organization_by_domain(self, domain: str) -> Optional[Organization]:
        """Get an organization by domain"""
        return self.db.query(Organization).filter(Organization.domain == domain).first()

    def create_organization(
        self, organization: OrganizationCreate, created_by_user_id: Optional[str] = None
    ) -> OrganizationResponse:
        """Create a new organization"""
        try:
            db_organization = Organization(
                name=organization.name,
                description=organization.description,
                domain=organization.domain,
                is_active=organization.is_active,
                configuration=organization.configuration,
                username=organization.username,
                password=organization.password,
                environment=organization.environment,
                identifier=organization.identifier,
            )

            self.db.add(db_organization)
            self.db.commit()
            self.db.refresh(db_organization)
            
            # Trigger paginated job logs for the new organization
            self._trigger_paginated_job_logs(str(db_organization.id))
            
            return OrganizationResponse.model_validate(db_organization)
        except IntegrityError:
            self.db.rollback()
            raise ValueError("Organization with this domain already exists")

    def update_organization(
        self, organization_id: str, organization: OrganizationUpdate
    ) -> Optional[OrganizationResponse]:
        """Update an organization"""
        try:
            try:
                org_uuid = uuid.UUID(organization_id)
            except Exception:
                org_uuid = organization_id
            
            db_organization = (
                self.db.query(Organization)
                .filter(Organization.id == org_uuid)
                .first()
            )

            if not db_organization:
                return None

            # Update fields if provided
            if organization.name is not None:
                db_organization.name = organization.name
            if organization.description is not None:
                db_organization.description = organization.description
            if organization.domain is not None:
                db_organization.domain = organization.domain
            if organization.is_active is not None:
                db_organization.is_active = organization.is_active
            if organization.configuration is not None:
                db_organization.configuration = organization.configuration
            if organization.username is not None:
                db_organization.username = organization.username
            if organization.password is not None:
                db_organization.password = organization.password
            if organization.environment is not None:
                db_organization.environment = organization.environment
            if organization.identifier is not None:
                db_organization.identifier = organization.identifier

            try:
                self.db.commit()
                self.db.refresh(db_organization)
                return OrganizationResponse.model_validate(db_organization)
            except IntegrityError:
                self.db.rollback()
                raise ValueError("Organization with this domain already exists")

        except ValueError:
            return None

    def delete_organization(self, organization_id: str) -> bool:
        """Delete an organization"""
        try:
            try:
                org_uuid = uuid.UUID(organization_id)
            except Exception:
                org_uuid = organization_id
            
            db_organization = self.db.query(Organization).filter(Organization.id == org_uuid).first()

            if not db_organization:
                return False

            self.db.delete(db_organization)
            self.db.commit()
            return True

        except ValueError:
            return False

    def get_organization_by_identifier(self, identifier: str) -> Optional[Organization]:
        """Get an organization by provider identifier"""
        return self.db.query(Organization).filter(Organization.identifier == identifier).first()

    def check_organization_exists_by_identifier(self, identifier: str) -> bool:
        """Check if an organization exists by provider identifier"""
        organization = self.get_organization_by_identifier(identifier)
        return organization is not None

    def get_organization_by_identifier_response(self, identifier: str) -> Optional[OrganizationResponse]:
        """Get an organization by provider identifier and return as response"""
        organization = self.get_organization_by_identifier(identifier)
        if organization:
            return OrganizationResponse.model_validate(organization)
        return None

    def _trigger_paginated_job_logs(self, organization_id: str) -> None:
        """
        Trigger paginated job logs for a newly created organization
        This runs asynchronously in the background to avoid blocking the API response
        """
        try:
            logger.info(f"Triggering paginated job logs for new organization: {organization_id}")
            
            # Run the paginated job logs in a background task
            # Using asyncio.create_task to run it asynchronously
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, create a task
                asyncio.create_task(
                    OrganizationHandlers.run_paginated_job_logs_for_organization(organization_id)
                )
            else:
                # If we're in a sync context, run it synchronously
                # This is a fallback for cases where the event loop isn't running
                success = OrganizationHandlers.run_paginated_job_logs_sync(organization_id)
                if success:
                    logger.info(f"Successfully completed paginated job logs for organization {organization_id}")
                else:
                    logger.error(f"Failed to complete paginated job logs for organization {organization_id}")
                    
        except Exception as e:
            logger.error(f"Error triggering paginated job logs for organization {organization_id}: {e}")
            # Don't raise the exception to avoid breaking the organization creation