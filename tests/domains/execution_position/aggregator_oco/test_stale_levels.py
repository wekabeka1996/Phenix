"""
Unit tests for Aggregator OCO stale levels functionality.

Tests dynamic recalculation of brackets when position changes (scale-in, averaging).
"""

import pytest
from decimal import Decimal

from apps.reference.domains.execution_position.aggregator_oco.contracts import (
    AggregatorInput,
    BracketAction,
    BracketConfig,
    OrderSnapshot,
    PositionSnapshot,
    cancel_action,
    place_sl_action,
    place_tp_action,
)
from apps.reference.domains.execution_position.aggregator_oco.engine import (
    _compute_bracket_plan_core,
)


class TestStaleLevelsDetection:
    """Test stale levels detection and recalculation."""

    def test_stale_levels_scale_in_long(self):
        """Test that stale SL/TP are detected and replaced on scale-in (LONG)."""
        # Scale-in scenario: position was 1.0@100.0, now 2.0@105.0 after averaging
        # Old brackets were for 100.0: SL=98.0, TP=104.0
        # New desired levels for 105.0: SL=102.9, TP=109.2
        position = PositionSnapshot(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("2.0"),
            entry_price=Decimal("105.0"),  # New averaged entry price
        )

        # Existing brackets with OLD levels (from before averaging)
        orders = [
            OrderSnapshot(
                symbol="BTCUSDT",
                order_id="sl_old",
                client_order_id="AUR-BTCUSDT-LONG-SL-C1-old",
                side="SELL",
                type="STOP_MARKET",
                stop_price=Decimal("98.0"),  # Old SL level (stale)
                status="NEW",
            ),
            OrderSnapshot(
                symbol="BTCUSDT",
                order_id="tp_old",
                client_order_id="AUR-BTCUSDT-LONG-TP-C1-old",
                side="BUY",
                type="TAKE_PROFIT_MARKET",
                stop_price=Decimal("104.0"),  # Old TP level (stale)
                status="NEW",
            ),
        ]

        agg_input = AggregatorInput(
            symbol="BTCUSDT",
            position=position,
            orders=orders,
        )

        cfg = BracketConfig(
            sl_pct=Decimal("0.02"),
            tp_rr=Decimal("2.0"),
        )

        plan = _compute_bracket_plan_core(agg_input, cfg)

        # Should detect stale levels and generate CANCEL + PLACE actions
        assert len(plan.actions) == 4
        assert plan.severity == "WARN"
        assert "stale_levels" in plan.why

        # Check CANCEL actions
        cancel_actions = [a for a in plan.actions if a.action == "CANCEL"]
        assert len(cancel_actions) == 2
        assert any("stale_sl" in a.why for a in cancel_actions)
        assert any("stale_tp" in a.why for a in cancel_actions)

        # Check PLACE actions with NEW levels
        place_actions = [a for a in plan.actions if a.action in ("PLACE_SL", "PLACE_TP")]
        assert len(place_actions) == 2
        assert any(a.action == "PLACE_SL" and abs(a.price - Decimal("102.9")) < Decimal("0.01") for a in place_actions)
        assert any(a.action == "PLACE_TP" and abs(a.price - Decimal("109.2")) < Decimal("0.01") for a in place_actions)

    def test_stale_levels_scale_in_short(self):
        """Test that stale SL/TP are detected and replaced on scale-in (SHORT)."""
        # Scale-in scenario: position was 1.0@100.0, now 2.0@95.0 after averaging
        # Old brackets were for 100.0: SL=102.0, TP=96.0
        # New desired levels for 95.0: SL=96.9, TP=92.0
        position = PositionSnapshot(
            symbol="BTCUSDT",
            side="SHORT",
            qty=Decimal("2.0"),
            entry_price=Decimal("95.0"),  # New averaged entry price
        )

        # Existing brackets with OLD levels (from before averaging)
        orders = [
            OrderSnapshot(
                symbol="BTCUSDT",
                order_id="sl_old",
                client_order_id="AUR-BTCUSDT-SHORT-SL-C1-old",
                side="BUY",
                type="STOP_MARKET",
                stop_price=Decimal("102.0"),  # Old SL level (stale)
                status="NEW",
            ),
            OrderSnapshot(
                symbol="BTCUSDT",
                order_id="tp_old",
                client_order_id="AUR-BTCUSDT-SHORT-TP-C1-old",
                side="SELL",
                type="TAKE_PROFIT_MARKET",
                stop_price=Decimal("96.0"),  # Old TP level (stale)
                status="NEW",
            ),
        ]

        agg_input = AggregatorInput(
            symbol="BTCUSDT",
            position=position,
            orders=orders,
        )

        cfg = BracketConfig(
            sl_pct=Decimal("0.02"),
            tp_rr=Decimal("2.0"),
        )

        plan = _compute_bracket_plan_core(agg_input, cfg)

        # Should detect stale levels and generate CANCEL + PLACE actions
        assert len(plan.actions) == 4
        assert plan.severity == "WARN"
        assert "stale_levels" in plan.why

    def test_fresh_levels_no_recalc(self):
        """Test that fresh bracket levels don't trigger recalculation."""
        # Position: 1.0 @ 100.0, SL=98.0, TP=104.0
        position = PositionSnapshot(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("1.0"),
            entry_price=Decimal("100.0"),
        )

        # Existing brackets with CORRECT levels
        orders = [
            OrderSnapshot(
                symbol="BTCUSDT",
                order_id="sl_fresh",
                client_order_id="AUR-BTCUSDT-LONG-SL-C1-fresh",
                side="SELL",
                type="STOP_MARKET",
                stop_price=Decimal("98.0"),  # Correct SL level
                status="NEW",
            ),
            OrderSnapshot(
                symbol="BTCUSDT",
                order_id="tp_fresh",
                client_order_id="AUR-BTCUSDT-LONG-TP-C1-fresh",
                side="BUY",
                type="TAKE_PROFIT_MARKET",
                stop_price=Decimal("104.0"),  # Correct TP level
                status="NEW",
            ),
        ]

        agg_input = AggregatorInput(
            symbol="BTCUSDT",
            position=position,
            orders=orders,
        )

        cfg = BracketConfig(
            sl_pct=Decimal("0.02"),
            tp_rr=Decimal("2.0"),
        )

        plan = _compute_bracket_plan_core(agg_input, cfg)

        # Should be OK - no actions needed
        assert len(plan.actions) == 0
        assert plan.severity == "INFO"
        assert plan.why == "brackets_ok"

    def test_partial_stale_sl_only(self):
        """Test recalc when only SL is stale."""
        position = PositionSnapshot(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("1.0"),
            entry_price=Decimal("100.0"),
        )

        # SL stale, TP fresh
        orders = [
            OrderSnapshot(
                symbol="BTCUSDT",
                order_id="sl_stale",
                client_order_id="AUR-BTCUSDT-LONG-SL-C1-stale",
                side="SELL",
                type="STOP_MARKET",
                stop_price=Decimal("99.0"),  # Wrong SL level
                status="NEW",
            ),
            OrderSnapshot(
                symbol="BTCUSDT",
                order_id="tp_fresh",
                client_order_id="AUR-BTCUSDT-LONG-TP-C1-fresh",
                side="BUY",
                type="TAKE_PROFIT_MARKET",
                stop_price=Decimal("104.0"),  # Correct TP level
                status="NEW",
            ),
        ]

        agg_input = AggregatorInput(
            symbol="BTCUSDT",
            position=position,
            orders=orders,
        )

        cfg = BracketConfig(
            sl_pct=Decimal("0.02"),
            tp_rr=Decimal("2.0"),
        )

        plan = _compute_bracket_plan_core(agg_input, cfg)

        # Should recalc only SL
        assert len(plan.actions) == 2  # CANCEL SL + PLACE SL
        assert plan.severity == "WARN"
        assert "stale_levels" in plan.why
        assert "sl_99.0→98.0" in plan.why

    def test_partial_stale_tp_only(self):
        """Test recalc when only TP is stale."""
        position = PositionSnapshot(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("1.0"),
            entry_price=Decimal("100.0"),
        )

        # SL fresh, TP stale
        orders = [
            OrderSnapshot(
                symbol="BTCUSDT",
                order_id="sl_fresh",
                client_order_id="AUR-BTCUSDT-LONG-SL-C1-fresh",
                side="SELL",
                type="STOP_MARKET",
                stop_price=Decimal("98.0"),  # Correct SL level
                status="NEW",
            ),
            OrderSnapshot(
                symbol="BTCUSDT",
                order_id="tp_stale",
                client_order_id="AUR-BTCUSDT-LONG-TP-C1-stale",
                side="BUY",
                type="TAKE_PROFIT_MARKET",
                stop_price=Decimal("105.0"),  # Wrong TP level
                status="NEW",
            ),
        ]

        agg_input = AggregatorInput(
            symbol="BTCUSDT",
            position=position,
            orders=orders,
        )

        cfg = BracketConfig(
            sl_pct=Decimal("0.02"),
            tp_rr=Decimal("2.0"),
        )

        plan = _compute_bracket_plan_core(agg_input, cfg)

        # Should recalc only TP
        assert len(plan.actions) == 2  # CANCEL TP + PLACE TP
        assert plan.severity == "WARN"
        assert "stale_levels" in plan.why
        assert "tp_105.0→104.0" in plan.why

    def test_tolerance_allows_small_differences(self):
        """Test that small price differences are tolerated."""
        position = PositionSnapshot(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("1.0"),
            entry_price=Decimal("100.0"),
        )

        # SL with tiny difference (within 0.1% tolerance)
        orders = [
            OrderSnapshot(
                symbol="BTCUSDT",
                order_id="sl_tiny_diff",
                client_order_id="AUR-BTCUSDT-LONG-SL-C1-tiny",
                side="SELL",
                type="STOP_MARKET",
                stop_price=Decimal("98.001"),  # 98.0 desired, tiny diff
                status="NEW",
            ),
            OrderSnapshot(
                symbol="BTCUSDT",
                order_id="tp_fresh",
                client_order_id="AUR-BTCUSDT-LONG-TP-C1-fresh",
                side="BUY",
                type="TAKE_PROFIT_MARKET",
                stop_price=Decimal("104.0"),  # Correct TP level
                status="NEW",
            ),
        ]

        agg_input = AggregatorInput(
            symbol="BTCUSDT",
            position=position,
            orders=orders,
        )

        cfg = BracketConfig(
            sl_pct=Decimal("0.02"),
            tp_rr=Decimal("2.0"),
        )

        plan = _compute_bracket_plan_core(agg_input, cfg)

        # Should be OK - tiny difference tolerated
        assert len(plan.actions) == 0
        assert plan.severity == "INFO"
        assert plan.why == "brackets_ok"
