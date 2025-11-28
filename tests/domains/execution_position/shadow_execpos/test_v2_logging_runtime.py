"""
Tests for V2 Runtime Logging
=============================

Verifies that ExecPosRuntimeV2 writes structured JSONL logs.
"""
import pytest
import json
import asyncio
from pathlib import Path
from unittest.mock import patch, mock_open

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.types import RuntimeEvent
from apps.reference.domains.execution_position.shadow_execpos import logging_v2
from tests.domains.execution_position.shadow_execpos.fake_adapter import FakeRecordingAdapter


@pytest.fixture
def fake_adapter():
    return FakeRecordingAdapter()


@pytest.fixture
def runtime(fake_adapter):
    config = {"cooldown_sec": 0.1}
    return ExecPosRuntimeV2(config, fake_adapter, None)


def parse_jsonl(content: str):
    """Parse JSONL content into list of dicts."""
    lines = [line for line in content.strip().split("\n") if line.strip()]
    return [json.loads(line) for line in lines]


@pytest.mark.asyncio
async def test_entry_rejected_logs_correctly(runtime, fake_adapter, tmp_path):
    """Test that rejected entry intent is logged with correct structure."""
    # Mock the log file to write to tmp directory
    log_file = tmp_path / "test_runtime.jsonl"

    with patch.object(logging_v2, 'LOG_FILE', log_file):
        # Inject instrument specs to enforce min_qty
        runtime.gatekeeper.update_instrument_specs({
            "BTCUSDT": {
                "min_qty": "0.000001",  # 1e-6
                "step_size": "0.00000001",
                "tick_size": "0.01",
                "min_notional": "5.0"
            }
        })

        # Create event with invalid quantity (too small)
        event = RuntimeEvent(
            kind="ENTRY_INTENT",
            symbol="BTCUSDT",
            timestamp=1700000000.0,
            payload={
                "side": "BUY",
                "quantity": "0.0000001",  # Too small (below min_qty 1e-6)
                "order_type": "MARKET"
            }
        )

        await runtime.handle(event)

        # Read and parse log
        assert log_file.exists()
        logs = parse_jsonl(log_file.read_text())

        # Should have one log entry
        assert len(logs) == 1
        log = logs[0]

        # Verify required fields
        assert log["runtime"] == "ExecPosRuntimeV2"
        assert log["symbol"] == "BTCUSDT"
        assert log["event_kind"] == "ENTRY_INTENT"
        assert log["action"] == "rejected"
        assert log["result"] == "blocked"
        assert "why" in log
        assert "ts" in log

        # Verify extra fields
        assert log["side"] == "BUY"
        assert log["quantity"] == "0.0000001"


@pytest.mark.asyncio
async def test_entry_success_logs_correctly(runtime, fake_adapter, tmp_path):
    """Test that successful entry intent is logged."""
    log_file = tmp_path / "test_runtime.jsonl"

    with patch.object(logging_v2, 'LOG_FILE', log_file):
        event = RuntimeEvent(
            kind="ENTRY_INTENT",
            symbol="BTCUSDT",
            timestamp=1700000000.0,
            payload={
                "side": "BUY",
                "quantity": "0.1",
                "price": "50000",
                "order_type": "LIMIT"
            }
        )

        await runtime.handle(event)

        logs = parse_jsonl(log_file.read_text())
        assert len(logs) == 1

        log = logs[0]
        assert log["runtime"] == "ExecPosRuntimeV2"
        assert log["event_kind"] == "ENTRY_INTENT"
        assert log["action"] == "executed"
        assert log["result"] == "success"
        assert "order_id" in log
        assert log["side"] == "BUY"


@pytest.mark.asyncio
async def test_logging_failure_doesnt_crash_runtime(runtime, fake_adapter):
    """Test that logging errors don't crash trading logic (fail-closed)."""
    # Mock logging to raise exception
    with patch.object(logging_v2, '_write_jsonl', side_effect=IOError("Disk full")):
        # This should NOT raise, even though logging fails
        event = RuntimeEvent(
            kind="ENTRY_INTENT",
            symbol="BTCUSDT",
            timestamp=1700000000.0,
            payload={
                "side": "BUY",
                "quantity": "0.1",
                "order_type": "MARKET"
            }
        )

        await runtime.handle(event)

        # Verify adapter was still called (trading logic proceeded)
        assert len(fake_adapter.calls) == 1


@pytest.mark.asyncio
async def test_multiple_events_create_multiple_logs(runtime, fake_adapter, tmp_path):
    """Test that multiple events create multiple JSONL lines."""
    log_file = tmp_path / "test_runtime.jsonl"

    with patch.object(logging_v2, 'LOG_FILE', log_file):
        # Send 3 events
        for i in range(3):
            event = RuntimeEvent(
                kind="ENTRY_INTENT",
                symbol=f"BTC{i}USDT",
                timestamp=1700000000.0 + i,
                payload={
                    "side": "BUY",
                    "quantity": "0.1",
                    "order_type": "MARKET"
                }
            )
            await runtime.handle(event)

        logs = parse_jsonl(log_file.read_text())
        assert len(logs) == 3

        # Verify each has unique symbol
        symbols = [log["symbol"] for log in logs]
        assert symbols == ["BTC0USDT", "BTC1USDT", "BTC2USDT"]
