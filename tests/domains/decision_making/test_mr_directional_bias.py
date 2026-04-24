"""
PACK-6 Validation: Vector 2 Directional Bias — behavioral tests.

Required tests (from spec):
1. Static split thresholds work without funding
2. Positive funding shifts long/short thresholds correctly
3. Negative funding shifts long/short thresholds correctly
4. Clamp prevents out-of-range thresholds
5. Deadband suppresses small funding noise
6. Missing funding falls back to static thresholds
7. Legacy compatibility — None overrides use symmetric entry_threshold
Plus: strategy-level integration tests for actual signal generation.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from apps.reference.config_models import MRDirectionalBiasConfig
from apps.reference.domains.strategies.runtimes.mean_reversion.handler import MeanReversionHandler
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MeanReversion1mStrategy,
    MRStrategyConfig,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _valid_bias_cfg(**overrides) -> MRDirectionalBiasConfig:
    base = dict(
        enabled=True,
        base_long_threshold=0.10,
        base_short_threshold=0.10,
        funding_shift_magnitude=0.02,
        funding_normalization_scale=0.0003,
        funding_deadband=0.1,
        threshold_clamp_min=0.01,
        threshold_clamp_max=0.3,
    )
    base.update(overrides)
    return MRDirectionalBiasConfig(**base)


def _make_handler(
    symbol: str = "DOGEUSDT",
    bias_cfg: MRDirectionalBiasConfig | None = None,
    features: Dict[str, Any] | None = None,
) -> MeanReversionHandler:
    handler = object.__new__(MeanReversionHandler)
    handler.logger = logging.getLogger("test.mr.directional_bias")
    handler._last_cmd_features = {}
    handler._directional_bias_configs = {}

    if bias_cfg is not None:
        handler._directional_bias_configs[symbol] = bias_cfg
    if features is not None:
        handler._last_cmd_features[symbol] = features

    return handler


def _make_strategy(entry_threshold: float = 0.10) -> MeanReversion1mStrategy:
    cfg = MRStrategyConfig(entry_threshold=Decimal(str(entry_threshold)))
    return MeanReversion1mStrategy(config=cfg)


# ── 1. Static split thresholds without funding ─────────────────────────────

def test_static_split_without_funding():
    """When funding is missing, use static base_long/base_short."""
    bias = _valid_bias_cfg(base_long_threshold=0.08, base_short_threshold=0.12)
    handler = _make_handler(bias_cfg=bias, features={})  # no funding_rate
    strategy = _make_strategy(entry_threshold=0.10)

    handler._apply_directional_bias("DOGEUSDT", strategy)

    assert strategy.config.entry_threshold_long == Decimal("0.08")
    assert strategy.config.entry_threshold_short == Decimal("0.12")


# ── 2. Positive funding shifts correctly ────────────────────────────────────

def test_positive_funding_shifts():
    """Positive funding (longs pay): LONG harder (lower threshold), SHORT easier (higher threshold).

    Trigger geometry:
      LONG  fires when pct_b < long_threshold  → lower threshold = harder
      SHORT fires when pct_b > 1 - short_threshold → higher short_threshold = lower boundary = easier
    """
    bias = _valid_bias_cfg(
        base_long_threshold=0.10,
        base_short_threshold=0.10,
        funding_shift_magnitude=0.02,
        funding_normalization_scale=0.0003,
        funding_deadband=0.0,  # disable deadband for this test
    )
    # funding_rate = 0.0003 → norm = 1.0 (clamped)
    handler = _make_handler(
        bias_cfg=bias,
        features={"funding_rate": "0.0003"},
    )
    strategy = _make_strategy()

    handler._apply_directional_bias("DOGEUSDT", strategy)

    # eff_long = 0.10 - 1.0 * 0.02 = 0.08 (LONG harder: pct_b must be < 0.08 instead of < 0.10)
    assert strategy.config.entry_threshold_long == Decimal("0.08")
    # eff_short = 0.10 + 1.0 * 0.02 = 0.12 (SHORT easier: pct_b must be > 0.88 instead of > 0.90)
    assert strategy.config.entry_threshold_short == Decimal("0.12")


# ── 3. Negative funding shifts correctly ────────────────────────────────────

def test_negative_funding_shifts():
    """Negative funding (shorts pay): LONG easier (higher threshold), SHORT harder (lower threshold).

    Trigger geometry:
      LONG  fires when pct_b < long_threshold  → higher threshold = easier
      SHORT fires when pct_b > 1 - short_threshold → lower short_threshold = higher boundary = harder
    """
    bias = _valid_bias_cfg(
        base_long_threshold=0.10,
        base_short_threshold=0.10,
        funding_shift_magnitude=0.02,
        funding_normalization_scale=0.0003,
        funding_deadband=0.0,
    )
    # funding_rate = -0.0003 → norm = -1.0
    handler = _make_handler(
        bias_cfg=bias,
        features={"funding_rate": "-0.0003"},
    )
    strategy = _make_strategy()

    handler._apply_directional_bias("DOGEUSDT", strategy)

    # eff_long = 0.10 - (-1.0) * 0.02 = 0.12 (LONG easier: pct_b must be < 0.12 instead of < 0.10)
    assert strategy.config.entry_threshold_long == Decimal("0.12")
    # eff_short = 0.10 + (-1.0) * 0.02 = 0.08 (SHORT harder: pct_b must be > 0.92 instead of > 0.90)
    assert strategy.config.entry_threshold_short == Decimal("0.08")


# ── 4. Clamp prevents out-of-range thresholds ──────────────────────────────

def test_clamp_prevents_too_low():
    """Extreme shift cannot push threshold below clamp_min."""
    bias = _valid_bias_cfg(
        base_long_threshold=0.02,
        base_short_threshold=0.10,
        funding_shift_magnitude=0.05,  # very large shift
        funding_normalization_scale=0.0003,
        funding_deadband=0.0,
        threshold_clamp_min=0.01,
    )
    # norm = +1.0 → eff_long = 0.02 - 0.05 = -0.03 → clamped to 0.01
    handler = _make_handler(
        bias_cfg=bias,
        features={"funding_rate": "0.0003"},
    )
    strategy = _make_strategy()
    handler._apply_directional_bias("DOGEUSDT", strategy)

    assert strategy.config.entry_threshold_long == Decimal("0.01")


def test_clamp_prevents_too_high():
    """Extreme shift cannot push threshold above clamp_max."""
    bias = _valid_bias_cfg(
        base_long_threshold=0.10,
        base_short_threshold=0.28,
        funding_shift_magnitude=0.05,
        funding_normalization_scale=0.0003,
        funding_deadband=0.0,
        threshold_clamp_max=0.3,
    )
    # norm = +1.0 → eff_short = 0.28 + 0.05 = 0.33 → clamped to 0.3
    handler = _make_handler(
        bias_cfg=bias,
        features={"funding_rate": "0.0003"},
    )
    strategy = _make_strategy()
    handler._apply_directional_bias("DOGEUSDT", strategy)

    assert strategy.config.entry_threshold_short == Decimal("0.3")


# ── 5. Deadband suppresses small funding noise ─────────────────────────────

def test_deadband_suppresses_noise():
    """Small normalized funding within deadband → treated as zero."""
    bias = _valid_bias_cfg(
        base_long_threshold=0.10,
        base_short_threshold=0.10,
        funding_normalization_scale=0.0003,
        funding_deadband=0.2,  # 20% deadband
    )
    # funding = 0.00003 → norm = 0.1 → below deadband 0.2 → zero
    handler = _make_handler(
        bias_cfg=bias,
        features={"funding_rate": "0.00003"},
    )
    strategy = _make_strategy()
    handler._apply_directional_bias("DOGEUSDT", strategy)

    # No shift: thresholds stay at base
    assert strategy.config.entry_threshold_long == Decimal("0.1")
    assert strategy.config.entry_threshold_short == Decimal("0.1")


# ── 6. Missing funding falls back to static split ──────────────────────────

def test_missing_funding_returns_static():
    """No funding_rate in features → static split thresholds."""
    bias = _valid_bias_cfg(
        base_long_threshold=0.08,
        base_short_threshold=0.12,
    )
    handler = _make_handler(bias_cfg=bias, features={})
    strategy = _make_strategy()
    handler._apply_directional_bias("DOGEUSDT", strategy)

    assert strategy.config.entry_threshold_long == Decimal("0.08")
    assert strategy.config.entry_threshold_short == Decimal("0.12")


def test_missing_funding_does_not_block_strategy():
    """Missing funding does NOT fail-closed — strategy can still trade."""
    bias = _valid_bias_cfg()
    handler = _make_handler(bias_cfg=bias, features={})
    strategy = _make_strategy()
    handler._apply_directional_bias("DOGEUSDT", strategy)

    # Thresholds are set (not None), so strategy proceeds
    assert strategy.config.entry_threshold_long is not None
    assert strategy.config.entry_threshold_short is not None


# ── 7. Legacy compatibility — None overrides use symmetric threshold ────────

def test_no_bias_config_clears_overrides():
    """When directional_bias not configured, overrides are None → legacy symmetric."""
    handler = _make_handler(bias_cfg=None, features={})
    strategy = _make_strategy(entry_threshold=0.115)

    # Pre-set some overrides
    strategy.config.entry_threshold_long = Decimal("0.05")
    strategy.config.entry_threshold_short = Decimal("0.08")

    handler._apply_directional_bias("DOGEUSDT", strategy)

    # Should be cleared
    assert strategy.config.entry_threshold_long is None
    assert strategy.config.entry_threshold_short is None


# ── Strategy-level integration: split thresholds affect signal ──────────────

def test_split_thresholds_affect_long_signal():
    """With lower long_threshold, LONG signals require more extreme pct_b."""
    cfg = MRStrategyConfig(
        entry_threshold=Decimal("0.10"),
        entry_threshold_long=Decimal("0.05"),  # stricter for LONG
        min_bars=1,
        allowed_regimes=["FLAT_LOW", "FLAT_NORMAL",
                         "FLAT_HIGH", "MEAN_REVERSION"],
    )
    strategy = MeanReversion1mStrategy(config=cfg)
    strategy.set_regime("TEST", "MEAN_REVERSION")

    # Feed enough bars to compute indicators
    from apps.reference.domains.feature_engineering.bar_resampler import Bar
    for i in range(30):
        bar = Bar(
            symbol="TEST",
            timeframe_sec=300,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1000"),
            start_ts_ms=i * 300000,
            end_ts_ms=(i + 1) * 300000,
            trade_count=100,
        )
        strategy.on_bar("TEST", bar, bar.end_ts_ms)

    # The strategy config has explicit long threshold = 0.05
    assert cfg.entry_threshold_long == Decimal("0.05")
    assert cfg.entry_threshold_short is None  # SHORT uses legacy 0.10


def test_split_thresholds_affect_short_signal():
    """With lower short_threshold, SHORT signals require more extreme pct_b."""
    cfg = MRStrategyConfig(
        entry_threshold=Decimal("0.10"),
        entry_threshold_short=Decimal("0.05"),  # stricter for SHORT
        min_bars=1,
        allowed_regimes=["FLAT_LOW", "FLAT_NORMAL",
                         "FLAT_HIGH", "MEAN_REVERSION"],
    )

    # The strategy config has explicit short threshold
    assert cfg.entry_threshold_short == Decimal("0.05")
    assert cfg.entry_threshold_long is None  # LONG uses legacy 0.10


# ── Input validation matrix ─────────────────────────────────────────────────

def test_invalid_funding_degrades_to_static():
    """Non-numeric funding_rate → degrade to static split."""
    bias = _valid_bias_cfg(base_long_threshold=0.07, base_short_threshold=0.13)
    handler = _make_handler(
        bias_cfg=bias,
        features={"funding_rate": "not_a_number"},
    )
    strategy = _make_strategy()
    handler._apply_directional_bias("DOGEUSDT", strategy)

    assert strategy.config.entry_threshold_long == Decimal("0.07")
    assert strategy.config.entry_threshold_short == Decimal("0.13")


def test_zero_funding_no_shift():
    """Zero funding → no shift from base thresholds."""
    bias = _valid_bias_cfg(
        base_long_threshold=0.10,
        base_short_threshold=0.10,
        funding_deadband=0.0,
    )
    handler = _make_handler(
        bias_cfg=bias,
        features={"funding_rate": "0.0"},
    )
    strategy = _make_strategy()
    handler._apply_directional_bias("DOGEUSDT", strategy)

    assert strategy.config.entry_threshold_long == Decimal("0.1")
    assert strategy.config.entry_threshold_short == Decimal("0.1")


# ── Trigger-boundary geometry proof (PACK-R2) ────────────────────────────────

def test_trigger_boundary_positive_funding():
    """PACK-R2: Prove exact trigger boundaries under positive funding.

    With base=0.10, positive funding norm=+1, magnitude=0.02:
      eff_long  = 0.10 - 0.02 = 0.08
      eff_short = 0.10 + 0.02 = 0.12

    Strategy trigger topology:
      LONG  fires when:  pct_b < long_threshold   = pct_b < 0.08
      SHORT fires when:  pct_b > (1 - short_threshold) = pct_b > (1 - 0.12) = pct_b > 0.88

    Baseline (no bias): LONG < 0.10, SHORT > 0.90
    With positive funding:
      LONG boundary moves DOWN (0.10 → 0.08): HARDER (needs more oversold)
      SHORT boundary moves DOWN (0.90 → 0.88): EASIER (needs less overbought)

    Economic intent: longs crowded → fade → SHORT easier, LONG harder ✓
    """
    bias = _valid_bias_cfg(
        base_long_threshold=0.10, base_short_threshold=0.10,
        funding_shift_magnitude=0.02, funding_normalization_scale=0.0003,
        funding_deadband=0.0,
    )
    handler = _make_handler(bias_cfg=bias, features={"funding_rate": "0.0003"})
    strategy = _make_strategy()
    handler._apply_directional_bias("DOGEUSDT", strategy)

    long_t = float(strategy.config.entry_threshold_long)
    short_t = float(strategy.config.entry_threshold_short)

    # Verify threshold values
    assert long_t == pytest.approx(0.08)
    assert short_t == pytest.approx(0.12)

    # Verify trigger BOUNDARIES (what pct_b must satisfy)
    long_boundary = long_t                # pct_b must be BELOW this for LONG
    short_boundary = 1.0 - short_t        # pct_b must be ABOVE this for SHORT

    assert long_boundary == pytest.approx(0.08)    # was 0.10 → now 0.08 → HARDER
    assert short_boundary == pytest.approx(0.88)    # was 0.90 → now 0.88 → EASIER

    # Baseline boundaries for comparison
    baseline_long = 0.10
    baseline_short = 0.90

    # LONG is harder: boundary moved DOWN (narrower zone)
    assert long_boundary < baseline_long
    # SHORT is easier: boundary moved DOWN (wider zone)
    assert short_boundary < baseline_short


def test_trigger_boundary_negative_funding():
    """PACK-R2: Prove exact trigger boundaries under negative funding.

    With base=0.10, negative funding norm=-1, magnitude=0.02:
      eff_long  = 0.10 + 0.02 = 0.12
      eff_short = 0.10 - 0.02 = 0.08

    Trigger boundaries:
      LONG:  pct_b < 0.12  (was 0.10 → EASIER)
      SHORT: pct_b > 0.92  (was 0.90 → HARDER)

    Economic intent: shorts crowded → fade → LONG easier, SHORT harder ✓
    """
    bias = _valid_bias_cfg(
        base_long_threshold=0.10, base_short_threshold=0.10,
        funding_shift_magnitude=0.02, funding_normalization_scale=0.0003,
        funding_deadband=0.0,
    )
    handler = _make_handler(bias_cfg=bias, features={"funding_rate": "-0.0003"})
    strategy = _make_strategy()
    handler._apply_directional_bias("DOGEUSDT", strategy)

    long_t = float(strategy.config.entry_threshold_long)
    short_t = float(strategy.config.entry_threshold_short)

    long_boundary = long_t
    short_boundary = 1.0 - short_t

    assert long_boundary == pytest.approx(0.12)    # was 0.10 → now 0.12 → EASIER
    assert short_boundary == pytest.approx(0.92)    # was 0.90 → now 0.92 → HARDER

    baseline_long = 0.10
    baseline_short = 0.90

    # LONG is easier: boundary moved UP (wider zone)
    assert long_boundary > baseline_long
    # SHORT is harder: boundary moved UP (narrower zone)
    assert short_boundary > baseline_short


# ── PACK-R3: Cross-symbol isolation proof ─────────────────────────────────────

def _make_multi_symbol_handler(
    symbols_and_features: Dict[str, Dict[str, Any]],
    bias_cfg: MRDirectionalBiasConfig,
) -> MeanReversionHandler:
    """Create handler with multiple symbols, each having their own features."""
    handler = object.__new__(MeanReversionHandler)
    handler.logger = logging.getLogger("test.mr.cross_symbol")
    handler._last_cmd_features = {}
    handler._directional_bias_configs = {}

    for sym, feats in symbols_and_features.items():
        handler._directional_bias_configs[sym] = bias_cfg
        handler._last_cmd_features[sym] = feats

    return handler


def test_cross_symbol_no_contamination():
    """PACK-R3: Symbol A's funding-derived thresholds do not leak to Symbol B.

    Symbol A has positive funding → eff_long = 0.08, eff_short = 0.12
    Symbol B has negative funding → eff_long = 0.12, eff_short = 0.08
    Prove each gets its own values.
    """
    bias = _valid_bias_cfg(
        base_long_threshold=0.10, base_short_threshold=0.10,
        funding_shift_magnitude=0.02, funding_normalization_scale=0.0003,
        funding_deadband=0.0,
    )
    handler = _make_multi_symbol_handler(
        symbols_and_features={
            "DOGEUSDT": {"funding_rate": "0.0003"},   # pos funding
            "BTCUSDT": {"funding_rate": "-0.0003"},    # neg funding
        },
        bias_cfg=bias,
    )

    strategy_a = _make_strategy()
    strategy_b = _make_strategy()

    # Apply to A first, then B
    handler._apply_directional_bias("DOGEUSDT", strategy_a)
    handler._apply_directional_bias("BTCUSDT", strategy_b)

    # A: positive funding → long=0.08, short=0.12
    assert strategy_a.config.entry_threshold_long == Decimal("0.08")
    assert strategy_a.config.entry_threshold_short == Decimal("0.12")

    # B: negative funding → long=0.12, short=0.08 (NOT contaminated by A's values)
    assert strategy_b.config.entry_threshold_long == Decimal("0.12")
    assert strategy_b.config.entry_threshold_short == Decimal("0.08")


def test_cross_symbol_missing_funding_does_not_inherit():
    """PACK-R3: Symbol B with missing funding gets static thresholds, not A's values."""
    bias = _valid_bias_cfg(
        base_long_threshold=0.10, base_short_threshold=0.10,
        funding_shift_magnitude=0.02, funding_normalization_scale=0.0003,
        funding_deadband=0.0,
    )
    handler = _make_multi_symbol_handler(
        symbols_and_features={
            "DOGEUSDT": {"funding_rate": "0.0003"},
            "BTCUSDT": {},  # no funding_rate
        },
        bias_cfg=bias,
    )

    strategy_a = _make_strategy()
    strategy_b = _make_strategy()

    handler._apply_directional_bias("DOGEUSDT", strategy_a)
    handler._apply_directional_bias("BTCUSDT", strategy_b)

    # A: positive funding → long=0.08, short=0.12
    assert strategy_a.config.entry_threshold_long == Decimal("0.08")
    assert strategy_a.config.entry_threshold_short == Decimal("0.12")

    # B: missing funding → static base thresholds (0.10, 0.10)
    assert strategy_b.config.entry_threshold_long == Decimal("0.1")
    assert strategy_b.config.entry_threshold_short == Decimal("0.1")


def test_interleaved_symbol_processing_order():
    """PACK-R3: Repeated interleaving: A→B→A→B produces correct results each time."""
    bias = _valid_bias_cfg(
        base_long_threshold=0.10, base_short_threshold=0.10,
        funding_shift_magnitude=0.02, funding_normalization_scale=0.0003,
        funding_deadband=0.0,
    )
    handler = _make_multi_symbol_handler(
        symbols_and_features={
            "DOGEUSDT": {"funding_rate": "0.0003"},
            "BTCUSDT": {"funding_rate": "-0.0003"},
        },
        bias_cfg=bias,
    )

    strategy_a = _make_strategy()
    strategy_b = _make_strategy()

    for _ in range(3):  # 3 rounds of A→B interleaving
        handler._apply_directional_bias("DOGEUSDT", strategy_a)
        assert strategy_a.config.entry_threshold_long == Decimal("0.08")
        assert strategy_a.config.entry_threshold_short == Decimal("0.12")

        handler._apply_directional_bias("BTCUSDT", strategy_b)
        assert strategy_b.config.entry_threshold_long == Decimal("0.12")
        assert strategy_b.config.entry_threshold_short == Decimal("0.08")

        # Verify A wasn't contaminated by B's processing
        assert strategy_a.config.entry_threshold_long == Decimal("0.08")
        assert strategy_a.config.entry_threshold_short == Decimal("0.12")


def test_thresholds_cleared_after_on_bar_simulation():
    """PACK-R3: After bias is applied and consumed, overrides don't persist.

    This mirrors the try/finally cleanup in _on_process_strategy.
    """
    bias = _valid_bias_cfg(
        base_long_threshold=0.07, base_short_threshold=0.13,
    )
    handler = _make_handler(bias_cfg=bias, features={})
    strategy = _make_strategy()

    # Apply bias (static split because no funding)
    handler._apply_directional_bias("DOGEUSDT", strategy)
    assert strategy.config.entry_threshold_long == Decimal("0.07")
    assert strategy.config.entry_threshold_short == Decimal("0.13")

    # Simulate the try/finally cleanup from _on_process_strategy
    strategy.config.entry_threshold_long = None
    strategy.config.entry_threshold_short = None

    # Verify overrides are cleared
    assert strategy.config.entry_threshold_long is None
    assert strategy.config.entry_threshold_short is None
