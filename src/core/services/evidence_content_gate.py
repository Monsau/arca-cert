"""Evidence content gate — proves validatable evidence against the Suite contracts.

Before a certification package may be built, every evidence entry carrying
inline content that indicates a validatable Suite artifact is proven against
the shared validators service:

  - ``.ttl`` / ``text/turtle``                      -> ``ontology_ttl``
  - JSON manifest-like                              -> ``ooc_manifest``
    (with ``content_format: "json"``)
  - YAML manifest-like                              -> ``ooc_manifest``
    (with ``content_format: "yaml"``)
  - workflow YAML (declares ``steps``)              -> ``workflow_yaml``

Classification is deterministic: the explicit ``mime`` field wins, then the
``ref_id``/``source`` extension; YAML content declaring top-level ``steps``
is treated as a workflow, otherwise as a manifest.

Fail-closed semantics (mirroring the packs adapter contract): ``valid=false``
and ``denied``/``degraded`` outcomes (including timeouts) raise
``EvidenceValidationError`` and block the package build. When the validators
URL is empty (default, Null adapter) content validation is skipped explicitly
— the evidence entry records ``validation: "skipped"`` — never silently.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Optional

from ...infra.validators import ContentValidator, ValidationOutcome, build_content_validator
from ..domain.cert_models import EvidenceRef

logger = logging.getLogger(__name__)


class EvidenceValidationError(RuntimeError):
    """Raised when evidence content fails the validators gate — build blocked."""


#: (mime fragment or extension) -> (artifact_kind, content_format)
_TTL_MIMES = ("text/turtle", "application/turtle", "application/x-turtle")
_JSON_MIMES = ("application/json", "text/json", "application/manifest+json")
_YAML_MIMES = (
    "application/yaml",
    "application/x-yaml",
    "text/yaml",
    "text/x-yaml",
)


def classify_artifact(ref: EvidenceRef) -> Optional[tuple[str, Optional[str]]]:
    """Map an evidence entry to (artifact_kind, content_format), or None.

    Returns None when the entry carries no inline content or its content/mime
    does not indicate a validatable Suite artifact.
    """
    content = (ref.content or "").strip()
    if not content:
        return None
    mime = (ref.mime or "").lower().split(";")[0].strip()
    name = (ref.ref_id or ref.source or "").lower()

    if mime in _TTL_MIMES or name.endswith(".ttl"):
        return ("ontology_ttl", None)
    if mime in _JSON_MIMES or name.endswith(".json"):
        return ("ooc_manifest", "json")
    if mime in _YAML_MIMES or name.endswith((".yaml", ".yml")):
        # Workflow YAML declares its steps; other YAML is manifest-like.
        if "\nsteps:" in content or content.lstrip().startswith("steps:"):
            return ("workflow_yaml", None)
        return ("ooc_manifest", "yaml")
    return None


class EvidenceContentGate:
    """Proves validatable evidence content against the shared validators service.

    ``gate`` returns the evidence list with the validation outcome recorded on
    each entry (``validation: "passed"`` | ``"skipped"``) and raises
    ``EvidenceValidationError`` on any violation or fail-closed outcome.
    """

    def __init__(
        self,
        validator: ContentValidator | None = None,
        authorization: Optional[str] = None,
    ):
        self._validator = validator or build_content_validator()
        self._authorization = authorization

    def gate(
        self,
        evidence: list[EvidenceRef],
        authorization: Optional[str] = None,
    ) -> list[EvidenceRef]:
        """Prove every validatable entry; block the build on any failure.

        The caller's SSO token is forwarded verbatim (security by design);
        the per-call ``authorization`` wins over the gate-level default.
        """
        token = authorization if authorization is not None else self._authorization
        gated: list[EvidenceRef] = []
        for ref in evidence:
            classified = classify_artifact(ref)
            if classified is None:
                gated.append(ref)
                continue
            artifact_kind, content_format = classified
            outcome: ValidationOutcome = self._validator.validate_ontology(
                ref.content,
                artifact_kind=artifact_kind,
                authorization=token,
                content_format=content_format,
            )
            if outcome.status == "disabled":
                # Gate disabled (Null adapter): skip explicitly, never silently.
                gated.append(replace(ref, validation="skipped"))
                continue
            if not outcome.valid:
                logger.warning(
                    "evidence content gate blocked %s (%s, status=%s): %s",
                    ref.ref_id,
                    artifact_kind,
                    outcome.status,
                    outcome.detail,
                )
                raise EvidenceValidationError(
                    f"evidence {ref.ref_id!r} failed the validators gate "
                    f"({artifact_kind}, status={outcome.status}): {outcome.detail}"
                )
            gated.append(replace(ref, validation="passed"))
        return gated
