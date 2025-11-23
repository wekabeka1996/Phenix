"""
Tests for ExecPosV2Guard Tool
==============================

Verifies regression guard logic.
"""
import pytest
import json
from pathlib import Path

from tools.execpos_v2_guard import ExecPosV2Guard, V2GuardStatus


def create_log_line(event_kind="ENTRY_INTENT", action="executed", result="success", **extra):
    """Helper to create JSONL log line."""
    log = {
        "ts": "2025-11-20T21:00:00Z",
        "runtime": "ExecPosRuntimeV2",
        "symbol": "BTCUSDT",
        "event_kind": event_kind,
        "action": action,
        "result": result,
        **extra
    }
    return json.dumps(log)


def test_guard_healthy_logs_returns_ok():
    """Test that healthy log data returns OK status."""
    guard = ExecPosV2Guard()
    
    # Create 100 successful events
    logs = [
        create_log_line(action="executed", result="success")
        for _ in range(100)
    ]
    
    result = guard.analyze_logs(logs)
    
    assert result["status"] == V2GuardStatus.OK
    assert len(result["issues"]) == 0
    assert result["metrics"]["executed_success"] == 100
    assert result["metrics"]["executed_failed"] == 0


def test_guard_high_failure_rate_returns_alert():
    """Test that high execution failure rate triggers ALERT."""
    guard = ExecPosV2Guard()
    
    # 50 success, 50 failures (50% failure rate > 10% threshold)
    logs = [
        create_log_line(action="executed", result="success")
        for _ in range(50)
    ] + [
        create_log_line(action="executed", result="failed", why="error")
        for _ in range(50)
    ]
    
    result = guard.analyze_logs(logs)
    
    assert result["status"] == V2GuardStatus.ALERT
    assert result["metrics"]["execution_failure_rate"] == 0.5
    assert len(result["issues"]) > 0
    assert "failure rate" in result["issues"][0].lower()


def test_guard_moderate_watchdog_violations_returns_warn():
    """Test that moderate watchdog violations trigger WARN."""
    guard = ExecPosV2Guard()
    
    # 90 normal events + 10 watchdog events (10% > 5% threshold)
    logs = [
        create_log_line(action="executed", result="success")
        for _ in range(90)
    ] + [
        create_log_line(event_kind="WATCHDOG_ACTION", action="healed", result="success")
        for _ in range(10)
    ]
    
    result = guard.analyze_logs(logs)
    
    assert result["status"] == V2GuardStatus.WARN
    assert result["metrics"]["watchdog_rate"] == 0.1
    assert len(result["issues"]) > 0


def test_guard_metrics_snapshot_analysis():
    """Test guard can analyze metrics snapshot."""
    guard = ExecPosV2Guard()
    
    snapshot = {
        "events_total": 100,
        "execution_success": 80,
        "execution_failed": 20,  # 20% failure rate > 10% threshold
        "fills_processed": 70,
        "fills_duplicate": 5,
        "watchdog_violations": 2
    }
    
    result = guard.analyze_metrics_snapshot(snapshot)
    
    assert result["status"] == V2GuardStatus.ALERT  # Due to high failure rate
    assert result["metrics"]["execution_failure_rate"] == 0.2


def test_guard_empty_logs_returns_ok():
    """Test that empty log data returns OK."""
    guard = ExecPosV2Guard()
    
    result = guard.analyze_logs([])
    
    assert result["status"] == V2GuardStatus.OK
    assert result["message"] == "No events to analyze"


def test_guard_custom_thresholds():
    """Test that custom thresholds can be configured."""
    # Set very low threshold
    guard = ExecPosV2Guard(config={"execution_failure_threshold": 0.01})  # 1%
    
    # Even 5% failure should trigger alert now
    logs = [
        create_log_line(action="executed", result="success")
        for _ in range(95)
    ] + [
        create_log_line(action="executed", result="failed")
        for _ in range(5)
    ]
    
    result = guard.analyze_logs(logs)
    
    assert result["status"] == V2GuardStatus.ALERT
    assert result["metrics"]["execution_failure_rate"] == 0.05


def test_guard_high_rejection_rate_triggers_warn():
    """Test that high rejection rate (gatekeeper) triggers WARN."""
    guard = ExecPosV2Guard()
    
    # 60% rejected
    logs = [
        create_log_line(action="rejected", result="blocked")
        for _ in range(60)
    ] + [
        create_log_line(action="executed", result="success")
        for _ in range(40)
    ]
    
    result = guard.analyze_logs(logs)
    
    assert result["status"] == V2GuardStatus.WARN
    assert result["metrics"]["rejection_rate"] == 0.6
