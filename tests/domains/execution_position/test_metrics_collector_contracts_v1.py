import pytest
import time
from apps.reference.domains.execution_position.telemetry.metrics_collector import MetricsCollector

@pytest.fixture
def collector():
    return MetricsCollector(window_size_minutes=1)

def test_metrics_record_trade_intent(collector):
    """1. increment counters on intent."""
    collector.record_trade_intent("BTCUSDT", "BUY")
    summary = collector.get_summary_metrics()
    assert summary["total_intents"] == 1
    
    symbol_metrics = collector.get_symbol_metrics("BTCUSDT")
    assert symbol_metrics["intents"] == 1

def test_metrics_record_trade_decision_accepted(collector):
    """2. increment on ACCEPTED."""
    collector.record_trade_decision("BTCUSDT", "BUY", "ACCEPTED")
    summary = collector.get_summary_metrics()
    assert summary["total_accepted"] == 1
    assert summary["acceptance_rate"] == 1.0

def test_metrics_record_trade_decision_rejected(collector):
    """3. increment on REJECTED."""
    collector.record_trade_decision("BTCUSDT", "BUY", "REJECTED", reason="Insufficient funds")
    summary = collector.get_summary_metrics()
    assert summary["total_rejected"] == 1
    assert summary["rejection_rate"] == 1.0
    assert summary["other_rejections"] == 1

def test_metrics_record_guard_rejection_cooldown(collector):
    """4. track cooldown specifically."""
    collector.record_trade_decision("BTCUSDT", "BUY", "REJECTED", reason="risk_cooldown")
    summary = collector.get_summary_metrics()
    assert summary["cooldown_rejections"] == 1

def test_metrics_record_execution_status(collector):
    """5. track execution outcomes."""
    collector.record_trade_execution("BTCUSDT", "BUY", "FILLED")
    collector.record_trade_execution("BTCUSDT", "BUY", "REJECTED")
    summary = collector.get_summary_metrics()
    assert summary["executions_filled"] == 1
    assert summary["executions_rejected"] == 1

def test_metrics_exposure_fail_closed(collector):
    """6. track exposure gate events."""
    collector.record_exposure_fail_closed("no_equity")
    summary = collector.get_summary_metrics()
    assert summary["exposure_fail_closed"]["no_equity"] == 1

def test_metrics_postfill_hold_lifecycle(collector):
    """7. track postfill hold state."""
    collector.record_postfill_hold(5)
    collector.record_postfill_expired()
    collector.record_postfill_released()
    summary = collector.get_summary_metrics()
    assert summary["postfill_hold_active"] == 5
    assert summary["postfill_hold_expired_total"] == 1
    assert summary["postfill_hold_released_total"] == 1

def test_metrics_latency_tracking(collector):
    """8. track mean time to open."""
    collector.record_time_to_open(100.0)
    collector.record_time_to_open(200.0)
    summary = collector.get_summary_metrics()
    assert summary["mean_time_to_open_ms"] == 150.0

def test_metrics_rejection_patterns_cooldown_dominant(collector):
    """9. analyze rejection patterns."""
    collector.record_trade_decision("BTCUSDT", "BUY", "REJECTED", reason="cooldown")
    collector.record_trade_decision("BTCUSDT", "BUY", "REJECTED", reason="cooldown")
    patterns = collector.get_rejection_patterns()
    assert patterns["cooldown_dominant"] is True

def test_metrics_reset_idempotent_testing(collector):
    """10. verify reset functionality."""
    collector.record_trade_intent("BTCUSDT", "BUY")
    collector.reset()
    summary = collector.get_summary_metrics()
    assert summary["total_intents"] == 0
    assert len(collector._rolling_data) == 0
