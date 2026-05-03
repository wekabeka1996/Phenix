import time
from apps.reference.domains.execution_position.telemetry.metrics_collector import MetricsCollector


def test_metrics_basic_flow():
    mc = MetricsCollector(window_size_minutes=1)

    mc.record_trade_intent("ETHUSDT", "BUY")
    mc.record_trade_decision("ETHUSDT", "BUY", "ACCEPTED")
    mc.record_trade_decision("ETHUSDT", "BUY", "REJECTED", reason="cooldown")
    mc.record_trade_execution("ETHUSDT", "BUY", "PLACED")
    mc.record_trade_execution("ETHUSDT", "BUY", "FILLED")

    summary = mc.get_summary_metrics()
    assert summary["total_intents"] == 1
    assert summary["total_accepted"] == 1
    assert summary["total_rejected"] == 1

    sym = mc.get_symbol_metrics("ETHUSDT")
    assert sym["intents"] == 1
    # acceptance_rate is accepted / (accepted+rejected)
    assert 0.0 <= sym["acceptance_rate"] <= 1.0

    # recent rejections (should include our REJECTED event)
    recent = mc.get_recent_rejections(minutes=5)
    assert any(e.get("decision") == "REJECTED" for e in recent)

    patterns = mc.get_rejection_patterns()
    assert isinstance(patterns, dict)

    mc.reset()
    s2 = mc.get_summary_metrics()
    assert s2["total_intents"] == 0
