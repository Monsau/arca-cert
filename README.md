# Arca Cert - Certification Dossier Builder

## Mission
Arca Cert assembles certification dossiers and remediation plans from trust scores, bench results and evidence bundles. It produces the versioned reports required by auditors and regulators.

## Status
Implemented and test-covered (103 tests: unit, integration, contract). The
module builds certification dossiers, sealed certification packages, evidence
binders, readiness assessments and remediation plans; it consumes bench
results and optional ArcaQ PROV-O traces, and enforces RBAC/ABAC plus the OOC
gate on every mutation.

## UI route
The embedded UI is served at `/cert` (static mount). This is deliberate: the
Suite portal (`arca-platform-k8s`, portal config `ui_base: /cert`) links to
`/cert`, and the `cert-root-redirect` ingress middleware rewrites `/` to
`/cert`. Do not rename the mount to `/ui/` without updating the portal and
ingress in `arca-platform-k8s`.

## Autonomy
This repository is an autonomous product. It does not depend on the code or the
database of any other Arca Suite module. Integration with other modules happens
exclusively through contracts:

- Synchronous APIs: REST and GraphQL (`contracts/rest/`, `contracts/graphql/`)
- Agent capabilities: MCP (`contracts/mcp/`)
- Asynchronous events: Kafka with Avro schemas (`contracts/kafka/`)
- Governance: Operational Ontology Contracts (OOC) and evidence bundles

## Embedded SOC
The module embeds its five security bricks in `src/infra/soc.py`:
Collector, Analyzer, Dashboard, Forensics, Responder. No bypass is allowed.

## Layout
See the standard layout documented in CONTRIBUTING.md:
`src/` (api, core, infra, policies), `tests/`, `contracts/`, `docs/`, `scripts/`.

## Quickstart
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
uvicorn src.main:app --host 0.0.0.0 --port 8093
curl http://localhost:8093/healthz
```

## Dependencies
None at code level (autonomous product). Contract-level inputs: arca-trust (scores, certification runs), arca-bench (test results, scores), arca-flow (evidence bundles).

## Operations
- Runbooks: `docs/runbooks/`
- ADRs: `docs/adr/`
- Data governance: `docs/data-governance.md`
- Kubernetes manifests: sibling repository `arca-cert-k8s`
