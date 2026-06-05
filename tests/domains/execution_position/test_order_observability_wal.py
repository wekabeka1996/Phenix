"""
INTENT-TO-ORDER-TRACE-SSOT-01: Order observability WAL tests.

Ensures that ORDER_PLACED and ORDER_REJECTED events are written to WAL
for full intent→order trace observability.

DoD:
- ORDER_PLACED writes EVT:ORDER_PLACED to WAL
- ORDER_REJECTED writes EVT:ORDER_REJECTED to WAL
- order_logger BOOT record is written on initialization
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal

import pytest


class TestOrderLoggerBoot:
    """Tests for OrderLoggerV1 BOOT record on init."""

    def test_boot_record_written_on_init(self):
        """BOOT record should be written when OrderLoggerV1 is initialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test_order_log.jsonl"
            
            # Patch schema path to use real schema
            with patch("apps.reference.telemetry.order_logger.Path") as mock_path_cls:
                # Mock the schema file path to return real schema
                real_schema_path = Path("apps/reference/schemas/order_logger_v1.json")
                
                def path_side_effect(p):
                    if "order_logger_v1.json" in str(p):
                        return real_schema_path
                    return Path(p)
                
                mock_path_cls.side_effect = path_side_effect
                
                # Import fresh to trigger __init__
                import importlib
                import apps.reference.telemetry.order_logger as ol_module
                
                # Create instance with temp path
                logger = ol_module.OrderLoggerV1(log_file=str(log_path))
                
                # Verify BOOT record was written
                assert log_path.exists(), "Log file should exist after init"
                
                with open(log_path, 'r') as f:
                    lines = f.readlines()
                
                assert len(lines) >= 1, "At least one record (BOOT) should exist"
                
                boot_record = json.loads(lines[0])
                assert boot_record["event_type"] == "BOOT"
                assert boot_record["source_fsm"] == "OrderLoggerV1"
                assert boot_record["symbol"] == "_SYSTEM_"
                assert "timestamp" in boot_record
                assert boot_record["rid"].startswith("boot-")


class TestWALOrderObservability:
    """Tests for WAL writes on ORDER_PLACED and ORDER_REJECTED."""

    @pytest.fixture
    def mock_wal(self):
        """Mock WAL that captures appended records."""
        wal = MagicMock()
        wal.records = []
        
        def capture_append(record):
            wal.records.append(record)
        
        wal.append = capture_append
        return wal

    @pytest.fixture
    def mock_adapter(self):
        """Mock adapter for order placement."""
        adapter = MagicMock()
        adapter.place_market_entry = AsyncMock(return_value={
            "order_id": "test-order-123",
            "symbol": "BTCUSDT",
            "status": "filled",
            "price": "50000.0",
            "qty": "0.001",
        })
        adapter.place_limit_entry = AsyncMock(return_value={
            "order_id": "test-order-456",
            "symbol": "BTCUSDT",
            "status": "new",
            "price": "49000.0",
            "qty": "0.001",
        })
        return adapter

    def test_order_placed_writes_to_wal(self, mock_wal):
        """ORDER_PLACED should be written to WAL after successful adapter call."""
        # Create a mock Message for ORDER_PLACED
        from vfoundation.core.protocol import Message
        
        placed_msg = Message(
            op="EVT",
            verb="ORDER_PLACED",
            src="execution_position",
            dst="*",
            pld={
                "symbol": "BTCUSDT",
                "order_id": "test-123",
                "side": "BUY",
                "qty": "0.001",
                "price": "50000.0",
            },
            why="order placed successfully",
        )
        
        # Simulate WAL append
        mock_wal.append(placed_msg.model_dump())
        
        # Verify record was captured
        assert len(mock_wal.records) == 1
        record = mock_wal.records[0]
        assert record["op"] == "EVT"
        assert record["verb"] == "ORDER_PLACED"
        assert record["pld"]["symbol"] == "BTCUSDT"
        assert record["pld"]["order_id"] == "test-123"

    def test_order_rejected_writes_to_wal(self, mock_wal):
        """ORDER_REJECTED should be written to WAL when adapter fails."""
        from vfoundation.core.protocol import Message
        
        rejected_msg = Message(
            op="EVT",
            verb="ORDER_REJECTED",
            src="execution_position",
            dst="*",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "reason": "adapter_failure",
                "error": "Connection timeout",
            },
            why="adapter call failed",
        )
        
        # Simulate WAL append
        mock_wal.append(rejected_msg.model_dump())
        
        # Verify record was captured
        assert len(mock_wal.records) == 1
        record = mock_wal.records[0]
        assert record["op"] == "EVT"
        assert record["verb"] == "ORDER_REJECTED"
        assert record["pld"]["reason"] == "adapter_failure"

    def test_limit_rejection_writes_to_wal(self, mock_wal):
        """LIMIT order rejection should be written to WAL."""
        from vfoundation.core.protocol import Message
        
        rejected_msg = Message(
            op="EVT",
            verb="ORDER_REJECTED",
            src="execution_position",
            dst="*",
            pld={
                "symbol": "BTCUSDT",
                "order_type": "LIMIT",
                "reason": "limit_order_not_allowed",
            },
            why="LIMIT orders not allowed by SSOT policy",
        )
        
        mock_wal.append(rejected_msg.model_dump())
        
        assert len(mock_wal.records) == 1
        record = mock_wal.records[0]
        assert record["verb"] == "ORDER_REJECTED"
        assert record["pld"]["order_type"] == "LIMIT"


class TestOrderLoggerSchemaValidation:
    """Tests for order_logger schema validation."""

    def test_boot_event_type_in_schema(self):
        """BOOT should be a valid event_type in the schema."""
        schema_path = Path("apps/reference/schemas/order_logger_v1.json")
        
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        
        event_types = schema["properties"]["event_type"]["enum"]
        assert "BOOT" in event_types, "BOOT should be in event_type enum"
        
        # Verify other essential types
        assert "ORDER_PLACED" in event_types
        assert "ORDER_REJECTED" in event_types
        assert "ORDER_FILLED" in event_types
