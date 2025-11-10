#!/usr/bin/env python3
"""
Test OrderGuardian cleanup with mock adapter to simulate real cleanup operations.
"""

from apps.reference.services.order_guardian import OrderGuardian
import asyncio
import logging
import sys
import os
from typing import Dict, List, Any, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))


# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Also set order_guardian logger to DEBUG
logging.getLogger('order_guardian').setLevel(logging.DEBUG)

LOG = logging.getLogger(__name__)


class MockAdapter:
    """Mock adapter for testing OrderGuardian cleanup"""

    def __init__(self):
        # Use exchange order IDs that match what OrderGuardian expects
        self.open_orders = [
            {
                "orderId": "EXCH_12345",  # Exchange order ID
                "clientOrderId": "client_12345",
                "symbol": "BTCUSDT",
                "status": "NEW",
                "type": "STOP_MARKET",
                "reduceOnly": True,
                "closePosition": True
            },
            {
                "orderId": "EXCH_12346",  # Exchange order ID
                "clientOrderId": "client_12346",
                "symbol": "BTCUSDT",
                "status": "NEW",
                "type": "TAKE_PROFIT_MARKET",
                "reduceOnly": True,
                "closePosition": True
            }
        ]
        self.positions = []  # No positions = should trigger cleanup

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return mock open orders"""
        if symbol:
            return [order for order in self.open_orders if order.get("symbol") == symbol]
        return self.open_orders

    async def get_open_positions(self) -> List[Dict[str, Any]]:
        """Return mock positions (empty to trigger cleanup)"""
        return self.positions

    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """Mock cancel order - always successful"""
        LOG.info(f"MockAdapter: Cancelling order {order_id} for {symbol}")
        # Remove from open orders
        self.open_orders = [
            o for o in self.open_orders if o.get("orderId") != order_id]
        return {"status": "CANCELED", "orderId": order_id}


async def test_guardian_cleanup_with_mock():
    """Test OrderGuardian cleanup with mock adapter"""
    LOG.info("🔍 Starting OrderGuardian cleanup test with mock adapter")

    # Create mock adapter
    mock_adapter = MockAdapter()

    # Create OrderGuardian with mock adapter
    guardian = OrderGuardian(
        adapter=mock_adapter,
        poll_interval_ms=1000,  # 1 second for faster testing
        bus=None
    )

    # Manually register some orders to simulate tracked brackets
    guardian.store.put("order:12345", {
        "symbol": "BTCUSDT",
        "type": "STOP_MARKET",
        "reduce_only": True,
        "close_position": True,
        "parent_entry_id": "99999",
        "client_order_id": "client_12345",
        "kind": "SL"
    })

    guardian.store.put("order:12346", {
        "symbol": "BTCUSDT",
        "type": "TAKE_PROFIT_MARKET",
        "reduce_only": True,
        "close_position": True,
        "parent_entry_id": "99999",
        "client_order_id": "client_12346",
        "kind": "TP"
    })

    # Simulate exchange order ID updates
    guardian.update_order_with_exchange_id("12345", "EXCH_12345", "BTCUSDT")
    guardian.update_order_with_exchange_id("12346", "EXCH_12346", "BTCUSDT")

    LOG.info("✅ OrderGuardian created with mock adapter and registered orders")

    try:
        # Start the cleanup loop
        await guardian.start()
        LOG.info("✅ OrderGuardian cleanup loop started")

        # Wait for cleanup to happen
        LOG.info("Waiting 5 seconds for cleanup operations...")
        await asyncio.sleep(5.0)

        LOG.info("✅ Test completed - cleanup should have cancelled orphan brackets")

    except Exception as e:
        LOG.error(f"❌ Test failed: {e}")
        raise
    finally:
        # Stop the guardian
        await guardian.stop()
        LOG.info("✅ OrderGuardian stopped")

if __name__ == "__main__":
    asyncio.run(test_guardian_cleanup_with_mock())
