"""Unit tests for arca-cert domain and services."""
import pytest

from src.core.domain.cert_models import (
    BenchResult,
    CertificationDossier,
    DossierStatus,
    EvidenceRef,
    ReadinessAssessment,
    ReadinessLevel,
    RemediationItem,
    ScoreInput,
)
from src.core.events.cert_events import OutboxPublisher
from src.core.services.cert_service import CertService
from src.core.services.certification_package_builder import CertificationPackageBuilder
from src.core.services.evidence_binder_assembler import EvidenceBinderAssembler
from src.core.services.readiness_assessor import ReadinessAssessor
from src.core.services.remediation_planner import RemediationPlanner
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


def test_revoke_dossier():
    d = CertificationDossier(
        target="x",
        scores=[ScoreInput(dimension="c", value=0.9)],
        evidence=[])
    d.publish("auditor-1")
    d.revoke("auditor-1", "compromised evidence")
    assert d.status is DossierStatus.REVOKED
    assert d.seal is None


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


def test_readiness_assessment_level():
    a = ReadinessAssessment(
        target="x",
        dimension_scores=[
            ScoreInput(dimension="security", value=0.9),
            ScoreInput(dimension="compliance", value=0.5),
        ],
        threshold=0.7,
    )
    assert a.level is ReadinessLevel.CONDITIONAL
    assert a.failing_dimensions() == ["compliance"]


def test_bench_result_validation():
    with pytest.raises(ValueError):
        BenchResult(bench_id="b1", target="x", dimension="d", passed=True, score=1.5)


def test_certification_package_builder():
    repo = SqlCertRepository(connect_sqlite())
    builder = CertificationPackageBuilder(repo)
    package = builder.build_package(
        target="arca-flow",
        scores=[{"dimension": "security", "value": 0.85}],
        evidence=[{"source": "trust", "ref_id": "r1"}],
    )
    assert package.dossier.status is DossierStatus.DRAFT
    assert package.assessment.level is ReadinessLevel.READY
    loaded = builder.get_package(package.id)
    assert loaded is not None
    assert loaded.dossier.target == "arca-flow"


def test_evidence_binder_assembler():
    repo = SqlCertRepository(connect_sqlite())
    dossier = CertificationDossier(
        target="x",
        scores=[ScoreInput(dimension="s", value=0.9)],
        evidence=[EvidenceRef(source="a", ref_id="r1")],
    )
    repo.save_dossier(dossier)
    asm = EvidenceBinderAssembler(repo)
    binder = asm.assemble(dossier, [{"source": "bench", "ref_id": "r2"}])
    assert len(binder.evidence) == 2
    assert binder.to_dict()["count"] == 2


def test_readiness_assessor():
    repo = SqlCertRepository(connect_sqlite())
    svc = ReadinessAssessor(repo)
    assessment = svc.assess("target-x", [{"dimension": "a", "value": 0.9}])
    assert assessment.level is ReadinessLevel.READY
    assert svc.get_assessment(assessment.id) is not None


def test_remediation_planner():
    repo = SqlCertRepository(connect_sqlite())
    dossier = CertificationDossier(
        target="x",
        scores=[ScoreInput(dimension="security", value=0.5)],
        evidence=[],
    )
    planner = RemediationPlanner(repo)
    plan = planner.create_plan(dossier, threshold=0.7)
    assert len(plan.items) == 1
    assert plan.items[0].dimension == "security"


def test_bench_result_consumer_inject_builds_package():
    from src.infra.kafka import BenchResultConsumer

    repo = SqlCertRepository(connect_sqlite())
    svc = CertService(repo)
    consumer = BenchResultConsumer(svc, topic="bench.results")
    consumer.inject({
        "bench_id": "b1",
        "target": "supplier-x",
        "dimension": "supplier-risk",
        "passed": True,
        "score": 0.85,
        "evidence": [],
    })
    packages = svc.list_packages()
    assert len(packages) == 1
    assert packages[0]["dossier"]["target"] == "supplier-x"
