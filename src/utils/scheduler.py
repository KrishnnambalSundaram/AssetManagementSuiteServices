import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from croniter import croniter

from src.models.job import Job
from src.models.job_execution import JobExecution
from src.models.job_template import JobTemplate
from src.modules.job_notification.service import JobNotificationService
from src.utils.database import SessionLocal

logger = logging.getLogger(__name__)


class JobScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.running_jobs: Dict[str, Any] = {}

    async def start(self):
        """Start the scheduler and load existing jobs"""
        try:

            # Start the scheduler
            self.scheduler.start()
            logger.info("Job scheduler started successfully")

            # Load and schedule existing jobs
            await self.load_existing_jobs()

        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise

    async def stop(self):
        """Stop the scheduler"""
        try:
            self.scheduler.shutdown()
            logger.info("Job scheduler stopped successfully")
        except Exception as e:
            logger.error(f"Failed to stop scheduler: {e}")

    async def load_existing_jobs(self):
        """Load all active jobs from database and schedule them"""
        db = SessionLocal()
        try:
            # Get all active jobs
            jobs = db.query(Job).filter(Job.status == "running").all()

            for job in jobs:
                await self.schedule_job(job)

            logger.info(f"Loaded {len(jobs)} existing jobs")

        except Exception as e:
            logger.error(f"Failed to load existing jobs: {e}")
        finally:
            db.close()

    async def schedule_job(self, job: Job):
        """Schedule a job based on its trigger type"""
        try:
            job_id = str(job.id)

            # Only schedule jobs with status "running"
            if job.status != "running":  # type: ignore
                logger.info(f"Job {job_id} is not running (status: {job.status}), removing from scheduler if exists")
                # Remove from scheduler if it exists
                if job_id in self.running_jobs:
                    try:
                        self.scheduler.remove_job(job_id)
                    except Exception:
                        pass  # Job might not exist in scheduler
                    del self.running_jobs[job_id]
                return

            # Remove existing job if it's already scheduled
            if job_id in self.running_jobs:
                self.scheduler.remove_job(job_id)
                del self.running_jobs[job_id]

            # Schedule based on trigger type
            if job.trigger_type == "manual":  # type: ignore
                logger.info(f"Manual job {job_id} registered (not scheduled)")
                return

            elif job.trigger_type == "frequency":  # type: ignore
                await self._schedule_frequency_job(job)

            elif job.trigger_type == "cron":  # type: ignore
                await self._schedule_cron_job(job)

            else:
                logger.warning(
                    f"Unknown trigger type '{job.trigger_type}' for job {job_id}"
                )

        except Exception as e:
            logger.error(f"Failed to schedule job {job.id}: {e}")

    async def _schedule_frequency_job(self, job: Job):
        """Schedule a frequency-based job"""
        job_id = str(job.id)

        if not all(
            [job.frequency_interval is not None, job.frequency_unit is not None]
        ):
            logger.warning(f"Frequency job {job_id} missing interval or unit")
            return

        # Convert frequency to seconds
        interval_seconds = self._get_interval_seconds(
            int(job.frequency_interval),  # type: ignore
            str(job.frequency_unit),  # type: ignore
        )

        # Create interval trigger
        trigger = IntervalTrigger(
            seconds=interval_seconds, end_date=job.frequency_end_time  # type: ignore
        )

        # Add job to scheduler
        self.scheduler.add_job(
            func=self._execute_job,
            trigger=trigger,
            args=[job_id],
            id=job_id,
            max_instances=1,
            replace_existing=True,
        )

        self.running_jobs[job_id] = job
        logger.info(
            f"Scheduled frequency job {job_id} with {interval_seconds}s interval"
        )

    async def _schedule_cron_job(self, job: Job):
        """Schedule a cron-based job"""
        job_id = str(job.id)

        if job.cron_expression is None:
            logger.warning(f"Cron job {job_id} missing cron expression")
            return

        try:
            # Validate cron expression
            croniter(job.cron_expression)  # type: ignore

            # Create cron trigger
            trigger = CronTrigger.from_crontab(str(job.cron_expression))  # type: ignore

            # Add job to scheduler
            self.scheduler.add_job(
                func=self._execute_job,
                trigger=trigger,
                args=[job_id],
                id=job_id,
                max_instances=1,
                replace_existing=True,
            )

            self.running_jobs[job_id] = job
            logger.info(
                f"Scheduled cron job {job_id} with expression: {job.cron_expression}"
            )

        except Exception as e:
            logger.error(f"Invalid cron expression for job {job_id}: {e}")

    def _get_interval_seconds(self, interval: int, unit: str) -> int:
        """Convert frequency interval to seconds"""
        unit_multipliers = {
            "seconds": 1,
            "minutes": 60,
            "hours": 3600,
            "days": 86400,
            "weeks": 604800,
        }

        return interval * unit_multipliers.get(unit, 1)

    async def _execute_job(self, job_id: str):
        """Execute a job"""
        db = SessionLocal()
        try:
            # Get job from database
            job = db.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
            if not job:
                logger.error(f"Job {job_id} not found")
                return

            # Check if job is still active
            if job.status != "running":  # type: ignore
                logger.info(f"Job {job_id} is not running, skipping execution")
                return

            # Get job template
            template = (
                db.query(JobTemplate).filter(JobTemplate.id == job.template_id).first()
            )
            if not template:
                logger.error(f"Template not found for job {job_id}")
                return

            # Create execution record
            execution = JobExecution(
                job_id=job.id, status="running", started_at=datetime.now(timezone.utc)
            )
            db.add(execution)
            db.commit()
            db.refresh(execution)

            logger.info(f"Starting execution of job {job_id}")

            # Execute the job
            try:
                await self._run_job_script(job, template, execution)
            except Exception as e:
                logger.error(f"Job {job_id} failed: {e}")

        except Exception as e:
            logger.error(f"Error executing job {job_id}: {e}")
        finally:
            db.close()

    async def _run_job_script(
        self, job: Job, template: JobTemplate, execution: JobExecution
    ) -> Dict[str, Any]:
        """Run the actual job script"""
        if template.script_type == "predefined":  # type: ignore
            await self._execute_predefined_script(job, template, execution)
        else:
            logger.error(f"Script type {template.script_type} not supported")

    async def _execute_predefined_script(
        self, job: Job, template: JobTemplate, execution: JobExecution
    ) -> Dict[str, Any]:
        """Execute a predefined script"""
        try:
            # For now, we'll just log the script
            logger.info(f"Executing predefined script for job {job.id}")
            # run script from script_path
            script_path = template.script_path  # type: ignore
            params_str = f" --job_id {job.id} --execution_id {execution.id}"
            if script_path:  # type: ignore
                # run script from script_path
                result = await asyncio.to_thread(
                    os.system, f"python src/scripts/{script_path}.py {params_str}"
                )
                return result
            else:
                logger.error(f"Script path not found for job {job.id}")
                return {"message": "Script path not found"}

        except Exception as e:
            logger.error(f"Script execution failed for job {job.id}: {e}")
            raise

    async def _send_notifications(
        self, job_id: str, trigger_type: str, result: Dict[str, Any]
    ):
        """Send notifications for job completion"""
        try:
            db = SessionLocal()
            notification_service = JobNotificationService(db)

            # Get notifications for this job
            notifications = notification_service.get_notifications_by_job(job_id)

            for notification in notifications:
                if notification.trigger_on in [trigger_type, "both"] and notification.is_active:  # type: ignore
                    await self._send_notification(notification, result)

        except Exception as e:
            logger.error(f"Failed to send notifications for job {job_id}: {e}")
        finally:
            db.close()

    async def _send_notification(self, notification, result: Dict[str, Any]):
        """Send a single notification"""
        try:
            # For now, we'll just log the notification
            # In a real implementation, you would:
            # 1. Send email notifications
            # 2. Send webhook notifications
            # 3. Send Slack/Discord notifications
            # 4. etc.

            logger.info(
                f"Notification sent: {notification.notification_type} to {notification.configuration}"
            )

        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    async def add_job(self, job: Job):
        """Add a new job to the scheduler"""
        await self.schedule_job(job)

    async def update_job(self, job: Job):
        """Update an existing job in the scheduler"""
        await self.schedule_job(job)

    async def remove_job(self, job_id: str):
        """Remove a job from the scheduler"""
        try:
            if job_id in self.running_jobs:
                self.scheduler.remove_job(job_id)
                del self.running_jobs[job_id]
                logger.info(f"Removed job {job_id} from scheduler")
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}: {e}")

    async def run_job_manually(self, job_id: str):
        """Manually trigger a job execution"""
        db = SessionLocal()
        try:
            await self._execute_job(job_id)
        except Exception as e:
            logger.error(f"Failed to run job {job_id}: {e}")
        finally:
            db.close()

    def get_scheduled_jobs(self) -> Dict[str, Any]:
        """Get all currently scheduled jobs"""
        return {
            job_id: {
                "id": job_id,
                "title": job.title,
                "trigger_type": job.trigger_type,
                "status": job.status,
            }
            for job_id, job in self.running_jobs.items()
        }


# Global scheduler instance
scheduler = JobScheduler()


async def start_scheduler():
    """Start the job scheduler"""
    await scheduler.start()


async def stop_scheduler():
    """Stop the job scheduler"""
    await scheduler.stop()
