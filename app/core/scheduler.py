"""
CasAI Provenance Lab — Background Task Scheduler
Periodic async tasks that run while the server is live:
  - Purge expired refresh tokens (every 1h)
  - Mark stale pending runs as failed (every 5m)
  - Snapshot benchmark stats for regression charts (every 24h)
  - Clean up old export zips (every 6h)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, update, select

from app.core.database import AsyncSessionLocal

logger = logging.getLogger("casai.scheduler")


async def purge_expired_refresh_tokens() -> int:
    """Delete revoked or expired refresh tokens older than 7 days."""
    async with AsyncSessionLocal() as db:
        from app.models.db_models import RefreshToken
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        result = await db.execute(
            delete(RefreshToken).where(
                (RefreshToken.revoked == True) |  # noqa
                (RefreshToken.expires_at < cutoff)
            )
        )
        await db.commit()
        count = result.rowcount
        if count:
            logger.info("Purged %d expired refresh tokens", count)
        return count


async def fail_stale_runs(timeout_minutes: int = 30) -> int:
    """Mark runs stuck in 'running' or 'pending' for too long as failed."""
    async with AsyncSessionLocal() as db:
        from app.models.db_models import Run
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        result = await db.execute(
            update(Run)
            .where(
                Run.status.in_(["running", "pending"]),
                Run.started_at < cutoff,
            )
            .values(status="failed", finished_at=datetime.now(timezone.utc))
        )
        await db.commit()
        count = result.rowcount
        if count:
            logger.warning("Marked %d stale runs as failed", count)
        return count


async def clean_old_exports(max_age_hours: int = 24) -> int:
    """Remove export ZIP files older than max_age_hours from disk."""
    from app.core.config import settings
    exports_dir = Path(settings.EXPORTS_DIR)
    if not exports_dir.exists():
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
    removed = 0
    for f in exports_dir.glob("*.zip"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            pass
    if removed:
        logger.info("Cleaned %d old export ZIPs", removed)
    return removed


async def snapshot_benchmark_stats() -> None:
    """Write a daily benchmark performance snapshot for regression charts."""
    async with AsyncSessionLocal() as db:
        from app.models.db_models import Run
        from sqlalchemy import func
        import json

        result = await db.execute(
            select(
                Run.track,
                func.count(Run.id).label("count"),
                func.avg(Run.on_target_mean).label("avg_on"),
                func.avg(Run.off_target_mean).label("avg_off"),
            )
            .where(Run.status == "completed", Run.benchmark_mode == True)  # noqa
            .group_by(Run.track)
        )
        rows = result.fetchall()
        snapshot = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tracks": [
                {"track": r.track, "count": r.count,
                 "avg_on": round(r.avg_on, 4) if r.avg_on else None,
                 "avg_off": round(r.avg_off, 4) if r.avg_off else None}
                for r in rows
            ]
        }
        snap_path = Path("./data/benchmarks/daily_snapshot.json")
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        # Append to history
        history = []
        if snap_path.exists():
            try:
                history = json.loads(snap_path.read_text())
            except Exception:
                history = []
        history.append(snapshot)
        history = history[-90:]  # keep 90 days
        snap_path.write_text(json.dumps(history, indent=2))
        logger.info("Benchmark snapshot written: %s", snapshot)


# ---------------------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------------------

async def run_scheduler() -> None:
    """Main scheduler coroutine — runs as a background asyncio task."""
    logger.info("Background scheduler started")
    tick = 0

    while True:
        await asyncio.sleep(60)  # base tick: 1 minute
        tick += 1

        try:
            # Every 5 minutes: fail stale runs
            if tick % 5 == 0:
                await fail_stale_runs()

            # Every 60 minutes: purge expired tokens
            if tick % 60 == 0:
                await purge_expired_refresh_tokens()

            # Every 360 minutes (6h): clean old exports
            if tick % 360 == 0:
                await clean_old_exports()

            # Every 1440 minutes (24h): snapshot benchmarks
            if tick % 1440 == 0:
                await snapshot_benchmark_stats()

        except Exception as e:
            logger.error("Scheduler error at tick %d: %s", tick, e)
