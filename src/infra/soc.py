"""Embedded SOC: the five mandatory bricks. No telemetry or audit bypass allowed.

Same wiring contract as arca-bench (ADR-009): the five bricks are composed in
``EmbeddedSOC`` and every mutation is routed through ``audit_operation`` so
operation_started / operation_succeeded / operation_failed events, traces and
error logs are collected without any bypass.
"""
import json
import logging
import threading
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class SOCCollector:
    """Collects events, logs, traces and metrics for the embedded SOC.

    In production these records are forwarded to the central SIEM; in dev/tests
    they are held in memory and exposed through the dashboard and forensics bricks.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._events: list = []
        self._logs: list = []
        self._traces: list = []
        self._metrics: dict = defaultdict(list)

    def collect_event(self, event_type: str, payload: dict, correlation_id: str):
        with self._lock:
            self._events.append({
                "event_type": event_type,
                "payload": payload,
                "correlation_id": correlation_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        logger.info("SOC event %s correlation=%s", event_type, correlation_id)

    def collect_log(self, level: str, message: str, context: dict):
        with self._lock:
            self._logs.append({
                "level": level,
                "message": message,
                "context": context,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        getattr(logger, level.lower(), logger.info)("%s context=%s", message, context)

    def collect_trace(self, span_name: str, attributes: dict):
        with self._lock:
            self._traces.append({
                "span_name": span_name,
                "attributes": attributes,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    def collect_metric(self, name: str, value: float, labels: dict):
        with self._lock:
            self._metrics[name].append({
                "value": value,
                "labels": labels,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    def events(self) -> list:
        with self._lock:
            return list(self._events)

    def logs(self) -> list:
        with self._lock:
            return list(self._logs)


class SOCAnalyzer:
    """Lightweight anomaly and risk detection over the collector stream."""

    def __init__(self, collector: SOCCollector | None = None):
        self._collector = collector

    def detect_anomaly(self, signal_type: str, threshold: float) -> list:
        if self._collector is None:
            return []
        anomalies = []
        for event in self._collector.events():
            payload = event.get("payload", {})
            value = payload.get("value")
            if value is not None and event.get("event_type") == signal_type and value > threshold:
                anomalies.append({
                    "correlation_id": event["correlation_id"],
                    "value": value,
                    "threshold": threshold,
                    "timestamp": event["timestamp"],
                })
        return anomalies

    def evaluate_risk(self, event_stream: list) -> dict:
        risk_score = 0
        factors = []
        for event in event_stream:
            payload = event.get("payload", {})
            if event.get("event_type") == "auth.failure":
                risk_score += 25
                factors.append("authentication failure")
            if payload.get("status") == "revoked":
                risk_score += 30
                factors.append("revoked dossier access")
            if payload.get("seal_valid") is False:
                risk_score += 40
                factors.append("seal verification failure")
        return {"score": min(risk_score, 100), "factors": factors}


class SOCDashboard:
    """In-memory SOC dashboard exposing health, risk summary and incidents."""

    def __init__(self, collector: SOCCollector | None = None,
                 analyzer: SOCAnalyzer | None = None):
        self._collector = collector
        self._analyzer = analyzer

    def health_status(self) -> dict:
        return {
            "status": "healthy",
            "events_collected": len(self._collector.events()) if self._collector else 0,
            "logs_collected": len(self._collector.logs()) if self._collector else 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def risk_summary(self) -> dict:
        if self._collector is None:
            return {"score": 0, "factors": []}
        events = self._collector.events()
        return self._analyzer.evaluate_risk(events) if self._analyzer else {"score": 0, "factors": []}

    def incident_list(self, status: str = None) -> list:
        if self._collector is None:
            return []
        incidents = [
            e for e in self._collector.events()
            if e.get("event_type", "").startswith("incident.")
        ]
        if status:
            incidents = [i for i in incidents if i.get("payload", {}).get("status") == status]
        return incidents


class SOCForensics:
    """Reconstruct timelines and audit trails from the collector stream."""

    def __init__(self, collector: SOCCollector | None = None):
        self._collector = collector

    def reconstruct_timeline(self, correlation_id: str) -> list:
        if self._collector is None:
            return []
        return [
            e for e in self._collector.events()
            if e.get("correlation_id") == correlation_id
        ]

    def audit_trail(self, entity_type: str, entity_id: str) -> list:
        if self._collector is None:
            return []
        return [
            e for e in self._collector.events()
            if e.get("payload", {}).get("entity_type") == entity_type
            and e.get("payload", {}).get("entity_id") == entity_id
        ]


class SOCResponder:
    """Automated response actions. In production these call platform APIs."""

    def __init__(self, collector: SOCCollector | None = None):
        self._collector = collector
        self._actions: list = []
        self._lock = threading.Lock()

    def _record(self, action: str, target: str, reason: str):
        with self._lock:
            self._actions.append({
                "action": action,
                "target": target,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        if self._collector:
            self._collector.collect_event(
                "soc.response",
                {"action": action, "target": target, "reason": reason},
                correlation_id=str(uuid.uuid4()),
            )

    def block(self, target: str, reason: str) -> bool:
        self._record("block", target, reason)
        logger.warning("SOC block target=%s reason=%s", target, reason)
        return True

    def limit(self, target: str, rate: int) -> bool:
        self._record("limit", target, f"rate={rate}")
        logger.warning("SOC limit target=%s rate=%s", target, rate)
        return True

    def isolate(self, target: str) -> bool:
        self._record("isolate", target, "anomaly detected")
        logger.warning("SOC isolate target=%s", target)
        return True

    def revoke(self, credential_id: str) -> bool:
        self._record("revoke", credential_id, "credential compromise")
        logger.warning("SOC revoke credential=%s", credential_id)
        return True

    def rollback(self, deployment_id: str) -> bool:
        self._record("rollback", deployment_id, "incident response")
        logger.warning("SOC rollback deployment=%s", deployment_id)
        return True

    def escalate(self, incident_id: str, level: str) -> bool:
        self._record("escalate", incident_id, f"level={level}")
        logger.warning("SOC escalate incident=%s level=%s", incident_id, level)
        return True

    def actions(self) -> list:
        with self._lock:
            return list(self._actions)


class EmbeddedSOC:
    """Composition root of the five SOC bricks (same pattern as arca-bench)."""

    def __init__(self):
        self.collector = SOCCollector()
        self.analyzer = SOCAnalyzer(self.collector)
        self.dashboard = SOCDashboard(self.collector, self.analyzer)
        self.forensics = SOCForensics(self.collector)
        self.responder = SOCResponder(self.collector)


@contextmanager
def audit_operation(soc: EmbeddedSOC, operation: str, correlation_id: str,
                    entity_type: str = None, entity_id: str = None,
                    user: dict = None):
    """Audit context manager: collect start/success/failure events and traces
    for a mutation. Failures are logged and re-raised — no silent bypass."""
    payload = {"operation": operation, "entity_type": entity_type,
               "entity_id": entity_id, "user": user}
    soc.collector.collect_event("operation_started", payload, correlation_id)
    soc.collector.collect_trace(operation, {"correlation_id": correlation_id})
    try:
        yield soc
        soc.collector.collect_event("operation_succeeded", payload,
                                    correlation_id)
    except Exception as exc:
        soc.collector.collect_event("operation_failed", {
            **payload, "error": str(exc)}, correlation_id)
        soc.collector.collect_log("error", str(exc), {
            "operation": operation, "correlation_id": correlation_id})
        raise
