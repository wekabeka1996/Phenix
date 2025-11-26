"""
Smoke test for BRACKET_EVAL_SNAPSHOT logging.

This test verifies that the bracket evaluation logging infrastructure
is correctly wired and writes BRACKET_EVAL_SNAPSHOT events to the log file.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState
from apps.reference.domains.execution_position.shadow_execpos import logging_v2


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    adapter.get_open_orders = AsyncMock(return_value=[])
    adapter.get_open_positions = AsyncMock(return_value=[])
    return adapter


@pytest.fixture
def runtime(mock_adapter, tmp_path):
    """Create a runtime instance with mocked dependencies and temp log file."""
    # Override log file to use temp path
    original_log_file = logging_v2.LOG_FILE
    logging_v2.LOG_FILE = tmp_path / "test_runtime.jsonl"
    
    config = {
        "aggregated_oco": {
            "enabled": True,
            "sl_pct": 2.0,
            "tp_pct": 3.0
        }
    }
    
    runtime = ExecPosRuntimeV2(config=config, adapter=mock_adapter, price_service=None)
    
    yield runtime
    
    # Restore original log file
    logging_v2.LOG_FILE = original_log_file


@pytest.mark.asyncio
async def test_bracket_eval_snapshot_logging(runtime, tmp_path):
    """
    Verify that _evaluate_brackets generates a BRACKET_EVAL_SNAPSHOT log entry.
    """
    # Setup: Create a position
    symbol = "BTCUSDT"
    position = PositionState(
        symbol=symbol,
        qty=1.0,
        avg_entry_price=50000.0,
        realized_pnl=0.0,
        unrealized_pnl=100.0,
        last_update_time=1234567890.0,
        cycle_id=42
    )
    
    runtime._positions_by_symbol[symbol] = position
    runtime._orders_snapshot_state[symbol] = "FRESH"
    runtime._open_orders_by_symbol[symbol] = []
    
    # Execute: Trigger bracket evaluation
    await runtime._evaluate_brackets(symbol, position, reason="test_smoke")
    
    # Verify: Check that log file contains BRACKET_EVAL_SNAPSHOT
    log_file = tmp_path / "test_runtime.jsonl"
    assert log_file.exists(), "Log file should be created"
    
    # Read log entries
    log_entries = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                log_entries.append(json.loads(line))
    
    # Find BRACKET_EVAL_SNAPSHOT entries
    snapshot_entries = [e for e in log_entries if e.get("event_kind") == "BRACKET_EVAL_SNAPSHOT"]
    
    assert len(snapshot_entries) >= 1, f"Expected at least 1 BRACKET_EVAL_SNAPSHOT, found {len(snapshot_entries)}"
    
    # Verify structure of the snapshot entry
    snapshot_entry = snapshot_entries[0]
    assert snapshot_entry["symbol"] == symbol
    assert snapshot_entry["side"] == "LONG"
    assert snapshot_entry["position_qty"] == 1.0
    assert "snapshot" in snapshot_entry
    
    # Parse the nested snapshot payload
    snapshot_payload = json.loads(snapshot_entry["snapshot"])
    assert snapshot_payload["symbol"] == symbol
    assert snapshot_payload["side"] == "LONG"
    assert snapshot_payload["position_qty"] == 1.0
    assert snapshot_payload["position_cycle_id"] == 42
    assert snapshot_payload["orders_snapshot_state"] in ("FRESH", "STALE")
    assert isinstance(snapshot_payload["open_brackets"], list)
    assert isinstance(snapshot_payload["bracket_plan"], list)
    
    print(f"✅ BRACKET_EVAL_SNAPSHOT logged successfully: {snapshot_entry}")


def test_log_bracket_eval_snapshot_direct():
    """
    Direct unit test for log_bracket_eval_snapshot function.
    """
    import tempfile
    original_log_file = logging_v2.LOG_FILE
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_log = Path(tmp_dir) / "direct_test.jsonl"
        logging_v2.LOG_FILE = tmp_log
        
        # Call the logging function directly
        logging_v2.log_bracket_eval_snapshot(
            symbol="ETHUSDT",
            side="SHORT",
            position_qty=10.0,
            position_cycle_id=100,
            snapshot_state="FRESH",
            open_brackets=[
                {"orderId": "123", "side": "BUY", "type": "STOP_MARKET", "qty": 10.0, "price": 4000.0, "clientOrderId": "AUR-SL-1"}
            ],
            bracket_plan=[
                {"action_type": "PLACE_SL", "qty": 10.0, "price": 4000.0, "why": "initial"}
            ]
        )
        
        # Verify log was written
        assert tmp_log.exists()
        
        with open(tmp_log, "r") as f:
            entry = json.loads(f.read())
        
        assert entry["event_kind"] == "BRACKET_EVAL_SNAPSHOT"
        assert entry["symbol"] == "ETHUSDT"
        assert entry["side"] == "SHORT"
        
        snapshot = json.loads(entry["snapshot"])
        assert len(snapshot["open_brackets"]) == 1
        assert len(snapshot["bracket_plan"]) == 1
        
    logging_v2.LOG_FILE = original_log_file
    print("✅ Direct logging test passed")
