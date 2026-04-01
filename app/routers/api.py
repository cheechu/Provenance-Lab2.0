"""
CasAI Provenance Lab — API Routers
All endpoints as specified in the architectural blueprint.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse

from app.models.schemas import (
    APIResponse,
    LeaderboardEntry,
    ManifestDiff,
    RunManifest,
    RunRequest,
    RunStatus,
    RunSummary,
    RunTrack,
)
from app.services import provenance as svc
from app.services.export_service import build_export_zip

import io

# ---------------------------------------------------------------------------
# Runs Router
# ---------------------------------------------------------------------------

runs_router = APIRouter(prefix="/runs", tags=["Runs"])


@runs_router.post(
    "",
    response_model=RunManifest,
    status_code=201,
    summary="Initiate a new base-editor design run",
    description=(
        "Submit a guide RNA + editor configuration to start a design run. "
        "Returns the full RunManifest including W3C PROV provenance metadata, "
        "scoring results, and interpretability explanations."
    ),
)
def create_run(run_request: RunRequest) -> RunManifest:
    try:
        return svc.create_run(run_request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@runs_router.get(
    "",
    response_model=list[RunSummary],
    summary="List all design runs",
)
def list_runs(
    track: Optional[RunTrack] = Query(None, description="Filter by track"),
    limit: int = Query(50, ge=1, le=200),
) -> list[RunSummary]:
    return svc.list_runs(track=track, limit=limit)


@runs_router.get(
    "/{run_id}",
    response_model=RunManifest,
    summary="Get a run's full manifest",
)
def get_run(run_id: UUID) -> RunManifest:
    manifest = svc.get_run(run_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    return manifest


@runs_router.get(
    "/{run_id}/manifest",
    summary="Get run manifest as W3C PROV JSON-LD",
    description=(
        "Returns the full JSON-LD provenance record conforming to the "
        "RO-Crate Process Run Crate v0.4 profile."
    ),
)
def get_manifest_jsonld(run_id: UUID):
    manifest = svc.get_run(run_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    return JSONResponse(content=manifest.as_json_ld())


@runs_router.get(
    "/{run_id}/diff",
    response_model=ManifestDiff,
    summary="Structural diff of two design runs",
    description=(
        "Compares two RunManifests and returns a structured diff of tool versions, "
        "input parameters, and scoring metrics. Useful for regression monitoring "
        "when models are updated."
    ),
)
def diff_runs(
    run_id: UUID,
    other_id: UUID = Query(..., description="UUID of the second run to compare against"),
) -> ManifestDiff:
    diff = svc.diff_runs(run_id, other_id)
    if not diff:
        raise HTTPException(status_code=404, detail="One or both runs not found.")
    return diff


@runs_router.post(
    "/rerun/{run_id}",
    response_model=RunManifest,
    status_code=201,
    summary="Re-run with identical archived inputs",
    description=(
        "Initiates a new design run using the exact inputs stored in the original "
        "RunManifest. The new run will have a fresh run_id and timestamps, but the "
        "inputs_digest will match, allowing reproducibility verification."
    ),
)
def rerun(run_id: UUID) -> RunManifest:
    result = svc.rerun(run_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    return result


@runs_router.get(
    "/{run_id}/export.zip",
    summary="Download lab-ready Export Pack",
    description=(
        "Streams a ZIP archive containing all artifacts needed for wet-lab transition: "
        "guide sequence, cloning oligos, validation primers, FASTA, the RunManifest "
        "JSON-LD, a human-readable report, and a provenance passport markdown."
    ),
    response_class=StreamingResponse,
)
def export_run(run_id: UUID):
    manifest = svc.get_run(run_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    if manifest.status != RunStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Run has not completed successfully.")

    zip_bytes = build_export_zip(manifest)

    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="casai_export_{run_id}.zip"',
            "Content-Length": str(len(zip_bytes)),
        },
    )


# ---------------------------------------------------------------------------
# Benchmarks Router
# ---------------------------------------------------------------------------

benchmarks_router = APIRouter(prefix="/benchmarks", tags=["Benchmarks"])


@benchmarks_router.post(
    "/run",
    response_model=RunManifest,
    status_code=201,
    summary="Run in benchmark mode (fixed recipe)",
    description=(
        "Executes a design run with benchmark_mode=True, ensuring output is "
        "written to benchmark_results.json for the leaderboard. "
        "The run request is stored as a standard RunManifest."
    ),
)
def benchmark_run(run_request: RunRequest) -> RunManifest:
    run_request.benchmark_mode = True
    try:
        return svc.create_run(run_request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@benchmarks_router.get(
    "/leaderboard",
    response_model=list[LeaderboardEntry],
    summary="Benchmark leaderboard",
    description=(
        "Returns ranked benchmark results. Supports filtering by model version "
        "and track. Displays percentile scores to motivate iteration."
    ),
)
def leaderboard(
    model_version: Optional[str] = Query(None, description="Filter by CasAI-Core model version"),
    track: Optional[RunTrack] = Query(None, description="Filter by application track"),
) -> list[LeaderboardEntry]:
    return svc.get_leaderboard(model_version=model_version, track=track)
