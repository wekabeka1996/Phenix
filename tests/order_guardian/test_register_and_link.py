"""
Tests for OrderGuardian registration and linking functionality.

Tests:
- register_entry: basic entry registration
- register_bracket: bracket registration with parent linkage
- link_existing_from_rest: placeholder implementation
- get_brackets_for_entry: query brackets for entry
- get_our_open_brackets: query open brackets (placeholder)
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from apps.reference.domains.execution_position.guardian.order_guardian import OrderGuardian, InMemoryStore


class TestRegisterAndLink:
    """Test OrderGuardian registration and linking functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.adapter = Mock()
        self.store = InMemoryStore()
        self.guardian = OrderGuardian(
            adapter=self.adapter,
            store=self.store,
            poll_interval_ms=0  # Disable polling
        )

    def test_register_entry_basic(self):
        """Test basic entry order registration"""
        # Register entry
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        # Verify entry data stored
        entry_key = "entry:12345"
        entry_data = self.store.get(entry_key)
        assert entry_data is not None
        assert entry_data["symbol"] == "BTCUSDT"
        assert entry_data["side"] == "BUY"
        assert entry_data["qty"] == 1.0
        assert "brackets" in entry_data
        assert entry_data["brackets"] == {}

        # Verify mappings
        client_mapping = self.store.get("client:client_123")
        assert client_mapping == "12345"

        order_meta = self.store.get("order:12345")
        assert order_meta["symbol"] == "BTCUSDT"
        assert order_meta["type"] == "MARKET"
        assert order_meta["reduce_only"] is False
        assert order_meta["close_position"] is False
        assert order_meta["parent_entry_id"] is None

    def test_register_entry_with_timestamp(self):
        """Test entry registration with custom timestamp"""
        custom_ts = 1234567890.0

        self.guardian.register_entry(
            symbol="ETHUSDT",
            order_id="67890",
            client_order_id="client_456",
            side="SELL",
            qty=0.5,
            ts=custom_ts
        )

        entry_data = self.store.get("entry:67890")
        assert entry_data["ts"] == custom_ts

    def test_register_bracket_sl(self):
        """Test stop-loss bracket registration"""
        # First register entry
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        # Register SL bracket
        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12346",
            client_order_id="client_sl_123",
            kind="SL"
        )

        # Verify bracket linked to entry
        entry_data = self.store.get("entry:12345")
        assert "sl" in entry_data["brackets"]
        sl_info = entry_data["brackets"]["sl"]
        assert sl_info["order_id"] == "12346"
        assert sl_info["client_order_id"] == "client_sl_123"

        # Verify bracket metadata
        order_meta = self.store.get("order:12346")
        assert order_meta["symbol"] == "BTCUSDT"
        assert order_meta["type"] == "STOP_MARKET"
        assert order_meta["reduce_only"] is True
        assert order_meta["close_position"] is True
        assert order_meta["parent_entry_id"] == "12345"

    def test_register_bracket_tp(self):
        """Test take-profit bracket registration"""
        # First register entry
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        # Register TP bracket
        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12347",
            client_order_id="client_tp_123",
            kind="TP"
        )

        # Verify bracket linked to entry
        entry_data = self.store.get("entry:12345")
        assert "tp" in entry_data["brackets"]
        tp_info = entry_data["brackets"]["tp"]
        assert tp_info["order_id"] == "12347"
        assert tp_info["client_order_id"] == "client_tp_123"

        # Verify bracket metadata
        order_meta = self.store.get("order:12347")
        assert order_meta["symbol"] == "BTCUSDT"
        assert order_meta["type"] == "TAKE_PROFIT_MARKET"
        assert order_meta["reduce_only"] is True
        assert order_meta["close_position"] is True
        assert order_meta["parent_entry_id"] == "12345"

    def test_register_multiple_brackets(self):
        """Test registering both SL and TP brackets for same entry"""
        # Register entry
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        # Register SL
        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12346",
            client_order_id="client_sl_123",
            kind="SL"
        )

        # Register TP
        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12347",
            client_order_id="client_tp_123",
            kind="TP"
        )

        # Verify both brackets linked
        entry_data = self.store.get("entry:12345")
        assert len(entry_data["brackets"]) == 2
        assert "sl" in entry_data["brackets"]
        assert "tp" in entry_data["brackets"]

    def test_resolve_terminal_bracket_context_tracks_registered_client_identity(self):
        """Guardian recovery returns the persisted child client identity when it was stored."""
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0,
        )
        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12346",
            client_order_id="algo_sl_123",
            kind="SL",
            corr_id="corr-1",
            rid="rid-1",
        )

        context = self.guardian.resolve_terminal_bracket_context(
            client_order_id="algo_sl_123",
            exchange_order_id="child-exchange-id",
            symbol="BTCUSDT",
        )

        assert context is not None
        assert context["tracked_bracket_order_id"] == "12346"
        assert context["tracked_client_order_id"] == "algo_sl_123"
        assert context["parent_entry_order_id"] == "12345"
        assert context["bracket_role"] == "SL"
        assert context["correlation_source"] == "order_guardian_client_order_id"

    def test_resolve_terminal_bracket_context_misses_when_actual_child_identity_was_not_stored(self):
        """Guardian cannot recover a child client identity that was never persisted."""
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0,
        )
        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12346",
            client_order_id="SL-legacy-123",
            kind="SL",
            corr_id="corr-1",
            rid="rid-1",
        )

        context = self.guardian.resolve_terminal_bracket_context(
            client_order_id="algo_sl_123",
            exchange_order_id="child-exchange-id",
            symbol="BTCUSDT",
        )

        assert context is None

    def test_register_bracket_nonexistent_parent(self):
        """Test registering bracket for non-existent parent entry"""
        # Try to register bracket without parent entry
        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="99999",  # Non-existent
            order_id="12346",
            client_order_id="client_sl_123",
            kind="SL"
        )

        # Bracket should still be registered, but not linked to entry
        entry_data = self.store.get("entry:99999")
        assert entry_data is None  # No entry data created

        # But bracket metadata should exist
        order_meta = self.store.get("order:12346")
        assert order_meta is not None
        assert order_meta["parent_entry_id"] == "99999"

    def test_get_brackets_for_entry(self):
        """Test querying brackets for an entry"""
        # Register entry
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        # Initially no brackets
        brackets = self.guardian.get_brackets_for_entry("12345")
        assert brackets == {}

        # Register SL bracket
        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12346",
            client_order_id="client_sl_123",
            kind="SL"
        )

        # Now should have SL bracket
        brackets = self.guardian.get_brackets_for_entry("12345")
        assert "sl" in brackets
        assert brackets["sl"]["order_id"] == "12346"

    def test_get_brackets_for_nonexistent_entry(self):
        """Test querying brackets for non-existent entry"""
        brackets = self.guardian.get_brackets_for_entry("99999")
        assert brackets == {}

    def test_get_our_open_brackets_placeholder(self):
        """Test get_our_open_brackets (currently placeholder)"""
        # Note: This test can't actually call the async method without an event loop
        # The method exists and is async, which is what's important for the interface
        assert hasattr(self.guardian, 'get_our_open_brackets')
        assert callable(self.guardian.get_our_open_brackets)
        # Check that it's a coroutine function
        import asyncio
        assert asyncio.iscoroutinefunction(self.guardian.get_our_open_brackets)

    def test_link_existing_from_rest_placeholder(self):
        """Test link_existing_from_rest (currently placeholder)"""
        # Should not raise exception
        self.guardian.link_existing_from_rest("BTCUSDT")

        # Method exists and is callable
        assert hasattr(self.guardian, 'link_existing_from_rest')
        assert callable(self.guardian.link_existing_from_rest)
