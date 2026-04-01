"""
CasAI Provenance Lab — WebSocket Router
Endpoints:
  POST /runs/stream          — create a run and get back a run_id to subscribe to
  WS   /ws/runs/{run_id}     — subscribe to live events for a run
  GET  /ws/status            — list active WS connections (admin)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.dependencies import get_current_user_optional, require_scope
from app.core.ws_manager import manager
from app.models.db_models import Run, User
from app.models.schemas import RunRequest
from app.models.ws_events import RunEventType, ev_connected, ev_failed
from app.services import auth_service as auth_svc
from app.services.streaming_pipeline import run_pipeline_streaming

logger = logging.getLogger(__name__)

ws_router = APIRouter(tags=["WebSocket"])


# ---------------------------------------------------------------------------
# POST /runs/stream — initiate a streaming run
# ---------------------------------------------------------------------------

@ws_router.post(
    "/runs/stream",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Initiate a streaming design run",
    description=(
        "Creates a pending Run and immediately returns `{run_id}`. "
        "Connect to `WS /ws/runs/{run_id}` to receive live progress events. "
        "Requires `write:runs` scope."
    ),
)
async def create_streaming_run(
    run_request: RunRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_scope("write:runs")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    run_id = str(uuid4())
    now = datetime.now(timezone.utc)

    # Create a pending Run row immediately so clients can subscribe before pipeline starts
    run_row = Run(
        id=run_id,
        user_id=user.id,
        status="pending",
        track=run_request.track.value,
        started_at=now,
        git_sha="unknown",          # will be filled by pipeline
        docker_image="casai-lab:1.0.0",
        inputs_digest="pending",
        random_seed=run_request.random_seed,
        benchmark_mode=run_request.benchmark_mode,
        guide_sequence=run_request.guide_rna.sequence,
        guide_pam=run_request.guide_rna.pam,
        target_gene=run_request.guide_rna.target_gene,
        chromosome=run_request.guide_rna.chromosome,
        position_start=run_request.guide_rna.position_start,
        position_end=run_request.guide_rna.position_end,
        strand=run_request.guide_rna.strand,
        editor_type=run_request.editor_config.editor_type.value,
        cas_variant=run_request.editor_config.cas_variant,
        deaminase=run_request.editor_config.deaminase,
        editing_window_start=run_request.editor_config.editing_window_start,
        editing_window_end=run_request.editor_config.editing_window_end,
        algorithms=",".join(a.value for a in run_request.editor_config.algorithms),
    )
    db.add(run_row)
    await db.commit()

    # Launch pipeline as background task (non-blocking)
    background_tasks.add_task(
        run_pipeline_streaming,
        run_id=run_id,
        run_request=run_request,
        db_session_factory=AsyncSessionLocal,
        user_id=user.id,
    )

    return {
        "run_id": run_id,
        "status": "pending",
        "ws_url": f"/ws/runs/{run_id}",
        "message": "Run initiated. Connect to ws_url to stream live events.",
    }


# ---------------------------------------------------------------------------
# WS /ws/runs/{run_id} — live event stream
# ---------------------------------------------------------------------------

@ws_router.websocket("/ws/runs/{run_id}")
async def ws_run_events(
    ws: WebSocket,
    run_id: str,
    token: Optional[str] = Query(None, description="JWT access token or raw API key"),
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket endpoint for live run event streaming.

    Auth: pass `?token=<jwt>` or `?token=casai_<key>` in the query string.
    Events are JSON objects conforming to RunEvent schema.

    The server closes the connection after a COMPLETED or FAILED event.
    """
    # ── Authenticate ──────────────────────────────────────────────────────
    user: Optional[User] = None
    if token:
        # Try JWT first
        payload = auth_svc.decode_access_token(token)
        if payload:
            user = await auth_svc.get_user_by_id(db, payload.sub)
        else:
            # Try API key
            api_key = await auth_svc.lookup_api_key(db, token)
            if api_key:
                user = await auth_svc.get_user_by_id(db, api_key.user_id)

    if not user:
        await ws.close(code=4001, reason="Unauthorized — provide ?token=<jwt_or_api_key>")
        return

    # ── Verify run exists and belongs to user ────────────────────────────
    run_row = await db.get(Run, run_id)
    if not run_row:
        await ws.close(code=4004, reason=f"Run {run_id} not found")
        return
    if run_row.user_id and run_row.user_id != user.id and not user.is_superuser:
        await ws.close(code=4003, reason="Forbidden — run belongs to another user")
        return

    # ── Connect ───────────────────────────────────────────────────────────
    await manager.connect(run_id, ws)
    logger.info("WS subscribed: user=%s run=%s", user.id, run_id)

    try:
        # Send immediate connection confirmation
        await ws.send_text(ev_connected(run_id, queue_position=0).to_json())

        # If run already completed, replay terminal event and close
        if run_row.status in ("completed", "failed", "cancelled"):
            from app.models.ws_events import RunEvent, RunEventType, ev_completed, ev_failed
            if run_row.status == "completed":
                evt = ev_completed(
                    run_id,
                    on_target_mean=run_row.on_target_mean or 0.0,
                    off_target_mean=run_row.off_target_mean or 0.0,
                    duration_ms=run_row.duration_ms or 0,
                )
            else:
                evt = ev_failed(run_id, f"Run {run_row.status}", run_row.status)
            await ws.send_text(evt.to_json())
            await ws.close(code=1000)
            return

        # Otherwise: stay open, forwarding events from manager until terminal event
        terminal_events = {RunEventType.COMPLETED, RunEventType.FAILED, RunEventType.CANCELLED}

        while True:
            # Keep connection alive; the pipeline pushes events via manager.send()
            # We just need to detect client disconnect or terminal state
            try:
                # ping/pong — if client disconnects this raises
                data = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                # Handle client cancellation request
                if data == '{"action":"cancel"}':
                    logger.info("Client requested cancel for run %s", run_id)
                    row = await db.get(Run, run_id)
                    if row and row.status == "pending":
                        row.status = "cancelled"
                        await db.commit()
                    break
            except asyncio.TimeoutError:
                # Timeout is fine — just keep the loop alive
                # Check if run finished
                await db.refresh(run_row)
                if run_row.status in ("completed", "failed", "cancelled"):
                    break
            except WebSocketDisconnect:
                logger.info("WS client disconnected: run=%s", run_id)
                break

    finally:
        await manager.disconnect(run_id, ws)


# ---------------------------------------------------------------------------
# GET /ws/status — active connections (admin/debug)
# ---------------------------------------------------------------------------

@ws_router.get(
    "/ws/status",
    summary="Active WebSocket connections (admin)",
    dependencies=[Depends(require_scope("admin"))],
)
def ws_status() -> dict:
    return {
        "total_connections": manager.total_connections,
        "active_runs": manager.active_runs(),
        "per_run": {
            run_id: manager.subscriber_count(run_id)
            for run_id in manager.active_runs()
        },
    }
