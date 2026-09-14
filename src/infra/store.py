"""SQL repository for the cert store (ADR-005, ADR-009).

PostgreSQL in production; SQLite is accepted for dev/tests.
"""
import json
import sqlite3
from datetime import datetime

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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS certification_dossiers (
    id TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    scores TEXT NOT NULL,
    evidence TEXT NOT NULL,
    valid_days INTEGER NOT NULL,
    status TEXT NOT NULL,
    reviewer TEXT,
    published_at TEXT,
    seal TEXT,
    revoked_at TEXT,
    revocation_reason TEXT
);
CREATE TABLE IF NOT EXISTS remediation_plans (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL UNIQUE,
    items TEXT NOT NULL,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS evidence_binders (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL UNIQUE,
    evidence TEXT NOT NULL,
    assembled_at TEXT
);
CREATE TABLE IF NOT EXISTS readiness_assessments (
    id TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    dimension_scores TEXT NOT NULL,
    threshold REAL NOT NULL,
    assessed_at TEXT
);
CREATE TABLE IF NOT EXISTS certification_packages (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL UNIQUE,
    assessment_id TEXT NOT NULL,
    binder_id TEXT NOT NULL,
    remediation_id TEXT,
    generated_at TEXT
);
CREATE TABLE IF NOT EXISTS provenance_trace_refs (
    id TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    activity TEXT NOT NULL,
    trace_uri TEXT,
    occurred_at TEXT NOT NULL
);
"""


class SqlCertRepository:
    def __init__(self, connection: sqlite3.Connection):
        self._conn = connection
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- dossiers -------------------------------------------------------------

    def save_dossier(self, dossier: CertificationDossier) -> None:
        self._conn.execute(
            "INSERT INTO certification_dossiers (id, target, scores, evidence,"
            " valid_days, status, reviewer, published_at, seal, revoked_at, revocation_reason)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET"
            " status=excluded.status, reviewer=excluded.reviewer,"
            " published_at=excluded.published_at, seal=excluded.seal,"
            " revoked_at=excluded.revoked_at, revocation_reason=excluded.revocation_reason",
            (
                dossier.id,
                dossier.target,
                json.dumps([s.to_dict() for s in dossier.scores]),
                json.dumps([e.to_dict() for e in dossier.evidence]),
                dossier.valid_days,
                dossier.status.value,
                dossier.reviewer,
                dossier.published_at.isoformat() if dossier.published_at else None,
                dossier.seal,
                dossier.revoked_at.isoformat() if dossier.revoked_at else None,
                dossier.revocation_reason,
            ),
        )
        self._conn.commit()

    def get_dossier(self, dossier_id: str) -> CertificationDossier | None:
        row = self._conn.execute(
            "SELECT * FROM certification_dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        return self._to_dossier(row) if row else None

    def list_dossiers(self, target: str | None = None) -> list:
        if target:
            rows = self._conn.execute(
                "SELECT * FROM certification_dossiers WHERE target = ?", (target,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM certification_dossiers").fetchall()
        return [self._to_dossier(r) for r in rows]

    # -- remediation ----------------------------------------------------------

    def save_remediation(self, plan: RemediationPlan) -> None:
        self._conn.execute(
            "INSERT INTO remediation_plans (id, dossier_id, items, created_at)"
            " VALUES (?,?,?,?) ON CONFLICT(dossier_id) DO UPDATE SET"
            " items=excluded.items, created_at=excluded.created_at",
            (
                plan.id,
                plan.dossier_id,
                json.dumps([i.to_dict() for i in plan.items]),
                plan.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def get_remediation(self, dossier_id: str) -> RemediationPlan | None:
        row = self._conn.execute(
            "SELECT * FROM remediation_plans WHERE dossier_id = ?", (dossier_id,)
        ).fetchone()
        if row is None:
            return None
        return RemediationPlan(
            id=row["id"],
            dossier_id=row["dossier_id"],
            items=[RemediationItem(**i) for i in json.loads(row["items"])],
            created_at=_dt(row["created_at"]),
        )

    # -- evidence binders -----------------------------------------------------

    def save_binder(self, binder: EvidenceBinder) -> None:
        self._conn.execute(
            "INSERT INTO evidence_binders (id, dossier_id, evidence, assembled_at)"
            " VALUES (?,?,?,?) ON CONFLICT(dossier_id) DO UPDATE SET"
            " evidence=excluded.evidence, assembled_at=excluded.assembled_at",
            (
                binder.id,
                binder.dossier_id,
                json.dumps([e.to_dict() for e in binder.evidence]),
                binder.assembled_at.isoformat(),
            ),
        )
        self._conn.commit()

    def get_binder(self, dossier_id: str) -> EvidenceBinder | None:
        row = self._conn.execute(
            "SELECT * FROM evidence_binders WHERE dossier_id = ?", (dossier_id,)
        ).fetchone()
        return self._to_binder(row) if row else None

    def get_binder_by_id(self, binder_id: str) -> EvidenceBinder | None:
        row = self._conn.execute(
            "SELECT * FROM evidence_binders WHERE id = ?", (binder_id,)
        ).fetchone()
        return self._to_binder(row) if row else None

    def _to_binder(self, row) -> EvidenceBinder:
        return EvidenceBinder(
            id=row["id"],
            dossier_id=row["dossier_id"],
            evidence=[EvidenceRef(**e) for e in json.loads(row["evidence"])],
            assembled_at=_dt(row["assembled_at"]),
        )

    # -- readiness assessments ------------------------------------------------

    def save_assessment(self, assessment: ReadinessAssessment) -> None:
        self._conn.execute(
            "INSERT INTO readiness_assessments (id, target, dimension_scores, threshold, assessed_at)"
            " VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET"
            " dimension_scores=excluded.dimension_scores, threshold=excluded.threshold,"
            " assessed_at=excluded.assessed_at",
            (
                assessment.id,
                assessment.target,
                json.dumps([s.to_dict() for s in assessment.dimension_scores]),
                assessment.threshold,
                assessment.assessed_at.isoformat(),
            ),
        )
        self._conn.commit()

    def get_assessment(self, assessment_id: str) -> ReadinessAssessment | None:
        row = self._conn.execute(
            "SELECT * FROM readiness_assessments WHERE id = ?", (assessment_id,)
        ).fetchone()
        if row is None:
            return None
        return ReadinessAssessment(
            id=row["id"],
            target=row["target"],
            dimension_scores=[ScoreInput(**s) for s in json.loads(row["dimension_scores"])],
            threshold=row["threshold"],
            assessed_at=_dt(row["assessed_at"]),
        )

    def list_assessments(self, target: str | None = None) -> list:
        if target:
            rows = self._conn.execute(
                "SELECT * FROM readiness_assessments WHERE target = ?", (target,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM readiness_assessments").fetchall()
        return [self._to_assessment(r) for r in rows]

    # -- provenance trace refs ------------------------------------------------

    def save_provenance_trace_ref(self, ref: ProvenanceTraceRef) -> None:
        self._conn.execute(
            "INSERT INTO provenance_trace_refs (id, target, trace_id, activity,"
            " trace_uri, occurred_at) VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET activity=excluded.activity,"
            " trace_uri=excluded.trace_uri, occurred_at=excluded.occurred_at",
            (ref.id, ref.target, ref.trace_id, ref.activity, ref.trace_uri,
             ref.occurred_at.isoformat()),
        )
        self._conn.commit()

    def list_provenance_trace_refs(self, target: str) -> list:
        rows = self._conn.execute(
            "SELECT * FROM provenance_trace_refs WHERE target = ?"
            " ORDER BY occurred_at DESC",
            (target,),
        ).fetchall()
        return [self._to_provenance_trace_ref(r) for r in rows]

    # -- certification packages -----------------------------------------------

    def save_package(self, package: CertificationPackage) -> None:
        self._conn.execute(
            "INSERT INTO certification_packages (id, dossier_id, assessment_id, binder_id,"
            " remediation_id, generated_at) VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(dossier_id) DO UPDATE SET"
            " assessment_id=excluded.assessment_id, binder_id=excluded.binder_id,"
            " remediation_id=excluded.remediation_id, generated_at=excluded.generated_at",
            (
                package.id,
                package.dossier.id,
                package.assessment.id,
                package.binder.id,
                package.remediation_id,
                package.generated_at.isoformat(),
            ),
        )
        self._conn.commit()

    def get_package(self, package_id: str) -> CertificationPackage | None:
        row = self._conn.execute(
            "SELECT * FROM certification_packages WHERE id = ?", (package_id,)
        ).fetchone()
        if row is None:
            return None
        return self._to_package(row)

    def get_package_by_dossier(self, dossier_id: str) -> CertificationPackage | None:
        row = self._conn.execute(
            "SELECT * FROM certification_packages WHERE dossier_id = ?", (dossier_id,)
        ).fetchone()
        if row is None:
            return None
        return self._to_package(row)

    def list_packages(self, target: str | None = None) -> list:
        if target:
            rows = self._conn.execute(
                "SELECT p.* FROM certification_packages p"
                " JOIN certification_dossiers d ON p.dossier_id = d.id"
                " WHERE d.target = ?",
                (target,),
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM certification_packages").fetchall()
        return [self._to_package(r) for r in rows]

    # -- internals ------------------------------------------------------------

    def _to_dossier(self, row) -> CertificationDossier:
        return CertificationDossier(
            id=row["id"],
            target=row["target"],
            scores=[ScoreInput(**s) for s in json.loads(row["scores"])],
            evidence=[EvidenceRef(**e) for e in json.loads(row["evidence"])],
            valid_days=row["valid_days"],
            status=DossierStatus(row["status"]),
            reviewer=row["reviewer"],
            published_at=_dt(row["published_at"]),
            seal=row["seal"],
            revoked_at=_dt(row["revoked_at"]),
            revocation_reason=row["revocation_reason"],
        )

    def _to_assessment(self, row) -> ReadinessAssessment:
        return ReadinessAssessment(
            id=row["id"],
            target=row["target"],
            dimension_scores=[ScoreInput(**s) for s in json.loads(row["dimension_scores"])],
            threshold=row["threshold"],
            assessed_at=_dt(row["assessed_at"]),
        )

    def _to_package(self, row) -> CertificationPackage:
        dossier = self.get_dossier(row["dossier_id"])
        assessment = self.get_assessment(row["assessment_id"])
        binder = self.get_binder_by_id(row["binder_id"])
        if dossier is None or assessment is None or binder is None:
            return None
        return CertificationPackage(
            id=row["id"],
            dossier=dossier,
            assessment=assessment,
            binder=binder,
            remediation_id=row["remediation_id"],
            generated_at=_dt(row["generated_at"]),
        )

    def _to_provenance_trace_ref(self, row) -> ProvenanceTraceRef:
        return ProvenanceTraceRef(
            id=row["id"],
            target=row["target"],
            trace_id=row["trace_id"],
            activity=row["activity"],
            trace_uri=row["trace_uri"],
            occurred_at=_dt(row["occurred_at"]),
        )


def connect_sqlite(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _dt(value):
    return datetime.fromisoformat(value) if value else None
