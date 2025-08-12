"""
Email Subscription Service for Events Handler
Handles subscription to email-replies topic and publishes to app-email-reply-event
"""

import asyncio
import json
import logging
import os
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
EMAIL_SOURCE_TOPIC = os.getenv("EMAIL_REPLIES_TOPIC", "email-replies")
EMAIL_SOURCE_SUBSCRIPTION = os.getenv("EMAIL_REPLIES_SUBSCRIPTION", "email-replies-subscription")

# Target topic to publish to (app events)
EMAIL_TARGET_TOPIC = os.getenv("EMAIL_REPLY_TOPIC", "stage-email-reply-topic")


class EmailSubscriptionService:
    """Service for handling email subscription and event processing"""
    
    def __init__(self):
        self._subscriber = None
        self._is_running = False
        # DISABLED: This service conflicts with the main email processing flow
        # The proper email processing happens through /api/v1/email/push endpoint
        logger.info("EmailSubscriptionService initialized (DISABLED - conflicts with main email flow)")

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
        logger.warning("EmailSubscriptionService is DISABLED - use /api/v1/email/push endpoint instead")
        return {
            "status": "disabled",
            "message": "EmailSubscriptionService is disabled - use /api/v1/email/push endpoint",
            "subscription_path": None,
            "topic_path": None
        }

    async def process_email_message(self, message: PubsubMessage) -> None:
        """Process incoming email message from subscription"""
        logger.warning("EmailSubscriptionService.process_email_message called but service is DISABLED")
        return
        
    def _convert_to_email_event(
        self, 
        message_data: Dict[str, Any], 
        attributes: Dict[str, str]
    ) -> Optional[EmailEventWrapper]:
        """Convert Gmail API message to EmailEventWrapper format"""
        logger.warning("EmailSubscriptionService._convert_to_email_event called but service is DISABLED")
        return None

    async def _publish_to_target_topic(self, email_event: EmailEventWrapper) -> None:
        """Publish email event to target topic"""
        logger.warning("EmailSubscriptionService._publish_to_target_topic called but service is DISABLED")
        return

    async def start_subscription_listener(self) -> None:
        """Start listening to email subscription"""
        logger.warning("EmailSubscriptionService is DISABLED - cannot start subscription listener")
        logger.info("Use the main email processing flow through /api/v1/email/push endpoint instead")
        return

    async def stop_subscription_listener(self) -> None:
        """Stop subscription listener"""
        logger.info("EmailSubscriptionService.stop_subscription_listener called (service is DISABLED)")
        self._is_running = False

    async def health_check(self) -> Dict[str, Any]:
        """Health check for email subscription service"""
        return {
            "status": "disabled",
            "service": "email-subscription",
            "message": "EmailSubscriptionService is disabled - use /api/v1/email/push endpoint instead",
            "is_running": False,
            "subscription_exists": False,
            "reason": "Conflicts with main email processing flow"
        }


# Global service instance
email_subscription_service = EmailSubscriptionService()