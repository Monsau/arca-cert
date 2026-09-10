"""Unit tests for arca-cert."""
import pytest

from src.core.domain.cert_models import (
    CertificationDossier,
    DossierStatus,
    EvidenceRef,
    RemediationItem,
    ScoreInput,
)
from src.core.events.cert_events import OutboxPublisher
from src.core.services.cert_service import CertService
from src.infra.store import SqlCertRepository, connect_sqlite


@pytest.fixture
def service():
    repo = SqlCertRepository(connect_sqlite())
    publisher = OutboxPublisher()
    return CertService(repo, publisher), publisher


def test_dossier_seal():
    d = CertificationDossier(
        target="arca-flow",
        scores=[ScoreInput(dimension="confidence", value=0.9)],
        evidence=[EvidenceRef(source="trust", ref_id="r1")])
    d.publish("auditor-1")
    assert d.verify_seal()
    d.scores = [ScoreInput(dimension="confidence", value=0.5)]
    assert not d.verify_seal()


def test_publish_requires_reviewer():
    d = CertificationDossier(
        target="x",
        scores=[ScoreInput(dimension="c", value=0.9)],
        evidence=[])
    with pytest.raises(ValueError):
        d.publish("")


def test_build_and_publish(service):
    svc, publisher = service
    dossier, plan = svc.build_dossier(
        target="arca-flow",
        scores=[{"dimension": "confidence", "value": 0.9},
                {"dimension": "security", "value": 0.5}],
        evidence=[{"source": "trust", "ref_id": "r1"}],
        threshold=0.7)
    assert dossier.status is DossierStatus.DRAFT
    assert len(plan.items) == 1
    assert plan.items[0].risk == "security score below 0.7"
    published = svc.publish_dossier(dossier.id, "auditor-2")
    assert published.status is DossierStatus.PUBLISHED
    topics = [e.topic for e in publisher.drain()]
    assert "cert.dossier.built" in topics
    assert "cert.remediation.issued" in topics
    assert "cert.dossier.published" in topics


def test_failing_dimensions():
    d = CertificationDossier(
        target="x",
        scores=[ScoreInput(dimension="a", value=0.9),
                ScoreInput(dimension="b", value=0.5)],
        evidence=[])
    assert d.failing_dimensions(threshold=0.7) == ["b"]


def test_store_roundtrip():
    repo = SqlCertRepository(connect_sqlite())
    d = CertificationDossier(
        target="x",
        scores=[ScoreInput(dimension="a", value=0.8)],
        evidence=[EvidenceRef(source="s", ref_id="r")])
    repo.save_dossier(d)
    loaded = repo.get_dossier(d.id)
    assert loaded.target == d.target
    assert loaded.scores[0].dimension == "a"
