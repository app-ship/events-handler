import json
import logging
from typing import Any, Dict, List, Optional

from google.api_core import exceptions as gcp_exceptions
from google.api_core.retry import Retry
from google.cloud import pubsub_v1
from google.pubsub_v1 import PublisherClient, SubscriberClient

from app.core.config import settings
from app.services.gcp_pubsub_client import get_pubsub_client
from app.utils.exceptions import (
    AuthenticationException,
    MessagePublishException,
    PubSubServiceException,
    TopicCreationException,
    TopicNotFoundException,
)

logger = logging.getLogger(__name__)


class PubSubService:
    """
    Legacy PubSubService that now uses secure service identity.
    Maintained for backward compatibility with existing code.
    """
    
    def __init__(self):
        # Use lazy loading to prevent startup failures
        self._client = None
        logger.info("PubSubService initialized (client will be created on first use)")

    @property
    def _get_client(self):
        """Lazy load the client"""
        if self._client is None:
            try:
                self._client = get_pubsub_client()
            except Exception as e:
                logger.error(f"Failed to initialize PubSub client: {e}")
                raise
        return self._client

    @property
    def publisher(self) -> PublisherClient:
        """Get publisher client (uses service identity)"""
        return self._get_client.publisher

    @property
    def subscriber(self) -> SubscriberClient:
        """Get subscriber client (uses service identity)"""
        return self._get_client.subscriber

    @property
    def project_id(self) -> str:
        """Get project ID"""
        return self._get_client.project_id

    def _get_topic_path(self, topic_id: str) -> str:
        """Get topic path - delegates to secure client"""
        return self._get_client.get_topic_path(topic_id)

    def _get_subscription_path(self, subscription_id: str) -> str:
        """Get subscription path - delegates to secure client"""
        return self._get_client.get_subscription_path(subscription_id)

    async def create_topic_if_not_exists(self, topic_id: str) -> Dict[str, Any]:
        """Create topic if not exists - uses secure service identity"""
        try:
            return await self._get_client.create_topic_if_not_exists(topic_id)
        except gcp_exceptions.PermissionDenied as e:
            logger.error(f"Permission denied creating topic {topic_id}: {e}")
            raise TopicCreationException(
                f"Permission denied creating topic '{topic_id}'",
                error_code="PERMISSION_DENIED",
                details={"topic_id": topic_id, "error": str(e)},
            )
        except Exception as e:
            logger.error(f"Failed to create topic {topic_id}: {e}")
            raise TopicCreationException(
                f"Failed to create topic '{topic_id}'",
                error_code="TOPIC_CREATION_ERROR",
                details={"topic_id": topic_id, "error": str(e)},
            )

    async def publish_message(
        self,
        topic_id: str,
        message_data: Dict[str, Any],
        attributes: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Publish message - uses secure service identity"""
        try:
            return await self._get_client.publish_message(topic_id, message_data, attributes)
        except Exception as e:
            logger.error(f"Failed to publish message to topic {topic_id}: {e}")
            raise MessagePublishException(
                f"Failed to publish message to topic '{topic_id}'",
                error_code="MESSAGE_PUBLISH_ERROR",
                details={
                    "topic_id": topic_id,
                    "error": str(e),
                    "message_data": message_data,
                },
            )

    async def list_topics(self) -> List[Dict[str, Any]]:
        """List topics - uses secure service identity"""
        try:
            return await self._get_client.list_topics()
        except Exception as e:
            logger.error(f"Failed to list topics: {e}")
            raise PubSubServiceException(
                "Failed to list topics",
                error_code="LIST_TOPICS_ERROR",
                details={"error": str(e)},
            )

    async def delete_topic(self, topic_id: str) -> Dict[str, Any]:
        """Delete topic - uses secure service identity"""
        try:
            return await self._get_client.delete_topic(topic_id)
        except gcp_exceptions.NotFound:
            logger.warning(f"Topic not found for deletion: {topic_id}")
            raise TopicNotFoundException(
                f"Topic '{topic_id}' not found",
                error_code="TOPIC_NOT_FOUND",
                details={"topic_id": topic_id},
            )
        except Exception as e:
            logger.error(f"Failed to delete topic {topic_id}: {e}")
            raise PubSubServiceException(
                f"Failed to delete topic '{topic_id}'",
                error_code="TOPIC_DELETE_ERROR",
                details={"topic_id": topic_id, "error": str(e)},
            )

    async def health_check(self) -> Dict[str, Any]:
        """Health check - uses secure service identity"""
        return await self._get_client.health_check()


# Global service instance
pubsub_service = PubSubService()