"""Configuration loaded from environment variables and Vault."""
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CERT_")

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


settings = Settings()
