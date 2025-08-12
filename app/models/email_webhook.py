"""
Email Webhook Models for Events Handler
Models for receiving Email Events API webhooks and publishing to pub/sub
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field


class EmailEvent(BaseModel):
    """Email event structure for events handler"""
    type: str
    event_ts: Optional[str] = None
    from_email: Optional[str] = None
    to_email: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    thread_id: Optional[str] = None
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    references: Optional[str] = None
    org_id: Optional[str] = None
    headers: Optional[Dict[str, Any]] = None


class EmailEventWrapper(BaseModel):
    """Email Events API payload for events handler"""
    token: Optional[str] = None
    project_id: str
    event: EmailEvent
    type: str = "email_callback"
    event_id: str
    event_time: int


class EmailChallenge(BaseModel):
    """Email URL verification challenge"""
    token: str
    challenge: str
    type: str = "url_verification"


# Union type for all possible Email webhook payloads
EmailWebhookPayload = Union[EmailEventWrapper, EmailChallenge]


class EmailWebhookResponse(BaseModel):
    """Response for Email webhook"""
    status: str
    message: Optional[str] = None
    challenge: Optional[str] = None


class EmailEventPublishRequest(BaseModel):
    """Request model for publishing Email events to pub/sub"""
    email_event: EmailEventWrapper
    source_service: str = Field(default="events-handler", description="Source service name")
    event_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")

    class Config:
        schema_extra = {
            "example": {
                "email_event": {
                    "project_id": "infis-ai",
                    "event": {
                        "type": "email_reply",
                        "from_email": "user@example.com",
                        "to_email": "support@infis-ai.com",
                        "subject": "Re: Support Request",
                        "body": "Thanks for your help!",
                        "thread_id": "thread123",
                        "message_id": "msg123",
                        "in_reply_to": "msg122",
                        "references": "msg121 msg122"
                    },
                    "type": "email_callback",
                    "event_id": "Em123456",
                    "event_time": 1234567890
                },
                "source_service": "events-handler",
                "event_timestamp": "2025-01-25T10:00:00.000Z"
            }
        }


class EmailEventPublishResponse(BaseModel):
    """Response for Email event publishing"""
    success: bool = Field(..., description="Whether the event was published successfully")
    message: str = Field(..., description="Success or error message")
    event_id: str = Field(..., description="Email event ID")
    message_id: str = Field(..., description="Pub/Sub message ID")
    topic_path: str = Field(..., description="Full path of the Pub/Sub topic")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Email event published successfully",
                "event_id": "Em123456",
                "message_id": "123456789",
                "topic_path": "projects/infis-ai/topics/app-email-reply-event",
                "timestamp": "2025-01-25T10:00:00.000Z"
            }
        }