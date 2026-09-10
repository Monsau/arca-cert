# Data Governance — Arca Cert - Certification Dossier Builder

## Classification
Dossiers and remediation plans: Confidential (audit/regulatory). No personal data is stored in this module.

## Retention
Published dossiers: 3 years (regulatory evidence). Drafts: until deletion + 30 days. Remediation plans: same as their dossier.

## Jurisdiction
Data residency follows the deployed Country Pack sovereignty rules; cross-border
transfers require an explicit governance decision recorded as an ADR.

## Encryption
- At rest: AES-256 (managed keys via Vault/ESO).
- In transit: mTLS STRICT inside the mesh (PeerAuthentication), TLS 1.3 at the edge.

## Secrets
No secret in clear text in code, manifests or docs. Runtime secrets come from
Vault through the External Secrets Operator.
