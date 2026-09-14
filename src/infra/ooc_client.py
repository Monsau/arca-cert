"""Optional OOC governance gate for certification publication.

The gate is disabled by default. When enabled, `CertService.publish_dossier`
queries the configured OOC endpoint to ensure an approved Operational Ontology
Contract exists for the dossier target before publication.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from src.config import settings

logger = logging.getLogger(__name__)


class OOCNotApprovedError(RuntimeError):
    """Raised when the target has no approved OOC and publication is blocked."""


@runtime_checkable
class OOCGateClient(Protocol):
    """Neutral interface for OOC approval checks."""

    def is_approved(self, target: str, version: str | None = None) -> bool:
        ...


class NullOOCGateClient:
    """No-op gate used when OOC integration is disabled."""

    def is_approved(self, target: str, version: str | None = None) -> bool:
        return True


class HttpOOCGateClient:
    """Best-effort HTTP client for OOC approval checks.

    Expects the OOC endpoint to expose `GET /{target}?version=...` returning
    JSON with an `approved` boolean.
    """

    def __init__(self, base_url: str, timeout: float = 5.0, client=None):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client

    def is_approved(self, target: str, version: str | None = None) -> bool:
        import httpx

        transport = self._client or httpx.Client(timeout=self._timeout)
        url = f"{self._base_url}/{target}"
        params = {}
        if version:
            params["version"] = version
        try:
            response = transport.get(url, params=params)
            response.raise_for_status()
            body = response.json()
            return bool(body.get("approved", False))
        except Exception as exc:  # noqa: BLE001
            logger.warning("OOC approval check failed for %s: %s", target, exc)
            return False


def build_ooc_gate_client(
    enabled: bool | None = None,
    url: str | None = None,
    timeout: float | None = None,
) -> OOCGateClient:
    """Factory: returns a no-op gate when the integration is disabled."""
    if enabled is None:
        enabled = settings.ooc_enabled
    if url is None:
        url = settings.ooc_url
    if timeout is None:
        timeout = settings.ooc_timeout_seconds
    if not enabled or not url:
        return NullOOCGateClient()
    return HttpOOCGateClient(base_url=url, timeout=timeout)
