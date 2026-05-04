from decimal import Decimal

from apps.reference.domains.feature_engineering.bar_resampler import Bar
from apps.reference.domains.feature_engineering.indicators import BollingerBands
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MRSignalType,
    MRStrategyConfig,
    MeanReversion1mStrategy,
    MomentumSeparationVetoConfig,
    SqueezeExpansionVetoConfig,
)
from apps.reference.domains.feature_engineering.regime_mapping import FlatRegime, MRParameters


def _squeeze_veto_config() -> SqueezeExpansionVetoConfig:
    return SqueezeExpansionVetoConfig(
        enabled=True,
        squeeze_width_max=Decimal("0.001"),
        post_squeeze_width_max=Decimal("0.005"),
        expansion_ratio_min=Decimal("3.0"),
        regimes=["FLAT_LOW"],
        sides=["LONG", "SHORT"],
    )


def _momentum_veto_config() -> MomentumSeparationVetoConfig:
    return MomentumSeparationVetoConfig(
        enabled=True,
        lookback_bars=4,
        min_drift_pct=Decimal("0.02"),
        min_current_bb_width=Decimal("0.020"),
        regimes=["FLAT_LOW"],
        sides=["LONG", "SHORT"],
    )


def _make_bar(symbol: str, close: Decimal, index: int) -> Bar:
    start_ts = 1_700_000_000_000 + index * 300_000
    return Bar(
        symbol=symbol,
        timeframe_sec=300,
        open=close,
        high=close + Decimal("0.02"),
        low=close - Decimal("0.02"),
        close=close,
        volume=Decimal("1000"),
        trade_count=20,
        start_ts_ms=start_ts,
        end_ts_ms=start_ts + 300_000,
    )


def _make_strategy(
    *,
    momentum_separation_veto: MomentumSeparationVetoConfig | None,
    squeeze_expansion_veto: SqueezeExpansionVetoConfig | None = None,
    flat_low_short_min_bb_width: Decimal | None = None,
) -> MeanReversion1mStrategy:
    config = MRStrategyConfig(
        bb_window=5,
        atr_window=3,
        rsi_window=3,
        min_bars=6,
        min_bb_width=Decimal("0.0001"),
        max_bb_width=Decimal("0.15"),
        entry_threshold=Decimal("0.05"),
        cooldown_sec=0,
        allowed_regimes=["FLAT_LOW", "FLAT_NORMAL",
                         "FLAT_HIGH", "MEAN_REVERSION"],
        flat_low_short_min_bb_width=flat_low_short_min_bb_width,
        squeeze_expansion_veto=squeeze_expansion_veto,
        momentum_separation_veto=momentum_separation_veto,
    )
    strategy = MeanReversion1mStrategy(config=config, timeframe_sec=300)
    strategy.set_regime("DOGEUSDT", "LOW_VOLATILITY")
    strategy.set_regime("BTCUSDT", "LOW_VOLATILITY")
    return strategy


def _run_sequence(
    *,
    symbol: str,
    closes: list[Decimal],
    momentum_separation_veto: MomentumSeparationVetoConfig | None,
    squeeze_expansion_veto: SqueezeExpansionVetoConfig | None = None,
) -> object:
    strategy = _make_strategy(
        momentum_separation_veto=momentum_separation_veto,
        squeeze_expansion_veto=squeeze_expansion_veto,
    )
    last_signal = None
    for index, close in enumerate(closes):
        last_signal = strategy.on_bar(
            symbol,
            _make_bar(symbol, close, index),
            1_700_000_000_000 + (index + 1) * 300_000,
        )
    return last_signal


def test_late_up_drift_short_fade_is_rejected() -> None:
    """
    Hypothesis:
    A late upper-band short fade should be vetoed once the market is already drifting upward hard.

    Why this matters:
    This is the post-squeeze toxic class left open after P2-B: the move is no longer a fresh breakout,
    but MR is still trying to fade a live directional drift.

    Current expected buggy behavior:
    The SHORT still passes because current MR has no late-drift separation gate.

    What future repair should change:
    The signal must be vetoed with an explicit momentum-separation reason.
    """
    signal = _run_sequence(
        symbol="DOGEUSDT",
        closes=[
            Decimal("100"),
            Decimal("100.4"),
            Decimal("100.8"),
            Decimal("101.2"),
            Decimal("101.6"),
            Decimal("103.2"),
        ],
        momentum_separation_veto=_momentum_veto_config(),
    )

    assert signal.signal_type == MRSignalType.NEUTRAL
    assert signal.why == "neutral:momentum_separation_veto:SHORT:+2.7888%"


def test_late_down_drift_long_fade_is_rejected() -> None:
    """
    Hypothesis:
    The same late-drift trap exists symmetrically on the long side after a persistent selloff.

    Why this matters:
    P2-C should separate mean reversion from obvious directional bleed on both sides when the
    same minimal drift geometry exists.

    Current expected buggy behavior:
    The LONG still passes because current MR only sees the lower-band touch.

    What future repair should change:
    The long fade must be vetoed with the same momentum-separation contract.
    """
    signal = _run_sequence(
        symbol="DOGEUSDT",
        closes=[
            Decimal("100"),
            Decimal("99.6"),
            Decimal("99.2"),
            Decimal("98.8"),
            Decimal("98.4"),
            Decimal("96.9"),
        ],
        momentum_separation_veto=_momentum_veto_config(),
    )

    assert signal.signal_type == MRSignalType.NEUTRAL
    assert signal.why == "neutral:momentum_separation_veto:LONG:-2.7108%"


def test_non_drifting_short_fade_is_still_allowed() -> None:
    """
    Hypothesis:
    A choppy upper-band touch should still be tradable when there is no sustained up-drift.

    Why this matters:
    The package must not turn into a blanket anti-short ban once bands widen.

    Current expected buggy behavior:
    None. This is the precision guard for P2-C.

    What future repair should change:
    Non-drifting short fades must remain on the existing MR path.
    """
    signal = _run_sequence(
        symbol="DOGEUSDT",
        closes=[
            Decimal("100"),
            Decimal("100.3"),
            Decimal("99.7"),
            Decimal("100.2"),
            Decimal("99.8"),
            Decimal("101.2"),
        ],
        momentum_separation_veto=_momentum_veto_config(),
    )

    assert signal.signal_type == MRSignalType.SHORT
    assert "price_above_upper_bb" in signal.why


def test_wider_band_but_non_drifting_long_signal_is_unaffected() -> None:
    """
    Hypothesis:
    P2-C should hit directional drift, not every wider-band lower-band touch.

    Why this matters:
    A wide-but-choppy long setup is not the same thing as a late-trend bleed.

    Current expected buggy behavior:
    None. This is the blast-radius guard for the new veto.

    What future repair should change:
    Wider-band long fades without persistent down-drift must still be allowed.
    """
    signal = _run_sequence(
        symbol="DOGEUSDT",
        closes=[
            Decimal("100"),
            Decimal("99.7"),
            Decimal("100.3"),
            Decimal("99.8"),
            Decimal("100.2"),
            Decimal("98.8"),
        ],
        momentum_separation_veto=_momentum_veto_config(),
    )

    assert signal.signal_type == MRSignalType.LONG
    assert "price_below_lower_bb" in signal.why


def test_squeeze_expansion_trap_stays_blocked_by_p2b_reason() -> None:
    """
    Hypothesis:
    Breakout-from-squeeze traps should still be owned by P2-B, not relabeled by P2-C.

    Why this matters:
    P2-C is about late drift after expansion, not about the initial squeeze break itself.

    Current expected buggy behavior:
    None. This is the contract boundary guard between P2-B and P2-C.

    What future repair should change:
    The squeeze trap must keep the P2-B reason when both vetoes are configured.
    """
    signal = _run_sequence(
        symbol="DOGEUSDT",
        closes=[
            Decimal("100"),
            Decimal("100.03"),
            Decimal("99.97"),
            Decimal("100.02"),
            Decimal("99.98"),
            Decimal("100.25"),
        ],
        momentum_separation_veto=_momentum_veto_config(),
        squeeze_expansion_veto=_squeeze_veto_config(),
    )

    assert signal.signal_type == MRSignalType.NEUTRAL
    assert signal.why == "neutral:squeeze_expansion_veto:SHORT:0.0009->0.0041"


def test_p2a_doge_hardening_still_works_with_momentum_veto_present() -> None:
    """
    Hypothesis:
    P2-C must not weaken the existing DOGE FLAT_LOW short hardening from P2-A.

    Why this matters:
    The packages are additive. P2-C should not rewrite the earlier explicit reason or scope.

    Current expected buggy behavior:
    None. This is the coexistence guard between P2-A and P2-C.

    What future repair should change:
    The P2-A width hardening must still win when late-drift context is unavailable.
    """
    strategy = _make_strategy(
        momentum_separation_veto=_momentum_veto_config(),
        flat_low_short_min_bb_width=Decimal("0.015"),
    )
    state = strategy.get_state("DOGEUSDT")
    state.add_bar(
        Bar(
            symbol="DOGEUSDT",
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
        width=0.010,
        pct_b=1.08,
    )
    state.atr = Decimal("0.0008")
    state.rsi = Decimal("65")

    signal = strategy._evaluate_signal(
        state,
        FlatRegime.FLAT_LOW,
        MRParameters.from_flat_regime(FlatRegime.FLAT_LOW),
        timestamp_ms=1_700_000_300_000,
    )

    assert signal.signal_type == MRSignalType.NEUTRAL
    assert signal.why == "neutral:flat_low_short_bb_width_too_narrow:0.01<0.015"


def test_non_target_symbol_behavior_is_unchanged_without_momentum_veto() -> None:
    """
    Hypothesis:
    Non-target symbols must keep current behavior unless the new veto is explicitly configured.

    Why this matters:
    P2-C should stay scoped to configured symbols instead of becoming a hidden global anti-trend rule.

    Current expected buggy behavior:
    None. This is the configuration scoping guard for the package.

    What future repair should change:
    The same late-drift sequence should still pass when no momentum veto is configured.
    """
    signal = _run_sequence(
        symbol="BTCUSDT",
        closes=[
            Decimal("100"),
            Decimal("100.4"),
            Decimal("100.8"),
            Decimal("101.2"),
            Decimal("101.6"),
            Decimal("103.2"),
        ],
        momentum_separation_veto=None,
    )

    assert signal.signal_type == MRSignalType.SHORT
    assert "price_above_upper_bb" in signal.why
