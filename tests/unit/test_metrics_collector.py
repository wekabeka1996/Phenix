import pytest
import time
import threading
from collections import defaultdict
from apps.reference.domains.execution_position.telemetry.metrics_collector import MetricsCollector

class TestMetricsCollector:
    
    @pytest.fixture
    def collector(self):
        return MetricsCollector(window_size_minutes=60)

    def test_initialization(self):
        """Test initialization with default and explicit values."""
        mc_default = MetricsCollector()
        assert mc_default.window_size_seconds == 3600
        
        mc_explicit = MetricsCollector(window_size_minutes=10)
        assert mc_explicit.window_size_seconds == 600

    def test_record_trade_intent(self, collector):
        """Test recording trade intents."""
        collector.record_trade_intent("BTCUSDT", "BUY")
        collector.record_trade_intent("ETHUSDT", "SELL")
        
        summary = collector.get_summary_metrics()
        assert summary["total_intents"] == 2
        
        btc_metrics = collector.get_symbol_metrics("BTCUSDT")
        assert btc_metrics["intents"] == 1
        
        eth_metrics = collector.get_symbol_metrics("ETHUSDT")
        assert eth_metrics["intents"] == 1

    def test_record_trade_decision(self, collector):
        """Test recording trade decisions (accepted/rejected)."""
        # Accepted
        collector.record_trade_decision("BTCUSDT", "BUY", "ACCEPTED")
        summary = collector.get_summary_metrics()
        assert summary["total_accepted"] == 1
        assert summary["acceptance_rate"] == 1.0
        
        # Rejected (Cooldown)
        collector.record_trade_decision("BTCUSDT", "BUY", "REJECTED", reason="cooldown active")
        summary = collector.get_summary_metrics()
        assert summary["total_rejected"] == 1
        assert summary["cooldown_rejections"] == 1
        assert summary["acceptance_rate"] == 0.5
        
        # Rejected (Other)
        collector.record_trade_decision("ETHUSDT", "SELL", "REJECTED", reason="insufficient funds")
        summary = collector.get_summary_metrics()
        assert summary["total_rejected"] == 2
        assert summary["other_rejections"] == 1
        
        # Symbol metrics
        btc_metrics = collector.get_symbol_metrics("BTCUSDT")
        assert btc_metrics["accepted"] == 1
        assert btc_metrics["rejected"] == 1
        assert btc_metrics["cooldown_rejects"] == 1

    def test_record_trade_execution(self, collector):
        """Test recording trade executions."""
        collector.record_trade_execution("BTCUSDT", "BUY", "PLACED")
        collector.record_trade_execution("BTCUSDT", "BUY", "FILLED")
        collector.record_trade_execution("ETHUSDT", "SELL", "CANCELLED")
        
        summary = collector.get_summary_metrics()
        assert summary["executions_placed"] == 1
        assert summary["executions_filled"] == 1
        assert summary["executions_cancelled"] == 1

    def test_exposure_metrics(self, collector):
        """Test exposure gate metrics."""
        collector.record_exposure_fail_closed("timeout")
        collector.record_exposure_fail_closed("timeout")
        collector.record_exposure_fail_closed("network_error")
        
        collector.record_postfill_hold(5)
        collector.record_postfill_expired()
        
        summary = collector.get_summary_metrics()
        assert summary["exposure_fail_closed"]["timeout"] == 2
        assert summary["exposure_fail_closed"]["network_error"] == 1
        assert summary["postfill_hold_active"] == 5
        assert summary["postfill_hold_expired_total"] == 1

    def test_latency_and_qos_metrics(self, collector):
        """Test latency and QoS metrics."""
        collector.record_cmd_open()
        collector.record_cmd_open()
        collector.record_open_success()
        
        collector.record_time_to_open(50.0)
        collector.record_time_to_open(150.0)
        
        collector.record_qos_cooldown_hit()
        
        # Simulate a rejection to affect defer_rate calculation
        collector.record_trade_decision("BTCUSDT", "BUY", "REJECTED", reason="some reason")
        
        summary = collector.get_summary_metrics()
        assert summary["cmd_open_total"] == 2
        assert summary["open_success_total"] == 1
        assert summary["mean_time_to_open_ms"] == 100.0
        assert summary["qos_cooldown_hits"] == 1
        
        # block_rate = qos_cooldown_hits / cmd_open_total = 1 / 2 = 0.5
        assert summary["block_rate"] == 0.5

    def test_rejection_patterns(self, collector):
        """Test rejection pattern analysis."""
        # Create a scenario with high rejection rate
        for _ in range(8):
            collector.record_trade_decision("BTCUSDT", "BUY", "REJECTED", reason="cooldown")
        for _ in range(2):
            collector.record_trade_decision("BTCUSDT", "BUY", "ACCEPTED")
            
        patterns = collector.get_rejection_patterns()
        assert patterns["high_rejection_rate"] is True  # 80% rejection
        assert patterns["cooldown_dominant"] is True    # 100% of rejections are cooldown
        
        problem_symbols = patterns["problem_symbols"]
        assert len(problem_symbols) == 1
        assert problem_symbols[0]["symbol"] == "BTCUSDT"
        assert problem_symbols[0]["rejection_rate"] == 0.8

    def test_thread_safety(self, collector):
        """Test thread safety of metric recording."""
        def worker():
            for _ in range(100):
                collector.record_trade_intent("BTCUSDT", "BUY")
                collector.record_trade_decision("BTCUSDT", "BUY", "ACCEPTED")
        
        threads = []
        for _ in range(10):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        summary = collector.get_summary_metrics()
        assert summary["total_intents"] == 1000
        assert summary["total_accepted"] == 1000

    def test_reset(self, collector):
        """Test resetting metrics."""
        collector.record_trade_intent("BTCUSDT", "BUY")
        collector.reset()
        
        summary = collector.get_summary_metrics()
        assert summary["total_intents"] == 0
        assert len(collector._symbol_metrics) == 0
        assert len(collector._rolling_data) == 0
