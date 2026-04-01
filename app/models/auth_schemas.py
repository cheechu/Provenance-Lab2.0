"""
CasAI Provenance Lab — Auth Schemas
Pydantic models for auth endpoints (register, login, token refresh, API keys).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Min 8 characters")
    full_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        return v


class UserOut(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    is_active: bool
    is_superuser: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8)


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int           # seconds until access token expires
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------

class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Human label for this key")
    scopes: str = Field(
        default="read:runs write:runs",
        description="Space-separated scope list",
    )
    expires_days: Optional[int] = Field(None, ge=1, le=365, description="Days until expiry; None = never expires")


class APIKeyOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: str
    is_active: bool
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime
    request_count: int

    model_config = {"from_attributes": True}


class APIKeyCreated(APIKeyOut):
    """Returned only once at creation — includes the raw key."""
    raw_key: str = Field(..., description="Store this — it will not be shown again")


# ---------------------------------------------------------------------------
# JWT payload (internal)
# ---------------------------------------------------------------------------

class JWTPayload(BaseModel):
    sub: str              # user_id
    email: str
    scopes: list[str] = []
    token_type: str = "access"   # "access" | "refresh"
    exp: Optional[int] = None
    iat: Optional[int] = None
    jti: Optional[str] = None    # JWT ID (for revocation)
