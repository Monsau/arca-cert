"""Vault-backed signing tests for Arca Cert dossiers."""
import pytest

from src.config import settings
from src.core.domain.cert_models import CertificationDossier, DossierStatus, EvidenceRef, ScoreInput
from src.infra.vault import DevSigner, get_signer


def test_dev_signer_roundtrip():
    signer = DevSigner(secret=b"test-secret")
    payload = b"canonical dossier bytes"
    signature = signer.sign("dossier-key", payload)
    assert signature.startswith("hmac-sha256:")
    assert signer.verify("dossier-key", payload, signature)
    assert not signer.verify("dossier-key", payload, signature + "x")
    assert not signer.verify("other-key", payload, signature)


def test_dev_signer_blocked_in_production(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "signer_backend", "dev")
    with pytest.raises(RuntimeError, match="not allowed outside dev/test"):
        get_signer()


def test_dossier_publish_with_dev_signer():
    dossier = CertificationDossier(
        target="arca-flow",
        scores=[ScoreInput(dimension="confidence", value=0.9)],
        evidence=[EvidenceRef(source="trust", ref_id="r1")],
    )
    signer = DevSigner(secret=b"test-secret")
    sealer = lambda payload: signer.sign("dossier-key", payload)
    verifier = lambda payload, signature: signer.verify("dossier-key", payload, signature)
    dossier.publish("auditor-1", sealer=sealer)
    assert dossier.status is DossierStatus.PUBLISHED
    assert dossier.seal.startswith("hmac-sha256:")
    assert dossier.verify_seal(verifier=verifier)
    dossier.scores = [ScoreInput(dimension="confidence", value=0.5)]
    assert not dossier.verify_seal(verifier=verifier)
