"""
Contract test: MeanReversion1mStrategy confidence formula reads from MRStrategyConfig fields.

MR-CONFIDENCE-CONFIG-CONTRACT-01:
Tier D migrated hardcoded confidence parameters (0.5, 2, 0.2) to configurable fields
in MRStrategyConfig. The _evaluate_signal method must use these config fields instead
of literal magic numbers.

Fields added to MRStrategyConfig:
    confidence_base: Decimal = Decimal("0.5")           # was hardcoded 0.5
    confidence_distance_mult: Decimal = Decimal("2")     # was hardcoded 2
    rsi_confidence_boost: Decimal = Decimal("0.2")       # was hardcoded 0.2

These tests verify behaviorally that changing each field has the expected effect
on output confidence, proving the code reads from config and not literals.
"""
import pytest
from decimal import Decimal
from typing import Optional

from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MeanReversion1mStrategy,
    MRStrategyConfig,
    MRSymbolState,
    MRSignalType,
)
from apps.reference.domains.feature_engineering.indicators import BollingerBands
from apps.reference.domains.feature_engineering.bar_resampler import Bar
from apps.reference.domains.feature_engineering.regime_mapping import (
    FlatRegime,
    MRParameters,
)

_REGIME_SIZING = {
    "FLAT_LOW": {"sizing_mult": 0.8, "stop_mult": 1.0, "target_mult": 0.8},
    "FLAT_NORMAL": {"sizing_mult": 1.0, "stop_mult": 1.0, "target_mult": 1.0},
    "FLAT_HIGH": {"sizing_mult": 0.7, "stop_mult": 1.5, "target_mult": 1.2},
}


def _make_bar(close: float = 100.0) -> Bar:
    """Create a minimal bar suitable for testing."""
    p = Decimal(str(close))
    return Bar(
        symbol="BTCUSDT",
        timeframe_sec=180,
        open=p,
        high=p,
        low=p,
        close=p,
        volume=Decimal("1.0"),
        trade_count=1,
        start_ts_ms=1700000000000,
        end_ts_ms=1700000180000,
    )


def _make_long_bb(pct_b: float = -0.1) -> BollingerBands:
    """
    BB that triggers a LONG signal: pct_b < entry_threshold (default 0.05).
    Width=0.04 is safely within [0.001, 0.05] bounds.
    """
    return BollingerBands(
        upper=Decimal("102.0"),
        lower=Decimal("98.0"),
        mid=Decimal("100.0"),
        width=0.04,
        pct_b=pct_b,
    )


def _make_short_bb(pct_b: float = 1.1) -> BollingerBands:
    """
    BB that triggers a SHORT signal: pct_b > 1 - entry_threshold (>0.95).
    """
    return BollingerBands(
        upper=Decimal("102.0"),
        lower=Decimal("98.0"),
        mid=Decimal("100.0"),
        width=0.04,
        pct_b=pct_b,
    )


def _make_state(
    symbol: str = "BTCUSDT",
    bb: Optional[BollingerBands] = None,
    rsi: Optional[float] = None,
) -> MRSymbolState:
    """Create MRSymbolState pre-populated with one bar, given BB and optional RSI."""
    state = MRSymbolState(symbol=symbol)
    state.add_bar(_make_bar())
    state.bb = bb
    state.rsi = Decimal(str(rsi)) if rsi is not None else None
    return state


def _make_strategy(
    confidence_base: str = "0.5",
    confidence_distance_mult: str = "2",
    rsi_confidence_boost: str = "0.2",
) -> MeanReversion1mStrategy:
    """Build a strategy with custom confidence parameters."""
    config = MRStrategyConfig(
        confidence_base=Decimal(confidence_base),
        confidence_distance_mult=Decimal(confidence_distance_mult),
        rsi_confidence_boost=Decimal(rsi_confidence_boost),
    )
    return MeanReversion1mStrategy(
        config=config,
        timeframe_sec=180,
        regime_sizing=_REGIME_SIZING,
    )


def _eval(strategy: MeanReversion1mStrategy, state: MRSymbolState):
    """Call _evaluate_signal with FLAT_NORMAL regime defaults."""
    flat_regime = FlatRegime.FLAT_NORMAL
    mr_params = MRParameters.from_flat_regime(flat_regime)
    return strategy._evaluate_signal(
        state=state,
        flat_regime=flat_regime,
        mr_params=mr_params,
        timestamp_ms=1700000000000,
    )


class TestConfidenceBaseIsConfigurable:
    """confidence_base must come from MRStrategyConfig, not hardcoded 0.5."""

    def test_base_07_gives_confidence_gte_07(self):
        """
        With confidence_base=0.7, all LONG signals must have confidence >= 0.7.
        If hardcoded to 0.5, this test will fail.
        """
        strategy = _make_strategy(confidence_base="0.7")
        state = _make_state(bb=_make_long_bb(-0.1))  # pct_b=-0.1 → LONG

        signal = _eval(strategy, state)

        assert signal.signal_type == MRSignalType.LONG
        assert signal.confidence >= Decimal("0.7"), (
            f"Expected confidence >= 0.7 (config base), got {signal.confidence}. "
            "confidence_base is hardcoded to 0.5."
        )

    def test_base_0_gives_lower_confidence_than_base_05(self):
        """confidence_base=0.0 must produce strictly lower confidence than default 0.5."""
        strategy_default = _make_strategy(confidence_base="0.5")
        strategy_zero = _make_strategy(confidence_base="0.0")

        sig_default = _eval(
            strategy_default, _make_state(bb=_make_long_bb(-0.1)))
        sig_zero = _eval(strategy_zero, _make_state(bb=_make_long_bb(-0.1)))

        assert sig_zero.confidence < sig_default.confidence, (
            "confidence_base=0.0 must give lower confidence than 0.5. "
            "Equal values mean confidence_base is hardcoded."
        )

    def test_default_base_matches_legacy_value(self):
        """
        Default confidence_base=0.5 with pct_b=-0.1 must equal legacy formula:
        0.5 + (0.05 - (-0.1)) * 2 = 0.5 + 0.15 * 2 = 0.8
        """
        strategy = _make_strategy(
            confidence_base="0.5", confidence_distance_mult="2")
        state = _make_state(bb=_make_long_bb(pct_b=-0.1))

        signal = _eval(strategy, state)

        assert signal.signal_type == MRSignalType.LONG
        assert signal.confidence == Decimal("0.8"), (
            f"Expected 0.8 per legacy formula, got {signal.confidence}."
        )


class TestConfidenceDistanceMultIsConfigurable:
    """confidence_distance_mult must come from MRStrategyConfig, not hardcoded 2."""

    def test_mult4_gives_higher_confidence_than_mult1(self):
        """Higher multiplier → higher (or capped) confidence for same BB distance."""
        strategy_mult1 = _make_strategy(confidence_distance_mult="1")
        strategy_mult4 = _make_strategy(confidence_distance_mult="4")

        # pct_b=-0.1: dist=0.15
        # mult=1: 0.5 + 0.15*1 = 0.65
        # mult=4: 0.5 + 0.15*4 = 1.1 → capped at 1.0
        sig1 = _eval(strategy_mult1, _make_state(bb=_make_long_bb(-0.1)))
        sig4 = _eval(strategy_mult4, _make_state(bb=_make_long_bb(-0.1)))

        assert sig4.confidence >= sig1.confidence, (
            f"mult=4 ({sig4.confidence}) must be >= mult=1 ({sig1.confidence}). "
            "confidence_distance_mult is hardcoded."
        )

    def test_mult1_not_equal_to_mult2(self):
        """Changing multiplier from default 2 to 1 must change confidence."""
        strategy_mult2 = _make_strategy(confidence_distance_mult="2")
        strategy_mult1 = _make_strategy(confidence_distance_mult="1")

        # Small pct_b so confidence doesn't cap at 1.0
        # pct_b=0.01: dist=0.04, mult=2: 0.5+0.08=0.58, mult=1: 0.5+0.04=0.54
        sig2 = _eval(strategy_mult2, _make_state(bb=_make_long_bb(0.01)))
        sig1 = _eval(strategy_mult1, _make_state(bb=_make_long_bb(0.01)))

        assert sig2.confidence != sig1.confidence, (
            "Different distance multipliers must produce different confidence values. "
            "confidence_distance_mult is hardcoded."
        )


class TestRsiConfidenceBoostIsConfigurable:
    """rsi_confidence_boost must come from MRStrategyConfig, not hardcoded 0.2."""

    def test_boost03_gives_higher_confidence_than_boost02_with_rsi_confirm(self):
        """
        RSI < 30 confirms LONG. With rsi_confidence_boost=0.3, confidence
        must be higher than with boost=0.2.

        Use a shallow pct_b=0.03 so pre-boost confidence (≈0.54) stays well below
        the 1.0 cap even with the larger boost: 0.54+0.2=0.74 vs 0.54+0.3=0.84.
        """
        strategy_02 = _make_strategy(rsi_confidence_boost="0.2")
        strategy_03 = _make_strategy(rsi_confidence_boost="0.3")

        # pct_b=0.03 is below entry_threshold=0.05 → LONG, but shallow enough
        # that +0.3 boost doesn't cap to 1.0 along with +0.2
        state_02 = _make_state(bb=_make_long_bb(
            0.03), rsi=25.0)   # RSI confirms
        state_03 = _make_state(bb=_make_long_bb(0.03), rsi=25.0)

        sig_02 = _eval(strategy_02, state_02)
        sig_03 = _eval(strategy_03, state_03)

        assert sig_02.signal_type == MRSignalType.LONG
        assert sig_03.signal_type == MRSignalType.LONG
        assert sig_03.confidence > sig_02.confidence, (
            f"boost=0.3 ({sig_03.confidence}) must be > boost=0.2 ({sig_02.confidence}). "
            "rsi_confidence_boost is hardcoded."
        )

    def test_boost_not_applied_when_rsi_does_not_confirm(self):
        """RSI=50 (neutral) must NOT trigger the boost."""
        strategy = _make_strategy(rsi_confidence_boost="0.3")

        state_neutral_rsi = _make_state(bb=_make_long_bb(-0.1), rsi=50.0)
        state_confirm_rsi = _make_state(bb=_make_long_bb(-0.1), rsi=25.0)

        sig_no_boost = _eval(strategy, state_neutral_rsi)
        sig_boost = _eval(strategy, state_confirm_rsi)

        assert sig_boost.confidence > sig_no_boost.confidence, (
            "RSI-confirmed signal must be more confident than non-confirmed. "
            "Boost was not applied."
        )

    def test_boost_zero_makes_rsi_irrelevant(self):
        """rsi_confidence_boost=0.0 means RSI confirmation has zero effect."""
        strategy = _make_strategy(rsi_confidence_boost="0.0")

        state_no_rsi = _make_state(
            bb=_make_long_bb(-0.1), rsi=50.0)   # no confirm
        state_rsi = _make_state(bb=_make_long_bb(-0.1),
                                rsi=25.0)      # confirms

        sig_no = _eval(strategy, state_no_rsi)
        sig_yes = _eval(strategy, state_rsi)

        assert sig_no.confidence == sig_yes.confidence, (
            f"boost=0.0 must make RSI irrelevant: no_rsi={sig_no.confidence}, "
            f"rsi={sig_yes.confidence}."
        )


class TestShortSideConfidenceConfig:
    """Config params apply symmetrically to SHORT signals."""

    def test_custom_base_for_short(self):
        """confidence_base=0.7 applies identically to SHORT signals."""
        strategy = _make_strategy(confidence_base="0.7")
        state = _make_state(bb=_make_short_bb(1.1))  # pct_b=1.1 → SHORT

        signal = _eval(strategy, state)

        assert signal.signal_type == MRSignalType.SHORT
        assert signal.confidence >= Decimal("0.7"), (
            f"SHORT: expected confidence >= 0.7, got {signal.confidence}."
        )

    def test_rsi_boost_for_short_with_overbought_rsi(self):
        """RSI > 70 confirms SHORT; boost must be added."""
        strategy_02 = _make_strategy(rsi_confidence_boost="0.2")
        strategy_05 = _make_strategy(rsi_confidence_boost="0.5")

        state_02 = _make_state(bb=_make_short_bb(
            1.1), rsi=75.0)  # confirms SHORT
        state_05 = _make_state(bb=_make_short_bb(1.1), rsi=75.0)

        sig_02 = _eval(strategy_02, state_02)
        sig_05 = _eval(strategy_05, state_05)

        assert sig_02.signal_type == MRSignalType.SHORT
        assert sig_05.signal_type == MRSignalType.SHORT
        assert sig_05.confidence >= sig_02.confidence, (
            f"Larger boost must produce >= confidence: boost=0.5 ({sig_05.confidence}) "
            f"vs boost=0.2 ({sig_02.confidence})."
        )
