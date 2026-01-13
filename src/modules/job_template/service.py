import uuid
from typing import Optional, List

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.job_template import JobTemplate
from src.modules.job_template.schema import (JobTemplateCreate,
                                             JobTemplateListResponse,
                                             JobTemplateResponse,
                                             JobTemplateUpdate)


class JobTemplateService:
    def __init__(self, db: Session):
        self.db = db

    def get_job_templates(
        self, 
        skip: int = 0, 
        limit: int = 100,
        search: Optional[str] = None,
        organization_id: Optional[List[str]] = None,
        script_type: Optional[List[str]] = None,
        is_active: Optional[bool] = None
    ) -> JobTemplateListResponse:
        """Get all job templates with pagination and filters"""
        query = self.db.query(JobTemplate)
        
        # Apply regex search across multiple fields
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    JobTemplate.title.ilike(search_pattern),
                    JobTemplate.description.ilike(search_pattern),
                    JobTemplate.script_type.ilike(search_pattern),
                    JobTemplate.script_content.ilike(search_pattern),
                    JobTemplate.script_path.ilike(search_pattern)
                )
            )
        
        # Apply array filters
        if organization_id:
            org_uuids = []
            for oid in organization_id:
                try:
                    org_uuids.append(uuid.UUID(oid))
                except ValueError:
                    pass
            if org_uuids:
                query = query.filter(JobTemplate.organization_id.in_(org_uuids))
        
        if script_type:
            query = query.filter(JobTemplate.script_type.in_(script_type))
        
        # Apply boolean filter
        if is_active is not None:
            query = query.filter(JobTemplate.is_active == is_active)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        job_templates = query.offset(skip).limit(limit).all()

        template_responses = [
            JobTemplateResponse.model_validate(template) for template in job_templates
        ]
        return JobTemplateListResponse(
            job_templates=template_responses,
            total=total,
            page=skip // limit + 1,
            limit=limit,
        )

    def get_job_template(self, job_template_id: str) -> Optional[JobTemplateResponse]:
        """Get a specific job template by ID"""
        try:
            try:
                template_uuid = uuid.UUID(job_template_id)
            except Exception:
                template_uuid = job_template_id
            
            template = (
                self.db.query(JobTemplate)
                .filter(JobTemplate.id == template_uuid)
                .first()
            )
            if template:
                return JobTemplateResponse.model_validate(template)
            return None
        except ValueError:
            return None

    def create_job_template(
        self, job_template: JobTemplateCreate, created_by_user_id: Optional[str] = None
    ) -> JobTemplateResponse:
        """Create a new job template"""
        try:
            created_by_uuid = None
            if created_by_user_id:
                created_by_uuid = uuid.UUID(created_by_user_id)

            db_template = JobTemplate(
                title=job_template.title,
                description=job_template.description,
                script_type=job_template.script_type,
                script_content=job_template.script_content,
                script_path=job_template.script_path,
                parameters_schema=job_template.parameters_schema,
                is_active=job_template.is_active,
                created_by=created_by_uuid,
            )

            self.db.add(db_template)
            self.db.commit()
            self.db.refresh(db_template)
            return JobTemplateResponse.model_validate(db_template)
        except IntegrityError:
            self.db.rollback()
            raise ValueError("Job template with this title already exists")

    def update_job_template(
        self, job_template_id: str, job_template: JobTemplateUpdate
    ) -> Optional[JobTemplateResponse]:
        """Update a job template"""
        try:
            try:
                template_uuid = uuid.UUID(job_template_id)
            except Exception:
                template_uuid = job_template_id
            
            db_template = (
                self.db.query(JobTemplate)
                .filter(JobTemplate.id == template_uuid)
                .first()
            )

            if not db_template:
                return None

            # Update fields if provided
            if job_template.title is not None:
                db_template.title = job_template.title  # type: ignore
            if job_template.description is not None:
                db_template.description = job_template.description  # type: ignore
            if job_template.script_type is not None:
                db_template.script_type = job_template.script_type  # type: ignore
            if job_template.script_content is not None:
                db_template.script_content = job_template.script_content  # type: ignore
            if job_template.script_path is not None:
                db_template.script_path = job_template.script_path  # type: ignore
            if job_template.parameters_schema is not None:
                db_template.parameters_schema = job_template.parameters_schema  # type: ignore
            if job_template.is_active is not None:
                db_template.is_active = job_template.is_active  # type: ignore

            try:
                self.db.commit()
                self.db.refresh(db_template)
                return JobTemplateResponse.model_validate(db_template)
            except IntegrityError:
                self.db.rollback()
                raise ValueError("Job template with this title already exists")

        except ValueError:
            return None

    def delete_job_template(self, job_template_id: str) -> bool:
        """Delete a job template"""
        try:
            try:
                template_uuid = uuid.UUID(job_template_id)
            except Exception:
                template_uuid = job_template_id
            
            db_template = (
                self.db.query(JobTemplate)
                .filter(JobTemplate.id == template_uuid)
                .first()
            )

            if not db_template:
                return False

            self.db.delete(db_template)
            self.db.commit()
            return True

        except ValueError:
            return False
