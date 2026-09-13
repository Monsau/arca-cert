"""Application entry point."""
import contextlib
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import graphql, mcp, rest
from .config import settings
from .core.services.cert_service import CertService
from .infra import otel
from .infra.kafka import BenchResultConsumer
from .infra.soc import SOCCollector
from .infra.store import SqlCertRepository, connect_sqlite
from .policies.oidc import OIDCValidator


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    repository = SqlCertRepository(connect_sqlite())
    collector = SOCCollector()
    app.state.cert_repository = repository
    app.state.soc_collector = collector
    app.state.oidc_validator = OIDCValidator(
        secret=settings.jwt_secret,
        issuer=settings.oidc_issuer,
        audience=settings.oidc_audience,
    )
    app.state.cert_service = CertService(repository, collector=collector)
    consumer = BenchResultConsumer(app.state.cert_service)
    app.state.bench_consumer = consumer
    consumer.start()
    yield
    consumer.stop()


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
