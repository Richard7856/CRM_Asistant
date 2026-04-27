"""
Middleware stack for CRM Agents.
Order matters — outermost middleware runs first. Registration in main.py:
  1. CORS (outermost)
  2. SecurityHeaders
  3. RateLimit
  4. RequestTiming (innermost)
"""

import logging
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings

logger = logging.getLogger(__name__)


# ─── Request Timing ───


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Log request duration and add X-Process-Time-Ms header."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s - %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"
        return response


# ─── Rate Limiting ───


# Module-level state — exposed for tests and future admin reset endpoints.
# The middleware instance is constructed once per app boot; keeping state at module
# level means we can reset between tests without grabbing the middleware instance
# out of Starlette's middleware stack.
_RATE_LIMIT_BUCKETS: dict[str, list[float]] = defaultdict(list)


def reset_rate_limit_state() -> None:
    """Clear all rate limit buckets. Used by tests; safe to call from admin tools."""
    _RATE_LIMIT_BUCKETS.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    In-memory sliding window rate limiter for auth endpoints.
    Tracks request timestamps per IP:path and rejects with 429 when exceeded.

    Why in-memory and not Redis: single-process uvicorn in MVP.
    State resets on restart — acceptable, no persistent penalty.
    Redis migration planned for Phase 7.
    """

    # (max_requests, window_seconds) per path
    RATE_LIMITS: dict[str, tuple[int, int]] = {
        "/api/v1/auth/login": (5, 60),
        "/api/v1/auth/register": (3, 60),
        "/api/v1/auth/refresh": (10, 60),
    }

    def __init__(self, app):
        super().__init__(app)
        # Reference the module-level buckets so tests/admin can reset them
        self._buckets = _RATE_LIMIT_BUCKETS
        self._request_count = 0

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP — supports reverse proxy via X-Forwarded-For."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup_stale_buckets(self) -> None:
        """Purge empty buckets every 1000 requests to prevent unbounded memory growth."""
        self._request_count += 1
        if self._request_count % 1000 == 0:
            stale = [k for k, v in self._buckets.items() if not v]
            for k in stale:
                del self._buckets[k]

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        limit_config = self.RATE_LIMITS.get(path)

        if limit_config is None or request.method == "OPTIONS":
            return await call_next(request)

        max_requests, window_seconds = limit_config
        client_ip = self._get_client_ip(request)
        key = f"{client_ip}:{path}"
        now = time.time()
        cutoff = now - window_seconds

        # Slide the window — remove expired timestamps
        bucket = self._buckets[key]
        self._buckets[key] = [ts for ts in bucket if ts > cutoff]
        bucket = self._buckets[key]

        remaining = max_requests - len(bucket)

        if remaining <= 0:
            # Calculate when the oldest request in the window expires
            retry_after = int(bucket[0] + window_seconds - now) + 1
            logger.warning(
                "Rate limit exceeded: %s on %s (%d/%d in %ds)",
                client_ip, path, len(bucket), max_requests, window_seconds,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Demasiadas solicitudes. Intenta de nuevo en {retry_after} segundos."
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )

        # Record this request
        bucket.append(now)
        self._cleanup_stale_buckets()

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining - 1)
        return response


# ─── Security Headers ───


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to every response.
    HSTS only added in non-debug mode to avoid breaking local dev with HTTP.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response
