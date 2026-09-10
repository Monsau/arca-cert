# ADR-008: SLO & Support

- Status: Proposed
- Date: 2026-09-05
- Owners: see CODEOWNERS

## Context
Auditors expect deterministic, reproducible dossiers.

## Decision
Availability SLO 99.9%, p95 dossier read < 300 ms. Alerts: seal verification failure, unpublished dossier older than 7 days (SEV1).

## Consequences
SLOs are measured on the module's own SLIs; alerting routes to the embedded SOC Responder and to the on-call runbook.

## Compliance
- Product autonomy: this module never reads another module's store directly.
- Integration happens only through published contracts (REST/GraphQL, MCP, Kafka, OOC, evidence).
- Embedded SOC bricks stay wired; OIDC, policies, telemetry and audit are never bypassed.
