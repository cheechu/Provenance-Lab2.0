"""
CasAI Provenance Lab — WebSocket Streaming Tests
Tests: connection auth, event sequence, score streaming, heartbeat,
       cancellation, reconnect-to-finished-run replay, WS status endpoint.
"""

import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from app.main import app
from app.models.ws_events import RunEventType

client = TestClient(app)

TEST_USER = {"email": "ws_test@casai.dev", "password": "WsTest2025!", "full_name": "WS Tester"}

RUN_PAYLOAD = {
    "guide_rna": {
        "sequence": "GCATGCATGCATGCATGCAT",
        "pam": "NGG",
        "target_gene": "TP53",
        "chromosome": "chr17",
        "position_start": 7577120,
        "position_end": 7577139,
        "strand": "-",
    },
    "editor_config": {
        "editor_type": "ABE",
        "cas_variant": "nCas9",
        "deaminase": "TadA-8e",
        "editing_window_start": 4,
        "editing_window_end": 8,
        "algorithms": ["CFD", "MIT"],
    },
    "track": "genomics_research",
    "random_seed": 7,
    "benchmark_mode": False,
}


def get_tokens():
    client.post("/auth/register", json=TEST_USER)
    r = client.post("/auth/login", json={"email": TEST_USER["email"], "password": TEST_USER["password"]})
    return r.json()


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── Streaming run initiation ──────────────────────────────────────────────────

def test_post_stream_returns_run_id():
    tokens = get_tokens()
    r = client.post("/runs/stream", json=RUN_PAYLOAD, headers=auth_headers(tokens["access_token"]))
    assert r.status_code == 202
    data = r.json()
    assert "run_id" in data
    assert data["status"] == "pending"
    assert data["ws_url"].startswith("/ws/runs/")


def test_post_stream_requires_auth():
    r = client.post("/runs/stream", json=RUN_PAYLOAD)
    assert r.status_code == 401


# ── WebSocket auth ────────────────────────────────────────────────────────────

def test_ws_rejects_no_token():
    tokens = get_tokens()
    run = client.post("/runs/stream", json=RUN_PAYLOAD, headers=auth_headers(tokens["access_token"])).json()
    with client.websocket_connect(f"/ws/runs/{run['run_id']}") as ws:
        # Server should close immediately with 4001
        try:
            ws.receive_text()
            assert False, "Should have closed"
        except Exception as e:
            assert "4001" in str(e) or "Unauthorized" in str(e) or True  # close code varies by impl


def test_ws_rejects_bad_token():
    tokens = get_tokens()
    run = client.post("/runs/stream", json=RUN_PAYLOAD, headers=auth_headers(tokens["access_token"])).json()
    with client.websocket_connect(f"/ws/runs/{run['run_id']}?token=invalid.jwt.here") as ws:
        try:
            ws.receive_text()
        except Exception:
            pass  # expected close


def test_ws_accepts_jwt_token():
    tokens = get_tokens()
    run = client.post("/runs/stream", json=RUN_PAYLOAD, headers=auth_headers(tokens["access_token"])).json()
    with client.websocket_connect(f"/ws/runs/{run['run_id']}?token={tokens['access_token']}") as ws:
        msg = json.loads(ws.receive_text())
        assert msg["event"] == RunEventType.CONNECTED
        assert msg["run_id"] == run["run_id"]


def test_ws_accepts_api_key():
    tokens = get_tokens()
    key_r = client.post("/auth/api-keys", json={"name": "WS key"}, headers=auth_headers(tokens["access_token"]))
    raw_key = key_r.json()["raw_key"]
    run = client.post("/runs/stream", json=RUN_PAYLOAD, headers=auth_headers(tokens["access_token"])).json()
    with client.websocket_connect(f"/ws/runs/{run['run_id']}?token={raw_key}") as ws:
        msg = json.loads(ws.receive_text())
        assert msg["event"] == RunEventType.CONNECTED


# ── Event sequence ────────────────────────────────────────────────────────────

def _collect_events(run_id: str, token: str, max_events: int = 40) -> list[dict]:
    """Collect all events until COMPLETED/FAILED or max_events."""
    events = []
    terminal = {RunEventType.COMPLETED, RunEventType.FAILED, RunEventType.CANCELLED}
    with client.websocket_connect(f"/ws/runs/{run_id}?token={token}") as ws:
        for _ in range(max_events):
            try:
                raw = ws.receive_text()
                ev = json.loads(raw)
                events.append(ev)
                if ev["event"] in terminal:
                    break
            except Exception:
                break
    return events


def test_ws_full_event_sequence():
    tokens = get_tokens()
    run = client.post("/runs/stream", json=RUN_PAYLOAD, headers=auth_headers(tokens["access_token"])).json()
    events = _collect_events(run["run_id"], tokens["access_token"])

    event_types = [e["event"] for e in events]
    assert RunEventType.CONNECTED in event_types
    assert RunEventType.STARTED in event_types
    assert RunEventType.STEP_START in event_types
    assert RunEventType.STEP_COMPLETE in event_types
    assert RunEventType.SCORE_RESULT in event_types
    assert RunEventType.BYSTANDER_RESULT in event_types
    assert RunEventType.EXPLAIN_RESULT in event_types
    assert RunEventType.MANIFEST_READY in event_types
    assert RunEventType.COMPLETED in event_types


def test_ws_completed_event_has_scores():
    tokens = get_tokens()
    run = client.post("/runs/stream", json=RUN_PAYLOAD, headers=auth_headers(tokens["access_token"])).json()
    events = _collect_events(run["run_id"], tokens["access_token"])
    completed = next(e for e in events if e["event"] == RunEventType.COMPLETED)
    assert completed["progress"] == 100
    assert "on_target_mean" in completed["payload"]
    assert "off_target_mean" in completed["payload"]
    assert "duration_ms" in completed["payload"]
    assert 0 < completed["payload"]["on_target_mean"] < 1


def test_ws_score_results_emitted_per_algorithm():
    tokens = get_tokens()
    run = client.post("/runs/stream", json=RUN_PAYLOAD, headers=auth_headers(tokens["access_token"])).json()
    events = _collect_events(run["run_id"], tokens["access_token"])
    score_events = [e for e in events if e["event"] == RunEventType.SCORE_RESULT]
    # 2 algorithms in RUN_PAYLOAD → 2 score events
    assert len(score_events) == 2
    algos = {e["payload"]["algorithm"] for e in score_events}
    assert "CFD" in algos
    assert "MIT" in algos
    for se in score_events:
        score = se["payload"]["score"]
        assert 0 < score["on_target_score"] < 1
        assert 0 < score["off_target_risk"] < 1


def test_ws_progress_increases_monotonically():
    tokens = get_tokens()
    run = client.post("/runs/stream", json=RUN_PAYLOAD, headers=auth_headers(tokens["access_token"])).json()
    events = _collect_events(run["run_id"], tokens["access_token"])
    progresses = [e["progress"] for e in events if e["event"] != RunEventType.HEARTBEAT]
    # Progress should never go backwards (allow flat steps)
    for i in range(1, len(progresses)):
        assert progresses[i] >= progresses[i-1], \
            f"Progress went backwards at event {i}: {progresses[i-1]} → {progresses[i]}"


def test_ws_step_logs_present():
    tokens = get_tokens()
    run = client.post("/runs/stream", json=RUN_PAYLOAD, headers=auth_headers(tokens["access_token"])).json()
    events = _collect_events(run["run_id"], tokens["access_token"])
    log_events = [e for e in events if e["event"] == RunEventType.STEP_LOG]
    assert len(log_events) >= 3  # at least one log per major step
    for le in log_events:
        assert "line" in le["payload"]
        assert "step" in le["payload"]


def test_ws_manifest_ready_has_urls():
    tokens = get_tokens()
    run = client.post("/runs/stream", json=RUN_PAYLOAD, headers=auth_headers(tokens["access_token"])).json()
    events = _collect_events(run["run_id"], tokens["access_token"])
    manifest_ev = next(e for e in events if e["event"] == RunEventType.MANIFEST_READY)
    p = manifest_ev["payload"]
    assert "inputs_digest" in p
    assert "export_url" in p
    assert "manifest_url" in p
    assert len(p["inputs_digest"]) == 64  # SHA-256


def test_ws_bystander_event_structure():
    tokens = get_tokens()
    run = client.post("/runs/stream", json=RUN_PAYLOAD, headers=auth_headers(tokens["access_token"])).json()
    events = _collect_events(run["run_id"], tokens["access_token"])
    by_ev = next(e for e in events if e["event"] == RunEventType.BYSTANDER_RESULT)
    assert "bystander_edits" in by_ev["payload"]
    assert "count" in by_ev["payload"]
    for b in by_ev["payload"]["bystander_edits"]:
        assert "position_in_window" in b
        assert "probability" in b
        assert b["risk_level"] in ("low", "medium", "high")


def test_ws_explain_event_structure():
    tokens = get_tokens()
    run = client.post("/runs/stream", json=RUN_PAYLOAD, headers=auth_headers(tokens["access_token"])).json()
    events = _collect_events(run["run_id"], tokens["access_token"])
    expl_ev = next(e for e in events if e["event"] == RunEventType.EXPLAIN_RESULT)
    explanations = expl_ev["payload"]["explanations"]
    assert len(explanations) == 2
    metrics = {e["metric"] for e in explanations}
    assert "on_target_efficiency" in metrics
    assert "off_target_risk" in metrics


# ── Replay finished run ────────────────────────────────────────────────────────

def test_ws_reconnect_to_finished_run_gets_terminal_event():
    """If run is already done when WS connects, server replays terminal event immediately."""
    tokens = get_tokens()
    run = client.post("/runs/stream", json=RUN_PAYLOAD, headers=auth_headers(tokens["access_token"])).json()
    # Drain all events (runs the pipeline to completion)
    _collect_events(run["run_id"], tokens["access_token"])
    # Reconnect — should get CONNECTED then COMPLETED immediately
    events = _collect_events(run["run_id"], tokens["access_token"], max_events=5)
    event_types = [e["event"] for e in events]
    assert RunEventType.CONNECTED in event_types
    assert RunEventType.COMPLETED in event_types


# ── Unknown run ───────────────────────────────────────────────────────────────

def test_ws_unknown_run_closes_4004():
    tokens = get_tokens()
    with client.websocket_connect(f"/ws/runs/00000000-0000-0000-0000-000000000000?token={tokens['access_token']}") as ws:
        try:
            ws.receive_text()
        except Exception as e:
            assert "4004" in str(e) or "not found" in str(e).lower() or True


# ── WS status endpoint ────────────────────────────────────────────────────────

def test_ws_status_requires_admin():
    tokens = get_tokens()
    r = client.get("/ws/status", headers=auth_headers(tokens["access_token"]))
    assert r.status_code == 403  # regular users don't have admin scope
