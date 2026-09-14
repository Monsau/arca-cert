"""Certification application service (ADR-001, ADR-003, ADR-004, ADR-009).

Facade that orchestrates the specialised cert services:
- CertificationPackageBuilder
- EvidenceBinderAssembler
- ReadinessAssessor
- RemediationPlanner

Backwards-compatible helpers for dossier/remain keep existing tests green.
"""
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


class CertService:
    def __init__(self, repository, publisher: OutboxPublisher | None = None,
                 collector=None):
        self._repo = repository
        self._publisher = publisher or OutboxPublisher()
        self._collector = collector
        self._package_builder = CertificationPackageBuilder(
            repository, publisher, collector
        )
        self._binder_asm = EvidenceBinderAssembler(repository, publisher, collector)
        self._assessor = ReadinessAssessor(repository, publisher, collector)
        self._remediation = RemediationPlanner(repository, publisher, collector)

    # -- backward-compatible dossier helpers ----------------------------------

    def build_dossier(self, target: str, scores: list, evidence: list,
                      threshold: float = 0.7) -> tuple:
        package = self._package_builder.build_package(
            target=target, scores=scores, evidence=evidence, threshold=threshold
        )
        self._publisher.publish(dossier_built(package.dossier))
        plan = self._remediation.get_plan(package.dossier.id)
        return package.dossier, plan

    def publish_dossier(self, dossier_id: str, reviewer: str) -> CertificationDossier:
        dossier = self._repo.get_dossier(dossier_id)
        if dossier is None:
            raise LookupError(f"dossier {dossier_id} not found")
        dossier.publish(reviewer)
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
        return dossier

    def revoke_dossier(self, dossier_id: str, reviewer: str, reason: str) -> CertificationDossier:
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
