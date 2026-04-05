"""
Tests for Binance algo order clientAlgoId bracket correlation fix.

Package: BRACKET_ALGO_CLIENT_ID_CORRELATION

Proves:
1. clientAlgoId from bracket placement response is registered as primary
   clientOrderId in OrderIndex (matching WS fill identity)
2. ManageFlowFSM._resolve_bracket_match() matches fills by algo_client_id
3. Legacy "SL-xxx"/"TP-xxx" IDs are registered as secondary fallback
4. set_bracket_ids() propagates algo client IDs to ManageFlowFSM
5. _clear_lifecycle_tracking() resets algo client IDs
6. Exchange fragmentation (N partial fills) remains safe after fix
"""

import pytest
from decimal import Decimal
from typing import Optional, Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch

from apps.reference.domains.execution_position.order_index import (
    OrderIndex,
    OrderRef,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manage_flow():
    """Create a ManageFlowFSM with minimal config for testing."""
    from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM

    # Build a minimal AuroraConfig mock that satisfies ManageFlowFSM __init__
    config = MagicMock()
    config.trading.execution.manage = MagicMock()
    config.trading.execution.manage.brackets = MagicMock()
    config.trading.execution.manage.brackets.oco_emulation = True
    config.trading.execution.manage.emergency = MagicMock()
    config.trading.execution.manage.emergency.wait_mode_bars = 2
    config.strategies.aurora = MagicMock()
    config.strategies.aurora.decision.bar_gating.bar_ms = 900000

    flow = ManageFlowFSM(config=config)
    return flow


# ---------------------------------------------------------------------------
# 1. OrderIndex registration uses clientAlgoId as primary
# ---------------------------------------------------------------------------

class TestOrderIndexAlgoClientIdRegistration:
    """Bracket child registration uses clientAlgoId for WS fill correlation."""

    @pytest.fixture
    def idx(self):
        return OrderIndex(ttl_sec=600)

    def test_primary_registration_uses_algo_client_id(self, idx):
        """When clientAlgoId is available, it should be the primary clientOrderId."""
        # Simulate what bracket_manager does with algo response:
        # sl_algo_client_id = sl_resp.get("clientAlgoId") -> "SL-abc123"
        # sl_id (system-generated) = "SL-7f3a2b1c90de"
        # The primary registration should use clientAlgoId
        ref = idx.register_bracket_child(
            rid="parent-rid",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",  # This is the clientAlgoId
            # This is the algoId (normalized to orderId)
            exchangeOrderId="500001",
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        # Must be findable by clientAlgoId (what WS fills send as clientOrderId)
        assert idx.get(clientOrderId="SL-abc123") is ref
        assert ref.order_kind == "SL"

    def test_secondary_registration_keeps_system_id(self, idx):
        """Both clientAlgoId and system sl_id should resolve to an OrderRef."""
        # Primary: clientAlgoId
        ref1 = idx.register_bracket_child(
            rid="parent-rid",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",
            exchangeOrderId="500001",
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        # Secondary: system-generated sl_id
        ref2 = idx.register_bracket_child(
            rid="parent-rid",
            idempotent_key="idem-1",
            clientOrderId="SL-7f3a2b1c90de",
            exchangeOrderId="500001",
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        # Both should be findable
        assert idx.get(clientOrderId="SL-abc123") is ref1
        assert idx.get(clientOrderId="SL-7f3a2b1c90de") is ref2
        # Both share the same exchangeOrderId
        assert ref1.exchangeOrderId == ref2.exchangeOrderId == "500001"

    def test_ws_fill_lookup_by_algo_client_id(self, idx):
        """Simulates WS fill arriving with clientOrderId=clientAlgoId."""
        idx.register_bracket_child(
            rid="parent-rid",
            idempotent_key="idem-1",
            clientOrderId="TP-xyz789",  # clientAlgoId
            exchangeOrderId="600001",
            symbol="ETHUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            order_kind="TP",
        )
        # WS fill arrives: clientOrderId = clientAlgoId, exchangeOrderId = NEW child ID
        ref = idx.get(clientOrderId="TP-xyz789")
        assert ref is not None
        assert ref.order_kind == "TP"
        assert ref.symbol == "ETHUSDT"

    def test_ws_fill_lookup_miss_when_only_system_id_registered(self, idx):
        """Without clientAlgoId fix, only system sl_id is registered — WS fill misses."""
        # Register with system sl_id (the OLD bug)
        idx.register_bracket_child(
            rid="parent-rid",
            idempotent_key="idem-1",
            clientOrderId="SL-7f3a2b1c90de",  # system-generated
            exchangeOrderId="500001",           # algoId
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        # WS fill arrives with clientAlgoId (different from system sl_id)
        ref = idx.get(clientOrderId="SL-abc123")
        assert ref is None  # MISS — this is the bug the fix addresses


# ---------------------------------------------------------------------------
# 2. ManageFlowFSM._resolve_bracket_match() uses algo_client_id
# ---------------------------------------------------------------------------

class TestManageFlowAlgoClientIdMatch:
    """ManageFlowFSM matches bracket fills by algo_client_id."""

    def test_sl_matched_by_algo_client_id(self):
        """SL fill matched when client_order_id equals sl_algo_client_id."""
        flow = _make_manage_flow()
        flow.sl_order_id = "500001"       # algoId/orderId
        # Binance clientAlgoId is typically the system-generated newClientOrderId
        # passed at placement time; however it may differ from what gets stored
        # as sl_order_id.  Here we use a non-"SL-" prefix to prove algo_client_id
        # matching works independently of prefix matching.
        flow.sl_algo_client_id = "algo_sl_99001"
        flow.tp_order_id = "600001"
        flow.tp_algo_client_id = "algo_tp_99002"

        role, matched, reason = flow._resolve_bracket_match(
            order_id="777001",               # NEW child exchangeOrderId
            client_order_id="algo_sl_99001",  # = clientAlgoId (non SL- prefix)
        )
        assert matched is True
        assert role == "SL"
        assert "algo_client_id" in reason

    def test_tp_matched_by_algo_client_id(self):
        """TP fill matched when client_order_id equals tp_algo_client_id."""
        flow = _make_manage_flow()
        flow.sl_order_id = "500001"
        flow.sl_algo_client_id = "algo_sl_99001"
        flow.tp_order_id = "600001"
        flow.tp_algo_client_id = "algo_tp_99002"

        role, matched, reason = flow._resolve_bracket_match(
            order_id="888001",
            client_order_id="algo_tp_99002",
        )
        assert matched is True
        assert role == "TP"
        assert "algo_client_id" in reason

    def test_no_match_without_algo_client_id(self):
        """Without algo_client_id set, child fills with non-prefix IDs don't match."""
        flow = _make_manage_flow()
        flow.sl_order_id = "500001"
        flow.tp_order_id = "600001"
        # algo_client_id not set (None)

        role, matched, reason = flow._resolve_bracket_match(
            order_id="777001",
            client_order_id="algo_sl_99001",  # non-prefix, untracked
        )
        assert matched is False
        assert role == "UNKNOWN"

    def test_sl_prefix_match_still_works_for_sl_format_ids(self):
        """clientAlgoId in "SL-xxx" format is caught by prefix match (defense in depth)."""
        flow = _make_manage_flow()
        flow.sl_order_id = "500001"
        flow.sl_algo_client_id = "SL-abc123"  # Same as newClientOrderId

        # Even without algo_client_id, prefix match catches "SL-" format
        role, matched, reason = flow._resolve_bracket_match(
            order_id="777001",
            client_order_id="SL-abc123",
        )
        assert matched is True
        assert role == "SL"
        # Prefix match fires first (defense in depth)
        assert "client_order_id_prefix" in reason

    def test_legacy_exact_match_still_works(self):
        """Legacy exact exchange_order_id match still works alongside algo path."""
        flow = _make_manage_flow()
        flow.sl_order_id = "500001"
        flow.sl_algo_client_id = "algo_sl_99001"

        # Legacy: order_id exactly matches tracked sl_order_id
        role, matched, reason = flow._resolve_bracket_match(
            order_id="500001",
            client_order_id="irrelevant",
        )
        assert matched is True
        assert role == "SL"
        assert "exchange_order_id_exact" in reason


# ---------------------------------------------------------------------------
# 3. set_bracket_ids() propagates algo client IDs
# ---------------------------------------------------------------------------

class TestSetBracketIdsAlgoClientId:
    """set_bracket_ids() stores algo client IDs for bracket matching."""

    def test_algo_client_ids_stored(self):
        flow = _make_manage_flow()
        flow.set_bracket_ids(
            sl_order_id="500001",
            tp_order_id="600001",
            sl_algo_client_id="SL-abc123",
            tp_algo_client_id="TP-xyz789",
        )
        assert flow.sl_order_id == "500001"
        assert flow.tp_order_id == "600001"
        assert flow.sl_algo_client_id == "SL-abc123"
        assert flow.tp_algo_client_id == "TP-xyz789"

    def test_backward_compatible_without_algo_ids(self):
        """set_bracket_ids() works without algo_client_id (backward compat)."""
        flow = _make_manage_flow()
        flow.set_bracket_ids(
            sl_order_id="500001",
            tp_order_id="600001",
        )
        assert flow.sl_order_id == "500001"
        assert flow.tp_order_id == "600001"
        assert flow.sl_algo_client_id is None
        assert flow.tp_algo_client_id is None


# ---------------------------------------------------------------------------
# 4. _clear_lifecycle_tracking() resets algo client IDs
# ---------------------------------------------------------------------------

class TestClearLifecycleAlgoClientId:
    """Lifecycle clearing resets algo client IDs to prevent stale matching."""

    def test_algo_ids_cleared(self):
        flow = _make_manage_flow()
        flow.sl_algo_client_id = "SL-abc123"
        flow.tp_algo_client_id = "TP-xyz789"
        flow._clear_lifecycle_tracking(reason="test", clear_symbol=True)
        assert flow.sl_algo_client_id is None
        assert flow.tp_algo_client_id is None


# ---------------------------------------------------------------------------
# 5. Exchange fragmentation safety
# ---------------------------------------------------------------------------

class TestExchangeFragmentationSafety:
    """Multiple partial fills for the same bracket order remain safe."""

    def test_second_fill_does_not_match_after_flat(self):
        """After SL fill transitions to FLAT, second partial fill doesn't re-match."""
        flow = _make_manage_flow()
        flow.sl_order_id = "500001"
        flow.sl_algo_client_id = "algo_sl_99001"
        flow.tp_order_id = "600001"
        flow.tp_algo_client_id = "algo_tp_99002"

        # First fill matches
        role, matched, reason = flow._resolve_bracket_match(
            order_id="777001",
            client_order_id="algo_sl_99001",
        )
        assert matched is True
        assert role == "SL"

        # Simulate lifecycle clear (happens in _handle_bracket_fill -> _clear_lifecycle_tracking)
        flow._clear_lifecycle_tracking(reason="sl_filled", clear_symbol=True)

        # Second fill: all IDs cleared, should not match
        role2, matched2, reason2 = flow._resolve_bracket_match(
            order_id="777001",
            client_order_id="algo_sl_99001",
        )
        assert matched2 is False
        assert role2 == "UNKNOWN"

    def test_orderindex_multiple_fills_same_client_id(self):
        """Multiple fills with same clientOrderId all resolve to same OrderRef."""
        idx = OrderIndex(ttl_sec=600)
        ref = idx.register_bracket_child(
            rid="parent-rid",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",
            exchangeOrderId="500001",
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        # All 3 partial fills use same clientOrderId
        for _ in range(3):
            found = idx.get(clientOrderId="SL-abc123")
            assert found is ref
            assert found.order_kind == "SL"
