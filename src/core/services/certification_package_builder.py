"""Certification package builder service (ADR-001, ADR-009).

Builds a sealed certification package from a dossier, readiness assessment,
evidence binder and remediation plan.
"""
from ..domain.cert_models import CertificationDossier, CertificationPackage, EvidenceRef, ScoreInput
from ..events.cert_events import OutboxPublisher, package_created
from .evidence_binder_assembler import EvidenceBinderAssembler
from .readiness_assessor import ReadinessAssessor
from .remediation_planner import RemediationPlanner


def _normalize_scores(scores: list) -> list:
    return [ScoreInput(**s) if isinstance(s, dict) else s for s in scores]


def _normalize_evidence(evidence: list) -> list:
    return [EvidenceRef(**e) if isinstance(e, dict) else e for e in evidence]


class CertificationPackageBuilder:
    def __init__(self, repository, publisher: OutboxPublisher | None = None,
                 collector=None):
        self._repo = repository
        self._publisher = publisher or OutboxPublisher()
        self._collector = collector
        self._assessor = ReadinessAssessor(repository, publisher, collector)
        self._binder_asm = EvidenceBinderAssembler(repository, publisher, collector)
        self._remediation = RemediationPlanner(repository, publisher, collector)

    def build_package(self, target: str, scores: list, evidence: list,
                      threshold: float = 0.7, valid_days: int = 90) -> CertificationPackage:
        if not target or not scores:
            raise ValueError("target and at least one score are required")
        score_objs = _normalize_scores(scores)
        evidence_objs = _normalize_evidence(evidence or [])
        dossier = CertificationDossier(
            target=target, scores=score_objs, evidence=evidence_objs, valid_days=valid_days
        )
        self._repo.save_dossier(dossier)
        if self._collector:
            self._collector.collect_event(
                "dossier.created",
                {"dossier_id": dossier.id, "target": target, "status": dossier.status.value},
                correlation_id=dossier.id,
            )

        assessment = self._assessor.assess(target, dossier.scores, threshold)
        binder = self._binder_asm.assemble(dossier)
        plan = self._remediation.create_plan(dossier, threshold)

        package = CertificationPackage(
            dossier=dossier,
            assessment=assessment,
            binder=binder,
            remediation_id=plan.id,
        )
        self._repo.save_package(package)
        self._publisher.publish(package_created(package))
        if self._collector:
            self._collector.collect_event(
                "package.created",
                {"package_id": package.id, "dossier_id": dossier.id, "target": target},
                correlation_id=dossier.id,
            )
        return package

    def get_package(self, package_id: str) -> CertificationPackage | None:
        return self._repo.get_package(package_id)

    def get_package_by_dossier(self, dossier_id: str) -> CertificationPackage | None:
        return self._repo.get_package_by_dossier(dossier_id)

    def list_packages(self, target: str | None = None) -> list:
        return self._repo.list_packages(target=target)
