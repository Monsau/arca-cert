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
    vault_transit_key: str = os.environ.get("VAULT_TRANSIT_KEY", "arca-cert")
    # Signature backend: "dev" (HMAC test signer) or "vault" (Vault Transit/PKI).
    # Production must use "vault"; dev/test may use "dev" explicitly.
    signer_backend: str = os.environ.get("SIGNER_BACKEND", "dev")
    kafka_bootstrap_servers: str = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_bench_topic: str = os.environ.get("KAFKA_BENCH_TOPIC", "bench.results")
    kafka_consumer_group: str = os.environ.get("KAFKA_CONSUMER_GROUP", "arca-cert")
    otel_endpoint: str = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    # Auth settings (ADR-009) — OIDC-only, no local secret (security by design)
    oidc_issuer: str = os.environ.get("CERT_OIDC_ISSUER", "")
    oidc_audience: str = os.environ.get("CERT_OIDC_AUDIENCE", "arca-cert")
    oidc_jwks_url: str = os.environ.get("CERT_OIDC_JWKS_URL", "")  # in-cluster Keycloak JWKS
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

    # Shared validators service (evidence content gate) — Suite contract
    # validation of validatable evidence artifacts (Turtle ontologies, JSON/YAML
    # manifests, workflow YAML) before a package may be built. Fail-closed when
    # configured; empty = disabled (Null adapter, evidence entries are marked
    # validation: "skipped" explicitly).
    validators_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "VALIDATORS_URL",
            "CERT_VALIDATORS_URL",
        ),
    )
    validators_timeout_seconds: float = Field(
        default=10.0,
        validation_alias=AliasChoices(
            "VALIDATORS_TIMEOUT_SECONDS",
            "CERT_VALIDATORS_TIMEOUT_SECONDS",
        ),
    )


settings = Settings()
