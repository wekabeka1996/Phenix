"""
PHASE 3: Regime adaptation tests.
Verify that ExposureGuard updates directional ratio based on market regime.
"""

import pytest
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List
from unittest.mock import Mock
from apps.reference.domains.execution_position.exposure_guard import ExposureGuard
from apps.reference.domains.execution_position.soft_clip import SoftLimitConfig, RegimeAdaptationConfig


@pytest.fixture
def guard():
    """Create a minimal ExposureGuard with test config."""
    config = {
        "trading": {
            "execution": {
                "exposure": {
                    "max_equity_utilization_pct": "0.20",
                    "max_portfolio_fraction": "0.20",
                    "max_side_utilization_pct": {"long": "0.12", "short": "0.12"},
                    "max_directional_ratio": "2.0",
                    "per_symbol_cap_pct": "0.08",
                    "reserve_margin_pct": "0.10",
                    "post_fill_hold_ttl_sec": 5,
                }
            }
        }
    }
    return ExposureGuard(config)


class TestRegimeAdaptation:
    """Test regime-based directional ratio adaptation."""

    def test_regime_trend_up(self, guard):
        """TREND_UP should increase directional ratio."""
        # Base ratio is 2.0 from init
        # TREND_UP adds +0.30 → 2.30
        guard.soft_limit_config = SoftLimitConfig(
            mode="clip",
            clip_min_notional_usdt=Decimal("10"),
            directional_ratio_max=Decimal("3.0"),
            side_exposure_usdt=Decimal("600"),
            margin_exposure_usdt=Decimal("1100"),
            regime_adaptation=RegimeAdaptationConfig(
                trend_up_delta=Decimal("0.30"),
                trend_down_delta=Decimal("0.30"),
                flat_delta=Decimal("-0.30"),
                bounds=[Decimal("2.0"), Decimal("4.0")],
            ),
        )

        # Simulate TREND_UP
        guard.on_regime_changed("TREND_UP")
        assert guard.max_directional_ratio == Decimal("3.30")

    def test_regime_trend_down(self, guard):
        """TREND_DOWN should increase directional ratio."""
        guard.soft_limit_config = SoftLimitConfig(
            mode="clip",
            clip_min_notional_usdt=Decimal("10"),
            directional_ratio_max=Decimal("3.0"),
            side_exposure_usdt=Decimal("600"),
            margin_exposure_usdt=Decimal("1100"),
            regime_adaptation=RegimeAdaptationConfig(
                trend_up_delta=Decimal("0.30"),
                trend_down_delta=Decimal("0.30"),
                flat_delta=Decimal("-0.30"),
                bounds=[Decimal("2.0"), Decimal("4.0")],
            ),
        )

        # Simulate TREND_DOWN
        guard.on_regime_changed("TREND_DOWN")
        expected = Decimal("3.0") + Decimal("0.30")  # 3.30
        assert guard.max_directional_ratio == expected

    def test_regime_flat(self, guard):
        """FLAT should decrease directional ratio."""
        guard.soft_limit_config = SoftLimitConfig(
            mode="clip",
            clip_min_notional_usdt=Decimal("10"),
            directional_ratio_max=Decimal("3.0"),
            side_exposure_usdt=Decimal("600"),
            margin_exposure_usdt=Decimal("1100"),
            regime_adaptation=RegimeAdaptationConfig(
                trend_up_delta=Decimal("0.30"),
                trend_down_delta=Decimal("0.30"),
                flat_delta=Decimal("-0.30"),
                bounds=[Decimal("2.0"), Decimal("4.0")],
            ),
        )

        # Simulate FLAT
        guard.on_regime_changed("FLAT")
        expected = Decimal("3.0") - Decimal("0.30")  # 2.70
        assert guard.max_directional_ratio == expected

    def test_regime_bounds_clamping(self, guard):
        """Ratio should be clamped to bounds."""
        # Set very high base ratio
        guard.max_directional_ratio = Decimal("4.0")
        guard.soft_limit_config = SoftLimitConfig(
            mode="clip",
            clip_min_notional_usdt=Decimal("10"),
            directional_ratio_max=Decimal("4.0"),  # At upper bound
            side_exposure_usdt=Decimal("600"),
            margin_exposure_usdt=Decimal("1100"),
            regime_adaptation=RegimeAdaptationConfig(
                trend_up_delta=Decimal("0.30"),
                trend_down_delta=Decimal("0.30"),
                flat_delta=Decimal("-0.30"),
                bounds=[Decimal("2.0"), Decimal("4.0")],
            ),
        )

        # Try TREND_UP → would be 4.30, should clamp to 4.0
        guard.on_regime_changed("TREND_UP")
        assert guard.max_directional_ratio == Decimal("4.0")

    def test_regime_bounds_lower_clamp(self, guard):
        """Ratio should clamp to lower bound."""
        # Set low base ratio
        guard.max_directional_ratio = Decimal("2.0")
        guard.soft_limit_config = SoftLimitConfig(
            mode="clip",
            clip_min_notional_usdt=Decimal("10"),
            directional_ratio_max=Decimal("2.0"),  # At lower bound
            side_exposure_usdt=Decimal("600"),
            margin_exposure_usdt=Decimal("1100"),
            regime_adaptation=RegimeAdaptationConfig(
                trend_up_delta=Decimal("0.30"),
                trend_down_delta=Decimal("0.30"),
                flat_delta=Decimal("-0.30"),
                bounds=[Decimal("2.0"), Decimal("4.0")],
            ),
        )

        # Try FLAT → would be 1.70, should clamp to 2.0
        guard.on_regime_changed("FLAT")
        assert guard.max_directional_ratio == Decimal("2.0")

    def test_regime_no_config(self, guard):
        """Should handle missing config gracefully."""
        original_ratio = guard.max_directional_ratio

        # Call without config - should not crash
        guard.on_regime_changed("TREND_UP")

        # Ratio should remain unchanged
        assert guard.max_directional_ratio == original_ratio

    def test_regime_uncertain(self, guard):
        """UNCERTAIN should use flat_delta (stricter)."""
        guard.soft_limit_config = SoftLimitConfig(
            mode="clip",
            clip_min_notional_usdt=Decimal("10"),
            directional_ratio_max=Decimal("3.0"),
            side_exposure_usdt=Decimal("600"),
            margin_exposure_usdt=Decimal("1100"),
            regime_adaptation=RegimeAdaptationConfig(
                trend_up_delta=Decimal("0.30"),
                trend_down_delta=Decimal("0.30"),
                flat_delta=Decimal("-0.30"),
                bounds=[Decimal("2.0"), Decimal("4.0")],
            ),
        )

        # Simulate UNCERTAIN (not explicitly mapped, but should fall into FLAT case)
        guard.on_regime_changed("UNCERTAIN")
        expected = Decimal("3.0") - Decimal("0.30")  # 2.70
        assert guard.max_directional_ratio == expected
