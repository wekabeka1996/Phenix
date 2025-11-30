"""
FTR-06: DecisionContext & Feature Views – Unit Tests
=====================================================

Tests cover:
1. V1 fallback – raw dict with only V1 features, Views handle missing V2 gracefully
2. Full V2 – all features present, Views compute correctly
3. Edge cases – empty dict, garbage values, boundary thresholds
4. Property calculations – is_bullish, is_bearish, combined_pressure, etc.
"""

from __future__ import annotations

import pytest
from decimal import Decimal

from apps.reference.domains.decision_making.decision_context import (
    TrendView,
    FlowView,
    VolatilityView,
    LiquidityView,
    CrowdingView,
    DecisionContext,
    safe_decimal,
    safe_decimal_optional,
    create_decision_context,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def v1_features() -> dict:
    """Minimal V1 feature set – no V2/Futures fields."""
    return {
        "ema_bias": "0.65",  # bullish > 0.55
        "delta_price": "0.002",
        "obi": "0.12",
        "tfi": "-0.05",
        "volatility_state": "0.5",  # normal
        "volume_spike": "0.4",
        "liquidity_kappa": "0.75",
        "depth_imbalance": "0.55",
    }


@pytest.fixture
def v2_full_features(v1_features: dict) -> dict:
    """Full V2 feature set with Futures data."""
    return {
        **v1_features,
        "large_trade_imbalance": "0.7",
        "volume_zscore": "0.8",
        "spread_bps": "25",
        "funding_rate_normalized": "0.8",
        "oi_delta_pct": "-0.05",
        "funding_rate": "0.0008",
    }


@pytest.fixture
def edge_empty_features() -> dict:
    """Empty dict – everything should fall back to defaults."""
    return {}


@pytest.fixture
def garbage_features() -> dict:
    """Non-numeric garbage values."""
    return {
        "ema_bias": "not_a_number",
        "obi": "",
        "tfi": "   ",
        "volatility_state": "garbage",
        "volume_spike": "yes",
        "funding_rate_normalized": "???",
    }


# ---------------------------------------------------------------------------
# safe_decimal helper
# ---------------------------------------------------------------------------

class TestSafeDecimal:
    """Tests for the safe_decimal helper function."""

    def test_valid_string(self):
        assert safe_decimal("1.23", Decimal("0")) == Decimal("1.23")

    def test_valid_int(self):
        assert safe_decimal(42, Decimal("0")) == Decimal("42")

    def test_valid_float(self):
        result = safe_decimal(0.5, Decimal("0"))
        assert abs(result - Decimal("0.5")) < Decimal("0.0001")

    def test_none_value_returns_default(self):
        assert safe_decimal(None, Decimal("99")) == Decimal("99")

    def test_garbage_string_returns_default(self):
        assert safe_decimal("garbage", Decimal("0")) == Decimal("0")

    def test_empty_string_returns_default(self):
        assert safe_decimal("", Decimal("0")) == Decimal("0")

    def test_whitespace_string_returns_default(self):
        assert safe_decimal("   ", Decimal("0")) == Decimal("0")


class TestSafeDecimalOptional:
    """Tests for safe_decimal_optional."""

    def test_valid_string_returns_decimal(self):
        assert safe_decimal_optional("1.5") == Decimal("1.5")

    def test_none_returns_none(self):
        assert safe_decimal_optional(None) is None

    def test_garbage_returns_none(self):
        assert safe_decimal_optional("garbage") is None


# ---------------------------------------------------------------------------
# TrendView
# ---------------------------------------------------------------------------

class TestTrendView:
    """Tests for TrendView dataclass and properties."""

    def test_bullish_when_ema_above_055(self):
        view = TrendView(ema_bias=Decimal("0.65"), delta_price=Decimal("0.005"))
        assert view.is_bullish is True
        assert view.is_bearish is False

    def test_bearish_when_ema_below_045(self):
        view = TrendView(ema_bias=Decimal("0.35"), delta_price=Decimal("-0.005"))
        assert view.is_bullish is False
        assert view.is_bearish is True

    def test_neutral_when_ema_in_range(self):
        view = TrendView(ema_bias=Decimal("0.50"), delta_price=Decimal("-0.005"))
        assert view.is_bullish is False
        assert view.is_bearish is False
        assert view.is_neutral is True

    def test_trend_strength(self):
        view = TrendView(ema_bias=Decimal("0.7"), delta_price=Decimal("0"))
        # |0.7 - 0.5| = 0.2
        assert view.trend_strength == Decimal("0.2")


# ---------------------------------------------------------------------------
# FlowView
# ---------------------------------------------------------------------------

class TestFlowView:
    """Tests for FlowView dataclass and properties."""

    def test_combined_pressure_without_v2(self):
        view = FlowView(
            obi=Decimal("0.2"),
            tfi=Decimal("0.1"),
            large_trade_imbalance=None,
        )
        # Average of [0.2, 0.1] = 0.15
        assert view.combined_pressure == Decimal("0.15")

    def test_combined_pressure_with_v2(self):
        view = FlowView(
            obi=Decimal("0.2"),
            tfi=Decimal("0.1"),
            large_trade_imbalance=Decimal("0.7"),  # normalized: (0.7-0.5)*2 = 0.4
        )
        # Average of [0.2, 0.1, 0.4] = 0.7/3 ≈ 0.2333
        result = view.combined_pressure
        expected = Decimal("0.7") / Decimal("3")
        assert abs(result - expected) < Decimal("0.0001")

    def test_is_buy_pressure(self):
        view = FlowView(obi=Decimal("0.5"), tfi=Decimal("0.3"))
        assert view.is_buy_pressure is True  # (0.5+0.3)/2 = 0.4 > 0.2

    def test_is_sell_pressure(self):
        view = FlowView(obi=Decimal("-0.5"), tfi=Decimal("-0.3"))
        assert view.is_sell_pressure is True  # (−0.5+(−0.3))/2 = −0.4 < −0.2


# ---------------------------------------------------------------------------
# VolatilityView
# ---------------------------------------------------------------------------

class TestVolatilityView:
    """Tests for VolatilityView dataclass and properties."""

    def test_is_high_volatility_when_state_above_07(self):
        view = VolatilityView(
            volatility_state=Decimal("0.8"),
            volume_spike=Decimal("0.5"),
        )
        assert view.is_high_volatility is True

    def test_is_low_volatility_when_state_below_03(self):
        view = VolatilityView(
            volatility_state=Decimal("0.2"),
            volume_spike=Decimal("0.3"),
        )
        assert view.is_low_volatility is True

    def test_normal_volatility(self):
        view = VolatilityView(
            volatility_state=Decimal("0.5"),
            volume_spike=Decimal("0.5"),
        )
        assert view.is_high_volatility is False
        assert view.is_low_volatility is False

    def test_is_volume_spike(self):
        view = VolatilityView(
            volatility_state=Decimal("0.5"),
            volume_spike=Decimal("0.8"),
        )
        assert view.is_volume_spike is True

    def test_combined_intensity_with_v2(self):
        view = VolatilityView(
            volatility_state=Decimal("0.6"),
            volume_spike=Decimal("0.4"),
            volume_zscore=Decimal("0.8"),
        )
        # (0.6 + 0.4 + 0.8) / 3 = 0.6
        assert view.combined_intensity == Decimal("0.6")


# ---------------------------------------------------------------------------
# LiquidityView
# ---------------------------------------------------------------------------

class TestLiquidityView:
    """Tests for LiquidityView dataclass."""

    def test_is_liquid(self):
        view = LiquidityView(
            liquidity_kappa=Decimal("0.8"),
            depth_imbalance=Decimal("0.5"),
        )
        assert view.is_liquid is True

    def test_is_illiquid_low_kappa(self):
        view = LiquidityView(
            liquidity_kappa=Decimal("0.3"),
            depth_imbalance=Decimal("0.5"),
        )
        assert view.is_illiquid is True

    def test_is_illiquid_high_spread(self):
        view = LiquidityView(
            liquidity_kappa=Decimal("0.8"),
            depth_imbalance=Decimal("0.5"),
            spread_bps=Decimal("60"),  # > 50
        )
        assert view.is_illiquid is True

    def test_effective_spread_with_v2(self):
        view = LiquidityView(
            liquidity_kappa=Decimal("0.8"),
            depth_imbalance=Decimal("0.5"),
            spread_bps=Decimal("25"),
        )
        assert view.effective_spread == Decimal("25")

    def test_effective_spread_estimated(self):
        view = LiquidityView(
            liquidity_kappa=Decimal("0.7"),
            depth_imbalance=Decimal("0.5"),
        )
        # (1 - 0.7) * 150 = 45
        assert view.effective_spread == Decimal("45")


# ---------------------------------------------------------------------------
# CrowdingView
# ---------------------------------------------------------------------------

class TestCrowdingView:
    """Tests for CrowdingView dataclass and properties."""

    def test_is_crowded_long_when_funding_high(self):
        view = CrowdingView(
            funding_rate_normalized=Decimal("0.7"),
            oi_delta_pct=Decimal("0.1"),
        )
        assert view.is_crowded_long is True
        assert view.is_crowded_short is False

    def test_is_crowded_short_when_funding_low(self):
        view = CrowdingView(
            funding_rate_normalized=Decimal("-0.6"),
            oi_delta_pct=Decimal("-0.05"),
        )
        assert view.is_crowded_long is False
        assert view.is_crowded_short is True

    def test_not_crowded_neutral(self):
        view = CrowdingView(
            funding_rate_normalized=Decimal("0.2"),
            oi_delta_pct=Decimal("0.01"),
        )
        assert view.is_crowded_long is False
        assert view.is_crowded_short is False

    def test_not_crowded_when_funding_none(self):
        view = CrowdingView(
            funding_rate_normalized=None,
            oi_delta_pct=None,
        )
        assert view.is_crowded_long is False
        assert view.is_crowded_short is False


# ---------------------------------------------------------------------------
# DecisionContext – Integration
# ---------------------------------------------------------------------------

class TestDecisionContextV1Fallback:
    """DecisionContext with V1 features only – V2 fields should be None/defaults."""

    def test_trend_view_parsed(self, v1_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=v1_features)
        assert ctx.trend.ema_bias == Decimal("0.65")
        assert ctx.trend.is_bullish is True

    def test_flow_view_v2_none(self, v1_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=v1_features)
        assert ctx.flow.large_trade_imbalance is None
        assert ctx.flow.obi == Decimal("0.12")

    def test_volatility_view(self, v1_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=v1_features)
        assert ctx.volatility.volume_zscore is None
        assert ctx.volatility.volatility_state == Decimal("0.5")

    def test_liquidity_view_v2_none(self, v1_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=v1_features)
        assert ctx.liquidity.spread_bps is None

    def test_crowding_view_all_none(self, v1_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=v1_features)
        assert ctx.crowding.funding_rate_normalized is None
        assert ctx.crowding.oi_delta_pct is None


class TestDecisionContextV2Full:
    """DecisionContext with full V2 features."""

    def test_trend_view(self, v2_full_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=v2_full_features)
        assert ctx.trend.ema_bias == Decimal("0.65")
        assert ctx.trend.is_bullish is True

    def test_flow_view_with_v2(self, v2_full_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=v2_full_features)
        assert ctx.flow.large_trade_imbalance == Decimal("0.7")

    def test_volatility_view_with_v2(self, v2_full_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=v2_full_features)
        assert ctx.volatility.volume_zscore == Decimal("0.8")

    def test_liquidity_view_with_v2(self, v2_full_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=v2_full_features)
        assert ctx.liquidity.spread_bps == Decimal("25")

    def test_crowding_view_with_futures(self, v2_full_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=v2_full_features)
        assert ctx.crowding.funding_rate_normalized == Decimal("0.8")
        assert ctx.crowding.oi_delta_pct == Decimal("-0.05")
        assert ctx.crowding.is_crowded_long is True


class TestDecisionContextEdgeCases:
    """Edge cases – empty dict, garbage values."""

    def test_empty_dict_all_defaults(self, edge_empty_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=edge_empty_features)
        # Trend defaults (ema_bias defaults to 0.5)
        assert ctx.trend.ema_bias == Decimal("0.5")
        assert ctx.trend.is_neutral is True
        # Flow defaults
        assert ctx.flow.obi == Decimal("0")
        assert ctx.flow.tfi == Decimal("0")
        # Crowding defaults
        assert ctx.crowding.is_crowded_long is False

    def test_garbage_values_fallback(self, garbage_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=garbage_features)
        # ema_bias: "not_a_number" → default 0.5
        assert ctx.trend.ema_bias == Decimal("0.5")
        # obi: "" → default 0
        assert ctx.flow.obi == Decimal("0")


class TestDecisionContextCaching:
    """Views are cached."""

    def test_views_are_cached(self, v1_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=v1_features)
        trend1 = ctx.trend
        trend2 = ctx.trend
        assert trend1 is trend2

    def test_all_views_independent(self, v1_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=v1_features)
        # Access all views – no cross-contamination
        _ = ctx.trend
        _ = ctx.flow
        _ = ctx.volatility
        _ = ctx.liquidity
        _ = ctx.crowding
        assert ctx.trend.ema_bias == Decimal("0.65")
        assert ctx.flow.obi == Decimal("0.12")


class TestDecisionContextConvenienceMethods:
    """Tests for convenience methods."""

    def test_is_favorable_for_long(self, v1_features: dict):
        # ema_bias 0.65 (bullish), obi+tfi positive → buy pressure
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=v1_features)
        # Need to check if combined_pressure > 0.2
        # (0.12 + (-0.05)) / 2 = 0.035 → not buy pressure
        assert ctx.is_favorable_for_long() is False

    def test_is_favorable_for_short(self):
        features = {
            "ema_bias": "0.35",  # bearish
            "obi": "-0.5",
            "tfi": "-0.3",
        }
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=features)
        # (−0.5 + (−0.3)) / 2 = −0.4 → sell pressure
        assert ctx.is_favorable_for_short() is True

    def test_should_reduce_risk_high_volatility(self):
        features = {"volatility_state": "0.9"}  # > 0.7
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=features)
        assert ctx.should_reduce_risk() is True

    def test_should_reduce_risk_illiquid(self):
        features = {"liquidity_kappa": "0.3"}  # < 0.5
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=features)
        assert ctx.should_reduce_risk() is True


class TestDecisionContextToDict:
    """Tests for to_dict method."""

    def test_to_dict_returns_dict(self, v1_features: dict):
        ctx = DecisionContext(symbol="BTCUSDT", ts=1234567890000, features=v1_features)
        result = ctx.to_dict()
        assert isinstance(result, dict)
        assert result["symbol"] == "BTCUSDT"
        assert result["ts"] == 1234567890000
        assert "trend" in result
        assert "flow" in result
        assert "volatility" in result
        assert "liquidity" in result
        assert "crowding" in result


class TestCreateDecisionContext:
    """Tests for factory function."""

    def test_factory_creates_context(self, v1_features: dict):
        ctx = create_decision_context("ETHUSDT", 9999, v1_features)
        assert ctx.symbol == "ETHUSDT"
        assert ctx.ts == 9999
        assert ctx.trend.ema_bias == Decimal("0.65")

    def test_factory_handles_none_features(self):
        ctx = create_decision_context("BTCUSDT", 1234, None)
        assert ctx.features == {}
        assert ctx.trend.ema_bias == Decimal("0.5")  # default
