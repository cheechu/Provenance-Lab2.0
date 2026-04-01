"""
CasAI Provenance Lab — Middleware
1. RequestLoggingMiddleware — structured JSON request/response logs
2. RateLimitMiddleware     — per-IP sliding window rate limiting (fallback for unauthenticated routes)
3. SecurityHeadersMiddleware — adds CSP, HSTS, X-Frame-Options
"""
from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import logging

logger = logging.getLogger("casai.access")


# ---------------------------------------------------------------------------
# 1. Request Logging
# ---------------------------------------------------------------------------

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())[:8]
        t0 = time.monotonic()

        response = await call_next(request)

        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.info(json.dumps({
            "request_id": request_id,
            "method": request.method,
            "path": str(request.url.path),
            "status": response.status_code,
            "duration_ms": duration_ms,
            "client": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", "")[:80],
        }))

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        return response


# ---------------------------------------------------------------------------
# 2. IP Rate Limiter (unauthenticated routes only — auth routes have stricter limits)
# ---------------------------------------------------------------------------

_ip_buckets: dict[str, deque] = defaultdict(deque)
_WINDOW_SECONDS = 60
_MAX_REQUESTS = 120   # per IP per minute (generous — auth layer does tighter per-key)

EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/playground"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = _ip_buckets[ip]

        while bucket and bucket[0] < now - _WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= _MAX_REQUESTS:
            return Response(
                content=json.dumps({"detail": "Rate limit exceeded. Max 120 requests/minute per IP."}),
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60"},
            )

        bucket.append(now)
        return await call_next(request)


# ---------------------------------------------------------------------------
# 3. Security Headers
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
