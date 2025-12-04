"""
Tests for portfolio_state_v1.json schema validation.

Validates that EVT:PORTFOLIO_STATE_UPDATED payloads conform to the updated schema.
"""

import json
import os
from decimal import Decimal
from pathlib import Path
import pytest


def load_schema():
    """Load the portfolio_state_v1.json schema."""
    schema_path = Path(__file__).parent.parent.parent / "apps" / "reference" / "domains" / "position_tracking" / "schemas" / "portfolio_state_v1.json"
    with open(schema_path) as f:
        return json.load(f)


@pytest.fixture
def schema():
    """Fixture for the schema."""
    return load_schema()


class TestSchemaStructure:
    """Tests for schema structure."""

    def test_schema_uses_draft_2020_12(self, schema):
        """Test schema uses JSON Schema 2020-12."""
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_schema_has_required_id(self, schema):
        """Test schema has required $id."""
        assert schema["$id"] == "portfolio_state_v1.json"

    def test_schema_required_fields(self, schema):
        """Test schema has correct required fields."""
        required = schema["required"]
        assert "ts" in required
        assert "equity" in required
        assert "realized_pnl" in required
        assert "unrealized_pnl" in required
        assert "positions" in required
        assert "positions_last_ts_ms" in required

    def test_schema_has_new_fields(self, schema):
        """Test schema includes all new fields (EXP-FIX, EXP-LEVERAGE-001)."""
        properties = schema["properties"]
        
        # EXP-FIX fields
        assert "equity_free_usdt" in properties
        assert "equity_cross_usdt" in properties
        assert "equity_ts" in properties
        assert "available_balance" in properties
        assert "open_positions_usd" in properties
        assert "open_positions_margin_usd" in properties
        assert "positions_by_side" in properties
        assert "positions_last_ts_ms" in properties

    def test_schema_positions_by_side_structure(self, schema):
        """Test positions_by_side has correct structure."""
        positions_by_side = schema["properties"]["positions_by_side"]
        
        assert positions_by_side["type"] == "object"
        assert "long_margin" in positions_by_side["properties"]
        assert "short_margin" in positions_by_side["properties"]
        assert positions_by_side["required"] == ["long_margin", "short_margin"]

    def test_schema_allows_additional_properties(self, schema):
        """Test schema allows additional properties (for backward compat)."""
        assert schema["additionalProperties"] == True

    def test_schema_position_item_structure(self, schema):
        """Test position item has correct structure."""
        position_schema = schema["properties"]["positions"]["items"]
        
        assert "symbol" in position_schema["properties"]
        assert "net_position" in position_schema["properties"]
        assert "avg_entry_price" in position_schema["properties"]
        assert "venues" in position_schema["properties"]


class TestSchemaValidation:
    """Tests for validating payloads against schema."""

    @pytest.fixture
    def valid_payload(self):
        """Create a valid portfolio state payload."""
        return {
            "ts": 1700000000000,
            "equity": "10000.00",
            "equity_free_usdt": "9500.00",
            "equity_cross_usdt": "9500.00",
            "equity_ts": 1700000000000,
            "realized_pnl": "500.00",
            "unrealized_pnl": "100.00",
            "available_balance": "8000.00",
            "open_positions_usd": "5000.00",
            "open_positions_margin_usd": "50.00",
            "positions_by_side": {
                "long_margin": "30.00",
                "short_margin": "20.00"
            },
            "positions_last_ts_ms": 1700000000000,
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "net_position": "0.1",
                    "avg_entry_price": "50000.00",
                    "venues": ["binance"]
                }
            ]
        }

    def test_valid_payload_matches_schema(self, schema, valid_payload):
        """Test that a valid payload matches the schema structure."""
        # Basic structural validation
        for field in schema["required"]:
            assert field in valid_payload, f"Missing required field: {field}"

    def test_decimal_string_pattern(self, schema):
        """Test decimal string pattern is correct."""
        pattern = schema["properties"]["equity"]["pattern"]
        
        import re
        regex = re.compile(pattern)
        
        # Valid patterns
        assert regex.match("0")
        assert regex.match("100")
        assert regex.match("100.50")
        assert regex.match("-100.50")
        assert regex.match("0.01")
        
        # Invalid patterns
        assert not regex.match("abc")
        assert not regex.match("")

    def test_positions_array_validation(self, schema):
        """Test positions array item validation."""
        position_schema = schema["properties"]["positions"]["items"]
        required_pos_fields = position_schema["required"]
        
        assert "symbol" in required_pos_fields
        assert "net_position" in required_pos_fields
        assert "avg_entry_price" in required_pos_fields
        assert "venues" in required_pos_fields


class TestSchemaWithRealPositionTracking:
    """Integration tests with real PositionTracking output."""

    def test_start_emits_schema_compliant_payload(self, schema):
        """Test that start() emits schema-compliant payload."""
        from apps.reference.domains.position_tracking.position_tracking import (
            PositionTracking,
        )
        
        class FSMCoreMock:
            def __init__(self):
                self.emitted = []
            
            def listen(self, *args, **kwargs):
                pass
            
            def emit(self, event_name, payload, why):
                self.emitted.append({"event": event_name, "payload": payload})
        
        fsm = FSMCoreMock()
        config = {"position_limits": {"max_positions": 10}}
        pt = PositionTracking(fsm=fsm, config=config)
        pt.start()
        
        # Find portfolio state event
        portfolio_events = [e for e in fsm.emitted if "PORTFOLIO" in e["event"]]
        assert len(portfolio_events) >= 1
        
        payload = portfolio_events[0]["payload"]
        
        # Validate required fields
        for field in schema["required"]:
            assert field in payload, f"Missing required field: {field}"

    def test_trade_emits_schema_compliant_payload(self, schema):
        """Test that on_trade_executed emits schema-compliant payload."""
        from apps.reference.domains.position_tracking.position_tracking import (
            PositionTracking,
        )
        from vfoundation.core.protocol import Message
        from unittest import mock
        
        class FSMCoreMock:
            def __init__(self):
                self.emitted = []
            
            def listen(self, *args, **kwargs):
                pass
            
            def emit(self, event_name, payload, why):
                self.emitted.append({"event": event_name, "payload": payload})
        
        fsm = FSMCoreMock()
        config = {"position_limits": {"max_positions": 10}}
        pt = PositionTracking(fsm=fsm, config=config)
        
        trade_event = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="test",
            dst="any",
            pld={
                "symbol": "BTCUSDT",
                "side": "buy",
                "price": 50000.0,
                "quantity": 0.1,
                "ts": 1700000000000,
                "fees": 0.5,
                "venue": "binance",
            },
            why="test",
        )
        
        with mock.patch('apps.reference.domains.position_tracking.position_tracking.wal') as mock_wal:
            mock_wal.append.return_value = "test_hash"
            pt.on_trade_executed(trade_event)
        
        # Find last portfolio state event
        portfolio_events = [e for e in fsm.emitted if "PORTFOLIO" in e["event"]]
        assert len(portfolio_events) >= 1
        
        payload = portfolio_events[-1]["payload"]
        
        # Validate required fields
        for field in schema["required"]:
            assert field in payload, f"Missing required field: {field}"
        
        # Validate positions_by_side structure
        assert "positions_by_side" in payload
        assert "long_margin" in payload["positions_by_side"]
        assert "short_margin" in payload["positions_by_side"]


class TestUnrealizedPnLInSchema:
    """Tests for unrealized_pnl field in schema."""

    def test_unrealized_pnl_description_updated(self, schema):
        """Test unrealized_pnl description mentions mark price formula."""
        description = schema["properties"]["unrealized_pnl"]["description"]
        assert "mark_price" in description.lower() or "entry_price" in description.lower()

    def test_unrealized_pnl_allows_negative(self, schema):
        """Test unrealized_pnl pattern allows negative numbers."""
        import re
        pattern = schema["properties"]["unrealized_pnl"]["pattern"]
        regex = re.compile(pattern)
        
        assert regex.match("-500.00")
        assert regex.match("-0.01")
