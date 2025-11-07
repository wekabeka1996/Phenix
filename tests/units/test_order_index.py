"""
Unit tests for OrderIndex functionality.
"""

import time
import pytest
from apps.reference.domains.execution_position.order_index import (
    OrderIndex,
    OrderRef,
)


class TestOrderIndex:
    """Test cases for OrderIndex operations."""

    @pytest.fixture
    def order_index(self):
        """Create OrderIndex instance for testing."""
        return OrderIndex(ttl_sec=60)  # Short TTL for testing

    def test_upsert_from_open_new_order(self, order_index):
        """Test creating new order reference from OPEN operation."""
        ref = order_index.upsert_from_open(
            rid="r1",
            idempotent_key="idem1",
            clientOrderId="cid1",
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
        )

        assert ref.rid == "r1"
        assert ref.idempotent_key == "idem1"
        assert ref.clientOrderId == "cid1"
        assert ref.symbol == "ETHUSDT"
        assert ref.side == "BUY"
        assert ref.order_type == "MARKET"
        assert ref.terminal is False
        assert ref.created_ts <= time.time()

    def test_upsert_from_open_existing_order(self, order_index):
        """Test updating existing order reference."""
        # Create initial reference
        ref1 = order_index.upsert_from_open(
            rid="r1",
            idempotent_key="idem1",
            clientOrderId=None,
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
        )

        # Update with clientOrderId
        ref2 = order_index.upsert_from_open(
            rid="r1",
            idempotent_key="idem1",
            clientOrderId="cid1",
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
        )

        assert ref1 is ref2  # Same object
        assert ref2.clientOrderId == "cid1"

    def test_attach_exchange_id(self, order_index):
        """Test attaching exchange order ID."""
        # Create order reference
        order_index.upsert_from_open(
            rid="r1",
            idempotent_key="idem1",
            clientOrderId="cid1",
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
        )

        # Attach exchange ID
        ref = order_index.attach_exchange_id(
            clientOrderId="cid1", exchangeOrderId="ex1"
        )

        assert ref is not None
        assert ref.exchangeOrderId == "ex1"

    def test_attach_exchange_id_not_found(self, order_index):
        """Test attaching exchange ID when clientOrderId not found."""
        ref = order_index.attach_exchange_id(
            clientOrderId="nonexistent", exchangeOrderId="ex1"
        )

        assert ref is None

    def test_get_by_rid(self, order_index):
        """Test getting order reference by RID."""
        ref = order_index.upsert_from_open(
            rid="r1",
            idempotent_key="idem1",
            clientOrderId="cid1",
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
        )

        found = order_index.get(rid="r1")
        assert found is ref

    def test_get_by_client_order_id(self, order_index):
        """Test getting order reference by clientOrderId."""
        ref = order_index.upsert_from_open(
            rid="r1",
            idempotent_key="idem1",
            clientOrderId="cid1",
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
        )

        found = order_index.get(clientOrderId="cid1")
        assert found is ref

    def test_get_by_exchange_order_id(self, order_index):
        """Test getting order reference by exchangeOrderId."""
        order_index.upsert_from_open(
            rid="r1",
            idempotent_key="idem1",
            clientOrderId="cid1",
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
        )
        order_index.attach_exchange_id(
            clientOrderId="cid1", exchangeOrderId="ex1")

        found = order_index.get(exchangeOrderId="ex1")
        assert found is not None
        assert found.rid == "r1"

    def test_get_not_found(self, order_index):
        """Test getting non-existent order reference."""
        found = order_index.get(rid="nonexistent")
        assert found is None

    def test_mark_terminal(self, order_index):
        """Test marking order as terminal."""
        ref = order_index.upsert_from_open(
            rid="r1",
            idempotent_key="idem1",
            clientOrderId="cid1",
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
        )

        assert ref.terminal is False
        order_index.mark_terminal(ref)
        assert ref.terminal is True

    def test_expire_terminal_orders(self, order_index):
        """Test expiring terminal orders."""
        # Create order and mark as terminal
        ref = order_index.upsert_from_open(
            rid="r1",
            idempotent_key="idem1",
            clientOrderId="cid1",
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
        )
        order_index.mark_terminal(ref)

        # Expire should remove it
        removed = order_index.expire()
        assert removed == 1
        assert order_index.get(rid="r1") is None

    def test_expire_by_ttl(self, order_index):
        """Test expiring orders by TTL."""
        # Create order with very short TTL for testing
        short_ttl_index = OrderIndex(ttl_sec=1)

        ref = short_ttl_index.upsert_from_open(
            rid="r1",
            idempotent_key="idem1",
            clientOrderId="cid1",
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
        )

        # Wait for TTL to expire
        time.sleep(1.1)

        # Expire should remove it
        removed = short_ttl_index.expire()
        assert removed == 1
        assert short_ttl_index.get(rid="r1") is None

    def test_expire_preserves_active_orders(self, order_index):
        """Test that expire preserves non-terminal, non-expired orders."""
        ref = order_index.upsert_from_open(
            rid="r1",
            idempotent_key="idem1",
            clientOrderId="cid1",
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
        )

        # Expire should not remove active order
        removed = order_index.expire()
        assert removed == 0
        assert order_index.get(rid="r1") is ref

    def test_multiple_lookups_consistency(self, order_index):
        """Test that all lookup methods return the same reference."""
        order_index.upsert_from_open(
            rid="r1",
            idempotent_key="idem1",
            clientOrderId="cid1",
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
        )
        order_index.attach_exchange_id(
            clientOrderId="cid1", exchangeOrderId="ex1")

        by_rid = order_index.get(rid="r1")
        by_client = order_index.get(clientOrderId="cid1")
        by_exchange = order_index.get(exchangeOrderId="ex1")

        assert by_rid is by_client is by_exchange
        assert by_rid.rid == "r1"
        assert by_rid.clientOrderId == "cid1"
        assert by_rid.exchangeOrderId == "ex1"
