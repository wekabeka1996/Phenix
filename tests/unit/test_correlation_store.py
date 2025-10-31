#!/usr/bin/env python3
"""
Unit tests for CorrelationStore.
"""

import time
import pytest
from vfoundation.obs.correlation import CorrelationStore


class TestCorrelationStore:
    """Test CorrelationStore functionality."""

    def test_put_and_get_entry_ack(self):
        """Test storing and retrieving entry order correlation data."""
        store = CorrelationStore(ttl_hours=1)

        order_id = "12345"
        data = {
            'corr_id': 'uuid-entry-1',
            'oco_group_id': 'uuid-group-1',
            'rid': 'rid-123',
            'parent_client_order_id': None
        }

        store.put_entry_ack(order_id, data)
        retrieved = store.get_by_order_id(order_id)

        assert retrieved is not None
        assert retrieved['corr_id'] == 'uuid-entry-1'
        assert retrieved['oco_group_id'] == 'uuid-group-1'
        assert retrieved['rid'] == 'rid-123'
        assert retrieved['parent_client_order_id'] is None

    def test_put_and_get_sl_tp_ack(self):
        """Test storing and retrieving SL/TP order correlation data."""
        store = CorrelationStore(ttl_hours=1)

        order_id = "67890"
        parent_client_order_id = "entry-client-123"
        corr_id = 'uuid-entry-1'
        oco_group_id = 'uuid-group-1'
        rid = 'rid-123'

        store.put_sl_tp_ack(order_id, parent_client_order_id, corr_id, oco_group_id, rid)
        retrieved = store.get_by_order_id(order_id)

        assert retrieved is not None
        assert retrieved['corr_id'] == corr_id
        assert retrieved['parent_client_order_id'] == parent_client_order_id
        assert retrieved['oco_group_id'] == oco_group_id
        assert retrieved['rid'] == rid

    def test_get_nonexistent_order(self):
        """Test retrieving data for non-existent order ID."""
        store = CorrelationStore()
        retrieved = store.get_by_order_id("nonexistent")
        assert retrieved is None

    def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        store = CorrelationStore(ttl_hours=0.0001)  # Very short TTL ~0.36 seconds

        order_id = "12345"
        data = {'corr_id': 'uuid-1', 'oco_group_id': 'group-1', 'rid': 'rid-1'}
        store.put_entry_ack(order_id, data)

        # Should exist immediately
        assert store.get_by_order_id(order_id) is not None

        # Wait for expiration
        import time
        time.sleep(1.0)  # 1.0 seconds > 0.36 seconds TTL

        # Should be expired
        assert store.get_by_order_id(order_id) is None

    def test_cleanup_expired(self):
        """Test that expired entries are cleaned up."""
        store = CorrelationStore(ttl_hours=0.0001)

        # Add multiple entries
        for i in range(5):
            store.put_entry_ack(f"order_{i}", {'corr_id': f'uuid-{i}'})

        # All should exist
        assert len(store.store) == 5

        # Wait for expiration
        import time
        time.sleep(1.0)

        # Trigger cleanup by calling get_stats
        store.get_stats()

        # All should be cleaned up
        assert len(store.store) == 0

    def test_get_stats(self):
        """Test getting store statistics."""
        store = CorrelationStore(ttl_hours=1)

        stats = store.get_stats()
        assert stats['total_entries'] == 0
        assert stats['ttl_seconds'] == 3600

        store.put_entry_ack("123", {'corr_id': 'test'})
        stats = store.get_stats()
        assert stats['total_entries'] == 1
