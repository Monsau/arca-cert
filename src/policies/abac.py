"""ABAC policy rules for arca-cert (ADR-009).

Attribute-based checks encode separation of duties and lifecycle constraints
that cannot be expressed by roles alone.
"""
from ..core.domain.cert_models import DossierStatus


def can_publish(user: dict, dossier) -> tuple[bool, str]:
    """Reviewers may not publish dossiers they created (separation of duties).
    Admins may override this rule.
    """
    if dossier.status is not DossierStatus.DRAFT:
        return False, f"dossier is {dossier.status.value}"
    if "cert-admin" in user.get("roles", []):
        return True, ""
    if user.get("sub") == dossier.reviewer:
        return False, "reviewer cannot publish a dossier they created"
    return True, ""


def can_revoke(user: dict, dossier) -> tuple[bool, str]:
    """Only admins can revoke published dossiers."""
    if dossier.status is not DossierStatus.PUBLISHED:
        return False, f"dossier is {dossier.status.value}"
    if "cert-admin" not in user.get("roles", []):
        return False, "revocation requires admin role"
    return True, ""


def can_mutate_draft(user: dict, dossier) -> tuple[bool, str]:
    """Writers can mutate only draft dossiers. Admins can mutate any state."""
    if "cert-admin" in user.get("roles", []):
        return True, ""
    if dossier.status is not DossierStatus.DRAFT:
        return False, f"dossier is {dossier.status.value}"
    return True, ""
