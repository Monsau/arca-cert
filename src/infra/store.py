"""SQL repository for the cert store (ADR-005, ADR-009).

SQLAlchemy backend: PostgreSQL in production (via DATABASE_URL, psycopg v3
driver); SQLite is accepted for dev/tests (in-memory by default).
Same persistence profile as arca-packs and arca-flow (suite platform profile).
"""
import json
from datetime import datetime

from sqlalchemy import Float, Integer, String, Text, create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool

from ..core.domain.cert_models import (
    BenchResult,
    CertificationDossier,
    CertificationPackage,
    DossierStatus,
    EvidenceBinder,
    EvidenceRef,
    ReadinessAssessment,
    ReadinessLevel,
    RemediationItem,
    RemediationPlan,
    ScoreInput,
)
from ..core.domain.provenance import ProvenanceTraceRef


class Base(DeclarativeBase):
    pass


class DossierRow(Base):
    __tablename__ = "certification_dossiers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target: Mapped[str] = mapped_column(String(256))
    scores: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    valid_days: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    reviewer: Mapped[str | None] = mapped_column(String(256), nullable=True)
    published_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    seal: Mapped[str | None] = mapped_column(String(256), nullable=True)
    revoked_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class RemediationPlanRow(Base):
    __tablename__ = "remediation_plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dossier_id: Mapped[str] = mapped_column(String(64), unique=True)
    items: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(String(64), nullable=True)


class EvidenceBinderRow(Base):
    __tablename__ = "evidence_binders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dossier_id: Mapped[str] = mapped_column(String(64), unique=True)
    evidence: Mapped[str] = mapped_column(Text)
    assembled_at: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ReadinessAssessmentRow(Base):
    __tablename__ = "readiness_assessments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target: Mapped[str] = mapped_column(String(256))
    dimension_scores: Mapped[str] = mapped_column(Text)
    threshold: Mapped[float] = mapped_column(Float)
    assessed_at: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CertificationPackageRow(Base):
    __tablename__ = "certification_packages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dossier_id: Mapped[str] = mapped_column(String(64), unique=True)
    assessment_id: Mapped[str] = mapped_column(String(64))
    binder_id: Mapped[str] = mapped_column(String(64))
    remediation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProvenanceTraceRefRow(Base):
    __tablename__ = "provenance_trace_refs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target: Mapped[str] = mapped_column(String(256))
    trace_id: Mapped[str] = mapped_column(String(128))
    activity: Mapped[str] = mapped_column(String(256))
    trace_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    occurred_at: Mapped[str] = mapped_column(String(64))


class SqlCertRepository:
    """SQL-backed repository for certification dossiers and related records.

    Accepts any SQLAlchemy DSN. A bare ``postgresql://`` DSN is rewritten to
    ``postgresql+psycopg://`` because the image ships psycopg v3, not
    psycopg2 (same convention as arca-packs / arca-flow).
    """

    def __init__(self, dsn: str):
        if dsn.startswith("postgresql://"):
            dsn = "postgresql+psycopg://" + dsn[len("postgresql://"):]
        kwargs: dict = {}
        if ":memory:" in dsn:
            # A default in-memory SQLite database would use one connection per
            # thread and lose data across sessions; pin a single shared
            # connection instead so the repository behaves like a real store.
            kwargs = {
                "poolclass": StaticPool,
                "connect_args": {"check_same_thread": False},
            }
        self.engine = create_engine(dsn, **kwargs)
        Base.metadata.create_all(self.engine)
        self._sessionmaker = sessionmaker(bind=self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self._sessionmaker()

    # -- dossiers -------------------------------------------------------------

    def save_dossier(self, dossier: CertificationDossier) -> None:
        with self.session() as s:
            row = s.get(DossierRow, dossier.id)
            if row is None:
                s.add(DossierRow(
                    id=dossier.id,
                    target=dossier.target,
                    scores=json.dumps([sc.to_dict() for sc in dossier.scores]),
                    evidence=json.dumps([e.to_dict() for e in dossier.evidence]),
                    valid_days=dossier.valid_days,
                    status=dossier.status.value,
                    reviewer=dossier.reviewer,
                    published_at=dossier.published_at.isoformat()
                    if dossier.published_at else None,
                    seal=dossier.seal,
                    revoked_at=dossier.revoked_at.isoformat()
                    if dossier.revoked_at else None,
                    revocation_reason=dossier.revocation_reason,
                ))
            else:
                # Upsert only the lifecycle fields; scores and evidence are
                # immutable once stored (same semantics as the previous
                # sqlite ON CONFLICT clause).
                row.status = dossier.status.value
                row.reviewer = dossier.reviewer
                row.published_at = (dossier.published_at.isoformat()
                                    if dossier.published_at else None)
                row.seal = dossier.seal
                row.revoked_at = (dossier.revoked_at.isoformat()
                                  if dossier.revoked_at else None)
                row.revocation_reason = dossier.revocation_reason
            s.commit()

    def get_dossier(self, dossier_id: str) -> CertificationDossier | None:
        with self.session() as s:
            row = s.get(DossierRow, dossier_id)
            return self._to_dossier(row) if row else None

    def list_dossiers(self, target: str | None = None) -> list:
        with self.session() as s:
            q = s.query(DossierRow)
            if target:
                q = q.filter_by(target=target)
            rows = q.all()
            return [self._to_dossier(r) for r in rows]

    # -- remediation ----------------------------------------------------------

    def save_remediation(self, plan: RemediationPlan) -> None:
        with self.session() as s:
            row = s.query(RemediationPlanRow).filter_by(
                dossier_id=plan.dossier_id).one_or_none()
            if row is None:
                s.add(RemediationPlanRow(
                    id=plan.id,
                    dossier_id=plan.dossier_id,
                    items=json.dumps([i.to_dict() for i in plan.items]),
                    created_at=plan.created_at.isoformat(),
                ))
            else:
                row.items = json.dumps([i.to_dict() for i in plan.items])
                row.created_at = plan.created_at.isoformat()
            s.commit()

    def get_remediation(self, dossier_id: str) -> RemediationPlan | None:
        with self.session() as s:
            row = s.query(RemediationPlanRow).filter_by(
                dossier_id=dossier_id).one_or_none()
            if row is None:
                return None
            return RemediationPlan(
                id=row.id,
                dossier_id=row.dossier_id,
                items=[RemediationItem(**i) for i in json.loads(row.items)],
                created_at=_dt(row.created_at),
            )

    # -- evidence binders -----------------------------------------------------

    def save_binder(self, binder: EvidenceBinder) -> None:
        with self.session() as s:
            row = s.query(EvidenceBinderRow).filter_by(
                dossier_id=binder.dossier_id).one_or_none()
            if row is None:
                s.add(EvidenceBinderRow(
                    id=binder.id,
                    dossier_id=binder.dossier_id,
                    evidence=json.dumps([e.to_dict() for e in binder.evidence]),
                    assembled_at=binder.assembled_at.isoformat(),
                ))
            else:
                row.evidence = json.dumps([e.to_dict() for e in binder.evidence])
                row.assembled_at = binder.assembled_at.isoformat()
            s.commit()

    def get_binder(self, dossier_id: str) -> EvidenceBinder | None:
        with self.session() as s:
            row = s.query(EvidenceBinderRow).filter_by(
                dossier_id=dossier_id).one_or_none()
            return self._to_binder(row) if row else None

    def get_binder_by_id(self, binder_id: str) -> EvidenceBinder | None:
        with self.session() as s:
            row = s.get(EvidenceBinderRow, binder_id)
            return self._to_binder(row) if row else None

    def _to_binder(self, row: EvidenceBinderRow) -> EvidenceBinder:
        return EvidenceBinder(
            id=row.id,
            dossier_id=row.dossier_id,
            evidence=[EvidenceRef(**e) for e in json.loads(row.evidence)],
            assembled_at=_dt(row.assembled_at),
        )

    # -- readiness assessments ------------------------------------------------

    def save_assessment(self, assessment: ReadinessAssessment) -> None:
        with self.session() as s:
            row = s.get(ReadinessAssessmentRow, assessment.id)
            if row is None:
                s.add(ReadinessAssessmentRow(
                    id=assessment.id,
                    target=assessment.target,
                    dimension_scores=json.dumps(
                        [sc.to_dict() for sc in assessment.dimension_scores]),
                    threshold=assessment.threshold,
                    assessed_at=assessment.assessed_at.isoformat(),
                ))
            else:
                row.dimension_scores = json.dumps(
                    [sc.to_dict() for sc in assessment.dimension_scores])
                row.threshold = assessment.threshold
                row.assessed_at = assessment.assessed_at.isoformat()
            s.commit()

    def get_assessment(self, assessment_id: str) -> ReadinessAssessment | None:
        with self.session() as s:
            row = s.get(ReadinessAssessmentRow, assessment_id)
            if row is None:
                return None
            return self._to_assessment(row)

    def list_assessments(self, target: str | None = None) -> list:
        with self.session() as s:
            q = s.query(ReadinessAssessmentRow)
            if target:
                q = q.filter_by(target=target)
            rows = q.all()
            return [self._to_assessment(r) for r in rows]

    # -- provenance trace refs ------------------------------------------------

    def save_provenance_trace_ref(self, ref: ProvenanceTraceRef) -> None:
        with self.session() as s:
            row = s.get(ProvenanceTraceRefRow, ref.id)
            if row is None:
                s.add(ProvenanceTraceRefRow(
                    id=ref.id,
                    target=ref.target,
                    trace_id=ref.trace_id,
                    activity=ref.activity,
                    trace_uri=ref.trace_uri,
                    occurred_at=ref.occurred_at.isoformat(),
                ))
            else:
                row.activity = ref.activity
                row.trace_uri = ref.trace_uri
                row.occurred_at = ref.occurred_at.isoformat()
            s.commit()

    def list_provenance_trace_refs(self, target: str) -> list:
        with self.session() as s:
            rows = (s.query(ProvenanceTraceRefRow)
                    .filter_by(target=target)
                    .order_by(ProvenanceTraceRefRow.occurred_at.desc())
                    .all())
            return [self._to_provenance_trace_ref(r) for r in rows]

    # -- certification packages -----------------------------------------------

    def save_package(self, package: CertificationPackage) -> None:
        with self.session() as s:
            row = s.query(CertificationPackageRow).filter_by(
                dossier_id=package.dossier.id).one_or_none()
            if row is None:
                s.add(CertificationPackageRow(
                    id=package.id,
                    dossier_id=package.dossier.id,
                    assessment_id=package.assessment.id,
                    binder_id=package.binder.id,
                    remediation_id=package.remediation_id,
                    generated_at=package.generated_at.isoformat(),
                ))
            else:
                row.assessment_id = package.assessment.id
                row.binder_id = package.binder.id
                row.remediation_id = package.remediation_id
                row.generated_at = package.generated_at.isoformat()
            s.commit()

    def get_package(self, package_id: str) -> CertificationPackage | None:
        with self.session() as s:
            row = s.get(CertificationPackageRow, package_id)
            if row is None:
                return None
            return self._to_package(row)

    def get_package_by_dossier(self, dossier_id: str) -> CertificationPackage | None:
        with self.session() as s:
            row = s.query(CertificationPackageRow).filter_by(
                dossier_id=dossier_id).one_or_none()
            if row is None:
                return None
            return self._to_package(row)

    def list_packages(self, target: str | None = None) -> list:
        with self.session() as s:
            q = s.query(CertificationPackageRow)
            if target:
                q = q.join(DossierRow,
                           CertificationPackageRow.dossier_id == DossierRow.id) \
                     .filter(DossierRow.target == target)
            rows = q.all()
            return [p for p in (self._to_package(r) for r in rows) if p is not None]

    # -- internals ------------------------------------------------------------

    def _to_dossier(self, row: DossierRow) -> CertificationDossier:
        return CertificationDossier(
            id=row.id,
            target=row.target,
            scores=[ScoreInput(**sc) for sc in json.loads(row.scores)],
            evidence=[EvidenceRef(**e) for e in json.loads(row.evidence)],
            valid_days=row.valid_days,
            status=DossierStatus(row.status),
            reviewer=row.reviewer,
            published_at=_dt(row.published_at),
            seal=row.seal,
            revoked_at=_dt(row.revoked_at),
            revocation_reason=row.revocation_reason,
        )

    def _to_assessment(self, row: ReadinessAssessmentRow) -> ReadinessAssessment:
        return ReadinessAssessment(
            id=row.id,
            target=row.target,
            dimension_scores=[ScoreInput(**sc)
                              for sc in json.loads(row.dimension_scores)],
            threshold=row.threshold,
            assessed_at=_dt(row.assessed_at),
        )

    def _to_package(self, row: CertificationPackageRow) -> CertificationPackage | None:
        dossier = self.get_dossier(row.dossier_id)
        assessment = self.get_assessment(row.assessment_id)
        binder = self.get_binder_by_id(row.binder_id)
        if dossier is None or assessment is None or binder is None:
            return None
        return CertificationPackage(
            id=row.id,
            dossier=dossier,
            assessment=assessment,
            binder=binder,
            remediation_id=row.remediation_id,
            generated_at=_dt(row.generated_at),
        )

    def _to_provenance_trace_ref(self, row: ProvenanceTraceRefRow) -> ProvenanceTraceRef:
        return ProvenanceTraceRef(
            id=row.id,
            target=row.target,
            trace_id=row.trace_id,
            activity=row.activity,
            trace_uri=row.trace_uri,
            occurred_at=_dt(row.occurred_at),
        )


def connect_sqlite(path: str = ":memory:") -> str:
    """Return a SQLAlchemy DSN for a SQLite database (in-memory by default).

    Kept as the dev/test factory so tests and local runs get a lightweight
    backend without a PostgreSQL server.
    """
    if path == ":memory:":
        return "sqlite:///:memory:"
    return f"sqlite:///{path}"


def _dt(value):
    return datetime.fromisoformat(value) if value else None
