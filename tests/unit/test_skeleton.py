"""Unit tests for arca-cert infrastructure skeleton."""
import inspect

from src.infra import soc


def test_soc_bricks_present():
    for cls_name in ("SOCCollector", "SOCAnalyzer", "SOCDashboard",
                     "SOCForensics", "SOCResponder"):
        assert hasattr(soc, cls_name), cls_name


def test_soc_collector_signatures():
    sig = inspect.signature(soc.SOCCollector.collect_event)
    assert list(sig.parameters) == ["self", "event_type", "payload", "correlation_id"]


def test_soc_collector_and_analyzer():
    collector = soc.SOCCollector()
    collector.collect_event("test.signal", {"value": 0.5}, "corr-1")
    analyzer = soc.SOCAnalyzer(collector)
    assert analyzer.detect_anomaly("test.signal", 0.6) == []
    collector.collect_event("test.signal", {"value": 0.9}, "corr-2")
    anomalies = analyzer.detect_anomaly("test.signal", 0.8)
    assert len(anomalies) == 1
    assert anomalies[0]["value"] == 0.9


def test_soc_responder_records_actions():
    responder = soc.SOCResponder()
    assert responder.block("1.2.3.4", "scan detected")
    assert len(responder.actions()) == 1
