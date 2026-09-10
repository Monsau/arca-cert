"""Cert domain events (ADR-003)."""
from dataclasses import dataclass, field
from datetime import datetime, timezone

TOPIC_DOSSIER_BUILT = "cert.dossier.built"
TOPIC_DOSSIER_PUBLISHED = "cert.dossier.published"
TOPIC_REMEDIATION_ISSUED = "cert.remediation.issued"


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
        payload={"dossier_id": dossier.id, "target": dossier.target,
                 "built_at": datetime.now(timezone.utc).isoformat()},
    )


def dossier_published(dossier) -> DomainEvent:
    return DomainEvent(
        topic=TOPIC_DOSSIER_PUBLISHED,
        key=dossier.id,
        payload={"dossier_id": dossier.id, "reviewer": dossier.reviewer,
                 "valid_until": dossier.valid_until.isoformat()},
    )


def remediation_issued(plan) -> DomainEvent:
    return DomainEvent(
        topic=TOPIC_REMEDIATION_ISSUED,
        key=plan.dossier_id,
        payload={"dossier_id": plan.dossier_id, "plan_id": plan.id,
                 "item_count": len(plan.items),
                 "issued_at": datetime.now(timezone.utc).isoformat()},
    )


class OutboxPublisher:
    def __init__(self):
        self._events: list = []

    def publish(self, event: DomainEvent) -> None:
        self._events.append(event)

    def drain(self) -> list:
        events, self._events = self._events, []
        return events
