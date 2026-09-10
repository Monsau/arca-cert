"""SQL repository for the cert store (ADR-005).

PostgreSQL in production; SQLite is accepted for dev/tests.
"""
import json
import sqlite3
from datetime import datetime

from ..core.domain.cert_models import (
    CertificationDossier,
    DossierStatus,
    EvidenceRef,
    RemediationItem,
    RemediationPlan,
    ScoreInput,
)

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
    seal TEXT
);
CREATE TABLE IF NOT EXISTS remediation_plans (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL UNIQUE,
    items TEXT NOT NULL
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
            " valid_days, status, reviewer, published_at, seal)"
            " VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET"
            " status=excluded.status, reviewer=excluded.reviewer,"
            " published_at=excluded.published_at, seal=excluded.seal",
            (dossier.id, dossier.target,
             json.dumps([s.to_dict() for s in dossier.scores]),
             json.dumps([e.to_dict() for e in dossier.evidence]),
             dossier.valid_days, dossier.status.value, dossier.reviewer,
             dossier.published_at.isoformat() if dossier.published_at else None,
             dossier.seal))
        self._conn.commit()

    def get_dossier(self, dossier_id: str) -> CertificationDossier | None:
        row = self._conn.execute(
            "SELECT * FROM certification_dossiers WHERE id = ?",
            (dossier_id,)).fetchone()
        return self._to_dossier(row) if row else None

    def list_dossiers(self, target: str | None = None) -> list:
        if target:
            rows = self._conn.execute(
                "SELECT * FROM certification_dossiers WHERE target = ?",
                (target,)).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM certification_dossiers").fetchall()
        return [self._to_dossier(r) for r in rows]

    # -- remediation ----------------------------------------------------------

    def save_remediation(self, plan: RemediationPlan) -> None:
        self._conn.execute(
            "INSERT INTO remediation_plans (id, dossier_id, items)"
            " VALUES (?,?,?) ON CONFLICT(dossier_id) DO UPDATE SET"
            " items=excluded.items",
            (plan.id, plan.dossier_id,
             json.dumps([i.to_dict() for i in plan.items])))
        self._conn.commit()

    def get_remediation(self, dossier_id: str) -> RemediationPlan | None:
        row = self._conn.execute(
            "SELECT * FROM remediation_plans WHERE dossier_id = ?",
            (dossier_id,)).fetchone()
        if row is None:
            return None
        return RemediationPlan(
            id=row["id"], dossier_id=row["dossier_id"],
            items=[RemediationItem(**i) for i in json.loads(row["items"])])

    # -- internals ------------------------------------------------------------

    def _to_dossier(self, row) -> CertificationDossier:
        return CertificationDossier(
            id=row["id"], target=row["target"],
            scores=[ScoreInput(**s) for s in json.loads(row["scores"])],
            evidence=[EvidenceRef(**e) for e in json.loads(row["evidence"])],
            valid_days=row["valid_days"],
            status=DossierStatus(row["status"]),
            reviewer=row["reviewer"],
            published_at=_dt(row["published_at"]),
            seal=row["seal"])


def connect_sqlite(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _dt(value):
    return datetime.fromisoformat(value) if value else None
