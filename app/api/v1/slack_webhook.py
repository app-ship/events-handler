"""
Slack Webhook API for Events Handler
Receives Slack Events API webhooks and publishes to pub/sub topics
"""

import logging
import hashlib
import hmac
import time
import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status, BackgroundTasks
from fastapi.responses import JSONResponse

from app.models.slack_webhook import (
    SlackWebhookPayload,
    SlackWebhookResponse,
    SlackEventWrapper,
    SlackChallenge,
    SlackEventPublishResponse,
)
from app.models.events import ErrorResponse
from app.services.pubsub import pubsub_service
from app.core.config import settings
from app.utils.exceptions import (
    EventsHandlerException,
    PubSubServiceException,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slack", tags=["slack"])

# Slack topic name for event publishing
SLACK_REPLY_EVENT_TOPIC = os.getenv("SLACK_REPLY_EVENT_TOPIC", "slack-reply-event")


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


def verify_slack_signature(request: Request, body: bytes, signing_secret: str) -> bool:
    """Verify Slack request signature for security"""
    try:
        timestamp = request.headers.get("X-Slack-Request-Timestamp")
        signature = request.headers.get("X-Slack-Signature")
        
        if not timestamp or not signature:
            logger.warning("Missing Slack signature headers")
            return False
        
        # Prevent replay attacks (timestamp should be within 5 minutes)
        if abs(time.time() - float(timestamp)) > 60 * 5:
            logger.warning("Slack request timestamp too old")
            return False
        
        # Create signature
        sig_basestring = f"v0:{timestamp}:{body.decode()}"
        my_signature = "v0=" + hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(my_signature, signature)
        
    except Exception as e:
        logger.error(f"Error verifying Slack signature: {e}")
        return False


@router.post(
    "/webhook",
    response_model=SlackWebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Slack Events API webhook",
    description="Receives Slack Events API webhooks and publishes them to the SLACK_REPLY_EVENT pub/sub topic",
    responses={
        200: {"model": SlackWebhookResponse, "description": "Slack event processed successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request data"},
        401: {"model": ErrorResponse, "description": "Invalid signature"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def slack_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Slack Events API webhook endpoint
    
    This endpoint:
    1. Receives Slack Events API webhooks
    2. Verifies Slack signatures for security
    3. Handles URL verification challenges
    4. Publishes Slack events to SLACK_REPLY_EVENT pub/sub topic (asynchronously)
    """
    try:
        # Get request body
        body = await request.body()
        
        # Verify signature if enabled
        if hasattr(settings, 'slack_signing_secret') and settings.slack_signing_secret:
            if not verify_slack_signature(request, body, settings.slack_signing_secret):
                logger.warning("Invalid Slack signature")
                return _create_error_response(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    error_message="Invalid signature",
                    error_code="INVALID_SIGNATURE",
                )
        else:
            logger.info("Slack signature verification disabled or not configured")
        
        # Parse payload
        try:
            import json
            payload_data = json.loads(body.decode())
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in Slack webhook: {e}")
            return _create_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_message="Invalid JSON payload",
                error_code="INVALID_JSON",
            )
        
        # Handle URL verification challenge
        if payload_data.get("type") == "url_verification":
            challenge = payload_data.get("challenge")
            if not challenge:
                logger.error("Missing challenge in URL verification")
                return _create_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    error_message="Missing challenge",
                    error_code="MISSING_CHALLENGE",
                )
            
            logger.info("Slack URL verification challenge received")
            return SlackWebhookResponse(
                status="ok",
                message="URL verification challenge",
                challenge=challenge
            )

        
        # Handle event callback
        elif payload_data.get("type") == "event_callback":
            try:
                # Parse the Slack event
                event_wrapper = SlackEventWrapper(**payload_data)
                
                logger.info(f"Received Slack event: {event_wrapper.event_id} from team {event_wrapper.team_id}")
                logger.info(f"Event type: {event_wrapper.event.type}")
                
                # Skip bot events to prevent loops
                if event_wrapper.event.bot_id or event_wrapper.event.app_id:
                    logger.info(f"Skipping bot event: {event_wrapper.event.type}")
                    return SlackWebhookResponse(status="ok", message="Bot event skipped")
                
                # Process supported Slack events (message and app_mention)
                supported_event_types = {"message", "app_mention"}
                if event_wrapper.event.type not in supported_event_types:
                    logger.info(f"Skipping unsupported event: {event_wrapper.event.type}")
                    return SlackWebhookResponse(status="ok", message="Unsupported event skipped")
                
                # Skip message subtypes that aren't user messages
                if hasattr(event_wrapper.event, 'subtype') and event_wrapper.event.subtype:
                    logger.info(f"Skipping message subtype: {event_wrapper.event.subtype}")
                    return SlackWebhookResponse(status="ok", message="Message subtype skipped")
                
                # Skip empty messages
                if not event_wrapper.event.text or not event_wrapper.event.text.strip():
                    logger.info("Skipping empty message")
                    return SlackWebhookResponse(status="ok", message="Empty message skipped")
                
                # Schedule Pub/Sub publishing as background task (respond to Slack immediately)
                background_tasks.add_task(publish_slack_event_background, event_wrapper)
                
                logger.info(f"Slack event {event_wrapper.event_id} queued for publishing")
                
                return SlackWebhookResponse(
                    status="ok",
                    message="Slack event received and queued for processing"
                )
                
            except Exception as e:
                logger.error(f"Error processing Slack event: {e}")
                return _create_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    error_message=f"Invalid event format: {str(e)}",
                    error_code="INVALID_EVENT",
                    details={"error": str(e)},
                )
        
        # Unknown event type
        else:
            logger.warning(f"Unknown Slack webhook type: {payload_data.get('type')}")
            return SlackWebhookResponse(status="ok", message="Unknown event type")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Slack webhook: {e}")
        return _create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_message="Internal server error occurred while processing Slack webhook",
            error_code="INTERNAL_ERROR",
            details={"error": str(e)},
        )


async def publish_slack_event(event_wrapper: SlackEventWrapper) -> Dict[str, str]:
    """
    Publish Slack event to SLACK_REPLY_EVENT pub/sub topic
    
    Args:
        event_wrapper: Slack event wrapper data
        
    Returns:
        Dictionary with publish result containing message_id
        
    Raises:
        PubSubServiceException: If publishing fails
    """
    try:
        # Prepare event data for pub/sub
        event_data = {
            "slack_event": event_wrapper.dict(),
            "source_service": "events-handler",
            "event_timestamp": time.time(),
            "event_type": "slack_reply",
        }
        
        # Prepare attributes for message routing
        attributes = {
            "source_service": "events-handler",
            "event_type": "slack_reply",
            "team_id": event_wrapper.team_id,
            "channel_id": event_wrapper.event.channel or "",
            "user_id": event_wrapper.event.user or "",
            "message_type": event_wrapper.event.type,
        }
        
        # Create topic if it doesn't exist
        topic_info = await pubsub_service.create_topic_if_not_exists(SLACK_REPLY_EVENT_TOPIC)
        
        # Publish the message
        publish_result = await pubsub_service.publish_message(
            topic_id=SLACK_REPLY_EVENT_TOPIC,
            message_data=event_data,
            attributes=attributes,
        )
        
        logger.info(f"Published Slack event to topic {topic_info['topic_path']} with message ID: {publish_result['message_id']}")
        
        return publish_result
        
    except Exception as e:
        logger.error(f"Failed to publish Slack event to pub/sub: {e}")
        raise PubSubServiceException(
            message=f"Failed to publish Slack event: {str(e)}",
            error_code="SLACK_PUBLISH_ERROR",
            details={"event_id": event_wrapper.event_id, "error": str(e)}
        )


async def publish_slack_event_background(event_wrapper: SlackEventWrapper) -> None:
    """
    Background task to publish Slack event to Pub/Sub
    This runs after responding to Slack to prevent timeouts
    """
    try:
        publish_result = await publish_slack_event(event_wrapper)
        logger.info(f"Background: Slack event {event_wrapper.event_id} published successfully with message ID: {publish_result['message_id']}")
    except Exception as e:
        logger.error(f"Background: Failed to publish Slack event {event_wrapper.event_id} to pub/sub: {e}")
        # Could implement retry logic or dead letter queue here


@router.get("/health")
async def slack_webhook_health():
    """Health check endpoint for Slack webhook"""
    return {"status": "healthy", "service": "slack-webhook"} 