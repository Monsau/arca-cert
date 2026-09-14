"""Configuration loaded from environment variables and Vault."""
import os

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CERT_", populate_by_name=True)

    app_name: str = "Arca Cert - Certification Dossier Builder"
    environment: str = os.environ.get("ENVIRONMENT", "dev")
    log_level: str = "INFO"
    # Store backend: "memory" (dev/tests) or "sql" (PostgreSQL via DATABASE_URL).
    store_backend: str = os.environ.get("STORE_BACKEND", "memory")
    database_url: str = os.environ.get("DATABASE_URL", "")
    vault_addr: str = os.environ.get("VAULT_ADDR", "")
    vault_role: str = os.environ.get("VAULT_ROLE", "arca-cert")
    kafka_bootstrap_servers: str = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_bench_topic: str = os.environ.get("KAFKA_BENCH_TOPIC", "bench.results")
    kafka_consumer_group: str = os.environ.get("KAFKA_CONSUMER_GROUP", "arca-cert")
    otel_endpoint: str = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    # Auth settings (ADR-009)
    jwt_secret: str = os.environ.get("CERT_JWT_SECRET", "")
    oidc_issuer: str = os.environ.get("CERT_OIDC_ISSUER", "")
    oidc_audience: str = os.environ.get("CERT_OIDC_AUDIENCE", "arca-cert")
    auth_disabled: bool = os.environ.get("CERT_AUTH_DISABLED", "false").lower() in ("1", "true", "yes")
    # Optional ArcaQ PROV-O trace ingestion (disabled by default so arca-cert
    # works without ArcaQ when the feature is off).
    arcaq_provo_enabled: bool = os.environ.get("CERT_ARCAQ_PROVO_ENABLED", "false").lower() in ("1", "true", "yes")
    arcaq_provo_topic: str = os.environ.get("CERT_ARCAQ_PROVO_TOPIC", "arcaq.prov-o.traces")

    # Optional OOC governance gate. Weak coupling: default endpoint follows the
    # ArcaQ DNS convention; the cognitive profile toggles only the enable flag.
    ooc_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "OOC_ENABLED",
            "CERT_OOC_ENABLED",
        ),
    )
    ooc_url: str = Field(
        default="http://arcaq-api.arcaq.svc.cluster.local:8000/api/v1/ooc",
        validation_alias=AliasChoices(
            "OOC_URL",
            "CERT_OOC_URL",
        ),
    )
    ooc_timeout_seconds: float = Field(
        default=5.0,
        validation_alias=AliasChoices(
            "OOC_TIMEOUT_SECONDS",
            "CERT_OOC_TIMEOUT_SECONDS",
        ),
    )


settings = Settings()
