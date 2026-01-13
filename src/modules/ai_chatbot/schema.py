from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant" 
    content: str
    timestamp: Optional[datetime] = None


class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[ChatMessage]] = []
    organization_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    data: Optional[Dict[str, Any]] = None
    query_type: Optional[str] = None
    execution_time: Optional[float] = None
    email_sent: Optional[bool] = False
    email_subject: Optional[str] = None


class EmailRequest(BaseModel):
    """Request model for email functionality"""
    message: str
    conversation_history: Optional[List[ChatMessage]] = []
    organization_id: Optional[str] = None
    recipient_email: Optional[str] = None  # If not provided, will use current user's email
