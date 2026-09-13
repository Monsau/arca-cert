"""REST handlers. Endpoints follow ADR-002; schemas follow contracts/rest/openapi.yaml.

All mutating endpoints require a valid Bearer JWT. Reads require cert-reader or
higher. RBAC and ABAC checks are enforced at the handler level and audit events
are emitted through the embedded SOC collector.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..config import settings
from ..policies.abac import can_publish, can_revoke
from .security import audit, require_permission, with_authz

router = APIRouter(prefix="/api/v1", tags=["arca-cert"])


def _service(request: Request):
    return request.app.state.cert_service


def _soc(request: Request):
    return request.app.state.soc_collector


@router.get("/cert/health")
def api_health():
    return {"service": settings.app_name, "status": "ok"}


@router.post("/dossiers", status_code=201)
def build_dossier(
    body: dict,
    request: Request,
    user: dict = Depends(with_authz("dossier:create", "cert-admin")),
):
    body = body or {}
    target = body.get("target")
    scores = body.get("scores", [])
    evidence = body.get("evidence", [])
    threshold = body.get("threshold", 0.7)
    if not target or not scores:
        raise HTTPException(status_code=422, detail="target and scores are required")
    try:
        dossier, plan = _service(request).build_dossier(target, scores, evidence, threshold)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(_service(request), "rest.dossier.created",
          {"target": target, "dossier_id": dossier.id, "user": user.get("sub")},
          dossier.id)
    return {"dossier": dossier.to_dict(), "remediation": plan.to_dict(),
            "correlation_id": dossier.id}


@router.get("/dossiers")
def list_dossiers(
    request: Request,
    target: str | None = None,
    user: dict = Depends(with_authz("dossier:read", "cert-admin")),
):
    audit(_service(request), "rest.dossiers.listed",
          {"target": target, "user": user.get("sub")}, "list-dossiers")
    return {"dossiers": [d.to_dict() for d in _service(request).list_dossiers(target=target)]}


@router.get("/dossiers/{dossier_id}")
def get_dossier(
    dossier_id: str,
    request: Request,
    user: dict = Depends(with_authz("dossier:read", "cert-admin")),
):
    dossier = _service(request).get_dossier(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail="dossier not found")
    audit(_service(request), "rest.dossier.read",
          {"dossier_id": dossier_id, "user": user.get("sub"),
           "seal_valid": dossier.verify_seal()},
          dossier_id)
    return dossier.to_dict()


@router.get("/dossiers/{dossier_id}/remediation")
def get_remediation(
    dossier_id: str,
    request: Request,
    user: dict = Depends(with_authz("remediation:read", "cert-admin")),
):
    plan = _service(request).get_remediation(dossier_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="remediation not found")
    audit(_service(request), "rest.remediation.read",
          {"dossier_id": dossier_id, "user": user.get("sub")}, dossier_id)
    return plan.to_dict()


@router.post("/dossiers/{dossier_id}/publish")
def publish_dossier(
    dossier_id: str,
    body: dict,
    request: Request,
    user: dict = Depends(with_authz("dossier:publish", "cert-admin")),
):
    reviewer = (body or {}).get("reviewer") or user.get("sub")
    dossier = _service(request).get_dossier(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail="dossier not found")
    allowed, reason = can_publish({**user, "sub": reviewer}, dossier)
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)
    try:
        dossier = _service(request).publish_dossier(dossier_id, reviewer)
    except LookupError:
        raise HTTPException(status_code=404, detail="dossier not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit(_service(request), "rest.dossier.published",
          {"dossier_id": dossier_id, "reviewer": reviewer}, dossier_id)
    return dossier.to_dict()


@router.post("/dossiers/{dossier_id}/revoke")
def revoke_dossier(
    dossier_id: str,
    body: dict,
    request: Request,
    user: dict = Depends(require_permission("dossier:revoke")),
):
    reason = (body or {}).get("reason")
    reviewer = user.get("sub")
    dossier = _service(request).get_dossier(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail="dossier not found")
    allowed, reason_msg = can_revoke(user, dossier)
    if not allowed:
        raise HTTPException(status_code=403, detail=reason_msg)
    if not reason:
        raise HTTPException(status_code=422, detail="reason is required")
    try:
        dossier = _service(request).revoke_dossier(dossier_id, reviewer, reason)
    except LookupError:
        raise HTTPException(status_code=404, detail="dossier not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit(_service(request), "rest.dossier.revoked",
          {"dossier_id": dossier_id, "reviewer": reviewer, "reason": reason},
          dossier_id)
    return dossier.to_dict()


@router.post("/packages", status_code=201)
def build_package(
    body: dict,
    request: Request,
    user: dict = Depends(with_authz("package:create", "cert-admin")),
):
    body = body or {}
    target = body.get("target")
    scores = body.get("scores", [])
    evidence = body.get("evidence", [])
    threshold = body.get("threshold", 0.7)
    valid_days = body.get("valid_days", 90)
    if not target or not scores:
        raise HTTPException(status_code=422, detail="target and scores are required")
    try:
        package = _service(request).build_package(
            target, scores, evidence, threshold, valid_days
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(_service(request), "rest.package.created",
          {"target": target, "package_id": package["id"], "user": user.get("sub")},
          package["id"])
    return package


@router.get("/packages")
def list_packages(
    request: Request,
    target: str | None = None,
    user: dict = Depends(with_authz("package:read", "cert-admin")),
):
    audit(_service(request), "rest.packages.listed",
          {"target": target, "user": user.get("sub")}, "list-packages")
    return {"packages": _service(request).list_packages(target=target)}


@router.get("/packages/{package_id}")
def get_package(
    package_id: str,
    request: Request,
    user: dict = Depends(with_authz("package:read", "cert-admin")),
):
    package = _service(request).get_package(package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="package not found")
    audit(_service(request), "rest.package.read",
          {"package_id": package_id, "user": user.get("sub")}, package_id)
    return package


@router.get("/evidence-binders/{dossier_id}")
def get_evidence_binder(
    dossier_id: str,
    request: Request,
    user: dict = Depends(with_authz("binder:read", "cert-admin")),
):
    binder = _service(request).get_evidence_binder(dossier_id)
    if binder is None:
        raise HTTPException(status_code=404, detail="evidence binder not found")
    audit(_service(request), "rest.evidence.read",
          {"dossier_id": dossier_id, "user": user.get("sub")}, dossier_id)
    return binder


@router.post("/readiness", status_code=201)
def assess_readiness(
    body: dict,
    request: Request,
    user: dict = Depends(with_authz("assessment:create", "cert-admin")),
):
    body = body or {}
    target = body.get("target")
    scores = body.get("scores", [])
    threshold = body.get("threshold", 0.7)
    if not target or not scores:
        raise HTTPException(status_code=422, detail="target and scores are required")
    try:
        assessment = _service(request).assess_readiness(target, scores, threshold)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(_service(request), "rest.readiness.assessed",
          {"target": target, "assessment_id": assessment["id"], "user": user.get("sub")},
          assessment["id"])
    return assessment


@router.get("/readiness/{assessment_id}")
def get_readiness(
    assessment_id: str,
    request: Request,
    user: dict = Depends(with_authz("assessment:read", "cert-admin")),
):
    assessment = _service(request).get_readiness(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    audit(_service(request), "rest.readiness.read",
          {"assessment_id": assessment_id, "user": user.get("sub")}, assessment_id)
    return assessment
