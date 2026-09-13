# Arca Cert — Product Specification (Arca Suite V2.3)

## Mission
Arca Cert transforms validated evidence, trust scores and bench results into audit-ready certification artefacts:
- **Certification packages** (sealed, versioned reports)
- **Evidence binders** (structured evidence references)
- **Readiness assessments** (per-dimension and overall readiness status)
- **Remediation plans** (actionable improvement plans with owners)
- **Validity tracking** (publication windows, seal verification, expiry)

## Scope
- Owns the certification dossier aggregate and its lifecycle (draft → published → expired).
- Receives asynchronous inputs from **arca-bench** (bench results) and **arca-trust** (scores, certification runs).
- Receives synchronous reads from auditors, cockpits and agents.
- Never reads another module's store directly; integration happens only through contracts.

## Autonomy
This module is a bounded context. It does not import business code from other Arca Suite modules and does not access their databases. Integration:
- Synchronous: REST (`contracts/rest/`) and GraphQL (`contracts/graphql/`)
- Agent: MCP (`contracts/mcp/`)
- Asynchronous: Kafka with Avro schemas (`contracts/kafka/`)
- Governance: OOC and evidence bundles

## Core Aggregates
1. **CertificationPackage** — the published dossier with scores, evidence references, seal and validity window.
2. **EvidenceBinder** — an ordered, auditable collection of evidence references.
3. **ReadinessAssessment** — a computed readiness verdict per dimension and overall.
4. **RemediationPlan** — actions required for failing dimensions.

## Security
- OIDC/JWT authentication via `Authorization: Bearer <jwt>`.
- RBAC roles: `cert-reader`, `cert-writer`, `cert-reviewer`, `cert-admin`.
- ABAC rules: reviewers publish only draft dossiers they did not create; admins may republish/revoke; readers cannot mutate.
- Embedded SOC bricks (Collector/Analyzer/Dashboard/Forensics/Responder) are wired into every operation.

## Operations
- REST: `POST /api/v1/dossiers`, `GET /api/v1/dossiers`, `GET /api/v1/dossiers/{id}`, `POST /api/v1/dossiers/{id}/publish`, `GET /api/v1/dossiers/{id}/remediation`, `GET /api/v1/readiness/{target}`, `GET /api/v1/evidence-binders/{dossier_id}`.
- GraphQL: `dossiers`, `dossier(id)`, `buildDossier`, `publishDossier`, `readiness(target)`.
- MCP: `create_cert_package`, `assemble_evidence`, `get_readiness_status`, `get_remediation_plan`, `publish_cert_package`.
- Kafka consumer: subscribes to `bench.results` and automatically builds certification packages from validated bench results.

## Validity & Sealing
- A published package is sealed with SHA-256 over its canonical payload.
- `valid_until` is `published_at + valid_days` (default 90 days).
- Seal verification is exposed on every read; tampering invalidates the seal.

## UI
- `src/ui/` serves an embedded cert cockpit:
  - Package list with status and validity
  - Evidence binder view
  - Report / seal view
  - Readiness dashboard
