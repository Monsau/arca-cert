"""Cert domain events (ADR-003, ADR-009)."""
from dataclasses import dataclass, field
from datetime import datetime, timezone

TOPIC_DOSSIER_BUILT = "cert.dossier.built"
TOPIC_DOSSIER_PUBLISHED = "cert.dossier.published"
TOPIC_DOSSIER_REVOKED = "cert.dossier.revoked"
TOPIC_REMEDIATION_ISSUED = "cert.remediation.issued"
TOPIC_EVIDENCE_BINDER_ASSEMBLED = "cert.evidence_binder.assembled"
TOPIC_READINESS_ASSESSED = "cert.readiness.assessed"
TOPIC_PACKAGE_CREATED = "cert.package.created"


@dataclass(frozen=True)
class DomainEvent:
    topic: str
    key: str
    payload: dict
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def dossier_built(dossier) -> DomainEvent:
    return DomainEvent(
        topic=TOPIC_DOSSIER_BUILT,
        key=dossier.id,
        payload={
            "dossier_id": dossier.id,
            "target": dossier.target,
            "built_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def dossier_published(dossier) -> DomainEvent:
    return DomainEvent(
        topic=TOPIC_DOSSIER_PUBLISHED,
        key=dossier.id,
        payload={
            "dossier_id": dossier.id,
            "reviewer": dossier.reviewer,
            "valid_until": dossier.valid_until.isoformat(),
            "seal": dossier.seal,
        },
    )


def dossier_revoked(dossier) -> DomainEvent:
    return DomainEvent(
        topic=TOPIC_DOSSIER_REVOKED,
        key=dossier.id,
        payload={
            "dossier_id": dossier.id,
            "reviewer": dossier.reviewer,
            "revoked_at": dossier.revoked_at.isoformat() if dossier.revoked_at else None,
            "reason": dossier.revocation_reason,
        },
    )


def remediation_issued(plan) -> DomainEvent:
    return DomainEvent(
        topic=TOPIC_REMEDIATION_ISSUED,
        key=plan.dossier_id,
        payload={
            "dossier_id": plan.dossier_id,
            "plan_id": plan.id,
            "item_count": len(plan.items),
            "issued_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def evidence_binder_assembled(binder) -> DomainEvent:
    return DomainEvent(
        topic=TOPIC_EVIDENCE_BINDER_ASSEMBLED,
        key=binder.dossier_id,
        payload={
            "binder_id": binder.id,
            "dossier_id": binder.dossier_id,
            "evidence_count": len(binder.evidence),
            "assembled_at": binder.assembled_at.isoformat(),
        },
    )


def readiness_assessed(assessment) -> DomainEvent:
    return DomainEvent(
        topic=TOPIC_READINESS_ASSESSED,
        key=assessment.target,
        payload={
            "assessment_id": assessment.id,
            "target": assessment.target,
            "level": assessment.level.value,
            "overall_score": assessment.overall_score,
            "assessed_at": assessment.assessed_at.isoformat(),
        },
    )


def package_created(package) -> DomainEvent:
    return DomainEvent(
        topic=TOPIC_PACKAGE_CREATED,
        key=package.dossier.id,
        payload={
            "package_id": package.id,
            "dossier_id": package.dossier.id,
            "target": package.dossier.target,
            "generated_at": package.generated_at.isoformat(),
        },
    )


class OutboxPublisher:
    def __init__(self):
        self._events: list = []

    def publish(self, event: DomainEvent) -> None:
        self._events.append(event)

    def drain(self) -> list:
        events, self._events = self._events, []
        return events
