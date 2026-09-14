# ADR-009: Optional ArcaQ PROV-O Trace Consumer for Certification Packages

- Status: Accepted
- Date: 2026-09-14
- Module: arca-cert

## Context

Certification packages must be auditable. ArcaQ emits PROV-O traces on `arcaq.prov-o.traces` that describe the origin and transformation of artifacts. Arca Cert should optionally include these trace references in certification packages, but it must work without ArcaQ when the feature is disabled.

## Decision

1. The consumer is controlled by `CERT_ARCAQ_PROVO_ENABLED` (default false).
2. When enabled, `ProvenanceTraceConsumer` subscribes to `arcaq.prov-o.traces`.
3. Trace references are stored per target in the cert repository.
4. `EvidenceBinderAssembler.assemble` hydrates the dossier's evidence binder with `arcaq.prov-o` evidence entries for the matching target.
5. When disabled, certification packages contain only the dossier's own evidence.

## Consequences

- Arca Cert remains autonomous by default.
- Enabled deployments produce certification packages with richer provenance evidence.
- The Kafka Avro contract records the consumed trace shape.

## Compliance

- No ArcaQ code is imported into Arca Cert.
- The consumer degrades gracefully when Kafka is unavailable.
