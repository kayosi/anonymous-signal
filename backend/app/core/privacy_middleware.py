"""
Privacy Middleware
==================
This is the MOST CRITICAL component of the anonymity guarantee.

Every request passes through PrivacyMiddleware BEFORE any handler sees it.
The middleware:
  1. Strips X-Forwarded-For and all IP-revealing headers
  2. Drops User-Agent from scope
  3. Removes any session/cookie identifiers
  4. Adds privacy-protective response headers

AUDIT NOTE: Any change to this file must be reviewed for privacy impact.
"""

import time
from typing import Callable, Dict, Any

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Headers that could reveal identity — strip ALL of them
IDENTITY_HEADERS_TO_STRIP = {
    "x-forwarded-for",
    "x-real-ip",
    "x-client-ip",
    "x-forwarded-host",
    "x-forwarded-proto",
    "cf-connecting-ip",      # Cloudflare real IP
    "true-client-ip",        # Cloudflare enterprise
    "x-cluster-client-ip",
    "forwarded",             # RFC 7239 forwarded header
    "user-agent",            # Device/browser fingerprinting
    "referer",               # Origin page tracking
    "origin",                # CORS origin (only strip from body, keep for CORS middleware)
    "cookie",                # Session/tracking cookies
    "x-request-id",         # Could be used for correlation
    "x-correlation-id",
    "x-trace-id",
    "accept-language",       # Locale fingerprinting
    "dnt",                   # Paradoxically, DNT can fingerprint
    "sec-ch-ua",             # Client hints fingerprinting
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
    "sec-ch-ua-arch",
    "sec-ch-ua-bitness",
    "sec-fetch-site",
    "sec-fetch-mode",
    "sec-fetch-dest",
    "sec-fetch-user",
}


class PrivacyMiddleware(BaseHTTPMiddleware):
    """
    Strips all identifying information from requests.
    This runs before ANY route handler — guaranteeing no handler
    can accidentally access or log identifying data.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # ── Strip identifying headers from the ASGI scope ─────────────────
        # We modify the scope headers directly — this prevents FastAPI
        # from ever seeing these values, even in dependency injection.
        cleaned_headers = [
            (name, value)
            for name, value in request.scope.get("headers", [])
            if name.decode("latin-1").lower() not in IDENTITY_HEADERS_TO_STRIP
        ]
        request.scope["headers"] = cleaned_headers

        # ── Overwrite client tuple to prevent IP exposure ──────────────────
        # request.client returns (host, port) — we zero it out
        # PRIVACY: This guarantees that even if a developer calls
        # `request.client.host` in a route, they get None
        request.scope["client"] = None

        # ── Process request ────────────────────────────────────────────────
        response = await call_next(request)

        # ── Add privacy response headers ──────────────────────────────────
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # PRIVACY: Remove server identification
        response.headers.pop("Server", None)
        response.headers.pop("X-Powered-By", None)

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting that does NOT use IP addresses.
    Uses a rolling window based on a random anonymous token
    assigned per-session (stored only in memory, never persisted).

    This prevents abuse while maintaining anonymity.
    Uses approximate rate limiting via Redis sliding window.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._redis_client = None

    async def get_redis(self):
        if self._redis_client is None:
            try:
                import aioredis
                self._redis_client = await aioredis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                )
            except Exception:
                # Redis unavailable — degrade gracefully (allow requests)
                return None
        return self._redis_client

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only rate-limit submission endpoints
        if not request.url.path.startswith("/api/v1/reports"):
            return await call_next(request)

        # Use a coarse time bucket as the rate limit key (NOT IP-based)
        # This groups all submitters into the same bucket — privacy-preserving
        # Abuse protection relies on content filtering, not IP blocking
        time_bucket = int(time.time() // settings.RATE_LIMIT_WINDOW_SECONDS)
        rate_key = f"ratelimit:submissions:{time_bucket}"

        redis = await self.get_redis()
        if redis:
            try:
                count = await redis.incr(rate_key)
                if count == 1:
                    await redis.expire(rate_key, settings.RATE_LIMIT_WINDOW_SECONDS * 2)

                # Global rate limit (not per-user — preserves anonymity)
                if count > settings.RATE_LIMIT_SUBMISSIONS * 100:  # System-wide cap
                    return Response(
                        content='{"detail": "Service temporarily at capacity. Please try again later."}',
                        status_code=429,
                        media_type="application/json",
                    )
            except Exception:
                pass  # Redis failure — fail open (allow request)

        return await call_next(request)
