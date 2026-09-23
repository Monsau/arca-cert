"""UI-route tests for the embedded cert module UI (mounted at /cert).

The UI is static (index.html + app.js + shared skin), so these tests pin:
- the static mount serves the shell and assets;
- the shell contains the real views (dossiers explorer, create form) and no
  dead panels (the removed SOC/readiness placeholders);
- app.js wires only endpoints that actually exist and keeps the
  transclusion base contract;
- the endpoints the JS calls return the shapes the renderer consumes.
"""
import os
import re

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import src.main  # noqa: E402
from src.main import app  # noqa: E402

UI_DIR = os.path.join(os.path.dirname(src.main.__file__), "ui")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def authed_client(dev_token):
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {dev_token}"
        yield c


def _ui_file(name):
    return os.path.join(UI_DIR, name)


def test_ui_index_served(client):
    response = client.get("/cert/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="dossiers-view"' in response.text
    assert 'id="dossier-detail"' in response.text
    assert 'id="create-form"' in response.text


def test_ui_assets_served(client):
    for asset in ("app.js", "arcasuite-ui.css", "styles.css"):
        response = client.get(f"/cert/{asset}")
        assert response.status_code == 200, asset


def test_ui_has_no_dead_panels():
    index = open(_ui_file("index.html"), encoding="utf-8").read()
    # The SOC collector is not exposed over HTTP and readiness has no list
    # endpoint — those placeholder panels were removed, not hidden.
    assert "soc-view" not in index
    assert "readiness-view" not in index
    assert "packages-view" not in index


def test_app_js_keeps_transclusion_contract():
    js = open(_ui_file("app.js"), encoding="utf-8").read()
    assert "window.__ARCA_MODULE_BASE__" in js
    assert re.search(r"/m/\(\[\^/\]\+\)/|/m/'\s*\+\s*_pm\[1\]\s*\+\s*'/", js) or "/m/" in js


def test_app_js_wires_existing_endpoints(authed_client):
    js = open(_ui_file("app.js"), encoding="utf-8").read()
    # Every API path the JS fetches must be a registered route. `${query}`
    # appends ?target=… (or nothing), so it is dropped before the check.
    paths = set(re.findall(r"\$\{API\}(/[a-z0-9{}$\-\/.]+)`", js))
    for path in paths:
        rendered = re.sub(r"\$\{query\}", "", path)
        rendered = re.sub(r"\$\{[^}]+\}", "x", rendered)
        # /dossiers/{id} and /dossiers/{id}/remediation with any id value.
        candidate = rendered.replace("x", "00000000-0000-0000-0000-000000000000")
        response = authed_client.get(f"/api/v1{candidate}")
        assert response.status_code != 404, f"app.js calls missing route: {path}"


def test_ui_api_shapes(authed_client):
    """The JSON shapes the JS renderer consumes, verified end to end."""
    built = authed_client.post("/api/v1/dossiers", json={
        "target": "arca-ui-shape",
        "scores": [{"dimension": "security", "value": 0.9}],
        "evidence": [{"source": "trust", "ref_id": "r1"}],
    }).json()
    dossier_id = built["dossier"]["id"]

    listing = authed_client.get("/api/v1/dossiers").json()
    assert isinstance(listing["dossiers"], list)
    listed = next(d for d in listing["dossiers"] if d["id"] == dossier_id)
    for key in ("id", "target", "status", "scores", "evidence", "valid_until"):
        assert key in listed, key

    detail = authed_client.get(f"/api/v1/dossiers/{dossier_id}").json()
    assert detail["target"] == "arca-ui-shape"
    assert detail["status"] == "draft"

    remediation = authed_client.get(
        f"/api/v1/dossiers/{dossier_id}/remediation").json()
    assert remediation["dossier_id"] == dossier_id
    assert isinstance(remediation["items"], list)


def test_ui_list_empty_state_shape(authed_client):
    # Fresh module: the list endpoint returns an empty collection; the UI
    # renders an explanatory empty state instead of a blank panel.
    response = authed_client.get("/api/v1/dossiers",
                                 params={"target": "no-such-target"})
    assert response.status_code == 200
    assert response.json() == {"dossiers": []}
