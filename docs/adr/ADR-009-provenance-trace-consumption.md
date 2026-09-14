# ADR-009: Optional ArcaQ PROV-O Trace References in Certification Packages

## Status
Accepted - Arca Suite V2.3 integration gap closure for trust-cert-prov-o.

## Context
ArcaQ emits PROV-O traces on the Kafka topic `arcaq.prov-o.traces`. These
traces provide lineage evidence that auditors may require when reviewing a
certification package. Arca Cert must be able to include trace references in
its evidence binders, but only when ArcaQ is present and the feature is
explicitly enabled.

## Decision
1. Introduce a neutral `ProvenanceTraceRef` model in
   `src/core/domain/provenance.py` that captures target, trace_id, activity
   and an optional trace URI.
2. Persist trace references in the cert store (`src/infra/store.py`) in a new
   `provenance_trace_refs` table keyed by `target`.
3. Add a dedicated `ProvenanceTraceConsumer` in
   `src/infra/provenance_consumer.py` that subscribes to
   `arcaq.prov-o.traces` and stores trace refs.
4. Update `EvidenceBinderAssembler` to automatically hydrate every evidence
   binder with trace refs for the dossier's target, adding them as
   `EvidenceRef(source="arcaq.prov-o", ...)` entries.
5. Wire the consumer only when `CERT_ARCAQ_PROVO_ENABLED=true` (default
   `false`). When disabled, arca-cert starts normally and works without
   ArcaQ.
6. Update the Avro contract in `contracts/kafka/events.avsc` with the
   `ProvenanceTrace` schema.

## Consequences
- Positive: certification packages can carry lineage references from ArcaQ.
- Positive: the feature is strictly opt-in; default deployments remain
  autonomous and do not require ArcaQ.
- Negative: evidence binders grow when many trace refs exist for a target;
  this is mitigated by keeping only references (not full trace payloads).

## Compliance
- CONTRIBUTING.md ground rules: autonomous product, embedded SOC wired, no
  ArcaQ code imports, no shared database.
- ADR-003: Kafka events follow contract schemas.
- ADR-005: trace refs persisted in the cert store (SQLite dev, PostgreSQL prod).
