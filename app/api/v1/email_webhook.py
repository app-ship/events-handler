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

from fastapi import APIRouter, HTTPException, Request, status, BackgroundTasks
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
EMAIL_REPLY_EVENT_TOPIC = os.getenv("EMAIL_REPLY_TOPIC", "stage-email-reply-topic")
EMAIL_REPLY_TOPIC = os.getenv("EMAIL_REPLY_TOPIC", "stage-email-reply-topic")


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
        content=error_response.model_dump(mode="json"),
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
async def email_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Email Events API webhook endpoint

    This endpoint:
    1. Receives Email Events API webhooks
    2. Handles URL verification challenges
    3. Publishes Email events to EMAIL_REPLY_EVENT pub/sub topic (asynchronously)
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
                
                # Log org_id information from the event
                org_id = getattr(event_wrapper.event, 'org_id', None)
                logger.info(f"[ORG ID TRACKING] Event received with org_id: {org_id}")
                logger.info(f"[ORG ID TRACKING] Event metadata: from_email={getattr(event_wrapper.event, 'from_email', 'N/A')}, to_email={getattr(event_wrapper.event, 'to_email', 'N/A')}")

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

                # Schedule Pub/Sub publishing as background task (respond to Gmail immediately)
                background_tasks.add_task(publish_email_event_background, event_wrapper)

                logger.info(f"Email event {event_wrapper.event_id} queued for publishing")

                return EmailWebhookResponse(
                    status="ok", message="Email event received and queued for processing"
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
        # Log org_id tracking at publish level
        org_id = getattr(event_wrapper.event, 'org_id', None)
        logger.info(f"[ORG ID TRACKING] Publishing email event with org_id: {org_id}")
        logger.info(f"[ORG ID TRACKING] Event ID: {event_wrapper.event_id}, Project ID: {event_wrapper.project_id}")
        
        # Prepare event data for pub/sub
        event_data = {
            "email_event": event_wrapper.model_dump(),
            "source_service": "events-handler",
            "event_timestamp": time.time(),
            "event_type": "email_reply",
        }

        # Log the full event data structure for debugging
        logger.info(f"[ORG ID TRACKING] Event data keys: {list(event_data.keys())}")
        logger.info(f"[ORG ID TRACKING] Email event keys: {list(event_data['email_event'].keys()) if 'email_event' in event_data else 'No email_event key'}")
        if 'email_event' in event_data and 'event' in event_data['email_event']:
            logger.info(f"[ORG ID TRACKING] Email event.event keys: {list(event_data['email_event']['event'].keys())}")
            logger.info(f"[ORG ID TRACKING] Email event.event.org_id: {event_data['email_event']['event'].get('org_id', 'NOT_FOUND')}")

        # Prepare attributes for message routing
        attributes = {
            "source_service": "events-handler",
            "event_type": "email_reply",
            "project_id": event_wrapper.project_id,
            "from_email": event_wrapper.event.from_email or "",
            "to_email": event_wrapper.event.to_email or "",
            "message_type": event_wrapper.event.type,
        }
        
        # Add org_id to attributes if present
        if org_id:
            attributes["org_id"] = org_id
            logger.info(f"[ORG ID TRACKING] Added org_id to pubsub attributes: {org_id}")
        else:
            logger.warning(f"[ORG ID TRACKING] No org_id found to add to pubsub attributes")

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


async def publish_email_event_background(event_wrapper: EmailEventWrapper) -> None:
    """
    Background task to publish Email event to Pub/Sub
    This runs after responding to Gmail to prevent timeouts
    """
    try:
        publish_result = await publish_email_event(event_wrapper)
        logger.info(f"Background: Email event {event_wrapper.event_id} published successfully with message ID: {publish_result['message_id']}")
    except Exception as e:
        logger.error(f"Background: Failed to publish Email event {event_wrapper.event_id} to pub/sub: {e}")
        # Could implement retry logic or dead letter queue here


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
        logger.info(f"[Gmail Notification] Attempting to fetch email content for {email_address}...")
        try:
            email_content = await fetch_recent_email_content(email_address)
            if email_content:
                logger.info(f"[Gmail Notification] Gmail API fetch SUCCESS - Retrieved email content")
                logger.info(f"[Gmail Notification] Content summary: From={email_content.get('from_email', 'N/A')}, Subject='{email_content.get('subject', 'N/A')}'")
                logger.debug(f"[Gmail Notification] Full email content keys: {list(email_content.keys())}")
            else:
                logger.warning(f"[Gmail Notification] Gmail API fetch FAILED - No content returned")
        except Exception as e:
            logger.error(f"[Gmail Notification] Gmail API fetch failed with exception: {e}")
            logger.error(f"[Gmail Notification] Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"[Gmail Notification] Full traceback: {traceback.format_exc()}")
            email_content = None

        if not email_content:
            logger.warning(
                f"No recent email content found for {email_address}, creating placeholder event"
            )
            logger.info("This could be due to: Gmail API failure, token expiration, no recent emails, or non-reply emails")
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
            try:
                email_event = EmailEventWrapper(**event_data)
                logger.info(f"Created fallback EmailEventWrapper: {email_event.event_id}")
                return email_event
            except Exception as e:
                logger.error(f"Failed to create fallback EmailEventWrapper: {e}")
                logger.error(f"Event data: {event_data}")
                return None

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
                "references": email_content.get("references", ""),
                "org_id": email_content.get("org_id"),  # Include org_id from email headers
                "headers": email_content.get("headers"),  # Include headers for additional metadata
            },
            "type": "email_callback",
            "event_id": f"Em{int(time.time())}{hash(email_content.get('message_id', '')) % 1000000}",
            "event_time": current_time,
        }

        # Validate and create EmailEventWrapper
        try:
            email_event = EmailEventWrapper(**event_data)
            logger.info(
                f"Created EmailEventWrapper from Gmail notification: {email_event.event_id}"
            )
            return email_event
        except Exception as e:
            logger.error(f"Failed to create EmailEventWrapper from Gmail content: {e}")
            logger.error(f"Email content: {email_content}")
            logger.error(f"Event data: {event_data}")
            return None

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
    logger.info(f"[Gmail API] Starting email content fetch for: {email_address}")
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import base64
        import re

        # Get Gmail credentials from settings
        from app.core.config import settings

        gmail_oauth_token = settings.gmail_oauth_token

        if not gmail_oauth_token:
            logger.error("[Gmail API] GMAIL_OAUTH_TOKEN not configured in settings")
            return None

        logger.debug(f"[Gmail API] Gmail OAuth token configured, length: {len(gmail_oauth_token)}")

        # Parse the OAuth token JSON
        try:
            token_info = json.loads(gmail_oauth_token)
            logger.debug(f"[Gmail API] Successfully parsed OAuth token, keys: {list(token_info.keys())}")
        except json.JSONDecodeError as e:
            logger.error(f"[Gmail API] Failed to parse GMAIL_OAUTH_TOKEN: {e}")
            return None

        # Create credentials from the token info
        logger.debug(f"[Gmail API] Creating credentials with client_id: {token_info.get('client_id', 'N/A')[:20]}...")
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

        logger.debug(f"[Gmail API] Credentials created. Expired: {creds.expired}, Has refresh token: {bool(creds.refresh_token)}")

        # Refresh token if expired
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request

            try:
                logger.info("[Gmail API] Refreshing expired credentials...")
                creds.refresh(Request())
                logger.info("[Gmail API] Gmail credentials refreshed successfully")
            except Exception as e:
                logger.error(f"[Gmail API] Failed to refresh Gmail credentials: {e}")
                return None

        # Build Gmail service
        logger.debug("[Gmail API] Building Gmail service client...")
        service = build("gmail", "v1", credentials=creds)
        logger.info("[Gmail API] Gmail service client built successfully")

        # Get the most recent message (within last 2 minutes)
        logger.info("[Gmail API] Querying for recent messages (newer than 2 minutes)...")
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
        logger.info(f"[Gmail API] Found {len(messages)} recent messages")
        
        if not messages:
            logger.info("[Gmail API] No recent messages found (within last 2 minutes)")
            return None

        # Get the most recent message details
        message_id = messages[0]["id"]
        logger.info(f"[Gmail API] Fetching details for message ID: {message_id}")
        message = service.users().messages().get(userId="me", id=message_id).execute()
        logger.debug(f"[Gmail API] Message details retrieved. Thread ID: {message.get('threadId', 'N/A')}")

        # Extract headers
        payload_headers = message.get("payload", {}).get("headers", [])
        headers = {
            h["name"]: h["value"] for h in payload_headers
        }
        logger.debug(f"[Gmail API] Extracted {len(headers)} headers from message")
        logger.debug(f"[Gmail API] Key headers: From={headers.get('From', 'N/A')}, Subject={headers.get('Subject', 'N/A')[:50]}...")
        
        # Check if this is a reply (has In-Reply-To or References headers)
        is_reply = "In-Reply-To" in headers or "References" in headers
        logger.info(f"[Gmail API] Message reply status: {is_reply} (In-Reply-To: {'✓' if 'In-Reply-To' in headers else '✗'}, References: {'✓' if 'References' in headers else '✗'})")
        
        # Extract org_id from X-Org-Id header if present in the reply message
        org_id = None
        for header_name in ['X-Org-Id', 'X-Organization-Id', 'X-Org-ID']:
            if header_name in headers:
                org_id = headers[header_name]
                logger.info(f"[ORG ID TRACKING - Gmail API] Found organization ID in reply header {header_name}: {org_id}")
                break
        
        # If no org_id in reply (which is normal), try to get it from the original message in the thread
        if not org_id and is_reply:
            logger.info("[ORG ID TRACKING - Gmail API] No org_id in reply message, fetching original message from thread")
            try:
                # Get the thread ID to fetch all messages in the thread
                thread_id = message.get("threadId")
                if thread_id:
                    logger.info(f"[ORG ID TRACKING - Gmail API] Fetching thread messages for thread_id: {thread_id}")
                    thread = service.users().threads().get(userId="me", id=thread_id).execute()
                    
                    # Look through all messages in thread to find the original message with X-Org-Id
                    thread_messages = thread.get("messages", [])
                    logger.info(f"[ORG ID TRACKING - Gmail API] Found {len(thread_messages)} messages in thread")
                    
                    for i, thread_message in enumerate(thread_messages):
                        # Skip the current reply message
                        if thread_message.get("id") == message_id:
                            continue
                            
                        thread_headers = {h["name"]: h["value"] for h in thread_message.get("payload", {}).get("headers", [])}
                        
                        # Look for X-Org-Id in this message
                        for header_name in ['X-Org-Id', 'X-Organization-Id', 'X-Org-ID']:
                            if header_name in thread_headers:
                                org_id = thread_headers[header_name]
                                logger.info(f"[ORG ID TRACKING - Gmail API] Found org_id in original message #{i}: {org_id}")
                                break
                        
                        if org_id:
                            break
                    
                    if not org_id:
                        logger.warning(f"[ORG ID TRACKING - Gmail API] No X-Org-Id found in any of {len(thread_messages)} messages in thread")
                else:
                    logger.warning("[ORG ID TRACKING - Gmail API] No thread_id available to fetch original message")
                    
            except Exception as e:
                logger.error(f"[ORG ID TRACKING - Gmail API] Error fetching original message from thread: {e}")
        
        if not org_id:
            logger.warning("[ORG ID TRACKING - Gmail API] No X-Org-Id header found in reply or original message")
            logger.info(f"[ORG ID TRACKING - Gmail API] Available reply headers: {list(headers.keys())}")
        else:
            logger.info(f"[ORG ID TRACKING - Gmail API] Successfully extracted org_id: {org_id}")
        
        if not is_reply:
            logger.info("[Gmail API] Latest message is not a reply, skipping")
            return None

        # Extract email content
        logger.info("[Gmail API] Extracting email content from message...")
        content = extract_email_content(message)
        
        if not content:
            logger.warning("[Gmail API] Could not extract content from email")
            return None
            
        logger.info(f"[Gmail API] Successfully extracted email content, length: {len(content)} characters")
        logger.debug(f"[Gmail API] Content preview: {content[:100]}...")

        extracted_data = {
            "from_email": headers.get("From", ""),
            "to_email": headers.get("To", ""),
            "subject": headers.get("Subject", "No Subject"),
            "body": content,
            "thread_id": message.get("threadId", ""),
            "message_id": headers.get("Message-ID", message_id),
            "in_reply_to": headers.get("In-Reply-To", ""),
            "references": headers.get("References", ""),
            "org_id": org_id,  # Add org_id from X-Org-Id header
            "headers": headers,  # Include all headers for additional parsing
        }
        
        logger.info(f"[Gmail API] Email extraction completed successfully:")
        logger.info(f"  From: {extracted_data['from_email']}")
        logger.info(f"  To: {extracted_data['to_email']}")
        logger.info(f"  Subject: {extracted_data['subject']}")
        logger.info(f"  Thread ID: {extracted_data['thread_id']}")
        logger.info(f"  Message-ID: {extracted_data['message_id']}")
        logger.info(f"  In-Reply-To: {extracted_data['in_reply_to']}")
        logger.info(f"  References: {extracted_data['references'][:100]}..." if len(extracted_data['references']) > 100 else f"  References: {extracted_data['references']}")
        logger.info(f"  Body length: {len(extracted_data['body'])} characters")
        logger.info(f"[ORG ID TRACKING - Gmail API] Final extracted org_id: {extracted_data.get('org_id', 'NOT_FOUND')}")
        
        return extracted_data

    except Exception as e:
        logger.error(f"[Gmail API] Error fetching email content from Gmail API: {e}")
        logger.error(f"[Gmail API] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"[Gmail API] Full traceback: {traceback.format_exc()}")
        return None


def extract_email_content(message: Dict[str, Any]) -> str:
    """
    Extract the text content from the email message, trying to get only the latest reply.
    """
    logger.debug("[Gmail Content] Starting email content extraction...")
    try:
        if "payload" not in message:
            logger.warning("[Gmail Content] No payload found in message")
            return ""

        content = ""
        payload = message["payload"]
        logger.debug(f"[Gmail Content] Payload structure: mimeType={payload.get('mimeType', 'N/A')}, has_parts={bool(payload.get('parts'))}")

        # Check for plain text parts first
        if "parts" in payload:
            parts = payload["parts"]
            logger.debug(f"[Gmail Content] Found {len(parts)} parts in message")
            
            for i, part in enumerate(parts):
                part_mime_type = part.get("mimeType", "unknown")
                logger.debug(f"[Gmail Content] Part {i}: mimeType={part_mime_type}, has_body_data={bool(part.get('body', {}).get('data'))}")
                
                if part_mime_type == "text/plain":
                    if "data" in part["body"]:
                        logger.info(f"[Gmail Content] Found plain text content in part {i}")
                        content = base64.urlsafe_b64decode(part["body"]["data"]).decode(
                            "utf-8"
                        )
                        logger.debug(f"[Gmail Content] Decoded content length: {len(content)} characters")
                        break
            
            if not content:
                logger.debug("[Gmail Content] No plain text parts found with content")
        else:
            logger.debug("[Gmail Content] No parts found in payload")

        # If no plain text parts, try to get the body directly
        if (
            not content
            and "body" in payload
            and "data" in payload["body"]
        ):
            payload_mime_type = payload.get("mimeType")
            logger.debug(f"[Gmail Content] Trying direct body extraction. Payload mimeType: {payload_mime_type}")
            
            if payload_mime_type == "text/plain":
                logger.info("[Gmail Content] Found plain text content in direct body")
                content = base64.urlsafe_b64decode(
                    payload["body"]["data"]
                ).decode("utf-8")
                logger.debug(f"[Gmail Content] Decoded direct body content length: {len(content)} characters")
            else:
                logger.debug(f"[Gmail Content] Direct body is not plain text ({payload_mime_type}), skipping")

        if content:
            logger.info(f"[Gmail Content] Processing content for reply extraction. Original length: {len(content)} characters")
            
            # Split content into lines
            lines = content.splitlines()
            logger.debug(f"[Gmail Content] Split content into {len(lines)} lines")

            # Find where quoted text begins and remove it
            cut_off_index = len(lines)
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                # Common reply headers
                if re.match(r"On\s.*(wrote|écrit):$", line_stripped, re.IGNORECASE):
                    logger.debug(f"[Gmail Content] Found reply header at line {i}: {line_stripped[:50]}...")
                    cut_off_index = i
                    break
                # Forwarded message header
                if line_stripped == "---------- Forwarded message ---------":
                    logger.debug(f"[Gmail Content] Found forwarded message header at line {i}")
                    cut_off_index = i
                    break

            logger.debug(f"[Gmail Content] Quote cut-off index: {cut_off_index} (out of {len(lines)} lines)")

            # Take all lines before the cut-off
            latest_reply_lines = lines[:cut_off_index]
            latest_reply = "\n".join(latest_reply_lines).strip()

            if latest_reply:
                logger.info(f"[Gmail Content] Successfully extracted reply content, length: {len(latest_reply)} characters")
                logger.debug(f"[Gmail Content] Reply preview: {latest_reply[:100]}...")
                return latest_reply
            else:
                logger.debug("[Gmail Content] No content after quote removal, trying quote line removal...")
                # Try removing quoted lines (starting with ">")
                last_non_quote = -1
                for i in range(len(lines) - 1, -1, -1):
                    if not lines[i].strip().startswith(">"):
                        last_non_quote = i
                        break
                        
                logger.debug(f"[Gmail Content] Last non-quote line index: {last_non_quote}")
                
                if last_non_quote != -1:
                    result = "\n".join(lines[: last_non_quote + 1]).strip()
                    logger.info(f"[Gmail Content] Extracted content after removing quote lines, length: {len(result)} characters")
                    return result
        else:
            logger.warning("[Gmail Content] No content extracted from message parts or body")

        # If we still don't have content, use the snippet
        snippet = message.get("snippet")
        if snippet:
            logger.info(f"[Gmail Content] Falling back to message snippet, length: {len(snippet)} characters")
            logger.debug(f"[Gmail Content] Snippet content: {snippet}")
            return snippet
        
        logger.warning("[Gmail Content] No content found in message - no parts, body, or snippet")
        return content

    except Exception as e:
        logger.error(f"[Gmail Content] Error extracting email content: {e}")
        logger.error(f"[Gmail Content] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"[Gmail Content] Full traceback: {traceback.format_exc()}")
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
            # Validate that we have a proper EmailEventWrapper before publishing
            if not isinstance(processed_event, EmailEventWrapper):
                logger.error(f"process_gmail_notification returned invalid type: {type(processed_event)}")
                return {
                    "status": "error",
                    "processed": False,
                    "message": "Invalid processed event type"
                }
            
            # Additional validation to ensure we're not publishing raw Gmail data
            if hasattr(processed_event, 'emailAddress') or hasattr(processed_event, 'historyId'):
                logger.error("Detected raw Gmail data in processed_event - preventing publication")
                logger.error(f"Problematic data: {processed_event}")
                return {
                    "status": "error", 
                    "processed": False,
                    "message": "Raw Gmail data detected - processing failed"
                }
            
            # Publish formatted event to stage topic for AgentHub consumption
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
