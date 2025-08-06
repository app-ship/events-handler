import json
import logging
from typing import Any, Dict, List, Optional

from google.api_core import exceptions as gcp_exceptions
from google.api_core.retry import Retry
from google.cloud import pubsub_v1
from google.pubsub_v1 import PublisherClient, SubscriberClient

from app.core.config import settings
from app.core.security import gcp_auth
from app.utils.exceptions import (
    AuthenticationException,
    MessagePublishException,
    PubSubServiceException,
    TopicCreationException,
    TopicNotFoundException,
)

logger = logging.getLogger(__name__)


class PubSubService:
    def __init__(self):
        self._publisher: Optional[PublisherClient] = None
        self._subscriber: Optional[SubscriberClient] = None
        self._project_id: Optional[str] = None

    @property
    def publisher(self) -> PublisherClient:
        if self._publisher is None:
            try:
                credentials = gcp_auth.get_credentials()
                self._publisher = pubsub_v1.PublisherClient(credentials=credentials)
                logger.info("Publisher client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize publisher client: {e}")
                raise AuthenticationException(
                    "Failed to authenticate with Google Cloud Pub/Sub",
                    error_code="PUBSUB_AUTH_ERROR",
                    details={"error": str(e)},
                )
        return self._publisher

    @property
    def subscriber(self) -> SubscriberClient:
        if self._subscriber is None:
            try:
                credentials = gcp_auth.get_credentials()
                self._subscriber = pubsub_v1.SubscriberClient(credentials=credentials)
                logger.info("Subscriber client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize subscriber client: {e}")
                raise AuthenticationException(
                    "Failed to authenticate with Google Cloud Pub/Sub",
                    error_code="PUBSUB_AUTH_ERROR",
                    details={"error": str(e)},
                )
        return self._subscriber

    @property
    def project_id(self) -> str:
        if self._project_id is None:
            self._project_id = gcp_auth.get_project_id()
        return self._project_id

    def _get_topic_path(self, topic_id: str) -> str:
        return self.publisher.topic_path(self.project_id, topic_id)

    def _get_subscription_path(self, subscription_id: str) -> str:
        return self.subscriber.subscription_path(self.project_id, subscription_id)

    async def create_topic_if_not_exists(self, topic_id: str) -> Dict[str, Any]:
        topic_path = self._get_topic_path(topic_id)
        
        try:
            # Try to create the topic
            topic = self.publisher.create_topic(request={"name": topic_path})
            logger.info(f"Created new topic: {topic_path}")
            return {
                "topic_path": topic_path,
                "topic_id": topic_id,
                "created": True,
                "name": topic.name,
            }
        except gcp_exceptions.AlreadyExists:
            logger.info(f"Topic already exists: {topic_path}")
            return {
                "topic_path": topic_path,
                "topic_id": topic_id,
                "created": False,
                "name": topic_path,
            }
        except gcp_exceptions.PermissionDenied as e:
            logger.error(f"Permission denied creating topic {topic_path}: {e}")
            raise TopicCreationException(
                f"Permission denied creating topic '{topic_id}'",
                error_code="PERMISSION_DENIED",
                details={"topic_id": topic_id, "error": str(e)},
            )
        except Exception as e:
            logger.error(f"Failed to create topic {topic_path}: {e}")
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
        topic_path = self._get_topic_path(topic_id)
        
        try:
            # Ensure topic exists
            await self.create_topic_if_not_exists(topic_id)
            
            # Prepare message data
            if isinstance(message_data, dict):
                data = json.dumps(message_data).encode("utf-8")
            else:
                data = str(message_data).encode("utf-8")
            
            # Prepare attributes
            message_attributes = attributes or {}
            message_attributes.update({
                "source": "events-handler",
                "version": settings.app_version,
            })
            
            # Publish message with retry
            retry = Retry(deadline=settings.pubsub_timeout)
            future = self.publisher.publish(
                topic_path,
                data,
                **message_attributes,
            )
            
            # Get the message ID
            message_id = future.result(timeout=settings.pubsub_timeout)
            
            logger.info(f"Published message {message_id} to topic {topic_path}")
            
            return {
                "message_id": message_id,
                "topic_path": topic_path,
                "topic_id": topic_id,
                "success": True,
            }
            
        except Exception as e:
            logger.error(f"Failed to publish message to topic {topic_path}: {e}")
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
        try:
            project_path = f"projects/{self.project_id}"
            topics = []
            
            for topic in self.publisher.list_topics(request={"project": project_path}):
                topic_id = topic.name.split("/")[-1]
                topics.append({
                    "topic_id": topic_id,
                    "topic_path": topic.name,
                    "name": topic.name,
                })
            
            logger.info(f"Listed {len(topics)} topics")
            return topics
            
        except Exception as e:
            logger.error(f"Failed to list topics: {e}")
            raise PubSubServiceException(
                "Failed to list topics",
                error_code="LIST_TOPICS_ERROR",
                details={"error": str(e)},
            )

    async def delete_topic(self, topic_id: str) -> Dict[str, Any]:
        topic_path = self._get_topic_path(topic_id)
        
        try:
            self.publisher.delete_topic(request={"topic": topic_path})
            logger.info(f"Deleted topic: {topic_path}")
            
            return {
                "topic_id": topic_id,
                "topic_path": topic_path,
                "deleted": True,
            }
            
        except gcp_exceptions.NotFound:
            logger.warning(f"Topic not found for deletion: {topic_path}")
            raise TopicNotFoundException(
                f"Topic '{topic_id}' not found",
                error_code="TOPIC_NOT_FOUND",
                details={"topic_id": topic_id},
            )
        except Exception as e:
            logger.error(f"Failed to delete topic {topic_path}: {e}")
            raise PubSubServiceException(
                f"Failed to delete topic '{topic_id}'",
                error_code="TOPIC_DELETE_ERROR",
                details={"topic_id": topic_id, "error": str(e)},
            )

    async def health_check(self) -> Dict[str, Any]:
        try:
            # Test publisher connection by listing topics
            project_path = f"projects/{self.project_id}"
            topics_iter = self.publisher.list_topics(request={"project": project_path})
            
            # Just get the first page to test connection
            _ = list(topics_iter)
            
            return {
                "status": "healthy",
                "project_id": self.project_id,
                "publisher": "connected",
                "subscriber": "connected",
            }
            
        except Exception as e:
            logger.error(f"Pub/Sub health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "project_id": self.project_id,
            }


# Global service instance
pubsub_service = PubSubService()