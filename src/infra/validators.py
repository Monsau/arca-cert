"""Cert validators client — cert-side adapter for the evidence content gate.

Evidence content carried by ``EvidenceRef`` entries (Turtle ontologies,
JSON/YAML manifests, workflow YAML) is delegated to the shared Suite
validators service (``POST /api/v1/validate``, contract documented in
``arca-platform/services/validators/``) before a certification package may be
built.

Adapter invariants (mirrored from the packs reference implementation —
cross-module code imports are forbidden, contracts only):

  - the caller's ``Authorization`` header is forwarded verbatim — security by
    design: every validation call carries the caller's SSO token, the
    validators service validates it (no anonymous validation path);
  - fail-closed semantics for the evidence gate: when the validators service
    is configured, an unreachable (``degraded``) or denying (``denied``)
    validator blocks the package build — evidence that cannot be proven must
    not be certified;
  - graceful degradation stays available by leaving ``CERT_VALIDATORS_URL``
    empty (disabled adapter): content validation is then skipped explicitly,
    with a ``validation: "skipped"`` marker recorded on the evidence entry.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)

#: Validation endpoint on the Suite validators service.
VALIDATE_ENDPOINT = "/api/v1/validate"


@dataclass
class ValidationOutcome:
    """Outcome of a validation attempt — never raises into the cert flow.

    ``status`` is one of ``valid`` | ``invalid`` | ``denied`` | ``degraded`` |
    ``disabled``. ``valid`` is True only when the service proved the content
    conforms; ``denied``/``degraded`` are fail-closed signals for the gate.
    """

    valid: bool = False
    status: str = "disabled"
    checks: list = field(default_factory=list)
    status_code: Optional[int] = None
    detail: str = ""


class ContentValidator(ABC):
    """Backend-agnostic evidence content validation contract."""

    @abstractmethod
    def validate_ontology(
        self,
        ttl: str,
        artifact_kind: str = "ontology_ttl",
        authorization: Optional[str] = None,
        content_format: Optional[str] = None,
    ) -> ValidationOutcome:
        """Validate an artifact against the Suite contracts."""


class NullContentValidator(ContentValidator):
    """Disabled adapter (default) — no network call, no exception."""

    def validate_ontology(
        self,
        ttl: str,
        artifact_kind: str = "ontology_ttl",
        authorization: Optional[str] = None,
        content_format: Optional[str] = None,
    ) -> ValidationOutcome:
        return ValidationOutcome(
            valid=True,  # nothing to prove — the gate is disabled, not failed
            status="disabled",
            detail="validators service is disabled (Null adapter)",
        )


class HttpContentValidator(ContentValidator):
    """HTTP client for the shared Suite validators service.

    Opt-in (``CERT_VALIDATORS_URL`` set), bounded timeout. Fail-closed:
    transport errors and authentication denials are surfaced as
    ``degraded``/``denied`` outcomes so the evidence gate refuses to certify
    unproven content.
    """

    def __init__(self, base_url: str, timeout: float = 10.0, client: Optional[object] = None):
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("httpx is required for the validators adapter") from exc

        self._httpx = httpx
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def validate_ontology(
        self,
        ttl: str,
        artifact_kind: str = "ontology_ttl",
        authorization: Optional[str] = None,
        content_format: Optional[str] = None,
    ) -> ValidationOutcome:
        headers = {"Authorization": authorization} if authorization else {}
        payload = {"artifact_kind": artifact_kind, "content": ttl}
        if content_format:
            payload["content_format"] = content_format

        try:
            response = self._client.post(
                VALIDATE_ENDPOINT,
                json=payload,
                headers=headers,
            )
        except self._httpx.HTTPError as exc:
            logger.error("validators service unreachable: %s", exc)
            return ValidationOutcome(
                valid=False,
                status="degraded",
                detail=f"validators service unreachable: {exc}",
            )

        if response.status_code == 200:
            body = response.json() if response.content else {}
            return ValidationOutcome(
                valid=bool(body.get("valid")),
                status="valid" if body.get("valid") else "invalid",
                checks=body.get("checks", []),
                status_code=response.status_code,
                detail=_summarize(body),
            )

        if response.status_code in (401, 403):
            logger.error("validators service denied the call: HTTP %s", response.status_code)
            return ValidationOutcome(
                valid=False,
                status="denied",
                status_code=response.status_code,
                detail=(
                    f"validators service denied the call (HTTP {response.status_code}): "
                    f"{response.text[:200]}"
                ),
            )

        logger.error("validators service error: HTTP %s", response.status_code)
        return ValidationOutcome(
            valid=False,
            status="degraded",
            status_code=response.status_code,
            detail=f"validators service returned HTTP {response.status_code}: {response.text[:200]}",
        )


def _summarize(body: dict) -> str:
    """Compact, human-readable summary of failed checks for the gate message."""
    failed = [c for c in body.get("checks", []) if c.get("passed") is False]
    if not failed:
        return "content conforms to the Suite contracts"
    parts = [f"{c.get('gate')}: {c.get('message', 'failed')}" for c in failed[:5]]
    suffix = f" (+{len(failed) - 5} more)" if len(failed) > 5 else ""
    return "; ".join(parts) + suffix


def build_content_validator(
    url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> ContentValidator:
    """Factory selecting the adapter from settings.

    Active only when a non-empty validators URL is set (``CERT_VALIDATORS_URL``).
    The evidence gate treats ``denied``/``degraded`` outcomes as failures
    (fail-closed); when the URL is empty the Null adapter skips content
    validation explicitly (``validation: "skipped"`` marker).
    """
    if url is None:
        url = settings.validators_url
    if timeout is None:
        timeout = settings.validators_timeout_seconds
    if url:
        return HttpContentValidator(url, timeout=timeout)
    return NullContentValidator()
