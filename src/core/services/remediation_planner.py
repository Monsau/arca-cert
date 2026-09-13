"""Remediation planner service (ADR-001, ADR-009).

Builds remediation plans from failing dimensions with concrete actions and owners.
"""
from ..domain.cert_models import RemediationItem, RemediationPlan
from ..events.cert_events import OutboxPublisher, remediation_issued


DEFAULT_ACTIONS = {
    "security": ("Patch or harden security controls; run a new bench.", "security-owner"),
    "compliance": ("Map controls to the missing compliance clauses; collect evidence.", "compliance-owner"),
    "availability": ("Improve redundancy and run a resilience bench.", "sre-owner"),
    "performance": ("Optimize critical paths and re-run load tests.", "performance-owner"),
    "confidence": ("Increase test coverage and review model drift.", "ml-owner"),
    "explainability": ("Add model cards and SHAP/saliency evidence.", "ml-owner"),
    "fairness": ("Audit training data and bias metrics.", "ethics-owner"),
}


class RemediationPlanner:
    def __init__(self, repository, publisher: OutboxPublisher | None = None,
                 collector=None):
        self._repo = repository
        self._publisher = publisher or OutboxPublisher()
        self._collector = collector

    def create_plan(self, dossier, threshold: float = 0.7) -> RemediationPlan:
        items = []
        for dim in dossier.failing_dimensions(threshold):
            action, owner = DEFAULT_ACTIONS.get(
                dim, (f"Investigate and improve {dim} controls", "domain-owner")
            )
            items.append(RemediationItem(
                risk=f"{dim} score below {threshold}",
                action=action,
                owner=owner,
                dimension=dim,
            ))
        plan = RemediationPlan(dossier_id=dossier.id, items=items)
        self._repo.save_remediation(plan)
        self._publisher.publish(remediation_issued(plan))
        if self._collector:
            self._collector.collect_event(
                "remediation.created",
                {"dossier_id": dossier.id, "plan_id": plan.id, "items": len(items)},
                correlation_id=dossier.id,
            )
        return plan

    def get_plan(self, dossier_id: str) -> RemediationPlan | None:
        return self._repo.get_remediation(dossier_id)
