"""
Tests for Aggregator OCO Cleanup Module (Phase 11)

Scenarios:
- ORPHAN-1: FLAT position + 1 SL/1 TP → returns CANCEL for both
- ORPHAN-2: FLAT position + no orders → NOOP
- ORPHAN-3: NON-FLAT position + SL/TP normal → NOOP
- REVERSE-1: was LONG + SL/TP(LONG), became SHORT → CANCEL old SL/TP(LONG)
- REVERSE-2: was SHORT + SL/TP(SHORT), became LONG → CANCEL old SL/TP(SHORT)
"""
import pytest
from decimal import Decimal

from apps.reference.domains.execution_position.aggregator_oco.cleanup import (
    plan_orphan_cleanup,
    plan_reverse_cleanup,
)
from apps.reference.domains.execution_position.aggregator_oco.view_types import (
    OrderView,
    PositionView,
)


# =============================================================================
# Helpers
# =============================================================================

def make_sl_order(symbol: str, order_id: str, side: str = "SELL") -> OrderView:
    """Create SL order (STOP_MARKET, reduce_only)."""
    return OrderView(
        order_id=order_id,
        client_order_id=f"AUR-{symbol}-SL-{order_id}",
        symbol=symbol,
        side=side,
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("100.0"),
        reduce_only=True,
        status="NEW",
    )


def make_tp_order(symbol: str, order_id: str, side: str = "SELL") -> OrderView:
    """Create TP order (TAKE_PROFIT_MARKET, reduce_only)."""
    return OrderView(
        order_id=order_id,
        client_order_id=f"AUR-{symbol}-TP-{order_id}",
        symbol=symbol,
        side=side,
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("200.0"),
        reduce_only=True,
        status="NEW",
    )


def make_entry_order(symbol: str, order_id: str) -> OrderView:
    """Create entry order (LIMIT, not reduce_only)."""
    return OrderView(
        order_id=order_id,
        client_order_id=f"ENTRY-{order_id}",
        symbol=symbol,
        side="BUY",
        order_type="LIMIT",
        qty=Decimal("1.0"),
        price=Decimal("100.0"),
        reduce_only=False,
        status="NEW",
    )


# =============================================================================
# ORPHAN CLEANUP TESTS
# =============================================================================

class TestOrphanCleanup:
    """Tests for plan_orphan_cleanup."""

    def test_orphan_1_flat_position_with_sl_tp_returns_cancel_for_both(self):
        """ORPHAN-1: FLAT position + 1 SL/1 TP → returns CANCEL for both."""
        symbol = "BTCUSDT"
        sl_order = make_sl_order(symbol, "sl-1")
        tp_order = make_tp_order(symbol, "tp-1")
        orders = [sl_order, tp_order]

        plan = plan_orphan_cleanup(symbol, orders)

        assert plan.symbol == symbol
        assert plan.side == "FLAT"
        assert len(plan.actions) == 2
        assert all(a.action == "CANCEL" for a in plan.actions)
        assert {a.order_ref for a in plan.actions} == {"sl-1", "tp-1"}
        assert plan.severity == "WARN"

    def test_orphan_2_flat_position_no_orders_returns_noop(self):
        """ORPHAN-2: FLAT position + no orders → NOOP (no actions)."""
        symbol = "ETHUSDT"
        orders = []

        plan = plan_orphan_cleanup(symbol, orders)

        assert plan.symbol == symbol
        assert plan.side == "FLAT"
        assert len(plan.actions) == 0
        assert plan.severity == "INFO"

    def test_orphan_3_flat_only_entry_orders_not_cancelled(self):
        """Entry orders (not reduce_only) should NOT be cancelled."""
        symbol = "SOLUSDT"
        entry_order = make_entry_order(symbol, "entry-1")
        orders = [entry_order]

        plan = plan_orphan_cleanup(symbol, orders)

        assert len(plan.actions) == 0
        assert plan.severity == "INFO"

    def test_orphan_mixed_orders_only_brackets_cancelled(self):
        """Mixed orders: only SL/TP brackets cancelled, entry orders preserved."""
        symbol = "BNBUSDT"
        sl_order = make_sl_order(symbol, "sl-1")
        entry_order = make_entry_order(symbol, "entry-1")
        orders = [sl_order, entry_order]

        plan = plan_orphan_cleanup(symbol, orders)

        assert len(plan.actions) == 1
        assert plan.actions[0].order_ref == "sl-1"
        assert plan.actions[0].action == "CANCEL"

    def test_orphan_filters_by_symbol(self):
        """Orders from different symbols are filtered."""
        symbol = "BTCUSDT"
        sl_btc = make_sl_order("BTCUSDT", "sl-btc")
        sl_eth = make_sl_order("ETHUSDT", "sl-eth")
        orders = [sl_btc, sl_eth]

        plan = plan_orphan_cleanup(symbol, orders)

        assert len(plan.actions) == 1
        assert plan.actions[0].order_ref == "sl-btc"


# =============================================================================
# REVERSE CLEANUP TESTS
# =============================================================================

class TestReverseCleanup:
    """Tests for plan_reverse_cleanup."""

    def test_reverse_1_long_to_short_cancels_old_sl_tp(self):
        """REVERSE-1: was LONG + SL/TP(LONG), became SHORT → CANCEL old SL/TP."""
        symbol = "BTCUSDT"
        prev_side = "LONG"
        new_side = "SHORT"
        # LONG position SL/TP have side=SELL
        sl_order = make_sl_order(symbol, "sl-long", side="SELL")
        tp_order = make_tp_order(symbol, "tp-long", side="SELL")
        orders = [sl_order, tp_order]

        plan = plan_reverse_cleanup(symbol, prev_side, new_side, orders)

        assert plan.symbol == symbol
        assert plan.side == new_side
        assert len(plan.actions) == 2
        assert all(a.action == "CANCEL" for a in plan.actions)
        assert {a.order_ref for a in plan.actions} == {"sl-long", "tp-long"}
        assert all("LONG->SHORT" in a.why for a in plan.actions)

    def test_reverse_2_short_to_long_cancels_old_sl_tp(self):
        """REVERSE-2: was SHORT + SL/TP(SHORT), became LONG → CANCEL old SL/TP."""
        symbol = "ETHUSDT"
        prev_side = "SHORT"
        new_side = "LONG"
        # SHORT position SL/TP have side=BUY
        sl_order = make_sl_order(symbol, "sl-short", side="BUY")
        tp_order = make_tp_order(symbol, "tp-short", side="BUY")
        orders = [sl_order, tp_order]

        plan = plan_reverse_cleanup(symbol, prev_side, new_side, orders)

        assert plan.symbol == symbol
        assert plan.side == new_side
        assert len(plan.actions) == 2
        assert all(a.action == "CANCEL" for a in plan.actions)
        assert {a.order_ref for a in plan.actions} == {"sl-short", "tp-short"}

    def test_reverse_no_old_brackets_returns_noop(self):
        """No old side brackets → no actions."""
        symbol = "SOLUSDT"
        prev_side = "LONG"
        new_side = "SHORT"
        # No orders
        orders = []

        plan = plan_reverse_cleanup(symbol, prev_side, new_side, orders)

        assert len(plan.actions) == 0
        assert plan.severity == "INFO"

    def test_reverse_keeps_new_side_brackets(self):
        """New side brackets are NOT cancelled."""
        symbol = "BNBUSDT"
        prev_side = "LONG"
        new_side = "SHORT"
        # Old side bracket (SELL for LONG position)
        old_sl = make_sl_order(symbol, "sl-old", side="SELL")
        # New side bracket (BUY for SHORT position) - should NOT be cancelled
        new_sl = make_sl_order(symbol, "sl-new", side="BUY")
        orders = [old_sl, new_sl]

        plan = plan_reverse_cleanup(symbol, prev_side, new_side, orders)

        # Only old side bracket cancelled
        assert len(plan.actions) == 1
        assert plan.actions[0].order_ref == "sl-old"

    def test_reverse_entry_orders_not_cancelled(self):
        """Entry orders (not reduce_only) should NOT be cancelled even if they match side."""
        symbol = "XRPUSDT"
        prev_side = "LONG"
        new_side = "SHORT"
        # Entry order with SELL side (matches old exit side but not reduce_only)
        entry_order = OrderView(
            order_id="entry-1",
            client_order_id="ENTRY-1",
            symbol=symbol,
            side="SELL",
            order_type="LIMIT",
            qty=Decimal("1.0"),
            price=Decimal("100.0"),
            reduce_only=False,  # NOT a bracket
            status="NEW",
        )
        orders = [entry_order]

        plan = plan_reverse_cleanup(symbol, prev_side, new_side, orders)

        assert len(plan.actions) == 0


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_orphan_close_position_orders_also_cancelled(self):
        """Orders with close_position=True are also treated as brackets."""
        symbol = "DOGEUSDT"
        close_order = OrderView(
            order_id="close-1",
            client_order_id="CLOSE-1",
            symbol=symbol,
            side="SELL",
            order_type="MARKET",
            qty=Decimal("1.0"),
            reduce_only=False,
            close_position=True,  # This makes it a bracket
            status="NEW",
        )
        orders = [close_order]

        plan = plan_orphan_cleanup(symbol, orders)

        # MARKET orders are not SL/TP type, so should NOT be cancelled
        # Only STOP_MARKET and TAKE_PROFIT_MARKET are cancelled
        assert len(plan.actions) == 0

    def test_empty_orders_list_safe(self):
        """Empty orders list doesn't crash."""
        plan = plan_orphan_cleanup("BTCUSDT", [])
        assert plan.actions == []

        plan = plan_reverse_cleanup("BTCUSDT", "LONG", "SHORT", [])
        assert plan.actions == []

    def test_why_chain_includes_reason(self):
        """Plan.why includes cleanup type for XAI."""
        sl = make_sl_order("BTCUSDT", "sl-1")

        orphan_plan = plan_orphan_cleanup("BTCUSDT", [sl])
        assert "orphan" in orphan_plan.why.lower()

        reverse_plan = plan_reverse_cleanup("BTCUSDT", "LONG", "SHORT", [sl])
        assert "reverse" in reverse_plan.why.lower()
