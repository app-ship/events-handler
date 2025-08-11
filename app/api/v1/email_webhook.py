"""
Email Webhook API for Events Handler
Receives Email Events API webhooks and publishes to pub/sub topics
"""

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.models.email_webhook import (
    EmailWebhookPayload,
    EmailWebhookResponse,
    EmailEventWrapper,
    EmailChallenge,
    EmailEventPublishResponse,
)
from app.models.events import ErrorResponse
from app.services.pubsub import pubsub_service
from app.core.config import settings
from app.utils.exceptions import (
    EventsHandlerException,
    PubSubServiceException,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/email", tags=["email"])

# Email topic name for event publishing
EMAIL_REPLY_EVENT_TOPIC = "app-email-reply-event"


def _create_error_response(
    status_code: int,
    error_message: str,
    error_code: str = None,
    details: Dict[str, Any] = None,
) -> JSONResponse:
    """Create standardized error response"""
    error_response = ErrorResponse(
        error=error_message,
        error_code=error_code,
        details=details or {},
    )
    return JSONResponse(
        status_code=status_code,
        content=error_response.dict(),
    )


@router.post(
    "/webhook",
    response_model=EmailWebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Email Events API webhook",
    description="Receives Email Events API webhooks and publishes them to the EMAIL_REPLY_EVENT pub/sub topic",
    responses={
        200: {"model": EmailWebhookResponse, "description": "Email event processed successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request data"},
        401: {"model": ErrorResponse, "description": "Invalid signature"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def email_webhook(request: Request):
    """
    Email Events API webhook endpoint
    
    This endpoint:
    1. Receives Email Events API webhooks
    2. Handles URL verification challenges
    3. Publishes Email events to EMAIL_REPLY_EVENT pub/sub topic
    """
    try:
        # Get request body
        body = await request.body()
        
        # Parse payload
        try:
            import json
            payload_data = json.loads(body.decode())
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in Email webhook: {e}")
            return _create_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_message="Invalid JSON payload",
                error_code="INVALID_JSON",
            )
        
        # Handle URL verification challenge
        if payload_data.get("type") == "url_verification":
            try:
                challenge_data = EmailChallenge(**payload_data)
                logger.info("Responding to Email URL verification challenge")
                return EmailWebhookResponse(
                    status="ok",
                    challenge=challenge_data.challenge
                )
            except Exception as e:
                logger.error(f"Error parsing Email challenge: {e}")
                return _create_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    error_message=f"Invalid challenge format: {str(e)}",
                    error_code="INVALID_CHALLENGE",
                )
        
        # Handle event callback
        elif payload_data.get("type") == "email_callback":
            try:
                # Parse the Email event
                event_wrapper = EmailEventWrapper(**payload_data)
                
                logger.info(f"Received Email event: {event_wrapper.event_id} from project {event_wrapper.project_id}")
                logger.info(f"Event type: {event_wrapper.event.type}")
                
                # Process supported Email events (email_reply)
                supported_event_types = {"email_reply"}
                if event_wrapper.event.type not in supported_event_types:
                    logger.info(f"Skipping unsupported event: {event_wrapper.event.type}")
                    return EmailWebhookResponse(status="ok", message="Unsupported event skipped")
                
                # Skip empty messages
                if not event_wrapper.event.body or not event_wrapper.event.body.strip():
                    logger.info("Skipping empty email message")
                    return EmailWebhookResponse(status="ok", message="Empty email message skipped")
                
                # Publish to pub/sub topic
                publish_result = await publish_email_event(event_wrapper)
                
                logger.info(f"Email event {event_wrapper.event_id} published successfully with message ID: {publish_result['message_id']}")
                
                return EmailWebhookResponse(
                    status="ok",
                    message="Email event published to pub/sub"
                )
                
            except Exception as e:
                logger.error(f"Error processing Email event: {e}")
                return _create_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    error_message=f"Invalid event format: {str(e)}",
                    error_code="INVALID_EVENT",
                    details={"error": str(e)},
                )
        
        # Unknown event type
        else:
            logger.warning(f"Unknown Email webhook type: {payload_data.get('type')}")
            return EmailWebhookResponse(status="ok", message="Unknown event type")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Email webhook: {e}")
        return _create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_message="Internal server error occurred while processing Email webhook",
            error_code="INTERNAL_ERROR",
            details={"error": str(e)},
        )


async def publish_email_event(event_wrapper: EmailEventWrapper) -> Dict[str, str]:
    """
    Publish Email event to EMAIL_REPLY_EVENT pub/sub topic
    
    Args:
        event_wrapper: Email event wrapper data
        
    Returns:
        Dictionary with publish result containing message_id
        
    Raises:
        PubSubServiceException: If publishing fails
    """
    try:
        # Prepare event data for pub/sub
        event_data = {
            "email_event": event_wrapper.dict(),
            "source_service": "events-handler",
            "event_timestamp": time.time(),
            "event_type": "email_reply",
        }
        
        # Prepare attributes for message routing
        attributes = {
            "source_service": "events-handler",
            "event_type": "email_reply",
            "project_id": event_wrapper.project_id,
            "from_email": event_wrapper.event.from_email or "",
            "to_email": event_wrapper.event.to_email or "",
            "message_type": event_wrapper.event.type,
        }
        
        # Create topic if it doesn't exist
        topic_info = await pubsub_service.create_topic_if_not_exists(EMAIL_REPLY_EVENT_TOPIC)
        
        # Publish the message
        publish_result = await pubsub_service.publish_message(
            topic_id=EMAIL_REPLY_EVENT_TOPIC,
            message_data=event_data,
            attributes=attributes,
        )
        
        logger.info(f"Published Email event to topic {topic_info['topic_path']} with message ID: {publish_result['message_id']}")
        
        return publish_result
        
    except Exception as e:
        logger.error(f"Failed to publish Email event to pub/sub: {e}")
        raise PubSubServiceException(
            message=f"Failed to publish Email event: {str(e)}",
            error_code="EMAIL_PUBLISH_ERROR",
            details={"event_id": event_wrapper.event_id, "error": str(e)}
        )


@router.get("/health")
async def email_webhook_health():
    """Health check endpoint for Email webhook"""
    return {"status": "healthy", "service": "email-webhook"}