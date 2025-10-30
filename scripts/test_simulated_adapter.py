#!/usr/bin/env python3
"""
Smoke test for SimulatedExecutionAdapter (Part EXECUTE-T04-B).

Runs basic validation without pytest framework.
Execute: python scripts/test_simulated_adapter.py
"""

import sys
from pathlib import Path
from decimal import Decimal

# Add paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "vfoundation" / "vfoundation"))
sys.path.insert(0, str(project_root / "apps"))

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.simulated_adapter import (
    SimulatedExecutionAdapter,
)


def test_simulated_adapter():
    """Run all smoke tests for SimulatedExecutionAdapter."""

    print("🧪 Running SimulatedExecutionAdapter smoke tests...")
    print()

    adapter = SimulatedExecutionAdapter()

    # Test 1: place_order returns ACCEPTED with correct structure
    print("Test 1: place_order")
    test_msg = Message(
        op="DEC",
        verb="OPEN",
        src="test",
        dst="execution",
        pld={"symbol": "BTCUSDT", "side": "buy", "qty": "0.01", "price": "50000.0"},
    )
    result = adapter.place_order(test_msg)

    assert result["status"] == "ACCEPTED", (
        f"❌ Expected ACCEPTED, got {result['status']}"
    )
    assert "sim_" in result["exchange_order_id"], (
        "❌ Order ID should have 'sim_' prefix"
    )
    assert Decimal(result["filled_qty"]) == Decimal("0.01"), "❌ Qty should match input"
    assert isinstance(result["timestamp"], int), "❌ Timestamp should be int"
    print(f"   ✅ Returns ACCEPTED with order_id={result['exchange_order_id']}")
    print(f"   ✅ Preserves quantity: {result['filled_qty']}")
    print()

    # Test 2: place_order preserves Decimal precision
    print("Test 2: Decimal precision preservation")
    high_precision_qty = "0.123456789012345678"
    precision_msg = Message(
        op="DEC",
        verb="OPEN",
        src="test",
        dst="execution",
        pld={
            "symbol": "ETHUSDT",
            "qty": high_precision_qty,
            "side": "sell",
            "price": "4000.0",
        },
    )
    result = adapter.place_order(precision_msg)

    assert result["filled_qty"] == high_precision_qty, (
        "❌ Decimal precision must be preserved"
    )
    assert Decimal(result["filled_qty"]) == Decimal(high_precision_qty), (
        "❌ Decimal conversion failed"
    )
    print(f"   ✅ Preserves high-precision qty: {high_precision_qty}")
    print()

    # Test 3: cancel_order returns ACCEPTED
    print("Test 3: cancel_order")
    cancel_msg = Message(
        op="DEC",
        verb="CANCEL",
        src="test",
        dst="execution",
        pld={"exchange_order_id": "sim_123456"},
    )
    result = adapter.cancel_order(cancel_msg)

    assert result["status"] == "ACCEPTED", "❌ Cancel should be accepted"
    assert result["exchange_order_id"] == "sim_123456", "❌ Order ID should be echoed"
    assert result["filled_qty"] == "0.0", "❌ No partial fills in simulation"
    print("   ✅ Returns ACCEPTED with echoed order_id")
    print(f"   ✅ No partial fills: {result['filled_qty']}")
    print()

    # Test 4: get_status returns CONNECTED
    print("Test 4: get_status")
    status = adapter.get_status()

    assert status == "CONNECTED", f"❌ Expected CONNECTED, got {status}"
    print("   ✅ Returns CONNECTED status")
    print()

    # Test 5: Unique order IDs
    print("Test 5: Unique order ID generation")
    result1 = adapter.place_order(test_msg)
    import time

    time.sleep(0.002)  # 2ms delay
    result2 = adapter.place_order(test_msg)

    assert result1["exchange_order_id"] != result2["exchange_order_id"], (
        "❌ Sequential orders should have unique IDs"
    )
    print(
        f"   ✅ Generated unique IDs: {result1['exchange_order_id']} != {result2['exchange_order_id']}"
    )
    print()

    # Test 6: Handles missing fields gracefully
    print("Test 6: Graceful handling of missing fields")
    minimal_msg = Message(
        op="DEC",
        verb="OPEN",
        src="test",
        dst="execution",
        pld={"symbol": "BTCUSDT"},  # Missing qty, side, price
    )
    result = adapter.place_order(minimal_msg)

    assert result["status"] == "ACCEPTED", "❌ Should not crash with minimal payload"
    assert "sim_" in result["exchange_order_id"], "❌ Should still generate order ID"
    print("   ✅ Doesn't crash with incomplete payload")
    print(f"   ✅ Uses defaults: qty={result['filled_qty']}")
    print()

    print("=" * 60)
    print("🎉 ALL TESTS PASSED!")
    print("=" * 60)
    print("\nSimulatedExecutionAdapter validation complete:")
    print("  ✅ place_order: Returns ACCEPTED with mock order ID")
    print("  ✅ cancel_order: Returns ACCEPTED with echoed ID")
    print("  ✅ get_status: Always returns CONNECTED")
    print("  ✅ Decimal precision: Preserved in filled_qty")
    print("  ✅ Unique IDs: Generated for each order")
    print("  ✅ Error handling: Graceful with missing fields")
    print()
    print("Ready for Part EXECUTE-T04-C integration!")


if __name__ == "__main__":
    try:
        test_simulated_adapter()
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
