"""
Tests for EntropyMonitor - System Anomaly Detection
"""
import pytest
import time
from vfoundation.obs.entropy_monitor import EntropyMonitor
from vfoundation.core.protocol import Message


def test_normal_operation_no_spike():
    """Normal operation should not trigger spike detection"""
    monitor = EntropyMonitor(window_sec=60, volume_threshold=100, error_rate_threshold=0.5)
    
    # Add 10 normal events
    for i in range(10):
        msg = Message(op="EVT", verb="TEST", src="test", dst="any")
        monitor.track_event(msg)
    
    spike, reason = monitor.detect_spike()
    assert spike is False, f"Unexpected spike: {reason}"
    
    metrics = monitor.get_metrics()
    assert metrics["total_events"] == 10
    assert metrics["error_rate"] == 0.0


def test_volume_spike_detection():
    """Should detect when event volume exceeds threshold"""
    monitor = EntropyMonitor(window_sec=60, volume_threshold=50)
    
    # Add 60 events (exceeds threshold of 50)
    for i in range(60):
        msg = Message(op="EVT", verb="TEST", src="test", dst="any")
        monitor.track_event(msg)
    
    spike, reason = monitor.detect_spike()
    assert spike is True
    assert "VOLUME_SPIKE" in reason
    assert "60" in reason


def test_error_rate_spike_detection():
    """Should detect when error rate exceeds threshold"""
    monitor = EntropyMonitor(
        window_sec=60, 
        volume_threshold=1000,  # High threshold to not trigger volume spike
        error_rate_threshold=0.5
    )
    
    # Add 10 normal events
    for i in range(10):
        msg = Message(op="EVT", verb="TEST", src="test", dst="any")
        monitor.track_event(msg)
    
    # Add 20 ERR events (20/30 = 66% error rate)
    for i in range(20):
        msg = Message(op="ERR", verb="FAIL", src="test", dst="any")
        monitor.track_event(msg)
    
    spike, reason = monitor.detect_spike()
    assert spike is True
    assert "ERROR_SPIKE" in reason
    
    metrics = monitor.get_metrics()
    assert metrics["error_rate"] > 0.5


def test_loop_detection():
    """Should detect when same event is repeated excessively"""
    monitor = EntropyMonitor(
        window_sec=60, 
        volume_threshold=1000,
        loop_threshold=10
    )
    
    # Send same event 15 times
    for i in range(15):
        msg = Message(op="CMD", verb="OPEN", src="test", dst="exec")
        monitor.track_event(msg)
    
    spike, reason = monitor.detect_spike()
    assert spike is True
    assert "LOOP_DETECTED" in reason
    assert "CMD:OPEN" in reason


def test_window_sliding():
    """Events should expire after window duration"""
    monitor = EntropyMonitor(window_sec=1)  # 1 second window
    
    # Add event
    msg = Message(op="EVT", verb="TEST", src="test", dst="any")
    monitor.track_event(msg)
    
    assert len(monitor.events) == 1
    
    # Wait for window to expire
    time.sleep(1.1)
    
    # Trigger cleanup by calling detect_spike
    monitor.detect_spike()
    
    # Event should be removed
    assert len(monitor.events) == 0


def test_metrics_reporting():
    """Should provide accurate metrics"""
    monitor = EntropyMonitor()
    
    # Add mixed events
    for i in range(5):
        msg = Message(op="EVT", verb="TEST", src="test", dst="any")
        monitor.track_event(msg)
    
    for i in range(3):
        msg = Message(op="ERR", verb="FAIL", src="test", dst="any")
        monitor.track_event(msg)
    
    for i in range(2):
        msg = Message(op="CMD", verb="OPEN", src="test", dst="any")
        monitor.track_event(msg)
    
    metrics = monitor.get_metrics()
    
    assert metrics["total_events"] == 10
    assert metrics["error_count"] == 3
    assert metrics["error_rate"] == 0.3
    assert metrics["unique_patterns"] == 3
    assert "EVT:TEST" in metrics["top_patterns"]
    assert "ERR:FAIL" in metrics["top_patterns"]
    assert "CMD:OPEN" in metrics["top_patterns"]


def test_reset():
    """Reset should clear all tracking"""
    monitor = EntropyMonitor()
    
    # Add some events
    for i in range(10):
        msg = Message(op="EVT", verb="TEST", src="test", dst="any")
        monitor.track_event(msg)
    
    assert len(monitor.events) > 0
    assert len(monitor.pattern_counts) > 0
    
    # Reset
    monitor.reset()
    
    assert len(monitor.events) == 0
    assert len(monitor.pattern_counts) == 0
