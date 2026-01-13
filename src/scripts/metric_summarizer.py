import argparse
import csv
import io
import logging
import os
import re
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
# flake8: noqa: E402
from src.models.job import Job
from src.models.job_execution import JobExecution
from src.models.metric_temp import MetricTemp
from src.models.meter_usage import MeterUsage
from src.models.organization import Organization
from src.utils.config import settings
from src.utils.database import engine
from src.utils.informatica import InformaticaUtils
from src.utils.notify import export_to_excel, send_email_with_attachment

logger = logging.getLogger(__name__)


class MetricSummarizerManager:
    # Job execution
    job_id: str
    execution_id: str
    job: Optional[Job]

    # Informatica credentials
    domain_url: Optional[str]
    username: str
    password: str
    organization_identifier: str

    # Job parameters
    frequency: str  # 'daily', 'weekly', 'monthly'
    change_threshold: float

    # Date ranges
    start_date: datetime
    end_date: datetime
    previous_start_date: datetime
    previous_end_date: datetime

    # Metric temp record
    metric_temp: Optional[MetricTemp]

    def __init__(self, job_id: str, execution_id: str) -> None:
        # Job execution
        self.job_id = job_id
        self.execution_id = execution_id
        self.job: Optional[Job] = None

        # Informatica credentials
        self.domain_url: Optional[str] = None
        self.username: str = ""
        self.password: str = ""
        self.organization_identifier: str = ""

        # Job parameters
        self.frequency: str = "daily"
        self.change_threshold: float = 10.0

        # Date ranges
        self.start_date = datetime.now(timezone.utc)
        self.end_date = datetime.now(timezone.utc)
        self.previous_start_date = datetime.now(timezone.utc)
        self.previous_end_date = datetime.now(timezone.utc)

        # Metric temp record
        self.metric_temp: Optional[MetricTemp] = None

        self.get_config(job_id)
        self.calculate_date_ranges()

    def get_config(self, job_id: str) -> bool:
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            self.job = db.query(Job).filter(Job.id == job_id).first()
            if not self.job:
                raise Exception(f"Job {job_id} not found")
            logger.info(f"Job {job_id} found, organization: {self.job.organization_id}")
            organization = (
                db.query(Organization)
                .filter(Organization.id == self.job.organization_id)
                .first()
            )
            if not organization:
                raise Exception(f"Organization {self.job.organization_id} not found")
            self.domain_url = organization.domain
            self.username = organization.username
            self.password = organization.password
            self.organization_identifier = organization.identifier

            # Get job parameters
            self.frequency = self.job.parameters.get("frequency", "daily")
            self.change_threshold = float(
                self.job.parameters.get("change_threshold", 10.0)
            )

            if self.frequency not in ["daily", "weekly", "monthly"]:
                raise ValueError(
                    f"Invalid frequency: {self.frequency}. Must be 'daily', 'weekly', or 'monthly'"
                )

            return True
        except Exception as e:
            logger.error(f"Error getting config: {e}")
            return False
        finally:
            db.close()

    def calculate_date_ranges(self) -> None:
        """Calculate start and end dates based on frequency"""
        now = datetime.now(timezone.utc)

        if self.frequency == "daily":
            # Current date (00:00:00Z – 23:59:59Z)
            self.start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self.end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            # Previous day
            self.previous_start_date = (self.start_date - timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            self.previous_end_date = (self.end_date - timedelta(days=1)).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )

        elif self.frequency == "weekly":
            # Last 7 days
            self.end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            self.start_date = (self.end_date - timedelta(days=6)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            # Previous 7 days
            self.previous_end_date = (self.start_date - timedelta(seconds=1)).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
            self.previous_start_date = (self.previous_end_date - timedelta(days=6)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        elif self.frequency == "monthly":
            # Last 1 month (30 days)
            self.end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            self.start_date = (self.end_date - timedelta(days=29)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            # Previous month (30 days)
            self.previous_end_date = (self.start_date - timedelta(seconds=1)).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
            self.previous_start_date = (self.previous_end_date - timedelta(days=29)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        logger.info(
            f"Date ranges calculated - Current: {self.start_date.isoformat()} to {self.end_date.isoformat()}, "
            f"Previous: {self.previous_start_date.isoformat()} to {self.previous_end_date.isoformat()}"
        )

    def update_job_execution(
        self,
        execution_id: str,
        status: str,
        result: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            execution = (
                db.query(JobExecution).filter(JobExecution.id == execution_id).first()
            )
            execution.status = status
            execution.completed_at = datetime.now(timezone.utc)
            if error_message:
                execution.error_message = error_message
            if result:
                execution.result = result
            db.commit()
            db.refresh(execution)
            return True
        except Exception as e:
            logger.error(f"Error updating job execution: {e}")
            return False
        finally:
            db.close()

    def create_metric_temp_record(self) -> Optional[MetricTemp]:
        """Create and persist metric_temp record"""
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            metric_temp = MetricTemp(
                internal_job_id=self.job_id,
                export_job_id=None,  # Will be updated when export job is created
                frequency=self.frequency,
                change_threshold=Decimal(str(self.change_threshold)),
                start_date=self.start_date,
                end_date=self.end_date,
                status="pending",
            )
            db.add(metric_temp)
            db.commit()
            db.refresh(metric_temp)
            logger.info(f"Created metric_temp record: {metric_temp.id}")
            return metric_temp
        except Exception as e:
            logger.error(f"Error creating metric_temp record: {e}")
            db.rollback()
            return None
        finally:
            db.close()

    def update_metric_temp_status(
        self, metric_temp_id: str, status: str, export_job_id: Optional[str] = None
    ) -> bool:
        """Update metric_temp record status"""
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            metric_temp = (
                db.query(MetricTemp).filter(MetricTemp.id == metric_temp_id).first()
            )
            if not metric_temp:
                logger.error(f"MetricTemp record {metric_temp_id} not found")
                return False
            metric_temp.status = status
            if export_job_id:
                metric_temp.export_job_id = export_job_id
            db.commit()
            db.refresh(metric_temp)
            return True
        except Exception as e:
            logger.error(f"Error updating metric_temp status: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    def trigger_export_metering_job(self) -> Optional[str]:
        """Trigger Export Metering Job and return export_job_id"""
        try:
            informatica_service = InformaticaUtils()
            informatica_service.set_credentials(
                username=self.username,
                password=self.password,
                domain_url=self.domain_url,
            )

            if not informatica_service.login(
                self.username, self.password, self.domain_url
            ):
                logger.error("Failed to login to Informatica")
                return None

            logger.info("Successfully logged in to Informatica")

            # Build callback URL (webhook endpoint)
            # Get base URL from environment variable or use default
            webhook_base_url = settings.WEBHOOK_BASE_URL
            callback_url = f"{webhook_base_url}/api/v1/webhooks/metric-summarizer"
            # Format dates in ISO UTC format
            start_date_iso = self.start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            end_date_iso = self.end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

            export_response = informatica_service.export_metering_data(
                start_date=start_date_iso,
                end_date=end_date_iso,
                callback_url=callback_url,
                job_type="SUMMARY",
                combined_meter_usage="TRUE",
                all_linked_orgs="TRUE",
            )

            if not export_response:
                logger.error("Failed to trigger export metering job")
                return None

            # Extract export jobId from response
            export_job_id = export_response.get("jobId") or export_response.get("id")
            if not export_job_id:
                logger.error("Could not extract export job ID from response")
                return None

            logger.info(f"Export metering job triggered successfully: {export_job_id}")
            return str(export_job_id)

        except Exception as e:
            logger.error(f"Error triggering export metering job: {e}")
            return None

    def process_metering_data(
        self, export_job_id: str, metric_temp_id: str
    ) -> bool:
        """Download, parse, and store metering data"""
        try:
            # Re-authenticate
            informatica_service = InformaticaUtils()
            informatica_service.set_credentials(
                username=self.username,
                password=self.password,
                domain_url=self.domain_url,
            )

            if not informatica_service.login(
                self.username, self.password, self.domain_url
            ):
                logger.error("Failed to login to Informatica for download")
                return False

            logger.info("Successfully logged in for download")

            # Download ZIP file
            zip_content = informatica_service.download_metering_data(export_job_id)
            if not zip_content:
                logger.error("Failed to download metering data")
                return False

            logger.info(f"Downloaded ZIP file: {len(zip_content)} bytes")

            # Extract and parse CSV files
            csv_rows_processed = 0
            db_inserts = 0

            with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_file:
                csv_files = [
                    f for f in zip_file.namelist() if f.lower().endswith(".csv")
                ]
                logger.info(f"Found {len(csv_files)} CSV files in ZIP")

                for csv_filename in csv_files:
                    logger.info(f"Processing CSV file: {csv_filename}")
                    with zip_file.open(csv_filename) as csv_file:
                        csv_content = csv_file.read().decode("utf-8")
                        rows_processed, inserts = self.parse_and_store_csv(
                            csv_content, metric_temp_id
                        )
                        csv_rows_processed += rows_processed
                        db_inserts += inserts

            logger.info(
                f"CSV processing complete - Rows processed: {csv_rows_processed}, DB inserts: {db_inserts}"
            )
            return True

        except Exception as e:
            logger.error(f"Error processing metering data: {e}")
            return False

    def parse_and_store_csv(
        self, csv_content: str, metric_temp_id: str
    ) -> Tuple[int, int]:
        """Parse CSV content and store in meter_usage table"""
        Session = sessionmaker(bind=engine)
        db = Session()
        rows_processed = 0
        inserts = 0

        try:
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            for row in csv_reader:
                rows_processed += 1

                # Ignore rows with missing MeterId or Date
                meter_id = row.get("MeterId", "").strip()
                date_str = row.get("Date", "").strip()

                if not meter_id or not date_str:
                    continue

                # Parse date
                try:
                    # Handle format like "2025-12-15 00:00:00.0"
                    usage_date = datetime.strptime(
                        date_str.split(".")[0], "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=timezone.utc)
                except Exception as e:
                    logger.warning(f"Could not parse date '{date_str}': {e}")
                    continue

                # Check for existing record
                existing = (
                    db.query(MeterUsage)
                    .filter(
                        MeterUsage.meter_id == meter_id,
                        MeterUsage.usage_date == usage_date,
                    )
                    .first()
                )

                if existing:
                    continue  # Skip duplicates

                # Parse MeterUsage as decimal
                meter_usage_value = None
                try:
                    meter_usage_str = row.get("MeterUsage", "").strip()
                    if meter_usage_str and meter_usage_str.lower() != "null":
                        meter_usage_value = Decimal(meter_usage_str)
                except Exception:
                    pass

                # Parse other numeric fields
                ipu_value = None
                try:
                    ipu_str = row.get("IPU", "").strip()
                    if ipu_str and ipu_str.lower() != "null":
                        ipu_value = Decimal(ipu_str)
                except Exception:
                    pass

                ipu_rate_value = None
                try:
                    ipu_rate_str = row.get("IPURate", "").strip()
                    if ipu_rate_str and ipu_rate_str.lower() != "null":
                        ipu_rate_value = Decimal(ipu_rate_str)
                except Exception:
                    pass

                # Parse billing period dates
                billing_period_start = None
                billing_period_end = None
                try:
                    billing_start_str = row.get("BillingPeriodStartDate", "").strip()
                    if billing_start_str and billing_start_str.lower() != "null":
                        billing_period_start = datetime.strptime(
                            billing_start_str.split(".")[0], "%Y-%m-%d %H:%M:%S"
                        ).replace(tzinfo=timezone.utc)
                except Exception:
                    pass

                try:
                    billing_end_str = row.get("BillingPeriodEndDate", "").strip()
                    if billing_end_str and billing_end_str.lower() != "null":
                        billing_period_end = datetime.strptime(
                            billing_end_str.split(".")[0], "%Y-%m-%d %H:%M:%S"
                        ).replace(tzinfo=timezone.utc)
                except Exception:
                    pass

                # Create meter_usage record
                meter_usage = MeterUsage(
                    org_id=row.get("OrgId", "").strip(),
                    meter_id=meter_id,
                    meter_name=row.get("MeterName", "").strip() or None,
                    usage_date=usage_date,
                    billing_period_start=billing_period_start,
                    billing_period_end=billing_period_end,
                    meter_usage=meter_usage_value,
                    ipu=ipu_value,
                    scalar=row.get("Scalar", "").strip() or None,
                    metric_category=row.get("MetricCategory", "").strip() or None,
                    org_name=row.get("OrgName", "").strip() or None,
                    org_type=row.get("OrgType", "").strip() or None,
                    ipu_rate=ipu_rate_value,
                    job_id=metric_temp_id,
                )

                db.add(meter_usage)
                inserts += 1

            db.commit()
            logger.info(f"Stored {inserts} new meter_usage records from CSV")
            return rows_processed, inserts

        except Exception as e:
            logger.error(f"Error parsing CSV: {e}")
            db.rollback()
            return rows_processed, inserts
        finally:
            db.close()

    def generate_comparison_csv(self, metric_temp_id: str) -> Optional[str]:
        """Generate comparison CSV with meters exceeding threshold"""
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            # Aggregate current period
            current_aggregates = (
                db.query(
                    MeterUsage.meter_id,
                    MeterUsage.meter_name,
                    func.sum(MeterUsage.meter_usage).label("total_usage"),
                )
                .filter(
                    MeterUsage.job_id == metric_temp_id,
                    MeterUsage.usage_date >= self.start_date,
                    MeterUsage.usage_date <= self.end_date,
                )
                .group_by(MeterUsage.meter_id, MeterUsage.meter_name)
                .all()
            )

            # Aggregate previous period
            previous_aggregates = (
                db.query(
                    MeterUsage.meter_id,
                    func.sum(MeterUsage.meter_usage).label("total_usage"),
                )
                .filter(
                    MeterUsage.usage_date >= self.previous_start_date,
                    MeterUsage.usage_date <= self.previous_end_date,
                )
                .group_by(MeterUsage.meter_id)
                .all()
            )

            # Create lookup for previous period
            previous_lookup = {
                meter_id: total_usage for meter_id, total_usage in previous_aggregates
            }

            # Calculate differences and filter by threshold
            comparison_data = []
            for meter_id, meter_name, current_total in current_aggregates:
                previous_total = previous_lookup.get(meter_id, Decimal("0"))
                if previous_total == 0:
                    continue  # Skip if no previous data

                difference = current_total - previous_total
                percentage_difference = (
                    (difference / previous_total * 100) if previous_total > 0 else 0
                )

                # Include only if absolute percentage difference >= threshold
                if abs(float(percentage_difference)) >= self.change_threshold:
                    comparison_data.append(
                        {
                            "MeterId": meter_id,
                            "MeterName": meter_name or "",
                            "PreviousMeterUsage": str(previous_total),
                            "CurrentMeterUsage": str(current_total),
                            "Difference": str(difference),
                            "PercentageDifference": f"{float(percentage_difference):.2f}%",
                        }
                    )

            if not comparison_data:
                logger.info("No meters exceeded the change threshold")
                return None

            # Generate CSV file
            filename = f"metric_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            headers = [
                "MeterId",
                "MeterName",
                "PreviousMeterUsage",
                "CurrentMeterUsage",
                "Difference",
                "PercentageDifference",
            ]

            with open(filename, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=headers)
                writer.writeheader()
                writer.writerows(comparison_data)

            logger.info(f"Generated comparison CSV: {filename} with {len(comparison_data)} meters")
            return filename

        except Exception as e:
            logger.error(f"Error generating comparison CSV: {e}")
            return None
        finally:
            db.close()

    def send_email_notification(self, comparison_csv_path: Optional[str]) -> None:
        """Send email notification with summary and optional CSV attachment"""
        try:
            Session = sessionmaker(bind=engine)
            db = Session()
            try:
                # Get total meter usage for current period
                total_usage = (
                    db.query(func.sum(MeterUsage.meter_usage))
                    .filter(
                        MeterUsage.job_id == self.metric_temp.id,
                        MeterUsage.usage_date >= self.start_date,
                        MeterUsage.usage_date <= self.end_date,
                    )
                    .scalar()
                ) or Decimal("0")

                subject = "[Informatica] Metric Summarizer Report"
                body = f"""Metric Summarizer Report

Frequency: {self.frequency}
Start Date: {self.start_date.strftime('%Y-%m-%d %H:%M:%S UTC')}
End Date: {self.end_date.strftime('%Y-%m-%d %H:%M:%S UTC')}
Change Threshold: {self.change_threshold}%

Total Meter Usage (Current Period): {total_usage}

"""
                if comparison_csv_path:
                    body += f"Attached is a comparison CSV with meters that exceeded the {self.change_threshold}% change threshold."
                else:
                    body += "No meters exceeded the change threshold for this period."

                send_email_with_attachment(
                    self.job.id, subject, body, comparison_csv_path
                )
                logger.info("Email notification sent successfully")

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error sending email notification: {e}")

    def process_metric_summarizer(self) -> None:
        """Main process to trigger export and wait for webhook"""
        logger.info(
            f"Starting metric summarizer processing (frequency: {self.frequency}, threshold: {self.change_threshold}%)"
        )

        try:
            # Validate that job and config were loaded successfully
            if not self.job:
                raise Exception(
                    f"Job {self.job_id} not found or failed to load configuration"
                )

            # Create metric_temp record
            self.metric_temp = self.create_metric_temp_record()
            if not self.metric_temp:
                raise Exception("Failed to create metric_temp record")

            # Trigger export metering job
            export_job_id = self.trigger_export_metering_job()
            if not export_job_id:
                self.update_metric_temp_status(
                    str(self.metric_temp.id), "failed"
                )
                raise Exception("Failed to trigger export metering job")

            # Update metric_temp with export_job_id
            self.update_metric_temp_status(
                str(self.metric_temp.id), "processing", export_job_id
            )

            logger.info(
                f"Export job triggered: {export_job_id}. Waiting for webhook callback..."
            )

            # Note: The actual processing will happen when webhook is received
            # For now, we just mark it as processing
            self.update_job_execution(
                self.execution_id,
                "completed",
                {
                    "message": "Export job triggered successfully. Processing will continue via webhook.",
                    "export_job_id": export_job_id,
                    "metric_temp_id": str(self.metric_temp.id),
                },
            )

        except Exception as e:
            logger.error(f"Error processing metric summarizer: {e}")
            if self.metric_temp:
                self.update_metric_temp_status(str(self.metric_temp.id), "failed")
            self.update_job_execution(
                self.execution_id, "failed", error_message=str(e)
            )
            raise Exception(f"Error processing metric summarizer: {e}")


def process_webhook_callback(export_job_id: str) -> bool:
    """
    Process webhook callback when export job completes.
    This function is called from the webhook endpoint.
    """
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # Find metric_temp record by export_job_id
        metric_temp = (
            db.query(MetricTemp)
            .filter(MetricTemp.export_job_id == export_job_id)
            .first()
        )

        if not metric_temp:
            logger.error(f"MetricTemp record not found for export_job_id: {export_job_id}")
            return False

        logger.info(f"Processing webhook callback for export_job_id: {export_job_id}")

        # Get job to access credentials
        job = db.query(Job).filter(Job.id == metric_temp.internal_job_id).first()
        if not job:
            logger.error(f"Job {metric_temp.internal_job_id} not found")
            return False

        organization = (
            db.query(Organization)
            .filter(Organization.id == job.organization_id)
            .first()
        )
        if not organization:
            logger.error(f"Organization {job.organization_id} not found")
            return False

        # Create manager instance (without execution_id for webhook processing)
        manager = MetricSummarizerManager.__new__(MetricSummarizerManager)
        manager.job_id = str(job.id)
        manager.execution_id = ""  # Not needed for webhook processing
        manager.job = job
        manager.domain_url = organization.domain
        manager.username = organization.username
        manager.password = organization.password
        manager.organization_identifier = organization.identifier
        manager.frequency = metric_temp.frequency
        manager.change_threshold = float(metric_temp.change_threshold)
        manager.metric_temp = metric_temp

        # Recalculate date ranges
        manager.start_date = metric_temp.start_date
        manager.end_date = metric_temp.end_date

        # Calculate previous period dates
        if manager.frequency == "daily":
            manager.previous_start_date = (manager.start_date - timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            manager.previous_end_date = (manager.end_date - timedelta(days=1)).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
        elif manager.frequency == "weekly":
            manager.previous_end_date = (manager.start_date - timedelta(seconds=1)).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
            manager.previous_start_date = (manager.previous_end_date - timedelta(days=6)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        elif manager.frequency == "monthly":
            manager.previous_end_date = (manager.start_date - timedelta(seconds=1)).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
            manager.previous_start_date = (manager.previous_end_date - timedelta(days=29)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        # Process metering data
        if not manager.process_metering_data(export_job_id, str(metric_temp.id)):
            manager.update_metric_temp_status(str(metric_temp.id), "failed")
            return False

        # Generate comparison CSV
        comparison_csv = manager.generate_comparison_csv(str(metric_temp.id))

        # Send email notification
        manager.send_email_notification(comparison_csv)

        # Clean up CSV file if it exists
        if comparison_csv and os.path.exists(comparison_csv):
            try:
                os.remove(comparison_csv)
                logger.info(f"Cleaned up temporary file: {comparison_csv}")
            except Exception as e:
                logger.warning(f"Failed to clean up CSV file: {e}")

        # Update status to completed
        manager.update_metric_temp_status(str(metric_temp.id), "completed")

        logger.info(f"Successfully processed webhook callback for export_job_id: {export_job_id}")
        return True

    except Exception as e:
        logger.error(f"Error processing webhook callback: {e}")
        # Try to update metric_temp status to failed
        try:
            metric_temp = (
                db.query(MetricTemp)
                .filter(MetricTemp.export_job_id == export_job_id)
                .first()
            )
            if metric_temp:
                metric_temp.status = "failed"
                db.commit()
        except Exception:
            pass
        return False
    finally:
        db.close()


def main() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Process Metric Summarizer job")
    parser.add_argument("--job_id", type=str, help="Job ID to process")
    parser.add_argument("--execution_id", type=str, help="Execution ID to process")
    args, unknown = parser.parse_known_args()

    try:
        manager = MetricSummarizerManager(args.job_id, args.execution_id)
        manager.process_metric_summarizer()
        return {"message": "Metric summarizer job triggered successfully"}
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        # Try to update job execution if possible
        try:
            Session = sessionmaker(bind=engine)
            db = Session()
            try:
                execution = (
                    db.query(JobExecution)
                    .filter(JobExecution.id == args.execution_id)
                    .first()
                )
                if execution and execution.status != "failed":
                    execution.status = "failed"
                    execution.completed_at = datetime.now(timezone.utc)
                    execution.error_message = f"Fatal error: {str(e)}"
                    db.commit()
            finally:
                db.close()
        except Exception as update_error:
            logger.error(f"Failed to update job execution: {update_error}")
        raise


if __name__ == "__main__":
    main()

