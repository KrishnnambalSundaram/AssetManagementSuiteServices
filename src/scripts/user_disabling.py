import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
# flake8: noqa: E402
from src.models.job import Job
from src.models.job_execution import JobExecution
from src.models.organization import Organization
from src.utils.config import settings
from src.utils.database import engine
from src.utils.notify import export_to_excel, send_email_with_attachment

logger = logging.getLogger(__name__)


class InformaticaUserManager:
    username: str
    password: str
    session_id: Optional[str]
    base_url: Optional[str]
    job_id: str
    execution_id: str
    domain_url: Optional[str]
    inactive_users: List[Dict[str, Any]]
    deleted_users: List[Dict[str, Any]]
    job: Optional[Job]
    dry_run: bool
    days_threshold: int

    def __init__(
        self, job_id: str, execution_id: str
    ) -> None:
        self.job_id = job_id
        self.execution_id = execution_id
        self.session_id: Optional[str] = None
        self.base_url: Optional[str] = None
        self.domain_url: Optional[str] = None
        self.inactive_users: List[Dict[str, Any]] = []
        self.deleted_users: List[Dict[str, Any]] = []
        self.job: Optional[Job] = None
        self.username: str = ""
        self.password: str = ""
        self.days_threshold: int = 30
        self.dry_run: bool = True
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
            # Ensure days_threshold is an integer
            days_threshold = self.job.parameters.get("days_threshold", 30)
            self.days_threshold = int(days_threshold) if days_threshold is not None else 30
            self.dry_run = self.job.parameters.get("dry_run", True)
            print(f"Days threshold: {self.days_threshold}, Dry run: {self.dry_run}")
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

    def login(self) -> bool:
        """
        Step 1: Login to Informatica and get session ID and base URL
        """
        login_payload = {"username": self.username, "password": self.password}

        headers = {"Content-Type": "application/json"}

        try:
            print("Attempting to login to Informatica...")
            response = requests.post(
                f"{self.domain_url}/saas/public/core/v3/login", json=login_payload, headers=headers
            )
            response.raise_for_status()

            login_data = response.json()
            products = login_data.get("products")
            user_data = login_data.get("userInfo")
            cloud_product = next(
                (p for p in products if p.get("name") == "Integration Cloud"), None
            )
            self.session_id = user_data.get("sessionId")
            self.base_url = cloud_product.get("baseApiUrl")

            if not self.session_id or not self.base_url:
                raise Exception(
                    "Failed to get session ID or base URL from login response"
                )

            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Login failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    def get_users(self) -> Optional[List[Dict[str, Any]]]:
        """
        Step 2: Fetch all users from Informatica
        """
        if not self.session_id or not self.base_url:
            logger.error("Not logged in. Please login first.")
            return None

        users_url = f"{self.base_url}/public/core/v3/users"
        headers = {
            "Content-Type": "application/json",
            "INFA-SESSION-ID": self.session_id,
        }

        try:
            print("Fetching users...")
            response = requests.get(users_url, headers=headers)
            response.raise_for_status()

            users_data = response.json()
            print(f"Retrieved {len(users_data)} users")
            return users_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch users: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching users: {e}")
            return None

    def is_user_inactive(self, user: Dict[str, Any], days_threshold: int = 30) -> bool:
        """
        Check if a user is inactive (last login over specified days ago)
        """
        try:
            # Check if user has lastLoginTime field
            if "lastLoginTime" not in user or not user["lastLoginTime"]:
                print(
                    f"User {user.get('name', user.get('id'))} has no login time - considering inactive"
                )
                return True

            # Parse last login time
            last_login_str = user["lastLoginTime"]
            # Assuming the date format is ISO 8601 or similar
            # You may need to adjust this based on the actual format from Informatica
            try:
                last_login = datetime.fromisoformat(
                    last_login_str.replace("Z", "+00:00")
                )
            except Exception as e:
                logger.error(f"Error parsing last login time: {e}")
                # Try alternative parsing if the above fails
                last_login = datetime.strptime(last_login_str, "%Y-%m-%dT%H:%M:%S.%fZ")

            # Calculate days since last login
            days_since_login = (
                datetime.now().replace(tzinfo=last_login.tzinfo) - last_login
            ).days

            is_inactive = days_since_login > days_threshold
            print(
                f"User {user.get('name', user.get('id'))}: "
                f"Last login {days_since_login} days ago - "
                f"{'INACTIVE' if is_inactive else 'ACTIVE'}"
            )

            return is_inactive

        except Exception as e:
            logger.error(
                f"Error checking user activity for {user.get('name', user.get('id'))}: {e}"
            )
            return False

    def delete_user(self, user_id: str) -> bool:
        """
        Step 3: Delete/Deactivate an inactive user
        """
        if not self.session_id or not self.base_url:
            logger.error("Not logged in. Please login first.")
            return False

        delete_url = f"{self.base_url}/public/core/v3/users/{user_id}"
        headers = {
            "Content-Type": "application/json",
            "INFA-SESSION-ID": self.session_id,
        }

        try:
            print(f"Deleting user with ID: {user_id}")
            response = requests.delete(delete_url, headers=headers)
            response.raise_for_status()
            print(f"Successfully deleted user: {user_id}")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to delete user {user_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")
            return False

    def process_inactive_users(self) -> None:
        """
        Main process to identify and deactivate inactive users
        """
        print(f"Starting inactive user processing (dry_run: {self.dry_run})")

        try:
            # Validate that job and config were loaded successfully
            if not self.job:
                raise Exception(f"Job {self.job_id} not found or failed to load configuration")

            # Step 1: Login
            if not self.login():
                raise Exception("Failed to login to Informatica")

            # Step 2: Get all users
            users = self.get_users()
            if not users:
                raise Exception("Failed to fetch users from Informatica")

            # Step 3: Identify inactive users
            inactive_users: List[Dict[str, Any]] = []
            for user in users:
                if self.is_user_inactive(user, self.days_threshold):
                    inactive_users.append(user)

            print(f"Found {len(inactive_users)} inactive users")
            self.inactive_users = inactive_users

            # Step 4: Process inactive users
            if not inactive_users:
                self.export_and_notify()
                print("No inactive users found.")
                # Update job execution with success even if no inactive users found
                self.update_job_execution(
                    self.execution_id,
                    "completed",
                    {
                        "users_disabled": 0,
                        "users_deleted": [],
                    },
                )
                return

            deleted_count = 0
            for user in inactive_users:
                user_id = user.get("id")
                user_name = user.get("firstName", "") + " " + user.get("lastName", "")
                if self.dry_run:
                    deleted_count += 1
                    print(
                        f"DRY RUN: Would delete user - ID: {user_id}, Name: {user_name}"
                    )
                else:
                    print(f"Deleting user - ID: {user_id}, Name: {user_name}")
                    if self.delete_user(user_id):
                        deleted_count += 1
                        self.deleted_users.append(user)

            if not self.dry_run:
                print(
                    f"Successfully deleted {deleted_count} out of {len(inactive_users)} inactive users"
                )
            else:
                print(
                    f"DRY RUN completed. {len(inactive_users)} users would be deleted"
                )

            # Export to Excel and send email using generic utils
            self.export_and_notify()

            self.update_job_execution(
                self.execution_id,
                "completed",
                {
                    "users_disabled": (
                        len(self.deleted_users)
                        if not self.dry_run
                        else len(self.inactive_users)
                    ),
                    "users_deleted": [
                        {
                            "id": x.get("id"),
                            "name": x.get("firstName", "") + " " + x.get("lastName", ""),
                        }
                        for x in (self.deleted_users if not self.dry_run else self.inactive_users)
                    ],
                },
            )
        except Exception as e:
            logger.error(f"Error processing inactive users: {e}")
            self.update_job_execution(self.execution_id, "failed", error_message=str(e))
            raise Exception(f"Error processing inactive users: {e}")

    def export_and_notify(self) -> None:
        try:
            users_to_export = self.inactive_users if self.dry_run else self.deleted_users
            if not users_to_export or len(users_to_export) == 0:
                print("[Inactive Users] No inactive users found to export and notify")
                # Send email indicating no inactive users found
                subject = "[Informatica] Inactive Users Report - No Data Found"
                body = f"""No inactive users were found matching the current parameters.

                Summary:
                - Total inactive users: 0
                - Days threshold: {self.days_threshold} days
                - Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                
                This means all users have been active within the last {self.days_threshold} days."""
                
                send_email_with_attachment(self.job.id, subject, body, None)
                print("No inactive users found. Email notification sent indicating no data.")
                return

            # Export to Excel
            headers = [
                "id",
                "firstName",
                "lastName",
                "email",
                "lastLoginTime",
                "status",
            ]
            headersLabel = [
                "ID",
                "First Name",
                "Last Name",
                "Email",
                "Last Login Time",
                "Status",
            ]
            filename = f"inactive_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            export_to_excel(users_to_export, filename, headers, headersLabel)

            # Send email with attachment
            subject = "[Informatica] Inactive Users Report"
            body = f"""Please find attached the list of inactive users.

                Summary:
                - Total inactive users: {len(users_to_export)}
                - Days threshold: {self.days_threshold} days
                - Dry run mode: {self.dry_run}
                - Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
                
            send_email_with_attachment(self.job.id, subject, body, filename)
            print(f"Successfully exported {len(users_to_export)} inactive users to {filename}")
            print(f"Email notification sent for job run {self.job.id}")
            
        except Exception as e:
            logger.error(f"Error exporting and notifying: {e}")
            return
        finally:
            if 'filename' in locals() and os.path.exists(filename):
                os.remove(filename)
                print(f"Cleaned up temporary file: {filename}")


def main() -> Dict[str, int]:
    parser = argparse.ArgumentParser(description="Disable Informatica users")
    parser.add_argument("--job_id", type=str, help="Job ID to process")
    parser.add_argument("--execution_id", type=str, help="Execution ID to process")
    args, unknown = parser.parse_known_args()  # unknown will skip any extra arguments

    try:
        manager = InformaticaUserManager(args.job_id, args.execution_id)
        manager.process_inactive_users()
        return {
           "message": "Inactive users processed successfully"
        }
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        # Try to update job execution if possible (in case process_inactive_users didn't catch it)
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
