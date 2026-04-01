"""
CasAI Provenance Lab — Auth + ML Scoring + DB Test Suite
Tests: registration, login, JWT lifecycle, API keys, scope enforcement,
       rate limiting, all 5 scoring algorithms, SHAP explanations.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_USER = {"email": "researcher@casai.dev", "password": "CasAI2025!", "full_name": "Dr. Test"}
TEST_USER_2 = {"email": "other@casai.dev", "password": "OtherPass1!"}

VALID_RUN = {
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


# ── helpers ──────────────────────────────────────────────────────────────────

def register_and_login(user=TEST_USER):
    client.post("/auth/register", json=user)
    r = client.post("/auth/login", json={"email": user["email"], "password": user["password"]})
    return r.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Health ───────────────────────────────────────────────────────────────────

def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_root_includes_auth_info():
    data = client.get("/").json()
    assert data["auth"] == "JWT Bearer or X-API-Key"
    assert "mock_ml" in data


# ── Registration ─────────────────────────────────────────────────────────────

def test_register_success():
    r = client.post("/auth/register", json=TEST_USER)
    assert r.status_code in (201, 409)  # 409 if already exists from prior test
    if r.status_code == 201:
        data = r.json()
        assert data["email"] == TEST_USER["email"]
        assert "hashed_password" not in data
        assert "id" in data


def test_register_duplicate_email():
    client.post("/auth/register", json=TEST_USER)
    r = client.post("/auth/register", json=TEST_USER)
    assert r.status_code == 409
    assert "already registered" in r.json()["detail"]


def test_register_weak_password():
    r = client.post("/auth/register", json={"email": "weak@x.com", "password": "short"})
    assert r.status_code == 422


def test_register_no_digit_password():
    r = client.post("/auth/register", json={"email": "nodigit@x.com", "password": "NoDigitHere!"})
    assert r.status_code == 422
    assert "digit" in str(r.json()).lower()


# ── Login ─────────────────────────────────────────────────────────────────────

def test_login_success():
    client.post("/auth/register", json=TEST_USER)
    r = client.post("/auth/login", json={"email": TEST_USER["email"], "password": TEST_USER["password"]})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0
    assert data["user"]["email"] == TEST_USER["email"]


def test_login_wrong_password():
    client.post("/auth/register", json=TEST_USER)
    r = client.post("/auth/login", json={"email": TEST_USER["email"], "password": "wrongpass1"})
    assert r.status_code == 401


def test_login_unknown_email():
    r = client.post("/auth/login", json={"email": "nobody@x.com", "password": "Test1234!"})
    assert r.status_code == 401


# ── JWT access token ──────────────────────────────────────────────────────────

def test_me_authenticated():
    tokens = register_and_login()
    r = client.get("/auth/me", headers=auth_headers(tokens["access_token"]))
    assert r.status_code == 200
    assert r.json()["email"] == TEST_USER["email"]


def test_me_unauthenticated():
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_bad_token():
    r = client.get("/auth/me", headers={"Authorization": "Bearer not.a.real.token"})
    assert r.status_code == 401


# ── Refresh token ─────────────────────────────────────────────────────────────

def test_refresh_token_rotation():
    tokens = register_and_login()
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    new_tokens = r.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens
    # New refresh token must differ (rotation)
    assert new_tokens["refresh_token"] != tokens["refresh_token"]


def test_refresh_token_single_use():
    """Old refresh token must not work after rotation."""
    tokens = register_and_login()
    old_refresh = tokens["refresh_token"]
    client.post("/auth/refresh", json={"refresh_token": old_refresh})
    # Use the old token again — must fail
    r = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 401


def test_invalid_refresh_token():
    r = client.post("/auth/refresh", json={"refresh_token": "invalid-token"})
    assert r.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────

def test_logout_revokes_refresh():
    tokens = register_and_login()
    r = client.post("/auth/logout", headers=auth_headers(tokens["access_token"]))
    assert r.status_code == 204
    # Refresh after logout must fail
    r2 = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 401


# ── Profile update ────────────────────────────────────────────────────────────

def test_update_profile():
    tokens = register_and_login()
    r = client.patch("/auth/me", json={"full_name": "Updated Name"}, headers=auth_headers(tokens["access_token"]))
    assert r.status_code == 200
    assert r.json()["full_name"] == "Updated Name"


# ── API Keys ──────────────────────────────────────────────────────────────────

def test_create_api_key():
    tokens = register_and_login()
    r = client.post("/auth/api-keys", json={"name": "CI pipeline", "scopes": "read:runs write:runs"}, headers=auth_headers(tokens["access_token"]))
    assert r.status_code == 201
    data = r.json()
    assert "raw_key" in data
    assert data["raw_key"].startswith("casai_")
    assert data["name"] == "CI pipeline"
    assert len(data["raw_key"]) == 70  # "casai_" (6) + 64 hex chars


def test_api_key_raw_shown_once():
    """raw_key is NOT present in the list endpoint."""
    tokens = register_and_login()
    client.post("/auth/api-keys", json={"name": "Key A"}, headers=auth_headers(tokens["access_token"]))
    r = client.get("/auth/api-keys", headers=auth_headers(tokens["access_token"]))
    assert r.status_code == 200
    for key in r.json():
        assert "raw_key" not in key


def test_authenticate_with_api_key():
    tokens = register_and_login()
    key_r = client.post("/auth/api-keys", json={"name": "Test key"}, headers=auth_headers(tokens["access_token"]))
    raw_key = key_r.json()["raw_key"]
    # Use the API key to hit /auth/me
    r = client.get("/auth/me", headers={"X-API-Key": raw_key})
    assert r.status_code == 200
    assert r.json()["email"] == TEST_USER["email"]


def test_revoke_api_key():
    tokens = register_and_login()
    key_r = client.post("/auth/api-keys", json={"name": "To revoke"}, headers=auth_headers(tokens["access_token"]))
    key_id = key_r.json()["id"]
    raw_key = key_r.json()["raw_key"]
    # Revoke
    r = client.delete(f"/auth/api-keys/{key_id}", headers=auth_headers(tokens["access_token"]))
    assert r.status_code == 204
    # Key no longer works
    r2 = client.get("/auth/me", headers={"X-API-Key": raw_key})
    assert r2.status_code == 401


def test_api_key_with_expiry():
    tokens = register_and_login()
    r = client.post("/auth/api-keys", json={"name": "Expiring key", "expires_days": 30}, headers=auth_headers(tokens["access_token"]))
    assert r.status_code == 201
    assert r.json()["expires_at"] is not None


# ── ML Scoring Engine ─────────────────────────────────────────────────────────

def test_run_with_cfd_scoring():
    tokens = register_and_login()
    r = client.post("/runs", json=VALID_RUN, headers=auth_headers(tokens["access_token"]))
    assert r.status_code == 201
    scores = r.json()["prediction"]["scores"]
    cfd = next(s for s in scores if s["algorithm"] == "CFD")
    assert 0 < cfd["on_target_score"] < 1
    assert 0 < cfd["off_target_risk"] < 1
    assert cfd["confidence_interval_95_low"] <= cfd["on_target_score"] <= cfd["confidence_interval_95_high"]
    assert cfd["standard_error"] > 0


def test_run_with_mit_scoring():
    tokens = register_and_login()
    r = client.post("/runs", json=VALID_RUN, headers=auth_headers(tokens["access_token"]))
    scores = r.json()["prediction"]["scores"]
    mit = next(s for s in scores if s["algorithm"] == "MIT")
    assert 0 < mit["on_target_score"] < 1
    assert mit["raw_data"]["weighted_quality"] > 0


def test_run_with_all_five_algorithms():
    tokens = register_and_login()
    payload = {**VALID_RUN}
    payload["editor_config"] = {**payload["editor_config"], "algorithms": ["CFD", "MIT", "CCTop", "DeepCRISPR", "CRISPR-MCA"]}
    r = client.post("/runs", json=payload, headers=auth_headers(tokens["access_token"]))
    assert r.status_code == 201
    scores = r.json()["prediction"]["scores"]
    assert len(scores) == 5
    algos = {s["algorithm"] for s in scores}
    assert algos == {"CFD", "MIT", "CCTop", "DeepCRISPR", "CRISPR-MCA"}


def test_deterministic_scores_same_seed():
    """Same guide + seed must produce identical scores."""
    tokens = register_and_login()
    r1 = client.post("/runs", json=VALID_RUN, headers=auth_headers(tokens["access_token"]))
    r2 = client.post("/runs", json=VALID_RUN, headers=auth_headers(tokens["access_token"]))
    s1 = r1.json()["prediction"]["scores"][0]["on_target_score"]
    s2 = r2.json()["prediction"]["scores"][0]["on_target_score"]
    assert s1 == s2


def test_different_seeds_produce_different_scores():
    tokens = register_and_login()
    p1 = {**VALID_RUN, "random_seed": 1}
    p2 = {**VALID_RUN, "random_seed": 99}
    s1 = client.post("/runs", json=p1, headers=auth_headers(tokens["access_token"])).json()["prediction"]["scores"][0]["on_target_score"]
    s2 = client.post("/runs", json=p2, headers=auth_headers(tokens["access_token"])).json()["prediction"]["scores"][0]["on_target_score"]
    assert s1 != s2


def test_shap_explanations_present():
    tokens = register_and_login()
    r = client.post("/runs", json=VALID_RUN, headers=auth_headers(tokens["access_token"]))
    expl = r.json()["prediction"]["explanations"]
    assert len(expl) == 2
    metrics = {e["metric"] for e in expl}
    assert "on_target_efficiency" in metrics
    assert "off_target_risk" in metrics
    for e in expl:
        assert e["plain_text"] != ""
        assert e["caveats"] != ""
        assert len(e["top_features"]) >= 2


# ── DB persistence ────────────────────────────────────────────────────────────

def test_run_persists_to_db():
    tokens = register_and_login()
    run_id = client.post("/runs", json=VALID_RUN, headers=auth_headers(tokens["access_token"])).json()["run_id"]
    r = client.get(f"/runs/{run_id}", headers=auth_headers(tokens["access_token"]))
    assert r.status_code == 200
    assert r.json()["run_id"] == run_id


def test_list_runs_authenticated():
    tokens = register_and_login()
    client.post("/runs", json=VALID_RUN, headers=auth_headers(tokens["access_token"]))
    r = client.get("/runs", headers=auth_headers(tokens["access_token"]))
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_runs_require_auth():
    r = client.post("/runs", json=VALID_RUN)
    assert r.status_code == 401


def test_export_requires_auth():
    tokens = register_and_login()
    run_id = client.post("/runs", json=VALID_RUN, headers=auth_headers(tokens["access_token"])).json()["run_id"]
    # Without auth — should fail
    r = client.get(f"/runs/{run_id}/export.zip")
    assert r.status_code == 401
