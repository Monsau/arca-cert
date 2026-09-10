"""REST handlers. Endpoints follow ADR-002; schemas follow contracts/rest/openapi.yaml."""
from fastapi import APIRouter, HTTPException, Request

from ..config import settings

router = APIRouter(prefix="/api/v1", tags=["arca-cert"])


def _service(request: Request):
    return request.app.state.cert_service


@router.get("/cert/health")
def api_health():
    return {"service": settings.app_name, "status": "ok"}


@router.post("/dossiers", status_code=201)
def build_dossier(body: dict, request: Request):
    body = body or {}
    target = body.get("target")
    scores = body.get("scores", [])
    evidence = body.get("evidence", [])
    if not target or not scores:
        raise HTTPException(status_code=422,
                            detail="target and scores are required")
    try:
        dossier, plan = _service(request).build_dossier(target, scores, evidence)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"dossier": dossier.to_dict(), "remediation": plan.to_dict(),
            "correlation_id": dossier.id}


@router.get("/dossiers")
def list_dossiers(request: Request, target: str | None = None):
    return {"dossiers": [d.to_dict() for d in _service(request).list_dossiers(target=target)]}


@router.get("/dossiers/{dossier_id}")
def get_dossier(dossier_id: str, request: Request):
    dossier = _service(request).get_dossier(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail="dossier not found")
    return dossier.to_dict()


@router.get("/dossiers/{dossier_id}/remediation")
def get_remediation(dossier_id: str, request: Request):
    plan = _service(request).get_remediation(dossier_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="remediation not found")
    return plan.to_dict()


@router.post("/dossiers/{dossier_id}/publish")
def publish_dossier(dossier_id: str, body: dict, request: Request):
    reviewer = (body or {}).get("reviewer")
    try:
        dossier = _service(request).publish_dossier(dossier_id, reviewer)
    except LookupError:
        raise HTTPException(status_code=404, detail="dossier not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return dossier.to_dict()
