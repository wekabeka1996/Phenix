"""
Aggregator OCO — Core Math Golden-Master Tests (Phase 6)

RID: EXEC-AGGREGATOR-OCO-PHASE6-CORE-MATH-EXTRACTION

These tests verify that `core_math.compute_desired_levels()` produces
IDENTICAL results to the legacy implementation in bracket_service.

Golden-master approach:
1. Call new core_math function
2. Call legacy fallback formula (same as bracket_service without aggregator)
3. Assert results are equal

This ensures that Phase 7 (switching runtime to use core_math) will be
zero-diff in behavior.
"""

import pytest
from decimal import Decimal
from typing import Dict

from apps.reference.domains.execution_position.aggregator_oco.core_math import (
    DesiredLevels,
    PriceConstraints,
    compute_desired_levels,
    compute_desired_levels_from_position,
    verify_level_invariants,
)


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY FORMULA REFERENCE (copied from bracket_service fallback)
# ═══════════════════════════════════════════════════════════════════════════════

def legacy_compute_desired_levels(
    side: str,
    entry_price: Decimal,
    sl_pct: Decimal,
    tp_rr: Decimal,
) -> Dict[str, Decimal]:
    """
    Exact copy of bracket_service._compute_desired_levels fallback formula.

    This is the golden master — the behavior we must match.
    Source: shadow_execpos/bracket_service.py lines 917-928
    """
    if side == "LONG":
        sl_price = entry_price * (Decimal("1") - sl_pct)
        tp_price = entry_price * (Decimal("1") + sl_pct * tp_rr)
    else:  # SHORT
        sl_price = entry_price * (Decimal("1") + sl_pct)
        tp_price = entry_price * (Decimal("1") - sl_pct * tp_rr)

    return {
        "sl_price": sl_price,
        "tp_price": tp_price,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# BASIC GOLDEN-MASTER TESTS (A1, A2 from Behavior Spec)
# ═══════════════════════════════════════════════════════════════════════════════

class TestGoldenMasterBasic:
    """Verify core_math matches legacy for basic scenarios."""

    def test_long_basic_matches_legacy(self):
        """A1: LONG, entry=100, sl_pct=0.02, tp_rr=2.0"""
        entry = Decimal("100")
        sl_pct = Decimal("0.02")
        tp_rr = Decimal("2.0")

        # New implementation
        levels = compute_desired_levels(
            side="LONG",
            entry_price=entry,
            sl_pct=sl_pct,
            tp_rr=tp_rr,
        )

        # Legacy reference
        legacy = legacy_compute_desired_levels(
            side="LONG",
            entry_price=entry,
            sl_pct=sl_pct,
            tp_rr=tp_rr,
        )

        # Golden-master assertion
        assert levels.sl_price == legacy["sl_price"], \
            f"SL mismatch: {levels.sl_price} != {legacy['sl_price']}"
        assert levels.tp_price == legacy["tp_price"], \
            f"TP mismatch: {levels.tp_price} != {legacy['tp_price']}"

        # Expected values (from BEHAVIOR.md)
        assert levels.sl_price == Decimal("98")
        assert levels.tp_price == Decimal("104")

    def test_short_basic_matches_legacy(self):
        """A2: SHORT, entry=100, sl_pct=0.02, tp_rr=2.0"""
        entry = Decimal("100")
        sl_pct = Decimal("0.02")
        tp_rr = Decimal("2.0")

        # New implementation
        levels = compute_desired_levels(
            side="SHORT",
            entry_price=entry,
            sl_pct=sl_pct,
            tp_rr=tp_rr,
        )

        # Legacy reference
        legacy = legacy_compute_desired_levels(
            side="SHORT",
            entry_price=entry,
            sl_pct=sl_pct,
            tp_rr=tp_rr,
        )

        # Golden-master assertion
        assert levels.sl_price == legacy["sl_price"]
        assert levels.tp_price == legacy["tp_price"]

        # Expected values
        assert levels.sl_price == Decimal("102")
        assert levels.tp_price == Decimal("96")

    def test_btc_like_price_matches_legacy(self):
        """High price scenario like BTC."""
        entry = Decimal("50000")
        sl_pct = Decimal("0.015")
        tp_rr = Decimal("3.0")

        levels = compute_desired_levels(
            side="LONG",
            entry_price=entry,
            sl_pct=sl_pct,
            tp_rr=tp_rr,
        )

        legacy = legacy_compute_desired_levels(
            side="LONG",
            entry_price=entry,
            sl_pct=sl_pct,
            tp_rr=tp_rr,
        )

        assert levels.sl_price == legacy["sl_price"]
        assert levels.tp_price == legacy["tp_price"]


# ═══════════════════════════════════════════════════════════════════════════════
# PARAMETRIZED GRID TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("entry_price", [
    Decimal("10"),
    Decimal("100"),
    Decimal("123.45"),
    Decimal("1000"),
    Decimal("50000"),
])
@pytest.mark.parametrize("sl_pct", [
    Decimal("0.005"),
    Decimal("0.01"),
    Decimal("0.02"),
    Decimal("0.05"),
])
@pytest.mark.parametrize("tp_rr", [
    Decimal("1.0"),
    Decimal("1.5"),
    Decimal("2.0"),
    Decimal("3.0"),
])
def test_long_grid_matches_legacy(entry_price, sl_pct, tp_rr):
    """
    Grid test: verify LONG formula matches legacy across parameter space.

    Total combinations: 5 × 4 × 4 = 80 test cases
    """
    levels = compute_desired_levels(
        side="LONG",
        entry_price=entry_price,
        sl_pct=sl_pct,
        tp_rr=tp_rr,
    )

    legacy = legacy_compute_desired_levels(
        side="LONG",
        entry_price=entry_price,
        sl_pct=sl_pct,
        tp_rr=tp_rr,
    )

    assert levels.sl_price == legacy["sl_price"], \
        f"LONG SL mismatch at entry={entry_price}, sl_pct={sl_pct}, tp_rr={tp_rr}"
    assert levels.tp_price == legacy["tp_price"], \
        f"LONG TP mismatch at entry={entry_price}, sl_pct={sl_pct}, tp_rr={tp_rr}"


@pytest.mark.parametrize("entry_price", [
    Decimal("10"),
    Decimal("100"),
    Decimal("123.45"),
    Decimal("1000"),
    Decimal("50000"),
])
@pytest.mark.parametrize("sl_pct", [
    Decimal("0.005"),
    Decimal("0.01"),
    Decimal("0.02"),
    Decimal("0.05"),
])
@pytest.mark.parametrize("tp_rr", [
    Decimal("1.0"),
    Decimal("1.5"),
    Decimal("2.0"),
    Decimal("3.0"),
])
def test_short_grid_matches_legacy(entry_price, sl_pct, tp_rr):
    """
    Grid test: verify SHORT formula matches legacy across parameter space.

    Total combinations: 5 × 4 × 4 = 80 test cases
    """
    levels = compute_desired_levels(
        side="SHORT",
        entry_price=entry_price,
        sl_pct=sl_pct,
        tp_rr=tp_rr,
    )

    legacy = legacy_compute_desired_levels(
        side="SHORT",
        entry_price=entry_price,
        sl_pct=sl_pct,
        tp_rr=tp_rr,
    )

    assert levels.sl_price == legacy["sl_price"], \
        f"SHORT SL mismatch at entry={entry_price}, sl_pct={sl_pct}, tp_rr={tp_rr}"
    assert levels.tp_price == legacy["tp_price"], \
        f"SHORT TP mismatch at entry={entry_price}, sl_pct={sl_pct}, tp_rr={tp_rr}"


# ═══════════════════════════════════════════════════════════════════════════════
# INVARIANT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvariants:
    """Verify core invariants hold for all computed levels."""

    @pytest.mark.parametrize("entry_price,sl_pct,tp_rr", [
        (Decimal("100"), Decimal("0.02"), Decimal("2.0")),
        (Decimal("50000"), Decimal("0.01"), Decimal("1.5")),
        (Decimal("1.5"), Decimal("0.05"), Decimal("3.0")),
    ])
    def test_INV4_long_sl_below_entry_tp_above(self, entry_price, sl_pct, tp_rr):
        """INV-4: For LONG, SL < entry < TP must hold."""
        levels = compute_desired_levels(
            side="LONG",
            entry_price=entry_price,
            sl_pct=sl_pct,
            tp_rr=tp_rr,
        )

        assert verify_level_invariants(levels), \
            f"INV-4 violated: SL={levels.sl_price}, entry={entry_price}, TP={levels.tp_price}"
        assert levels.sl_price < levels.entry_price < levels.tp_price

    @pytest.mark.parametrize("entry_price,sl_pct,tp_rr", [
        (Decimal("100"), Decimal("0.02"), Decimal("2.0")),
        (Decimal("50000"), Decimal("0.01"), Decimal("1.5")),
        (Decimal("1.5"), Decimal("0.05"), Decimal("3.0")),
    ])
    def test_INV5_short_tp_below_entry_sl_above(self, entry_price, sl_pct, tp_rr):
        """INV-5: For SHORT, TP < entry < SL must hold."""
        levels = compute_desired_levels(
            side="SHORT",
            entry_price=entry_price,
            sl_pct=sl_pct,
            tp_rr=tp_rr,
        )

        assert verify_level_invariants(levels), \
            f"INV-5 violated: TP={levels.tp_price}, entry={entry_price}, SL={levels.sl_price}"
        assert levels.tp_price < levels.entry_price < levels.sl_price

    def test_INV6_why_field_length(self):
        """INV-6: why field must be ≤ 80 characters."""
        levels = compute_desired_levels(
            side="LONG",
            entry_price=Decimal("100"),
            sl_pct=Decimal("0.02"),
            tp_rr=Decimal("2.0"),
        )

        assert len(levels.why) <= 80, f"why too long ({len(levels.why)} chars)"


# ═══════════════════════════════════════════════════════════════════════════════
# INPUT VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestInputValidation:
    """Verify proper error handling for invalid inputs."""

    def test_invalid_side_raises(self):
        """Invalid side should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid side"):
            compute_desired_levels(
                side="INVALID",  # type: ignore
                entry_price=Decimal("100"),
                sl_pct=Decimal("0.02"),
                tp_rr=Decimal("2.0"),
            )

    def test_zero_entry_price_raises(self):
        """entry_price <= 0 should raise ValueError."""
        with pytest.raises(ValueError, match="entry_price must be > 0"):
            compute_desired_levels(
                side="LONG",
                entry_price=Decimal("0"),
                sl_pct=Decimal("0.02"),
                tp_rr=Decimal("2.0"),
            )

    def test_negative_entry_price_raises(self):
        """Negative entry_price should raise ValueError."""
        with pytest.raises(ValueError, match="entry_price must be > 0"):
            compute_desired_levels(
                side="LONG",
                entry_price=Decimal("-100"),
                sl_pct=Decimal("0.02"),
                tp_rr=Decimal("2.0"),
            )

    def test_zero_sl_pct_raises(self):
        """sl_pct <= 0 should raise ValueError."""
        with pytest.raises(ValueError, match="sl_pct must be > 0"):
            compute_desired_levels(
                side="LONG",
                entry_price=Decimal("100"),
                sl_pct=Decimal("0"),
                tp_rr=Decimal("2.0"),
            )

    def test_zero_tp_rr_raises(self):
        """tp_rr <= 0 should raise ValueError."""
        with pytest.raises(ValueError, match="tp_rr must be > 0"):
            compute_desired_levels(
                side="LONG",
                entry_price=Decimal("100"),
                sl_pct=Decimal("0.02"),
                tp_rr=Decimal("0"),
            )


# ═══════════════════════════════════════════════════════════════════════════════
# ROUNDING TESTS (with constraints)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRounding:
    """Verify price rounding behavior matches expectations."""

    def test_tick_size_rounding(self):
        """Prices should round down to tick_size."""
        constraints = PriceConstraints(
            tick_size=Decimal("0.01"),
            min_price=Decimal("0.01"),
        )

        # Entry that produces non-round SL/TP
        levels = compute_desired_levels(
            side="LONG",
            entry_price=Decimal("100.55"),
            sl_pct=Decimal("0.02"),
            tp_rr=Decimal("2.0"),
            constraints=constraints,
        )

        # SL = 100.55 * 0.98 = 98.539 → rounds to 98.53
        # TP = 100.55 * 1.04 = 104.572 → rounds to 104.57
        assert levels.sl_price == Decimal("98.53")
        assert levels.tp_price == Decimal("104.57")

    def test_no_constraints_no_rounding(self):
        """Without constraints, raw values are returned."""
        levels = compute_desired_levels(
            side="LONG",
            entry_price=Decimal("100.55"),
            sl_pct=Decimal("0.02"),
            tp_rr=Decimal("2.0"),
            constraints=None,
        )

        # Raw values without rounding
        expected_sl = Decimal("100.55") * Decimal("0.98")
        expected_tp = Decimal("100.55") * Decimal("1.04")

        assert levels.sl_price == expected_sl
        assert levels.tp_price == expected_tp


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestConvenienceFunctions:
    """Test helper functions."""

    def test_compute_from_position_matches_direct(self):
        """compute_desired_levels_from_position should match direct call."""
        levels_direct = compute_desired_levels(
            side="LONG",
            entry_price=Decimal("100"),
            sl_pct=Decimal("0.02"),
            tp_rr=Decimal("2.0"),
        )

        levels_helper = compute_desired_levels_from_position(
            position_side="LONG",
            position_entry_price=Decimal("100"),
            sl_pct=Decimal("0.02"),
            tp_rr=Decimal("2.0"),
        )

        assert levels_direct.sl_price == levels_helper.sl_price
        assert levels_direct.tp_price == levels_helper.tp_price


# ═══════════════════════════════════════════════════════════════════════════════
# DATA PRESERVATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataPreservation:
    """Verify DesiredLevels captures all input data for tracing."""

    def test_levels_contain_inputs(self):
        """DesiredLevels should preserve input parameters."""
        levels = compute_desired_levels(
            side="LONG",
            entry_price=Decimal("100"),
            sl_pct=Decimal("0.02"),
            tp_rr=Decimal("2.0"),
        )

        assert levels.side == "LONG"
        assert levels.entry_price == Decimal("100")
        assert levels.sl_pct == Decimal("0.02")
        assert levels.tp_rr == Decimal("2.0")

    def test_levels_are_frozen(self):
        """DesiredLevels should be immutable (frozen dataclass)."""
        levels = compute_desired_levels(
            side="LONG",
            entry_price=Decimal("100"),
            sl_pct=Decimal("0.02"),
            tp_rr=Decimal("2.0"),
        )

        with pytest.raises(AttributeError):
            levels.sl_price = Decimal("0")  # type: ignore
