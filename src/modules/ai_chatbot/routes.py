from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging

from src.utils.database import db
from src.utils.auth import get_current_user
from src.models.user import User
from src.models.user_organization import UserOrganization
from .schema import ChatRequest, ChatResponse, EmailRequest
from .service import AIChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-chat", tags=["AI Chat"])


@router.post("/message", response_model=ChatResponse)
async def send_chat_message(
    request: ChatRequest,
    db: Session = Depends(db),
    current_user: User = Depends(get_current_user)
):
    """
    Send a message to the AI chat assistant
    
    The AI can answer questions about:
    - Inactive users (e.g., "users inactive for 30 days")
    - Long running jobs (e.g., "jobs running for over 10 minutes") 
    - Recent job executions (e.g., "last 10 jobs")
    - Job statistics and performance (e.g., "job success rate")
    - Recently logged users (e.g., "last 10 logged users")
    
    Email functionality:
    - Add email keywords to any query to receive email reports
    - Examples: "email me users inactive for 30 days", "send me failed jobs"
    - Emails are sent to your registered email address
    
    Organization context:
    - If no organization_id is provided, the AI will use the user's primary organization
    - Users can specify a different organization_id to query data from other organizations they have access to
    """
    try:
        chat_service = AIChatService()
        
        # Determine organization_id - use request's organization_id or user's primary organization
        organization_id = request.organization_id
        if not organization_id:
            # Get user's primary organization (first active organization)
            user_org = db.query(UserOrganization).filter(
                UserOrganization.user_id == current_user.id,
                UserOrganization.is_active == True
            ).first()
            
            if user_org:
                organization_id = user_org.organization_id
                logger.info(f"Using user's primary organization: {organization_id}")
            else:
                logger.warning(f"User {current_user.id} has no active organizations")
        
        # Update request with determined organization_id
        request.organization_id = organization_id
        
        # Check if this is an email request
        if chat_service.email_service.is_email_request(request.message):
            # Process as email request
            email_request = EmailRequest(
                message=request.message,
                conversation_history=request.conversation_history,
                organization_id=organization_id,
                recipient_email=None
            )
            response = await chat_service.process_email_request(email_request, db, current_user)
        else:
            # Process as regular chat message
            response = await chat_service.process_chat_message(request, db)
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat message: {str(e)}")


@router.get("/capabilities")
async def get_chat_capabilities():
    """
    Get information about what the AI chat assistant can help with
    """
    return {
        "capabilities": [
            {
                "category": "User Activity & Inactivity",
                "description": "Query user activity, inactive users, and engagement",
                "examples": [
                    "users inactive for 30 days",
                    "users who haven't logged in for 60 days",
                    "last 10 logged users",
                    "user engagement summary",
                    "dormant users 45 days",
                    "show me inactive users 30 days"
                ],
                "email_examples": [
                    "email me users inactive for 30 days",
                    "send me the last 10 logged users",
                    "mail me user engagement summary"
                ]
            },
            {
                "category": "Job Performance & Duration",
                "description": "Analyze job execution performance, duration, and issues",
                "examples": [
                    "jobs running for over 10 minutes",
                    "jobs that exceeded 30 minutes",
                    "long running jobs over 15 minutes",
                    "slow jobs 20 minutes",
                    "performance issues 25 minutes",
                    "jobs with duration over 10 minutes"
                ],
                "email_examples": [
                    "email me jobs running for over 10 minutes",
                    "send me long running jobs over 15 minutes",
                    "mail me performance issues 25 minutes"
                ]
            },
            {
                "category": "Job Status & Results",
                "description": "Query job success, failures, and execution status",
                "examples": [
                    "failed jobs",
                    "successful jobs",
                    "jobs that failed",
                    "completed jobs",
                    "jobs with errors",
                    "problematic jobs"
                ],
                "email_examples": [
                    "email me failed jobs",
                    "send me successful jobs",
                    "mail me jobs with errors"
                ]
            },
            {
                "category": "Recent Activity & History",
                "description": "Get recent job executions and user activity",
                "examples": [
                    "last 10 jobs",
                    "recent job executions",
                    "latest 5 jobs",
                    "recent activity",
                    "latest executions",
                    "recent job history"
                ],
                "email_examples": [
                    "email me the last 10 jobs",
                    "send me recent job executions",
                    "mail me latest 5 jobs"
                ]
            },
            {
                "category": "Analytics & Statistics",
                "description": "Comprehensive job and user analytics",
                "examples": [
                    "job performance summary",
                    "average job duration",
                    "job duration analysis",
                    "user engagement stats",
                    "performance metrics",
                    "execution health"
                ],
                "email_examples": [
                    "email me job performance summary",
                    "send me job duration analysis",
                    "mail me user engagement stats"
                ]
            },
            {
                "category": "Connection Management",
                "description": "Database connection analysis and cleanup",
                "examples": [
                    "unused connections",
                    "unused database connections",
                    "connections not in use",
                    "orphaned connections",
                    "cleanup connections",
                    "connection usage analysis"
                ],
                "email_examples": [
                    "email me unused connections",
                    "send me unused database connections",
                    "mail me connection cleanup report"
                ]
            },
            {
                "category": "Job Performance Insights",
                "description": "Advanced job performance analysis and trend detection",
                "examples": [
                    "slow jobs",
                    "jobs running slower than expected",
                    "jobs that have taken twice the time than the last run",
                    "jobs that have taken 30% more run time compared to last 30 days average",
                    "job performance degradation",
                    "jobs showing performance trends",
                    "jobs with increasing execution time",
                    "performance issues over time"
                ],
                "email_examples": [
                    "email me slow jobs",
                    "send me jobs with performance degradation",
                    "mail me jobs that have taken 30% more time",
                    "email me jobs showing performance trends over 30 days"
                ]
            }
        ],
        "email_features": {
            "description": "AI-powered natural language email detection - no rigid keywords required!",
            "ai_detection": "Uses AI to intelligently detect email requests from natural language",
            "features": [
                "AI-powered email request detection",
                "Intelligent recipient extraction from natural language",
                "Multiple recipient support",
                "Automatic Excel attachment with complete data",
                "Formatted HTML and text email content",
                "Professional email templates",
                "Automatic cleanup of temporary files",
                "Email delivery confirmation",
                "Integrated into main chat endpoint - no separate API needed"
            ],
            "natural_language_examples": [
                "email users inactive for 30 days to navarocks123@gmail.com",
                "send me the last 10 jobs to admin@company.com",
                "email me and john@example.com the failed jobs",
                "forward user stats to manager@company.com",
                "share job performance with team@company.com",
                "email me failed jobs",  # Uses current user's email
                "send me unused connections to admin@company.com",
                "email me unused database connections"
            ],
            "recipient_handling": [
                "Default: Current user's email address (from JWT token)",
                "Single recipient: 'email data to user@example.com'",
                "Multiple recipients: 'email data to user1@example.com, user2@example.com'",
                "Current user + others: 'email me and admin@company.com the data'",
                "Flexible language: 'send', 'forward', 'share', 'email' all work"
            ],
            "usage": "Simply use natural language in the /ai-chat/message endpoint - AI handles the rest!"
        }
    }


@router.get("/health")
async def chat_health_check():
    """Health check for AI chat service"""
    try:
        # Basic service check
        chat_service = AIChatService()
        return {
            "status": "healthy",
            "service": "AI Chat Assistant",
            "version": "1.0.0"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")
