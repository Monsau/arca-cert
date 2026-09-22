"""Unit tests for arca-cert security layer."""
import pytest

from src.core.domain.cert_models import CertificationDossier, ScoreInput
from src.policies.abac import can_publish, can_revoke
from src.policies.oidc import OIDCValidator
from src.policies.rbac import Role, has_permission, require_permission

from tests.oidc_test_utils import (
    TEST_AUDIENCE,
    TEST_ISSUER,
    generate_keypair,
    install_test_jwks,
    mint_test_token,
)


def test_rbac_permissions():
    assert has_permission(Role.READER, "dossier:read")
    assert not has_permission(Role.READER, "dossier:create")
    assert has_permission(Role.ADMIN, "dossier:revoke")
    assert require_permission([Role.WRITER, Role.READER], "dossier:create")


def test_jwt_validation_rs256():
    """Tokens are verified against the realm JWKS — the same strict path as
    production, exercised with a generated test keypair (no bypass)."""
    private_key, jwk = generate_keypair()
    validator = OIDCValidator(
        issuer=TEST_ISSUER, audience=TEST_AUDIENCE, jwks=[jwk],
    )
    token = mint_test_token(private_key, "u1", ["cert-reader"])
    user = validator.validate(token)
    assert user.sub == "u1"
    assert "cert-reader" in user.roles


def test_jwt_validation_rejects_hs256():
    """Security by design: symmetric HS256 tokens are never accepted."""
    from jose import jwt as jose_jwt

    validator = OIDCValidator(issuer=TEST_ISSUER, audience=TEST_AUDIENCE,
                              jwks=[{"kty": "RSA", "kid": "k"}])
    hs_token = jose_jwt.encode({"sub": "u1", "roles": ["cert-admin"]},
                               "test-secret", algorithm="HS256")
    with pytest.raises(Exception):
        validator.validate(hs_token)


def test_abac_separation_of_duties():
    # A reviewer cannot publish a dossier where they are already recorded as reviewer.
    dossier = CertificationDossier(
        target="x",
        scores=[ScoreInput(dimension="s", value=0.9)],
        evidence=[],
        reviewer="alice",
    )
    allowed, reason = can_publish({"sub": "alice", "roles": ["cert-reviewer"]}, dossier)
    assert not allowed
    assert "cannot publish" in reason
    # Another reviewer can publish.
    dossier2 = CertificationDossier(
        target="y",
        scores=[ScoreInput(dimension="s", value=0.9)],
        evidence=[],
    )
    allowed, _ = can_publish({"sub": "bob", "roles": ["cert-reviewer"]}, dossier2)
    assert allowed


def test_abac_revoke_requires_admin():
    dossier = CertificationDossier(
        target="x",
        scores=[ScoreInput(dimension="s", value=0.9)],
        evidence=[],
    )
    dossier.publish("alice")
    allowed, reason = can_revoke({"sub": "bob", "roles": ["cert-reviewer"]}, dossier)
    assert not allowed
    assert "admin" in reason
    allowed, _ = can_revoke({"sub": "carol", "roles": ["cert-admin"]}, dossier)
    assert allowed
