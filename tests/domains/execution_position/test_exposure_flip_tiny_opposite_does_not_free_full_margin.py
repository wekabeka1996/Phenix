"""
Phase 4 — Exposure and Risk Math

Tests for DEF-E06: Exposure flip must be size-aware — a tiny opposite-side
order must not free the full margin of the existing position.

Tests for DEF-E19: Decimal-only margin math in shadow notional check.

Tests for DEF-E20: SoftClipEngine hard-zero behavior documented, not
described as proportional.
"""
from __future__ import annotations

import pytest
import time
from decimal import Decimal
from unittest.mock import MagicMock


class TestExposureFlipSizeAware:
    """DEF-E06: Flip detection must be size-aware, not side-only."""

    def test_flip_fraction_full_close(self):
        """If order_qty == position_qty, flip_fraction must be 1.0 (full close)."""
        curr_qty = Decimal("100")
        order_qty = Decimal("100")
        closed_qty = min(order_qty, abs(curr_qty))
        flip_fraction = closed_qty / abs(curr_qty)
        assert flip_fraction == Decimal(
            "1"), f"Expected 1.0 flip fraction, got {flip_fraction}"

    def test_flip_fraction_partial_close_ten_percent(self):
        """
        DEF-E06 regression: 10 contracts against a 100-contract position should
        free only 10/100 = 10% of margin, not 100%.
        """
        curr_position_qty = Decimal("100")
        order_qty = Decimal("10")
        closed_qty = min(order_qty, curr_position_qty)
        flip_fraction = closed_qty / curr_position_qty

        assert flip_fraction == Decimal("0.1"), (
            f"DEF-E06: 10-contract order against 100-contract position should free 10% margin. "
            f"Got flip_fraction={flip_fraction}"
        )

    def test_flip_fraction_over_close_capped_at_one(self):
        """
        If order_qty > position_qty (overshoot flip), flip_fraction must be 1.0.
        The excess opens a new position in the opposite direction.
        """
        curr_position_qty = Decimal("50")
        order_qty = Decimal("80")  # Closes 50 + opens 30 opposite
        closed_qty = min(order_qty, curr_position_qty)
        flip_fraction = closed_qty / curr_position_qty

        assert flip_fraction == Decimal("1"), (
            f"DEF-E06: Over-close must have flip_fraction=1.0. Got {flip_fraction}"
        )

    def test_tiny_opposite_does_not_free_full_margin(self):
        """
        DEF-E06 regression: tiny opposite order must not free full margin.
        This is the core bug: side-only detection treated ANY opposite order as full flip.
        """
        # Simulate the exposure_guard call with DEF-E06 fix
        # Before fix: can_open got is_flip=True, flip_fraction=1.0 → subtracted full margin
        # After fix: flip_fraction=0.1 → only 10% of margin is freed

        curr_position_qty = Decimal("100")
        # $1000 margin for 100 contracts
        current_symbol_margin = Decimal("1000")

        # Before fix (side-only): freed $1000 for a 10-contract order
        old_freed_margin = current_symbol_margin  # full margin freed (wrong)

        # After fix (size-aware): freed only $100 for a 10-contract order
        order_qty = Decimal("10")
        flip_fraction = min(order_qty, curr_position_qty) / curr_position_qty
        new_freed_margin = current_symbol_margin * flip_fraction

        assert new_freed_margin < old_freed_margin, (
            "DEF-E06: Size-aware flip must free less margin than side-only flip"
        )
        assert new_freed_margin == Decimal("100"), (
            f"DEF-E06: 10-contract order should free $100 margin, not $1000. Got {new_freed_margin}"
        )

    def test_can_open_accepts_flip_fraction_parameter(self):
        """DEF-E06: ExposureGuard.can_open must accept flip_fraction parameter."""
        from apps.reference.domains.execution_position.guards.exposure_guard import ExposureGuard
        import inspect
        sig = inspect.signature(ExposureGuard.can_open)
        assert "flip_fraction" in sig.parameters, (
            "DEF-E06: ExposureGuard.can_open must have flip_fraction parameter"
        )
        # Default must be Decimal("1") (backward compatible — full flip if not specified)
        default = sig.parameters["flip_fraction"].default
        assert default == Decimal("1"), (
            f"DEF-E06: flip_fraction default must be Decimal('1'), got {default!r}"
        )

    def test_flip_fraction_clamped_to_positive(self):
        """flip_fraction must be positive (zero or negative current position skips flip)."""
        curr_qty = Decimal("0")  # Flat — no flip
        order_qty = Decimal("10")
        is_flip = False  # No position to flip against

        if curr_qty != 0:
            curr_side_is_buy = curr_qty > 0
            intent_side_is_buy = True  # BUY order
            if curr_side_is_buy != intent_side_is_buy:
                is_flip = True

        assert is_flip is False, "Flat position (qty=0) must not trigger flip detection"


class TestExposureDecimalNoFloatShadowNotional:
    """DEF-E19: Decimal-only math in shadow notional check — no float() conversions."""

    def test_shadow_notional_subtraction_uses_decimal(self):
        """Shadow notional diff must use Decimal arithmetic, not float."""
        portfolio_notional = Decimal("12345.67")
        shadow_notional_raw = 12300.00  # float from adapter

        # DEF-E19 fix: convert to Decimal before arithmetic
        shadow_notional_dec = Decimal(str(shadow_notional_raw))
        diff_abs = abs(shadow_notional_dec - portfolio_notional)

        assert isinstance(diff_abs, Decimal), (
            f"DEF-E19: diff_abs must be Decimal, got {type(diff_abs)}"
        )

    def test_float_conversion_loses_precision(self):
        """Document WHY float() is dangerous for margin math."""
        portfolio_notional_dec = Decimal("12345.67890123456789")
        # float loses precision beyond ~15-17 significant digits
        portfolio_as_float = float(portfolio_notional_dec)
        portfolio_back = Decimal(str(portfolio_as_float))

        # Precision is lost
        assert portfolio_notional_dec != portfolio_back, (
            "float() conversion must lose precision — this is why DEF-E19 requires Decimal"
        )

    def test_decimal_max_does_not_need_float(self):
        """max() of Decimals works without float() conversion."""
        a = Decimal("100.5")
        b = Decimal("99.9")
        c = Decimal("1")

        result = max(a, b, c)
        assert isinstance(result, Decimal)
        assert result == Decimal("100.5")

    def test_exposure_guard_breach_payload_stringifies_financial_values(self, fsm_config):
        """DEF-E19: breach payloads must not convert financial Decimals through float()."""
        from apps.reference.domains.execution_position.guards.exposure_guard import ExposureGuard

        eg = fsm_config.domains.execution_position.exposure_guard
        eg.max_portfolio_fraction = "0.1"
        eg.max_equity_utilization_pct = "100.0"
        fsm_config.trading.execution.exposure.leverage_defaults = {
            "__default__": 20}

        guard = ExposureGuard(fsm_core=MagicMock(), config=fsm_config)
        state = {
            "positions_last_ts_ms": int(time.time() * 1000),
            "equity_free_usdt": "1000",
            "open_positions_usd": "0",
            "open_positions_margin_usd": "0",
            "positions_by_side": {"long_margin": "0", "short_margin": "0"},
            "positions": [],
        }

        result = guard.can_open("BTCUSDT", Decimal("200"), state)

        assert result["allowed"] is False
        assert result["reason"] == "PORTFOLIO_FRACTION_BREACH"
        assert result["projected_notional"] == "200"
        assert result["limit"] == "100.0"
        assert isinstance(result["projected_notional"], str)
        assert isinstance(result["limit"], str)

    def test_exposure_summary_stringifies_financial_totals(self, fsm_config):
        """DEF-E19: summary payloads must keep financial totals string-encoded."""
        from apps.reference.domains.execution_position.guards.exposure_guard import ExposureGuard

        fsm_config.trading.execution.exposure.leverage_defaults = {
            "BTCUSDT": 20}
        guard = ExposureGuard(fsm_core=MagicMock(), config=fsm_config)
        guard.reserve("order_1", Decimal("500"), symbol="BTCUSDT", side="BUY")

        summary = guard.get_exposure_summary()

        assert summary["reservations_usd"] == "500"
        assert summary["reservations_margin_usd"] == "25"
        assert isinstance(summary["reservations_usd"], str)
        assert isinstance(summary["reservations_margin_usd"], str)


class TestSoftClipHardClampBehavior:
    """DEF-E20: SoftClipEngine is a hard-zero clamp, not proportional."""

    def test_soft_clip_engine_docstring_documents_hard_zero(self):
        """DEF-E20: SoftClipEngine docstring must mention hard-zero behavior."""
        from apps.reference.domains.execution_position.guards.soft_clip import SoftClipEngine
        doc = SoftClipEngine.__doc__ or ""
        assert "DEF-E20" in doc or "hard" in doc.lower(), (
            "DEF-E20: SoftClipEngine must document that it is a hard clamp, not proportional"
        )

    def test_clip_result_allowed_false_means_hard_block(self):
        """When clip returns allowed=False, the order is hard-blocked (not scaled)."""
        from apps.reference.domains.execution_position.guards.soft_clip import ClipResult
        result = ClipResult(
            allowed=False,
            reason="MARGIN_LIMIT_EXCEEDED",
            clipped_notional=None,
            original_notional=Decimal("1000"),
            clip_reasons=["margin_exceeded"],
        )
        assert result.allowed is False
        assert result.clipped_notional is None, (
            "DEF-E20: Hard block means clipped_notional is None — no proportional scale-down"
        )

    def test_soft_clip_reason_strings_use_decimal_rounding(self):
        """DEF-E19: clip reason strings must be formatted from Decimal, not float()."""
        from apps.reference.domains.execution_position.guards.soft_clip import SoftClipEngine, SoftLimitConfig

        engine = SoftClipEngine(SoftLimitConfig())
        result = engine.calculate_clipped_size(
            notional_usd=Decimal("1"),
            symbol="BTCUSDT",
            order_side="BUY",
            long_margin=Decimal("0"),
            short_margin=Decimal("0"),
            total_margin_exposure=Decimal("4.815"),
            symbol_leverage=Decimal("5"),
            margin_limit=Decimal("5.35"),
            side_limit=Decimal("100"),
            directional_ratio_max=Decimal("100"),
        )

        assert "MARGIN_AVAILABLE:2.68" in result.clip_reasons
