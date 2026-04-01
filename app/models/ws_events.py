"""
CasAI Provenance Lab — WebSocket Event Schemas
All message types sent over the WS run-streaming connection.

Protocol:
  Client connects: WS /ws/runs/{run_id}?token=<jwt_or_api_key>
  Server streams:  sequence of RunEvent JSON objects
  Server closes:   on COMPLETED or FAILED event

Event flow:
  CONNECTED → QUEUED → STEP_START (×N) → STEP_COMPLETE (×N)
    → SCORE_RESULT → BYSTANDER_RESULT → EXPLAIN_RESULT
      → MANIFEST_READY → COMPLETED   (happy path)
                       → FAILED      (error path)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class RunEventType(str, Enum):
    # Lifecycle
    CONNECTED      = "connected"       # WS handshake OK
    QUEUED         = "queued"          # run accepted, waiting for worker
    STARTED        = "started"         # pipeline begins
    # Per-step
    STEP_START     = "step_start"      # individual pipeline step begins
    STEP_COMPLETE  = "step_complete"   # individual pipeline step done
    STEP_LOG       = "step_log"        # stdout/stderr line from step
    # Partial results (streamed as they arrive)
    SCORE_RESULT   = "score_result"    # one AlgorithmScore ready
    BYSTANDER_RESULT = "bystander_result"  # bystander edit predictions ready
    EXPLAIN_RESULT = "explain_result"  # SHAP explanations ready
    MANIFEST_READY = "manifest_ready"  # full RunManifest available
    # Terminal
    COMPLETED      = "completed"       # run finished successfully
    FAILED         = "failed"          # run failed
    # Control
    HEARTBEAT      = "heartbeat"       # keepalive ping every 5s
    CANCELLED      = "cancelled"       # client requested cancellation


# ---------------------------------------------------------------------------
# Step definitions (matches scoring_engine pipeline)
# ---------------------------------------------------------------------------

class PipelineStep(str, Enum):
    VALIDATE      = "validate"
    SCORING       = "scoring"
    BYSTANDER     = "bystander_analysis"
    INTERPRETABILITY = "interpretability"
    PROVENANCE    = "provenance"
    EXPORT        = "export"


STEP_LABELS: dict[PipelineStep, str] = {
    PipelineStep.VALIDATE:          "Validating guide RNA inputs",
    PipelineStep.SCORING:           "Running scoring algorithms",
    PipelineStep.BYSTANDER:         "Predicting bystander edits",
    PipelineStep.INTERPRETABILITY:  "Computing SHAP explanations",
    PipelineStep.PROVENANCE:        "Sealing provenance manifest",
    PipelineStep.EXPORT:            "Generating export artifacts",
}

STEP_ORDER = list(PipelineStep)
STEP_WEIGHTS = {
    PipelineStep.VALIDATE:         5,
    PipelineStep.SCORING:          50,
    PipelineStep.BYSTANDER:        15,
    PipelineStep.INTERPRETABILITY: 15,
    PipelineStep.PROVENANCE:       10,
    PipelineStep.EXPORT:           5,
}


def progress_at_step(step: PipelineStep, complete: bool = False) -> int:
    """Returns 0–100 progress percentage."""
    idx = STEP_ORDER.index(step)
    base = sum(STEP_WEIGHTS[STEP_ORDER[i]] for i in range(idx))
    return base + (STEP_WEIGHTS[step] if complete else 0)


# ---------------------------------------------------------------------------
# Base event
# ---------------------------------------------------------------------------

class RunEvent(BaseModel):
    event: RunEventType
    run_id: str
    ts: datetime = Field(default_factory=_now)
    progress: int = Field(default=0, ge=0, le=100)   # 0–100
    payload: Optional[dict[str, Any]] = None

    def to_json(self) -> str:
        return self.model_dump_json()


# ---------------------------------------------------------------------------
# Typed event constructors (factory functions for clean call sites)
# ---------------------------------------------------------------------------

def ev_connected(run_id: str, queue_position: int = 0) -> RunEvent:
    return RunEvent(
        event=RunEventType.CONNECTED,
        run_id=run_id,
        progress=0,
        payload={"message": "WebSocket connection established", "queue_position": queue_position},
    )


def ev_queued(run_id: str, position: int) -> RunEvent:
    return RunEvent(
        event=RunEventType.QUEUED,
        run_id=run_id,
        progress=0,
        payload={"queue_position": position, "message": f"Run queued at position {position}"},
    )


def ev_started(run_id: str, total_steps: int) -> RunEvent:
    return RunEvent(
        event=RunEventType.STARTED,
        run_id=run_id,
        progress=2,
        payload={"total_steps": total_steps, "message": "Pipeline started"},
    )


def ev_step_start(run_id: str, step: PipelineStep, step_num: int) -> RunEvent:
    return RunEvent(
        event=RunEventType.STEP_START,
        run_id=run_id,
        progress=progress_at_step(step, complete=False),
        payload={
            "step": step.value,
            "step_num": step_num,
            "total_steps": len(STEP_ORDER),
            "label": STEP_LABELS[step],
        },
    )


def ev_step_complete(run_id: str, step: PipelineStep, step_num: int, duration_ms: int) -> RunEvent:
    return RunEvent(
        event=RunEventType.STEP_COMPLETE,
        run_id=run_id,
        progress=progress_at_step(step, complete=True),
        payload={
            "step": step.value,
            "step_num": step_num,
            "label": STEP_LABELS[step],
            "duration_ms": duration_ms,
        },
    )


def ev_step_log(run_id: str, step: PipelineStep, line: str, stream: str = "stdout") -> RunEvent:
    return RunEvent(
        event=RunEventType.STEP_LOG,
        run_id=run_id,
        progress=progress_at_step(step, complete=False),
        payload={"step": step.value, "stream": stream, "line": line},
    )


def ev_score_result(run_id: str, algorithm: str, score: dict) -> RunEvent:
    return RunEvent(
        event=RunEventType.SCORE_RESULT,
        run_id=run_id,
        progress=progress_at_step(PipelineStep.SCORING, complete=False) + 10,
        payload={"algorithm": algorithm, "score": score},
    )


def ev_bystander_result(run_id: str, bystanders: list[dict]) -> RunEvent:
    return RunEvent(
        event=RunEventType.BYSTANDER_RESULT,
        run_id=run_id,
        progress=progress_at_step(PipelineStep.BYSTANDER, complete=True),
        payload={"bystander_edits": bystanders, "count": len(bystanders)},
    )


def ev_explain_result(run_id: str, explanations: list[dict]) -> RunEvent:
    return RunEvent(
        event=RunEventType.EXPLAIN_RESULT,
        run_id=run_id,
        progress=progress_at_step(PipelineStep.INTERPRETABILITY, complete=True),
        payload={"explanations": explanations},
    )


def ev_manifest_ready(run_id: str, inputs_digest: str, duration_ms: int) -> RunEvent:
    return RunEvent(
        event=RunEventType.MANIFEST_READY,
        run_id=run_id,
        progress=95,
        payload={
            "inputs_digest": inputs_digest,
            "duration_ms": duration_ms,
            "export_url": f"/runs/{run_id}/export.zip",
            "manifest_url": f"/runs/{run_id}/manifest",
        },
    )


def ev_completed(run_id: str, on_target_mean: float, off_target_mean: float, duration_ms: int) -> RunEvent:
    return RunEvent(
        event=RunEventType.COMPLETED,
        run_id=run_id,
        progress=100,
        payload={
            "on_target_mean": on_target_mean,
            "off_target_mean": off_target_mean,
            "duration_ms": duration_ms,
            "message": "Run completed successfully",
        },
    )


def ev_failed(run_id: str, error: str, step: Optional[str] = None) -> RunEvent:
    return RunEvent(
        event=RunEventType.FAILED,
        run_id=run_id,
        progress=0,
        payload={"error": error, "step": step, "message": "Run failed"},
    )


def ev_heartbeat(run_id: str, progress: int) -> RunEvent:
    return RunEvent(
        event=RunEventType.HEARTBEAT,
        run_id=run_id,
        progress=progress,
        payload={"alive": True},
    )
