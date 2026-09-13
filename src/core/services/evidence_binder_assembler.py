"""Evidence binder assembler service (ADR-001, ADR-009).

Assembles ordered evidence binders from a dossier and enriches them with
metadata required by auditors.
"""
from ..domain.cert_models import EvidenceBinder, EvidenceRef
from ..events.cert_events import OutboxPublisher, evidence_binder_assembled


class EvidenceBinderAssembler:
    def __init__(self, repository, publisher: OutboxPublisher | None = None,
                 collector=None):
        self._repo = repository
        self._publisher = publisher or OutboxPublisher()
        self._collector = collector

    def assemble(self, dossier, additional_refs: list | None = None) -> EvidenceBinder:
        binder = EvidenceBinder(dossier_id=dossier.id, evidence=list(dossier.evidence))
        for ref in additional_refs or []:
            binder.add(EvidenceRef(**ref))
        self._repo.save_binder(binder)
        self._publisher.publish(evidence_binder_assembled(binder))
        if self._collector:
            self._collector.collect_event(
                "evidence.assembled",
                {"dossier_id": dossier.id, "binder_id": binder.id,
                 "evidence_count": len(binder.evidence)},
                correlation_id=dossier.id,
            )
        return binder

    def get_binder(self, dossier_id: str) -> EvidenceBinder | None:
        return self._repo.get_binder(dossier_id)
