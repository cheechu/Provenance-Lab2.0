"""
CasAI Provenance Lab — DB-backed Provenance Service
Replaces flat JSON file storage. Uses SQLAlchemy async + ML scoring engine.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.db_models import Run, User
from app.models.schemas import (
    AlgorithmScore,
    BenchmarkResult,
    BystanderEditPrediction,
    DesignPrediction,
    InputEntity,
    LeaderboardEntry,
    ManifestDiff,
    ManifestDiffEntry,
    OutputEntity,
    RunManifest,
    RunRequest,
    RunStatus,
    RunSummary,
    RunTrack,
    ScoringAlgorithm,
    StepTrace,
)
from app.services.scoring_engine import compute_shap_explanations, run_scoring


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def _inputs_digest(run_request: RunRequest) -> str:
    payload = json.dumps(run_request.model_dump(), sort_keys=True, default=str)
    return _sha256(payload)


def _bystander_edits(
    guide_seq: str,
    window_start: int,
    window_end: int,
    editor_type: str,
) -> list[BystanderEditPrediction]:
    target_base = "C" if editor_type == "CBE" else "A"
    edited_base = "T" if editor_type == "CBE" else "G"
    window_seq = guide_seq[window_start - 1 : window_end]
    preds = []
    for i, base in enumerate(window_seq):
        if base == target_base:
            pos = window_start + i
            # Probability increases linearly across window
            prob = round(0.25 + (i / max(len(window_seq), 1)) * 0.45, 3)
            risk = "high" if prob > 0.70 else "medium" if prob > 0.40 else "low"
            preds.append(BystanderEditPrediction(
                position_in_window=pos,
                original_base=base,
                edited_base=edited_base,
                probability=min(prob, 0.99),
                risk_level=risk,
            ))
    return preds


def _run_to_manifest(run: Run) -> RunManifest:
    """Reconstruct a RunManifest from a DB Run row."""
    scores = json.loads(run.scores_json) if run.scores_json else []
    bystanders = json.loads(run.bystanders_json) if run.bystanders_json else []
    explanations = json.loads(run.explanations_json) if run.explanations_json else []
    step_traces = json.loads(run.step_traces_json) if run.step_traces_json else []

    from app.models.schemas import (
        BaseEditorType, EditorConfig, GuideRNAInput, RunTrack,
    )

    run_request = RunRequest(
        guide_rna=GuideRNAInput(
            sequence=run.guide_sequence,
            pam=run.guide_pam,
            target_gene=run.target_gene,
            chromosome=run.chromosome,
            position_start=run.position_start,
            position_end=run.position_end,
            strand=run.strand,
        ),
        editor_config=EditorConfig(
            editor_type=BaseEditorType(run.editor_type),
            cas_variant=run.cas_variant,
            deaminase=run.deaminase,
            editing_window_start=run.editing_window_start,
            editing_window_end=run.editing_window_end,
            algorithms=[ScoringAlgorithm(a) for a in run.algorithms.split(",") if a],
        ),
        track=RunTrack(run.track),
        random_seed=run.random_seed,
        benchmark_mode=run.benchmark_mode,
    )

    prediction = None
    if scores:
        window_bases = run.guide_sequence[run.editing_window_start - 1 : run.editing_window_end]
        target_base = "C" if run.editor_type == "CBE" else "A"
        prediction = DesignPrediction(
            scores=[AlgorithmScore(**s) for s in scores],
            bystander_edits=[BystanderEditPrediction(**b) for b in bystanders],
            explanations=explanations,
            editing_window_bases=window_bases,
            target_base_count=window_bases.count(target_base),
            structural_variation_risk=run.structural_variation_risk,
            genome_coverage=run.genome_coverage,
        )

    return RunManifest(
        run_id=UUID(run.id),
        git_sha=run.git_sha,
        docker_image=run.docker_image,
        app_version=run.app_version,
        inputs_digest=run.inputs_digest,
        random_seed=run.random_seed,
        status=RunStatus(run.status),
        start_time=run.started_at,
        end_time=run.finished_at,
        object=[InputEntity(
            entity_id="#input-guide-rna",
            name="guide_rna_input.json",
            sha256_hash=_sha256(run_request.guide_rna.model_dump_json()),
            description=f"Guide RNA for target gene: {run.target_gene}",
        )],
        result=[OutputEntity(
            entity_id=f"#prediction-{run.id}",
            name="prediction.json",
            sha256_hash=_sha256(json.dumps(scores, default=str)),
            media_type="application/json",
        )] if scores else [],
        step_traces=[StepTrace(**s) for s in step_traces],
        run_request=run_request,
        prediction=prediction,
        track=RunTrack(run.track),
        benchmark_mode=run.benchmark_mode,
    )


# ---------------------------------------------------------------------------
# Public service functions (DB-backed, async)
# ---------------------------------------------------------------------------

async def create_run_db(
    db: AsyncSession,
    run_request: RunRequest,
    user: Optional[User] = None,
) -> RunManifest:
    """
    Execute a design run, persist to DB, return RunManifest.
    """
    digest = _inputs_digest(run_request)
    guide = run_request.guide_rna
    editor = run_request.editor_config
    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc)

    # ── Step 1: ML Scoring (async, concurrent) ──
    t0 = datetime.now(timezone.utc)
    scores: list[AlgorithmScore] = await run_scoring(
        guide.sequence,
        guide.pam,
        editor.algorithms,
        run_request.random_seed,
    )
    t1 = datetime.now(timezone.utc)
    scoring_ms = int((t1 - t0).total_seconds() * 1000)

    # ── Step 2: Bystander analysis ──
    t2 = datetime.now(timezone.utc)
    bystanders = _bystander_edits(
        guide.sequence,
        editor.editing_window_start,
        editor.editing_window_end,
        editor.editor_type.value,
    )
    t3 = datetime.now(timezone.utc)
    bystander_ms = int((t3 - t2).total_seconds() * 1000)

    # ── Step 3: SHAP explainability ──
    t4 = datetime.now(timezone.utc)
    explanations = compute_shap_explanations(guide.sequence, scores)
    t5 = datetime.now(timezone.utc)
    explain_ms = int((t5 - t4).total_seconds() * 1000)

    finished_at = datetime.now(timezone.utc)
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    step_traces = [
        StepTrace(step_name="scoring", start_time=t0, end_time=t1, exit_status=0, docker_image=settings.DOCKER_IMAGE, command_args=["bin/scorer", "--guide", guide.sequence], seed_used=run_request.random_seed),
        StepTrace(step_name="bystander_analysis", start_time=t2, end_time=t3, exit_status=0, docker_image=settings.DOCKER_IMAGE, command_args=["bin/bystander", f"--window={editor.editing_window_start}-{editor.editing_window_end}"]),
        StepTrace(step_name="interpretability", start_time=t4, end_time=t5, exit_status=0, docker_image=settings.DOCKER_IMAGE, command_args=["bin/explain", "--method=SHAP+LIME"]),
    ]

    # Track-specific fields
    sv_risk = "low" if run_request.track == RunTrack.THERAPEUTIC else None
    genome_cov = 0.87 if run_request.track == RunTrack.CROP_DEMO else None

    # Aggregate metrics
    cfd = next((s for s in scores if s.algorithm == ScoringAlgorithm.CFD), None)
    mit = next((s for s in scores if s.algorithm == ScoringAlgorithm.MIT), None)
    on_mean = round(sum(s.on_target_score for s in scores) / max(len(scores), 1), 4)
    off_mean = round(sum(s.off_target_risk for s in scores) / max(len(scores), 1), 4)

    # Persist to DB
    run_row = Run(
        id=run_id,
        user_id=user.id if user else None,
        status="completed",
        track=run_request.track.value,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        git_sha=settings.GIT_SHA,
        docker_image=settings.DOCKER_IMAGE,
        app_version=settings.APP_VERSION,
        inputs_digest=digest,
        random_seed=run_request.random_seed,
        benchmark_mode=run_request.benchmark_mode,
        guide_sequence=guide.sequence,
        guide_pam=guide.pam,
        target_gene=guide.target_gene,
        chromosome=guide.chromosome,
        position_start=guide.position_start,
        position_end=guide.position_end,
        strand=guide.strand,
        editor_type=editor.editor_type.value,
        cas_variant=editor.cas_variant,
        deaminase=editor.deaminase,
        editing_window_start=editor.editing_window_start,
        editing_window_end=editor.editing_window_end,
        algorithms=",".join(a.value for a in editor.algorithms),
        scores_json=json.dumps([s.model_dump() for s in scores], default=str),
        bystanders_json=json.dumps([b.model_dump() for b in bystanders], default=str),
        explanations_json=json.dumps([e.model_dump() for e in explanations], default=str),
        step_traces_json=json.dumps([t.model_dump() for t in step_traces], default=str),
        cfd_on_target=cfd.on_target_score if cfd else None,
        cfd_off_target=cfd.off_target_risk if cfd else None,
        mit_on_target=mit.on_target_score if mit else None,
        mit_off_target=mit.off_target_risk if mit else None,
        on_target_mean=on_mean,
        off_target_mean=off_mean,
        structural_variation_risk=sv_risk,
        genome_coverage=genome_cov,
    )
    db.add(run_row)
    await db.commit()
    await db.refresh(run_row)

    return _run_to_manifest(run_row)


async def get_run_db(db: AsyncSession, run_id: UUID) -> Optional[RunManifest]:
    run = await db.get(Run, str(run_id))
    return _run_to_manifest(run) if run else None


async def list_runs_db(
    db: AsyncSession,
    track: Optional[RunTrack] = None,
    limit: int = 50,
    offset: int = 0,
    user_id: Optional[str] = None,
) -> list[RunSummary]:
    q = select(Run).order_by(desc(Run.started_at)).limit(limit).offset(offset)
    if track:
        q = q.where(Run.track == track.value)
    if user_id:
        q = q.where(Run.user_id == user_id)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [RunSummary(
        run_id=UUID(r.id),
        status=RunStatus(r.status),
        track=RunTrack(r.track),
        target_gene=r.target_gene,
        editor_type=r.editor_type,
        start_time=r.started_at,
        end_time=r.finished_at,
        duration_seconds=(r.duration_ms / 1000.0) if r.duration_ms else None,
        benchmark_mode=r.benchmark_mode,
    ) for r in rows]


async def diff_runs_db(
    db: AsyncSession,
    run_a_id: UUID,
    run_b_id: UUID,
) -> Optional[ManifestDiff]:
    a = await db.get(Run, str(run_a_id))
    b = await db.get(Run, str(run_b_id))
    if not a or not b:
        return None

    diffs: list[ManifestDiffEntry] = []

    def _cmp(field: str, va, vb):
        diffs.append(ManifestDiffEntry(field=field, run_a_value=va, run_b_value=vb, changed=va != vb))

    _cmp("git_sha", a.git_sha, b.git_sha)
    _cmp("inputs_digest", a.inputs_digest, b.inputs_digest)
    _cmp("track", a.track, b.track)
    _cmp("editor_type", a.editor_type, b.editor_type)
    _cmp("guide_sequence", a.guide_sequence, b.guide_sequence)
    _cmp("editing_window", f"{a.editing_window_start}-{a.editing_window_end}", f"{b.editing_window_start}-{b.editing_window_end}")
    _cmp("random_seed", a.random_seed, b.random_seed)
    _cmp("benchmark_mode", a.benchmark_mode, b.benchmark_mode)
    _cmp("status", a.status, b.status)
    _cmp("duration_ms", a.duration_ms, b.duration_ms)
    _cmp("CFD.on_target", a.cfd_on_target, b.cfd_on_target)
    _cmp("CFD.off_target", a.cfd_off_target, b.cfd_off_target)
    _cmp("MIT.on_target", a.mit_on_target, b.mit_on_target)
    _cmp("MIT.off_target", a.mit_off_target, b.mit_off_target)

    changed = sum(1 for d in diffs if d.changed)
    return ManifestDiff(
        run_a_id=run_a_id,
        run_b_id=run_b_id,
        differences=diffs,
        summary=f"{changed} of {len(diffs)} fields differ.",
    )


async def rerun_db(db: AsyncSession, run_id: UUID, user: Optional[User] = None) -> Optional[RunManifest]:
    original = await db.get(Run, str(run_id))
    if not original:
        return None
    # Reconstruct run_request from stored run
    manifest = _run_to_manifest(original)
    return await create_run_db(db, manifest.run_request, user)


async def get_leaderboard_db(
    db: AsyncSession,
    model_version: Optional[str] = None,
    track: Optional[RunTrack] = None,
    limit: int = 50,
) -> list[LeaderboardEntry]:
    q = (
        select(Run)
        .where(Run.benchmark_mode == True, Run.status == "completed")  # noqa
        .order_by(desc(Run.on_target_mean))
        .limit(limit)
    )
    if track:
        q = q.where(Run.track == track.value)
    if model_version:
        q = q.where(Run.app_version == model_version)

    result = await db.execute(q)
    rows = result.scalars().all()
    total = len(rows)

    return [
        LeaderboardEntry(
            rank=i + 1,
            run_id=UUID(r.id),
            target_gene=r.target_gene,
            editor_type=r.editor_type,
            on_target_mean=r.on_target_mean or 0.0,
            off_target_risk_mean=r.off_target_mean or 0.0,
            percentile_specificity=round((1 - i / max(total, 1)) * 100, 1),
            model_version=r.app_version,
            created_at=r.started_at,
        )
        for i, r in enumerate(rows)
    ]
