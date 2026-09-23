"""Security: /docs, /redoc and /openapi.json are anonymous API-surface
disclosure on the direct ingress.

Zero Trust / defense-in-depth: outside dev/standalone these metadata
endpoints require a valid Keycloak JWT through the module JWKS/RS256 stack
(ADR-009); in dev they stay open (module dev-gate convention). Health
endpoints stay open for k8s probes. Tests mint real RS256 tokens so they
exercise the same strict validation path as production (no bypass).
"""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from src.config import settings  # noqa: E402
from src.main import app  # noqa: E402
from src.policies import oidc as cert_oidc  # noqa: E402
from tests.oidc_test_utils import (  # noqa: E402
    generate_keypair,
    install_test_jwks,
    mint_test_token,
)

_PRIVATE_KEY, _ = generate_keypair()

client = TestClient(app)

DOCS_PATHS = ("/openapi.json", "/docs", "/redoc")


@pytest.fixture
def docs_key():
    """Install this module's test key in the JWKS cache for the duration of
    a test, then restore the previous entries (conftest installs its own key
    in the same cache slot, and the app state may already cache a validator
    built from it)."""
    previous_jwks = cert_oidc._JWKS_CACHE.get("test-jwks")
    previous_validator = getattr(app.state, "oidc_validator", None)
    install_test_jwks(_PRIVATE_KEY)
    if hasattr(app.state, "oidc_validator"):
        del app.state.oidc_validator
    yield
    if previous_jwks is None:
        cert_oidc._JWKS_CACHE.pop("test-jwks", None)
    else:
        cert_oidc._JWKS_CACHE["test-jwks"] = previous_jwks
    if previous_validator is None:
        app.state.__dict__.pop("oidc_validator", None)
    else:
        app.state.oidc_validator = previous_validator


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")


@pytest.fixture
def dev(monkeypatch):
    monkeypatch.setattr(settings, "environment", "dev")


def _auth_headers() -> dict:
    token = mint_test_token(_PRIVATE_KEY, "docs-tester", ["cert-reader"])
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("path", DOCS_PATHS)
def test_metadata_anonymous_is_rejected_in_production(path, production, docs_key):
    response = client.get(path)
    assert response.status_code == 401


@pytest.mark.parametrize("path", DOCS_PATHS)
def test_metadata_invalid_token_is_rejected_in_production(path, production, docs_key):
    response = client.get(path, headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


@pytest.mark.parametrize("path", DOCS_PATHS)
def test_metadata_valid_token_is_served_in_production(path, production, docs_key):
    response = client.get(path, headers=_auth_headers())
    assert response.status_code == 200


def test_openapi_schema_content_served_with_token_in_production(production, docs_key):
    response = client.get("/openapi.json", headers=_auth_headers())
    assert response.status_code == 200
    assert response.json()["info"]["title"] == settings.app_name


@pytest.mark.parametrize("path", DOCS_PATHS)
def test_metadata_stays_open_in_dev(path, dev, docs_key):
    response = client.get(path)
    assert response.status_code == 200


def test_health_stays_open_in_production(production, docs_key):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
