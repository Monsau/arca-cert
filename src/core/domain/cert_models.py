"""Certification domain model for arca-cert (ADR-001, ADR-005).

Aggregates:
- CertificationDossier: the audit-ready package with scores, test results,
  evidence references and a validity window.
- RemediationPlan: the list of remediation actions required when the dossier
  contains failing dimensions.

A published dossier is sealed (SHA-256) and carries a mandatory reviewer identity.
"""
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


def _now():
    return datetime.now(timezone.utc)


class DossierStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


@dataclass(frozen=True)
class EvidenceRef:
    source: str
    ref_id: str
    description: str = ""

    def to_dict(self) -> dict:
        return {"source": self.source, "ref_id": self.ref_id,
                "description": self.description}


@dataclass(frozen=True)
class ScoreInput:
    dimension: str
    value: float

    def __post_init__(self):
        if not 0.0 <= self.value <= 1.0:
            raise ValueError("score value must be in [0, 1]")

    def to_dict(self) -> dict:
        return {"dimension": self.dimension, "value": self.value}


@dataclass(frozen=True)
class RemediationItem:
    risk: str
    action: str
    owner: str

    def to_dict(self) -> dict:
        return {"risk": self.risk, "action": self.action, "owner": self.owner}


@dataclass
class CertificationDossier:
    target: str
    scores: list
    evidence: list
    valid_days: int = 90
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: DossierStatus = DossierStatus.DRAFT
    reviewer: str | None = None
    published_at: datetime | None = None
    seal: str | None = None

    def _canonical(self) -> bytes:
        payload = {
            "id": self.id, "target": self.target,
            "scores": sorted((s.to_dict() for s in self.scores), key=lambda x: x["dimension"]),
            "evidence": sorted((e.to_dict() for e in self.evidence), key=lambda x: x["ref_id"]),
            "reviewer": self.reviewer,
        }
        return json.dumps(payload, sort_keys=True).encode("utf-8")

    @property
    def valid_until(self) -> datetime:
        base = self.published_at or _now()
        return base + timedelta(days=self.valid_days)

    def publish(self, reviewer: str) -> None:
        if self.status is not DossierStatus.DRAFT:
            raise ValueError(f"dossier {self.id} is {self.status.value}")
        if not reviewer:
            raise ValueError("reviewer identity is mandatory")
        self.reviewer = reviewer
        self.seal = hashlib.sha256(self._canonical()).hexdigest()
        self.status = DossierStatus.PUBLISHED
        self.published_at = _now()

    def verify_seal(self) -> bool:
        if self.seal is None:
            return False
        return self.seal == hashlib.sha256(self._canonical()).hexdigest()

    def failing_dimensions(self, threshold: float = 0.7) -> list:
        return [s.dimension for s in self.scores if s.value < threshold]

    def to_dict(self) -> dict:
        return {
            "id": self.id, "target": self.target,
            "status": self.status.value,
            "scores": [s.to_dict() for s in self.scores],
            "evidence": [e.to_dict() for e in self.evidence],
            "reviewer": self.reviewer,
            "valid_until": self.valid_until.isoformat(),
            "seal": self.seal,
        }


@dataclass
class RemediationPlan:
    dossier_id: str
    items: list
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {"id": self.id, "dossier_id": self.dossier_id,
                "items": [i.to_dict() for i in self.items]}
