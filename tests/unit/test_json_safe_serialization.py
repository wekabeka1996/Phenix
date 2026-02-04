"""
Unit tests for JSON serialization safety in WAL writes.

Tests that Decimal, datetime, and nested structures are serialized correctly.
"""

import json
from decimal import Decimal
from datetime import datetime
import pytest


def json_safe_value(v):
    """Convert non-JSON-serializable values to JSON-safe types."""
    if isinstance(v, Decimal):
        return float(v)
    elif isinstance(v, datetime):
        return v.isoformat()
    elif isinstance(v, dict):
        return {k: json_safe_value(val) for k, val in v.items()}
    elif isinstance(v, (list, tuple)):
        return [json_safe_value(item) for item in v]
    return v


class TestJsonSafeValue:
    """Tests for json_safe_value helper."""
    
    def test_decimal_conversion(self):
        """Decimal should be converted to float."""
        result = json_safe_value(Decimal("1.234"))
        assert isinstance(result, float)
        assert abs(result - 1.234) < 0.001
    
    def test_datetime_conversion(self):
        """Datetime should be converted to ISO string."""
        dt = datetime(2026, 2, 3, 12, 30, 45)
        result = json_safe_value(dt)
        assert isinstance(result, str)
        assert result == "2026-02-03T12:30:45"
    
    def test_nested_dict(self):
        """Nested dicts with Decimal/datetime should be converted."""
        data = {
            "score": Decimal("0.75"),
            "timestamp": datetime(2026, 1, 1),
            "nested": {
                "value": Decimal("-0.5")
            }
        }
        result = json_safe_value(data)
        
        assert isinstance(result["score"], float)
        assert isinstance(result["timestamp"], str)
        assert isinstance(result["nested"]["value"], float)
        
        # Must be JSON serializable
        json_str = json.dumps(result)
        assert json_str
    
    def test_list_of_decimals(self):
        """Lists with Decimals should be converted."""
        data = [Decimal("1"), Decimal("2"), Decimal("3")]
        result = json_safe_value(data)
        
        assert result == [1.0, 2.0, 3.0]
        json.dumps(result)  # Must not raise
    
    def test_alpha_score_like_dict(self):
        """AlphaScore-like structure should serialize correctly."""
        score_dict = {
            "model_name": "aurora_adapter",
            "symbol": "BTCUSDT",
            "score": Decimal("0.42"),
            "confidence": Decimal("0.85"),
            "timestamp": datetime(2026, 2, 3, 20, 0, 0),
            "features_used": ["delta_price", "vol_ratio"],
            "why": ["strong_momentum", "high_vol"]
        }
        
        result = json_safe_value(score_dict)
        
        # All values should be JSON-serializable
        json_str = json.dumps(result)
        parsed = json.loads(json_str)
        
        assert parsed["score"] == 0.42
        assert parsed["confidence"] == 0.85
        assert parsed["timestamp"] == "2026-02-03T20:00:00"
        assert parsed["features_used"] == ["delta_price", "vol_ratio"]
    
    def test_passthrough_primitives(self):
        """Primitives should pass through unchanged."""
        assert json_safe_value("string") == "string"
        assert json_safe_value(42) == 42
        assert json_safe_value(3.14) == 3.14
        assert json_safe_value(True) is True
        assert json_safe_value(None) is None
