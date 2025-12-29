"""
Test for order index synchronization with exchange.
"""
import pytest
from unittest.mock import MagicMock

from apps.reference.domains.execution_position.infra.order_index import OrderIndex


class TestOrderIndexSync:
    """Test order index synchronization."""

    def test_reconcile_snapshot_updates_index(self):
        """Test that reconcile_snapshot properly updates the index."""
        index = OrderIndex()

        # Initial state - empty
        assert len(index.get_by_symbol("BTCUSDT")) == 0

        # Mock orders from exchange
        orders = [
            {
                "orderId": "12345",
                "clientOrderId": "AUR-BTCUSDT-L-TP-C0-hash1",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "TAKE_PROFIT_MARKET",
                "quantity": "0.001",
                "price": None,
                "stopPrice": "51000",
                "status": "NEW"
            },
            {
                "orderId": "12346",
                "clientOrderId": "AUR-BTCUSDT-L-SL-C0-hash2",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "STOP_MARKET",
                "quantity": "0.001",
                "price": None,
                "stopPrice": "49000",
                "status": "NEW"
            }
        ]

        # Reconcile snapshot
        index.reconcile_snapshot("BTCUSDT", orders)

        # Verify orders are in index
        btc_orders = index.get_by_symbol("BTCUSDT")
        assert len(btc_orders) == 2

        # Verify by client ID lookup
        order1 = index.get(clientOrderId="AUR-BTCUSDT-L-TP-C0-hash1")
        assert order1 is not None
        assert order1.exchangeOrderId == "12345"

        order2 = index.get(clientOrderId="AUR-BTCUSDT-L-SL-C0-hash2")
        assert order2 is not None
        assert order2.exchangeOrderId == "12346"

    def test_empty_snapshot_clears_index(self):
        """Test that empty snapshot clears existing orders."""
        index = OrderIndex()

        # Add some orders
        orders = [
            {
                "orderId": "12345",
                "clientOrderId": "AUR-BTCUSDT-L-TP-C0-hash1",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "TAKE_PROFIT_MARKET",
                "quantity": "0.001",
                "status": "NEW"
            }
        ]
        index.reconcile_snapshot("BTCUSDT", orders)
        assert len(index.get_by_symbol("BTCUSDT")) == 1

        # Empty snapshot should clear (after grace period)
        import time
        time.sleep(2.1)  # Wait for in-flight grace period to expire
        index.reconcile_snapshot("BTCUSDT", [])
        assert len(index.get_by_symbol("BTCUSDT")) == 0

    def test_duplicate_client_id_prevents_new_order(self):
        """Test that duplicate clientOrderId prevents placement of new order."""
        index = OrderIndex()

        # Add existing order
        orders = [
            {
                "orderId": "12345",
                "clientOrderId": "AUR-BTCUSDT-L-TP-C0-hash1",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "TAKE_PROFIT_MARKET",
                "quantity": "0.001",
                "status": "NEW"
            }
        ]
        index.reconcile_snapshot("BTCUSDT", orders)

        # Check if client ID exists
        existing = index.get(clientOrderId="AUR-BTCUSDT-L-TP-C0-hash1")
        assert existing is not None

        # This simulates the duplicate check before placing new order
        # If client ID exists, we should not place new order
        assert existing.exchangeOrderId == "12345"
