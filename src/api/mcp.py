"""MCP capability handlers. Capabilities follow contracts/mcp/capabilities.json (ADR-004, ADR-009)."""
from fastapi import APIRouter, Depends, HTTPException, Request

from ..policies.abac import can_publish
from .security import audit, get_current_user, require_permission

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _service(request: Request):
    return request.app.state.cert_service


@router.get("/capabilities")
def list_capabilities():
    return {
        "capabilities": [
            "create_cert_package",
            "assemble_evidence",
            "get_readiness_status",
            "get_remediation_plan",
            "publish_cert_package",
        ]
    }


@router.post("/tools/create_cert_package")
def create_cert_package(
    body: dict,
    request: Request,
    user: dict = Depends(require_permission("package:create")),
):
    body = body or {}
    target = body.get("target")
    scores = body.get("scores", [])
    evidence = body.get("evidence", [])
    threshold = body.get("threshold", 0.7)
    valid_days = body.get("valid_days", 90)
    if not target or not scores:
        raise HTTPException(status_code=422, detail="target and scores required")
    try:
        package = _service(request).build_package(
            target, scores, evidence, threshold, valid_days
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(_service(request), "mcp.package.created",
          {"package_id": package["id"], "target": target, "user": user.get("sub")},
          package["id"])
    return {
        "package_id": package["id"],
        "dossier_id": package["dossier"]["id"],
        "status": package["dossier"]["status"],
        "level": package["assessment"]["level"],
        "overall_score": package["assessment"]["overall_score"],
    }


@router.post("/tools/assemble_evidence")
def assemble_evidence(
    body: dict,
    request: Request,
    user: dict = Depends(require_permission("binder:create")),
):
    dossier_id = (body or {}).get("dossier_id")
    additional_refs = (body or {}).get("additional_refs", [])
    if not dossier_id:
        raise HTTPException(status_code=422, detail="dossier_id required")
    try:
        binder = _service(request).assemble_evidence(dossier_id, additional_refs)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit(_service(request), "mcp.evidence.assembled",
          {"dossier_id": dossier_id, "binder_id": binder["id"], "user": user.get("sub")},
          dossier_id)
    return {"binder_id": binder["id"], "evidence_count": binder["count"],
            "evidence": binder["evidence"]}


@router.post("/tools/get_readiness_status")
def get_readiness_status(
    body: dict,
    request: Request,
    user: dict = Depends(require_permission("assessment:read")),
):
    body = body or {}
    assessment_id = body.get("assessment_id")
    if assessment_id:
        assessment = _service(request).get_readiness(assessment_id)
        if assessment is None:
            raise HTTPException(status_code=404, detail="assessment not found")
        audit(_service(request), "mcp.readiness.read",
              {"assessment_id": assessment_id, "user": user.get("sub")}, assessment_id)
        return assessment
    target = body.get("target")
    scores = body.get("scores", [])
    threshold = body.get("threshold", 0.7)
    if not target or not scores:
        raise HTTPException(status_code=422, detail="target and scores or assessment_id required")
    try:
        assessment = _service(request).assess_readiness(target, scores, threshold)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(_service(request), "mcp.readiness.assessed",
          {"target": target, "assessment_id": assessment["id"], "user": user.get("sub")},
          assessment["id"])
    return assessment


@router.post("/tools/get_remediation_plan")
def get_remediation_plan(
    body: dict,
    request: Request,
    user: dict = Depends(require_permission("remediation:read")),
):
    dossier_id = (body or {}).get("dossier_id")
    if not dossier_id:
        raise HTTPException(status_code=422, detail="dossier_id required")
    plan = _service(request).get_remediation(dossier_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="remediation not found")
    audit(_service(request), "mcp.remediation.read",
          {"dossier_id": dossier_id, "user": user.get("sub")}, dossier_id)
    return {"plan_id": plan.id, "items": [i.to_dict() for i in plan.items]}


@router.post("/tools/publish_cert_package")
def publish_cert_package(
    body: dict,
    request: Request,
    user: dict = Depends(require_permission("dossier:publish")),
):
    dossier_id = (body or {}).get("dossier_id")
    reviewer = (body or {}).get("reviewer") or user.get("sub")
    if not dossier_id:
        raise HTTPException(status_code=422, detail="dossier_id required")
    dossier = _service(request).get_dossier(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail="dossier not found")
    allowed, reason = can_publish({**user, "sub": reviewer}, dossier)
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)
    try:
        dossier = _service(request).publish_dossier(dossier_id, reviewer)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit(_service(request), "mcp.dossier.published",
          {"dossier_id": dossier_id, "reviewer": reviewer, "user": user.get("sub")},
          dossier_id)
    return {"dossier_id": dossier.id, "status": dossier.status.value,
            "seal": dossier.seal, "valid_until": dossier.valid_until.isoformat()}
