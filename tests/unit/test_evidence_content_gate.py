"""Evidence content gate unit tests — certification package build path.

Proves that validatable evidence content is proven against the shared
validators service before a package may be built: violations (valid=false),
denials and degraded outcomes (including timeouts) raise
EvidenceValidationError and block the build; a disabled validators URL skips
content validation explicitly with a validation: "skipped" marker. Fakes
only — no network.
"""
import pytest

from src.core.domain.cert_models import EvidenceRef
from src.core.services.certification_package_builder import CertificationPackageBuilder
from src.core.services.evidence_content_gate import (
    EvidenceContentGate,
    EvidenceValidationError,
    classify_artifact,
)
from src.core.events.cert_events import OutboxPublisher
from src.infra.store import SqlCertRepository, connect_sqlite
from src.infra.validators import NullContentValidator, ValidationOutcome


class FakeValidator:
    """ContentValidator fake: queued outcomes per call, records every call."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []

    def validate_ontology(self, ttl, artifact_kind="ontology_ttl",
                          authorization=None, content_format=None):
        self.calls.append({
            "content": ttl,
            "artifact_kind": artifact_kind,
            "authorization": authorization,
            "content_format": content_format,
        })
        return self._outcomes.pop(0) if self._outcomes else ValidationOutcome(
            valid=True, status="valid"
        )


def _builder(gate):
    repo = SqlCertRepository(connect_sqlite())
    return CertificationPackageBuilder(
        repo, publisher=OutboxPublisher(), content_gate=gate
    ), repo


_SCORES = [{"dimension": "confidence", "value": 0.9}]


# -- classification -----------------------------------------------------------

def test_classify_ttl_by_extension_and_mime():
    assert classify_artifact(EvidenceRef(source="ooc", ref_id="model.ttl",
                                         content="<ttl>")) == ("ontology_ttl", None)
    assert classify_artifact(EvidenceRef(source="ooc", ref_id="m",
                                         content="<ttl>", mime="text/turtle")) == (
        "ontology_ttl", None)


def test_classify_json_manifest_with_content_format():
    assert classify_artifact(EvidenceRef(source="packs", ref_id="manifest.json",
                                         content="{}")) == ("ooc_manifest", "json")


def test_classify_yaml_manifest_and_workflow():
    assert classify_artifact(EvidenceRef(source="packs", ref_id="manifest.yaml",
                                         content="pack: x")) == ("ooc_manifest", "yaml")
    assert classify_artifact(EvidenceRef(source="flow", ref_id="wf.yml",
                                         content="steps:\n  - s1")) == (
        "workflow_yaml", None)


def test_classify_skips_reference_only_or_unknown_content():
    assert classify_artifact(EvidenceRef(source="trust", ref_id="r1")) is None
    assert classify_artifact(EvidenceRef(source="trust", ref_id="r1",
                                         content="plain text note")) is None


# -- gate semantics ------------------------------------------------------------

def test_gate_marks_skipped_when_disabled():
    ref = EvidenceRef(source="ooc", ref_id="model.ttl", content="<ttl>")
    gate = EvidenceContentGate(validator=NullContentValidator())
    gated = gate.gate([ref])
    assert gated[0].validation == "skipped"


def test_gate_marks_passed_and_forwards_authorization():
    ref = EvidenceRef(source="ooc", ref_id="model.ttl", content="<ttl>")
    validator = FakeValidator([ValidationOutcome(valid=True, status="valid")])
    gate = EvidenceContentGate(validator=validator, authorization="Bearer gate-tok")
    gated = gate.gate([ref], authorization="Bearer call-tok")
    assert gated[0].validation == "passed"
    assert validator.calls[0]["authorization"] == "Bearer call-tok"


def test_gate_is_fail_closed_on_degraded_and_denied():
    for status in ("degraded", "denied"):
        ref = EvidenceRef(source="ooc", ref_id="model.ttl", content="<ttl>")
        gate = EvidenceContentGate(
            validator=FakeValidator([ValidationOutcome(valid=False, status=status)])
        )
        with pytest.raises(EvidenceValidationError):
            gate.gate([ref])


# -- builder integration -------------------------------------------------------

def test_invalid_evidence_blocks_package_build():
    validator = FakeValidator(
        [ValidationOutcome(valid=False, status="invalid",
                           detail="shacl-contracts: missing fr label")]
    )
    builder, repo = _builder(EvidenceContentGate(validator=validator))

    with pytest.raises(EvidenceValidationError) as excinfo:
        builder.build_package(
            target="arca-flow",
            scores=_SCORES,
            evidence=[{"source": "ooc", "ref_id": "model.ttl", "content": "<bad ttl>"}],
            authorization="Bearer tok",
        )
    assert "model.ttl" in str(excinfo.value)
    assert "shacl-contracts" in str(excinfo.value)
    # Fail-closed before persistence: nothing was saved.
    assert repo.list_packages() == []
    assert validator.calls[0]["authorization"] == "Bearer tok"
    assert validator.calls[0]["artifact_kind"] == "ontology_ttl"


def test_valid_evidence_builds_package_and_records_passed():
    validator = FakeValidator([ValidationOutcome(valid=True, status="valid", checks=[])])
    builder, _ = _builder(EvidenceContentGate(validator=validator))

    package = builder.build_package(
        target="arca-flow",
        scores=_SCORES,
        evidence=[{"source": "ooc", "ref_id": "model.ttl", "content": "<ttl>"}],
    )
    assert package.dossier.evidence[0].validation == "passed"


def test_timeout_maps_to_degraded_and_blocks_build():
    validator = FakeValidator(
        [ValidationOutcome(valid=False, status="degraded",
                           detail="validators service unreachable: timed out")]
    )
    builder, _ = _builder(EvidenceContentGate(validator=validator))

    with pytest.raises(EvidenceValidationError) as excinfo:
        builder.build_package(
            target="arca-flow",
            scores=_SCORES,
            evidence=[{"source": "flow", "ref_id": "wf.yaml",
                       "content": "steps:\n  - s1"}],
        )
    assert "degraded" in str(excinfo.value)
    assert validator.calls[0]["artifact_kind"] == "workflow_yaml"


def test_disabled_adapter_marks_skipped_and_builds():
    builder, _ = _builder(EvidenceContentGate(validator=NullContentValidator()))

    package = builder.build_package(
        target="arca-flow",
        scores=_SCORES,
        evidence=[{"source": "ooc", "ref_id": "model.ttl", "content": "<ttl>"}],
    )
    entry = package.dossier.evidence[0]
    assert entry.validation == "skipped"
    assert entry.to_dict()["validation"] == "skipped"


def test_reference_only_evidence_untouched_when_disabled():
    builder, _ = _builder(EvidenceContentGate(validator=NullContentValidator()))

    package = builder.build_package(
        target="arca-flow",
        scores=_SCORES,
        evidence=[{"source": "trust", "ref_id": "r1"}],
    )
    entry = package.dossier.evidence[0]
    assert entry.validation == ""
    assert "validation" not in entry.to_dict()
