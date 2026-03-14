from decimal import Decimal

from apps.reference.domains.feature_engineering.bar_resampler import Bar
from apps.reference.domains.feature_engineering.indicators import BollingerBands
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MRSignalType,
    MRStrategyConfig,
    MeanReversion1mStrategy,
)
from apps.reference.domains.feature_engineering.regime_mapping import FlatRegime, MRParameters


def _squeeze_veto_config() -> dict:
    return {
        "enabled": True,
        "squeeze_width_max": Decimal("0.001"),
        "post_squeeze_width_max": Decimal("0.005"),
        "expansion_ratio_min": Decimal("3.0"),
        "regimes": ["FLAT_LOW"],
        "sides": ["LONG", "SHORT"],
    }


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
    squeeze_expansion_veto: dict | None,
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
        allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "MEAN_REVERSION"],
        flat_low_short_min_bb_width=flat_low_short_min_bb_width,
        squeeze_expansion_veto=squeeze_expansion_veto,
    )
    strategy = MeanReversion1mStrategy(config=config, timeframe_sec=300)
    strategy.set_regime("DOGEUSDT", "LOW_VOLATILITY")
    strategy.set_regime("BTCUSDT", "LOW_VOLATILITY")
    return strategy


def _run_sequence(
    *,
    symbol: str,
    closes: list[Decimal],
    squeeze_expansion_veto: dict | None,
) -> object:
    strategy = _make_strategy(squeeze_expansion_veto=squeeze_expansion_veto)
    last_signal = None
    for index, close in enumerate(closes):
        last_signal = strategy.on_bar(
            symbol,
            _make_bar(symbol, close, index),
            1_700_000_000_000 + (index + 1) * 300_000,
        )
    return last_signal


def test_narrow_squeeze_expansion_short_fade_trigger_is_rejected() -> None:
    """
    Hypothesis:
    A narrow squeeze that rapidly expands into an upper-band breakout should not be faded by MR.

    Why this matters:
    This is the breakout-from-squeeze trap class identified in the P1 MR review.

    Current expected buggy behavior:
    The SHORT passes because current MR only sees the active band touch, not the squeeze->expansion transition.

    What future repair should change:
    The signal must be vetoed with an explicit squeeze-expansion reason.
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
        squeeze_expansion_veto=_squeeze_veto_config(),
    )

    assert signal.signal_type == MRSignalType.NEUTRAL
    assert signal.why == "neutral:squeeze_expansion_veto:SHORT:0.0009->0.0041"


def test_narrow_squeeze_expansion_long_fade_trigger_is_rejected() -> None:
    """
    Hypothesis:
    The same squeeze->expansion trap exists symmetrically for lower-band breakdown fades.

    Why this matters:
    The package should stay symmetric when the same minimal signal geometry applies on both sides.

    Current expected buggy behavior:
    The LONG passes because there is no expansion-aware veto on lower-band fades.

    What future repair should change:
    Lower-band squeeze-breakdown fades should be vetoed by the same contract.
    """
    signal = _run_sequence(
        symbol="DOGEUSDT",
        closes=[
            Decimal("100"),
            Decimal("99.98"),
            Decimal("100.02"),
            Decimal("100.00"),
            Decimal("100.01"),
            Decimal("99.80"),
        ],
        squeeze_expansion_veto=_squeeze_veto_config(),
    )

    assert signal.signal_type == MRSignalType.NEUTRAL
    assert signal.why == "neutral:squeeze_expansion_veto:LONG:0.0005->0.0033"


def test_narrow_but_non_expanding_signal_is_still_allowed() -> None:
    """
    Hypothesis:
    Narrow bands alone should not be banned; the veto is about squeeze expansion, not narrowness itself.

    Why this matters:
    A blanket narrow-band ban would destroy valid MR fades and duplicate the wrong kind of global hardening.

    Current expected buggy behavior:
    None. This is the precision guard for the new veto.

    What future repair should change:
    A narrow signal with insufficient width expansion must still be allowed.
    """
    signal = _run_sequence(
        symbol="DOGEUSDT",
        closes=[
            Decimal("100"),
            Decimal("100.02"),
            Decimal("99.98"),
            Decimal("100.01"),
            Decimal("99.99"),
            Decimal("100.08"),
        ],
        squeeze_expansion_veto=_squeeze_veto_config(),
    )

    assert signal.signal_type == MRSignalType.SHORT
    assert "price_above_upper_bb" in signal.why


def test_wider_band_signal_is_unaffected_by_squeeze_veto() -> None:
    """
    Hypothesis:
    Once the current band is already wider than the configured post-squeeze scope, this veto should stand down.

    Why this matters:
    P2-B must stay a narrow breakout-from-squeeze block, not a general expansion ban.

    Current expected buggy behavior:
    None. This is the blast-radius guard for the new veto.

    What future repair should change:
    Wider-band fades outside the configured post-squeeze scope must remain on the old path.
    """
    signal = _run_sequence(
        symbol="DOGEUSDT",
        closes=[
            Decimal("100"),
            Decimal("100.02"),
            Decimal("99.98"),
            Decimal("100.01"),
            Decimal("99.99"),
            Decimal("100.35"),
        ],
        squeeze_expansion_veto=_squeeze_veto_config(),
    )

    assert signal.signal_type == MRSignalType.SHORT
    assert "price_above_upper_bb" in signal.why


def test_non_target_symbol_behavior_is_unchanged_without_veto_config() -> None:
    """
    Hypothesis:
    Symbols without an explicit squeeze-expansion contract must keep the current MR behavior.

    Why this matters:
    The package should not silently broaden its blast radius beyond configured symbols.

    Current expected buggy behavior:
    None. This is the configuration scoping guard for the package.

    What future repair should change:
    The same squeeze-style sequence should still pass when no veto is configured.
    """
    signal = _run_sequence(
        symbol="BTCUSDT",
        closes=[
            Decimal("100"),
            Decimal("100.03"),
            Decimal("99.97"),
            Decimal("100.02"),
            Decimal("99.98"),
            Decimal("100.25"),
        ],
        squeeze_expansion_veto=None,
    )

    assert signal.signal_type == MRSignalType.SHORT
    assert "price_above_upper_bb" in signal.why


def test_p2a_flat_low_short_hardening_reason_still_wins_when_no_previous_width_exists() -> None:
    """
    Hypothesis:
    P2-B must not break the existing P2-A DOGE guard or change its explicit reason.

    Why this matters:
    P2-B is additive and should not silently rewrite the already-closed DOGE hardening contract.

    Current expected buggy behavior:
    None. This is the coexistence guard between P2-A and P2-B.

    What future repair should change:
    When previous-width context is unavailable, the P2-A width hardening should still block with the same reason.
    """
    strategy = _make_strategy(
        squeeze_expansion_veto=_squeeze_veto_config(),
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
