"""GraphQL schema and resolvers. Types follow contracts/graphql/schema.graphql (ADR-002, ADR-009)."""
import os

from ariadne import MutationType, ObjectType, QueryType, load_schema_from_path, make_executable_schema
from ariadne.asgi import GraphQL
from fastapi import APIRouter, Depends, Request
from starlette.responses import Response

from ..core.domain.cert_models import EvidenceRef
from .security import get_current_user

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(BASE_DIR, "..", "contracts", "graphql", "schema.graphql")

type_defs = load_schema_from_path(SCHEMA_PATH)

query = QueryType()
mutation = MutationType()

dossier_type = ObjectType("CertificationDossier")
dossier_type.set_alias("validUntil", "valid_until")
dossier_type.set_alias("isExpired", "is_expired")

package_type = ObjectType("CertificationPackage")
package_type.set_alias("generatedAt", "generated_at")
package_type.set_alias("remediationId", "remediation_id")

# Domain models serialize to snake_case dicts; alias the camelCase SDL fields
# to the underlying dict keys so the default resolver finds them.
evidence_type = ObjectType("EvidenceRef")
evidence_type.set_alias("refId", "ref_id")
evidence_type.set_alias("collectedAt", "collected_at")

remediation_item_type = ObjectType("RemediationItem")
remediation_item_type.set_alias("dueDays", "due_days")

remediation_plan_type = ObjectType("RemediationPlan")
remediation_plan_type.set_alias("dossierId", "dossier_id")
remediation_plan_type.set_alias("createdAt", "created_at")

readiness_type = ObjectType("ReadinessAssessment")
readiness_type.set_alias("overallScore", "overall_score")
readiness_type.set_alias("assessedAt", "assessed_at")
readiness_type.set_alias("failingDimensions", "failing_dimensions")

binder_type = ObjectType("EvidenceBinder")
binder_type.set_alias("dossierId", "dossier_id")
binder_type.set_alias("assembledAt", "assembled_at")


async def _service(info):
    return info.context["request"].app.state.cert_service


def _to_evidence_refs(evidence: list | None) -> list:
    """Map GraphQL EvidenceInput dicts (camelCase) to EvidenceRef field names
    (snake_case) so the domain model can consume them directly.

    Ariadne passes input objects through with their SDL field names, so
    ``refId`` / ``collectedAt`` must be translated here; anything already in
    snake_case (REST-style payloads) is passed through unchanged.
    """
    refs = []
    for item in evidence or []:
        if not isinstance(item, dict):
            refs.append(item)
            continue
        ref = {
            "source": item.get("source", ""),
            "ref_id": item.get("ref_id", item.get("refId", "")),
            "description": item.get("description", ""),
            "content": item.get("content", ""),
            "mime": item.get("mime", ""),
            "validation": item.get("validation", ""),
        }
        # Only forward an explicit timestamp; otherwise EvidenceRef's
        # default_factory stamps collection time at construction.
        collected_at = item.get("collected_at", item.get("collectedAt"))
        if collected_at:
            ref["collected_at"] = collected_at
        refs.append(ref)
    return refs


@query.field("dossiers")
async def resolve_dossiers(_, info):
    service = await _service(info)
    return [d.to_dict() for d in service.list_dossiers()]


@query.field("dossier")
async def resolve_dossier(_, info, id):
    service = await _service(info)
    dossier = service.get_dossier(id)
    return dossier.to_dict() if dossier else None


@query.field("packages")
async def resolve_packages(_, info):
    service = await _service(info)
    return service.list_packages()


@query.field("package")
async def resolve_package(_, info, id):
    service = await _service(info)
    package = service.get_package(id)
    return package


@query.field("readiness")
async def resolve_readiness(_, info, assessmentId):
    service = await _service(info)
    assessment = service.get_readiness(assessmentId)
    return assessment


@query.field("readinessByTarget")
async def resolve_readiness_by_target(_, info, target):
    service = await _service(info)
    return service.list_readiness(target=target)


@query.field("remediation")
async def resolve_remediation(_, info, dossierId):
    service = await _service(info)
    plan = service.get_remediation(dossierId)
    if plan is None:
        return None
    return plan.to_dict()


@mutation.field("buildDossier")
async def resolve_build_dossier(_, info, target, scores, evidence=None, threshold=0.7):
    service = await _service(info)
    dossier, _ = service.build_dossier(
        target, scores, _to_evidence_refs(evidence), threshold)
    return dossier.to_dict()


@mutation.field("buildPackage")
async def resolve_build_package(_, info, target, scores, evidence=None,
                                threshold=0.7, validDays=90):
    service = await _service(info)
    return service.build_package(
        target, scores, _to_evidence_refs(evidence), threshold, validDays)


@mutation.field("publishDossier")
async def resolve_publish_dossier(_, info, id, reviewer=None):
    request = info.context["request"]
    service = await _service(info)
    reviewer = reviewer or request.state.user.get("sub")
    dossier = service.publish_dossier(id, reviewer)
    return dossier.to_dict()


@mutation.field("assembleEvidence")
async def resolve_assemble_evidence(_, info, dossierId, additionalRefs=None):
    service = await _service(info)
    return service.assemble_evidence(dossierId, _to_evidence_refs(additionalRefs))


@mutation.field("assessReadiness")
async def resolve_assess_readiness(_, info, target, scores, threshold=0.7):
    service = await _service(info)
    return service.assess_readiness(target, scores, threshold)


schema = make_executable_schema(
    type_defs, query, mutation, dossier_type, package_type, evidence_type,
    remediation_item_type, remediation_plan_type, readiness_type, binder_type)

graphql_app = GraphQL(schema, debug=True,
                      context_value=lambda request, data: {"request": request})

router = APIRouter(prefix="/graphql", tags=["graphql"])


async def _dispatch_graphql(request: Request) -> Response:
    """Run the ariadne ASGI app and re-assemble its ASGI response into a
    starlette Response so it can be returned from a FastAPI handler.

    starlette's Request exposes ``scope``/``receive`` but no ``send``, so the
    ASGI messages are captured explicitly instead of delegating to a
    non-existent attribute.
    """
    status_code = 200
    raw_headers: list = []
    body = bytearray()

    async def send(message: dict) -> None:
        nonlocal status_code, raw_headers
        if message["type"] == "http.response.start":
            status_code = message["status"]
            raw_headers = list(message.get("headers", []))
        elif message["type"] == "http.response.body":
            body.extend(message.get("body", b""))

    await graphql_app(request.scope, request.receive, send)
    headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in raw_headers}
    # Content-Length is recomputed from the re-assembled body.
    headers.pop("content-length", None)
    return Response(content=bytes(body), status_code=status_code,
                    headers=headers)


@router.post("")
async def graphql_endpoint(request: Request, user: dict = Depends(get_current_user)):
    request.state.user = user
    return await _dispatch_graphql(request)


@router.get("")
async def graphql_playground(request: Request):
    return await _dispatch_graphql(request)
