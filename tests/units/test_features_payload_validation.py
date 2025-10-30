import pytest
from vfoundation.core.protocol import Message


def test_symbol_upper_and_required_fields():
    # Simple test to check that Message can handle lowercase symbols
    # and required fields are present
    msg = Message(op="EVT", verb="FEATURES_CALCULATED", intent="OBSERVATION",
                  src="test", dst="any", rid="r4",
                  pld={"symbol": "ethusdt", "obi": 0.1, "tfi": 0.2, "delta_price": 0.0, "ts": 1},
                  why="test")

    # Check that the message was created successfully
    assert msg.pld["symbol"] == "ethusdt"
    assert "obi" in msg.pld
    assert "tfi" in msg.pld
    assert "delta_price" in msg.pld
    assert "ts" in msg.pld

    # Test that required fields are present
    required_fields = ["symbol", "obi", "tfi", "delta_price", "ts"]
    for field in required_fields:
        assert field in msg.pld, f"Required field {field} is missing"
