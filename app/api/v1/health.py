import logging
from datetime import datetime

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.models.events import HealthCheckResponse, ErrorResponse
from app.services.pubsub import pubsub_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Basic health check",
    description="Basic health check endpoint that returns service status.",
    responses={
        200: {"description": "Service is healthy"},
        503: {"description": "Service is unhealthy"},
    },
)
async def health_check():
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "service": settings.app_name,
            "version": settings.app_version,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


@router.get(
    "/pubsub",
    response_model=HealthCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Pub/Sub health check",
    description="Check the health of Google Cloud Pub/Sub connection and services.",
    responses={
        200: {"model": HealthCheckResponse, "description": "Pub/Sub is healthy"},
        503: {"model": ErrorResponse, "description": "Pub/Sub is unhealthy"},
    },
)
async def pubsub_health_check():
    try:
        logger.info("Performing Pub/Sub health check")
        
        # Use a timeout to prevent hanging
        import asyncio
        health_info = await asyncio.wait_for(
            pubsub_service.health_check(), 
            timeout=10.0  # 10 second timeout
        )
        
        if health_info["status"] == "healthy":
            logger.info("Pub/Sub health check passed")
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=HealthCheckResponse(**health_info).dict(),
            )
        else:
            logger.warning("Pub/Sub health check failed")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=ErrorResponse(
                    error="Pub/Sub service is unhealthy",
                    error_code="PUBSUB_UNHEALTHY",
                    details=health_info,
                ).dict(),
            )
            
    except asyncio.TimeoutError:
        logger.error("Pub/Sub health check timed out")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse(
                error="Pub/Sub health check timed out",
                error_code="HEALTH_CHECK_TIMEOUT",
                details={"timeout": "10s"},
            ).dict(),
        )
    except Exception as e:
        logger.error(f"Pub/Sub health check error: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse(
                error="Failed to perform Pub/Sub health check",
                error_code="HEALTH_CHECK_ERROR",
                details={"error": str(e)},
            ).dict(),
        )


@router.get(
    "/ready",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Readiness check",
    description="Check if the service is ready to handle requests (includes Pub/Sub connectivity).",
    responses={
        200: {"description": "Service is ready"},
        503: {"description": "Service is not ready"},
    },
)
async def readiness_check():
    try:
        # Check Pub/Sub connectivity with timeout
        import asyncio
        health_info = await asyncio.wait_for(
            pubsub_service.health_check(),
            timeout=10.0  # 10 second timeout
        )
        
        if health_info["status"] == "healthy":
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "ready",
                    "service": settings.app_name,
                    "version": settings.app_version,
                    "pubsub": "connected",
                    "project_id": health_info.get("project_id"),
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "not ready",
                    "service": settings.app_name,
                    "version": settings.app_version,
                    "pubsub": "disconnected",
                    "error": health_info.get("error"),
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
            
    except asyncio.TimeoutError:
        logger.error("Readiness check timed out")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not ready",
                "service": settings.app_name,
                "version": settings.app_version,
                "pubsub": "timeout",
                "error": "Health check timed out after 10 seconds",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    except Exception as e:
        logger.error(f"Readiness check error: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not ready",
                "service": settings.app_name,
                "version": settings.app_version,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@router.get(
    "/live",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Liveness check",
    description="Check if the service is alive (basic service health without external dependencies).",
    responses={
        200: {"description": "Service is alive"},
    },
)
async def liveness_check():
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "alive",
            "service": settings.app_name,
            "version": settings.app_version,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )