"""Certification application service (ADR-001, ADR-003, ADR-004).

Builds dossiers from score inputs and evidence references, generates
remediation plans for failing dimensions, and publishes sealed dossiers.
"""
from ..domain.cert_models import (
    CertificationDossier,
    EvidenceRef,
    RemediationItem,
    RemediationPlan,
    ScoreInput,
)
from ..events.cert_events import (
    OutboxPublisher,
    dossier_built,
    dossier_published,
    remediation_issued,
)


class CertService:
    def __init__(self, repository, publisher: OutboxPublisher | None = None):
        self._repo = repository
        self._publisher = publisher or OutboxPublisher()

    def build_dossier(self, target: str, scores: list, evidence: list,
                      threshold: float = 0.7) -> tuple:
        if not target or not scores:
            raise ValueError("target and at least one score are required")
        score_objs = [ScoreInput(**s) for s in scores]
        evidence_objs = [EvidenceRef(**e) for e in evidence]
        dossier = CertificationDossier(
            target=target, scores=score_objs, evidence=evidence_objs)
        self._repo.save_dossier(dossier)
        self._publisher.publish(dossier_built(dossier))
        plan = self._build_remediation(dossier, threshold)
        self._repo.save_remediation(plan)
        self._publisher.publish(remediation_issued(plan))
        return dossier, plan

    def publish_dossier(self, dossier_id: str, reviewer: str) -> CertificationDossier:
        dossier = self._repo.get_dossier(dossier_id)
        if dossier is None:
            raise LookupError(f"dossier {dossier_id} not found")
        dossier.publish(reviewer)
        self._repo.save_dossier(dossier)
        self._publisher.publish(dossier_published(dossier))
        return dossier

    def get_dossier(self, dossier_id: str):
        return self._repo.get_dossier(dossier_id)

    def list_dossiers(self, target: str | None = None) -> list:
        return self._repo.list_dossiers(target=target)

    def get_remediation(self, dossier_id: str):
        return self._repo.get_remediation(dossier_id)

    # -- internals ------------------------------------------------------------

    def _build_remediation(self, dossier: CertificationDossier,
                           threshold: float) -> RemediationPlan:
        items = []
        for dim in dossier.failing_dimensions(threshold):
            items.append(RemediationItem(
                risk=f"{dim} score below {threshold}",
                action=f"Investigate and improve {dim} controls",
                owner="domain-owner"))
        return RemediationPlan(dossier_id=dossier.id, items=items)
