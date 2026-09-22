"""FastAPI security dependencies for arca-cert (ADR-009)."""
import os
from functools import wraps

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import settings
from ..policies.abac import can_publish, can_revoke
from ..policies.oidc import OIDCValidator, validator_from_settings

bearer = HTTPBearer(auto_error=False)


def get_validator(request: Request) -> OIDCValidator:
    if not hasattr(request.app.state, "oidc_validator"):
        request.app.state.oidc_validator = validator_from_settings(settings)
    return request.app.state.oidc_validator


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    # Security by design: no dev bypass — the Suite portal injects the user's
    # Keycloak access token on every call.
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    validator = get_validator(request)
    try:
        user = validator.validate(credentials.credentials)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return {"sub": user.sub, "email": user.email, "roles": user.roles}


def require_roles(*allowed: str):
    def checker(user: dict = Depends(get_current_user)) -> dict:
        user_roles = set(user.get("roles", []))
        if not user_roles.intersection(allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires one of roles: {allowed}",
            )
        return user

    return checker


def require_permission(permission: str):
    from ..policies.rbac import require_permission as _require_permission

    def checker(user: dict = Depends(get_current_user)) -> dict:
        roles = user.get("roles", [])
        if not _require_permission(roles, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing permission {permission}",
            )
        return user

    return checker


def with_authz(permission: str, *allowed_roles: str):
    """Combine RBAC permission check with optional role short-circuit."""
    from ..policies.rbac import require_permission as _require_permission

    def checker(user: dict = Depends(get_current_user)) -> dict:
        roles = user.get("roles", [])
        if allowed_roles and set(roles).intersection(allowed_roles):
            return user
        if not _require_permission(roles, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing permission {permission}",
            )
        return user

    return checker


def audit(service, event_type: str, payload: dict, correlation_id: str):
    """Emit an audit event through the embedded SOC collector if available."""
    if hasattr(service, "audit") and callable(service.audit):
        service.audit(event_type, payload, correlation_id)
