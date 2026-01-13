import uuid
from typing import Optional, List
from datetime import datetime
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.job import Job
from src.models.job_notification import JobNotification
from src.models.job_template import JobTemplate
from src.modules.job.schema import (JobCreate, JobListResponse, JobResponse,
                                    JobUpdate)
from src.modules.job_notification.schema import JobNotificationResponse
from src.modules.job_template.schema import JobTemplateResponse
from src.modules.job_execution.service import JobExecutionService
from src.modules.organization.schema import OrganizationResponse
from src.models.organization import Organization
from src.utils.scheduler import scheduler
from src.utils.constants import PREDEFINED_SCRIPTS

logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, db: Session):
        self.db = db

    def _build_job_response(self, job: Job) -> JobResponse:
        """Helper method to build JobResponse with related data"""
        # Get related data
        template = job.template
        notifications = job.notifications
        organization = job.organization

        # Build response
        job_response = JobResponse.model_validate(job)
        job_response.template = (
            JobTemplateResponse.model_validate(template) if template else None
        )
        job_response.notifications = [
            JobNotificationResponse.model_validate(n) for n in notifications
        ]
        job_response.organization = (
            OrganizationResponse.model_validate(organization) if organization else None
        )

        return job_response

    def get_jobs(
        self, 
        skip: int = 0, 
        limit: int = 100,
        title_search: Optional[str] = None,
        template_id: Optional[List[str]] = None,
        organization_id: Optional[List[str]] = None,
        status: Optional[List[str]] = None,
        trigger_type: Optional[List[str]] = None,
        frequency_unit: Optional[List[str]] = None,
        frequency_interval_operator: Optional[str] = None,
        frequency_interval_value: Optional[int] = None,
        frequency_count_operator: Optional[str] = None,
        frequency_count_value: Optional[int] = None,
        frequency_end_time_operator: Optional[str] = None,
        frequency_end_time_value: Optional[datetime] = None,
        timeout_seconds_operator: Optional[str] = None,
        timeout_seconds_value: Optional[int] = None,
        max_retries_operator: Optional[str] = None,
        max_retries_value: Optional[int] = None
    ) -> JobListResponse:
        """Get all jobs with pagination and filters"""
        query = self.db.query(Job)
        
        # Apply regex search on title
        if title_search:
            query = query.filter(Job.title.ilike(f"%{title_search}%"))
        
        # Apply array filters for IDs and enums
        if template_id:
            template_uuids = []
            for tid in template_id:
                try:
                    template_uuids.append(uuid.UUID(tid))
                except ValueError:
                    pass
            if template_uuids:
                query = query.filter(Job.template_id.in_(template_uuids))
        
        if organization_id:
            org_uuids = []
            for oid in organization_id:
                try:
                    org_uuids.append(uuid.UUID(oid))
                except ValueError:
                    pass
            if org_uuids:
                query = query.filter(Job.organization_id.in_(org_uuids))
        
        if status:
            query = query.filter(Job.status.in_(status))
        
        if trigger_type:
            query = query.filter(Job.trigger_type.in_(trigger_type))
        
        if frequency_unit:
            query = query.filter(Job.frequency_unit.in_(frequency_unit))
        
        # Apply numeric filters with operator pattern
        if frequency_interval_operator and frequency_interval_value is not None:
            if frequency_interval_operator == 'lt':
                query = query.filter(Job.frequency_interval < frequency_interval_value)
            elif frequency_interval_operator == 'gt':
                query = query.filter(Job.frequency_interval > frequency_interval_value)
            elif frequency_interval_operator == 'lte':
                query = query.filter(Job.frequency_interval <= frequency_interval_value)
            elif frequency_interval_operator == 'gte':
                query = query.filter(Job.frequency_interval >= frequency_interval_value)
            elif frequency_interval_operator == 'eq':
                query = query.filter(Job.frequency_interval == frequency_interval_value)
            elif frequency_interval_operator == 'ne':
                query = query.filter(Job.frequency_interval != frequency_interval_value)
        
        if frequency_count_operator and frequency_count_value is not None:
            if frequency_count_operator == 'lt':
                query = query.filter(Job.frequency_count < frequency_count_value)
            elif frequency_count_operator == 'gt':
                query = query.filter(Job.frequency_count > frequency_count_value)
            elif frequency_count_operator == 'lte':
                query = query.filter(Job.frequency_count <= frequency_count_value)
            elif frequency_count_operator == 'gte':
                query = query.filter(Job.frequency_count >= frequency_count_value)
            elif frequency_count_operator == 'eq':
                query = query.filter(Job.frequency_count == frequency_count_value)
            elif frequency_count_operator == 'ne':
                query = query.filter(Job.frequency_count != frequency_count_value)
        
        if timeout_seconds_operator and timeout_seconds_value is not None:
            if timeout_seconds_operator == 'lt':
                query = query.filter(Job.timeout_seconds < timeout_seconds_value)
            elif timeout_seconds_operator == 'gt':
                query = query.filter(Job.timeout_seconds > timeout_seconds_value)
            elif timeout_seconds_operator == 'lte':
                query = query.filter(Job.timeout_seconds <= timeout_seconds_value)
            elif timeout_seconds_operator == 'gte':
                query = query.filter(Job.timeout_seconds >= timeout_seconds_value)
            elif timeout_seconds_operator == 'eq':
                query = query.filter(Job.timeout_seconds == timeout_seconds_value)
            elif timeout_seconds_operator == 'ne':
                query = query.filter(Job.timeout_seconds != timeout_seconds_value)
        
        if max_retries_operator and max_retries_value is not None:
            if max_retries_operator == 'lt':
                query = query.filter(Job.max_retries < max_retries_value)
            elif max_retries_operator == 'gt':
                query = query.filter(Job.max_retries > max_retries_value)
            elif max_retries_operator == 'lte':
                query = query.filter(Job.max_retries <= max_retries_value)
            elif max_retries_operator == 'gte':
                query = query.filter(Job.max_retries >= max_retries_value)
            elif max_retries_operator == 'eq':
                query = query.filter(Job.max_retries == max_retries_value)
            elif max_retries_operator == 'ne':
                query = query.filter(Job.max_retries != max_retries_value)
        
        # Apply datetime filters with operator pattern
        if frequency_end_time_operator and frequency_end_time_value:
            if frequency_end_time_operator == 'lt':
                query = query.filter(Job.frequency_end_time < frequency_end_time_value)
            elif frequency_end_time_operator == 'gt':
                query = query.filter(Job.frequency_end_time > frequency_end_time_value)
            elif frequency_end_time_operator == 'lte':
                query = query.filter(Job.frequency_end_time <= frequency_end_time_value)
            elif frequency_end_time_operator == 'gte':
                query = query.filter(Job.frequency_end_time >= frequency_end_time_value)
            elif frequency_end_time_operator == 'eq':
                query = query.filter(Job.frequency_end_time == frequency_end_time_value)
            elif frequency_end_time_operator == 'ne':
                query = query.filter(Job.frequency_end_time != frequency_end_time_value)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        jobs = query.offset(skip).limit(limit).all()

        job_responses = []
        for job in jobs:
            # Get related data
            template = job.template
            notifications = job.notifications
            organization = job.organization

            # Build response
            job_response = JobResponse.model_validate(job)
            job_response.template = (
                JobTemplateResponse.model_validate(template) if template else None
            )
            job_response.notifications = [
                JobNotificationResponse.model_validate(n) for n in notifications
            ]
            job_response.organization = (
                OrganizationResponse.model_validate(organization) if organization else None
            )

            job_responses.append(job_response)

        return JobListResponse(
            jobs=job_responses,
            total=total,
            page=skip // limit + 1,
            limit=limit,
        )

    def get_job(self, job_id: str) -> Optional[JobResponse]:
        """Get a specific job by ID"""
        try:
            try:
                job_uuid = uuid.UUID(job_id)
            except Exception:
                job_uuid = job_id
            
            job = self.db.query(Job).filter(Job.id == job_uuid).first()
            if job:
                return self._build_job_response(job)
            return None
        except ValueError:
            return None

    def create_job(
        self, job: JobCreate, created_by_user_id: Optional[str] = None
    ) -> JobResponse:
        """Create a new job"""
        logger.info(f"Starting job creation process for job: {job.title}")
        logger.info(f"Job data: template_id={job.template_id}, organization_id={job.organization_id}")
        
        try:
            created_by_uuid = None
            if created_by_user_id:
                created_by_uuid = uuid.UUID(created_by_user_id)
                logger.info(f"Created by user UUID: {created_by_uuid}")

            # Handle template_id - could be UUID or script path
            template_uuid = None
            try:
                # Try to convert to UUID first
                template_uuid = uuid.UUID(job.template_id)
                logger.info(f"Template ID is UUID: {template_uuid}")
            except ValueError:
                logger.info(f"Template ID is script path: {job.template_id}. Finding or creating template...")
                # If not a valid UUID, treat as script path and find/create template
                template = self._find_or_create_template_from_script_path(job.template_id, job.organization_id)
                if template:
                    template_uuid = template.id
                    logger.info(f"Found/created template with UUID: {template_uuid}")
                else:
                    logger.error(f"Template not found for script path: {job.template_id}")
                    raise ValueError(f"Template not found for script path: {job.template_id}")

            # Convert organization_id to UUID if provided and validate it exists
            organization_uuid = None
            logger.info(f"Processing organization_id: {job.organization_id}")
            try:
                organization_uuid = uuid.UUID(job.organization_id)
                logger.info(f"Organization ID converted to UUID: {organization_uuid}")
            except Exception as e:
                organization_uuid = job.organization_id
                logger.warning(f"Could not convert organization_id to UUID: {e}, using as-is: {organization_uuid}")
            
            # Verify the organization exists
            logger.info(f"Checking if organization exists: {organization_uuid}")
            existing_org = self.db.query(Organization).filter(Organization.id == organization_uuid).first()
            if not existing_org:
                logger.error(f"Organization with ID {organization_uuid} does not exist in database")
                # Let's also check what organizations do exist
                all_orgs = self.db.query(Organization).all()
                logger.error(f"Available organizations: {[(org.id, org.name if hasattr(org, 'name') else 'no name') for org in all_orgs]}")
                raise ValueError(f"Organization with ID {organization_uuid} does not exist")
            else:
                logger.info(f"Organization found: ID={existing_org.id}, Name={getattr(existing_org, 'name', 'no name')}")

            logger.info("Creating job object...")
            db_job = Job(
                title=job.title,
                template_id=template_uuid,
                organization_id=organization_uuid,
                parameters=job.parameters,
                status=job.status,
                trigger_type=job.trigger_type,
                frequency_interval=job.frequency_interval,
                frequency_unit=job.frequency_unit,
                frequency_count=job.frequency_count,
                frequency_end_time=job.frequency_end_time,
                cron_expression=job.cron_expression,
                timeout_seconds=job.timeout_seconds,
                max_retries=job.max_retries,
                created_by=created_by_uuid,
            )
            logger.info("Adding job to database session...")
            self.db.add(db_job)
            logger.info("Committing job to database...")
            self.db.commit()
            logger.info("Refreshing job object...")
            self.db.refresh(db_job)
            logger.info(f"Job created successfully with ID: {db_job.id}")
            return JobResponse.model_validate(db_job)
        except IntegrityError as e:
            logger.error(f"IntegrityError during job creation: {str(e)}")
            self.db.rollback()
            raise ValueError(f"Job with this title already exists, {e}")
        except Exception as e:
            logger.error(f"Unexpected error during job creation: {str(e)}")
            self.db.rollback()
            raise

    def update_job(
        self, job_id: str, job: JobUpdate
    ) -> Optional[JobResponse]:
        """Update a job"""
        try:
            try:
                job_uuid = uuid.UUID(job_id)
            except Exception:
                job_uuid = job_id
            
            db_job = self.db.query(Job).filter(Job.id == job_uuid).first()

            if not db_job:
                return None

            # Update fields if provided
            if job.title is not None:
                db_job.title = job.title
            if job.parameters is not None:
                db_job.parameters = job.parameters
            if job.status is not None:
                db_job.status = job.status
            if job.trigger_type is not None:
                db_job.trigger_type = job.trigger_type
            if job.frequency_interval is not None:
                db_job.frequency_interval = job.frequency_interval
            if job.frequency_unit is not None:
                db_job.frequency_unit = job.frequency_unit
            if job.frequency_count is not None:
                db_job.frequency_count = job.frequency_count
            if job.frequency_end_time is not None:
                db_job.frequency_end_time = job.frequency_end_time
            if job.cron_expression is not None:
                db_job.cron_expression = job.cron_expression
            if job.timeout_seconds is not None:
                db_job.timeout_seconds = job.timeout_seconds
            if job.max_retries is not None:
                db_job.max_retries = job.max_retries

            try:
                self.db.commit()
                self.db.refresh(db_job)
                return JobResponse.model_validate(db_job)
            except IntegrityError:
                self.db.rollback()
                raise ValueError("Job with this title already exists")

        except ValueError:
            return None

    def delete_job(self, job_id: str) -> bool:
        """Delete a job"""
        try:
            try:
                job_uuid = uuid.UUID(job_id)
            except Exception:
                job_uuid = job_id
            
            db_job = self.db.query(Job).filter(Job.id == job_uuid).first()

            if not db_job:
                return False

            self.db.delete(db_job)
            self.db.commit()
            return True

        except ValueError:
            return False
    
    def trigger_job(self, job_id: str) -> bool:
        """Trigger a job"""
        job = self.get_job(job_id)
        if not job:
            return False
        return True


    def _find_or_create_template_from_script_path(self, script_path: str, organization_id: Optional[str] = None) -> Optional[JobTemplate]:
        """Find existing template by script path or create new one from predefined script"""
        logger.info(f"Finding or creating template for script_path: {script_path}, organization_id: {organization_id}")
        
        # First, try to find existing template with this script path
        try:
            template_query = self.db.query(JobTemplate).filter(JobTemplate.script_path == script_path)
            try:
                org_uuid = uuid.UUID(organization_id)
                logger.info(f"Organization ID converted to UUID for template search: {org_uuid}")
            except Exception as e:
                org_uuid = organization_id
                logger.warning(f"Could not convert organization_id to UUID for template search: {e}, using as-is: {org_uuid}")
            
            template_query = template_query.filter(JobTemplate.organization_id == org_uuid)
            template = template_query.first()
            if template:
                logger.info(f"Found existing template: {template.id}")
                return template

            # If not found, try to create from predefined script
            logger.info("Existing template not found, creating from predefined script...")
            try:
                new_template = self._create_job_template_from_predefined_script(script_path, organization_id)
                logger.info(f"Created new template: {new_template.id}")
                return new_template
            except ValueError as e:
                logger.error(f"Failed to create template from predefined script: {e}")
                return None
        except ValueError as e:
            logger.error(f"Error in template find/create process: {e}")
            return None

    def _create_job_template_from_predefined_script(self, script_path: str, organization_id: Optional[str] = None) -> JobTemplate:
        """Create a job template from a predefined script"""
        logger.info(f"Creating job template from predefined script: {script_path}, organization_id: {organization_id}")
        
        predefined_script = next((script for script in PREDEFINED_SCRIPTS if script["script"] == script_path), None)
        if not predefined_script:
            logger.error(f"Predefined script not found: {script_path}")
            raise ValueError(f"Predefined script not found: {script_path}")
        
        logger.info(f"Found predefined script: {predefined_script['name']}")
        
        # Convert organization_id to UUID if provided and validate it exists
        org_uuid = None
        if organization_id:
            if isinstance(organization_id, str):
                try:
                    org_uuid = uuid.UUID(organization_id)
                    logger.info(f"Organization ID converted to UUID for template creation: {org_uuid}")
                except ValueError as e:
                    logger.error(f"Invalid organization_id format: {organization_id}, error: {e}")
                    raise ValueError(f"Invalid organization_id format: {organization_id}")
            else:
                org_uuid = organization_id
                logger.info(f"Organization ID used as-is for template creation: {org_uuid}")
            
            # Verify the organization exists
            logger.info(f"Verifying organization exists for template creation: {org_uuid}")
            existing_org = self.db.query(Organization).filter(Organization.id == org_uuid).first()
            if not existing_org:
                logger.error(f"Organization with ID {org_uuid} does not exist for template creation")
                # Let's also check what organizations do exist
                all_orgs = self.db.query(Organization).all()
                logger.error(f"Available organizations for template: {[(org.id, getattr(org, 'name', 'no name')) for org in all_orgs]}")
                raise ValueError(f"Organization with ID {org_uuid} does not exist")
            else:
                logger.info(f"Organization verified for template creation: ID={existing_org.id}, Name={getattr(existing_org, 'name', 'no name')}")
        
        logger.info("Building parameters schema...")
        parameters_schema = {}
        for parameter in predefined_script["parameters"]:
            parameters_schema[parameter["name"]] = parameter["type"]
        logger.info(f"Parameters schema: {parameters_schema}")
        
        logger.info("Creating JobTemplate object...")
        template = JobTemplate(
            title=predefined_script["name"],
            description=predefined_script["description"],
            organization_id=org_uuid,
            script_type="predefined",
            script_path=predefined_script["script"],
            parameters_schema=parameters_schema,
            is_active=True,
        )
        
        logger.info("Adding template to database session...")
        self.db.add(template)
        logger.info("Committing template to database...")
        try:
            self.db.commit()
            logger.info("Template committed successfully")
            self.db.refresh(template)
            logger.info(f"Template created successfully with ID: {template.id}")
            return template
        except IntegrityError as e:
            logger.error(f"IntegrityError during template creation: {str(e)}")
            self.db.rollback()
            raise ValueError(f"Failed to create template: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during template creation: {str(e)}")
            self.db.rollback()
            raise
