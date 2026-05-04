from decimal import Decimal

from apps.reference.domains.feature_engineering.bar_resampler import Bar
from apps.reference.domains.feature_engineering.indicators import BollingerBands
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MRSignalType,
    MRStrategyConfig,
    MeanReversion1mStrategy,
)
from apps.reference.domains.feature_engineering.regime_mapping import FlatRegime, MRParameters


def _make_strategy(
    *,
    flat_low_short_min_bb_width: Decimal | None = None,
) -> MeanReversion1mStrategy:
    config = MRStrategyConfig(
        min_bb_width=Decimal("0.005"),
        max_bb_width=Decimal("0.15"),
        entry_threshold=Decimal("0.05"),
        cooldown_sec=0,
        allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "MEAN_REVERSION"],
        flat_low_short_min_bb_width=flat_low_short_min_bb_width,
    )
    return MeanReversion1mStrategy(config=config, timeframe_sec=300)


def _evaluate_signal(
    *,
    symbol: str,
    flat_regime: FlatRegime,
    pct_b: float,
    bb_width: float,
    flat_low_short_min_bb_width: Decimal | None,
) -> tuple[MeanReversion1mStrategy, object]:
    strategy = _make_strategy(
        flat_low_short_min_bb_width=flat_low_short_min_bb_width,
    )
    state = strategy.get_state(symbol)
    state.add_bar(
        Bar(
            symbol=symbol,
            timeframe_sec=300,
            open=Decimal("0.1000"),
            high=Decimal("0.1010"),
            low=Decimal("0.0990"),
            close=Decimal("0.1005"),
            volume=Decimal("1000"),
            trade_count=25,
            start_ts_ms=1_700_000_000_000,
            end_ts_ms=1_700_000_300_000,
        )
    )
    state.bb = BollingerBands(
        upper=Decimal("0.1010"),
        lower=Decimal("0.0990"),
        mid=Decimal("0.1000"),
        width=bb_width,
        pct_b=pct_b,
    )
    state.atr = Decimal("0.0008")
    state.rsi = Decimal("65")

    signal = strategy._evaluate_signal(
        state,
        flat_regime,
        MRParameters.from_flat_regime(flat_regime),
        timestamp_ms=1_700_000_300_000,
    )
    return strategy, signal


def test_doge_flat_low_short_with_narrow_band_breakout_setup_is_rejected() -> None:
    """
    Hypothesis:
    DOGE/high-beta FLAT_LOW shorts need a stricter width gate than the global floor.

    Why this matters:
    The toxic 2026-03-13 class was a narrow-band breakout fade that current MR admitted.

    Current expected buggy behavior:
    The narrow-band SHORT still passes because only the generic min_bb_width is enforced.

    What future repair should change:
    A per-symbol FLAT_LOW short width hardening gate must block this setup with explicit why.
    """
    _, signal = _evaluate_signal(
        symbol="DOGEUSDT",
        flat_regime=FlatRegime.FLAT_LOW,
        pct_b=1.08,
        bb_width=0.010,
        flat_low_short_min_bb_width=Decimal("0.015"),
    )

    assert signal.signal_type == MRSignalType.NEUTRAL
    assert signal.why == "neutral:flat_low_short_bb_width_too_narrow:0.01<0.015"


def test_doge_valid_wider_band_flat_low_short_remains_allowed() -> None:
    """
    Hypothesis:
    DOGE hardening must not kill every FLAT_LOW short, only the narrow toxic class.

    Why this matters:
    A global or overbroad fix would erase the remaining MR short edge instead of hardening it.

    Current expected buggy behavior:
    Wider-band and narrow-band DOGE shorts are treated the same.

    What future repair should change:
    Wider FLAT_LOW DOGE shorts should still emit SHORT when they clear the stricter width floor.
    """
    _, signal = _evaluate_signal(
        symbol="DOGEUSDT",
        flat_regime=FlatRegime.FLAT_LOW,
        pct_b=1.08,
        bb_width=0.020,
        flat_low_short_min_bb_width=Decimal("0.015"),
    )

    assert signal.signal_type == MRSignalType.SHORT
    assert "price_above_upper_bb" in signal.why


def test_non_target_symbol_behavior_is_unchanged_without_explicit_override() -> None:
    """
    Hypothesis:
    Non-target symbols must keep current behavior unless the new hardening field is configured.

    Why this matters:
    P2-A is a DOGE/high-beta package, not a stealth global MR retune.

    Current expected buggy behavior:
    None. This is the blast-radius guard for the repair package.

    What future repair should change:
    BTC/ETH-style paths should continue using the old generic width gate when no override exists.
    """
    _, signal = _evaluate_signal(
        symbol="BTCUSDT",
        flat_regime=FlatRegime.FLAT_LOW,
        pct_b=1.08,
        bb_width=0.010,
        flat_low_short_min_bb_width=None,
    )

    assert signal.signal_type == MRSignalType.SHORT
    assert "price_above_upper_bb" in signal.why


def test_flat_low_short_hardening_blocks_only_the_targeted_toxic_class() -> None:
    """
    Hypothesis:
    The new gate should apply only to FLAT_LOW shorts, not longs or other flat regimes.

    Why this matters:
    The package must stay narrow and avoid a hidden regime-wide MR redesign.

    Current expected buggy behavior:
    None. This is the precision guard for the repair package.

    What future repair should change:
    FLAT_LOW longs and FLAT_NORMAL shorts must remain on the existing logic path.
    """
    _, long_signal = _evaluate_signal(
        symbol="DOGEUSDT",
        flat_regime=FlatRegime.FLAT_LOW,
        pct_b=-0.08,
        bb_width=0.010,
        flat_low_short_min_bb_width=Decimal("0.015"),
    )
    _, flat_normal_short = _evaluate_signal(
        symbol="DOGEUSDT",
        flat_regime=FlatRegime.FLAT_NORMAL,
        pct_b=1.08,
        bb_width=0.010,
        flat_low_short_min_bb_width=Decimal("0.015"),
    )

    assert long_signal.signal_type == MRSignalType.LONG
    assert flat_normal_short.signal_type == MRSignalType.SHORT
