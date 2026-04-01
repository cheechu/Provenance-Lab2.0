"""
CasAI Provenance Lab — Auth Dependencies
FastAPI dependency injection for authentication and authorization.

Usage in routes:
    @router.get("/runs")
    async def list_runs(user = Depends(require_user)):  ...

    @router.post("/runs")
    async def create_run(user = Depends(require_scope("write:runs"))):  ...
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.db_models import APIKey, User
from app.services import auth_service as svc

# ---------------------------------------------------------------------------
# Security schemes (OpenAPI)
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# ---------------------------------------------------------------------------
# In-memory rate limit store (per API key id, requests per minute)
# Production: replace with Redis sorted sets
# ---------------------------------------------------------------------------

from collections import defaultdict, deque
import time

_rate_buckets: dict[str, deque] = defaultdict(deque)
_WINDOW = 60  # seconds


def _check_rate_limit(key_id: str, limit: int) -> bool:
    """Returns True if request is within limit, False if throttled."""
    now = time.monotonic()
    bucket = _rate_buckets[key_id]
    # Evict timestamps older than window
    while bucket and bucket[0] < now - _WINDOW:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


# ---------------------------------------------------------------------------
# Core: resolve principal (User) from JWT or API key
# ---------------------------------------------------------------------------

async def _get_current_principal(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
    api_key_value: Optional[str] = Security(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, list[str]]:
    """
    Resolves the caller to (User, scopes).
    Tries JWT Bearer first, then X-API-Key header.
    Raises 401 if neither is valid.
    """
    # ── JWT path ──
    if credentials and credentials.credentials:
        payload = svc.decode_access_token(credentials.credentials)
        if payload:
            user = await svc.get_user_by_id(db, payload.sub)
            if user and user.is_active:
                return user, payload.scopes
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── API key path ──
    if api_key_value:
        api_key: Optional[APIKey] = await svc.lookup_api_key(db, api_key_value)
        if api_key:
            from app.core.config import settings
            if not _check_rate_limit(api_key.id, settings.RATE_LIMIT_DEFAULT):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded — max 60 requests/minute per key",
                    headers={"Retry-After": "60"},
                )
            # Update last_used_at and request_count (fire and forget)
            api_key.last_used_at = datetime.now(timezone.utc)
            api_key.request_count += 1
            await db.flush()

            user = await svc.get_user_by_id(db, api_key.user_id)
            if user and user.is_active:
                return user, api_key.scopes.split()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required — provide Bearer token or X-API-Key header",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ---------------------------------------------------------------------------
# Public dependencies
# ---------------------------------------------------------------------------

async def require_user(
    principal: tuple[User, list[str]] = Depends(_get_current_principal),
) -> User:
    """Dependency: returns the authenticated User (any valid auth)."""
    user, _ = principal
    return user


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
    api_key_value: Optional[str] = Security(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Dependency: returns User if authenticated, None otherwise. Never raises."""
    try:
        user, _ = await _get_current_principal(request, credentials, api_key_value, db)
        return user
    except HTTPException:
        return None


def require_scope(scope: str):
    """
    Dependency factory: enforces a specific scope.

    Usage:
        @router.post("/runs", dependencies=[Depends(require_scope("write:runs"))])
    """
    async def _inner(
        principal: tuple[User, list[str]] = Depends(_get_current_principal),
    ) -> User:
        user, scopes = principal
        if not svc.has_scope(scopes, scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Scope required: {scope}. Your token has: {scopes}",
            )
        return user
    return _inner


def require_superuser(
    principal: tuple[User, list[str]] = Depends(_get_current_principal),
) -> User:
    """Dependency: requires is_superuser=True."""
    user, _ = principal
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser required")
    return user
