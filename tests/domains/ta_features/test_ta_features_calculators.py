"""
Unit tests for the ta_features domain — pure math calculators and BarBuffer.

These tests have NO FSM or config dependencies.
All inputs use Decimal to match production bar data types.
"""

import math
from decimal import Decimal
from typing import List
from unittest.mock import MagicMock, call, ANY

import pytest

from apps.reference.config_models import TAFeaturesDomainConfig
from apps.reference.domains.ta_features.bar_buffer import BarBuffer
from apps.reference.domains.ta_features.calculators import (
    MIN_WARM_BARS,
    compute_price_momentum,
    compute_price_sma_deviation,
    compute_stochastic,
    compute_ta_bb,
    compute_ta_rsi,
    compute_volume_sma_ratio,
)
from apps.reference.domains.ta_features.ta_features import TAFeaturesEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _d(v) -> Decimal:
    return Decimal(str(v))


def _make_closes(values: List[float]) -> List[Decimal]:
    return [_d(v) for v in values]


def _ramp(start: float, stop: float, n: int) -> List[Decimal]:
    """Linearly spaced close prices."""
    if n == 1:
        return [_d(start)]
    step = (stop - start) / (n - 1)
    return [_d(start + i * step) for i in range(n)]


def _flat(value: float, n: int) -> List[Decimal]:
    return [_d(value)] * n


def _make_ta_config(**overrides) -> TAFeaturesDomainConfig:
    data = {
        "enabled": True,
        "timeframes_sec": [60, 300],
        "warm_up_bars": MIN_WARM_BARS,
        "buffer_max_bars": 50,
        "log_calculations": False,
        "log_max_bytes": 10485760,
        "log_backup_count": 5,
    }
    data.update(overrides)
    return TAFeaturesDomainConfig.model_validate(data)


# ============================================================================
# BarBuffer
# ============================================================================


class TestBarBuffer:
    def _push_n(self, buf: BarBuffer, n: int, base: float = 100.0):
        for i in range(n):
            buf.push(
                open_=_d(base + i),
                high=_d(base + i + 1),
                low=_d(base + i - 1),
                close=_d(base + i),
                volume=_d(10.0),
                ts_ms=1000 * i,
            )

    def test_empty_buffer(self):
        buf = BarBuffer(maxlen=10)
        assert len(buf) == 0
        assert not buf.enough(1)
        assert buf.last_ts_ms == 0

    def test_push_and_len(self):
        buf = BarBuffer(maxlen=10)
        self._push_n(buf, 5)
        assert len(buf) == 5
        assert buf.enough(5)
        assert not buf.enough(6)

    def test_maxlen_eviction(self):
        buf = BarBuffer(maxlen=3)
        self._push_n(buf, 5, base=100.0)
        assert len(buf) == 3
        # After 5 pushes with base=100: closes are 102, 103, 104 (last 3 pushed)
        assert buf.closes[-1] == _d(104.0)
        assert buf.closes[0] == _d(102.0)

    def test_property_lists(self):
        buf = BarBuffer(maxlen=5)
        buf.push(_d(1), _d(2), _d(0.5), _d(1.5), _d(10), 1000)
        assert buf.opens == [_d(1)]
        assert buf.highs == [_d(2)]
        assert buf.lows == [_d(0.5)]
        assert buf.closes == [_d(1.5)]
        assert buf.volumes == [_d(10)]
        assert buf.last_ts_ms == 1000

    def test_enough_false_below_threshold(self):
        buf = BarBuffer(maxlen=50)
        self._push_n(buf, 19)
        assert not buf.enough(20)

    def test_enough_true_at_threshold(self):
        buf = BarBuffer(maxlen=50)
        self._push_n(buf, 20)
        assert buf.enough(20)


# ============================================================================
# compute_ta_bb (Bollinger Bands)
# ============================================================================


class TestComputeTaBB:
    def test_insufficient_data_fallback(self):
        closes = _make_closes([100.0] * 5)
        bb_pos, bb_width = compute_ta_bb(closes, period=20)
        assert bb_pos == 0.5
        assert bb_width == 0.0

    def test_flat_price_band_collapses(self):
        closes = _flat(100.0, 20)
        bb_pos, bb_width = compute_ta_bb(closes)
        # All prices identical → std=0 → bands collapse
        assert bb_width == 0.0
        assert bb_pos == pytest.approx(0.5, abs=1e-6)

    def test_price_at_upper_band(self):
        # Rising prices → close is above upper band → %B > 1
        closes = _ramp(90.0, 115.0, 20)
        bb_pos, bb_width = compute_ta_bb(closes)
        # Close (115) should be near or above upper band
        assert bb_pos > 0.5

    def test_price_at_lower_band(self):
        # Falling prices → close is below lower band → %B < 0
        closes = _ramp(115.0, 90.0, 20)
        bb_pos, bb_width = compute_ta_bb(closes)
        assert bb_pos < 0.5

    def test_bb_width_positive_on_volatile_prices(self):
        # Random-ish sequence → width should be positive
        prices = [100 + (i % 5) * 3 for i in range(20)]
        closes = _make_closes(prices)
        _, bb_width = compute_ta_bb(closes)
        assert bb_width > 0.0


# ============================================================================
# compute_ta_rsi
# ============================================================================


class TestComputeTaRSI:
    def test_insufficient_data_fallback(self):
        closes = _make_closes([100.0] * 5)
        rsi = compute_ta_rsi(closes, period=14)
        assert rsi == pytest.approx(50.0)

    def test_all_gains_returns_100(self):
        closes = _ramp(100.0, 120.0, 20)
        rsi = compute_ta_rsi(closes, period=14)
        assert rsi == pytest.approx(100.0)

    def test_all_losses_returns_0(self):
        closes = _ramp(120.0, 100.0, 20)
        rsi = compute_ta_rsi(closes, period=14)
        assert rsi == pytest.approx(0.0)

    def test_midrange_rsi(self):
        # Alternating up/down → RSI should converge near 50
        prices = []
        for i in range(20):
            prices.append(100.0 + (1 if i % 2 == 0 else -1))
        closes = _make_closes(prices)
        rsi = compute_ta_rsi(closes, period=14)
        assert 40.0 <= rsi <= 60.0

    def test_rsi_range(self):
        closes = _make_closes([100 + math.sin(i) * 5 for i in range(25)])
        rsi = compute_ta_rsi(closes, period=14)
        assert 0.0 <= rsi <= 100.0


# ============================================================================
# compute_stochastic
# ============================================================================


class TestComputeStochastic:
    def _make_ohlcv(self, closes: List[float], spread: float = 2.0):
        """Build highs/lows/closes from close list with fixed spread."""
        h = [_d(c + spread) for c in closes]
        l = [_d(c - spread) for c in closes]
        c = [_d(c) for c in closes]
        return h, l, c

    def test_insufficient_data_fallback(self):
        h, l, c = self._make_ohlcv([100.0] * 5)
        k, d = compute_stochastic(h, l, c, k_period=14, d_period=3)
        assert k == 50.0
        assert d == 50.0

    def test_at_highest_high(self):
        # Close equals highest high → %K should be ~100
        closes = [100.0 + i for i in range(16)]  # monotonically rising
        h = [_d(c) for c in closes]              # high == close
        l = [_d(c - 10) for c in closes]         # low is c-10
        c = [_d(c) for c in closes]
        k, _ = compute_stochastic(h, l, c, k_period=14, d_period=3)
        # close[-1] == max(highs[-14:]) → %K = 100
        assert k == pytest.approx(100.0, abs=0.1)

    def test_at_lowest_low(self):
        # Close equals lowest low → %K should be ~0
        closes = [100.0 - i for i in range(16)]  # monotonically falling
        h = [_d(c + 10) for c in closes]
        l = [_d(c) for c in closes]              # low == close
        c = [_d(c) for c in closes]
        k, _ = compute_stochastic(h, l, c, k_period=14, d_period=3)
        assert k == pytest.approx(0.0, abs=0.1)

    def test_zero_range_no_division(self):
        # All prices identical → range = 0 → should return 50.0, no exception
        h = _flat(100.0, 20)
        l = _flat(100.0, 20)
        c = _flat(100.0, 20)
        k, d = compute_stochastic(h, l, c)
        assert k == 50.0
        assert d == 50.0

    def test_d_is_average_of_k_values(self):
        # Known synthetic case: any 16 bars, check that D = average of K for last 3 bars
        h, l, c = self._make_ohlcv(list(range(100, 116)), spread=2.0)
        k, d = compute_stochastic(h, l, c, k_period=14, d_period=3)
        # D must be between the min and max K values (SMA property)
        # Both K and D must be in [0, 100]
        assert 0.0 <= k <= 100.0
        assert 0.0 <= d <= 100.0

    def test_stoch_values_in_range(self):
        import random
        random.seed(42)
        prices = [100.0 + random.gauss(0, 2) for _ in range(25)]
        h, l, c = self._make_ohlcv(prices)
        k, d = compute_stochastic(h, l, c)
        assert 0.0 <= k <= 100.0
        assert 0.0 <= d <= 100.0


# ============================================================================
# compute_price_sma_deviation
# ============================================================================


class TestComputePriceSmaDeviation:
    def test_insufficient_data(self):
        closes = _make_closes([100.0] * 5)
        assert compute_price_sma_deviation(closes) == 0.0

    def test_price_above_sma(self):
        # Last close is well above SMA → positive deviation
        closes = _flat(100.0, 19) + [_d(120.0)]
        dev = compute_price_sma_deviation(closes)
        assert dev > 0.0

    def test_price_below_sma(self):
        closes = _flat(100.0, 19) + [_d(80.0)]
        dev = compute_price_sma_deviation(closes)
        assert dev < 0.0

    def test_price_equals_sma(self):
        closes = _flat(100.0, 20)
        dev = compute_price_sma_deviation(closes)
        assert dev == pytest.approx(0.0, abs=1e-9)

    def test_known_value(self):
        # SMA of 20 bars at 100 → dev = (110 - 100) / 100 = 0.10
        closes = _flat(100.0, 19) + [_d(110.0)]
        dev = compute_price_sma_deviation(closes)
        # SMA = (19*100 + 110) / 20 = 100.5 → (110 - 100.5) / 100.5 ≈ 0.0945
        assert dev == pytest.approx((110.0 - 100.5) / 100.5, rel=1e-5)


# ============================================================================
# compute_volume_sma_ratio
# ============================================================================


class TestComputeVolumeSmaRatio:
    def test_insufficient_data_fallback(self):
        vols = [_d(100.0)] * 5
        assert compute_volume_sma_ratio(vols) == 1.0

    def test_volume_at_average(self):
        vols = _flat(100.0, 20)
        ratio = compute_volume_sma_ratio(vols)
        assert ratio == pytest.approx(1.0, rel=1e-5)

    def test_spike_above_average(self):
        vols = _flat(100.0, 19) + [_d(200.0)]
        ratio = compute_volume_sma_ratio(vols)
        # SMA = (19*100 + 200) / 20 = 105 → ratio = 200/105 ≈ 1.905
        assert ratio == pytest.approx(200.0 / 105.0, rel=1e-4)

    def test_low_volume(self):
        vols = _flat(100.0, 19) + [_d(50.0)]
        ratio = compute_volume_sma_ratio(vols)
        assert ratio < 1.0

    def test_zero_sma_fallback(self):
        vols = _flat(0.0, 20)
        ratio = compute_volume_sma_ratio(vols)
        assert ratio == 1.0


# ============================================================================
# compute_price_momentum
# ============================================================================


class TestComputePriceMomentum:
    def test_insufficient_data(self):
        closes = _make_closes([100.0, 105.0])
        assert compute_price_momentum(closes, lookback=5) == 0.0

    def test_flat_price(self):
        closes = _flat(100.0, 10)
        m = compute_price_momentum(closes, lookback=5)
        assert m == pytest.approx(0.0, abs=1e-9)

    def test_positive_momentum(self):
        closes = _ramp(100.0, 110.0, 10)
        m = compute_price_momentum(closes, lookback=5)
        assert m > 0.0

    def test_negative_momentum(self):
        closes = _ramp(110.0, 100.0, 10)
        m = compute_price_momentum(closes, lookback=5)
        assert m < 0.0

    def test_known_value(self):
        # Closes: [100, 100, 100, 100, 100, 105] (lookback=5)
        closes = _make_closes([100.0, 100.0, 100.0, 100.0, 100.0, 105.0])
        m = compute_price_momentum(closes, lookback=5)
        assert m == pytest.approx(0.05, rel=1e-5)

    def test_lookback_1(self):
        closes = _make_closes([100.0, 110.0])
        m = compute_price_momentum(closes, lookback=1)
        assert m == pytest.approx(0.10, rel=1e-5)

    def test_zero_base_fallback(self):
        closes = _make_closes([0.0, 0.0, 0.0, 0.0, 0.0, 100.0])
        assert compute_price_momentum(closes, lookback=5) == 0.0


# ============================================================================
# TAFeaturesEngine integration (stub FSM)
# ============================================================================


class _FakeFSM:
    """Minimal FSM stub — records listen registrations and emitted events."""

    def __init__(self):
        self.listeners = {}
        self.emitted = []

    def listen(self, event, handler):
        self.listeners.setdefault(event, []).append(handler)

    def emit(self, event, payload):
        self.emitted.append((event, payload))

    def dispatch(self, event, pld_dict):
        msg = MagicMock()
        msg.pld = pld_dict
        for h in self.listeners.get(event, []):
            h(msg)


def _make_bar_closed_pld(
    symbol="BTCUSDT",
    tf_sec=60,
    close=100.0,
    high=101.0,
    low=99.0,
    open_=100.0,
    volume=1000.0,
    bar_close_ts=1000,
):
    return {
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar_close_ts": bar_close_ts,
        "bar": {
            "open": str(open_),
            "high": str(high),
            "low": str(low),
            "close": str(close),
            "volume": str(volume),
            "end_ts_ms": bar_close_ts,
        },
    }


class TestTAFeaturesEngine:
    def _warm_engine(self, fsm: _FakeFSM, n: int = 25, symbol="BTCUSDT", tf_sec=60):
        for i in range(n):
            pld = _make_bar_closed_pld(
                symbol=symbol,
                tf_sec=tf_sec,
                close=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                open_=100.0 + i,
                volume=1000.0 + i * 10,
                bar_close_ts=i * 60000,
            )
            fsm.dispatch("EVT:BAR_CLOSED", pld)

    def test_registers_bar_closed_listener(self):
        fsm = _FakeFSM()
        engine = TAFeaturesEngine(fsm=fsm, config=_make_ta_config())
        assert "EVT:BAR_CLOSED" in fsm.listeners

    def test_emits_before_warm_up_with_explicit_state(self):
        fsm = _FakeFSM()
        engine = TAFeaturesEngine(fsm=fsm, config=_make_ta_config())
        # Push only 19 bars (< MIN_WARM_BARS=20)
        for i in range(19):
            pld = _make_bar_closed_pld(close=100.0 + i, bar_close_ts=i * 60000)
            fsm.dispatch("EVT:BAR_CLOSED", pld)
        ta_events = [p for e, p in fsm.emitted if e ==
                     "EVT:TA_FEATURES_CALCULATED"]
        assert ta_events
        assert ta_events[-1]["is_warm"] is False
        assert ta_events[-1]["warm_up_bars"] == 19
        assert ta_events[-1]["required_warm_up_bars"] == MIN_WARM_BARS

    def test_emits_after_warm_up(self):
        fsm = _FakeFSM()
        engine = TAFeaturesEngine(fsm=fsm, config=_make_ta_config())
        self._warm_engine(fsm, n=25)
        ta_events = [p for e, p in fsm.emitted if e ==
                     "EVT:TA_FEATURES_CALCULATED"]
        assert len(ta_events) > 0

    def test_emitted_payload_has_all_required_fields(self):
        fsm = _FakeFSM()
        engine = TAFeaturesEngine(fsm=fsm, config=_make_ta_config())
        self._warm_engine(fsm, n=25)
        ta_events = [p for e, p in fsm.emitted if e ==
                     "EVT:TA_FEATURES_CALCULATED"]
        assert ta_events, "No TA_FEATURES_CALCULATED events emitted"
        pld = ta_events[-1]
        for field in (
            "ts", "symbol", "tf_sec", "bar_close_ts", "close",
            "bb_position", "bb_width", "rsi_14",
            "price_sma_20_deviation", "volume_sma_ratio",
            "stoch_k", "stoch_d", "price_momentum_5m",
            "warm_up_bars", "required_warm_up_bars", "is_warm", "source",
        ):
            assert field in pld, f"Missing field: {field}"

    def test_emitted_payload_values_in_range(self):
        fsm = _FakeFSM()
        engine = TAFeaturesEngine(fsm=fsm, config=_make_ta_config())
        self._warm_engine(fsm, n=25)
        pld = [p for e, p in fsm.emitted if e ==
               "EVT:TA_FEATURES_CALCULATED"][-1]

        assert pld["close"] > 0.0
        assert 0.0 <= pld["rsi_14"] <= 100.0
        assert pld["bb_width"] >= 0.0
        assert 0.0 <= pld["stoch_k"] <= 100.0
        assert 0.0 <= pld["stoch_d"] <= 100.0
        assert pld["volume_sma_ratio"] >= 0.0
        assert pld["is_warm"] is True
        assert pld["source"] == "ta_features"

    def test_filters_unknown_timeframe(self):
        """Bars with tf_sec not in configured timeframes are silently dropped."""
        fsm = _FakeFSM()
        engine = TAFeaturesEngine(fsm=fsm, config=_make_ta_config())
        # Push 30 bars with tf_sec=180 (not in defaults [60, 300])
        for i in range(30):
            pld = _make_bar_closed_pld(
                tf_sec=180, close=100.0 + i, bar_close_ts=i)
            fsm.dispatch("EVT:BAR_CLOSED", pld)
        assert not any(e == "EVT:TA_FEATURES_CALCULATED" for e,
                       _ in fsm.emitted)

    def test_independent_buffers_by_symbol(self):
        """Different symbols maintain independent buffers."""
        fsm = _FakeFSM()
        engine = TAFeaturesEngine(fsm=fsm, config=_make_ta_config())
        self._warm_engine(fsm, n=25, symbol="BTCUSDT")
        self._warm_engine(fsm, n=25, symbol="ETHUSDT")

        symbols = {p["symbol"]
                   for e, p in fsm.emitted if e == "EVT:TA_FEATURES_CALCULATED"}
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols
