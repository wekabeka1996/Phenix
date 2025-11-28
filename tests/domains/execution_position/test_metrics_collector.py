import pytest
import time
from threading import Thread
from apps.reference.domains.execution_position.observability.metrics_collector import MetricsCollector

@pytest.fixture
def collector():
    return MetricsCollector(window_size_minutes=1)

def test_initialization(collector):
    summary = collector.get_summary_metrics()
    assert summary["total_intents"] == 0
    assert summary["total_accepted"] == 0
    assert summary["total_rejected"] == 0

def test_record_trade_intent(collector):
    collector.record_trade_intent("BTCUSDT", "BUY")
    summary = collector.get_summary_metrics()
    assert summary["total_intents"] == 1

    symbol_metrics = collector.get_symbol_metrics("BTCUSDT")
    assert symbol_metrics["intents"] == 1

def test_record_trade_decision_accepted(collector):
    collector.record_trade_decision("BTCUSDT", "BUY", "ACCEPTED")
    summary = collector.get_summary_metrics()
    assert summary["total_accepted"] == 1
    assert summary["acceptance_rate"] == 1.0

    symbol_metrics = collector.get_symbol_metrics("BTCUSDT")
    assert symbol_metrics["accepted"] == 1

def test_record_trade_decision_rejected(collector):
    collector.record_trade_decision("BTCUSDT", "BUY", "REJECTED", reason="cooldown active")
    summary = collector.get_summary_metrics()
    assert summary["total_rejected"] == 1
    assert summary["cooldown_rejections"] == 1
    assert summary["rejection_rate"] == 1.0

    symbol_metrics = collector.get_symbol_metrics("BTCUSDT")
    assert symbol_metrics["rejected"] == 1
    assert symbol_metrics["cooldown_rejects"] == 1

def test_record_trade_execution(collector):
    collector.record_trade_execution("BTCUSDT", "BUY", "FILLED")
    summary = collector.get_summary_metrics()
    assert summary["executions_filled"] == 1

def test_record_exposure_fail_closed(collector):
    collector.record_exposure_fail_closed("PORTFOLIO_STALE")
    summary = collector.get_summary_metrics()
    assert summary["exposure_fail_closed"]["PORTFOLIO_STALE"] == 1

def test_record_time_to_open(collector):
    collector.record_time_to_open(100.0)
    collector.record_time_to_open(200.0)
    summary = collector.get_summary_metrics()
    assert summary["mean_time_to_open_ms"] == 150.0

def test_thread_safety(collector):
    def worker():
        for _ in range(100):
            collector.record_trade_intent("BTCUSDT", "BUY")
            collector.record_trade_decision("BTCUSDT", "BUY", "ACCEPTED")

    threads = [Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    summary = collector.get_summary_metrics()
    assert summary["total_intents"] == 1000
    assert summary["total_accepted"] == 1000

def test_rejection_patterns(collector):
    # Simulate high rejection rate due to cooldown
    for _ in range(9):
        collector.record_trade_decision("BTCUSDT", "BUY", "REJECTED", reason="cooldown")
    collector.record_trade_decision("BTCUSDT", "BUY", "ACCEPTED")

    patterns = collector.get_rejection_patterns()
    assert patterns["high_rejection_rate"] is True
    assert patterns["cooldown_dominant"] is True
    assert len(patterns["problem_symbols"]) == 1
    assert patterns["problem_symbols"][0]["symbol"] == "BTCUSDT"

def test_reset(collector):
    collector.record_trade_intent("BTCUSDT", "BUY")
    collector.reset()
    summary = collector.get_summary_metrics()
    assert summary["total_intents"] == 0
