import argparse
import logging
import os
import sys
import csv
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
# flake8: noqa: E402
from src.models.job import Job
from src.models.job_execution import JobExecution
from src.models.organization import Organization
from src.utils.config import settings
from src.utils.database import engine
from src.utils.notify import send_email_with_attachment
from src.utils.informatica import InformaticaUtils

logger = logging.getLogger(__name__)


class InformaticaUnusedConnectionsManager:

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
    unused_connections: List[Dict[str, Any]]

    def __init__(
        self, job_id: str, execution_id: str
    ) -> None:

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
        self.unused_connections: List[Dict[str, Any]] = []
        self.get_config(job_id)

    def get_config(self, job_id: str) -> bool:
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            self.job = db.query(Job).filter(Job.id == job_id).first()
            if not self.job:
                raise Exception(f"Job {job_id} not found")
            print(f"Job {job_id} found, organization: {self.job.organization_id}")
            organization = db.query(Organization).filter(Organization.id == self.job.organization_id).first()
            if not organization:
                raise Exception(f"Organization {self.job.organization_id} not found")
            self.domain_url = organization.domain
            self.username = organization.username
            self.password = organization.password
            self.organization_identifier = organization.identifier
            
            # Validate required configuration
            if not self.domain_url:
                raise Exception(f"Organization {self.job.organization_id} has no domain URL configured")
            if not self.username:
                raise Exception(f"Organization {self.job.organization_id} has no username configured")
            if not self.password:
                raise Exception(f"Organization {self.job.organization_id} has no password configured")
            
            return True
        except Exception as e:
            logger.error(f"Error getting config: {e}")
            return False
        finally:
            db.close()

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

    def get_unused_connections(self) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch all connections from Informatica and identify unused ones
        """
        try:
            # Validate credentials before attempting login
            if not self.domain_url:
                logger.error("Domain URL is not configured")
                return None
            if not self.username:
                logger.error("Username is not configured")
                return None
            if not self.password:
                logger.error("Password is not configured")
                return None
            
            # Initialize InformaticaUtils
            informatica_utils = InformaticaUtils()
            informatica_utils.set_credentials(
                self.username, 
                self.password, 
                self.domain_url
            )
            
            # Login to Informatica
            if not informatica_utils.login(self.username, self.password, self.domain_url):
                logger.error("Failed to login to Informatica")
                return None
            
            # Get all connections
            connections = informatica_utils.get_connections()
            if connections is None:
                logger.error("Failed to fetch connections from Informatica")
                return None
            
            print(f"Retrieved {len(connections)} connections")
            
            # Extract connection names for lookup
            connection_names = [conn.get("name") for conn in connections if conn.get("name")]
            if not connection_names:
                print("No connection names found")
                return []
            
            # Lookup connection details
            connection_details = informatica_utils.lookup_connections(connection_names)
            if connection_details is None:
                logger.error("Failed to lookup connection details")
                return None
            
            print(f"Retrieved details for {len(connection_details)} connections")
            
            # Check each connection for usage
            unused_connections = []
            for connection in connection_details:
                connection_id = connection.get("id")
                if not connection_id:
                    continue
                
                # Get object references to check if connection is used
                references = informatica_utils.get_object_references(connection_id)
                if references is None:
                    logger.warning(f"Failed to get references for connection {connection.get('path')}")
                    continue
                
                reference_count = references.get("count", 0)
                print(f"Connection {connection.get('path')}: {reference_count} references")
                
                # If no references, connection is unused
                if reference_count == 0:
                    unused_connections.append(connection)
            
            print(f"Found {len(unused_connections)} unused connections")
            return unused_connections

        except Exception as e:
            logger.error(f"Error fetching unused connections: {e}")
            return None

    def export_to_csv(self, unused_connections: List[Dict[str, Any]]) -> str:
        """
        Export unused connections to CSV file
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"unused_connections_{timestamp}.csv"
        
        # Define CSV headers based on the required format
        headers = ["id", "path", "type", "description", "updatedBy", "updateTime"]
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            
            for connection in unused_connections:
                # Map the connection data to CSV format
                row = {
                    "id": connection.get("id", ""),
                    "path": connection.get("path", ""),
                    "type": connection.get("type", ""),
                    "description": connection.get("description", ""),
                    "updatedBy": connection.get("updatedBy", ""),
                    "updateTime": connection.get("updateTime", "")
                }
                writer.writerow(row)
        
        print(f"Exported {len(unused_connections)} unused connections to {filename}")
        return filename

    def process_unused_connections(self) -> None:
        """
        Main process to identify and report unused connections
        """
        print("Starting unused connections processing")

        try:
            # Validate that job and config were loaded successfully
            if not self.job:
                raise Exception(f"Job {self.job_id} not found or failed to load configuration")
            
            # Get unused connections
            unused_connections = self.get_unused_connections()
            if unused_connections is None:
                self.export_and_notify()
                logger.error("Failed to fetch connections. Exiting.")
                raise Exception("Failed to fetch connections from Informatica")

            self.unused_connections = unused_connections

            # Export to CSV and send email
            self.export_and_notify()
            
            # Update job execution with results
            self.update_job_execution(
                self.execution_id,
                "completed",
                {
                    "unused_connections_count": len(self.unused_connections),
                    "unused_connections": self.unused_connections,
                },
            )
        except Exception as e:
            logger.error(f"Error processing unused connections: {e}")
            self.update_job_execution(self.execution_id, "failed", error_message=str(e))
            raise Exception(f"Error processing unused connections: {e}")

    def export_and_notify(self) -> None:
        try:
            if not self.job:
                logger.error("Cannot export and notify: Job not found")
                return
                
            connections_to_export = self.unused_connections
            
            if not connections_to_export or len(connections_to_export) == 0:
                # Send email indicating no unused connections found
                subject = "[Informatica] Unused Connections Report - No Data Found"
                body = f"""No unused connections were found.

                Summary:
                - Total unused connections: 0
                - Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                
                This means all connections are being used by mappings or other objects."""
                
                send_email_with_attachment(self.job.id, subject, body, None)
                print("No unused connections found. Email notification sent indicating no data.")
                return

            # Export to CSV
            filename = self.export_to_csv(connections_to_export)

            # Send email with attachment
            subject = "[Informatica] Unused Connections Report"
            body = f"""Please find attached the list of unused connections.

                Summary:
                - Total unused connections: {len(connections_to_export)}
                - Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                
                These connections are not referenced by any mappings or other objects and may be candidates for cleanup."""
                
            send_email_with_attachment(self.job.id, subject, body, filename)
            
            print(f"Successfully exported {len(connections_to_export)} unused connections to {filename}")
            print(f"Email notification sent for job run {self.job.id}")
            
        except Exception as e:
            logger.error(f"Error exporting and notifying: {e}")
            return
        finally:
            if 'filename' in locals() and os.path.exists(filename):
                os.remove(filename)
                print(f"Cleaned up temporary file: {filename}")


def main() -> Dict[str, int]:
    parser = argparse.ArgumentParser(description="Process Informatica unused connections")
    parser.add_argument("--job_id", type=str, help="Job ID to process")
    parser.add_argument("--execution_id", type=str, help="Execution ID to process")
    args, unknown = parser.parse_known_args()  # unknown will skip any extra arguments

    try:
        manager = InformaticaUnusedConnectionsManager(args.job_id, args.execution_id)
        manager.process_unused_connections()
        return {
           "message": "Unused connections processed successfully"
        }
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        # Try to update job execution if possible (in case process_unused_connections didn't catch it)
        try:
            Session = sessionmaker(bind=engine)
            db = Session()
            try:
                execution = (
                    db.query(JobExecution).filter(JobExecution.id == args.execution_id).first()
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
