"""Integration tests for arca-cert REST and MCP."""
import os

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from src.main import app  # noqa: E402


@pytest.fixture
def client(dev_token):
    with TestClient(app) as c:
        # Every call carries a valid SSO access token, like the Suite portal
        # does in production (security by design: no anonymous fallback).
        c.headers["Authorization"] = f"Bearer {dev_token}"
        yield c


SCORES = [
    {"dimension": "confidence", "value": 0.9},
    {"dimension": "security", "value": 0.5},
]
EVIDENCE = [{"source": "trust", "ref_id": "r1"}]


def test_healthz(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_build_and_publish_dossier(client):
    built = client.post("/api/v1/dossiers", json={
        "target": "arca-flow", "scores": SCORES, "evidence": EVIDENCE}).json()
    dossier_id = built["dossier"]["id"]
    assert built["dossier"]["status"] == "draft"
    assert len(built["remediation"]["items"]) == 1
    published = client.post(f"/api/v1/dossiers/{dossier_id}/publish",
                            json={"reviewer": "auditor-1"}).json()
    assert published["status"] == "published"
    assert published["seal"]


def test_list_and_get(client):
    client.post("/api/v1/dossiers", json={
        "target": "arca-hub", "scores": SCORES, "evidence": EVIDENCE})
    response = client.get("/api/v1/dossiers", params={"target": "arca-hub"})
    assert response.status_code == 200
    assert len(response.json()["dossiers"]) == 1


def test_remediation_endpoint(client):
    built = client.post("/api/v1/dossiers", json={
        "target": "arca-packs", "scores": SCORES, "evidence": EVIDENCE}).json()
    rid = built["dossier"]["id"]
    plan = client.get(f"/api/v1/dossiers/{rid}/remediation").json()
    assert plan["dossier_id"] == rid


def test_build_package(client):
    response = client.post("/api/v1/packages", json={
        "target": "arca-exchange", "scores": SCORES, "evidence": EVIDENCE})
    assert response.status_code == 201
    package = response.json()
    assert package["id"]
    assert package["assessment"]["level"]


def test_readiness_endpoint(client):
    response = client.post("/api/v1/readiness", json={
        "target": "arca-readiness", "scores": SCORES})
    assert response.status_code == 201
    data = response.json()
    assert data["level"] == "conditional"


def test_evidence_binder_endpoint(client):
    built = client.post("/api/v1/dossiers", json={
        "target": "arca-binder", "scores": SCORES, "evidence": EVIDENCE}).json()
    rid = built["dossier"]["id"]
    response = client.get(f"/api/v1/evidence-binders/{rid}")
    assert response.status_code == 200
    assert response.json()["dossier_id"] == rid


def test_mcp_create_cert_package(client):
    response = client.post("/mcp/tools/create_cert_package", json={
        "target": "arca-exchange", "scores": SCORES, "evidence": EVIDENCE})
    assert response.status_code == 200
    assert response.json()["package_id"]


def test_mcp_evidence_assemble(client):
    built = client.post("/api/v1/dossiers", json={
        "target": "arca-studio", "scores": SCORES, "evidence": EVIDENCE}).json()
    rid = built["dossier"]["id"]
    response = client.post("/mcp/tools/assemble_evidence", json={
        "dossier_id": rid,
        "additional_refs": [{"source": "bench", "ref_id": "b1"}]})
    assert response.status_code == 200
    assert response.json()["evidence_count"] == 2


def test_mcp_get_readiness_status(client):
    response = client.post("/mcp/tools/get_readiness_status", json={
        "target": "arca-studio", "scores": SCORES})
    assert response.status_code == 200
    assert response.json()["level"]


def test_mcp_publish_cert_package(client):
    built = client.post("/api/v1/dossiers", json={
        "target": "arca-publish", "scores": SCORES, "evidence": EVIDENCE}).json()
    rid = built["dossier"]["id"]
    response = client.post("/mcp/tools/publish_cert_package", json={
        "dossier_id": rid, "reviewer": "auditor-mcp"})
    assert response.status_code == 200
    assert response.json()["status"] == "published"


def test_auth_required_without_token():
    """Security by design: no Authorization header means 401 — there is no
    anonymous or dev bypass."""
    with TestClient(app) as c:
        response = c.get("/api/v1/dossiers")
        assert response.status_code == 401


def test_dossier_with_unknown_score_keys_is_422_not_500(client):
    """Regression: ScoreInput(**s) raised TypeError on unknown keys -> 500.
    Payload validation failures must answer 422 (honest API contract)."""
    response = client.post("/api/v1/dossiers", json={
        "target": "arca-hub",
        "scores": [{"run_id": "r1", "passed": 1, "total": 1}]})
    assert response.status_code == 422
    response = client.post("/api/v1/packages", json={
        "target": "arca-hub",
        "scores": [{"run_id": "r1", "passed": 1, "total": 1}]})
    assert response.status_code == 422
