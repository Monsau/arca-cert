"""Shared test configuration for arca-cert."""
import os

import pytest

from tests.oidc_test_utils import (
    TEST_AUDIENCE,
    TEST_ISSUER,
    generate_keypair,
    install_test_jwks,
    mint_test_token,
)

os.environ.setdefault("CERT_OIDC_ISSUER", TEST_ISSUER)
os.environ.setdefault("CERT_OIDC_AUDIENCE", TEST_AUDIENCE)
os.environ.setdefault("CERT_KAFKA_CONSUME", "0")  # no broker in unit tests
os.environ.pop("CERT_AUTH_DISABLED", None)

_PRIVATE_KEY, _ = generate_keypair()
os.environ["CERT_OIDC_JWKS_URL"] = install_test_jwks(_PRIVATE_KEY)


@pytest.fixture
def dev_token():
    """A valid RS256 SSO access token for the test realm (roles: cert-admin)."""
    return mint_test_token(_PRIVATE_KEY, "test-user", ["cert-admin"])


@pytest.fixture
def auth_headers(dev_token):
    return {"Authorization": f"Bearer {dev_token}"}
