"""Contract conformance tests — verify contract artifacts and basic endpoints."""
import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from src.main import app

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_openapi_contract_parses():
    doc = yaml.safe_load((CONTRACTS / "rest" / "openapi.yaml").read_text(encoding="utf-8"))
    assert doc.get("openapi", "").startswith("3.")
    assert doc.get("paths")


def test_graphql_sdl_nonempty():
    sdl = (CONTRACTS / "graphql" / "schema.graphql").read_text(encoding="utf-8")
    assert "type Query" in sdl


def test_mcp_capabilities_valid_json():
    caps = json.loads((CONTRACTS / "mcp" / "capabilities.json").read_text(encoding="utf-8"))
    assert caps.get("capabilities")


def test_kafka_avsc_parses():
    json.loads((CONTRACTS / "kafka" / "events.avsc").read_text(encoding="utf-8"))


def test_health_endpoint_responds(client):
    for path in ("/health", "/healthz"):
        resp = client.get(path)
        if resp.status_code in (200, 401, 403):
            break
    else:
        pytest.fail("no health endpoint responded")
    if resp.status_code == 200:
        body = resp.json()
        assert body.get("status") in ("ok", "ready")
