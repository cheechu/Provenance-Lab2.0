"""
CasAI Provenance Lab — Streaming Pipeline Service
Executes the design pipeline step-by-step, emitting a RunEvent at each
stage so connected WebSocket clients see live progress.

Architecture:
  POST /runs/stream  →  creates a pending Run row  →  returns {run_id}
                     →  kicks off run_pipeline_streaming() as a background task
  WS  /ws/runs/{id}  →  client receives events as they fire
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.ws_manager import manager
from app.models.db_models import Run, User
from app.models.schemas import (
    AlgorithmScore,
    BaseEditorType,
    BystanderEditPrediction,
    EditorConfig,
    GuideRNAInput,
    RunRequest,
    RunStatus,
    RunTrack,
    ScoringAlgorithm,
)
from app.models.ws_events import (
    PipelineStep,
    ev_bystander_result,
    ev_completed,
    ev_explain_result,
    ev_failed,
    ev_heartbeat,
    ev_manifest_ready,
    ev_score_result,
    ev_started,
    ev_step_complete,
    ev_step_log,
    ev_step_start,
)
from app.services.scoring_engine import compute_shap_explanations, run_scoring

logger = logging.getLogger(__name__)


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _bystanders(guide: str, ws: int, we: int, editor: str) -> list[dict]:
    target = "C" if editor == "CBE" else "A"
    edited = "T" if editor == "CBE" else "G"
    window = guide[ws - 1 : we]
    preds = []
    for i, b in enumerate(window):
        if b == target:
            pos = ws + i
            prob = round(0.25 + i / max(len(window), 1) * 0.45, 3)
            risk = "high" if prob > 0.70 else "medium" if prob > 0.40 else "low"
            preds.append({"position_in_window": pos, "original_base": b,
                          "edited_base": edited, "probability": prob, "risk_level": risk})
    return preds


async def _emit(run_id: str, event) -> None:
    """Send event to WS subscribers. Never raises — isolated from pipeline."""
    try:
        await manager.send(run_id, event)
    except Exception as e:
        logger.warning("WS emit failed for run %s: %s", run_id, e)


async def run_pipeline_streaming(
    run_id: str,
    run_request: RunRequest,
    db_session_factory,                    # callable → AsyncSession context manager
    user_id: Optional[str] = None,
) -> None:
    """
    Background task: full pipeline with WS event emission at each stage.
    DB session is created fresh (background tasks outlive request sessions).
    """
    t_total_start = time.monotonic()
    current_step: Optional[str] = None

    async with db_session_factory() as db:
        try:
            # ── STARTED ──────────────────────────────────────────────────
            await _emit(run_id, ev_started(run_id, total_steps=len(PipelineStep)))

            # ── Step 1: VALIDATE ─────────────────────────────────────────
            current_step = PipelineStep.VALIDATE.value
            t0 = time.monotonic()
            await _emit(run_id, ev_step_start(run_id, PipelineStep.VALIDATE, 1))
            await _emit(run_id, ev_step_log(run_id, PipelineStep.VALIDATE,
                f"guide={run_request.guide_rna.sequence} pam={run_request.guide_rna.pam} gene={run_request.guide_rna.target_gene}"))
            await asyncio.sleep(0.01)  # yield event loop
            dur = int((time.monotonic() - t0) * 1000)
            await _emit(run_id, ev_step_complete(run_id, PipelineStep.VALIDATE, 1, dur))

            # ── Step 2: SCORING (concurrent per-algorithm) ───────────────
            current_step = PipelineStep.SCORING.value
            t0 = time.monotonic()
            await _emit(run_id, ev_step_start(run_id, PipelineStep.SCORING, 2))
            guide = run_request.guide_rna
            editor = run_request.editor_config
            await _emit(run_id, ev_step_log(run_id, PipelineStep.SCORING,
                f"algorithms={[a.value for a in editor.algorithms]} seed={run_request.random_seed}"))

            # Score each algorithm, emit result as it arrives
            scores: list[AlgorithmScore] = []
            tasks = {
                algo: asyncio.create_task(
                    run_scoring(guide.sequence, guide.pam, [algo], run_request.random_seed)
                )
                for algo in editor.algorithms
            }
            for algo, task in tasks.items():
                result = await task
                score = result[0]
                scores.append(score)
                await _emit(run_id, ev_score_result(run_id, algo.value, score.model_dump()))
                await _emit(run_id, ev_step_log(run_id, PipelineStep.SCORING,
                    f"{algo.value}: on={score.on_target_score:.4f} off={score.off_target_risk:.4f} SE={score.standard_error:.4f}"))

            dur = int((time.monotonic() - t0) * 1000)
            await _emit(run_id, ev_step_complete(run_id, PipelineStep.SCORING, 2, dur))

            # ── Step 3: BYSTANDER ANALYSIS ───────────────────────────────
            current_step = PipelineStep.BYSTANDER.value
            t0 = time.monotonic()
            await _emit(run_id, ev_step_start(run_id, PipelineStep.BYSTANDER, 3))
            await _emit(run_id, ev_step_log(run_id, PipelineStep.BYSTANDER,
                f"window={editor.editing_window_start}-{editor.editing_window_end} editor={editor.editor_type.value}"))
            bystanders = _bystanders(
                guide.sequence, editor.editing_window_start,
                editor.editing_window_end, editor.editor_type.value,
            )
            await _emit(run_id, ev_bystander_result(run_id, bystanders))
            dur = int((time.monotonic() - t0) * 1000)
            await _emit(run_id, ev_step_complete(run_id, PipelineStep.BYSTANDER, 3, dur))

            # ── Step 4: INTERPRETABILITY (SHAP) ─────────────────────────
            current_step = PipelineStep.INTERPRETABILITY.value
            t0 = time.monotonic()
            await _emit(run_id, ev_step_start(run_id, PipelineStep.INTERPRETABILITY, 4))
            loop = asyncio.get_event_loop()
            explanations = await loop.run_in_executor(
                None, compute_shap_explanations, guide.sequence, scores
            )
            expl_dicts = [e.model_dump() for e in explanations]
            await _emit(run_id, ev_explain_result(run_id, expl_dicts))
            dur = int((time.monotonic() - t0) * 1000)
            await _emit(run_id, ev_step_complete(run_id, PipelineStep.INTERPRETABILITY, 4, dur))

            # ── Step 5: PROVENANCE ───────────────────────────────────────
            current_step = PipelineStep.PROVENANCE.value
            t0 = time.monotonic()
            await _emit(run_id, ev_step_start(run_id, PipelineStep.PROVENANCE, 5))

            inputs_digest = _sha256(
                json.dumps(run_request.model_dump(), sort_keys=True, default=str)
            )
            total_ms = int((time.monotonic() - t_total_start) * 1000)

            on_mean = round(sum(s.on_target_score for s in scores) / max(len(scores), 1), 4)
            off_mean = round(sum(s.off_target_risk for s in scores) / max(len(scores), 1), 4)
            cfd = next((s for s in scores if s.algorithm == ScoringAlgorithm.CFD), None)
            mit = next((s for s in scores if s.algorithm == ScoringAlgorithm.MIT), None)

            # Persist to DB
            finished_at = datetime.now(timezone.utc)
            run_row = await db.get(Run, run_id)
            if run_row:
                run_row.status = "completed"
                run_row.finished_at = finished_at
                run_row.duration_ms = total_ms
                run_row.inputs_digest = inputs_digest
                run_row.scores_json = json.dumps([s.model_dump() for s in scores], default=str)
                run_row.bystanders_json = json.dumps(bystanders, default=str)
                run_row.explanations_json = json.dumps(expl_dicts, default=str)
                run_row.cfd_on_target = cfd.on_target_score if cfd else None
                run_row.cfd_off_target = cfd.off_target_risk if cfd else None
                run_row.mit_on_target = mit.on_target_score if mit else None
                run_row.mit_off_target = mit.off_target_risk if mit else None
                run_row.on_target_mean = on_mean
                run_row.off_target_mean = off_mean
                await db.commit()

            dur = int((time.monotonic() - t0) * 1000)
            await _emit(run_id, ev_step_complete(run_id, PipelineStep.PROVENANCE, 5, dur))
            await _emit(run_id, ev_manifest_ready(run_id, inputs_digest, total_ms))

            # ── Step 6: EXPORT ───────────────────────────────────────────
            current_step = PipelineStep.EXPORT.value
            t0 = time.monotonic()
            await _emit(run_id, ev_step_start(run_id, PipelineStep.EXPORT, 6))
            await _emit(run_id, ev_step_log(run_id, PipelineStep.EXPORT, "Bundling ZIP export pack"))
            await asyncio.sleep(0.005)  # simulate zip build
            dur = int((time.monotonic() - t0) * 1000)
            await _emit(run_id, ev_step_complete(run_id, PipelineStep.EXPORT, 6, dur))

            # ── COMPLETED ────────────────────────────────────────────────
            await _emit(run_id, ev_completed(run_id, on_mean, off_mean, total_ms))
            logger.info("Run %s completed in %dms on=%s off=%s", run_id, total_ms, on_mean, off_mean)

        except asyncio.CancelledError:
            logger.info("Run %s cancelled", run_id)
            await _emit(run_id, ev_failed(run_id, "Run was cancelled", current_step))
            async with db_session_factory() as db2:
                row = await db2.get(Run, run_id)
                if row:
                    row.status = "cancelled"
                    await db2.commit()

        except Exception as exc:
            logger.exception("Run %s failed at step %s: %s", run_id, current_step, exc)
            await _emit(run_id, ev_failed(run_id, str(exc), current_step))
            async with db_session_factory() as db2:
                row = await db2.get(Run, run_id)
                if row:
                    row.status = "failed"
                    await db2.commit()


async def heartbeat_loop(run_id: str, progress_ref: list[int], stop_event: asyncio.Event) -> None:
    """
    Sends a heartbeat every 5 seconds while the run is active.
    progress_ref is a mutable single-element list so the pipeline can update it.
    """
    while not stop_event.is_set():
        await asyncio.sleep(5)
        if stop_event.is_set():
            break
        await _emit(run_id, ev_heartbeat(run_id, progress_ref[0]))
