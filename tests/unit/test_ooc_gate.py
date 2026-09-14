"""Unit tests for the OOC governance gate in CertService."""
import pytest

from src.core.domain.cert_models import CertificationDossier, DossierStatus, EvidenceRef, ScoreInput
from src.core.events.cert_events import OutboxPublisher
from src.core.services.cert_service import CertService
from src.infra.ooc_client import OOCGateClient, OOCNotApprovedError
from src.infra.store import SqlCertRepository, connect_sqlite


class _ApprovedOOCGateClient:
    def is_approved(self, target: str, version: str | None = None) -> bool:
        return True


class _RejectedOOCGateClient:
    def __init__(self, expected_version: str | None = None):
        self._expected_version = expected_version

    def is_approved(self, target: str, version: str | None = None) -> bool:
        if self._expected_version is not None:
            assert version == self._expected_version
        return False


def _build_draft(service: CertService) -> CertificationDossier:
    dossier, _ = service.build_dossier(
        target="supplier-x",
        scores=[{"dimension": "confidence", "value": 0.9}],
        evidence=[{"source": "trust", "ref_id": "r1"}],
        threshold=0.7,
    )
    return dossier


def test_publish_allowed_when_ooc_approved():
    repo = SqlCertRepository(connect_sqlite())
    publisher = OutboxPublisher()
    svc = CertService(repo, publisher=publisher, ooc_client=_ApprovedOOCGateClient())
    dossier = _build_draft(svc)

    published = svc.publish_dossier(dossier.id, "auditor-1")

    assert published.status is DossierStatus.PUBLISHED
    assert any(e.topic == "cert.dossier.published" for e in publisher.drain())


def test_publish_blocked_when_ooc_rejected():
    repo = SqlCertRepository(connect_sqlite())
    publisher = OutboxPublisher()
    svc = CertService(repo, publisher=publisher, ooc_client=_RejectedOOCGateClient())
    dossier = _build_draft(svc)

    with pytest.raises(OOCNotApprovedError):
        svc.publish_dossier(dossier.id, "auditor-1")

    # dossier must remain draft and no publication event emitted
    loaded = svc.get_dossier(dossier.id)
    assert loaded.status is DossierStatus.DRAFT
    assert not any(e.topic == "cert.dossier.published" for e in publisher.drain())


def test_publish_uses_version_when_provided():
    repo = SqlCertRepository(connect_sqlite())
    publisher = OutboxPublisher()
    ooc = _RejectedOOCGateClient(expected_version="v2.3")
    svc = CertService(repo, publisher=publisher, ooc_client=ooc)
    dossier = _build_draft(svc)

    with pytest.raises(OOCNotApprovedError):
        svc.publish_dossier(dossier.id, "auditor-1", version="v2.3")


def test_ooc_disabled_defaults_to_null_gate():
    repo = SqlCertRepository(connect_sqlite())
    publisher = OutboxPublisher()
    svc = CertService(repo, publisher=publisher)
    dossier = _build_draft(svc)

    published = svc.publish_dossier(dossier.id, "auditor-1")
    assert published.status is DossierStatus.PUBLISHED
