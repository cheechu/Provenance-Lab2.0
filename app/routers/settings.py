"""
CasAI Provenance Lab — Settings & Admin Router
GET  /settings/me          — user preferences
PUT  /settings/me          — update preferences
GET  /admin/users          — list all users (superuser)
GET  /admin/stats          — system stats (superuser)
GET  /notifications        — list notifications
POST /notifications/read   — mark all read
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_scope, require_superuser
from app.models.db_models import Run, User
from app.models.auth_schemas import UserOut
from app.services.notifications import (
    NotificationOut, get_notifications, mark_all_read, mark_read
)

settings_router = APIRouter(tags=["Settings & Admin"])


# ---------------------------------------------------------------------------
# User preferences (stored in memory for now — extend to DB column)
# ---------------------------------------------------------------------------

_prefs: dict[str, dict] = {}


class UserPreferences(BaseModel):
    default_track: str = "genomics_research"
    default_editor: str = "CBE"
    default_algorithms: list[str] = ["CFD", "MIT"]
    notify_on_completion: bool = True
    notify_on_failure: bool = True
    notify_high_off_target: bool = True
    off_target_threshold: float = 0.40
    on_target_threshold: float = 0.60
    theme: str = "dark"
    ws_auto_connect: bool = True


@settings_router.get("/settings/me", response_model=UserPreferences)
async def get_preferences(user: User = Depends(require_scope("read:runs"))) -> UserPreferences:
    return UserPreferences(**_prefs.get(user.id, {}))


@settings_router.put("/settings/me", response_model=UserPreferences)
async def update_preferences(
    prefs: UserPreferences,
    user: User = Depends(require_scope("write:runs")),
) -> UserPreferences:
    _prefs[user.id] = prefs.model_dump()
    return prefs


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@settings_router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    unread_only: bool = False,
    user: User = Depends(require_scope("read:runs")),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await get_notifications(db, user.id, unread_only)


@settings_router.post("/notifications/{notif_id}/read", status_code=204)
async def read_notification(
    notif_id: str,
    user: User = Depends(require_scope("read:runs")),
    db: AsyncSession = Depends(get_db),
) -> None:
    await mark_read(db, user.id, notif_id)
    await db.commit()


@settings_router.post("/notifications/read-all", status_code=204)
async def read_all_notifications(
    user: User = Depends(require_scope("read:runs")),
    db: AsyncSession = Depends(get_db),
) -> None:
    await mark_all_read(db, user.id)
    await db.commit()


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

class SystemStats(BaseModel):
    total_users: int
    total_runs: int
    completed_runs: int
    failed_runs: int
    benchmark_runs: int
    avg_on_target_mean: Optional[float]
    active_ws_connections: int
    uptime_seconds: float
    db_url_masked: str
    model_version: str
    git_sha: str

_startup_time = datetime.now(timezone.utc)


@settings_router.get("/admin/stats", response_model=SystemStats)
async def admin_stats(
    _: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> SystemStats:
    from app.core.config import settings as cfg
    from app.core.ws_manager import manager

    total_users = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    total_runs = (await db.execute(select(func.count()).select_from(Run))).scalar() or 0
    completed = (await db.execute(select(func.count()).select_from(Run).where(Run.status == "completed"))).scalar() or 0
    failed = (await db.execute(select(func.count()).select_from(Run).where(Run.status == "failed"))).scalar() or 0
    benchmarks = (await db.execute(select(func.count()).select_from(Run).where(Run.benchmark_mode == True))).scalar() or 0  # noqa
    avg_on = (await db.execute(select(func.avg(Run.on_target_mean)).where(Run.status == "completed"))).scalar()

    uptime = (datetime.now(timezone.utc) - _startup_time).total_seconds()
    db_masked = cfg.DATABASE_URL.split("@")[-1] if "@" in cfg.DATABASE_URL else cfg.DATABASE_URL.split("///")[-1]

    return SystemStats(
        total_users=total_users, total_runs=total_runs,
        completed_runs=completed, failed_runs=failed, benchmark_runs=benchmarks,
        avg_on_target_mean=round(avg_on, 4) if avg_on else None,
        active_ws_connections=manager.total_connections,
        uptime_seconds=round(uptime, 1),
        db_url_masked=db_masked,
        model_version=cfg.APP_VERSION,
        git_sha=cfg.GIT_SHA,
    )


@settings_router.get("/admin/users", response_model=list[UserOut])
async def admin_list_users(
    _: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()
