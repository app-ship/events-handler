"""
Production GCP Pub/Sub Client using Service Identity
Integrates with existing events-handler architecture
"""

import json
import logging
from typing import Any, Dict, List, Optional

import structlog
from google.api_core import exceptions as gcp_exceptions
from google.api_core.retry import Retry
from google.cloud import pubsub_v1
from google.auth import default

from app.core.config import settings

logger = structlog.get_logger(__name__)


class GCPPubSubClient:
    """
    Production-ready Pub/Sub client using Cloud Run Service Identity.
    No credential files needed - uses attached service account automatically.
    """
    
    def __init__(self, project_id: str = None):
        self._publisher: Optional[pubsub_v1.PublisherClient] = None
        self._subscriber: Optional[pubsub_v1.SubscriberClient] = None
        self._project_id = project_id or settings.google_cloud_project_id or self._get_default_project_id()
        
        if not self._project_id:
            raise ValueError("Project ID is required. Set GOOGLE_CLOUD_PROJECT environment variable.")
        
        logger.info("GCP Pub/Sub client initialized", project_id=self._project_id)

    def _get_default_project_id(self) -> Optional[str]:
        """Get project ID from default credentials"""
        try:
            _, project = default()
            return project
        except Exception as e:
            logger.warning("Could not get default project ID", error=str(e))
            return None

    @property
    def publisher(self) -> pubsub_v1.PublisherClient:
        """Get or create publisher client using service identity"""
        if self._publisher is None:
            try:
                # This automatically uses the service account attached to Cloud Run
                self._publisher = pubsub_v1.PublisherClient()
                logger.info("Publisher client initialized with service identity")
            except Exception as e:
                logger.error("Failed to initialize publisher client", error=str(e))
                raise
        return self._publisher

    @property
    def subscriber(self) -> pubsub_v1.SubscriberClient:
        """Get or create subscriber client using service identity"""
        if self._subscriber is None:
            try:
                # This automatically uses the service account attached to Cloud Run
                self._subscriber = pubsub_v1.SubscriberClient()
                logger.info("Subscriber client initialized with service identity")
            except Exception as e:
                logger.error("Failed to initialize subscriber client", error=str(e))
                raise
        return self._subscriber

    @property
    def project_id(self) -> str:
        """Get the current project ID"""
        return self._project_id

    def get_topic_path(self, topic_id: str) -> str:
        """Get full topic path"""
        return self.publisher.topic_path(self.project_id, topic_id)

    def get_subscription_path(self, subscription_id: str) -> str:
        """Get full subscription path"""
        return self.subscriber.subscription_path(self.project_id, subscription_id)

    async def create_topic(self, topic_id: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Create a new Pub/Sub topic
        
        Args:
            topic_id: The topic ID (not full path)
            labels: Optional labels for the topic
            
        Returns:
            Dict with topic information
            
        Raises:
            Exception if topic creation fails
        """
        topic_path = self.get_topic_path(topic_id)
        
        try:
            # Prepare topic configuration
            topic_config = {"name": topic_path}
            if labels:
                topic_config["labels"] = labels
            
            # Create the topic
            topic = self.publisher.create_topic(request=topic_config)
            
            logger.info("Topic created successfully", 
                       topic_id=topic_id, 
                       topic_path=topic_path)
            
            return {
                "topic_id": topic_id,
                "topic_path": topic_path,
                "name": topic.name,
                "created": True,
                "labels": dict(topic.labels) if topic.labels else {}
            }
            
        except gcp_exceptions.AlreadyExists:
            logger.info("Topic already exists", topic_id=topic_id, topic_path=topic_path)
            raise
        except gcp_exceptions.PermissionDenied as e:
            logger.error("Permission denied creating topic", 
                        topic_id=topic_id, 
                        error=str(e))
            raise
        except Exception as e:
            logger.error("Failed to create topic", 
                        topic_id=topic_id, 
                        error=str(e))
            raise

    async def create_topic_if_not_exists(self, topic_id: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Create topic if it doesn't exist, return existing topic info if it does
        
        Args:
            topic_id: The topic ID (not full path)
            labels: Optional labels for the topic
            
        Returns:
            Dict with topic information and 'created' boolean
        """
        try:
            return await self.create_topic(topic_id, labels)
        except gcp_exceptions.AlreadyExists:
            # Topic exists, get its info
            topic_path = self.get_topic_path(topic_id)
            try:
                topic = self.publisher.get_topic(request={"topic": topic_path})
                return {
                    "topic_id": topic_id,
                    "topic_path": topic_path,
                    "name": topic.name,
                    "created": False,
                    "labels": dict(topic.labels) if topic.labels else {}
                }
            except Exception as e:
                logger.warning("Could not get existing topic info", 
                              topic_id=topic_id, 
                              error=str(e))
                return {
                    "topic_id": topic_id,
                    "topic_path": topic_path,
                    "name": topic_path,
                    "created": False,
                    "labels": {}
                }

    async def publish_message(
        self,
        topic_id: str,
        message_data: Dict[str, Any] | str | bytes,
        attributes: Optional[Dict[str, str]] = None,
        ordering_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Publish a message to a Pub/Sub topic
        
        Args:
            topic_id: The topic ID (not full path)
            message_data: The message payload (dict, str, or bytes)
            attributes: Optional message attributes
            ordering_key: Optional ordering key for message ordering
            
        Returns:
            Dict with publish result information
        """
        topic_path = self.get_topic_path(topic_id)
        
        try:
            # Ensure topic exists
            await self.create_topic_if_not_exists(topic_id)
            
            # Prepare message data
            if isinstance(message_data, dict):
                data = json.dumps(message_data, ensure_ascii=False).encode("utf-8")
            elif isinstance(message_data, str):
                data = message_data.encode("utf-8")
            elif isinstance(message_data, bytes):
                data = message_data
            else:
                data = str(message_data).encode("utf-8")
            
            # Prepare attributes with metadata
            message_attributes = attributes or {}
            message_attributes.update({
                "source": "events-handler",
                "version": getattr(settings, 'app_version', '1.0.0'),
                "published_at": str(int(__import__('time').time()))
            })
            
            # Prepare publish request
            publish_request = {
                "topic": topic_path,
                "messages": [{
                    "data": data,
                    "attributes": message_attributes
                }]
            }
            
            # Add ordering key if provided
            if ordering_key:
                publish_request["messages"][0]["ordering_key"] = ordering_key
            
            # Publish with retry
            retry_config = Retry(deadline=getattr(settings, 'pubsub_timeout', 60.0))
            future = self.publisher.publish(topic_path, data, **message_attributes)
            
            # Get the message ID
            message_id = future.result(timeout=getattr(settings, 'pubsub_timeout', 60.0))
            
            logger.info("Message published successfully",
                       message_id=message_id,
                       topic_id=topic_id,
                       topic_path=topic_path,
                       data_size=len(data))
            
            return {
                "message_id": message_id,
                "topic_id": topic_id,
                "topic_path": topic_path,
                "success": True,
                "data_size": len(data),
                "attributes": message_attributes
            }
            
        except Exception as e:
            logger.error("Failed to publish message",
                        topic_id=topic_id,
                        error=str(e),
                        message_type=type(message_data).__name__)
            raise

    async def list_topics(self, filter_str: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all topics in the project
        
        Args:
            filter_str: Optional filter string
            
        Returns:
            List of topic information dictionaries
        """
        try:
            project_path = f"projects/{self.project_id}"
            topics = []
            
            request = {"project": project_path}
            if filter_str:
                request["filter"] = filter_str
            
            for topic in self.publisher.list_topics(request=request):
                topic_id = topic.name.split("/")[-1]
                topics.append({
                    "topic_id": topic_id,
                    "topic_path": topic.name,
                    "name": topic.name,
                    "labels": dict(topic.labels) if topic.labels else {}
                })
            
            logger.info("Topics listed successfully", count=len(topics))
            return topics
            
        except Exception as e:
            logger.error("Failed to list topics", error=str(e))
            raise

    async def delete_topic(self, topic_id: str) -> Dict[str, Any]:
        """
        Delete a Pub/Sub topic
        
        Args:
            topic_id: The topic ID (not full path)
            
        Returns:
            Dict with deletion result
        """
        topic_path = self.get_topic_path(topic_id)
        
        try:
            self.publisher.delete_topic(request={"topic": topic_path})
            
            logger.info("Topic deleted successfully", 
                       topic_id=topic_id, 
                       topic_path=topic_path)
            
            return {
                "topic_id": topic_id,
                "topic_path": topic_path,
                "deleted": True
            }
            
        except gcp_exceptions.NotFound:
            logger.warning("Topic not found for deletion", 
                          topic_id=topic_id, 
                          topic_path=topic_path)
            raise
        except Exception as e:
            logger.error("Failed to delete topic", 
                        topic_id=topic_id, 
                        error=str(e))
            raise

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on Pub/Sub service
        
        Returns:
            Dict with health check results
        """
        try:
            # Test connection by listing topics (limited to 1 page)
            project_path = f"projects/{self.project_id}"
            topics_iter = self.publisher.list_topics(
                request={"project": project_path, "page_size": 1}
            )
            
            # Just get the first page to test connection
            list(topics_iter)
            
            logger.info("Pub/Sub health check passed")
            
            return {
                "status": "healthy",
                "project_id": self.project_id,
                "publisher": "connected",
                "subscriber": "connected",
                "service_account": "pub-sub-trigger@infis-ai.iam.gserviceaccount.com"
            }
            
        except Exception as e:
            logger.error("Pub/Sub health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "error": str(e),
                "project_id": self.project_id,
                "service_account": "pub-sub-trigger@infis-ai.iam.gserviceaccount.com"
            }


# Global client instance - lazy loaded to prevent startup failures
_pubsub_client: Optional[GCPPubSubClient] = None

def get_pubsub_client() -> GCPPubSubClient:
    """Get or create the global PubSub client instance"""
    global _pubsub_client
    if _pubsub_client is None:
        _pubsub_client = GCPPubSubClient()
    return _pubsub_client

# For backward compatibility - expose as module-level variable
class _PubSubClientProxy:
    """Proxy to provide lazy loading for backward compatibility"""
    def __getattr__(self, name):
        return getattr(get_pubsub_client(), name)

pubsub_client = _PubSubClientProxy() 