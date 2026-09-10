# ADR-001: Bounded Context & Ownership

- Status: Accepted
- Date: 2026-09-05
- Owners: see CODEOWNERS

## Context
Arca Cert owns the audit-ready dossier. Bounded context aggregates: CertificationDossier (aggregate root) and RemediationPlan. Inputs come only through contracts from arca-trust and arca-bench.

## Decision
CertificationDossier and RemediationPlan are owned here. Dossiers are sealed, versioned and carry a mandatory reviewer identity before publication.
- Pass 2: materialized in code (domain, service, SQL repository, REST and MCP handlers).

## Consequences
The bounded context is owned by this repo's CODEOWNERS; aggregates can only be modified through this module's APIs and events.

## Compliance
- Product autonomy: this module never reads another module's store directly.
- Integration happens only through published contracts (REST/GraphQL, MCP, Kafka, OOC, evidence).
- Embedded SOC bricks stay wired; OIDC, policies, telemetry and audit are never bypassed.
