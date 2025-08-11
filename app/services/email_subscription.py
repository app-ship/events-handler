"""
Email Subscription Service for Events Handler
Handles subscription to email-replies topic and publishes to app-email-reply-event
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

from google.api_core import exceptions as gcp_exceptions
from google.cloud import pubsub_v1
from google.pubsub_v1 import SubscriberClient
from google.pubsub_v1.types import PubsubMessage

from app.models.email_webhook import EmailEventWrapper
from app.services.pubsub import pubsub_service
from app.core.config import settings
from app.utils.exceptions import (
    PubSubServiceException,
    SubscriptionException,
)

logger = logging.getLogger(__name__)

# Source topic to subscribe to (Gmail API events)
EMAIL_SOURCE_TOPIC = "email-replies"
EMAIL_SOURCE_SUBSCRIPTION = "email-replies-subscription"

# Target topic to publish to (app events)
EMAIL_TARGET_TOPIC = "app-email-reply-event"


class EmailSubscriptionService:
    """Service for handling email subscription and event processing"""
    
    def __init__(self):
        self._subscriber = None
        self._is_running = False
        logger.info("EmailSubscriptionService initialized")

    @property
    def subscriber(self) -> SubscriberClient:
        """Get subscriber client"""
        if self._subscriber is None:
            self._subscriber = pubsub_service.subscriber
        return self._subscriber

    def _get_subscription_path(self, subscription_id: str) -> str:
        """Get subscription path"""
        return self.subscriber.subscription_path(
            pubsub_service.project_id, subscription_id
        )

    def _get_topic_path(self, topic_id: str) -> str:
        """Get topic path"""
        return self.subscriber.topic_path(pubsub_service.project_id, topic_id)

    async def create_subscription_if_not_exists(self) -> Dict[str, Any]:
        """Create email subscription if it doesn't exist"""
        try:
            subscription_path = self._get_subscription_path(EMAIL_SOURCE_SUBSCRIPTION)
            topic_path = self._get_topic_path(EMAIL_SOURCE_TOPIC)
            
            # Check if subscription exists
            try:
                subscription = self.subscriber.get_subscription(
                    request={"subscription": subscription_path}
                )
                logger.info(f"Email subscription already exists: {subscription_path}")
                return {
                    "subscription_path": subscription_path,
                    "topic_path": topic_path,
                    "created": False,
                    "message": "Subscription already exists"
                }
            except gcp_exceptions.NotFound:
                pass
            
            # Create subscription
            subscription = self.subscriber.create_subscription(
                request={
                    "name": subscription_path,
                    "topic": topic_path,
                    "ack_deadline_seconds": 600,  # 10 minutes
                }
            )
            
            logger.info(f"Created email subscription: {subscription_path}")
            return {
                "subscription_path": subscription_path,
                "topic_path": topic_path,
                "created": True,
                "message": "Subscription created successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to create email subscription: {e}")
            raise SubscriptionException(
                f"Failed to create email subscription: {str(e)}",
                error_code="SUBSCRIPTION_CREATION_ERROR",
                details={"error": str(e)}
            )

    async def process_email_message(self, message: PubsubMessage) -> None:
        """Process incoming email message from subscription"""
        try:
            # Parse message data
            message_data = json.loads(message.data.decode('utf-8'))
            logger.info(f"Processing email message: {message.message_id}")
            
            # Convert to EmailEventWrapper format
            email_event = self._convert_to_email_event(message_data, message.attributes)
            
            # Skip if conversion failed
            if not email_event:
                logger.warning("Skipping message - failed to convert to email event")
                message.ack()
                return
            
            # Publish to target topic
            await self._publish_to_target_topic(email_event)
            
            # Acknowledge the message
            message.ack()
            logger.info(f"Successfully processed email message: {message.message_id}")
            
        except Exception as e:
            logger.error(f"Error processing email message {message.message_id}: {e}")
            # Don't acknowledge - let it retry
            message.nack()

    def _convert_to_email_event(
        self, 
        message_data: Dict[str, Any], 
        attributes: Dict[str, str]
    ) -> Optional[EmailEventWrapper]:
        """Convert Gmail API message to EmailEventWrapper format"""
        try:
            # Extract email data from Gmail API format
            # This is a simplified conversion - adjust based on actual Gmail API format
            email_data = {
                "project_id": "infis-ai",
                "event": {
                    "type": "email_reply",
                    "event_ts": str(int(time.time())),
                    "from_email": message_data.get("from", ""),
                    "to_email": message_data.get("to", ""),
                    "subject": message_data.get("subject", ""),
                    "body": message_data.get("body", ""),
                    "thread_id": message_data.get("threadId", ""),
                    "message_id": message_data.get("messageId", ""),
                    "in_reply_to": message_data.get("inReplyTo", "")
                },
                "type": "email_callback",
                "event_id": f"Em{int(time.time())}{hash(message_data.get('messageId', '')) % 1000000}",
                "event_time": int(time.time())
            }
            
            # Validate required fields
            if not email_data["event"]["from_email"] or not email_data["event"]["body"]:
                logger.warning("Missing required email fields")
                return None
            
            return EmailEventWrapper(**email_data)
            
        except Exception as e:
            logger.error(f"Failed to convert message to email event: {e}")
            return None

    async def _publish_to_target_topic(self, email_event: EmailEventWrapper) -> None:
        """Publish email event to target topic"""
        try:
            # Prepare event data for pub/sub
            event_data = {
                "email_event": email_event.dict(),
                "source_service": "events-handler",
                "event_timestamp": time.time(),
                "event_type": "email_reply",
            }
            
            # Prepare attributes for message routing
            attributes = {
                "source_service": "events-handler",
                "event_type": "email_reply",
                "project_id": email_event.project_id,
                "from_email": email_event.event.from_email or "",
                "to_email": email_event.event.to_email or "",
                "message_type": email_event.event.type,
            }
            
            # Create topic if it doesn't exist
            topic_info = await pubsub_service.create_topic_if_not_exists(EMAIL_TARGET_TOPIC)
            
            # Publish the message
            publish_result = await pubsub_service.publish_message(
                topic_id=EMAIL_TARGET_TOPIC,
                message_data=event_data,
                attributes=attributes,
            )
            
            logger.info(f"Published email event to {EMAIL_TARGET_TOPIC} with message ID: {publish_result['message_id']}")
            
        except Exception as e:
            logger.error(f"Failed to publish email event to target topic: {e}")
            raise PubSubServiceException(
                f"Failed to publish email event: {str(e)}",
                error_code="EMAIL_PUBLISH_ERROR",
                details={"event_id": email_event.event_id, "error": str(e)}
            )

    async def start_subscription_listener(self) -> None:
        """Start listening to email subscription"""
        try:
            # Create subscription if needed
            await self.create_subscription_if_not_exists()
            
            subscription_path = self._get_subscription_path(EMAIL_SOURCE_SUBSCRIPTION)
            
            # Configure flow control
            flow_control = pubsub_v1.types.FlowControl(max_messages=100)
            
            logger.info(f"Starting email subscription listener on: {subscription_path}")
            self._is_running = True
            
            # Start pulling messages
            while self._is_running:
                try:
                    # Pull messages synchronously with timeout
                    response = self.subscriber.pull(
                        request={
                            "subscription": subscription_path,
                            "max_messages": 10,
                        },
                        timeout=30.0,  # 30 second timeout
                    )
                    
                    if response.received_messages:
                        logger.info(f"Received {len(response.received_messages)} email messages")
                        
                        # Process messages
                        for received_message in response.received_messages:
                            await self.process_email_message(received_message.message)
                    
                    # Small delay to prevent tight loop
                    await asyncio.sleep(1)
                    
                except gcp_exceptions.DeadlineExceeded:
                    # Timeout is normal - continue listening
                    continue
                except Exception as e:
                    logger.error(f"Error in email subscription listener: {e}")
                    await asyncio.sleep(5)  # Wait before retrying
            
        except Exception as e:
            logger.error(f"Failed to start email subscription listener: {e}")
            raise SubscriptionException(
                f"Failed to start email subscription listener: {str(e)}",
                error_code="SUBSCRIPTION_LISTENER_ERROR",
                details={"error": str(e)}
            )

    async def stop_subscription_listener(self) -> None:
        """Stop subscription listener"""
        logger.info("Stopping email subscription listener")
        self._is_running = False

    async def health_check(self) -> Dict[str, Any]:
        """Health check for email subscription service"""
        try:
            subscription_path = self._get_subscription_path(EMAIL_SOURCE_SUBSCRIPTION)
            
            # Check if subscription exists
            subscription = self.subscriber.get_subscription(
                request={"subscription": subscription_path}
            )
            
            return {
                "status": "healthy",
                "service": "email-subscription",
                "subscription_path": subscription_path,
                "is_running": self._is_running,
                "subscription_exists": True
            }
            
        except gcp_exceptions.NotFound:
            return {
                "status": "unhealthy",
                "service": "email-subscription",
                "subscription_path": subscription_path,
                "is_running": self._is_running,
                "subscription_exists": False,
                "error": "Subscription not found"
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "email-subscription",
                "is_running": self._is_running,
                "error": str(e)
            }


# Global service instance
email_subscription_service = EmailSubscriptionService()