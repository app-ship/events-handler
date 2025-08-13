from typing import Any, Dict, Optional
from datetime import datetime

from pydantic import BaseModel, Field, validator


class EventTriggerRequest(BaseModel):
    event_name: str = Field(
        ...,
        description="Name of the event to trigger (will be used as topic name)",
        min_length=1,
        max_length=255,
        pattern=r"^[a-zA-Z][a-zA-Z0-9-_]*$",
    )
    event_data: Dict[str, Any] = Field(
        ...,
        description="Data payload for the event",
    )
    attributes: Optional[Dict[str, str]] = Field(
        default=None,
        description="Optional message attributes (key-value pairs as strings)",
    )
    source_service: Optional[str] = Field(
        default=None,
        description="Name of the service triggering the event",
    )

    @validator("event_name")
    def validate_event_name(cls, v):
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Event name can only contain letters, numbers, hyphens, and underscores")
        return v.lower()  # Normalize to lowercase

    @validator("attributes")
    def validate_attributes(cls, v):
        if v is None:
            return v
        
        # Ensure all values are strings
        for key, value in v.items():
            if not isinstance(value, str):
                v[key] = str(value)
        
        return v

    class Config:
        schema_extra = {
            "example": {
                "event_name": "deep-research-called",
                "event_data": {
                    "user_id": "123",
                    "query": "Latest AI research",
                    "timestamp": "2025-08-06T10:00:00Z"
                },
                "attributes": {
                    "priority": "high",
                    "environment": "production"
                },
                "source_service": "deep-research-service"
            }
        }


class EventTriggerResponse(BaseModel):
    success: bool = Field(..., description="Whether the event was triggered successfully")
    message: str = Field(..., description="Success or error message")
    event_name: str = Field(..., description="Name of the triggered event")
    topic_path: str = Field(..., description="Full path of the Pub/Sub topic")
    message_id: str = Field(..., description="ID of the published message")
    topic_created: bool = Field(..., description="Whether the topic was newly created")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Event triggered successfully",
                "event_name": "deep-research-called",
                "topic_path": "projects/my-project/topics/deep-research-called",
                "message_id": "123456789",
                "topic_created": False,
                "timestamp": "2025-08-06T10:00:00.000Z"
            }
        }


class TopicCreateRequest(BaseModel):
    topic_id: str = Field(
        ...,
        description="ID for the new topic",
        min_length=1,
        max_length=255,
        pattern=r"^[a-zA-Z][a-zA-Z0-9-_]*$",
    )

    @validator("topic_id")
    def validate_topic_id(cls, v):
        return v.lower()

    class Config:
        schema_extra = {
            "example": {
                "topic_id": "user-signup"
            }
        }


class TopicResponse(BaseModel):
    topic_id: str = Field(..., description="ID of the topic")
    topic_path: str = Field(..., description="Full path of the Pub/Sub topic")
    name: str = Field(..., description="Full name of the topic")

    class Config:
        schema_extra = {
            "example": {
                "topic_id": "user-signup",
                "topic_path": "projects/my-project/topics/user-signup",
                "name": "projects/my-project/topics/user-signup"
            }
        }


class TopicCreateResponse(BaseModel):
    success: bool = Field(..., description="Whether the topic was created successfully")
    message: str = Field(..., description="Success or error message")
    topic: TopicResponse = Field(..., description="Topic details")
    created: bool = Field(..., description="Whether the topic was newly created")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Topic created successfully",
                "topic": {
                    "topic_id": "user-signup",
                    "topic_path": "projects/my-project/topics/user-signup",
                    "name": "projects/my-project/topics/user-signup"
                },
                "created": True,
                "timestamp": "2025-08-06T10:00:00.000Z"
            }
        }


class TopicsListResponse(BaseModel):
    success: bool = Field(..., description="Whether the request was successful")
    message: str = Field(..., description="Success or error message")
    topics: list[TopicResponse] = Field(..., description="List of topics")
    count: int = Field(..., description="Number of topics")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Topics retrieved successfully",
                "topics": [
                    {
                        "topic_id": "user-signup",
                        "topic_path": "projects/my-project/topics/user-signup",
                        "name": "projects/my-project/topics/user-signup"
                    },
                    {
                        "topic_id": "deep-research-called",
                        "topic_path": "projects/my-project/topics/deep-research-called",
                        "name": "projects/my-project/topics/deep-research-called"
                    }
                ],
                "count": 2,
                "timestamp": "2025-08-06T10:00:00.000Z"
            }
        }


class TopicDeleteResponse(BaseModel):
    success: bool = Field(..., description="Whether the topic was deleted successfully")
    message: str = Field(..., description="Success or error message")
    topic_id: str = Field(..., description="ID of the deleted topic")
    topic_path: str = Field(..., description="Full path of the deleted topic")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Topic deleted successfully",
                "topic_id": "old-event-topic",
                "topic_path": "projects/my-project/topics/old-event-topic",
                "timestamp": "2025-08-06T10:00:00.000Z"
            }
        }


class HealthCheckResponse(BaseModel):
    status: str = Field(..., description="Health status")
    project_id: Optional[str] = Field(None, description="Google Cloud project ID")
    publisher: Optional[str] = Field(None, description="Publisher connection status")
    subscriber: Optional[str] = Field(None, description="Subscriber connection status")
    error: Optional[str] = Field(None, description="Error message if unhealthy")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Health check timestamp")

    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "project_id": "my-project",
                "publisher": "connected",
                "subscriber": "connected",
                "timestamp": "2025-08-06T10:00:00.000Z"
            }
        }


class ErrorResponse(BaseModel):
    success: bool = Field(default=False, description="Always false for error responses")
    error: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Error code for programmatic handling")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

    class Config:
        schema_extra = {
            "example": {
                "success": False,
                "error": "Failed to publish message to topic 'invalid-topic'",
                "error_code": "MESSAGE_PUBLISH_ERROR",
                "details": {
                    "topic_id": "invalid-topic",
                    "error": "Topic not found"
                },
                "timestamp": "2025-08-06T10:00:00.000Z"
            }
        }