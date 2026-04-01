"""
CasAI Provenance Lab — Test Suite
Tests for RunManifest lifecycle, provenance, diff, export, and benchmarks.
"""

import json
import zipfile
import io
import pytest
from uuid import UUID
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import BaseEditorType, RunTrack, ScoringAlgorithm, RunStatus

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_GUIDE_PAYLOAD = {
    "guide_rna": {
        "sequence": "ATGCATGCATGCATGCATGC",
        "pam": "NGG",
        "target_gene": "BRCA1",
        "chromosome": "chr17",
        "position_start": 41196312,
        "position_end": 41196331,
        "strand": "+",
    },
    "editor_config": {
        "editor_type": "CBE",
        "cas_variant": "nCas9",
        "deaminase": "APOBEC3A",
        "editing_window_start": 4,
        "editing_window_end": 8,
        "algorithms": ["CFD", "MIT"],
    },
    "track": "genomics_research",
    "random_seed": 42,
    "benchmark_mode": False,
}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root_info():
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "CasAI Provenance Lab API"
    assert "git_sha" in data


# ---------------------------------------------------------------------------
# Run Creation
# ---------------------------------------------------------------------------

def test_create_run_success():
    r = client.post("/runs", json=VALID_GUIDE_PAYLOAD)
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "completed"
    assert data["track"] == "genomics_research"
    assert "run_id" in data
    assert "inputs_digest" in data
    assert data["inputs_digest"] != ""


def test_create_run_populates_prediction():
    r = client.post("/runs", json=VALID_GUIDE_PAYLOAD)
    assert r.status_code == 201
    pred = r.json()["prediction"]
    assert pred is not None
    assert len(pred["scores"]) == 2  # CFD + MIT
    assert len(pred["explanations"]) == 2


def test_create_run_invalid_sequence():
    payload = json.loads(json.dumps(VALID_GUIDE_PAYLOAD))
    payload["guide_rna"]["sequence"] = "ATGCATGCATGCATGCATXX"  # invalid bases
    r = client.post("/runs", json=payload)
    assert r.status_code == 422


def test_create_run_bad_window():
    payload = json.loads(json.dumps(VALID_GUIDE_PAYLOAD))
    payload["editor_config"]["editing_window_start"] = 8
    payload["editor_config"]["editing_window_end"] = 4  # end < start
    r = client.post("/runs", json=payload)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def test_get_run():
    run_id = client.post("/runs", json=VALID_GUIDE_PAYLOAD).json()["run_id"]
    r = client.get(f"/runs/{run_id}")
    assert r.status_code == 200
    assert r.json()["run_id"] == run_id


def test_get_run_not_found():
    r = client.get("/runs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_list_runs():
    client.post("/runs", json=VALID_GUIDE_PAYLOAD)
    r = client.get("/runs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1


# ---------------------------------------------------------------------------
# Provenance Manifest (JSON-LD)
# ---------------------------------------------------------------------------

def test_get_manifest_jsonld():
    run_id = client.post("/runs", json=VALID_GUIDE_PAYLOAD).json()["run_id"]
    r = client.get(f"/runs/{run_id}/manifest")
    assert r.status_code == 200
    data = r.json()
    assert "@context" in data
    assert "@graph" in data
    graph_types = [node.get("@type") for node in data["@graph"]]
    assert any("Dataset" in str(t) for t in graph_types)
    assert any("CreateAction" in str(t) for t in graph_types)


def test_manifest_contains_inputs_digest():
    r = client.post("/runs", json=VALID_GUIDE_PAYLOAD)
    assert r.json()["inputs_digest"] != ""


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

def test_diff_runs():
    r1 = client.post("/runs", json=VALID_GUIDE_PAYLOAD).json()["run_id"]
    payload2 = json.loads(json.dumps(VALID_GUIDE_PAYLOAD))
    payload2["random_seed"] = 99
    r2 = client.post("/runs", json=payload2).json()["run_id"]

    r = client.get(f"/runs/{r1}/diff", params={"other_id": r2})
    assert r.status_code == 200
    diff = r.json()
    assert diff["run_a_id"] == r1
    assert diff["run_b_id"] == r2
    assert len(diff["differences"]) > 0
    seed_diff = next((d for d in diff["differences"] if d["field"] == "random_seed"), None)
    assert seed_diff is not None
    assert seed_diff["changed"] is True


# ---------------------------------------------------------------------------
# Re-run
# ---------------------------------------------------------------------------

def test_rerun():
    original = client.post("/runs", json=VALID_GUIDE_PAYLOAD).json()
    original_id = original["run_id"]
    original_digest = original["inputs_digest"]

    r = client.post(f"/runs/rerun/{original_id}")
    assert r.status_code == 201
    rerun_data = r.json()
    assert rerun_data["run_id"] != original_id
    assert rerun_data["inputs_digest"] == original_digest  # same inputs


# ---------------------------------------------------------------------------
# Export Pack
# ---------------------------------------------------------------------------

def test_export_zip():
    run_id = client.post("/runs", json=VALID_GUIDE_PAYLOAD).json()["run_id"]
    r = client.get(f"/runs/{run_id}/export.zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert "run.manifest.json" in names
    assert "report.txt" in names
    assert "cloning_oligos.json" in names
    assert "validation_primers.json" in names
    assert "protospacer.fasta" in names
    assert "provenance_passport.md" in names


def test_export_manifest_valid_jsonld():
    run_id = client.post("/runs", json=VALID_GUIDE_PAYLOAD).json()["run_id"]
    r = client.get(f"/runs/{run_id}/export.zip")
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    manifest_data = json.loads(zf.read("run.manifest.json"))
    assert "@context" in manifest_data
    assert "@graph" in manifest_data


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

def test_benchmark_run():
    r = client.post("/benchmarks/run", json=VALID_GUIDE_PAYLOAD)
    assert r.status_code == 201
    assert r.json()["benchmark_mode"] is True


def test_leaderboard():
    client.post("/benchmarks/run", json=VALID_GUIDE_PAYLOAD)
    r = client.get("/benchmarks/leaderboard")
    assert r.status_code == 200
    board = r.json()
    assert isinstance(board, list)
    if board:
        entry = board[0]
        assert "rank" in entry
        assert "percentile_specificity" in entry
        assert entry["rank"] == 1


def test_leaderboard_filter_by_track():
    r = client.get("/benchmarks/leaderboard", params={"track": "genomics_research"})
    assert r.status_code == 200
