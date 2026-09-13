"""GraphQL schema and resolvers. Types follow contracts/graphql/schema.graphql (ADR-002, ADR-009)."""
import os

from ariadne import MutationType, ObjectType, QueryType, load_schema_from_path, make_executable_schema
from ariadne.asgi import GraphQL
from fastapi import APIRouter, Depends, Request
from starlette.datastructures import Headers

from ..core.domain.cert_models import EvidenceRef
from .security import get_current_user

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(BASE_DIR, "..", "contracts", "graphql", "schema.graphql")

type_defs = load_schema_from_path(SCHEMA_PATH)

query = QueryType()
mutation = MutationType()

dossier_type = ObjectType("CertificationDossier")
package_type = ObjectType("CertificationPackage")


async def _service(info):
    return info.context["request"].app.state.cert_service


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
    dossier, _ = service.build_dossier(target, scores, evidence or [], threshold)
    return dossier.to_dict()


@mutation.field("buildPackage")
async def resolve_build_package(_, info, target, scores, evidence=None,
                                threshold=0.7, validDays=90):
    service = await _service(info)
    return service.build_package(target, scores, evidence or [], threshold, validDays)


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
    return service.assemble_evidence(dossierId, additionalRefs or [])


@mutation.field("assessReadiness")
async def resolve_assess_readiness(_, info, target, scores, threshold=0.7):
    service = await _service(info)
    return service.assess_readiness(target, scores, threshold)


schema = make_executable_schema(type_defs, query, mutation, dossier_type, package_type)

graphql_app = GraphQL(schema, debug=True, context_value=lambda request: {"request": request})

router = APIRouter(prefix="/graphql", tags=["graphql"])


@router.post("")
async def graphql_endpoint(request: Request, user: dict = Depends(get_current_user)):
    request.state.user = user
    return await graphql_app(request.scope, request.receive, request.send)


@router.get("")
async def graphql_playground(request: Request):
    return await graphql_app(request.scope, request.receive, request.send)
