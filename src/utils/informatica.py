import logging
import requests
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from src.modules.informatica_job_logs.schema import InformaticaJobLogsResponse
import json

logger = logging.getLogger(__name__)


class InformaticaUtils:
    def __init__(self):
        self.session_id: Optional[str] = None
        self.domain_url: Optional[str] = None
        self.username: str = ""
        self.password: str = ""
        self.base_url: str= ""

    def set_credentials(self, username: str, password: str, domain_url: str) -> None:
        """Set credentials for Informatica login"""
        self.username = username
        self.password = password
        self.domain_url = domain_url

    def login(self, username: str, password: str, domain_url: str) -> bool:
        """
        Login to Informatica and get session ID and base URL
        """
        self.set_credentials(username, password, domain_url)
        
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
        Fetch all users from Informatica
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

    def get_job_logs(self, organization_identifier: str, limit: int = 5) -> list[InformaticaJobLogsResponse]:
        """
        Fetch job logs from Informatica in the new activity log entry format
        """
        if not self.session_id:
            logger.error("Not logged in. Please login first.")
            return []

        logs_url = f"{self.base_url}/api/v2/activity/activityLog?rowLimit=5000"
        headers = {
            "Content-Type": "application/json",
            "icSessionId": self.session_id,
        }

        try:
            print(f"Fetching job logs for organization ID: {organization_identifier}")
            response = requests.get(logs_url, headers=headers)
            response.raise_for_status()

            logs_data = response.json()
            print(f"Retrieved {len(logs_data)} job logs")
            
            # # Convert to InformaticaJobLogsResponse objects
            job_logs = []
            for log in logs_data:
                try:
                    informatica_id = log.get("id")
                    run_id = log.get("runId")
                    
                    # Fetch session log for this job (failures are handled gracefully)
                    log_data = ""
                    if informatica_id:
                        log_data = self._get_session_log(informatica_id, run_id)
                    
                    # Transform the data to match our new schema
                    transformed_log = {
                        "informatica_id": informatica_id,
                        "type": log.get("type"),
                        "object_id": log.get("objectId"),
                        "object_name": log.get("objectName"),
                        "run_id": run_id,
                        "start_time": log.get("startTime"),
                        "end_time": log.get("endTime"),
                        "start_time_utc": log.get("startTimeUtc"),
                        "end_time_utc": log.get("endTimeUtc"),
                        "state": log.get("state"),
                        "ui_state": log.get("UIState"),
                        "failed_source_rows": log.get("failedSourceRows"),
                        "success_source_rows": log.get("successSourceRows"),
                        "failed_target_rows": log.get("failedTargetRows"),
                        "success_target_rows": log.get("successTargetRows"),
                        "started_by": log.get("startedBy"),
                        "run_context_type": log.get("runContextType"),
                        "entries": log.get("entries", []),
                        "sub_task_entries": log.get("subTaskEntries", []),
                        "transformation_entries": log.get("transformationEntries", []),
                        "log_entry_item_attrs": log.get("logEntryItemAttrs"),
                        "session_variables": log.get("sessionVariables"),
                        "total_success_rows": log.get("totalSuccessRows"),
                        "total_failed_rows": log.get("totalFailedRows"),
                        "stop_on_error": log.get("stopOnError"),
                        "has_stop_on_error_record": log.get("hasStopOnErrorRecord"),
                        "is_stopped": log.get("isStopped"),
                        "log_data": log_data
                    }
                    
                    job_log = InformaticaJobLogsResponse(**transformed_log)
                    job_logs.append(job_log)
                except Exception as e:
                    logger.error(f"Error parsing job log: {e}")
                    continue
            
            print(f"Successfully processed {len(job_logs)} job logs")
            return job_logs

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch job logs: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching job logs: {e}")
            return []

    def get_connections(self) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch all connections from Informatica
        """
        if not self.session_id or not self.base_url:
            logger.error("Not logged in. Please login first.")
            return None

        connections_url = f"{self.base_url}/api/v2/connection"
        headers = {
            "icSessionId": self.session_id,
            "Accept": "application/json"
        }

        try:
            print("Fetching connections...")
            response = requests.get(connections_url, headers=headers)
            response.raise_for_status()

            connections_data = response.json()
            print(f"Retrieved {len(connections_data)} connections")
            return connections_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch connections: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching connections: {e}")
            return None

    def get_schedules(self, query_params: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch schedules from Informatica
        """
        if not self.session_id or not self.base_url:
            logger.error("Not logged in. Please login first.")
            return None

        schedules_url = f"{self.base_url}/public/core/v3/schedule"
        headers = {
            "INFA-SESSION-ID": self.session_id,
            "Accept": "application/json"
        }


        try:
            print("Fetching schedules...")
            response = requests.get(schedules_url, headers=headers, params=query_params)
            response.raise_for_status()

            schedules_data = response.json()
            
            # Handle case where API returns a dict wrapper instead of list
            if isinstance(schedules_data, dict):
                print(f"DEBUG: Response keys: {list(schedules_data.keys())}")
                if "schedules" in schedules_data:
                    schedules_data = schedules_data["schedules"]
                elif "value" in schedules_data:
                    schedules_data = schedules_data["value"]
                elif "objects" in schedules_data:
                    schedules_data = schedules_data["objects"]
                elif "items" in schedules_data:
                    schedules_data = schedules_data["items"]
            
            print(f"Retrieved {len(schedules_data)} schedules")
            return schedules_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch schedules: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching schedules: {e}")
            return None

    def lookup_connections(self, connection_names: List[str]) -> Optional[List[Dict[str, Any]]]:
        """
        Lookup connection details using the lookup API
        """
        if not self.session_id or not self.base_url:
            logger.error("Not logged in. Please login first.")
            return None

        lookup_url = f"{self.base_url}/public/core/v3/lookup"
        headers = {
            "INFA-SESSION-ID": self.session_id,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # Prepare objects array for lookup
        objects = [{"path": name, "type": "CONNECTION"} for name in connection_names]

        payload = {"objects": objects}

        try:
            print(f"Looking up {len(connection_names)} connections...")
            response = requests.post(lookup_url, headers=headers, json=payload)
            response.raise_for_status()

            lookup_data = response.json()
            connections = lookup_data.get("objects", [])
            print(f"Retrieved details for {len(connections)} connections")
            return connections

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to lookup connections: {e}")
            return None
        except Exception as e:
            logger.error(f"Error looking up connections: {e}")
            return None

    def get_object_references(self, object_id: str) -> Optional[Dict[str, Any]]:
        """
        Get object references for a given object ID
        """
        if not self.session_id or not self.base_url:
            logger.error("Not logged in. Please login first.")
            return None

        references_url = f"{self.base_url}/public/core/v3/objects/{object_id}/references?refType=usedBy"
        headers = {
            "INFA-SESSION-ID": self.session_id,
            "Accept": "application/json"
        }

        try:
            response = requests.get(references_url, headers=headers)
            response.raise_for_status()

            references_data = response.json()
            return references_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get object references for {object_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting object references for {object_id}: {e}")
            return None

    def _get_session_log(self, informatica_id: str, run_id: int) -> str:
        """
        Fetch session log for a specific job log entry.
        Returns empty string if the call fails to ensure data flow is not impacted.
        """
        if not self.session_id or not self.base_url or not informatica_id:
            return ""
        
        session_log_url = f"{self.base_url}/api/v2/activity/activityLog/{informatica_id}/sessionLog?runId={run_id}"
        headers = {
            "icSessionId": self.session_id,
        }
        
        try:
            response = requests.get(session_log_url, headers=headers)
            response.raise_for_status()
            # Response is text, not JSON
            return response.text
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch session log for {informatica_id}: {e}")
            return ""
        except Exception as e:
            logger.warning(f"Error fetching session log for {informatica_id}: {e}")
            return ""
    
    def _make_request(self, url: str, headers: Dict[str, str]) -> Optional[requests.Response]:
        """
        Make a generic HTTP request with error handling
        """
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error making request to {url}: {e}")
            return None

    def export_metering_data(
        self,
        start_date: str,
        end_date: str,
        callback_url: str,
        job_type: str = "SUMMARY",
        combined_meter_usage: str = "TRUE",
        all_linked_orgs: str = "TRUE",
    ) -> Optional[Dict[str, Any]]:
        """
        Trigger Export Metering Job via POST /saas/public/core/v3/license/metering/ExportMeteringData
        """
        if not self.session_id or not self.base_url:
            logger.error("Not logged in. Please login first.")
            return None

        # The metering API requires /saas prefix
        # Check if base_url already includes /saas
        if "/saas" in self.base_url:
            export_url = f"{self.base_url}/public/core/v3/license/metering/ExportMeteringData"
        else:
            export_url = f"{self.base_url}/saas/public/core/v3/license/metering/ExportMeteringData"
        headers = {
            "INFA-SESSION-ID": self.session_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "startDate": start_date,
            "endDate": end_date,
            "jobType": job_type,
            "combinedMeterUsage": combined_meter_usage,
            "allLinkedOrgs": all_linked_orgs,
            "callbackUrl": callback_url,
        }

        try:
            logger.info(f"Triggering export metering job: {start_date} to {end_date}")
            response = requests.post(export_url, headers=headers, json=payload)
            response.raise_for_status()

            export_data = response.json()
            logger.info(f"Export job created successfully: {export_data}")
            return export_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to export metering data: {e}")
            return None
        except Exception as e:
            logger.error(f"Error exporting metering data: {e}")
            return None

    def download_metering_data(self, job_id: str) -> Optional[bytes]:
        """
        Download metering data ZIP file via GET
        /saas/public/core/v3/license/metering/ExportMeteringData/{jobId}/download
        """
        if not self.session_id or not self.base_url:
            logger.error("Not logged in. Please login first.")
            return None

        # The metering API requires /saas prefix based on the error URL
        # Check if base_url already includes /saas
        if "/saas" in self.base_url:
            download_url = f"{self.base_url}/public/core/v3/license/metering/ExportMeteringData/{job_id}/download"
        else:
            download_url = f"{self.base_url}/saas/public/core/v3/license/metering/ExportMeteringData/{job_id}/download"
        
        headers = {
            "INFA-SESSION-ID": self.session_id,
            "Accept": "application/octet-stream, */*",
        }

        try:
            logger.info(f"Downloading metering data for job: {job_id}")
            logger.info(f"Download URL: {download_url}")
            response = requests.get(download_url, headers=headers)
            
            # Log response details for debugging
            logger.info(f"Response status: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"Response headers: {dict(response.headers)}")
                try:
                    logger.error(f"Response body: {response.text[:500]}")
                except:
                    pass
            
            response.raise_for_status()

            # Read the content
            content = response.content
            logger.info(f"Successfully downloaded metering data: {len(content)} bytes")
            return content

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error downloading metering data: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response body: {e.response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download metering data: {e}")
            return None
        except Exception as e:
            logger.error(f"Error downloading metering data: {e}")
            return None