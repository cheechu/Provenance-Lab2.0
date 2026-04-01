"""
CasAI Provenance Lab — Auth Router
Endpoints: register, login, refresh, logout, /me, API key management.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_user
from app.models.auth_schemas import (
    APIKeyCreate,
    APIKeyCreated,
    APIKeyOut,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.models.db_models import APIKey, User
from app.services import auth_service as svc

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

@auth_router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account",
)
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    existing = await svc.get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email already registered: {body.email}",
        )
    user = await svc.create_user(db, body.email, body.password, body.full_name)
    await db.commit()
    return user


# ---------------------------------------------------------------------------
# Login → JWT pair
# ---------------------------------------------------------------------------

@auth_router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email + password, receive JWT access + refresh tokens",
)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    user = await svc.get_user_by_email(db, body.email)
    if not user or not svc.verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    access_token, expires_in = svc.create_access_token(user)
    refresh_value = svc.create_refresh_token_value()
    await svc.save_refresh_token(
        db,
        user.id,
        refresh_value,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_value,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": user,
    }


# ---------------------------------------------------------------------------
# Refresh → new access token (+ rotated refresh token)
# ---------------------------------------------------------------------------

@auth_router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and receive a new access token",
)
async def refresh(body: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    result = await svc.rotate_refresh_token(
        db,
        body.refresh_token,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid, expired, or already used",
        )
    user, new_refresh = result
    access_token, expires_in = svc.create_access_token(user)
    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": user,
    }


# ---------------------------------------------------------------------------
# Logout — revoke all refresh tokens for this user
# ---------------------------------------------------------------------------

@auth_router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Revoke all active refresh tokens for the current user",
)
async def logout(user: User = Depends(require_user), db: AsyncSession = Depends(get_db)) -> dict:
    from sqlalchemy import update
    from app.models.db_models import RefreshToken

    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked == False)  # noqa: E712
        .values(revoked=True)
    )
    await db.commit()
    return {"message": "Logged out successfully"}


# ---------------------------------------------------------------------------
# /me — current user profile
# ---------------------------------------------------------------------------

@auth_router.get("/me", response_model=UserOut, summary="Get current user profile")
async def me(user: User = Depends(require_user)) -> User:
    return user


@auth_router.patch("/me", response_model=UserOut, summary="Update profile or password")
async def update_me(
    body: UserUpdate,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.password is not None:
        user.hashed_password = svc.hash_password(body.password)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

@auth_router.post(
    "/api-keys",
    response_model=APIKeyCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key — raw key shown only once",
)
async def create_api_key(
    body: APIKeyCreate,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    raw_key, prefix, key_hash = svc.generate_api_key()
    expires_at = None
    if body.expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_days)

    api_key = APIKey(
        user_id=user.id,
        name=body.name,
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=body.scopes,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return {
        **{c.name: getattr(api_key, c.name) for c in APIKey.__table__.columns},
        "raw_key": raw_key,
    }


@auth_router.get(
    "/api-keys",
    response_model=list[APIKeyOut],
    summary="List all API keys for the current user",
)
async def list_api_keys(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> list[APIKey]:
    result = await db.execute(
        select(APIKey)
        .where(APIKey.user_id == user.id)
        .order_by(APIKey.created_at.desc())
    )
    return result.scalars().all()


@auth_router.delete(
    "/api-keys/{key_id}",
    status_code=status.HTTP_200_OK,
    summary="Revoke (soft-delete) an API key",
)
async def revoke_api_key(
    key_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user.id)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    key.is_active = False
    await db.commit()
    return {"message": "API key revoked"}