"""Shared test configuration for arca-cert."""
import os

import pytest

os.environ.setdefault("CERT_AUTH_DISABLED", "true")
os.environ.setdefault("CERT_JWT_SECRET", "test-secret")


@pytest.fixture
def dev_token():
    from src.policies.oidc import mint_dev_token
    return mint_dev_token("test-user", ["cert-admin"], "test-secret")
