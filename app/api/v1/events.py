import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from app.models.events import (
    EventTriggerRequest,
    EventTriggerResponse,
    TopicCreateRequest,
    TopicCreateResponse,
    TopicsListResponse,
    TopicDeleteResponse,
    TopicResponse,
    ErrorResponse,
)
from app.services.pubsub import pubsub_service
from app.utils.exceptions import (
    EventsHandlerException,
    PubSubServiceException,
    TopicNotFoundException,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["events"])


def _create_error_response(
    status_code: int,
    error_message: str,
    error_code: str = None,
    details: Dict[str, Any] = None,
) -> JSONResponse:
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
    "/trigger",
    response_model=EventTriggerResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger an event",
    description="Trigger an event by publishing a message to a Pub/Sub topic. "
    "The topic will be created automatically if it doesn't exist.",
    responses={
        200: {"model": EventTriggerResponse, "description": "Event triggered successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request data"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def trigger_event(request: EventTriggerRequest):
    try:
        logger.info(f"Triggering event: {request.event_name}")
        
        # Prepare attributes
        attributes = request.attributes or {}
        if request.source_service:
            attributes["source_service"] = request.source_service
        
        # First, create topic if not exists
        topic_info = await pubsub_service.create_topic_if_not_exists(request.event_name)
        
        # Publish the message
        publish_result = await pubsub_service.publish_message(
            topic_id=request.event_name,
            message_data=request.event_data,
            attributes=attributes,
        )
        
        logger.info(f"Event '{request.event_name}' triggered successfully with message ID: {publish_result['message_id']}")
        
        return EventTriggerResponse(
            success=True,
            message="Event triggered successfully",
            event_name=request.event_name,
            topic_path=topic_info["topic_path"],
            message_id=publish_result["message_id"],
            topic_created=topic_info["created"],
        )
        
    except EventsHandlerException as e:
        logger.error(f"Events handler error: {e.message}")
        return _create_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_message=e.message,
            error_code=e.error_code,
            details=e.details,
        )
    except Exception as e:
        logger.error(f"Unexpected error triggering event: {e}")
        return _create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_message="Internal server error occurred while triggering event",
            error_code="INTERNAL_ERROR",
            details={"error": str(e)},
        )


@router.get(
    "/topics",
    response_model=TopicsListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all topics",
    description="Retrieve a list of all Pub/Sub topics in the project.",
    responses={
        200: {"model": TopicsListResponse, "description": "Topics retrieved successfully"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def list_topics():
    try:
        logger.info("Listing all topics")
        
        topics_data = await pubsub_service.list_topics()
        
        topics = [
            TopicResponse(
                topic_id=topic["topic_id"],
                topic_path=topic["topic_path"],
                name=topic["name"],
            )
            for topic in topics_data
        ]
        
        logger.info(f"Retrieved {len(topics)} topics")
        
        return TopicsListResponse(
            success=True,
            message="Topics retrieved successfully",
            topics=topics,
            count=len(topics),
        )
        
    except PubSubServiceException as e:
        logger.error(f"Pub/Sub service error: {e.message}")
        return _create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_message=e.message,
            error_code=e.error_code,
            details=e.details,
        )
    except Exception as e:
        logger.error(f"Unexpected error listing topics: {e}")
        return _create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_message="Internal server error occurred while listing topics",
            error_code="INTERNAL_ERROR",
            details={"error": str(e)},
        )


@router.post(
    "/topics",
    response_model=TopicCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a topic",
    description="Manually create a new Pub/Sub topic.",
    responses={
        201: {"model": TopicCreateResponse, "description": "Topic created successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request data"},
        409: {"model": TopicCreateResponse, "description": "Topic already exists"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def create_topic(request: TopicCreateRequest):
    try:
        logger.info(f"Creating topic: {request.topic_id}")
        
        topic_info = await pubsub_service.create_topic_if_not_exists(request.topic_id)
        
        topic = TopicResponse(
            topic_id=topic_info["topic_id"],
            topic_path=topic_info["topic_path"],
            name=topic_info["name"],
        )
        
        response_status = status.HTTP_201_CREATED if topic_info["created"] else status.HTTP_200_OK
        message = "Topic created successfully" if topic_info["created"] else "Topic already exists"
        
        logger.info(f"Topic '{request.topic_id}' {'created' if topic_info['created'] else 'already exists'}")
        
        response = TopicCreateResponse(
            success=True,
            message=message,
            topic=topic,
            created=topic_info["created"],
        )
        
        return JSONResponse(
            status_code=response_status,
            content=response.dict(),
        )
        
    except EventsHandlerException as e:
        logger.error(f"Events handler error: {e.message}")
        return _create_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_message=e.message,
            error_code=e.error_code,
            details=e.details,
        )
    except Exception as e:
        logger.error(f"Unexpected error creating topic: {e}")
        return _create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_message="Internal server error occurred while creating topic",
            error_code="INTERNAL_ERROR",
            details={"error": str(e)},
        )


@router.delete(
    "/topics/{topic_id}",
    response_model=TopicDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a topic",
    description="Delete an existing Pub/Sub topic.",
    responses={
        200: {"model": TopicDeleteResponse, "description": "Topic deleted successfully"},
        404: {"model": ErrorResponse, "description": "Topic not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def delete_topic(topic_id: str):
    try:
        logger.info(f"Deleting topic: {topic_id}")
        
        result = await pubsub_service.delete_topic(topic_id)
        
        logger.info(f"Topic '{topic_id}' deleted successfully")
        
        return TopicDeleteResponse(
            success=True,
            message="Topic deleted successfully",
            topic_id=result["topic_id"],
            topic_path=result["topic_path"],
        )
        
    except TopicNotFoundException as e:
        logger.warning(f"Topic not found for deletion: {e.message}")
        return _create_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            error_message=e.message,
            error_code=e.error_code,
            details=e.details,
        )
    except EventsHandlerException as e:
        logger.error(f"Events handler error: {e.message}")
        return _create_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_message=e.message,
            error_code=e.error_code,
            details=e.details,
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting topic: {e}")
        return _create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_message="Internal server error occurred while deleting topic",
            error_code="INTERNAL_ERROR",
            details={"error": str(e)},
        )