"""Application entry point."""
import contextlib
import os

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles

from .api import graphql, mcp, rest
from .api.security import get_current_user
from .config import settings
from .core.services.cert_service import CertService
from .infra import otel
from .infra.kafka import BenchResultConsumer, KafkaEvent, KafkaProducer
from .infra.ooc_client import build_ooc_gate_client
from .infra.provenance_consumer import ProvenanceTraceConsumer
from .infra.soc import SOCCollector
from .infra.store import SqlCertRepository, connect_sqlite
from .policies.oidc import OIDCValidator, _load_jwks


class KafkaDomainEventPublisher:
    def __init__(self, producer: KafkaProducer):
        self._producer = producer

    def publish(self, event) -> None:
        self._producer.publish(
            KafkaEvent(
                topic=event.topic,
                key=event.key,
                payload=event.payload,
            )
        )


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    repository = SqlCertRepository(connect_sqlite())
    collector = SOCCollector()
    kafka_producer = KafkaProducer()
    kafka_publisher = KafkaDomainEventPublisher(kafka_producer)
    app.state.cert_repository = repository
    app.state.soc_collector = collector
    app.state.kafka_publisher = kafka_publisher
    app.state.oidc_validator = OIDCValidator(
        issuer=settings.oidc_issuer or None,
        audience=settings.oidc_audience,
        jwks=_load_jwks(settings.oidc_jwks_url),
    )
    app.state.cert_service = CertService(
        repository,
        publisher=kafka_publisher,
        collector=collector,
        ooc_client=build_ooc_gate_client(),
    )
    consumer = None
    # Kafka consumption is enabled by default so cert packages react to
    # bench.results events. Set CERT_KAFKA_CONSUME=0 to disable it (dev
    # profiles without a broker), same convention as trust and studio.
    if os.environ.get("CERT_KAFKA_CONSUME", "1") != "0":
        consumer = BenchResultConsumer(app.state.cert_service)
        app.state.bench_consumer = consumer
        consumer.start()

    provenance_consumer = None
    # Optional ArcaQ PROV-O trace ingestion. Disabled by default so arca-cert
    # can run without ArcaQ when the feature is not needed.
    if settings.arcaq_provo_enabled:
        provenance_consumer = ProvenanceTraceConsumer(repository)
        provenance_consumer.start()
    app.state.provenance_consumer = provenance_consumer
    yield
    if consumer:
        consumer.stop()
    if provenance_consumer:
        provenance_consumer.stop()


def _docs_metadata_guard(request: Request) -> None:
    """Zero Trust gate for the API metadata endpoints (/docs, /redoc,
    /openapi.json).

    Dev/standalone keeps them open (module dev-gate convention); every other
    environment requires a valid Keycloak JWT through the existing JWKS/RS256
    stack (ADR-009). The endpoints are re-served below with this guard — they
    are protected, not hidden. Health endpoints stay open for k8s probes.
    """
    if settings.environment == "dev":
        return
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=auth[7:]
        )
    else:
        credentials = None
    get_current_user(request, credentials)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
otel.instrument(app)

app.include_router(rest.router)
app.include_router(mcp.router)
app.include_router(graphql.router)


@app.get("/openapi.json", include_in_schema=False)
async def openapi_json(_: None = Depends(_docs_metadata_guard)):
    return app.openapi()


@app.get("/docs", include_in_schema=False)
async def swagger_ui(_: None = Depends(_docs_metadata_guard)):
    return get_swagger_ui_html(
        openapi_url="/openapi.json", title=f"{settings.app_name} - Swagger UI"
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_ui(_: None = Depends(_docs_metadata_guard)):
    return get_redoc_html(
        openapi_url="/openapi.json", title=f"{settings.app_name} - ReDoc"
    )

# Serve embedded cert UI static files when present.
ui_dir = os.path.join(os.path.dirname(__file__), "ui")
if os.path.isdir(ui_dir):
    app.mount("/cert", StaticFiles(directory=ui_dir, html=True), name="cert-ui")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": settings.app_name}


@app.get("/readyz")
def readyz():
    return {"status": "ready"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
