"""Integration tests for arca-cert REST and MCP."""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from src.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
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


def test_mcp_dossier_generate(client):
    response = client.post("/mcp/tools/dossier-generate", json={
        "target": "arca-exchange", "scores": SCORES, "evidence": EVIDENCE})
    assert response.status_code == 200
    assert response.json()["dossier_id"]


def test_mcp_evidence_collect(client):
    built = client.post("/api/v1/dossiers", json={
        "target": "arca-studio", "scores": SCORES, "evidence": EVIDENCE}).json()
    rid = built["dossier"]["id"]
    response = client.post("/mcp/tools/evidence-collect", json={"dossier_id": rid})
    assert response.status_code == 200
    assert response.json()["evidence"]
