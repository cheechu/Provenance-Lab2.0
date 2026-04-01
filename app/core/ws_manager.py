"""
CasAI Provenance Lab — WebSocket Connection Manager
Manages active WS connections per run_id.
Supports: send to one run, broadcast to all, graceful disconnect.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from app.models.ws_events import RunEvent, RunEventType

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Thread-safe registry of WebSocket connections keyed by run_id.
    Multiple clients can subscribe to the same run (e.g. team members).
    """

    def __init__(self):
        # run_id → list of active WebSocket connections
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def connect(self, run_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[run_id].append(ws)
        logger.info("WS connected: run=%s total_for_run=%d", run_id, len(self._connections[run_id]))

    async def disconnect(self, run_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(run_id, [])
            if ws in conns:
                conns.remove(ws)
            if not conns:
                self._connections.pop(run_id, None)
        logger.info("WS disconnected: run=%s", run_id)

    async def send(self, run_id: str, event: RunEvent) -> None:
        """Send an event to all subscribers of run_id. Dead connections are pruned."""
        conns = list(self._connections.get(run_id, []))
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(event.to_json())
            except Exception:
                dead.append(ws)
        # Prune dead connections
        if dead:
            async with self._lock:
                for ws in dead:
                    try:
                        self._connections[run_id].remove(ws)
                    except ValueError:
                        pass

    async def broadcast(self, event: RunEvent) -> None:
        """Send to ALL connected clients across all runs."""
        for run_id in list(self._connections.keys()):
            await self.send(run_id, event)

    def subscriber_count(self, run_id: str) -> int:
        return len(self._connections.get(run_id, []))

    def active_runs(self) -> list[str]:
        return list(self._connections.keys())

    @property
    def total_connections(self) -> int:
        return sum(len(v) for v in self._connections.values())


# Singleton — imported by routers and streaming service
manager = ConnectionManager()
