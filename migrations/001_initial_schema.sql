-- Auto-generated initial migration from store._SCHEMA

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
