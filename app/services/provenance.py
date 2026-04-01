"""
CasAI Provenance Lab — Provenance Service
Handles run lifecycle: creation, persistence, retrieval, diff, re-run.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from app.core.config import settings
from app.models.schemas import (
    AlgorithmScore,
    APIResponse,
    BaseEditorType,
    BystanderEditPrediction,
    DesignPrediction,
    ExplainabilityEntry,
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
    BenchmarkResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def _inputs_digest(run_request: RunRequest) -> str:
    """Stable SHA-256 of the frozen run inputs."""
    payload = json.dumps(run_request.model_dump(), sort_keys=True, default=str)
    return _sha256(payload)


def _runs_path() -> Path:
    p = Path(settings.RUNS_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _benchmarks_path() -> Path:
    p = Path(settings.BENCHMARKS_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _exports_path() -> Path:
    p = Path(settings.EXPORTS_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _manifest_file(run_id: UUID) -> Path:
    return _runs_path() / f"{run_id}.json"


def _save_manifest(manifest: RunManifest) -> None:
    path = _manifest_file(manifest.run_id)
    path.write_text(manifest.model_dump_json(indent=2))


def _load_manifest(run_id: UUID) -> Optional[RunManifest]:
    path = _manifest_file(run_id)
    if not path.exists():
        return None
    return RunManifest.model_validate_json(path.read_text())


# ---------------------------------------------------------------------------
# Mock scoring engine (placeholder until real ML is wired)
# ---------------------------------------------------------------------------

def _mock_score(algorithm: ScoringAlgorithm, seed: int, guide_seq: str) -> AlgorithmScore:
    """
    Deterministic mock scores derived from guide sequence + seed.
    Replace with real model calls in production.
    """
    import random
    rng = random.Random(seed + hash(algorithm.value) + hash(guide_seq))

    on_target = round(rng.uniform(0.55, 0.95), 4)
    off_target = round(rng.uniform(0.05, 0.45), 4)
    se = round(rng.uniform(0.01, 0.08), 4)
    ci_low = round(max(0.0, on_target - 1.96 * se), 4)
    ci_high = round(min(1.0, on_target + 1.96 * se), 4)

    return AlgorithmScore(
        algorithm=algorithm,
        on_target_score=on_target,
        off_target_risk=off_target,
        confidence_interval_95_low=ci_low,
        confidence_interval_95_high=ci_high,
        standard_error=se,
        raw_data={"mock": True, "seed": seed},
    )


def _mock_bystander_edits(guide_seq: str, window_start: int, window_end: int, editor_type: BaseEditorType) -> list[BystanderEditPrediction]:
    """Predict bystander edits within the editing window."""
    target_base = "C" if editor_type == BaseEditorType.CBE else "A"
    edited_base = "T" if editor_type == BaseEditorType.CBE else "G"
    window_seq = guide_seq[window_start - 1 : window_end]
    predictions = []
    for i, base in enumerate(window_seq):
        if base == target_base:
            pos = window_start + i
            prob = round(0.3 + (i * 0.1), 2)  # mock gradient
            risk = "high" if prob > 0.7 else "medium" if prob > 0.4 else "low"
            predictions.append(BystanderEditPrediction(
                position_in_window=pos,
                original_base=base,
                edited_base=edited_base,
                probability=min(prob, 0.99),
                risk_level=risk,
            ))
    return predictions


def _mock_explanations(scores: list[AlgorithmScore]) -> list[ExplainabilityEntry]:
    return [
        ExplainabilityEntry(
            metric="on_target_efficiency",
            value=scores[0].on_target_score if scores else 0.0,
            plain_text="On-target efficiency is primarily driven by the GC content and seed region motif of the guide RNA.",
            caveats="Predictions are derived from aggregate datasets and may not generalize to rare cell types or genetic variants.",
            top_features=[
                {"feature": "gc_content", "shap_value": 0.21},
                {"feature": "seed_region_motif", "shap_value": 0.17},
                {"feature": "pam_accessibility", "shap_value": 0.09},
            ],
        ),
        ExplainabilityEntry(
            metric="off_target_risk",
            value=scores[0].off_target_risk if scores else 0.0,
            plain_text="Off-target risk is elevated due to partial homology with 3 known off-target loci at ≤4 mismatches.",
            caveats="Cas9 can bind at sites with up to 6 mismatches; exponential site growth means risk may be underestimated.",
            top_features=[
                {"feature": "seed_mismatch_count", "shap_value": 0.34},
                {"feature": "pam_distal_homology", "shap_value": 0.12},
            ],
        ),
    ]


def _run_design_pipeline(manifest: RunManifest) -> RunManifest:
    """
    Execute the (mocked) design pipeline and populate prediction + step traces.
    In production, each step calls real ML inference.
    """
    req = manifest.run_request
    guide = req.guide_rna
    editor = req.editor_config
    seed = req.random_seed

    # Step 1 — scoring
    step_start = datetime.now(timezone.utc)
    scores = [_mock_score(algo, seed, guide.sequence) for algo in editor.algorithms]
    step1 = StepTrace(
        step_name="scoring",
        start_time=step_start,
        end_time=datetime.now(timezone.utc),
        exit_status=0,
        docker_image=manifest.docker_image,
        command_args=["bin/scorer", "--guide", guide.sequence, "--seed", str(seed)],
        seed_used=seed,
    )

    # Step 2 — bystander analysis
    step_start = datetime.now(timezone.utc)
    bystanders = _mock_bystander_edits(
        guide.sequence,
        editor.editing_window_start,
        editor.editing_window_end,
        editor.editor_type,
    )
    step2 = StepTrace(
        step_name="bystander_analysis",
        start_time=step_start,
        end_time=datetime.now(timezone.utc),
        exit_status=0,
        docker_image=manifest.docker_image,
        command_args=["bin/bystander", "--window", f"{editor.editing_window_start}-{editor.editing_window_end}"],
    )

    # Step 3 — interpretability
    step_start = datetime.now(timezone.utc)
    explanations = _mock_explanations(scores)
    step3 = StepTrace(
        step_name="interpretability",
        start_time=step_start,
        end_time=datetime.now(timezone.utc),
        exit_status=0,
        docker_image=manifest.docker_image,
        command_args=["bin/explain", "--method", "SHAP+LIME"],
    )

    # Track-specific fields
    structural_variation_risk = None
    genome_coverage = None
    if manifest.track == RunTrack.THERAPEUTIC:
        structural_variation_risk = "low"  # mock
    elif manifest.track in (RunTrack.CROP_DEMO,):
        genome_coverage = 0.87  # mock

    window_bases = guide.sequence[editor.editing_window_start - 1 : editor.editing_window_end]
    target_base = "C" if editor.editor_type == BaseEditorType.CBE else "A"

    prediction = DesignPrediction(
        scores=scores,
        bystander_edits=bystanders,
        explanations=explanations,
        editing_window_bases=window_bases,
        target_base_count=window_bases.count(target_base),
        structural_variation_risk=structural_variation_risk,
        genome_coverage=genome_coverage,
    )

    # Output entities
    pred_json = json.dumps(prediction.model_dump(), default=str)
    result_entity = OutputEntity(
        entity_id=f"#prediction-{manifest.run_id}",
        name="prediction.json",
        sha256_hash=_sha256(pred_json),
        media_type="application/json",
        description="Aggregated scoring and interpretability output",
    )

    manifest.prediction = prediction
    manifest.step_traces = [step1, step2, step3]
    manifest.result = [result_entity]
    manifest.status = RunStatus.COMPLETED
    manifest.end_time = datetime.now(timezone.utc)

    return manifest


# ---------------------------------------------------------------------------
# Public Service Functions
# ---------------------------------------------------------------------------

def create_run(run_request: RunRequest) -> RunManifest:
    """Initialize and execute a new design run, persist the manifest."""
    digest = _inputs_digest(run_request)

    input_entity = InputEntity(
        entity_id=f"#input-guide-rna",
        name="guide_rna_input.json",
        sha256_hash=_sha256(run_request.guide_rna.model_dump_json()),
        media_type="application/json",
        description=f"Guide RNA for target gene: {run_request.guide_rna.target_gene}",
    )

    manifest = RunManifest(
        git_sha=settings.GIT_SHA,
        docker_image=settings.DOCKER_IMAGE,
        inputs_digest=digest,
        object=[input_entity],
        run_request=run_request,
        track=run_request.track,
        benchmark_mode=run_request.benchmark_mode,
        status=RunStatus.RUNNING,
    )

    # Execute pipeline
    manifest = _run_design_pipeline(manifest)

    # Persist
    _save_manifest(manifest)

    # Write to benchmark ledger if flagged
    if run_request.benchmark_mode:
        _write_benchmark_result(manifest)

    return manifest


def get_run(run_id: UUID) -> Optional[RunManifest]:
    return _load_manifest(run_id)


def list_runs(track: Optional[RunTrack] = None, limit: int = 50) -> list[RunSummary]:
    runs_dir = _runs_path()
    summaries = []
    for f in sorted(runs_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        try:
            m = RunManifest.model_validate_json(f.read_text())
            if track and m.track != track:
                continue
            summaries.append(RunSummary(
                run_id=m.run_id,
                status=m.status,
                track=m.track,
                target_gene=m.run_request.guide_rna.target_gene,
                editor_type=m.run_request.editor_config.editor_type,
                start_time=m.start_time,
                end_time=m.end_time,
                duration_seconds=m.duration_seconds,
                benchmark_mode=m.benchmark_mode,
            ))
        except Exception:
            continue
    return summaries


def diff_runs(run_a_id: UUID, run_b_id: UUID) -> Optional[ManifestDiff]:
    """Structural diff of two run manifests — surfaces metric and config changes."""
    a = _load_manifest(run_a_id)
    b = _load_manifest(run_b_id)
    if not a or not b:
        return None

    diffs: list[ManifestDiffEntry] = []

    def _compare(field: str, val_a, val_b):
        diffs.append(ManifestDiffEntry(field=field, run_a_value=val_a, run_b_value=val_b, changed=val_a != val_b))

    _compare("instrument_version", a.instrument_version, b.instrument_version)
    _compare("git_sha", a.git_sha, b.git_sha)
    _compare("inputs_digest", a.inputs_digest, b.inputs_digest)
    _compare("track", a.track, b.track)
    _compare("editor_type", a.run_request.editor_config.editor_type, b.run_request.editor_config.editor_type)
    _compare("guide_sequence", a.run_request.guide_rna.sequence, b.run_request.guide_rna.sequence)
    _compare("editing_window", f"{a.run_request.editor_config.editing_window_start}-{a.run_request.editor_config.editing_window_end}",
                                f"{b.run_request.editor_config.editing_window_start}-{b.run_request.editor_config.editing_window_end}")
    _compare("random_seed", a.run_request.random_seed, b.run_request.random_seed)
    _compare("benchmark_mode", a.benchmark_mode, b.benchmark_mode)
    _compare("status", a.status, b.status)
    _compare("duration_seconds", a.duration_seconds, b.duration_seconds)

    # Score comparison
    if a.prediction and b.prediction:
        for score_a in a.prediction.scores:
            score_b_list = [s for s in b.prediction.scores if s.algorithm == score_a.algorithm]
            if score_b_list:
                score_b = score_b_list[0]
                _compare(f"{score_a.algorithm.value}.on_target_score", score_a.on_target_score, score_b.on_target_score)
                _compare(f"{score_a.algorithm.value}.off_target_risk", score_a.off_target_risk, score_b.off_target_risk)

    changed_count = sum(1 for d in diffs if d.changed)
    summary = f"{changed_count} of {len(diffs)} fields differ between run {run_a_id} and {run_b_id}."

    return ManifestDiff(
        run_a_id=run_a_id,
        run_b_id=run_b_id,
        differences=diffs,
        summary=summary,
    )


def rerun(run_id: UUID) -> Optional[RunManifest]:
    """Re-execute a run using its archived inputs (same inputs_digest)."""
    original = _load_manifest(run_id)
    if not original:
        return None
    return create_run(original.run_request)


def _write_benchmark_result(manifest: RunManifest) -> None:
    if not manifest.prediction:
        return
    scores = manifest.prediction.scores
    on_target_mean = round(sum(s.on_target_score for s in scores) / len(scores), 4) if scores else 0.0
    off_target_mean = round(sum(s.off_target_risk for s in scores) / len(scores), 4) if scores else 0.0

    result = BenchmarkResult(
        run_id=manifest.run_id,
        track=manifest.track,
        task_success=on_target_mean >= 0.6 and off_target_mean <= 0.4,
        on_target_mean=on_target_mean,
        off_target_risk_mean=off_target_mean,
        completion_time_seconds=manifest.duration_seconds or 0.0,
        model_version=manifest.instrument_version,
    )

    bench_file = _benchmarks_path() / "benchmark_results.json"
    results = []
    if bench_file.exists():
        try:
            results = json.loads(bench_file.read_text())
        except Exception:
            results = []
    results.append(json.loads(result.model_dump_json()))
    bench_file.write_text(json.dumps(results, indent=2))


def get_leaderboard(model_version: Optional[str] = None, track: Optional[RunTrack] = None) -> list[LeaderboardEntry]:
    bench_file = _benchmarks_path() / "benchmark_results.json"
    if not bench_file.exists():
        return []
    try:
        raw = json.loads(bench_file.read_text())
    except Exception:
        return []

    entries = []
    for r in raw:
        if model_version and r.get("model_version") != model_version:
            continue
        if track and r.get("track") != track:
            continue
        entries.append(r)

    # Rank by on_target_mean desc
    entries.sort(key=lambda x: x["on_target_mean"], reverse=True)
    total = len(entries)

    leaderboard = []
    for i, e in enumerate(entries):
        run = _load_manifest(UUID(e["run_id"]))
        gene = run.run_request.guide_rna.target_gene if run else "unknown"
        editor = run.run_request.editor_config.editor_type if run else BaseEditorType.CBE
        percentile = round((1 - i / max(total, 1)) * 100, 1)
        leaderboard.append(LeaderboardEntry(
            rank=i + 1,
            run_id=UUID(e["run_id"]),
            target_gene=gene,
            editor_type=editor,
            on_target_mean=e["on_target_mean"],
            off_target_risk_mean=e["off_target_risk_mean"],
            percentile_specificity=percentile,
            model_version=e["model_version"],
            created_at=datetime.fromisoformat(e["created_at"]),
        ))
    return leaderboard
