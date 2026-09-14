"""Provenance trace reference model for arca-cert.

A lightweight reference to a PROV-O trace consumed from ArcaQ. Trace refs
are kept separately from dossier evidence so they can be hydrated into
certification packages only when ArcaQ is enabled.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


@dataclass
class ProvenanceTraceRef:
    target: str
    trace_id: str
    activity: str
    trace_uri: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "target": self.target,
            "trace_id": self.trace_id,
            "activity": self.activity,
            "trace_uri": self.trace_uri,
            "occurred_at": self.occurred_at.isoformat(),
        }
