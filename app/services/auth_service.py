"""
CasAI Provenance Lab — Auth Service
Handles: password hashing (bcrypt), JWT access/refresh tokens,
         API key generation/validation, and scope enforcement.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.auth_schemas import JWTPayload
from app.models.db_models import APIKey, RefreshToken, User


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """Return bcrypt hash of plain-text password."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(settings.API_KEY_HASH_ROUNDS)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def create_access_token(user: User, extra_scopes: list[str] | None = None) -> tuple[str, int]:
    """Return (encoded_jwt, expires_in_seconds)."""
    exp_seconds = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    payload = {
        "sub": user.id,
        "email": user.email,
        "scopes": extra_scopes or ["read:runs", "write:runs"],
        "token_type": "access",
        "iat": _now_ts(),
        "exp": _now_ts() + exp_seconds,
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, exp_seconds


def create_refresh_token_value() -> str:
    """Generate a cryptographically secure refresh token string."""
    return secrets.token_urlsafe(48)


def _hash_token(value: str) -> str:
    """SHA-256 hash of a token value for safe storage."""
    return hashlib.sha256(value.encode()).hexdigest()


async def save_refresh_token(
    db: AsyncSession,
    user_id: str,
    token_value: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> RefreshToken:
    rt = RefreshToken(
        user_id=user_id,
        token_hash=_hash_token(token_value),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(rt)
    await db.flush()
    return rt


async def rotate_refresh_token(
    db: AsyncSession,
    old_token_value: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[User, str] | None:
    """
    Validate + revoke old refresh token, issue a new one.
    Returns (user, new_token_value) or None if invalid/expired.
    """
    token_hash = _hash_token(old_token_value)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,  # noqa
        )
    )
    rt = result.scalar_one_or_none()
    if not rt:
        return None
    if rt.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return None

    # Revoke old token (rotation — one use only)
    rt.revoked = True
    await db.flush()

    # Load user
    user = await db.get(User, rt.user_id)
    if not user or not user.is_active:
        return None

    # Issue new token
    new_value = create_refresh_token_value()
    await save_refresh_token(db, user.id, new_value, user_agent, ip_address)
    return user, new_value


def decode_access_token(token: str) -> JWTPayload | None:
    """Decode and validate a JWT access token. Returns None on failure."""
    try:
        raw = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if raw.get("token_type") != "access":
            return None
        return JWTPayload(**raw)
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# API key generation + validation
# ---------------------------------------------------------------------------

def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.
    Returns (raw_key, key_prefix, key_hash).
    raw_key = "casai_" + 64 hex chars (32 random bytes)
    key_prefix = first 12 chars of raw_key (for DB lookup)
    key_hash = bcrypt hash of raw_key
    """
    entropy = secrets.token_hex(settings.API_KEY_LENGTH)
    raw = f"{settings.API_KEY_PREFIX}{entropy}"
    prefix = raw[:12]
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt(settings.API_KEY_HASH_ROUNDS)).decode()
    return raw, prefix, hashed


def verify_api_key(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode(), hashed.encode())
    except Exception:
        return False


async def lookup_api_key(db: AsyncSession, raw_key: str) -> APIKey | None:
    """
    Efficiently find and validate an API key.
    Uses prefix index for fast lookup, then bcrypt verify.
    """
    if not raw_key.startswith(settings.API_KEY_PREFIX):
        return None
    prefix = raw_key[:12]
    result = await db.execute(
        select(APIKey).where(
            APIKey.key_prefix == prefix,
            APIKey.is_active == True,  # noqa
        )
    )
    candidates = result.scalars().all()
    for key in candidates:
        if verify_api_key(raw_key, key.key_hash):
            # Check expiry
            if key.expires_at and key.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                return None
            return key
    return None


# ---------------------------------------------------------------------------
# User CRUD helpers
# ---------------------------------------------------------------------------

async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    return await db.get(User, user_id)


async def create_user(db: AsyncSession, email: str, password: str, full_name: str | None = None) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
    )
    db.add(user)
    await db.flush()
    return user


# ---------------------------------------------------------------------------
# Scope enforcement
# ---------------------------------------------------------------------------

SCOPE_HIERARCHY: dict[str, int] = {
    "read:runs":      1,
    "write:runs":     2,
    "read:benchmarks": 1,
    "write:benchmarks": 2,
    "admin":          99,
}

def has_scope(token_scopes: list[str], required: str) -> bool:
    """Check if the token's scopes satisfy the required scope."""
    if "admin" in token_scopes:
        return True
    return required in token_scopes
