"""
Anonymous Signal - Backend Entry Point
=======================================
Privacy-first FastAPI application.

PRIVACY GUARANTEES:
  - Access logs DISABLED at Uvicorn and middleware levels
  - Request IP never read or stored
  - No session tracking
  - No fingerprinting headers forwarded
"""

import asyncio
import logging
import sys

import structlog
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import create_db_and_tables
from app.core.privacy_middleware import PrivacyMiddleware, RateLimitMiddleware
from app.core.security_headers import SecurityHeadersMiddleware

# ─── Logging Configuration ────────────────────────────────────────────────────
# PRIVACY: structlog configured to NEVER include IP, user-agent, or request path
# in production. Only log processing events, errors, and AI pipeline steps.
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer()
        if settings.ENVIRONMENT == "development"
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.DEBUG if settings.ENVIRONMENT == "development" else logging.WARNING
    ),
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = structlog.get_logger(__name__)

# Background task handle (so we can cancel on shutdown)
_scheduler_task: asyncio.Task | None = None


def create_application() -> FastAPI:
    """Factory function to create the FastAPI application."""

    app = FastAPI(
        title="Anonymous Signal API",
        description="Privacy-first anonymous reporting & early-warning platform",
        version="1.0.0",
        # PRIVACY: Disable OpenAPI docs in production to prevent API enumeration
        docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
        openapi_url="/openapi.json" if settings.ENVIRONMENT == "development" else None,
    )

    # ─── Privacy Middleware (MUST be first) ───────────────────────────────────
    app.add_middleware(PrivacyMiddleware)

    # ─── Rate Limiting ────────────────────────────────────────────────────────
    app.add_middleware(RateLimitMiddleware)

    # ─── Security Headers ─────────────────────────────────────────────────────
    app.add_middleware(SecurityHeadersMiddleware)

    # ─── CORS ─────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,  # No cookies, no credentials
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=[],
    )

    # ─── Trusted Host ─────────────────────────────────────────────────────────
    if settings.ENVIRONMENT == "production":
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.ALLOWED_HOSTS,
        )

    # ─── Routes ───────────────────────────────────────────────────────────────
    app.include_router(api_router, prefix="/api/v1")

    # ─── Lifecycle Events ─────────────────────────────────────────────────────
    @app.on_event("startup")
    async def startup_event():
        global _scheduler_task
        logger.info("anonymous_signal_starting", environment=settings.ENVIRONMENT)
        await create_db_and_tables()
        logger.info("database_initialized")

        # Start the intelligence scheduler as a background task
        if settings.ENVIRONMENT != "testing":
            from app.services.intelligence_scheduler import run_intelligence_scheduler
            _scheduler_task = asyncio.create_task(
                run_intelligence_scheduler(settings.DATABASE_URL)
            )
            logger.info("intelligence_scheduler_started")

    @app.on_event("shutdown")
    async def shutdown_event():
        global _scheduler_task
        if _scheduler_task and not _scheduler_task.done():
            _scheduler_task.cancel()
            try:
                await _scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("anonymous_signal_shutting_down")

    # ─── Global Exception Handler ─────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # PRIVACY: Do NOT include request details in error responses
        logger.error("unhandled_exception", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # ─── Health Check ─────────────────────────────────────────────────────────
    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "operational", "service": "anonymous-signal"}

    return app


app = create_application()

if __name__ == "__main__":
    # PRIVACY: access_log=False disables Uvicorn's built-in request logging
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        access_log=False,  # PRIVACY: No request logging
        log_level="warning",
        reload=settings.ENVIRONMENT == "development",
    )
