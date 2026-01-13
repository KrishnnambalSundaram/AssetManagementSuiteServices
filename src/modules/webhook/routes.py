import logging
import re
from typing import Dict

from fastapi import APIRouter, HTTPException, Request

from src.scripts.metric_summarizer import process_webhook_callback

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"],
)


@router.post("/metric-summarizer")
async def metric_summarizer_webhook(request: Request):
    """
    Webhook endpoint to receive job completion callbacks from Informatica.
    Expected message format: "Job with jobID: <jobId> has completed and the Job Status is SUCCESS."
    """
    try:
        # Get request body as text (Informatica sends plain text)
        body = await request.body()
        message = body.decode("utf-8")
        
        logger.info(f"Received webhook callback: {message}")

        # Extract export jobId from message
        # Pattern: "Job with jobID: <jobId> has completed and the Job Status is SUCCESS."
        match = re.search(r"jobID:\s*([^\s,]+)", message, re.IGNORECASE)
        if not match:
            logger.error(f"Could not extract job ID from message: {message}")
            raise HTTPException(
                status_code=400,
                detail="Could not extract job ID from webhook message"
            )

        export_job_id = match.group(1).strip()
        logger.info(f"Extracted export_job_id: {export_job_id}")

        # Check if message indicates success
        if "SUCCESS" not in message.upper():
            logger.warning(f"Job {export_job_id} did not complete successfully: {message}")
            # Still process it, but log the warning
            # You might want to handle failures differently

        # Process the webhook callback
        success = process_webhook_callback(export_job_id)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process webhook callback for job {export_job_id}"
            )

        return {"status": "success", "message": "Webhook processed successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

