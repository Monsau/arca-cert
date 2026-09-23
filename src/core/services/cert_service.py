"""Certification application service (ADR-001, ADR-003, ADR-004, ADR-009).

Facade that orchestrates the specialised cert services:
- CertificationPackageBuilder
- EvidenceBinderAssembler
- ReadinessAssessor
- RemediationPlanner

Every mutation is routed through the embedded SOC via ``audit_operation``
(same wiring as arca-bench): audit events, traces and escalation on security
signals (seal failure, OOC denial, revocation). No telemetry bypass allowed.
"""
import contextlib

from ...config import settings
from ...infra.soc import EmbeddedSOC, audit_operation
from ..domain.cert_models import CertificationDossier, DossierStatus
from ..events.cert_events import (
    OutboxPublisher,
    asset_published,
    dossier_built,
    dossier_published,
    dossier_revoked,
)
from .certification_package_builder import CertificationPackageBuilder
from .evidence_binder_assembler import EvidenceBinderAssembler
from .readiness_assessor import ReadinessAssessor
from .remediation_planner import RemediationPlanner
from ...infra.ooc_client import OOCGateClient, OOCNotApprovedError, build_ooc_gate_client
from ...infra.vault import Signer, get_signer


class CertService:
    def __init__(self, repository, publisher: OutboxPublisher | None = None,
                 collector=None, ooc_client: OOCGateClient | None = None,
                 signer: Signer | None = None, soc: EmbeddedSOC | None = None):
        self._repo = repository
        self._publisher = publisher or OutboxPublisher()
        self._collector = collector
        # Full SOC wiring (ADR-009): when provided, mutations are audited
        # through audit_operation and security signals trigger responder
        # escalation, same pattern as arca-bench.
        self._soc = soc
        self._ooc_client = ooc_client if ooc_client is not None else build_ooc_gate_client()
        self._signer = signer if signer is not None else get_signer()
        self._package_builder = CertificationPackageBuilder(
            repository, publisher, collector
        )
        self._binder_asm = EvidenceBinderAssembler(repository, publisher, collector)
        self._assessor = ReadinessAssessor(repository, publisher, collector)
        self._remediation = RemediationPlanner(repository, publisher, collector)

    def _audit(self, operation: str, correlation_id: str,
               entity_type: str = None, entity_id: str = None):
        """Audit context for mutations; no-op when no SOC is wired."""
        if self._soc is not None:
            return audit_operation(self._soc, operation, correlation_id,
                                   entity_type, entity_id)
        return contextlib.nullcontext()

    # -- backward-compatible dossier helpers ----------------------------------

    def build_dossier(self, target: str, scores: list, evidence: list,
                      threshold: float = 0.7) -> tuple:
        with self._audit("build_dossier", correlation_id=f"dossier:{target}",
                         entity_type="target", entity_id=target):
            package = self._package_builder.build_package(
                target=target, scores=scores, evidence=evidence, threshold=threshold
            )
            self._publisher.publish(dossier_built(package.dossier))
            plan = self._remediation.get_plan(package.dossier.id)
            return package.dossier, plan

    def _sealer(self):
        key = settings.vault_transit_key
        return lambda payload: self._signer.sign(key, payload)

    def _verifier(self):
        key = settings.vault_transit_key
        return lambda payload, signature: self._signer.verify(key, payload, signature)

    def publish_dossier(self, dossier_id: str, reviewer: str, version: str | None = None) -> CertificationDossier:
        with self._audit("publish_dossier", correlation_id=dossier_id,
                         entity_type="dossier", entity_id=dossier_id):
            dossier = self._repo.get_dossier(dossier_id)
            if dossier is None:
                raise LookupError(f"dossier {dossier_id} not found")
            if not self._ooc_client.is_approved(dossier.target, version):
                # OOC gate denial is a security-relevant event: escalate.
                if self._soc:
                    self._soc.responder.escalate(
                        dossier_id, "medium")
                raise OOCNotApprovedError(
                    f"dossier {dossier_id}: no approved OOC for target {dossier.target}"
                )
            dossier.publish(reviewer, sealer=self._sealer())
            self._repo.save_dossier(dossier)
            self._publisher.publish(dossier_published(dossier))
            package_id = dossier.id
            self._publisher.publish(asset_published(dossier, package_id))
            if self._collector:
                self._collector.collect_event(
                    "dossier.published",
                    {"dossier_id": dossier_id, "reviewer": reviewer,
                     "seal": dossier.seal},
                    correlation_id=dossier_id,
                )
            # Fail-closed seal check: a broken seal on a published dossier is
            # escalated immediately (same escalation pattern as arca-bench
            # run-completion anomaly handling).
            if self._soc:
                if not dossier.verify_seal():
                    self._soc.collector.collect_event(
                        "seal.failure",
                        {"dossier_id": dossier_id, "value": 1.0},
                        correlation_id=dossier_id,
                    )
                anomalies = self._soc.analyzer.detect_anomaly("seal.failure", 0.0)
                if anomalies:
                    self._soc.responder.escalate(dossier_id, "high")
            return dossier

    def revoke_dossier(self, dossier_id: str, reviewer: str, reason: str) -> CertificationDossier:
        with self._audit("revoke_dossier", correlation_id=dossier_id,
                         entity_type="dossier", entity_id=dossier_id):
            dossier = self._repo.get_dossier(dossier_id)
            if dossier is None:
                raise LookupError(f"dossier {dossier_id} not found")
            dossier.revoke(reviewer, reason)
            self._repo.save_dossier(dossier)
            self._publisher.publish(dossier_revoked(dossier))
            if self._collector:
                self._collector.collect_event(
                    "dossier.revoked",
                    {"dossier_id": dossier_id, "reviewer": reviewer, "reason": reason},
                    correlation_id=dossier_id,
                )
            # Revoking a published dossier is a high-severity event.
            if self._soc:
                self._soc.responder.escalate(dossier_id, "high")
            return dossier

    def get_dossier(self, dossier_id: str):
        return self._repo.get_dossier(dossier_id)

    def list_dossiers(self, target: str | None = None) -> list:
        return self._repo.list_dossiers(target=target)

    def get_remediation(self, dossier_id: str):
        return self._repo.get_remediation(dossier_id)

    # -- package oriented API -------------------------------------------------

    def build_package(self, target: str, scores: list, evidence: list,
                      threshold: float = 0.7, valid_days: int = 90) -> dict:
        with self._audit("build_package", correlation_id=f"package:{target}",
                         entity_type="target", entity_id=target):
            package = self._package_builder.build_package(
                target, scores, evidence, threshold, valid_days
            )
            return package.to_dict()

    def get_package(self, package_id: str) -> dict | None:
        package = self._package_builder.get_package(package_id)
        return package.to_dict() if package else None

    def list_packages(self, target: str | None = None) -> list:
        return [p.to_dict() for p in self._package_builder.list_packages(target=target)]

    # -- evidence / readiness -------------------------------------------------

    def assemble_evidence(self, dossier_id: str, additional_refs: list | None = None):
        dossier = self._repo.get_dossier(dossier_id)
        if dossier is None:
            raise LookupError(f"dossier {dossier_id} not found")
        binder = self._binder_asm.assemble(dossier, additional_refs)
        return binder.to_dict()

    def get_evidence_binder(self, dossier_id: str) -> dict | None:
        binder = self._binder_asm.get_binder(dossier_id)
        return binder.to_dict() if binder else None

    def assess_readiness(self, target: str, scores: list, threshold: float = 0.7) -> dict:
        assessment = self._assessor.assess(target, scores, threshold)
        return assessment.to_dict()

    def get_readiness(self, assessment_id: str) -> dict | None:
        assessment = self._assessor.get_assessment(assessment_id)
        return assessment.to_dict() if assessment else None

    def list_readiness(self, target: str | None = None) -> list:
        return [a.to_dict() for a in self._assessor.list_assessments(target=target)]

    # -- audit helper ---------------------------------------------------------

    def audit(self, event_type: str, payload: dict, correlation_id: str):
        if self._collector:
            self._collector.collect_event(event_type, payload, correlation_id)
