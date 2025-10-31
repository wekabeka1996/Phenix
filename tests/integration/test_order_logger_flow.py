"""Integration test for OrderLoggerV1 flow from intent to execution."""

import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from vfoundation.obs.order_logger import order_logger
from vfoundation.core.protocol import Message


class TestOrderLoggerFlow:
    """Test complete order logging flow."""

    def setup_method(self):
        """Clean up log file before each test."""
        log_file = Path("logs/order_log_v1.jsonl")
        if log_file.exists():
            log_file.unlink()

    def teardown_method(self):
        """Clean up log file after each test."""
        log_file = Path("logs/order_log_v1.jsonl")
        if log_file.exists():
            log_file.unlink()

    def read_log_entries(self):
        """Read all entries from the log file."""
        log_file = Path("logs/order_log_v1.jsonl")
        if not log_file.exists():
            return []

        entries = []
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
        return entries

    def test_intent_to_open_flow(self):
        """Test ORDER_INTENT → ORDER_PLACED flow."""
        # Simulate ORDER_INTENT from DecisionMaking
        intent_entry = {
            "rid": "test_rid_001",
            "event_type": "ORDER_INTENT",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.001,
            "source_fsm": "DecisionMaking",
            "metadata": {"intent_proposed": True}
        }
        order_logger.write(intent_entry)

        # Simulate ORDER_PLACED from ExecPosFSM
        placed_entry = {
            "rid": "test_rid_001",
            "event_type": "ORDER_PLACED",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.001,
            "client_order_id": "ENTRY_BTCUSDT_123",
            "order_id": "12345",
            "source_fsm": "ExecPosFSM",
            "reservation_id": "reserve_001",
            "adapter_response": {"orderId": 12345, "status": "NEW"},
            "metadata": {"order_type": "MARKET_ENTRY"}
        }
        order_logger.write(placed_entry)

        # Simulate ORDER_STATE_CHANGED (FILLED)
        filled_entry = {
            "rid": "test_rid_001",
            "event_type": "ORDER_STATE_CHANGED",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.001,
            "price": 50000.0,
            "client_order_id": "ENTRY_BTCUSDT_123",
            "order_id": "12345",
            "source_fsm": "ExecPosFSM",
            "reservation_id": "reserve_001",
            "metadata": {"fill_status": "FILLED", "notional_usd": 50.0}
        }
        order_logger.write(filled_entry)

        # Verify log entries
        entries = self.read_log_entries()
        assert len(entries) == 3

        # Check INTENT entry
        intent = next(e for e in entries if e["event_type"] == "ORDER_INTENT")
        assert intent["rid"] == "test_rid_001"
        assert intent["symbol"] == "BTCUSDT"
        assert intent["side"] == "BUY"
        assert intent["source_fsm"] == "DecisionMaking"

        # Check PLACED entry
        placed = next(e for e in entries if e["event_type"] == "ORDER_PLACED")
        assert placed["rid"] == "test_rid_001"
        assert placed["order_id"] == "12345"
        assert placed["client_order_id"] == "ENTRY_BTCUSDT_123"
        assert placed["adapter_response"]["orderId"] == 12345
        assert placed["source_fsm"] == "ExecPosFSM"

        # Check STATE_CHANGED entry
        state_changed = next(e for e in entries if e["event_type"] == "ORDER_STATE_CHANGED")
        assert state_changed["rid"] == "test_rid_001"
        assert state_changed["metadata"]["fill_status"] == "FILLED"
        assert state_changed["metadata"]["notional_usd"] == 50.0

    def test_rejection_flows(self):
        """Test various rejection scenarios."""
        # QoS defer rejection
        defer_entry = {
            "rid": "test_rid_002",
            "event_type": "ORDER_INTENT",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "nrr_code": "NRR-012",
            "why": "QoS cooldown active",
            "source_fsm": "DecisionMaking",
            "metadata": {"defer_reason": "QOS_COOLDOWN"}
        }
        order_logger.write(defer_entry)

        # Exposure limit rejection
        exposure_entry = {
            "rid": "test_rid_003",
            "event_type": "ORDER_REJECTED",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 1.0,
            "nrr_code": "NRR-011",
            "why": "Exposure limit exceeded: 100000.0 > 50000.0",
            "source_fsm": "ExposureGuard",
            "metadata": {"exposure_check": True}
        }
        order_logger.write(exposure_entry)

        # Execution failure rejection
        exec_fail_entry = {
            "rid": "test_rid_004",
            "event_type": "ORDER_REJECTED",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.001,
            "nrr_code": "NRR-015",
            "why": "Adapter execution failed: Connection timeout",
            "source_fsm": "ExecPosFSM",
            "metadata": {"error": "Connection timeout"}
        }
        order_logger.write(exec_fail_entry)

        # Verify entries
        entries = self.read_log_entries()
        assert len(entries) == 3

        # Check QoS defer
        qos = next(e for e in entries if e["nrr_code"] == "NRR-012")
        assert qos["event_type"] == "ORDER_INTENT"
        assert qos["metadata"]["defer_reason"] == "QOS_COOLDOWN"

        # Check exposure rejection
        exposure = next(e for e in entries if e["nrr_code"] == "NRR-011")
        assert exposure["event_type"] == "ORDER_REJECTED"
        assert "Exposure limit exceeded" in exposure["why"]

        # Check execution failure
        exec_fail = next(e for e in entries if e["nrr_code"] == "NRR-015")
        assert exec_fail["event_type"] == "ORDER_REJECTED"
        assert "Adapter execution failed" in exec_fail["why"]

    def test_reservation_logging(self):
        """Test reservation creation and usage logging."""
        # Reservation created
        reserve_entry = {
            "rid": "reserve_test_001",
            "event_type": "ORDER_INTENT",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.001,
            "source_fsm": "ExposureGuard",
            "reservation_id": "reserve_123",
            "metadata": {"reservation_created": True}
        }
        order_logger.write(reserve_entry)

        # Order placed with reservation
        placed_entry = {
            "rid": "order_test_001",
            "event_type": "ORDER_PLACED",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.001,
            "reservation_id": "reserve_123",
            "source_fsm": "ExecPosFSM",
            "metadata": {"order_type": "MARKET_ENTRY"}
        }
        order_logger.write(placed_entry)

        # Fill event
        fill_entry = {
            "rid": "fill_test_001",
            "event_type": "ORDER_STATE_CHANGED",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.001,
            "price": 50000.0,
            "reservation_id": "reserve_123",
            "source_fsm": "ExecPosFSM",
            "metadata": {"fill_status": "FILLED"}
        }
        order_logger.write(fill_entry)

        # Verify reservation_id consistency
        entries = self.read_log_entries()
        assert len(entries) == 3

        reservation_ids = [e.get("reservation_id") for e in entries]
        assert all(rid == "reserve_123" for rid in reservation_ids if rid is not None)

    def test_timestamp_ordering(self):
        """Test that entries have timestamps and are in order."""
        import time

        start_time = int(time.time() * 1000)

        # Write entries with small delay
        for i in range(3):
            entry = {
                "rid": f"timestamp_test_{i}",
                "event_type": "ORDER_INTENT",
                "symbol": "BTCUSDT",
                "source_fsm": "DecisionMaking"
            }
            order_logger.write(entry)
            time.sleep(0.001)  # 1ms delay

        entries = self.read_log_entries()
        assert len(entries) == 3

        # Check timestamps exist and are increasing
        timestamps = [e["timestamp"] for e in entries]
        assert all(ts >= start_time for ts in timestamps)
        assert timestamps == sorted(timestamps)

    def test_correlation_by_rid(self):
        """Test that entries can be correlated by RID."""
        test_rid = "correlation_test_123"

        # Multiple events for same RID
        events = [
            {"event_type": "ORDER_INTENT", "symbol": "BTCUSDT"},
            {"event_type": "ORDER_PLACED", "order_id": "12345"},
            {"event_type": "ORDER_STATE_CHANGED", "metadata": {"fill_status": "FILLED"}},
        ]

        for event in events:
            entry = {
                "rid": test_rid,
                "source_fsm": "TestFSM",
                "symbol": "BTCUSDT",
                **event
            }
            order_logger.write(entry)

        entries = self.read_log_entries()
        assert len(entries) == 3

        # All entries should have same RID
        rids = [e["rid"] for e in entries]
        assert all(rid == test_rid for rid in rids)

        # Should have all event types
        event_types = {e["event_type"] for e in entries}
        assert event_types == {"ORDER_INTENT", "ORDER_PLACED", "ORDER_STATE_CHANGED"}
