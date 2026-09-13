"""RBAC policy definitions for arca-cert (ADR-009)."""
from enum import Enum


class Role(str, Enum):
    READER = "cert-reader"
    WRITER = "cert-writer"
    REVIEWER = "cert-reviewer"
    ADMIN = "cert-admin"


# Permission matrix: role -> set of permission names.
PERMISSIONS = {
    Role.READER: {
        "dossier:read",
        "package:read",
        "binder:read",
        "assessment:read",
        "remediation:read",
        "soc:read",
    },
    Role.WRITER: {
        "dossier:read",
        "dossier:create",
        "package:create",
        "binder:create",
        "assessment:create",
        "remediation:read",
        "soc:read",
    },
    Role.REVIEWER: {
        "dossier:read",
        "dossier:publish",
        "package:read",
        "binder:read",
        "assessment:read",
        "remediation:read",
        "soc:read",
    },
    Role.ADMIN: {
        "dossier:read",
        "dossier:create",
        "dossier:publish",
        "dossier:revoke",
        "package:create",
        "package:read",
        "binder:create",
        "binder:read",
        "assessment:create",
        "assessment:read",
        "remediation:read",
        "soc:read",
        "soc:respond",
    },
}


def has_permission(role: Role, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())


def require_permission(roles: list[Role], permission: str) -> bool:
    return any(has_permission(r, permission) for r in roles)
