"""MCP capability handlers. Capabilities follow contracts/mcp/capabilities.json (ADR-004)."""
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _service(request: Request):
    return request.app.state.cert_service


@router.get("/capabilities")
def list_capabilities():
    return {"capabilities": ["dossier-generate", "remediation-plan", "evidence-collect"]}


@router.post("/tools/dossier-generate")
def dossier_generate(body: dict, request: Request):
    body = body or {}
    target, scores, evidence = body.get("target"), body.get("scores", []), body.get("evidence", [])
    if not target or not scores:
        raise HTTPException(status_code=422, detail="target and scores required")
    dossier, plan = _service(request).build_dossier(target, scores, evidence)
    return {"dossier_id": dossier.id, "remediation_id": plan.id,
            "failing_dimensions": dossier.failing_dimensions()}


@router.post("/tools/remediation-plan")
def remediation_plan(body: dict, request: Request):
    dossier_id = (body or {}).get("dossier_id")
    if not dossier_id:
        raise HTTPException(status_code=422, detail="dossier_id required")
    plan = _service(request).get_remediation(dossier_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="remediation not found")
    return plan.to_dict()


@router.post("/tools/evidence-collect")
def evidence_collect(body: dict, request: Request):
    dossier_id = (body or {}).get("dossier_id")
    if not dossier_id:
        raise HTTPException(status_code=422, detail="dossier_id required")
    dossier = _service(request).get_dossier(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail="dossier not found")
    return {"dossier_id": dossier.id, "evidence": [e.to_dict() for e in dossier.evidence]}
