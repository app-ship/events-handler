import logging
import sys
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import events, health
from app.core.config import settings
from app.utils.exceptions import EventsHandlerException


def setup_logging():
    """Configure structured logging"""
    timestamper = structlog.processors.TimeStamper(fmt="iso")
    
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    setup_logging()
    logger = structlog.get_logger()
    logger.info("Starting Events Handler API", version=settings.app_version)
    
    yield
    
    # Shutdown
    logger.info("Shutting down Events Handler API")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Centralized event handling microservice using Google Cloud Pub/Sub",
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_hosts,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(EventsHandlerException)
async def events_handler_exception_handler(request: Request, exc: EventsHandlerException):
    """Handle custom EventsHandlerException"""
    logger = structlog.get_logger()
    logger.error(
        "EventsHandlerException occurred",
        error=exc.message,
        error_code=exc.error_code,
        details=exc.details,
        path=request.url.path,
        method=request.method,
    )
    
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "error": exc.message,
            "error_code": exc.error_code,
            "details": exc.details,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    logger = structlog.get_logger()
    logger.error(
        "Unhandled exception occurred",
        error=str(exc),
        path=request.url.path,
        method=request.method,
        exc_info=True,
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "An unexpected error occurred",
            "error_code": "INTERNAL_ERROR",
        },
    )


# Add request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests"""
    logger = structlog.get_logger()
    
    # Log request
    logger.info(
        "Request received",
        method=request.method,
        path=request.url.path,
        query_params=str(request.query_params),
        client_host=request.client.host if request.client else None,
    )
    
    # Process request
    response = await call_next(request)
    
    # Log response
    logger.info(
        "Request completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
    )
    
    return response


# Include API routers
app.include_router(
    events.router,
    prefix=settings.api_v1_prefix,
)

app.include_router(
    health.router,
    prefix=settings.api_v1_prefix,
)

# Root health check (for load balancers)
@app.get("/health")
async def root_health_check():
    """Simple health check for load balancers"""
    return {"status": "healthy", "service": settings.app_name}


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "description": "Centralized event handling microservice using Google Cloud Pub/Sub",
        "docs": "/docs",
        "health": "/health",
        "api": {
            "v1": {
                "events": f"{settings.api_v1_prefix}/events",
                "health": f"{settings.api_v1_prefix}/health",
            }
        },
    }


if __name__ == "__main__":
    import uvicorn
    
    port = settings.port
    
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=port,  # Use the port variable instead of hardcoded 8001
        reload=settings.debug,
        log_config=None,  # We use our own logging configuration
    )