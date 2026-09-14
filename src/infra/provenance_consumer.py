"""Optional Kafka consumer for ArcaQ PROV-O traces in arca-cert.

Subscribes to ``arcaq.prov-o.traces`` when ``CERT_ARCAQ_PROVO_ENABLED`` is set.
Trace references are stored per target and later hydrated into certification
packages by the ``EvidenceBinderAssembler``. When disabled (the default)
arca-cert works without ArcaQ.
"""
import json
import logging
import threading
import time
from datetime import datetime, timezone

from ..config import settings
from ..core.domain.provenance import ProvenanceTraceRef

logger = logging.getLogger(__name__)


try:  # pragma: no cover - optional dependency
    from kafka import KafkaConsumer as _KafkaConsumer
    _KAFKA_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _KAFKA_AVAILABLE = False


class ProvenanceTraceConsumer:
    """Consumes PROV-O trace events from ArcaQ and stores trace refs."""

    def __init__(self,
                 repository,
                 bootstrap_servers: str | None = None,
                 topic: str | None = None,
                 group_id: str = "arca-cert-provenance-consumer",
                 poll_interval: float = 1.0):
        self._repo = repository
        self._bootstrap = bootstrap_servers or settings.kafka_bootstrap_servers
        self._topic = topic or settings.arcaq_provo_topic
        self._group_id = group_id
        self._poll_interval = poll_interval
        self._consumer = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._in_memory: list = []

    def _create_consumer(self):
        if not _KAFKA_AVAILABLE:
            logger.info("Kafka not available; provenance consumer runs in memory-only mode")
            return None
        try:
            return _KafkaConsumer(
                self._topic,
                bootstrap_servers=self._bootstrap.split(","),
                group_id=self._group_id,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="earliest",
            )
        except Exception as exc:  # pragma: no cover - optional platform profile
            logger.warning("Kafka provenance consumer not available: %s", exc)
            return None

    def inject(self, payload: dict) -> None:
        """Inject a trace as if it came from Kafka. Used for tests."""
        self._in_memory.append(payload)
        self._handle_trace(payload)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._consumer = self._create_consumer()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Provenance trace consumer started on topic: %s", self._topic)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._consumer is None:
                    time.sleep(self._poll_interval)
                    continue
                records = self._consumer.poll(timeout_ms=1000)
                for tp, messages in records.items():
                    for msg in messages:
                        try:
                            self._handle_trace(msg.value)
                        except Exception as exc:  # pragma: no cover
                            logger.error("Failed to process provenance trace: %s", exc)
            except Exception as exc:  # pragma: no cover
                logger.error("Provenance consumer error: %s", exc)
                time.sleep(self._poll_interval)

    def _handle_trace(self, payload: dict) -> None:
        if isinstance(payload, dict) and isinstance(payload.get("payload"), dict):
            trace = payload["payload"]
        elif isinstance(payload, dict):
            trace = payload
        else:
            logger.warning("Ignoring malformed provenance trace: %s", payload)
            return

        target = trace.get("target") or trace.get("subject")
        trace_id = trace.get("trace_id") or trace.get("id")
        if not target or not trace_id:
            logger.warning("Ignoring provenance trace without target/trace_id: %s", trace)
            return

        occurred_at = trace.get("occurred_at") or trace.get("timestamp")
        if isinstance(occurred_at, str):
            occurred_at = datetime.fromisoformat(occurred_at)
        if not isinstance(occurred_at, datetime):
            occurred_at = datetime.now(timezone.utc)

        ref = ProvenanceTraceRef(
            target=str(target),
            trace_id=str(trace_id),
            activity=str(trace.get("activity", "unknown")),
            trace_uri=trace.get("trace_uri") or trace.get("uri"),
            occurred_at=occurred_at,
        )
        self._repo.save_provenance_trace_ref(ref)
        logger.debug("Stored provenance trace ref %s for target %s", ref.trace_id, ref.target)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        if self._consumer:
            self._consumer.close()
            self._consumer = None
