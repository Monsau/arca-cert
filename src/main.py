"""Application entry point."""
import contextlib
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import graphql, mcp, rest
from .config import settings
from .core.services.cert_service import CertService
from .infra import otel
from .infra.kafka import BenchResultConsumer, KafkaEvent, KafkaProducer
from .infra.ooc_client import build_ooc_gate_client
from .infra.provenance_consumer import ProvenanceTraceConsumer
from .infra.soc import SOCCollector
from .infra.store import SqlCertRepository, connect_sqlite
from .policies.oidc import OIDCValidator


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
        secret=settings.jwt_secret,
        issuer=settings.oidc_issuer,
        audience=settings.oidc_audience,
    )
    app.state.cert_service = CertService(
        repository,
        publisher=kafka_publisher,
        collector=collector,
        ooc_client=build_ooc_gate_client(),
    )
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
    consumer.stop()
    if provenance_consumer:
        provenance_consumer.stop()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
otel.instrument(app)

app.include_router(rest.router)
app.include_router(mcp.router)
app.include_router(graphql.router)

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
