"""Unit tests for ArcaQ PROV-O trace integration in arca-cert."""
import pytest

from src.core.domain.cert_models import CertificationDossier, EvidenceRef, ScoreInput
from src.core.domain.provenance import ProvenanceTraceRef
from src.core.services.cert_service import CertService
from src.core.services.evidence_binder_assembler import EvidenceBinderAssembler
from src.infra.provenance_consumer import ProvenanceTraceConsumer
from src.infra.store import SqlCertRepository, connect_sqlite


@pytest.fixture
def repo():
    return SqlCertRepository(connect_sqlite())


def test_trace_ref_roundtrip(repo):
    ref = ProvenanceTraceRef(
        target="arca-flow",
        trace_id="trace-1",
        activity="prov:wasGeneratedBy",
        trace_uri="https://arcaq.internal/traces/trace-1",
    )
    repo.save_provenance_trace_ref(ref)
    loaded = repo.list_provenance_trace_refs("arca-flow")
    assert len(loaded) == 1
    assert loaded[0].trace_id == "trace-1"
    assert loaded[0].activity == "prov:wasGeneratedBy"


def test_evidence_binder_includes_trace_refs(repo):
    ref = ProvenanceTraceRef(
        target="arca-flow",
        trace_id="trace-2",
        activity="prov:used",
        trace_uri="https://arcaq.internal/traces/trace-2",
    )
    repo.save_provenance_trace_ref(ref)

    dossier = CertificationDossier(
        target="arca-flow",
        scores=[ScoreInput(dimension="security", value=0.9)],
        evidence=[EvidenceRef(source="trust", ref_id="r1")],
    )
    repo.save_dossier(dossier)

    assembler = EvidenceBinderAssembler(repo)
    binder = assembler.assemble(dossier)

    prov_evidence = [e for e in binder.evidence if e.source == "arcaq.prov-o"]
    assert len(prov_evidence) == 1
    assert prov_evidence[0].ref_id == "trace-2"
    assert "prov:used" in prov_evidence[0].description


def test_consumer_inject_stores_trace_ref(repo):
    consumer = ProvenanceTraceConsumer(repo)
    consumer.inject({
        "trace_id": "trace-3",
        "target": "arca-studio",
        "activity": "prov:wasAttributedTo",
        "trace_uri": "https://arcaq.internal/traces/trace-3",
    })
    refs = repo.list_provenance_trace_refs("arca-studio")
    assert len(refs) == 1
    assert refs[0].trace_id == "trace-3"


def test_consumer_ignores_malformed_trace(repo):
    consumer = ProvenanceTraceConsumer(repo)
    consumer.inject({"trace_id": "trace-4"})  # missing target
    assert repo.list_provenance_trace_refs("arca-studio") == []


def test_consumer_accepts_envelope(repo):
    consumer = ProvenanceTraceConsumer(repo)
    consumer.inject({
        "event_id": "evt-1",
        "correlation_id": "corr-1",
        "occurred_at": "2026-09-05T12:00:00+00:00",
        "payload": {
            "trace_id": "trace-5",
            "target": "arca-hub",
            "activity": "prov:wasInformedBy",
        },
    })
    refs = repo.list_provenance_trace_refs("arca-hub")
    assert len(refs) == 1
    assert refs[0].trace_id == "trace-5"


def test_build_package_includes_provenance_refs(repo):
    consumer = ProvenanceTraceConsumer(repo)
    consumer.inject({
        "trace_id": "trace-6",
        "target": "supplier-x",
        "activity": "prov:used",
        "trace_uri": "https://arcaq.internal/traces/trace-6",
    })

    service = CertService(repo)
    package = service.build_package(
        target="supplier-x",
        scores=[{"dimension": "supplier-risk", "value": 0.85}],
        evidence=[{"source": "trust", "ref_id": "r1"}],
    )

    binder = package["binder"]
    prov_evidence = [e for e in binder["evidence"] if e["source"] == "arcaq.prov-o"]
    assert len(prov_evidence) == 1
    assert prov_evidence[0]["ref_id"] == "trace-6"
