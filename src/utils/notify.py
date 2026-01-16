from typing import Any, Dict, List, Optional
from datetime import datetime
import openpyxl
import yagmail
from dotenv.main import logger
from sqlalchemy.orm import sessionmaker

from src.models.job_notification import JobNotification
from src.utils.config import settings
from src.utils.database import engine


def export_to_excel(
    data: List[Dict[str, Any]],
    filename: str,
    headers: List[str],
    headersLabel: List[str],
) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Export"
    ws.append(headersLabel)
    
    for row in data:
        # Convert timezone-aware datetimes to timezone-naive for Excel compatibility
        processed_row = []
        for h in headers:
            value = row.get(h, "")
            # Handle datetime objects with timezone info
            if isinstance(value, datetime) and value.tzinfo is not None:
                value = value.replace(tzinfo=None)
            processed_row.append(value)
        ws.append(processed_row)
    
    wb.save(filename)
    return filename


def get_email_recipients(job_id: str) -> List[str]:
    Session = sessionmaker(bind=engine)
    db = Session()
    try:

        notifications: Optional[JobNotification] = (
            db.query(JobNotification)
            .filter(
                JobNotification.notification_type == "email",
                JobNotification.is_active == True,
                JobNotification.job_id == job_id,
            )
            .first()
        )
        recipients: List[str] = []
        config: dict = notifications.configuration or {} if notifications else {}
        emails = config.get("emails")
        if isinstance(emails, list):
            for email in emails:
                recipients.append(email)
        else:
            if emails:
                recipients.append(emails)
        return recipients
    finally:
        db.close()


def send_email_with_attachment(
    job_id: str, subject: str, body: str, attachment_path: str = "", custom_recipients: list[str] = None
) -> None:
    recipients: List[str] = custom_recipients if custom_recipients else get_email_recipients(job_id)
    if not recipients:
        logger.info(f"[Email] No recipients found for {subject}")
        return
    yag = yagmail.SMTP(settings.EMAIL_USERNAME, settings.EMAIL_PASSWORD)
    attachments = []
    if attachment_path:
        attachments.append(attachment_path)
    yag.send(to=recipients, subject=subject, contents=body, attachments=attachments)
    logger.info(f"[Email] Email sent to {recipients} with subject {subject}")
