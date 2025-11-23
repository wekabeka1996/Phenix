"""Tests for order trace parsers"""
import json
import tempfile
from pathlib import Path

from apps.reference.tools.order_trace.parsers import (
    parse_decision_log,
    parse_execpos_runtime_log,
    parse_wal_records,
)


def test_parse_decision_log():
    """Test DecisionLog parsing."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        # Write sample DecisionLog entries
        f.write('2025-11-20 17:30:00 | INFO | {"ts": 1700000000000, "event": "FEATURES_RX", "rid": "rid_123", "symbol": "BTCUSDT", "why": ["feature_x>0.5"]}\n')
        f.write('2025-11-20 17:30:01 | INFO | {"ts": 1700000001000, "event": "DECISION_INTENT", "rid": "rid_123", "symbol": "BTCUSDT", "signal_score": 0.75, "why": ["signal_strong"]}\n')
        temp_path = f.name
    
    try:
        events = parse_decision_log(temp_path, symbol="BTCUSDT")
        assert len(events) == 2
        assert events[0].event_type == "FEATURES_RX"
        assert events[0].source == "DECISION"
        assert events[1].event_type == "DECISION_INTENT"
        assert events[1].why == "signal_strong"
    finally:
        Path(temp_path).unlink()


def test_parse_execpos_runtime_log():
    """Test ExecPos V2 runtime log parsing."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
        f.write(json.dumps({"ts": "2025-11-20T17:30:00.123Z", "runtime": "ExecPosRuntimeV2", "symbol": "BTCUSDT", "event_kind": "ENTRY_INTENT", "action": "allowed", "result": "success", "why": "gatekeeper_passed"}) + "\n")
        f.write(json.dumps({"ts": "2025-11-20T17:30:01.456Z", "runtime": "ExecPosRuntimeV2", "symbol": "ETHUSDT", "event_kind": "TRADE_EXECUTED", "action": "processed", "result": "success", "why": "fill_recorded"}) + "\n")
        temp_path = f.name
    
    try:
        events = parse_execpos_runtime_log(temp_path, symbol="BTCUSDT")
        assert len(events) == 1
        assert events[0].event_type == "ENTRY_INTENT"
        assert events[0].why == "gatekeeper_passed"
    finally:
        Path(temp_path).unlink()


def test_parse_wal_records():
    """Test WAL record parsing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        wal_file = Path(temp_dir) / "2025-11-20.jsonl"
        with open(wal_file, "w") as f:
            f.write(json.dumps({"event_type": "EXEC_TRADE", "domain": "execution_position", "runtime": "v2", "ts": 1700000000.123, "symbol": "BTCUSDT", "trade_id": "T123", "order_id": "O456", "role": "ENTRY", "qty": "1.5", "price": "50000"}) + "\n")
            f.write(json.dumps({"event_type": "EXEC_POSITION", "domain": "execution_position", "runtime": "v2", "ts": 1700000000.456, "symbol": "BTCUSDT", "position_size": "1.5", "direction": "LONG"}) + "\n")
        
        events = parse_wal_records(temp_dir, trade_id="T123")
        assert len(events) >= 1
        assert events[0].event_type == "EXEC_TRADE"
        assert events[0].payload["role"] == "ENTRY"
