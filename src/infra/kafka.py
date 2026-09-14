"""Kafka producer/consumer for arca-cert (ADR-003, ADR-009).

Schemas follow contracts/kafka/events.avsc. The consumer subscribes to
`bench.results` and builds certification packages from validated bench results.

In production the consumer runs as a background task. In tests/dev it can be
driven by an in-memory message queue when Kafka is unavailable.
"""
import json
import logging
import threading
import time
from dataclasses import dataclass, field

from ..config import settings

logger = logging.getLogger(__name__)


try:  # pragma: no cover - optional dependency
    from kafka import KafkaConsumer, KafkaProducer as _KafkaProducer
    _KAFKA_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _KAFKA_AVAILABLE = False


@dataclass
class KafkaEvent:
    topic: str
    key: str
    payload: dict
    headers: dict = field(default_factory=dict)


class KafkaProducer:
    def __init__(self, bootstrap_servers: str | None = None):
        self._bootstrap = bootstrap_servers or settings.kafka_bootstrap_servers
        self._producer = None
        if _KAFKA_AVAILABLE:
            try:
                self._producer = _KafkaProducer(
                    bootstrap_servers=self._bootstrap.split(","),
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8") if k else None,
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("Kafka producer not available: %s", exc)

    def publish(self, event: KafkaEvent) -> str:
        if self._producer is None:
            logger.info("Kafka producer unavailable; dropping event %s", event.topic)
            return "dropped"
        future = self._producer.send(
            event.topic, key=event.key, value=event.payload, headers=event.headers
        )
        try:
            record = future.get(timeout=10)
            return f"{record.topic}-{record.partition}-{record.offset}"
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to publish Kafka event: %s", exc)
            return "failed"


class BenchResultConsumer:
    """Consumes bench.results events and builds certification packages.

    The payload shape expected from arca-bench is the standard Kafka envelope
    with a nested BenchResults payload:
      {
        "event_id": "...",
        "correlation_id": "...",
        "occurred_at": "...",
        "actor": null,
        "payload": {
          "bench_id": "uuid",
          "target": "arca-flow",
          "dimension": "security",
          "passed": true,
          "score": 0.85,
          "evidence": [{"source": "bench", "ref_id": "...", "description": "..."}]
        }
      }
    """

    def __init__(self, cert_service, bootstrap_servers: str | None = None,
                 topic: str | None = None, group_id: str | None = None):
        self._service = cert_service
        self._bootstrap = bootstrap_servers or settings.kafka_bootstrap_servers
        self._topic = topic or settings.kafka_bench_topic
        self._group_id = group_id or settings.kafka_consumer_group
        self._consumer = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._in_memory: list = []

    def _build_package(self, value: dict) -> None:
        if isinstance(value, dict) and "payload" in value and isinstance(value.get("payload"), dict):
            payload = value["payload"]
        elif isinstance(value, dict):
            payload = value
        else:
            logger.warning("Ignoring malformed bench result: %s", value)
            return
        target = payload.get("target")
        dimension = payload.get("dimension")
        score = payload.get("score")
        evidence = payload.get("evidence", [])
        if not target or dimension is None or score is None:
            logger.warning("Ignoring malformed bench result: %s", payload)
            return
        bench_evidence = [{"source": "bench", "ref_id": payload.get("bench_id", ""),
                           "description": f"bench result for {dimension}"}]
        for e in evidence:
            if isinstance(e, dict):
                bench_evidence.append(e)
        try:
            self._service.build_package(
                target=target,
                scores=[{"dimension": dimension, "value": score}],
                evidence=bench_evidence,
            )
            logger.info("Built certification package from bench result for %s", target)
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to build package from bench result: %s", exc)

    def inject(self, payload: dict) -> None:
        """Inject a message as if it came from Kafka. Used for tests."""
        self._in_memory.append(payload)
        self._build_package(payload)

    def start(self) -> None:
        if not _KAFKA_AVAILABLE:
            logger.info("Kafka not available; consumer running in memory-only mode")
            return
        self._consumer = KafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap.split(","),
            group_id=self._group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
        )
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                records = self._consumer.poll(timeout_ms=1000)
            except Exception as exc:  # pragma: no cover
                logger.error("Kafka poll error: %s", exc)
                time.sleep(1)
                continue
            for tp, messages in records.items():
                for msg in messages:
                    try:
                        self._build_package(msg.value)
                    except Exception as exc:  # pragma: no cover
                        logger.error("Failed to process bench result: %s", exc)

    def stop(self) -> None:
        self._stop.set()
        if self._consumer:
            self._consumer.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
