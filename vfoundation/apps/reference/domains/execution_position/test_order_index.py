"""
Unit tests for OrderIndex correlation system.
"""

import time
import pytest
from .order_index import OrderIndex, OrderRef


class TestOrderIndex:
    """Test OrderIndex functionality."""

    def test_upsert_from_open(self):
        """Test creating order reference from OPEN operation."""
        idx = OrderIndex()
        ref = idx.upsert_from_open(
            rid="test_rid",
            idempotent_key="test_key",
            clientOrderId="client123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
        )

        assert ref.rid == "test_rid"
        assert ref.idempotent_key == "test_key"
        assert ref.clientOrderId == "client123"
        assert ref.symbol == "BTCUSDT"
        assert ref.side == "BUY"
        assert ref.order_type == "MARKET"
        assert not ref.terminal

    def test_get_by_rid(self):
        """Test lookup by rid."""
        idx = OrderIndex()
        idx.upsert_from_open(
            rid="test_rid",
            idempotent_key="test_key",
            clientOrderId="client123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
        )

        found = idx.get(rid="test_rid")
        assert found is not None
        assert found.rid == "test_rid"

    def test_get_by_client_order_id(self):
        """Test lookup by clientOrderId."""
        idx = OrderIndex()
        idx.upsert_from_open(
            rid="test_rid",
            idempotent_key="test_key",
            clientOrderId="client123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
        )

        found = idx.get(clientOrderId="client123")
        assert found is not None
        assert found.clientOrderId == "client123"

    def test_attach_exchange_id(self):
        """Test attaching exchange order ID."""
        idx = OrderIndex()
        ref = idx.upsert_from_open(
            rid="test_rid",
            idempotent_key="test_key",
            clientOrderId="client123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
        )

        updated = idx.attach_exchange_id(clientOrderId="client123", exchangeOrderId="exchange456")
        assert updated is ref
        assert ref.exchangeOrderId == "exchange456"

        # Test lookup by exchange ID
        found = idx.get(exchangeOrderId="exchange456")
        assert found is ref

    def test_get_by_exchange_order_id(self):
        """Test lookup by exchangeOrderId."""
        idx = OrderIndex()
        idx.upsert_from_open(
            rid="test_rid",
            idempotent_key="test_key",
            clientOrderId="client123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
        )
        idx.attach_exchange_id(clientOrderId="client123", exchangeOrderId="exchange456")

        found = idx.get(exchangeOrderId="exchange456")
        assert found is not None
        assert found.exchangeOrderId == "exchange456"

    def test_mark_terminal(self):
        """Test marking order as terminal."""
        idx = OrderIndex()
        ref = idx.upsert_from_open(
            rid="test_rid",
            idempotent_key="test_key",
            clientOrderId="client123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
        )

        assert not ref.terminal
        idx.mark_terminal(ref)
        assert ref.terminal

    def test_expire_by_ttl(self):
        """Test TTL-based expiration."""
        idx = OrderIndex(ttl_sec=1)  # 1 second TTL
        ref = idx.upsert_from_open(
            rid="test_rid",
            idempotent_key="test_key",
            clientOrderId="client123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
        )

        # Manually set old timestamp
        ref.created_ts = time.time() - 2  # 2 seconds ago

        removed = idx.expire()
        assert removed == 1

        # Should not be found anymore
        found = idx.get(rid="test_rid")
        assert found is None

    def test_expire_terminal(self):
        """Test expiration of terminal orders."""
        idx = OrderIndex(ttl_sec=3600)  # Long TTL
        ref = idx.upsert_from_open(
            rid="test_rid",
            idempotent_key="test_key",
            clientOrderId="client123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
        )

        idx.mark_terminal(ref)
        removed = idx.expire()
        assert removed == 1

        # Should not be found anymore
        found = idx.get(rid="test_rid")
        assert found is None

    def test_get_not_found(self):
        """Test lookup of non-existent order."""
        idx = OrderIndex()

        assert idx.get(rid="nonexistent") is None
        assert idx.get(clientOrderId="nonexistent") is None
        assert idx.get(exchangeOrderId="nonexistent") is None

    def test_upsert_updates_existing(self):
        """Test that upsert updates existing reference."""
        idx = OrderIndex()
        ref1 = idx.upsert_from_open(
            rid="test_rid",
            idempotent_key="test_key",
            clientOrderId=None,
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
        )

        # Update with clientOrderId
        ref2 = idx.upsert_from_open(
            rid="test_rid",
            idempotent_key="test_key",
            clientOrderId="client123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
        )

        assert ref1 is ref2
        assert ref2.clientOrderId == "client123"
