import uuid
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.job import Job
from src.models.job_notification import JobNotification
from src.modules.job_notification.schema import (JobNotificationCreate,
                                                 JobNotificationResponse,
                                                 JobNotificationUpdate,
                                                 JobNotificationListResponse)


class JobNotificationService:
    def __init__(self, db: Session):
        self.db = db

    def get_job_notifications(
        self, skip: int = 0, limit: int = 100
    ) -> JobNotificationListResponse:
        """Get all job notifications with pagination"""
        notifications = self.db.query(JobNotification).offset(skip).limit(limit).all()
        total = self.db.query(JobNotification).count()

        notification_responses = [
            JobNotificationResponse.model_validate(notification)
            for notification in notifications
        ]
        return JobNotificationListResponse(
            notifications=notification_responses,
            total=total,
            page=skip // limit + 1,
            limit=limit,
        )

    def get_job_notification(self, notification_id: str) -> Optional[JobNotificationResponse]:
        """Get a specific job notification by ID"""
        try:
            try:
                notification_uuid = uuid.UUID(notification_id)
            except Exception:
                notification_uuid = notification_id
            
            notification = (
                self.db.query(JobNotification)
                .filter(JobNotification.id == notification_uuid)
                .first()
            )
            if notification:
                return JobNotificationResponse.model_validate(notification)
            return None
        except ValueError:
            return None

    def create_job_notification(
        self, notification: JobNotificationCreate, created_by_user_id: Optional[str] = None
    ) -> JobNotificationResponse:
        """Create a new job notification"""
        try:
            try:
                job_id = uuid.UUID(notification.job_id)
            except Exception:
                job_id = notification.job_id

            db_notification = JobNotification(
                job_id=job_id,
                notification_type=notification.notification_type,
                configuration=notification.configuration,
                is_active=notification.is_active,
                trigger_on=notification.trigger_on,
            )

            self.db.add(db_notification)
            self.db.commit()
            self.db.refresh(db_notification)
            return JobNotificationResponse.model_validate(db_notification)
        except IntegrityError as e:
            self.db.rollback()
            raise ValueError("Job notification with this configuration already exists")
        except Exception as e:
            return f'Error creating job notification {e}'

    def update_job_notification(
        self, notification_id: str, notification: JobNotificationUpdate
    ) -> Optional[JobNotificationResponse]:
        """Update a job notification"""
        try:
            try:
                notification_uuid = uuid.UUID(notification_id)
                job_id = uuid.UUID(notification.job_id)
            except Exception as e:
                notification_uuid = notification_id
                job_id = notification.job_id

            db_notification = (
                self.db.query(JobNotification)
                .filter(JobNotification.id == notification_uuid)
                .first()
            )

            if not db_notification:
                return None

            

            # Update fields if provided
            if notification.job_id is not None:
                db_notification.job_id = job_id
            if notification.notification_type is not None:
                db_notification.notification_type = notification.notification_type
            if notification.configuration is not None:
                db_notification.configuration = notification.configuration
            if notification.is_active is not None:
                db_notification.is_active = notification.is_active

            try:
                self.db.commit()
                self.db.refresh(db_notification)
                return JobNotificationResponse.model_validate(db_notification)
            except IntegrityError:
                self.db.rollback()
                raise ValueError("Job notification with this configuration already exists")

        except ValueError:
            return None

    def delete_job_notification(self, notification_id: str) -> bool:
        """Delete a job notification"""
        try:
            try:
                notification_uuid = uuid.UUID(notification_id)
            except Exception:
                notification_uuid = notification_id
            
            db_notification = (
                self.db.query(JobNotification)
                .filter(JobNotification.id == notification_uuid)
                .first()
            )

            if not db_notification:
                return False

            self.db.delete(db_notification)
            self.db.commit()
            return True

        except ValueError:
            return False

    def toggle_notification_status(
        self, notification_id: str
    ) -> Optional[JobNotificationResponse]:
        """Toggle the active status of a job notification"""
        try:
            try:
                notification_uuid = uuid.UUID(notification_id)
            except Exception:
                notification_uuid = notification_id
            
            db_notification = (
                self.db.query(JobNotification)
                .filter(JobNotification.id == notification_uuid)
                .first()
            )

            if not db_notification:
                return None

            db_notification.is_active = not db_notification.is_active  # type: ignore

            self.db.commit()
            self.db.refresh(db_notification)
            return JobNotificationResponse.from_orm(db_notification)

        except ValueError:
            return None

    def get_notifications_by_job(self, job_id: str) -> List[JobNotificationResponse]:
        """Get all notifications for a specific job"""
        try:
            try:
                job_uuid = uuid.UUID(job_id)
            except Exception as e:
                job_uuid = job_id

            notifications = (
                self.db.query(JobNotification)
                .filter(JobNotification.job_id == job_uuid)
                .all()
            )
            try:
                return [JobNotificationResponse.model_validate(n) for n in notifications]
            except Exception as e:
                print(e)
                return []
        except ValueError:
            return []
        except Exception as e:
            print(e)
            return []
