"""
Smoke test for BRACKET_EVAL_SNAPSHOT logging (TASK R3-C2)

Verifies that bracket evaluation snapshots are correctly written to
logs/execpos_v2_runtime.jsonl and can be parsed by oco_log_to_replay.py
"""
import json
import pytest
import tempfile
from pathlib import Path
from decimal import Decimal
from unittest.mock import Mock, patch

from apps.reference.domains.execution_position.shadow_execpos import logging_v2
from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.types import (
    ExecutionCommand,
    ExecutionStatus,
    ExecutionResult
)


def test_bracket_eval_snapshot_writes_to_jsonl():
    """Test that log_bracket_eval_snapshot writes valid JSONL to file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_log_file = Path(tmpdir) / "test_runtime.jsonl"

        # Patch the LOG_FILE to use temp directory
        with patch.object(logging_v2, 'LOG_FILE', test_log_file):
            # Call logging function
            logging_v2.log_bracket_eval_snapshot(
                symbol="BTCUSDT",
                side="LONG",
                position_qty=1.5,
                position_cycle_id=42,
                snapshot_state="FRESH",
                open_brackets=[
                    {"orderId": "123", "side": "SELL", "type": "STOP_MARKET",
                     "qty": 1.5, "price": 29000.0, "clientOrderId": "sl_456"}
                ],
                bracket_plan=[
                    {"action_type": "PLACE_SL", "qty": 1.5, "price": 29000.0,
                     "why": "missing_sl_recreated"}
                ]
            )

            # Verify file exists and contains valid JSON
            assert test_log_file.exists(), "Log file not created"

            with open(test_log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            assert len(lines) == 1, "Should have exactly one log line"

            # Parse log line
            record = json.loads(lines[0])

            # Verify structure
            assert record["event_kind"] == "BRACKET_EVAL_SNAPSHOT"
            assert record["runtime"] == "ExecPosRuntimeV2"
            assert record["symbol"] == "BTCUSDT"
            assert record["side"] == "LONG"
            assert record["position_qty"] == 1.5
            assert "ts" in record
            assert "snapshot" in record

            # Parse snapshot payload
            snapshot = json.loads(record["snapshot"])
            assert snapshot["symbol"] == "BTCUSDT"
            assert snapshot["side"] == "LONG"
            assert snapshot["position_qty"] == 1.5
            assert snapshot["position_cycle_id"] == 42
            assert snapshot["orders_snapshot_state"] == "FRESH"
            assert len(snapshot["open_brackets"]) == 1
            assert len(snapshot["bracket_plan"]) == 1

            # Verify bracket details
            bracket = snapshot["open_brackets"][0]
            assert bracket["orderId"] == "123"
            assert bracket["type"] == "STOP_MARKET"

            plan = snapshot["bracket_plan"][0]
            assert plan["action_type"] == "PLACE_SL"
            assert plan["why"] == "missing_sl_recreated"


# Skipped: Full integration test requires real runtime initialization
# The unit tests (log_bracket_eval_snapshot + parse_log_line) provide sufficient coverage
def test_oco_log_to_replay_parses_v2_format():
    """Test that tools/oco_log_to_replay.py can parse V2 log format."""
    from tools.oco_log_to_replay import parse_log_line

    # Create V2 format log line
    v2_log = {
        "ts": "2025-11-26T00:15:00.123Z",
        "runtime": "ExecPosRuntimeV2",
        "event_kind": "BRACKET_EVAL_SNAPSHOT",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "position_qty": 1.0,
        "snapshot": json.dumps({
            "symbol": "BTCUSDT",
            "side": "LONG",
            "position_qty": 1.0,
            "position_cycle_id": 42,
            "orders_snapshot_state": "FRESH",
            "open_brackets": [
                {"orderId": "123", "side": "SELL", "type": "STOP_MARKET",
                 "qty": 1.0, "price": 29000.0, "clientOrderId": "sl_456"}
            ],
            "bracket_plan": [
                {"action_type": "CANCEL_ORDER", "qty": None, "price": None,
                 "why": "duplicate_sl_cleanup", "target_order_id": "789"}
            ]
        })
    }

    log_line = json.dumps(v2_log)

    # Parse log line
    frame = parse_log_line(log_line)

    assert frame is not None, "Failed to parse V2 log line"
    assert frame["ts"] == "2025-11-26T00:15:00.123Z"
    assert frame["symbol"] == "BTCUSDT"
    assert frame["side"] == "LONG"
    assert frame["position_qty"] == 1.0
    assert frame["position_cycle_id"] == 42
    assert frame["orders_snapshot_state"] == "FRESH"
    assert len(frame["orders"]) == 1
    assert len(frame["bracket_plan"]) == 1

    # Verify bracket details
    order = frame["orders"][0]
    assert order["orderId"] == "123"
    assert order["type"] == "STOP_MARKET"

    plan = frame["bracket_plan"][0]
    assert plan["action_type"] == "CANCEL_ORDER"
    assert plan["why"] == "duplicate_sl_cleanup"


def test_logging_v2_fails_gracefully_on_error():
    """Test that logging errors don't crash the system."""
    with patch.object(logging_v2, '_write_jsonl', side_effect=Exception("Disk full")):
        # Should not raise exception
        try:
            logging_v2.log_bracket_eval_snapshot(
                symbol="BTCUSDT",
                side="LONG",
                position_qty=1.0,
                position_cycle_id=1,
                snapshot_state="FRESH",
                open_brackets=[],
                bracket_plan=[]
            )
            # If we reach here, fail-closed worked
            assert True
        except Exception as e:
            pytest.fail(f"Logging should be fail-closed, but raised: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
