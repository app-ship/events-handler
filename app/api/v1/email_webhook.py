"""
Email Webhook API for Events Handler
Receives Email Events API webhooks and publishes to pub/sub topics
"""

import logging
import time
import base64
import json
import os
import re
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

    This function fetches actual email content from Gmail API using the historyId.
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

        # Fetch actual email content from Gmail API
        email_content = await fetch_recent_email_content(email_address)

        if not email_content:
            logger.warning(
                f"No recent email content found for {email_address}, creating placeholder event"
            )
            # Fallback to placeholder content if Gmail API fails
            current_time = int(time.time())
            event_data = {
                "project_id": "infis-ai",  # Default project
                "event": {
                    "type": "email_reply",
                    "event_ts": str(current_time),
                    "from_email": email_address,
                    "to_email": "",  # Would be populated from Gmail API
                    "subject": f"Gmail Notification (History ID: {history_id})",
                    "body": f"Email notification received for {email_address} with history ID {history_id}. Gmail API content fetch failed, using placeholder.",
                    "thread_id": str(history_id),
                    "message_id": f"gmail-{history_id}-{current_time}",
                    "in_reply_to": "",
                },
                "type": "email_callback",
                "event_id": f"gmail-{history_id}-{current_time}",
                "event_time": current_time,
            }

            # Validate and create EmailEventWrapper with placeholder
            email_event = EmailEventWrapper(**event_data)
            logger.info(f"Created fallback EmailEventWrapper: {email_event.event_id}")
            return email_event

        # Create EmailEventWrapper with actual email content
        current_time = int(time.time())
        event_data = {
            "project_id": "infis-ai",  # Default project
            "event": {
                "type": "email_reply",
                "event_ts": str(current_time),
                "from_email": email_content["from_email"],
                "to_email": email_content["to_email"],
                "subject": email_content["subject"],
                "body": email_content["body"],
                "thread_id": email_content["thread_id"],
                "message_id": email_content["message_id"],
                "in_reply_to": email_content.get("in_reply_to", ""),
            },
            "type": "email_callback",
            "event_id": f"gmail-{history_id}-{current_time}",
            "event_time": current_time,
        }

        # Skip empty messages
        if not email_content["body"] or not email_content["body"].strip():
            logger.info("Skipping empty email message")
            return None

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


async def fetch_recent_email_content(email_address: str) -> Optional[Dict[str, str]]:
    """
    Fetch the most recent email content for the given email address using Gmail API.

    Returns:
        Dictionary with email content fields or None if no recent email found
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import base64
        import re

        # Get Gmail credentials from settings
        from app.core.config import settings

        gmail_oauth_token = settings.gmail_oauth_token

        if not gmail_oauth_token:
            logger.error("GMAIL_OAUTH_TOKEN not configured in settings")
            return None

        # Parse the OAuth token JSON
        try:
            token_info = json.loads(gmail_oauth_token)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse GMAIL_OAUTH_TOKEN: {e}")
            return None

        # Create credentials from the token info
        creds = Credentials(
            token=token_info.get("token"),
            refresh_token=token_info.get("refresh_token"),
            token_uri=token_info.get("token_uri"),
            client_id=token_info.get("client_id"),
            client_secret=token_info.get("client_secret"),
            scopes=[
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://mail.google.com/",
            ],
        )

        # Refresh token if expired
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request

            try:
                creds.refresh(Request())
                logger.info("Gmail credentials refreshed successfully")
            except Exception as e:
                logger.error(f"Failed to refresh Gmail credentials: {e}")
                return None

        # Build Gmail service
        service = build("gmail", "v1", credentials=creds)

        # Get the most recent message (within last 2 minutes)
        results = (
            service.users()
            .messages()
            .list(
                userId="me",
                q="newer_than:2m",  # Messages newer than 2 minutes
                maxResults=1,
            )
            .execute()
        )

        messages = results.get("messages", [])
        if not messages:
            logger.info("No recent messages found")
            return None

        # Get the most recent message details
        message_id = messages[0]["id"]
        message = service.users().messages().get(userId="me", id=message_id).execute()

        # Extract headers
        headers = {
            h["name"]: h["value"] for h in message.get("payload", {}).get("headers", [])
        }

        # Check if this is a reply (has In-Reply-To or References headers)
        is_reply = "In-Reply-To" in headers or "References" in headers
        if not is_reply:
            logger.info("Latest message is not a reply, skipping")
            return None

        # Extract email content
        content = extract_email_content(message)
        if not content:
            logger.warning("Could not extract content from email")
            return None

        return {
            "from_email": headers.get("From", ""),
            "to_email": headers.get("To", ""),
            "subject": headers.get("Subject", "No Subject"),
            "body": content,
            "thread_id": message.get("threadId", ""),
            "message_id": headers.get("Message-ID", message_id),
            "in_reply_to": headers.get("In-Reply-To", ""),
        }

    except Exception as e:
        logger.error(f"Error fetching email content from Gmail API: {e}")
        return None


def extract_email_content(message: Dict[str, Any]) -> str:
    """
    Extract the text content from the email message, trying to get only the latest reply.
    """
    try:
        if "payload" not in message:
            return ""

        content = ""

        # Check for plain text parts first
        if "parts" in message["payload"]:
            for part in message["payload"]["parts"]:
                if part["mimeType"] == "text/plain":
                    if "data" in part["body"]:
                        content = base64.urlsafe_b64decode(part["body"]["data"]).decode(
                            "utf-8"
                        )
                        break

        # If no plain text parts, try to get the body directly
        if (
            not content
            and "body" in message["payload"]
            and "data" in message["payload"]["body"]
        ):
            if message["payload"].get("mimeType") == "text/plain":
                content = base64.urlsafe_b64decode(
                    message["payload"]["body"]["data"]
                ).decode("utf-8")

        if content:
            # Split content into lines
            lines = content.splitlines()

            # Find where quoted text begins and remove it
            cut_off_index = len(lines)
            for i, line in enumerate(lines):
                # Common reply headers
                if re.match(r"On\s.*(wrote|écrit):$", line.strip(), re.IGNORECASE):
                    cut_off_index = i
                    break
                # Forwarded message header
                if line.strip() == "---------- Forwarded message ---------":
                    cut_off_index = i
                    break

            # Take all lines before the cut-off
            latest_reply_lines = lines[:cut_off_index]
            latest_reply = "\n".join(latest_reply_lines).strip()

            if latest_reply:
                return latest_reply
            else:
                # Try removing quoted lines (starting with ">")
                last_non_quote = -1
                for i in range(len(lines) - 1, -1, -1):
                    if not lines[i].strip().startswith(">"):
                        last_non_quote = i
                        break
                if last_non_quote != -1:
                    return "\n".join(lines[: last_non_quote + 1]).strip()

        # If we still don't have content, use the snippet
        if message.get("snippet"):
            return message.get("snippet", "")

        return content

    except Exception as e:
        logger.error(f"Error extracting email content: {e}")
        return ""


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
