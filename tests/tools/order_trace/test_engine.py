"""Tests for order trace correlation engine"""
import json
import tempfile
from pathlib import Path

from apps.reference.tools.order_trace import build_trace_for_trade, TraceSources


def test_build_trace_for_trade():
    """Test building trade trace from WAL."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create WAL file
        wal_file = Path(temp_dir) / "2025-11-20.jsonl"
        with open(wal_file, "w") as f:
            f.write(json.dumps({
                "event_type": "EXEC_TRADE",
                "domain": "execution_position",
                "runtime": "v2",
                "ts": 1700000000.123,
                "symbol": "BTCUSDT",
                "trade_id": "T123",
                "order_id": "O456",
                "role": "ENTRY",
                "qty": "1.5",
                "price": "50000",
                "realized_pnl": "0"
            }) + "\n")
        
        # Create runtime log
        runtime_log = Path(temp_dir) / "execpos_v2_runtime.jsonl"
        with open(runtime_log, "w") as f:
            f.write(json.dumps({
                "ts": "2025-11-20T17:30:00.123Z",
                "runtime": "ExecPosRuntimeV2",
                "symbol": "BTCUSDT",
                "event_kind": "ENTRY_INTENT",
                "action": "allowed",
                "result": "success",
                "why": "gatekeeper_passed"
            }) + "\n")
        
        sources = TraceSources(
            wal_dir=temp_dir,
            runtime_log_path=str(runtime_log),
        )
        
        trace= build_trace_for_trade("T123", sources)
        assert trace is not None
        assert trace.symbol == "BTCUSDT"
        assert trace.trace_id == "T123"
        assert len(trace.events) >= 2
        assert trace.entry_info is not None
        assert trace.entry_info["price"] == "50000"
