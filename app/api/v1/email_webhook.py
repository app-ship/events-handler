"""
Email Webhook API for Events Handler
Receives Email Events API webhooks and publishes to pub/sub topics
"""

import logging
import time
import base64
import json
from typing import Any, Dict, Optional

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
EMAIL_REPLY_EVENT_TOPIC = "stage-email-reply-topic"
STAGE_EMAIL_REPLY_TOPIC = "stage-email-reply-topic"
RAW_GMAIL_PUSH_TOPIC = "raw-gmail-push-stage"


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
        200: {
            "model": EmailWebhookResponse,
            "description": "Email event processed successfully",
        },
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

        # Parse JSON body
        try:
            payload_data = json.loads(body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in request body")
            return _create_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_message="Invalid JSON",
                error_code="INVALID_JSON",
            )

        # Handle URL verification challenge
        if payload_data.get("type") == "url_verification":
            try:
                challenge = EmailChallenge(**payload_data)
                return EmailWebhookResponse(status="ok", challenge=challenge.challenge)
            except Exception as e:
                logger.error(f"Invalid challenge payload: {e}")
                return _create_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    error_message=f"Invalid challenge payload: {str(e)}",
                    error_code="INVALID_CHALLENGE",
                )

        # Handle event callback
        elif payload_data.get("type") == "email_callback":
            try:
                # Parse the Email event
                event_wrapper = EmailEventWrapper(**payload_data)

                logger.info(
                    f"Received Email event: {event_wrapper.event_id} from project {event_wrapper.project_id}"
                )
                logger.info(f"Event type: {event_wrapper.event.type}")

                # Process supported Email events (email_reply)
                supported_event_types = {"email_reply"}
                if event_wrapper.event.type not in supported_event_types:
                    logger.info(
                        f"Skipping unsupported event: {event_wrapper.event.type}"
                    )
                    return EmailWebhookResponse(
                        status="ok", message="Unsupported event skipped"
                    )

                # Skip empty messages
                if not event_wrapper.event.body or not event_wrapper.event.body.strip():
                    logger.info("Skipping empty email message")
                    return EmailWebhookResponse(
                        status="ok", message="Empty email message skipped"
                    )

                # Publish to pub/sub topic
                publish_result = await publish_email_event(event_wrapper)

                logger.info(
                    f"Email event {event_wrapper.event_id} published successfully with message ID: {publish_result['message_id']}"
                )

                return EmailWebhookResponse(
                    status="ok", message="Email event published to pub/sub"
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
            "email_event": event_wrapper.model_dump(),
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
        topic_info = await pubsub_service.create_topic_if_not_exists(
            EMAIL_REPLY_EVENT_TOPIC
        )

        # Publish the message
        publish_result = await pubsub_service.publish_message(
            topic_id=EMAIL_REPLY_EVENT_TOPIC,
            message_data=event_data,
            attributes=attributes,
        )

        logger.info(
            f"Published Email event to topic {topic_info['topic_path']} with message ID: {publish_result['message_id']}"
        )

        return publish_result

    except Exception as e:
        logger.error(f"Failed to publish Email event to pub/sub: {e}")
        raise PubSubServiceException(
            message=f"Failed to publish Email event: {str(e)}",
            error_code="EMAIL_PUBLISH_ERROR",
            details={"event_id": event_wrapper.event_id, "error": str(e)},
        )


async def process_gmail_notification(
    gmail_data: Dict[str, Any], _attributes: Dict[str, str]
) -> Optional[EmailEventWrapper]:
    """
    Process Gmail push notification and convert to EmailEventWrapper format.

    Gmail push notifications have format:
    {
        "emailAddress": "user@domain.com",
        "historyId": 12345
    }

    This function would need to fetch actual email content from Gmail API using the historyId.
    For now, we'll create a placeholder implementation that handles basic structure.
    """
    try:
        # Extract email address and history ID from Gmail notification
        email_address = gmail_data.get("emailAddress")
        history_id = gmail_data.get("historyId")

        if not email_address or not history_id:
            logger.warning(
                f"Missing required fields in Gmail notification: emailAddress={email_address}, historyId={history_id}"
            )
            return None

        logger.info(
            f"Processing Gmail notification for {email_address} with historyId {history_id}"
        )

        # TODO: In a complete implementation, you would:
        # 1. Use Gmail API to fetch the actual email content using historyId
        # 2. Extract the email subject, body, thread_id, message_id, etc.
        # 3. Determine if this is actually a reply that needs processing

        # For now, create a placeholder EmailEventWrapper with available data
        # This ensures the structure is correct even without full Gmail API integration
        current_time = int(time.time())
        event_data = {
            "project_id": "infis-ai",  # Default project
            "event": {
                "type": "email_reply",
                "event_ts": str(current_time),
                "from_email": email_address,
                "to_email": "",  # Would be populated from Gmail API
                "subject": f"Gmail Notification (History ID: {history_id})",
                "body": f"Email notification received for {email_address} with history ID {history_id}. Full content would be fetched from Gmail API.",
                "thread_id": str(history_id),
                "message_id": f"gmail-{history_id}-{current_time}",
                "in_reply_to": "",
            },
            "type": "email_callback",
            "event_id": f"gmail-{history_id}-{current_time}",
            "event_time": current_time,
        }

        # Validate and create EmailEventWrapper
        email_event = EmailEventWrapper(**event_data)
        logger.info(
            f"Created EmailEventWrapper from Gmail notification: {email_event.event_id}"
        )
        return email_event

    except Exception as e:
        logger.error(f"Failed to process Gmail notification: {e}")
        logger.error(f"Gmail data: {gmail_data}")
        return None


@router.post(
    "/push",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Pub/Sub push endpoint for Gmail email-replies",
    description="Receives Pub/Sub push messages from topic 'email-replies', processes Gmail notifications, and publishes formatted events to 'stage-email-reply-topic'",
)
async def email_push_subscription(request: Request):
    """Handle Pub/Sub push for projects/infis-ai/topics/email-replies and process Gmail notifications"""
    try:
        body = await request.json()
        # Expecting standard Pub/Sub push: {"message": {"data": base64, "attributes": {...}}, "subscription": "..."}
        message = body.get("message", {})
        attributes = message.get("attributes", {}) or {}
        data_b64 = message.get("data", "")

        try:
            decoded = (
                json.loads(base64.b64decode(data_b64).decode("utf-8"))
                if data_b64
                else {}
            )
        except Exception as e:
            logger.error(f"Invalid base64 data in Pub/Sub push: {e}")
            return _create_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_message="Invalid Pub/Sub data",
                error_code="INVALID_PUBSUB_DATA",
            )

        logger.info(f"Received Gmail push notification: {decoded}")

        # Republish raw payload to raw stage topic for debugging/backup
        await pubsub_service.create_topic_if_not_exists(RAW_GMAIL_PUSH_TOPIC)
        await pubsub_service.publish_message(
            topic_id=RAW_GMAIL_PUSH_TOPIC,
            message_data=decoded,
            attributes=attributes,
        )

        # Process Gmail notification data into EmailReplyEventData format
        processed_event = await process_gmail_notification(decoded, attributes)
        if processed_event:
            # Publish formatted event to stage topic for AgentHog consumption
            publish_result = await publish_email_event(processed_event)
            logger.info(
                f"Successfully processed Gmail notification and published event with message ID: {publish_result['message_id']}"
            )
            return {
                "status": "ok",
                "message_id": publish_result.get("message_id"),
                "processed": True,
            }
        else:
            logger.info("Gmail notification skipped - no actionable email event")
            return {
                "status": "ok",
                "processed": False,
                "message": "No actionable email event",
            }

    except Exception as e:
        logger.error(f"Error handling email push subscription: {e}")
        return _create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_message="Internal error handling Pub/Sub push",
            error_code="PUSH_HANDLER_ERROR",
            details={"error": str(e)},
        )


@router.get("/health")
async def email_webhook_health():
    """Health check endpoint for Email webhook"""
    return {"status": "healthy", "service": "email-webhook"}
