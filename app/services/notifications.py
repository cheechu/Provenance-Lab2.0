"""
CasAI Provenance Lab — Notification Service
In-app notification system with severity levels, run event hooks,
and score threshold alerts. Persists to DB; streams via WS.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(10), nullable=False, default="info")   # info | success | warning | error
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    action_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class NotificationOut(BaseModel):
    id: str
    level: str
    title: str
    body: str
    run_id: Optional[str]
    read: bool
    created_at: datetime
    action_url: Optional[str]
    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Factory helpers — called by pipeline at key moments
# ---------------------------------------------------------------------------

def notif_run_completed(user_id: str, run_id: str, gene: str, on_target: float) -> dict:
    level = "success" if on_target >= 0.75 else "warning" if on_target >= 0.60 else "error"
    return dict(
        user_id=user_id, run_id=run_id, level=level,
        title=f"Run completed · {gene}",
        body=f"On-target efficiency: {on_target:.4f}. {'Above threshold — ready for export.' if on_target >= 0.75 else 'Below threshold — review scores before proceeding.'}",
        action_url=f"/runs/{run_id}",
    )


def notif_run_failed(user_id: str, run_id: str, gene: str, error: str) -> dict:
    return dict(
        user_id=user_id, run_id=run_id, level="error",
        title=f"Run failed · {gene}",
        body=f"Pipeline error: {error[:120]}",
        action_url=f"/runs/{run_id}",
    )


def notif_benchmark_top(user_id: str, run_id: str, gene: str, percentile: float) -> dict:
    return dict(
        user_id=user_id, run_id=run_id, level="success",
        title=f"Top {100 - percentile:.0f}% benchmark · {gene}",
        body=f"Your design ranked in the {percentile:.0f}th percentile for on-target specificity.",
        action_url="/benchmarks/leaderboard",
    )


def notif_export_ready(user_id: str, run_id: str, gene: str) -> dict:
    return dict(
        user_id=user_id, run_id=run_id, level="info",
        title=f"Export pack ready · {gene}",
        body="ZIP export pack is ready. Contains cloning oligos, primers, provenance passport, and FASTA.",
        action_url=f"/runs/{run_id}/export.zip",
    )


def notif_high_off_target(user_id: str, run_id: str, gene: str, risk: float) -> dict:
    return dict(
        user_id=user_id, run_id=run_id, level="warning",
        title=f"High off-target risk · {gene}",
        body=f"Off-target risk score {risk:.4f} exceeds threshold (0.40). Consider redesigning the guide RNA.",
        action_url=f"/runs/{run_id}",
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update


async def create_notification(db: AsyncSession, **kwargs) -> Notification:
    n = Notification(**kwargs)
    db.add(n)
    await db.flush()
    # Push to WS subscribers
    from app.core.ws_manager import manager
    from app.models.ws_events import RunEvent, RunEventType
    import json
    event = RunEvent(
        event=RunEventType.HEARTBEAT,
        run_id=kwargs.get("run_id", "system"),
        payload={"notification": NotificationOut.model_validate(n).model_dump(default=str)},
    )
    try:
        await manager.broadcast(event)
    except Exception:
        pass
    return n


async def get_notifications(db: AsyncSession, user_id: str, unread_only: bool = False) -> list[Notification]:
    q = select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc()).limit(50)
    if unread_only:
        q = q.where(Notification.read == False)  # noqa
    result = await db.execute(q)
    return result.scalars().all()


async def mark_read(db: AsyncSession, user_id: str, notif_id: str) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.id == notif_id, Notification.user_id == user_id)
        .values(read=True)
    )


async def mark_all_read(db: AsyncSession, user_id: str) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read == False)  # noqa
        .values(read=True)
    )
