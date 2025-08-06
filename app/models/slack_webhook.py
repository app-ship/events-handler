"""
Slack Webhook Models for Events Handler
Models for receiving Slack Events API webhooks and publishing to pub/sub
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field


class SlackEvent(BaseModel):
    """Slack event structure for events handler"""
    type: str
    event_ts: Optional[str] = None
    user: Optional[str] = None
    channel: Optional[str] = None
    text: Optional[str] = None
    ts: Optional[str] = None
    thread_ts: Optional[str] = None
    bot_id: Optional[str] = None
    app_id: Optional[str] = None


class SlackEventWrapper(BaseModel):
    """Slack Events API payload for events handler"""
    token: Optional[str] = None
    team_id: str
    api_app_id: str
    event: SlackEvent
    type: str = "event_callback"
    event_id: str
    event_time: int
    authed_users: Optional[List[str]] = None


class SlackChallenge(BaseModel):
    """Slack URL verification challenge"""
    token: str
    challenge: str
    type: str = "url_verification"


# Union type for all possible Slack webhook payloads
SlackWebhookPayload = Union[SlackEventWrapper, SlackChallenge]


class SlackWebhookResponse(BaseModel):
    """Response for Slack webhook"""
    status: str
    message: Optional[str] = None
    challenge: Optional[str] = None


class SlackEventPublishRequest(BaseModel):
    """Request model for publishing Slack events to pub/sub"""
    slack_event: SlackEventWrapper
    source_service: str = Field(default="events-handler", description="Source service name")
    event_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")

    class Config:
        schema_extra = {
            "example": {
                "slack_event": {
                    "team_id": "T123456",
                    "api_app_id": "A123456",
                    "event": {
                        "type": "message",
                        "user": "U123456",
                        "channel": "C123456",
                        "text": "Hello, agent!",
                        "ts": "1234567890.123456",
                        "thread_ts": None
                    },
                    "type": "event_callback",
                    "event_id": "Ev123456",
                    "event_time": 1234567890
                },
                "source_service": "events-handler",
                "event_timestamp": "2025-01-25T10:00:00.000Z"
            }
        }


class SlackEventPublishResponse(BaseModel):
    """Response for Slack event publishing"""
    success: bool = Field(..., description="Whether the event was published successfully")
    message: str = Field(..., description="Success or error message")
    event_id: str = Field(..., description="Slack event ID")
    message_id: str = Field(..., description="Pub/Sub message ID")
    topic_path: str = Field(..., description="Full path of the Pub/Sub topic")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Slack event published successfully",
                "event_id": "Ev123456",
                "message_id": "123456789",
                "topic_path": "projects/my-project/topics/slack-reply-event",
                "timestamp": "2025-01-25T10:00:00.000Z"
            }
        } 