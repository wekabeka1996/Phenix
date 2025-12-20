"""Test OrderLoggerV1 schema validation and constraints."""

import json
import os
import pytest
from pathlib import Path

from apps.reference.telemetry.order_logger import OrderLoggerV1


class TestOrderLoggerSchema:
    """Test OrderLoggerV1 schema validation."""

    def test_valid_minimal_entry(self):
        """Test minimal valid entry."""
        logger = OrderLoggerV1()
        entry = {
            "rid": "test_rid_123",
            "timestamp": 1640995200000,  # 2022-01-01 00:00:00 UTC in milliseconds
            "event_type": "ORDER_INTENT",
            "symbol": "BTCUSDT",
            "source_fsm": "DecisionMaking"
        }
        # Should not raise exception
        logger.write(entry)

    def test_valid_full_entry(self):
        """Test full valid entry with all fields."""
        logger = OrderLoggerV1()
        entry = {
            "rid": "test_rid_123",
            "timestamp": 1640995200000,
            "event_type": "ORDER_PLACED",
            "order_id": "12345",
            "client_order_id": "client_123",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.001,
            "price": 50000.0,
            "nrr_code": "NRR-011",
            "why": "Test reason",
            "source_fsm": "ExecPosFSM",
            "reservation_id": "reserve_123",
            "adapter_response": {"orderId": 12345, "status": "NEW"},
            "metadata": {"test": "data"}
        }
        logger.write(entry)

    def test_invalid_event_type(self):
        """Test invalid event_type."""
        os.environ['ENV'] = 'TEST'
        logger = OrderLoggerV1()
        entry = {
            "rid": "test_rid_123",
            "timestamp": 1640995200000,
            "event_type": "INVALID_TYPE",
            "symbol": "BTCUSDT",
            "source_fsm": "DecisionMaking"
        }
        with pytest.raises(ValueError, match="validation failed"):
            logger.write(entry)

    def test_invalid_nrr_code_format(self):
        """Test invalid NRR code format."""
        os.environ['ENV'] = 'TEST'
        logger = OrderLoggerV1()
        entry = {
            "rid": "test_rid_123",
            "timestamp": 1640995200000,
            "event_type": "ORDER_INTENT",
            "symbol": "BTCUSDT",
            "source_fsm": "DecisionMaking",
            "nrr_code": "INVALID-123"
        }
        with pytest.raises(ValueError, match="validation failed"):
            logger.write(entry)

    def test_valid_nrr_code_format(self):
        """Test valid NRR code format."""
        logger = OrderLoggerV1()
        entry = {
            "rid": "test_rid_123",
            "timestamp": 1640995200000,
            "event_type": "ORDER_INTENT",
            "symbol": "BTCUSDT",
            "source_fsm": "DecisionMaking",
            "nrr_code": "NRR-011"
        }
        logger.write(entry)

    def test_why_max_length(self):
        """Test why field max length."""
        logger = OrderLoggerV1()
        # Valid length
        entry = {
            "rid": "test_rid_123",
            "timestamp": 1640995200000,
            "event_type": "ORDER_INTENT",
            "symbol": "BTCUSDT",
            "source_fsm": "DecisionMaking",
            "why": "x" * 80  # Exactly 80 chars
        }
        logger.write(entry)

        # Invalid length
        os.environ['ENV'] = 'TEST'
        entry["why"] = "x" * 81  # 81 chars
        with pytest.raises(ValueError, match="validation failed"):
            logger.write(entry)

    def test_required_fields(self):
        """Test required fields validation."""
        os.environ['ENV'] = 'TEST'
        logger = OrderLoggerV1()
        # Missing rid
        entry = {
            "timestamp": 1640995200000,
            "event_type": "ORDER_INTENT",
            "symbol": "BTCUSDT",
            "source_fsm": "DecisionMaking"
        }
        with pytest.raises(ValueError, match="validation failed"):
            logger.write(entry)

        # Missing event_type
        entry = {
            "rid": "test_rid_123",
            "timestamp": 1640995200000,
            "symbol": "BTCUSDT",
            "source_fsm": "DecisionMaking"
        }
        with pytest.raises(ValueError, match="validation failed"):
            logger.write(entry)

        # Missing symbol
        entry = {
            "rid": "test_rid_123",
            "timestamp": 1640995200000,
            "event_type": "ORDER_INTENT",
            "source_fsm": "DecisionMaking"
        }
        with pytest.raises(ValueError, match="validation failed"):
            logger.write(entry)

        # Missing source_fsm
        entry = {
            "rid": "test_rid_123",
            "timestamp": 1640995200000,
            "event_type": "ORDER_INTENT",
            "symbol": "BTCUSDT"
        }
        with pytest.raises(ValueError, match="validation failed"):
            logger.write(entry)

    def test_side_enum_values(self):
        """Test side enum validation."""
        logger = OrderLoggerV1()
        valid_sides = ["BUY", "SELL", "NONE"]

        for side in valid_sides:
            entry = {
                "rid": "test_rid_123",
                "timestamp": 1640995200000,
                "event_type": "ORDER_INTENT",
                "symbol": "BTCUSDT",
                "source_fsm": "DecisionMaking",
                "side": side
            }
            logger.write(entry)

        # Invalid side
        os.environ['ENV'] = 'TEST'
        entry["side"] = "INVALID"
        with pytest.raises(ValueError, match="validation failed"):
            logger.write(entry)

    def test_timestamp_auto_addition(self):
        """Test automatic timestamp addition."""
        logger = OrderLoggerV1()
        entry = {
            "rid": "test_rid_123",
            "event_type": "ORDER_INTENT",
            "symbol": "BTCUSDT",
            "source_fsm": "DecisionMaking"
        }
        logger.write(entry)
        # Should not raise exception - timestamp added automatically
