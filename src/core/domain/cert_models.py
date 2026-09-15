"""Certification domain model for arca-cert (ADR-001, ADR-005, ADR-009).

Aggregates:
- CertificationDossier: the audit-ready package with scores, test results,
  evidence references and a validity window.
- RemediationPlan: the list of remediation actions required when the dossier
  contains failing dimensions.
- EvidenceBinder: an auditable, ordered collection of evidence references.
- ReadinessAssessment: per-dimension and overall readiness verdict.
- CertificationPackage: a published, sealed report view of a dossier.

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
    REVOKED = "revoked"


class ReadinessLevel(str, Enum):
    READY = "ready"
    CONDITIONAL = "conditional"
    NOT_READY = "not_ready"


@dataclass(frozen=True)
class EvidenceRef:
    source: str
    ref_id: str
    description: str = ""
    collected_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict:
        collected_at = self.collected_at
        if isinstance(collected_at, datetime):
            collected_at = collected_at.isoformat()
        return {
            "source": self.source,
            "ref_id": self.ref_id,
            "description": self.description,
            "collected_at": collected_at,
        }


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
class BenchResult:
    bench_id: str
    target: str
    dimension: str
    passed: bool
    score: float
    evidence: list = field(default_factory=list)

    def __post_init__(self):
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("bench score must be in [0, 1]")

    def to_dict(self) -> dict:
        return {
            "bench_id": self.bench_id,
            "target": self.target,
            "dimension": self.dimension,
            "passed": self.passed,
            "score": self.score,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class RemediationItem:
    risk: str
    action: str
    owner: str
    due_days: int = 30
    dimension: str = ""

    def to_dict(self) -> dict:
        return {
            "risk": self.risk,
            "action": self.action,
            "owner": self.owner,
            "due_days": self.due_days,
            "dimension": self.dimension,
        }


@dataclass
class EvidenceBinder:
    dossier_id: str
    evidence: list = field(default_factory=list)
    assembled_at: datetime = field(default_factory=_now)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def add(self, ref: EvidenceRef) -> None:
        self.evidence.append(ref)
        self.assembled_at = _now()

    def by_source(self, source: str) -> list:
        return [e for e in self.evidence if e.source == source]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dossier_id": self.dossier_id,
            "assembled_at": self.assembled_at.isoformat(),
            "evidence": [e.to_dict() for e in self.evidence],
            "count": len(self.evidence),
        }


@dataclass
class ReadinessAssessment:
    target: str
    dimension_scores: list
    threshold: float = 0.7
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    assessed_at: datetime = field(default_factory=_now)

    @property
    def overall_score(self) -> float:
        if not self.dimension_scores:
            return 0.0
        return round(sum(s.value for s in self.dimension_scores) / len(self.dimension_scores), 4)

    @property
    def level(self) -> ReadinessLevel:
        failing = [s for s in self.dimension_scores if s.value < self.threshold]
        if not failing:
            return ReadinessLevel.READY
        if any(s.value < self.threshold / 2 for s in failing):
            return ReadinessLevel.NOT_READY
        return ReadinessLevel.CONDITIONAL

    def failing_dimensions(self) -> list:
        return [s.dimension for s in self.dimension_scores if s.value < self.threshold]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "target": self.target,
            "overall_score": self.overall_score,
            "level": self.level.value,
            "threshold": self.threshold,
            "assessed_at": self.assessed_at.isoformat(),
            "dimensions": [s.to_dict() for s in self.dimension_scores],
            "failing_dimensions": self.failing_dimensions(),
        }


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
    revoked_at: datetime | None = None
    revocation_reason: str | None = None

    def _canonical(self) -> bytes:
        payload = {
            "id": self.id,
            "target": self.target,
            "scores": sorted((s.to_dict() for s in self.scores), key=lambda x: x["dimension"]),
            "evidence": sorted((e.to_dict() for e in self.evidence), key=lambda x: x["ref_id"]),
            "reviewer": self.reviewer,
            "status": self.status.value,
        }
        return json.dumps(payload, sort_keys=True).encode("utf-8")

    @property
    def valid_until(self) -> datetime:
        base = self.published_at or _now()
        return base + timedelta(days=self.valid_days)

    @property
    def is_expired(self) -> bool:
        return self.status == DossierStatus.PUBLISHED and _now() > self.valid_until

    def publish(self, reviewer: str, sealer=None) -> None:
        if self.status is not DossierStatus.DRAFT:
            raise ValueError(f"dossier {self.id} is {self.status.value}")
        if not reviewer:
            raise ValueError("reviewer identity is mandatory")
        self.reviewer = reviewer
        self.status = DossierStatus.PUBLISHED
        self.published_at = _now()
        canonical = self._canonical()
        self.seal = sealer(canonical) if sealer else hashlib.sha256(canonical).hexdigest()

    def revoke(self, reviewer: str, reason: str) -> None:
        if self.status is not DossierStatus.PUBLISHED:
            raise ValueError(f"dossier {self.id} is {self.status.value}")
        if not reviewer or not reason:
            raise ValueError("reviewer identity and reason are mandatory")
        self.status = DossierStatus.REVOKED
        self.revoked_at = _now()
        self.revocation_reason = reason
        self.seal = None

    def verify_seal(self, verifier=None) -> bool:
        if self.seal is None or self.status != DossierStatus.PUBLISHED:
            return False
        canonical = self._canonical()
        if verifier:
            return verifier(canonical, self.seal)
        return self.seal == hashlib.sha256(canonical).hexdigest()

    def failing_dimensions(self, threshold: float = 0.7) -> list:
        return [s.dimension for s in self.scores if s.value < threshold]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "target": self.target,
            "status": self.status.value,
            "scores": [s.to_dict() for s in self.scores],
            "evidence": [e.to_dict() for e in self.evidence],
            "reviewer": self.reviewer,
            "valid_until": self.valid_until.isoformat(),
            "is_expired": self.is_expired,
            "seal": self.seal,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "revocation_reason": self.revocation_reason,
        }


@dataclass
class CertificationPackage:
    dossier: CertificationDossier
    assessment: ReadinessAssessment
    binder: EvidenceBinder
    remediation_id: str | None = None
    generated_at: datetime = field(default_factory=_now)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dossier": self.dossier.to_dict(),
            "assessment": self.assessment.to_dict(),
            "binder": self.binder.to_dict(),
            "remediation_id": self.remediation_id,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass
class RemediationPlan:
    dossier_id: str
    items: list
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dossier_id": self.dossier_id,
            "created_at": self.created_at.isoformat(),
            "items": [i.to_dict() for i in self.items],
        }
