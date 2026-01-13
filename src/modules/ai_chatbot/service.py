import logging
import re
import json
import os
import tempfile
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import openai
import yagmail

from src.models.job import Job
from src.models.job_execution import JobExecution
from src.models.user import User
from src.models.organization import Organization
from src.utils.config import settings
from src.utils.database import db
from src.utils.notify import export_to_excel
from .schema import ChatRequest, ChatResponse, EmailRequest

logger = logging.getLogger(__name__)


class AIEmailService:
    """Service to handle email functionality for AI chatbot"""
    
    def __init__(self):
        self.email_username = settings.EMAIL_USERNAME
        self.email_password = settings.EMAIL_PASSWORD
    
    def is_email_request(self, message: str) -> bool:
        """Use AI to intelligently detect if this is an email request"""
        try:
            # Use AI to classify if this is an email request
            classification_prompt = f"""
            You are an AI assistant that determines if a user message is requesting an email report.
            
            Analyze this user message and determine if they want to receive data via email:
            "{message}"
            
            Consider these patterns as email requests:
            - "email me [data]"
            - "send me [data]"
            - "mail me [data]"
            - "email [data] to [email]"
            - "send [data] to [email]"
            - "forward [data] to [email]"
            - "share [data] with [email]"
            - "email [data] and [email]"
            - "send [data] to me and [email]"
            - Any request that mentions sending/sharing data via email
            
            Respond with ONLY a JSON object:
            {{
                "is_email_request": true/false,
                "confidence": 0.95,
                "reasoning": "brief explanation"
            }}
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an email request classifier. Respond only with valid JSON."},
                    {"role": "user", "content": classification_prompt}
                ],
                temperature=0.1,
                max_tokens=200
            )
            
            # Parse AI response
            ai_response = response.choices[0].message.content.strip()
            logger.info(f"AI email detection response: {ai_response}")
            
            # Try to extract JSON from the response
            try:
                # Remove any markdown formatting if present
                if ai_response.startswith("```json"):
                    ai_response = ai_response.replace("```json", "").replace("```", "").strip()
                
                classification = json.loads(ai_response)
                is_email = classification.get("is_email_request", False)
                confidence = classification.get("confidence", 0)
                
                # Only consider it an email request if confidence is high enough
                if confidence >= 0.7:
                    logger.info(f"AI classified as email request: {is_email} (confidence: {confidence})")
                    return is_email
                else:
                    logger.info(f"Low confidence email classification: {confidence}")
                    return False
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI email detection response: {e}")
                # Fallback to simple keyword detection
                return self._fallback_email_detection(message)
                
        except Exception as e:
            logger.error(f"Error during AI email detection: {e}")
            # Fallback to simple keyword detection
            return self._fallback_email_detection(message)
    
    def _fallback_email_detection(self, message: str) -> bool:
        """Fallback email detection using simple keywords"""
        email_keywords = [
            "email me", "send me", "mail me", "email to", "send to",
            "email the", "mail the", "send the", "email this", "mail this"
        ]
        
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in email_keywords)
    
    def extract_email_recipients(self, message: str, current_user: User) -> List[str]:
        """Use AI to intelligently extract recipient emails from message"""
        try:
            # Use AI to extract recipient emails
            extraction_prompt = f"""
            You are an AI assistant that extracts email recipients from user messages.
            
            Analyze this user message and extract all email addresses that should receive the data:
            "{message}"
            
            Consider these patterns:
            - "email me [data]" -> use current user's email
            - "send [data] to john@example.com" -> john@example.com
            - "email [data] to me and admin@company.com" -> current user + admin@company.com
            - "send [data] to john@example.com, jane@example.com" -> both emails
            - "email [data] and cc admin@company.com" -> current user + admin@company.com
            - "forward [data] to manager@company.com" -> manager@company.com
            
            Current user email: {current_user.email}
            
            Respond with ONLY a JSON object:
            {{
                "recipients": ["email1@example.com", "email2@example.com"],
                "reasoning": "explanation of how recipients were determined"
            }}
            
            Rules:
            1. If no specific emails mentioned, include current user's email
            2. If "me" or "my email" mentioned, include current user's email
            3. Extract all valid email addresses mentioned
            4. Remove duplicates
            5. Always include at least one valid email address
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an email recipient extractor. Respond only with valid JSON."},
                    {"role": "user", "content": extraction_prompt}
                ],
                temperature=0.1,
                max_tokens=300
            )
            
            # Parse AI response
            ai_response = response.choices[0].message.content.strip()
            logger.info(f"AI recipient extraction response: {ai_response}")
            
            # Try to extract JSON from the response
            try:
                # Remove any markdown formatting if present
                if ai_response.startswith("```json"):
                    ai_response = ai_response.replace("```json", "").replace("```", "").strip()
                
                extraction = json.loads(ai_response)
                recipients = extraction.get("recipients", [])
                
                # Validate and clean up recipients
                valid_recipients = []
                for email in recipients:
                    if self._is_valid_email(email):
                        valid_recipients.append(email.lower().strip())
                
                # Remove duplicates while preserving order
                unique_recipients = []
                for email in valid_recipients:
                    if email not in unique_recipients:
                        unique_recipients.append(email)
                
                # Ensure at least current user's email is included if no valid emails found
                if not unique_recipients:
                    unique_recipients = [current_user.email]
                
                logger.info(f"AI extracted recipients: {unique_recipients}")
                return unique_recipients
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI recipient extraction response: {e}")
                # Fallback to simple email extraction
                return self._fallback_recipient_extraction(message, current_user)
                
        except Exception as e:
            logger.error(f"Error during AI recipient extraction: {e}")
            # Fallback to simple email extraction
            return self._fallback_recipient_extraction(message, current_user)
    
    def _fallback_recipient_extraction(self, message: str, current_user: User) -> List[str]:
        """Fallback recipient extraction using regex"""
        # Look for email patterns in the message
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, message)
        
        # Clean up emails
        valid_emails = []
        for email in emails:
            if self._is_valid_email(email):
                valid_emails.append(email.lower().strip())
        
        # Remove duplicates
        unique_emails = list(dict.fromkeys(valid_emails))
        
        # If no emails found, use current user's email
        if not unique_emails:
            unique_emails = [current_user.email]
        
        return unique_emails
    
    def _is_valid_email(self, email: str) -> bool:
        """Validate email format"""
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(email_pattern, email) is not None
    
    def generate_email_subject(self, query_type: str, data_summary: str) -> str:
        """Generate email subject based on query type and data"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        subject_map = {
            "inactive_users": f"Inactive Users Report - {timestamp}",
            "long_running_jobs": f"Long Running Jobs Report - {timestamp}",
            "recent_jobs": f"Recent Job Executions - {timestamp}",
            "last_logged_users": f"Recently Logged Users - {timestamp}",
            "failed_jobs": f"Failed Jobs Report - {timestamp}",
            "successful_jobs": f"Successful Jobs Report - {timestamp}",
            "job_statistics": f"Job Statistics Report - {timestamp}",
            "job_duration_analysis": f"Job Duration Analysis - {timestamp}",
            "user_engagement": f"User Engagement Summary - {timestamp}",
            "unused_connections": f"Unused Connections Report - {timestamp}"
        }
        
        return subject_map.get(query_type, f"Informatica Report - {timestamp}")
    
    def format_data_for_email(self, data_result: Dict[str, Any], query_type: str) -> Tuple[str, str, Optional[str]]:
        """Format data for email - returns (html_body, text_body, excel_file_path)"""
        data = data_result.get("data", [])
        summary = data_result.get("summary", "")
        
        if not data:
            html_body = f"""
            <html>
            <body>
                <h2>Informatica Report</h2>
                <p><strong>Summary:</strong> {summary}</p>
                <p>No data found for the requested query.</p>
                <hr>
                <p><em>Generated by Informatica AI Assistant on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</em></p>
            </body>
            </html>
            """
            
            text_body = f"""
            Informatica Report
            
            Summary: {summary}
            
            No data found for the requested query.
            
            Generated by Informatica AI Assistant on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            """
            
            return html_body, text_body, None
        
        # Generate Excel file for data
        excel_file_path = self._create_excel_attachment(data, query_type)
        
        # Generate HTML email body
        html_body = self._generate_html_body(data, summary, query_type)
        
        # Generate text email body
        text_body = self._generate_text_body(data, summary, query_type)
        
        return html_body, text_body, excel_file_path
    
    def _create_excel_attachment(self, data: List[Dict[str, Any]], query_type: str) -> str:
        """Create Excel attachment from data"""
        if not data:
            return None
        
        # Create temporary file
        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"informatica_report_{query_type}_{timestamp}.xlsx"
        file_path = os.path.join(temp_dir, filename)
        
        # Get headers from first data item
        if data:
            headers = list(data[0].keys())
            headers_label = [h.replace('_', ' ').title() for h in headers]
            
            # Export to Excel
            export_to_excel(data, file_path, headers, headers_label)
            return file_path
        
        return None
    
    def _generate_html_body(self, data: List[Dict[str, Any]], summary: str, query_type: str) -> str:
        """Generate HTML email body"""
        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h2 {{ color: #2c3e50; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .summary {{ background-color: #e8f4f8; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; }}
            </style>
        </head>
        <body>
            <h2>Informatica Report</h2>
            
            <div class="summary">
                <h3>Summary</h3>
                <p><strong>{summary}</strong></p>
                <p>Total records: {len(data)}</p>
            </div>
        """
        
        if data:
            # Create table
            html_body += "<h3>Data Details</h3><table>"
            
            # Table headers
            headers = list(data[0].keys())
            html_body += "<tr>"
            for header in headers:
                html_body += f"<th>{header.replace('_', ' ').title()}</th>"
            html_body += "</tr>"
            
            # Table rows
            for row in data[:50]:  # Limit to 50 rows in email
                html_body += "<tr>"
                for header in headers:
                    value = row.get(header, "")
                    # Format datetime values
                    if isinstance(value, datetime):
                        value = value.strftime("%Y-%m-%d %H:%M:%S")
                    html_body += f"<td>{value}</td>"
                html_body += "</tr>"
            
            html_body += "</table>"
            
            if len(data) > 50:
                html_body += f"<p><em>Showing first 50 records. Complete data is available in the Excel attachment.</em></p>"
        
        html_body += f"""
            <div class="footer">
                <p><em>Generated by Informatica AI Assistant on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</em></p>
                <p>This report was generated based on your query and contains the most recent data available.</p>
            </div>
        </body>
        </html>
        """
        
        return html_body
    
    def _generate_text_body(self, data: List[Dict[str, Any]], summary: str, query_type: str) -> str:
        """Generate text email body"""
        text_body = f"""
        INFORMATICA REPORT
        ==================
        
        Summary: {summary}
        Total records: {len(data)}
        
        """
        
        if data:
            text_body += "DATA DETAILS:\n"
            text_body += "=" * 50 + "\n"
            
            # Show first few records in text format
            for i, row in enumerate(data[:10]):  # Limit to 10 rows in text
                text_body += f"\nRecord {i+1}:\n"
                for key, value in row.items():
                    if isinstance(value, datetime):
                        value = value.strftime("%Y-%m-%d %H:%M:%S")
                    text_body += f"  {key.replace('_', ' ').title()}: {value}\n"
            
            if len(data) > 10:
                text_body += f"\n... and {len(data) - 10} more records (see Excel attachment for complete data)\n"
        
        text_body += f"""
        
        Generated by Informatica AI Assistant on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        This report was generated based on your query and contains the most recent data available.
        """
        
        return text_body
    
    def send_email(self, recipient_emails: List[str], subject: str, html_body: str, text_body: str, excel_file_path: Optional[str] = None) -> Dict[str, bool]:
        """Send email to multiple recipients with optional Excel attachment"""
        results = {}
        
        try:
            yag = yagmail.SMTP(self.email_username, self.email_password)
            
            attachments = []
            if excel_file_path and os.path.exists(excel_file_path):
                attachments.append(excel_file_path)
            
            # Send to all recipients
            for email in recipient_emails:
                try:
                    yag.send(
                        to=email,
                        subject=subject,
                        contents=[text_body, html_body],
                        attachments=attachments
                    )
                    results[email] = True
                    logger.info(f"Email sent successfully to {email} with subject: {subject}")
                    
                except Exception as e:
                    results[email] = False
                    logger.error(f"Failed to send email to {email}: {e}")
            
            # Clean up temporary file after all emails are sent
            if excel_file_path and os.path.exists(excel_file_path):
                try:
                    os.remove(excel_file_path)
                    logger.info(f"Cleaned up temporary file: {excel_file_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary file {excel_file_path}: {e}")
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to initialize email service: {e}")
            # Mark all recipients as failed
            for email in recipient_emails:
                results[email] = False
            return results


class AIDataService:
    """Service to fetch data for AI chatbot responses"""
    
    def __init__(self, db: Session):
        self.db = db
        self.informatica_utils = None
    
    def _get_informatica_connection(self, organization_id: str = None) -> bool:
        """Get Informatica connection for the organization"""
        try:
            logger.info(f"Getting Informatica connection for organization_id: {organization_id}")
            
            # Handle Postman template variables that weren't replaced
            if organization_id and organization_id.startswith("{{") and organization_id.endswith("}}"):
                logger.warning(f"Organization ID appears to be a template variable: {organization_id}")
                organization_id = None
            
            if organization_id:
                # Get organization credentials from database
                organization = self.db.query(Organization).filter(Organization.id == organization_id).first()
                if not organization:
                    logger.error(f"Organization {organization_id} not found in database")
                    return False
                
                # Initialize InformaticaUtils with organization credentials
                from src.utils.informatica import InformaticaUtils
                self.informatica_utils = InformaticaUtils()
                
                # Login to Informatica
                if not self.informatica_utils.login(
                    organization.username, 
                    organization.password, 
                    organization.domain
                ):
                    logger.error("Failed to login to Informatica")
                    return False
                
                return True
            else:
                # Use default organization or first available
                organization = self.db.query(Organization).first()
                if not organization:
                    logger.error("No organization found in database")
                    return False
                
                return self._get_informatica_connection(organization.id)
                
        except Exception as e:
            logger.error(f"Error getting Informatica connection: {e}")
            return False
    
    def get_inactive_users(self, days_inactive: int = 30, limit: int = 10, organization_id: str = None) -> List[Dict[str, Any]]:
        """Get users inactive for specified days from Informatica API"""
        try:
            # Get Informatica connection
            if not self._get_informatica_connection(organization_id):
                logger.error("Failed to establish Informatica connection")
                return []
            
            # Fetch users from Informatica API
            users_data = self.informatica_utils.get_users()
            if not users_data:
                logger.error("Failed to fetch users from Informatica")
                return []
            
            # Filter inactive users using the same logic as user_disabling script
            inactive_users = []
            for user in users_data:
                if self._is_user_inactive(user, days_inactive):
                    inactive_users.append({
                        "id": user.get("id"),
                        "name": f"{user.get('firstName', '')} {user.get('lastName', '')}".strip(),
                        "email": user.get("email"),
                        "last_login_time": user.get("lastLoginTime"),
                        "days_inactive": self._calculate_days_inactive(user.get("lastLoginTime")),
                        "status": user.get("status", "active")
                    })
                    
                    if len(inactive_users) >= limit:
                        break
            
            return inactive_users
            
        except Exception as e:
            logger.error(f"Error getting inactive users: {e}")
            return []
    
    def _is_user_inactive(self, user: Dict[str, Any], days_threshold: int = 30) -> bool:
        """Check if a user is inactive (same logic as user_disabling script)"""
        try:
            # Check if user has lastLoginTime field
            if "lastLoginTime" not in user or not user["lastLoginTime"]:
                logger.info(f"User {user.get('name', user.get('id'))} has no login time - considering inactive")
                return True

            # Parse last login time
            last_login_str = user["lastLoginTime"]
            try:
                last_login = datetime.fromisoformat(last_login_str.replace("Z", "+00:00"))
            except Exception as e:
                logger.error(f"Error parsing last login time: {e}")
                # Try alternative parsing if the above fails
                last_login = datetime.strptime(last_login_str, "%Y-%m-%dT%H:%M:%S.%fZ")

            # Calculate days since last login
            days_since_login = (datetime.now().replace(tzinfo=last_login.tzinfo) - last_login).days

            is_inactive = days_since_login > days_threshold
            logger.info(f"User {user.get('name', user.get('id'))}: Last login {days_since_login} days ago - {'INACTIVE' if is_inactive else 'ACTIVE'}")

            return is_inactive

        except Exception as e:
            logger.error(f"Error checking user activity for {user.get('name', user.get('id'))}: {e}")
            return False
    
    def _calculate_days_inactive(self, last_login_time: str) -> int:
        """Calculate days since last login"""
        if not last_login_time:
            return 999  # Consider very inactive if no login time
        
        try:
            last_login = datetime.fromisoformat(last_login_time.replace("Z", "+00:00"))
            return (datetime.now().replace(tzinfo=last_login.tzinfo) - last_login).days
        except Exception as e:
            logger.error(f"Error calculating days inactive: {e}")
            return 999
    
    def get_long_running_jobs(self, duration_threshold: int = 10, limit: int = 10, organization_id: str = None, job_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get jobs that ran longer than threshold (in minutes) from Informatica API"""
        try:
            # Get Informatica connection
            if not self._get_informatica_connection(organization_id):
                logger.error("Failed to establish Informatica connection")
                return []
            
            # Get organization identifier for job logs
            organization = self.db.query(Organization).filter(Organization.id == organization_id).first() if organization_id else self.db.query(Organization).first()
            if not organization:
                logger.error("No organization found for job logs")
                return []
            
            # Fetch job logs from Informatica API
            job_logs = self.informatica_utils.get_job_logs(organization.identifier)
            if not job_logs:
                logger.error("Failed to fetch job logs from Informatica")
                return []
            
            # Convert to dictionary format and filter for long running jobs
            threshold_seconds = duration_threshold * 60
            long_running = []
            
            for log in job_logs:
                if hasattr(log, 'model_dump'):
                    job_data = log.model_dump()
                else:
                    job_data = dict(log)
                
                # Apply job type filter if specified
                if job_type and job_data.get("type") != job_type:
                    continue
                
                # Check if job is delayed using same logic as delayed_jobs script
                if self._is_job_delayed(job_data, threshold_seconds):
                    long_running.append({
                        "id": job_data.get("id"),
                        "name": job_data.get("object_name", "Unknown"),
                        "type": job_data.get("type"),
                        "run_id": job_data.get("run_id"),
                        "start_time": job_data.get("start_time"),
                        "end_time": job_data.get("end_time"),
                        "duration_minutes": self._calculate_job_duration(job_data),
                        "state": job_data.get("state"),
                        "ui_state": job_data.get("ui_state"),
                        "started_by": job_data.get("started_by"),
                        "error_msg": job_data.get("error_msg"),
                        "total_success_rows": job_data.get("total_success_rows"),
                        "total_failed_rows": job_data.get("total_failed_rows")
                    })
                    
                    if len(long_running) >= limit:
                        break
            
            return sorted(long_running, key=lambda x: x['duration_minutes'], reverse=True)
            
        except Exception as e:
            logger.error(f"Error getting long running jobs: {e}")
            return []
    
    def _is_job_delayed(self, job: Dict[str, Any], threshold_seconds: int) -> bool:
        """Check if a job is delayed (same logic as delayed_jobs script)"""
        try:
            # Calculate duration from start and end times
            start_time = job.get("start_time")
            end_time = job.get("end_time")
            
            if not start_time or not end_time:
                return False

            # Convert string timestamps to datetime if needed
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            if isinstance(end_time, str):
                end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            
            # Calculate duration in seconds
            duration = (end_time - start_time).total_seconds()
            
            # Consider jobs as delayed if they took longer than threshold
            if duration > threshold_seconds:
                job_name = job.get('object_name', job.get('id', 'Unknown'))
                logger.info(f"Job {job_name}: Duration {duration:.2f}s exceeds threshold {threshold_seconds}s")
                return True
            
            return False

        except Exception as e:
            logger.error(f"Error checking if job is delayed: {e}")
            return False
    
    def _calculate_job_duration(self, job: Dict[str, Any]) -> float:
        """Calculate job duration in minutes"""
        try:
            start_time = job.get("start_time")
            end_time = job.get("end_time")
            
            if not start_time or not end_time:
                return 0.0

            # Convert string timestamps to datetime if needed
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            if isinstance(end_time, str):
                end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            
            # Calculate duration in minutes
            duration = (end_time - start_time).total_seconds() / 60
            return round(duration, 2)

        except Exception as e:
            logger.error(f"Error calculating job duration: {e}")
            return 0.0
    
    def _calculate_job_duration_from_log(self, log) -> float:
        """Calculate job duration in minutes from database log object"""
        try:
            start_time = log.start_time
            end_time = log.end_time
            
            if not start_time or not end_time:
                logger.debug(f"Job {log.object_id} missing start_time or end_time: start={start_time}, end={end_time}")
                return 0.0
            
            # Calculate duration in minutes
            duration = (end_time - start_time).total_seconds() / 60
            logger.debug(f"Job {log.object_id} duration: {duration:.2f} minutes")
            return round(duration, 2)

        except Exception as e:
            logger.error(f"Error calculating job duration from log: {e}")
            return 0.0
    
    def get_recent_job_executions(self, limit: int = 10, status: Optional[str] = None, job_type: Optional[str] = None, organization_id: str = None) -> List[Dict[str, Any]]:
        """Get recent job executions with optional filtering"""
        try:
            # Get Informatica connection
            if not self._get_informatica_connection(organization_id):
                logger.error("Failed to establish Informatica connection")
                return []
            
            # Get organization identifier for job logs
            organization = self.db.query(Organization).filter(Organization.id == organization_id).first() if organization_id else self.db.query(Organization).first()
            if not organization:
                logger.error("No organization found for job logs")
                return []
            
            # Fetch job logs from Informatica API
            job_logs = self.informatica_utils.get_job_logs(organization.identifier)
            if not job_logs:
                logger.error("Failed to fetch job logs from Informatica")
                return []
            
            # Filter and process jobs
            filtered_jobs = []
            for log in job_logs:
                if hasattr(log, 'model_dump'):
                    job_data = log.model_dump()
                else:
                    job_data = dict(log)
                
                # Apply job type filter if specified
                if job_type and job_data.get("type") != job_type:
                    continue
                
                # Apply status filter if specified
                if status:
                    if status == "failed" and not self._is_job_failed(job_data):
                        continue
                    elif status == "successful" and not self._is_job_successful(job_data):
                        continue
                
                filtered_jobs.append({
                    "id": job_data.get("id"),
                    "name": job_data.get("object_name", "Unknown"),
                    "type": job_data.get("type"),
                    "run_id": job_data.get("run_id"),
                    "start_time": job_data.get("start_time"),
                    "end_time": job_data.get("end_time"),
                    "duration_minutes": self._calculate_job_duration(job_data),
                    "state": job_data.get("state"),
                    "ui_state": job_data.get("ui_state"),
                    "started_by": job_data.get("started_by"),
                    "error_msg": job_data.get("error_msg"),
                    "total_success_rows": job_data.get("total_success_rows"),
                    "total_failed_rows": job_data.get("total_failed_rows")
                })
                
                if len(filtered_jobs) >= limit:
                    break
            
            return sorted(filtered_jobs, key=lambda x: x.get("start_time", ""), reverse=True)
            
        except Exception as e:
            logger.error(f"Error getting recent job executions: {e}")
            return []
    
    def get_job_statistics(self, period: str = "last_30_days") -> Dict[str, Any]:
        """Get job execution statistics for specified period"""
        days_map = {
            "last_7_days": 7,
            "last_30_days": 30,
            "last_90_days": 90
        }
        
        days = days_map.get(period, 30)
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Total executions
        total_executions = self.db.query(JobExecution).filter(
            JobExecution.started_at >= cutoff_date
        ).count()
        
        # Success rate
        successful_executions = self.db.query(JobExecution).filter(
            JobExecution.started_at >= cutoff_date,
            JobExecution.status == 'completed'
        ).count()
        
        # Failed executions
        failed_executions = self.db.query(JobExecution).filter(
            JobExecution.started_at >= cutoff_date,
            JobExecution.status == 'failed'
        ).count()
        
        # Average duration for completed jobs
        completed_jobs = self.db.query(JobExecution).filter(
            JobExecution.started_at >= cutoff_date,
            JobExecution.status == 'completed',
            JobExecution.completed_at.isnot(None)
        ).all()
        
        durations = []
        for job in completed_jobs:
            if job.started_at and job.completed_at:
                duration = (job.completed_at - job.started_at).total_seconds() / 60
                durations.append(duration)
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        success_rate = (successful_executions / total_executions * 100) if total_executions > 0 else 0
        
        return {
            "period": period,
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "failed_executions": failed_executions,
            "success_rate": round(success_rate, 2),
            "average_duration_minutes": round(avg_duration, 2),
            "period_start": cutoff_date.isoformat(),
            "period_end": datetime.utcnow().isoformat()
        }
    
    def get_last_logged_users(self, limit: int = 10, organization_id: str = None) -> List[Dict[str, Any]]:
        """Get last logged users from Informatica API"""
        try:
            # Get Informatica connection
            if not self._get_informatica_connection(organization_id):
                logger.error("Failed to establish Informatica connection")
                return []
            
            # Fetch users from Informatica API
            users_data = self.informatica_utils.get_users()
            if not users_data:
                logger.error("Failed to fetch users from Informatica")
                return []
            
            # Sort users by last login time and get the most recent ones
            users_with_login = []
            for user in users_data:
                if user.get("lastLoginTime"):
                    users_with_login.append({
                        "id": user.get("id"),
                        "name": f"{user.get('firstName', '')} {user.get('lastName', '')}".strip(),
                        "email": user.get("email"),
                        "last_login_time": user.get("lastLoginTime"),
                        "days_since_login": self._calculate_days_inactive(user.get("lastLoginTime")),
                        "status": user.get("status", "active")
                    })
            
            # Sort by last login time (most recent first) and limit results
            users_with_login.sort(key=lambda x: x.get("last_login_time", ""), reverse=True)
            return users_with_login[:limit]
            
        except Exception as e:
            logger.error(f"Error getting last logged users: {e}")
            return []
    
    def get_failed_jobs(self, limit: int = 10, organization_id: str = None, job_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get failed jobs from Informatica API"""
        try:
            # Get Informatica connection
            if not self._get_informatica_connection(organization_id):
                logger.error("Failed to establish Informatica connection")
                return []
            
            # Get organization identifier for job logs
            organization = self.db.query(Organization).filter(Organization.id == organization_id).first() if organization_id else self.db.query(Organization).first()
            if not organization:
                logger.error("No organization found for job logs")
                return []
            
            # Fetch job logs from Informatica API
            job_logs = self.informatica_utils.get_job_logs(organization.identifier)
            if not job_logs:
                logger.error("Failed to fetch job logs from Informatica")
                return []
            
            # Filter for failed jobs
            failed_jobs = []
            for log in job_logs:
                if hasattr(log, 'model_dump'):
                    job_data = log.model_dump()
                else:
                    job_data = dict(log)
                
                # Apply job type filter if specified
                if job_type and job_data.get("type") != job_type:
                    continue
                
                # Check if job failed (state indicates failure or error_msg exists)
                if self._is_job_failed(job_data):
                    failed_jobs.append({
                        "id": job_data.get("id"),
                        "name": job_data.get("object_name", "Unknown"),
                        "type": job_data.get("type"),
                        "run_id": job_data.get("run_id"),
                        "start_time": job_data.get("start_time"),
                        "end_time": job_data.get("end_time"),
                        "duration_minutes": self._calculate_job_duration(job_data),
                        "state": job_data.get("state"),
                        "ui_state": job_data.get("ui_state"),
                        "started_by": job_data.get("started_by"),
                        "error_msg": job_data.get("error_msg"),
                        "total_success_rows": job_data.get("total_success_rows"),
                        "total_failed_rows": job_data.get("total_failed_rows")
                    })
                    
                    if len(failed_jobs) >= limit:
                        break
            
            return sorted(failed_jobs, key=lambda x: x.get("start_time", ""), reverse=True)
            
        except Exception as e:
            logger.error(f"Error getting failed jobs: {e}")
            return []
    
    def get_successful_jobs(self, limit: int = 10, organization_id: str = None, job_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get successful jobs from Informatica API"""
        try:
            # Get Informatica connection
            if not self._get_informatica_connection(organization_id):
                logger.error("Failed to establish Informatica connection")
                return []
            
            # Get organization identifier for job logs
            organization = self.db.query(Organization).filter(Organization.id == organization_id).first() if organization_id else self.db.query(Organization).first()
            if not organization:
                logger.error("No organization found for job logs")
                return []
            
            # Fetch job logs from Informatica API
            job_logs = self.informatica_utils.get_job_logs(organization.identifier)
            if not job_logs:
                logger.error("Failed to fetch job logs from Informatica")
                return []
            
            # Filter for successful jobs
            successful_jobs = []
            for log in job_logs:
                if hasattr(log, 'model_dump'):
                    job_data = log.model_dump()
                else:
                    job_data = dict(log)
                
                # Apply job type filter if specified
                if job_type and job_data.get("type") != job_type:
                    continue
                
                # Check if job succeeded
                if self._is_job_successful(job_data):
                    successful_jobs.append({
                        "id": job_data.get("id"),
                        "name": job_data.get("object_name", "Unknown"),
                        "type": job_data.get("type"),
                        "run_id": job_data.get("run_id"),
                        "start_time": job_data.get("start_time"),
                        "end_time": job_data.get("end_time"),
                        "duration_minutes": self._calculate_job_duration(job_data),
                        "state": job_data.get("state"),
                        "ui_state": job_data.get("ui_state"),
                        "started_by": job_data.get("started_by"),
                        "total_success_rows": job_data.get("total_success_rows"),
                        "total_failed_rows": job_data.get("total_failed_rows")
                    })
                    
                    if len(successful_jobs) >= limit:
                        break
            
            return sorted(successful_jobs, key=lambda x: x.get("start_time", ""), reverse=True)
            
        except Exception as e:
            logger.error(f"Error getting successful jobs: {e}")
            return []
    
    def get_job_duration_analysis(self, organization_id: str = None) -> Dict[str, Any]:
        """Get job duration analysis from Informatica API"""
        try:
            # Get Informatica connection
            if not self._get_informatica_connection(organization_id):
                logger.error("Failed to establish Informatica connection")
                return {}
            
            # Get organization identifier for job logs
            organization = self.db.query(Organization).filter(Organization.id == organization_id).first() if organization_id else self.db.query(Organization).first()
            if not organization:
                logger.error("No organization found for job logs")
                return {}
            
            # Fetch job logs from Informatica API
            job_logs = self.informatica_utils.get_job_logs(organization.identifier)
            if not job_logs:
                logger.error("Failed to fetch job logs from Informatica")
                return {}
            
            # Calculate duration statistics
            durations = []
            for log in job_logs:
                if hasattr(log, 'model_dump'):
                    job_data = log.model_dump()
                else:
                    job_data = dict(log)
                
                duration = self._calculate_job_duration(job_data)
                if duration > 0:  # Only include jobs with valid duration
                    durations.append(duration)
            
            if not durations:
                return {
                    "total_jobs": 0,
                    "average_duration_minutes": 0,
                    "min_duration_minutes": 0,
                    "max_duration_minutes": 0,
                    "median_duration_minutes": 0
                }
            
            # Calculate statistics
            avg_duration = sum(durations) / len(durations)
            min_duration = min(durations)
            max_duration = max(durations)
            median_duration = sorted(durations)[len(durations) // 2]
            
            return {
                "total_jobs": len(durations),
                "average_duration_minutes": round(avg_duration, 2),
                "min_duration_minutes": round(min_duration, 2),
                "max_duration_minutes": round(max_duration, 2),
                "median_duration_minutes": round(median_duration, 2),
                "duration_distribution": {
                    "under_5_min": len([d for d in durations if d < 5]),
                    "5_to_15_min": len([d for d in durations if 5 <= d < 15]),
                    "15_to_30_min": len([d for d in durations if 15 <= d < 30]),
                    "over_30_min": len([d for d in durations if d >= 30])
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting job duration analysis: {e}")
            return {}
    
    def get_user_engagement_summary(self, organization_id: str = None) -> Dict[str, Any]:
        """Get user engagement summary from Informatica API"""
        try:
            # Get Informatica connection
            if not self._get_informatica_connection(organization_id):
                logger.error("Failed to establish Informatica connection")
                return {}
            
            # Fetch users from Informatica API
            users_data = self.informatica_utils.get_users()
            if not users_data:
                logger.error("Failed to fetch users from Informatica")
                return {}
            
            # Analyze user activity
            total_users = len(users_data)
            active_users = 0
            inactive_users = 0
            users_with_login = 0
            recent_users = 0  # Active in last 7 days
            
            for user in users_data:
                if user.get("lastLoginTime"):
                    users_with_login += 1
                    days_inactive = self._calculate_days_inactive(user.get("lastLoginTime"))
                    
                    if days_inactive <= 30:
                        active_users += 1
                    else:
                        inactive_users += 1
                    
                    if days_inactive <= 7:
                        recent_users += 1
            
            users_without_login = total_users - users_with_login
            
            return {
                "total_users": total_users,
                "active_users": active_users,
                "inactive_users": inactive_users,
                "recent_users": recent_users,
                "users_with_login": users_with_login,
                "users_without_login": users_without_login,
                "engagement_rates": {
                    "active_rate": round((active_users / total_users * 100), 2) if total_users > 0 else 0,
                    "recent_activity_rate": round((recent_users / total_users * 100), 2) if total_users > 0 else 0,
                    "login_rate": round((users_with_login / total_users * 100), 2) if total_users > 0 else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting user engagement summary: {e}")
            return {}
    
    def get_unused_connections(self, organization_id: str = None) -> List[Dict[str, Any]]:
        """Get unused connections from Informatica API (same logic as unused_connections script)"""
        try:
            # Get Informatica connection
            if not self._get_informatica_connection(organization_id):
                logger.error("Failed to establish Informatica connection")
                return []
            
            logger.info("Fetching connections from Informatica API")
            
            # Get all connections
            connections = self.informatica_utils.get_connections()
            if connections is None:
                logger.error("Failed to fetch connections from Informatica")
                return []
            
            logger.info(f"Retrieved {len(connections)} connections")
            
            # Extract connection names for lookup
            connection_names = [conn.get("name") for conn in connections if conn.get("name")]
            if not connection_names:
                logger.info("No connection names found")
                return []
            
            # Lookup connection details
            connection_details = self.informatica_utils.lookup_connections(connection_names)
            if connection_details is None:
                logger.error("Failed to lookup connection details")
                return []
            
            logger.info(f"Retrieved details for {len(connection_details)} connections")
            
            # Check each connection for usage
            unused_connections = []
            for connection in connection_details:
                connection_id = connection.get("id")
                if not connection_id:
                    continue
                
                # Get object references to check if connection is used
                references = self.informatica_utils.get_object_references(connection_id)
                if references is None:
                    logger.warning(f"Failed to get references for connection {connection.get('path')}")
                    continue
                
                reference_count = references.get("count", 0)
                logger.info(f"Connection {connection.get('path')}: {reference_count} references")
                
                # If no references, connection is unused
                if reference_count == 0:
                    unused_connections.append({
                        "id": connection.get("id"),
                        "path": connection.get("path"),
                        "type": connection.get("type"),
                        "description": connection.get("description"),
                        "updated_by": connection.get("updatedBy"),
                        "update_time": connection.get("updateTime"),
                        "reference_count": reference_count
                    })
            
            logger.info(f"Found {len(unused_connections)} unused connections")
            return unused_connections
            
        except Exception as e:
            logger.error(f"Error getting unused connections: {e}")
            return []
    
    def _is_job_failed(self, job: Dict[str, Any]) -> bool:
        """Check if a job failed"""
        try:
            # Check for error message
            if job.get("error_msg"):
                return True
            
            # Check state for failure indicators
            state = job.get("state")
            ui_state = job.get("ui_state")
            
            # Common failure states (may need adjustment based on actual Informatica states)
            failure_indicators = ["failed", "error", "aborted", "stopped", "terminated"]
            
            if state and any(indicator in str(state).lower() for indicator in failure_indicators):
                return True
            
            if ui_state and any(indicator in str(ui_state).lower() for indicator in failure_indicators):
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking if job failed: {e}")
            return False
    
    def _is_job_successful(self, job: Dict[str, Any]) -> bool:
        """Check if a job succeeded"""
        try:
            # Check for error message
            if job.get("error_msg"):
                return False
            
            # Check state for success indicators
            state = job.get("state")
            ui_state = job.get("ui_state")
            
            # Common success states (may need adjustment based on actual Informatica states)
            success_indicators = ["completed", "success", "finished", "done"]
            
            if state and any(indicator in str(state).lower() for indicator in success_indicators):
                return True
            
            if ui_state and any(indicator in str(ui_state).lower() for indicator in success_indicators):
                return True
            
            # If no error message and job has end time, consider it successful
            if job.get("end_time") and not job.get("error_msg"):
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking if job succeeded: {e}")
            return False
    
    def get_slow_jobs(self, threshold_percentage: float = 0.1, limit: int = 10, organization_id: str = None) -> List[Dict[str, Any]]:
        """Get jobs that are running slower than expected based on historical data from database"""
        try:
            # Get job logs from database instead of API calls
            from src.models.informatica_jobs_logs import InformaticaJobLogs
            from src.models.informatica_job_runs import InformaticaJobRuns
            
            # Get organization for filtering - with fallback to all logs if no organization data
            if organization_id:
                job_runs = self.db.query(InformaticaJobRuns).filter(
                    InformaticaJobRuns.organization_id == organization_id
                ).all()
                job_run_ids = [run.id for run in job_runs]
                logger.info(f"Found {len(job_runs)} job runs for organization {organization_id}")
                logger.info(f"Job run IDs: {job_run_ids}")
                
                if job_run_ids:
                    job_logs = self.db.query(InformaticaJobLogs).filter(
                        InformaticaJobLogs.job_run_id.in_(job_run_ids)
                    ).all()
                    logger.info(f"Found {len(job_logs)} job logs for organization {organization_id}")
                else:
                    logger.warning(f"No job runs found for organization {organization_id}, falling back to all job logs")
                    job_logs = self.db.query(InformaticaJobLogs).all()
            else:
                logger.info("No organization_id provided, getting all job logs")
                job_logs = self.db.query(InformaticaJobLogs).all()
            
            if not job_logs:
                logger.error("No job logs found in database")
                return []
            
            logger.info(f"Found {len(job_logs)} job logs to analyze for slow jobs")
            
            # Debug: Show sample of job logs
            if job_logs:
                sample_log = job_logs[0]
                logger.info(f"Sample job log - ID: {sample_log.id}, object_id: {sample_log.object_id}, "
                          f"object_name: {sample_log.object_name}, start_time: {sample_log.start_time}, "
                          f"end_time: {sample_log.end_time}")
            
            # Group jobs by object_id and calculate performance metrics
            job_performance = {}
            valid_duration_count = 0
            for log in job_logs:
                job_id = log.object_id or "Unknown"
                job_name = log.object_name or "Unknown"
                duration = self._calculate_job_duration_from_log(log)
                
                if job_id not in job_performance:
                    job_performance[job_id] = []
                
                if duration > 0:  # Only include jobs with valid duration
                    valid_duration_count += 1
                    job_performance[job_id].append({
                        "duration": duration,
                        "start_time": log.start_time,
                        "end_time": log.end_time,
                        "state": log.state,
                        "error_msg": log.error_msg,
                        "job_data": {
                            "id": log.id,
                            "object_id": log.object_id,
                            "object_name": log.object_name,
                            "type": log.type,
                            "run_id": log.run_id
                        }
                    })
            
            logger.info(f"Grouped jobs into {len(job_performance)} unique job IDs")
            logger.info(f"Found {valid_duration_count} job logs with valid duration > 0")
            
            # Debug: Show job performance summary
            for job_id, runs in job_performance.items():
                if len(runs) > 1:  # Only show jobs with multiple runs
                    logger.info(f"Job {job_id} has {len(runs)} runs")
                    for i, run in enumerate(runs):
                        logger.info(f"  Run {i+1}: {run['duration']:.2f}min at {run['start_time']}")
            
            # Find slow jobs
            slow_jobs = []
            jobs_with_multiple_runs = 0
            for job_id, runs in job_performance.items():
                if len(runs) < 2:  # Need at least 2 runs to compare
                    continue
                
                jobs_with_multiple_runs += 1
                
                # Sort by start time to get chronological order
                runs.sort(key=lambda x: x.get("start_time", ""))
                
                # Get the most recent run
                latest_run = runs[-1]
                latest_duration = latest_run["duration"]
                
                # Calculate average duration from previous runs (excluding the latest)
                previous_runs = runs[:-1]
                if not previous_runs:
                    continue
                
                avg_previous_duration = sum(run["duration"] for run in previous_runs) / len(previous_runs)
                
                # Check if latest run is significantly slower
                if avg_previous_duration > 0:
                    performance_ratio = (latest_duration - avg_previous_duration) / avg_previous_duration * 100
                    
                    logger.info(f"Job {job_id} ({runs[-1].get('job_data', {}).get('object_name', 'Unknown')}): "
                              f"Latest: {latest_duration:.2f}min, Avg Previous: {avg_previous_duration:.2f}min, "
                              f"Ratio: {performance_ratio:.2f}%")
                    
                    if performance_ratio >= threshold_percentage:
                        slow_jobs.append({
                            "job_id": job_id,
                            "job_name": latest_run.get("job_data", {}).get("object_name", "Unknown"),
                            "latest_duration_minutes": round(latest_duration, 2),
                            "average_previous_duration_minutes": round(avg_previous_duration, 2),
                            "performance_degradation_percentage": round(performance_ratio, 2),
                            "latest_start_time": latest_run.get("start_time"),
                            "latest_end_time": latest_run.get("end_time"),
                            "latest_state": latest_run.get("state"),
                            "latest_error_msg": latest_run.get("error_msg"),
                            "total_runs_analyzed": len(runs),
                            "job_data": latest_run.get("job_data")
                        })
            
            logger.info(f"Analyzed {jobs_with_multiple_runs} jobs with multiple runs, found {len(slow_jobs)} slow jobs")
            
            # Sort by performance degradation percentage (highest first)
            slow_jobs.sort(key=lambda x: x['performance_degradation_percentage'], reverse=True)
            
            return slow_jobs[:limit]
            
        except Exception as e:
            logger.error(f"Error getting slow jobs: {e}")
            return []
    
    def get_job_performance_degradation(self, threshold_percentage: float = 5.0, limit: int = 10, organization_id: str = None) -> List[Dict[str, Any]]:
        """Get jobs that have taken significantly longer than their previous runs from database"""
        try:
            # Get job logs from database instead of API calls
            from src.models.informatica_jobs_logs import InformaticaJobLogs
            from src.models.informatica_job_runs import InformaticaJobRuns
            
            # Get organization for filtering
            if organization_id:
                job_runs = self.db.query(InformaticaJobRuns).filter(
                    InformaticaJobRuns.organization_id == organization_id
                ).all()
                job_run_ids = [run.id for run in job_runs]
                job_logs = self.db.query(InformaticaJobLogs).filter(
                    InformaticaJobLogs.job_run_id.in_(job_run_ids)
                ).all()
            else:
                job_logs = self.db.query(InformaticaJobLogs).all()
            
            if not job_logs:
                logger.error("No job logs found in database")
                return []
            
            # Group jobs by object_id and analyze performance trends
            job_analysis = {}
            for log in job_logs:
                job_id = log.object_id or "Unknown"
                job_name = log.object_name or "Unknown"
                duration = self._calculate_job_duration_from_log(log)
                
                if job_id not in job_analysis:
                    job_analysis[job_id] = []
                
                if duration > 0:  # Only include jobs with valid duration
                    job_analysis[job_id].append({
                        "duration": duration,
                        "start_time": log.start_time,
                        "end_time": log.end_time,
                        "state": log.state,
                        "error_msg": log.error_msg,
                        "job_data": {
                            "id": log.id,
                            "object_id": log.object_id,
                            "object_name": log.object_name,
                            "type": log.type,
                            "run_id": log.run_id
                        }
                    })
            
            # Analyze performance degradation
            degraded_jobs = []
            for job_id, runs in job_analysis.items():
                if len(runs) < 2:  # Need at least 2 runs to compare
                    continue
                
                # Sort by start time to get chronological order
                runs.sort(key=lambda x: x.get("start_time", ""))
                
                # Get the most recent run
                latest_run = runs[-1]
                latest_duration = latest_run["duration"]
                
                # Get the previous run for direct comparison
                previous_run = runs[-2]
                previous_duration = previous_run["duration"]
                
                # Calculate performance degradation
                if previous_duration > 0:
                    degradation_percentage = (latest_duration - previous_duration) / previous_duration * 100
                    
                    if degradation_percentage >= threshold_percentage:
                        degraded_jobs.append({
                            "job_id": job_id,
                            "job_name": latest_run.get("job_data", {}).get("object_name", "Unknown"),
                            "latest_duration_minutes": round(latest_duration, 2),
                            "previous_duration_minutes": round(previous_duration, 2),
                            "degradation_percentage": round(degradation_percentage, 2),
                            "latest_start_time": latest_run.get("start_time"),
                            "latest_end_time": latest_run.get("end_time"),
                            "previous_start_time": previous_run.get("start_time"),
                            "previous_end_time": previous_run.get("end_time"),
                            "latest_state": latest_run.get("state"),
                            "latest_error_msg": latest_run.get("error_msg"),
                            "job_data": latest_run.get("job_data")
                        })
            
            # Sort by degradation percentage (highest first)
            degraded_jobs.sort(key=lambda x: x['degradation_percentage'], reverse=True)
            
            return degraded_jobs[:limit]
            
        except Exception as e:
            logger.error(f"Error getting job performance degradation: {e}")
            return []
    
    def get_job_trend_analysis(self, days: int = 30, threshold_percentage: float = 5.0, limit: int = 10, organization_id: str = None) -> List[Dict[str, Any]]:
        """Get jobs showing performance degradation over time periods from database"""
        try:
            # Get job logs from database instead of API calls
            from src.models.informatica_jobs_logs import InformaticaJobLogs
            from src.models.informatica_job_runs import InformaticaJobRuns
            
            # Filter logs by date range
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Get organization for filtering
            if organization_id:
                job_runs = self.db.query(InformaticaJobRuns).filter(
                    InformaticaJobRuns.organization_id == organization_id
                ).all()
                job_run_ids = [run.id for run in job_runs]
                job_logs = self.db.query(InformaticaJobLogs).filter(
                    InformaticaJobLogs.job_run_id.in_(job_run_ids),
                    InformaticaJobLogs.start_time >= cutoff_date
                ).all()
            else:
                job_logs = self.db.query(InformaticaJobLogs).filter(
                    InformaticaJobLogs.start_time >= cutoff_date
                ).all()
            
            if not job_logs:
                logger.error("No job logs found in database for the specified period")
                return []
            
            # Group jobs by object_id and analyze trends
            job_trends = {}
            for log in job_logs:
                job_id = log.object_id or "Unknown"
                job_name = log.object_name or "Unknown"
                duration = self._calculate_job_duration_from_log(log)
                
                if job_id not in job_trends:
                    job_trends[job_id] = []
                
                if duration > 0:  # Only include jobs with valid duration
                    job_trends[job_id].append({
                        "duration": duration,
                        "start_time": log.start_time,
                        "end_time": log.end_time,
                        "state": log.state,
                        "error_msg": log.error_msg,
                        "job_data": {
                            "id": log.id,
                            "object_id": log.object_id,
                            "object_name": log.object_name,
                            "type": log.type,
                            "run_id": log.run_id
                        }
                    })
            
            # Analyze trends for each job
            trend_analysis = []
            for job_id, runs in job_trends.items():
                if len(runs) < 3:  # Need at least 3 runs to analyze trends
                    continue
                
                # Sort by start time to get chronological order
                runs.sort(key=lambda x: x.get("start_time", ""))
                
                # Split runs into two halves for comparison
                mid_point = len(runs) // 2
                first_half = runs[:mid_point]
                second_half = runs[mid_point:]
                
                if not first_half or not second_half:
                    continue
                
                # Calculate average duration for each half
                first_half_avg = sum(run["duration"] for run in first_half) / len(first_half)
                second_half_avg = sum(run["duration"] for run in second_half) / len(second_half)
                
                # Calculate trend
                if first_half_avg > 0:
                    trend_percentage = (second_half_avg - first_half_avg) / first_half_avg * 100
                    
                    if trend_percentage >= threshold_percentage:
                        trend_analysis.append({
                            "job_id": job_id,
                            "job_name": runs[-1].get("job_data", {}).get("object_name", "Unknown"),
                            "first_half_avg_duration_minutes": round(first_half_avg, 2),
                            "second_half_avg_duration_minutes": round(second_half_avg, 2),
                            "trend_percentage": round(trend_percentage, 2),
                            "total_runs_analyzed": len(runs),
                            "first_half_runs": len(first_half),
                            "second_half_runs": len(second_half),
                            "latest_run": runs[-1],
                            "trend_direction": "degrading" if trend_percentage > 0 else "improving"
                        })
            
            # Sort by trend percentage (highest degradation first)
            trend_analysis.sort(key=lambda x: x['trend_percentage'], reverse=True)
            
            return trend_analysis[:limit]
            
        except Exception as e:
            logger.error(f"Error getting job trend analysis: {e}")
            return []


class AIChatService:
    """Main AI chat service"""
    
    def __init__(self):
        openai.api_key = settings.OPENAI_API_KEY
        self.email_service = AIEmailService()
        
    def parse_user_query(self, message: str) -> Tuple[str, Dict[str, Any], Dict[str, str]]:
        """Parse user message to determine query type and extract parameters using AI classification"""
        logger.info(f"Parsing query: '{message}'")
        
        # Define our supported query types and their descriptions
        supported_queries = {
            "inactive_users": "Queries about users who have not logged in for a specified number of days",
            "long_running_jobs": "Queries about jobs that ran for longer than a specified duration in minutes",
            "recent_jobs": "Queries about recent job executions with optional limit and job type filtering",
            "last_logged_users": "Queries about recently logged in users with optional limit",
            "failed_jobs": "Queries about failed job executions with optional job type filtering",
            "successful_jobs": "Queries about successful job executions with optional job type filtering",
            "job_statistics": "Queries about job performance metrics, success rates, and analytics",
            "job_duration_analysis": "Queries about average job duration and timing analysis",
            "user_engagement": "Queries about user activity patterns and engagement metrics",
            "unused_connections": "Queries about unused database connections that are not referenced by any mappings or objects",
            "slow_jobs": "Queries about jobs that are running slower than expected based on historical data",
            "job_performance_degradation": "Queries about jobs that have taken significantly longer than their previous runs",
            "job_trend_analysis": "Queries about jobs showing performance degradation over time periods"
        }
        
        try:
            # Use AI to classify the query
            classification_prompt = f"""
            You are a query classifier for an Informatica job monitoring system. 
            Analyze the user's message and classify it into one of the supported query types.
            
            Supported query types:
            {chr(10).join([f"- {k}: {v}" for k, v in supported_queries.items()])}
            
            User message: "{message}"
            
            Respond with ONLY a JSON object in this exact format:
            {{
                "query_type": "one_of_the_supported_types_above",
                "confidence": 0.95,
                "parameters": {{
                    "days_threshold": null,
                    "duration_threshold": null,
                    "limit": null,
                    "job_type": null,
                    "threshold_percentage": null,
                    "days": null
                }},
                "reasoning": "brief explanation of why this classification was chosen"
            }}
            
            Extract any numeric values and job types from the message. If no specific values are mentioned, use null.
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a query classifier. Respond only with valid JSON."},
                    {"role": "user", "content": classification_prompt}
                ],
                temperature=0.1,
                max_tokens=300
            )
            
            # Parse AI response
            ai_response = response.choices[0].message.content.strip()
            logger.info(f"AI classification response: {ai_response}")
            
            # Try to extract JSON from the response
            try:
                # Remove any markdown formatting if present
                if ai_response.startswith("```json"):
                    ai_response = ai_response.replace("```json", "").replace("```", "").strip()
                
                classification = json.loads(ai_response)
                query_type = classification.get("query_type")
                confidence = classification.get("confidence", 0)
                parameters = classification.get("parameters", {})
                
                # Validate the classification
                if query_type not in supported_queries:
                    logger.warning(f"AI returned unsupported query type: {query_type}")
                    return "general", {}, supported_queries
                
                if confidence < 0.7:
                    logger.warning(f"Low confidence classification: {confidence}")
                    return "general", {}, supported_queries
                
                # Clean up parameters - remove None values
                clean_params = {k: v for k, v in parameters.items() if v is not None}
                
                logger.info(f"AI classified query - type: {query_type}, confidence: {confidence}, params: {clean_params}")
                return query_type, clean_params, supported_queries
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI response as JSON: {e}")
                logger.error(f"Raw AI response: {ai_response}")
                return "general", {}, supported_queries
                
        except Exception as e:
            logger.error(f"Error during AI classification: {e}")
            return "general", {}, supported_queries
        
        # Fallback to general if AI classification fails
        logger.info("AI classification failed, returning 'general'")
        return "general", {}, supported_queries
    
    def execute_data_query(self, query_type: str, params: Dict[str, Any], db: Session, organization_id: str = None, supported_queries: Dict[str, str] = None) -> Dict[str, Any]:
        """Execute data query and return results"""
        logger.info(f"Executing data query: type={query_type}, params={params}, organization_id={organization_id}")
        data_service = AIDataService(db)
        
        try:
            if query_type == "inactive_users":
                days = params.get("days_threshold", 30)
                limit = params.get("limit", 10)
                data = data_service.get_inactive_users(days, limit, organization_id)
                return {
                    "type": "inactive_users",
                    "data": data,
                    "summary": f"Found {len(data)} users inactive for {days}+ days"
                }
            
            elif query_type == "long_running_jobs":
                threshold = params.get("duration_threshold", 10)
                limit = params.get("limit", 10)
                job_type = params.get("job_type")
                logger.info(f"Getting long running jobs: threshold={threshold} minutes, limit={limit}, job_type={job_type}")
                data = data_service.get_long_running_jobs(threshold, limit, organization_id, job_type)
                logger.info(f"Retrieved {len(data)} long running jobs")
                summary = f"Found {len(data)} jobs running longer than {threshold} minutes"
                if job_type:
                    summary += f" of type {job_type}"
                return {
                    "type": "long_running_jobs", 
                    "data": data,
                    "summary": summary
                }
            
            elif query_type == "recent_jobs":
                limit = params.get("limit", 10)
                job_type = params.get("job_type")
                logger.info(f"Getting recent jobs: limit={limit}, job_type={job_type}")
                data = data_service.get_recent_job_executions(limit, organization_id=organization_id, job_type=job_type)
                summary = f"Last {len(data)} job executions"
                if job_type:
                    summary += f" of type {job_type}"
                return {
                    "type": "recent_jobs",
                    "data": data,
                    "summary": summary
                }
            
            elif query_type == "job_statistics":
                period = params.get("period", "last_30_days")
                data = data_service.get_job_statistics(period)
                return {
                    "type": "job_statistics",
                    "data": data,
                    "summary": f"Job statistics for {period}"
                }
            
            elif query_type == "last_logged_users":
                limit = params.get("limit", 10)
                data = data_service.get_last_logged_users(limit, organization_id)
                return {
                    "type": "last_logged_users",
                    "data": data,
                    "summary": f"Last {len(data)} active users"
                }
            
            elif query_type == "failed_jobs":
                limit = params.get("limit", 10)
                job_type = params.get("job_type")
                logger.info(f"Getting failed jobs: limit={limit}, job_type={job_type}")
                data = data_service.get_failed_jobs(limit, organization_id, job_type)
                summary = f"Found {len(data)} failed jobs"
                if job_type:
                    summary += f" of type {job_type}"
                return {
                    "type": "failed_jobs",
                    "data": data,
                    "summary": summary
                }
            
            elif query_type == "successful_jobs":
                limit = params.get("limit", 10)
                job_type = params.get("job_type")
                logger.info(f"Getting successful jobs: limit={limit}, job_type={job_type}")
                data = data_service.get_successful_jobs(limit, organization_id, job_type)
                summary = f"Found {len(data)} successful jobs"
                if job_type:
                    summary += f" of type {job_type}"
                return {
                    "type": "successful_jobs",
                    "data": data,
                    "summary": summary
                }
            
            elif query_type == "job_duration_analysis":
                data = data_service.get_job_duration_analysis(organization_id)
                return {
                    "type": "job_duration_analysis",
                    "data": data,
                    "summary": f"Job duration analysis for {data.get('total_jobs', 0)} jobs"
                }
            
            elif query_type == "user_engagement":
                data = data_service.get_user_engagement_summary(organization_id)
                return {
                    "type": "user_engagement",
                    "data": data,
                    "summary": f"User engagement summary for {data.get('total_users', 0)} users"
                }
            
            elif query_type == "unused_connections":
                data = data_service.get_unused_connections(organization_id)
                return {
                    "type": "unused_connections",
                    "data": data,
                    "summary": f"Found {len(data)} unused connections"
                }
            
            elif query_type == "slow_jobs":
                threshold = params.get("threshold_percentage", 5.0)
                limit = params.get("limit", 10)
                logger.info(f"Getting slow jobs: threshold={threshold}%, limit={limit}")
                data = data_service.get_slow_jobs(threshold, limit, organization_id)
                summary = f"Found {len(data)} jobs running slower than expected"
                if threshold != 5.0:
                    summary += f" (threshold: {threshold}%)"
                return {
                    "type": "slow_jobs",
                    "data": data,
                    "summary": summary
                }
            
            elif query_type == "job_performance_degradation":
                threshold = params.get("threshold_percentage", 5.0)
                limit = params.get("limit", 10)
                logger.info(f"Getting job performance degradation: threshold={threshold}%, limit={limit}")
                data = data_service.get_job_performance_degradation(threshold, limit, organization_id)
                summary = f"Found {len(data)} jobs with performance degradation"
                if threshold != 5.0:
                    summary += f" (threshold: {threshold}%)"
                return {
                    "type": "job_performance_degradation",
                    "data": data,
                    "summary": summary
                }
            
            elif query_type == "job_trend_analysis":
                days = params.get("days", 30)
                threshold = params.get("threshold_percentage", 5.0)
                limit = params.get("limit", 10)
                logger.info(f"Getting job trend analysis: days={days}, threshold={threshold}%, limit={limit}")
                data = data_service.get_job_trend_analysis(days, threshold, limit, organization_id)
                summary = f"Found {len(data)} jobs showing performance trends over {days} days"
                if threshold != 5.0:
                    summary += f" (threshold: {threshold}%)"
                return {
                    "type": "job_trend_analysis",
                    "data": data,
                    "summary": summary
                }
            
            else:
                return {
                    "type": "unsupported",
                    "data": None,
                    "summary": "Query not supported",
                    "supported_queries": supported_queries or {}
                }
                
        except Exception as e:
            logger.error(f"Error executing data query: {e}")
            return {
                "type": "error",
                "data": None,
                "summary": f"Error executing query: {str(e)}"
            }
    
    def generate_ai_response(self, user_message: str, data_result: Dict[str, Any], conversation_history: List[Dict[str, str]] = None, organization_id: str = None) -> str:
        """Generate AI response using OpenAI"""
        try:
            # Handle unsupported queries with a clear message
            if data_result.get("type") == "unsupported":
                return f"""I'm sorry, but I don't support that type of query. Try from supported queries"""
                
            # Build context for AI for supported queries
            organization_context = ""
            if organization_id:
                organization_context = f"\n\nOrganization Context: This data is specific to organization ID: {organization_id}"
            
            context = f"""
            You are an AI assistant for an Informatica job monitoring system. You help users understand their job executions, user activity, and system performance.
            
            User Question: {user_message}
            
            Data Retrieved: {json.dumps(data_result, indent=2)}{organization_context}
            
            Please provide a helpful, conversational response that:
            1. Directly answers the user's question
            2. Summarizes the key findings from the data
            3. Provides insights or recommendations when relevant
            4. Uses a friendly, professional tone
            5. Formats the response clearly with bullet points or numbered lists when appropriate
            6. Acknowledges the organization context when relevant
            
            If the data shows concerning patterns (like many failed jobs or inactive users), mention this and suggest possible actions.
            """
            
            messages = [
                {"role": "system", "content": "You are a helpful AI assistant for Informatica job monitoring and analytics."},
                {"role": "user", "content": context}
            ]
            
            # Add conversation history if provided
            if conversation_history:
                for msg in conversation_history[-5:]:  # Include last 5 messages for context
                    messages.insert(-1, {"role": msg["role"], "content": msg["content"]})
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            return f"I found the following information: {data_result.get('summary', 'No data available')}. However, I encountered an issue generating a detailed response."
    
    async def process_email_request(self, request: EmailRequest, db: Session, current_user: User) -> ChatResponse:
        """Process email request - fetch data and send email"""
        start_time = datetime.utcnow()
        
        try:
            logger.info(f"Processing email request: '{request.message}' for user: {current_user.email}")
            
            # Check if this is an email request
            if not self.email_service.is_email_request(request.message):
                return ChatResponse(
                    response="I didn't detect an email request in your message. Please include phrases like 'email me' or 'send me' to request email reports.",
                    data=None,
                    query_type="error",
                    execution_time=(datetime.utcnow() - start_time).total_seconds(),
                    email_sent=False
                )
            
            # Extract recipient emails using AI
            recipient_emails = self.email_service.extract_email_recipients(request.message, current_user)
            
            # Parse the user query (remove email keywords for better classification)
            clean_message = self._clean_email_message(request.message)
            query_type, params, supported_queries = self.parse_user_query(clean_message)
            logger.info(f"Parsed email query - type: {query_type}, params: {params}")
            
            # Execute data query
            data_result = self.execute_data_query(query_type, params, db, request.organization_id, supported_queries)
            logger.info(f"Data query result - type: {data_result.get('type')}, summary: {data_result.get('summary')}")
            
            # Generate email content
            subject = self.email_service.generate_email_subject(query_type, data_result.get('summary', ''))
            html_body, text_body, excel_file_path = self.email_service.format_data_for_email(data_result, query_type)
            
            # Send email to all recipients
            email_results = self.email_service.send_email(recipient_emails, subject, html_body, text_body, excel_file_path)
            
            # Generate response message based on results
            successful_emails = [email for email, success in email_results.items() if success]
            failed_emails = [email for email, success in email_results.items() if not success]
            
            if successful_emails:
                response_message = f"✅ Email sent successfully to {len(successful_emails)} recipient(s)!\n\n"
                response_message += f"**Recipients:** {', '.join(successful_emails)}\n"
                response_message += f"**Subject:** {subject}\n"
                response_message += f"**Summary:** {data_result.get('summary', 'No summary available')}\n"
                if excel_file_path:
                    response_message += "**Attachment:** Excel file with complete data\n"
                response_message += f"\nThe email contains the requested data and has been delivered."
                
                if failed_emails:
                    response_message += f"\n\n⚠️ Failed to send to: {', '.join(failed_emails)}"
            else:
                response_message = f"❌ Failed to send email to all recipients: {', '.join(recipient_emails)}. Please check the email configuration and try again."
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Determine if any emails were sent successfully
            email_sent = len(successful_emails) > 0
            
            return ChatResponse(
                response=response_message,
                data=data_result,
                query_type=query_type,
                execution_time=execution_time,
                email_sent=email_sent,
                email_subject=subject if email_sent else None
            )
            
        except Exception as e:
            logger.error(f"Error processing email request: {e}", exc_info=True)
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            return ChatResponse(
                response=f"I apologize, but I encountered an error while processing your email request: {str(e)}",
                data=None,
                query_type="error",
                execution_time=execution_time,
                email_sent=False
            )
    
    def _clean_email_message(self, message: str) -> str:
        """Use AI to intelligently clean email-related keywords from message for better query classification"""
        try:
            # Use AI to clean the message
            cleaning_prompt = f"""
            You are an AI assistant that cleans user messages to extract the core data query.
            
            Clean this user message by removing email-related keywords while preserving the data request:
            "{message}"
            
            Remove these types of phrases:
            - "email me", "send me", "mail me"
            - "email to [email]", "send to [email]"
            - "forward to [email]", "share with [email]"
            - "and [email]", "cc [email]"
            - Any email addresses mentioned
            
            Keep the core data request intact.
            
            Examples:
            - "email me users inactive for 30 days" -> "users inactive for 30 days"
            - "send me the last 10 jobs to admin@company.com" -> "the last 10 jobs"
            - "email users inactive for 30 days to navarocks123@gmail.com" -> "users inactive for 30 days"
            
            Respond with ONLY the cleaned message, no explanations.
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a message cleaner. Respond only with the cleaned message."},
                    {"role": "user", "content": cleaning_prompt}
                ],
                temperature=0.1,
                max_tokens=100
            )
            
            cleaned_message = response.choices[0].message.content.strip()
            logger.info(f"AI cleaned message: '{message}' -> '{cleaned_message}'")
            return cleaned_message
            
        except Exception as e:
            logger.error(f"Error during AI message cleaning: {e}")
            # Fallback to simple keyword removal
            return self._fallback_clean_message(message)
    
    def _fallback_clean_message(self, message: str) -> str:
        """Fallback message cleaning using simple keyword removal"""
        email_keywords = [
            "email me", "send me", "mail me", "email to", "send to",
            "email the", "mail the", "send the", "email this", "mail this"
        ]
        
        clean_message = message.lower()
        for keyword in email_keywords:
            clean_message = clean_message.replace(keyword, "")
        
        # Remove email addresses
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        clean_message = re.sub(email_pattern, '', clean_message)
        
        # Remove extra whitespace
        clean_message = " ".join(clean_message.split())
        
        return clean_message.strip()

    async def process_chat_message(self, request: ChatRequest, db: Session) -> ChatResponse:
        """Main method to process chat messages"""
        start_time = datetime.utcnow()
        
        try:
            logger.info(f"Processing chat message: '{request.message}' with organization_id: {request.organization_id}")
            
            # Parse the user query
            query_type, params, supported_queries = self.parse_user_query(request.message)
            logger.info(f"Parsed query - type: {query_type}, params: {params}")
            
            # Execute data query
            data_result = self.execute_data_query(query_type, params, db, request.organization_id, supported_queries)
            logger.info(f"Data query result - type: {data_result.get('type')}, summary: {data_result.get('summary')}")

            # For unsupported queries, generate a clear response
            if data_result.get('type') == 'unsupported':
                conversation_history = [msg.dict() for msg in request.conversation_history] if request.conversation_history else []
                ai_response = self.generate_ai_response(request.message, data_result, conversation_history, request.organization_id)
                
                execution_time = (datetime.utcnow() - start_time).total_seconds()
                
                return ChatResponse(
                    response=ai_response,
                    data=data_result,
                    query_type=query_type,
                    execution_time=execution_time
                )
            
            # Generate AI response
            conversation_history = [msg.dict() for msg in request.conversation_history] if request.conversation_history else []
            ai_response = self.generate_ai_response(request.message, data_result, conversation_history, request.organization_id)
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            return ChatResponse(
                response=ai_response,
                data=data_result,
                query_type=query_type,
                execution_time=execution_time
            )
            
        except Exception as e:
            logger.error(f"Error processing chat message: {e}", exc_info=True)
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            return ChatResponse(
                response=f"I apologize, but I encountered an error while processing your request: {str(e)}",
                data=None,
                query_type="error",
                execution_time=execution_time
            )
