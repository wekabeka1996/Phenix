"""
Unit Tests for Pillar Indicators — Aurora Phase 9.

Tests the pure functions in pillar_indicators.py:
- normalize_to_pm1
- compute_roc / compute_tactician
- compute_linreg_slope / compute_adx / compute_operator
- compute_sma / compute_strategist
- aggregate_pillars
"""

import math
import pytest
from collections import deque

from apps.reference.domains.feature_engineering.pillar_indicators import (
    normalize_to_pm1,
    compute_roc,
    compute_tactician,
    compute_linreg_slope,
    compute_adx,
    compute_operator,
    compute_sma,
    compute_strategist,
    aggregate_pillars,
)
from apps.reference.domains.feature_engineering.types import PillarState


# =============================================================================
# normalize_to_pm1
# =============================================================================

class TestNormalize:
    def test_zero(self):
        assert normalize_to_pm1(0.0) == 0.0

    def test_positive(self):
        val = normalize_to_pm1(1.0, sensitivity=1.0)
        assert 0.7 < val < 0.8  # tanh(1) ≈ 0.7616

    def test_negative(self):
        val = normalize_to_pm1(-1.0, sensitivity=1.0)
        assert -0.8 < val < -0.7

    def test_symmetry(self):
        pos = normalize_to_pm1(0.5, sensitivity=3.0)
        neg = normalize_to_pm1(-0.5, sensitivity=3.0)
        assert abs(pos + neg) < 1e-10

    def test_saturation(self):
        val = normalize_to_pm1(10.0, sensitivity=3.0)
        assert val > 0.999  # tanh(30) ≈ 1.0

    def test_nan_returns_zero(self):
        assert normalize_to_pm1(float('nan')) == 0.0

    def test_inf_returns_zero(self):
        assert normalize_to_pm1(float('inf')) == 0.0

    def test_high_sensitivity(self):
        val = normalize_to_pm1(0.1, sensitivity=10.0)
        assert val > 0.7  # tanh(1.0) ≈ 0.7616

    def test_low_sensitivity(self):
        val = normalize_to_pm1(0.1, sensitivity=1.0)
        assert val < 0.15  # tanh(0.1) ≈ 0.0997


# =============================================================================
# ROC / Tactician
# =============================================================================

class TestROC:
    def test_basic_roc(self):
        closes = [100.0] * 14 + [110.0]  # 15 bars, period=14
        roc = compute_roc(closes, period=14)
        assert roc == pytest.approx(0.10, abs=1e-6)  # (110 - 100) / 100

    def test_negative_roc(self):
        closes = [100.0] * 14 + [90.0]
        roc = compute_roc(closes, period=14)
        assert roc == pytest.approx(-0.10, abs=1e-6)

    def test_insufficient_data(self):
        closes = [100.0] * 10
        assert compute_roc(closes, period=14) is None

    def test_zero_prev_close(self):
        closes = [0.0] * 14 + [100.0]
        assert compute_roc(closes, period=14) is None

    def test_tactician_normalized(self):
        closes = [100.0] * 14 + [105.0]
        val = compute_tactician(closes, roc_period=14, sensitivity=3.0)
        assert val is not None
        assert -1.0 <= val <= 1.0
        assert val > 0  # Positive ROC → positive tactician

    def test_tactician_none_on_insufficient(self):
        closes = [100.0] * 5
        assert compute_tactician(closes, roc_period=14) is None


# =============================================================================
# LinReg Slope
# =============================================================================

class TestLinRegSlope:
    def test_upward_trend(self):
        closes = list(range(100, 120))
        slope = compute_linreg_slope(closes, period=20)
        assert slope is not None
        assert slope > 0

    def test_downward_trend(self):
        closes = list(range(120, 100, -1))
        slope = compute_linreg_slope(closes, period=20)
        assert slope is not None
        assert slope < 0

    def test_flat(self):
        closes = [100.0] * 20
        slope = compute_linreg_slope(closes, period=20)
        assert slope is not None
        assert abs(slope) < 1e-10

    def test_insufficient_data(self):
        closes = [100.0] * 5
        assert compute_linreg_slope(closes, period=20) is None


# =============================================================================
# ADX
# =============================================================================

class TestADX:
    def test_strong_trend(self):
        # Strong uptrend: each bar higher
        n = 60
        highs = [100 + i * 2.0 for i in range(n)]
        lows = [99 + i * 2.0 for i in range(n)]
        closes = [99.5 + i * 2.0 for i in range(n)]
        adx = compute_adx(highs, lows, closes, period=14)
        assert adx is not None
        assert adx > 20  # Should be a strong trend

    def test_sideways(self):
        # Oscillating — weak trend
        n = 60
        highs = [101.0 + (i % 3) for i in range(n)]
        lows = [99.0 - (i % 3) for i in range(n)]
        closes = [100.0 + (0.5 if i % 2 == 0 else -0.5) for i in range(n)]
        adx = compute_adx(highs, lows, closes, period=14)
        assert adx is not None
        # ADX should be relatively low (no clear trend)

    def test_insufficient_data(self):
        highs = [100.0] * 10
        lows = [99.0] * 10
        closes = [99.5] * 10
        assert compute_adx(highs, lows, closes, period=14) is None

    def test_mismatched_lengths(self):
        highs = [100.0] * 60
        lows = [99.0] * 59  # One short
        closes = [99.5] * 60
        assert compute_adx(highs, lows, closes, period=14) is None


# =============================================================================
# Operator (LinReg + ADX)
# =============================================================================

class TestOperator:
    def test_strong_uptrend(self):
        n = 60
        highs = [100 + i * 1.5 for i in range(n)]
        lows = [99 + i * 1.5 for i in range(n)]
        closes = [99.5 + i * 1.5 for i in range(n)]
        val = compute_operator(closes, highs, lows)
        assert val is not None
        assert -1.0 <= val <= 1.0
        assert val > 0  # Upward trend

    def test_insufficient_data(self):
        closes = [100.0] * 10
        highs = [101.0] * 10
        lows = [99.0] * 10
        assert compute_operator(closes, highs, lows) is None


# =============================================================================
# SMA / Strategist
# =============================================================================

class TestSMA:
    def test_basic_sma(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert compute_sma(values, period=5) == pytest.approx(3.0)

    def test_insufficient_data(self):
        values = [1.0, 2.0]
        assert compute_sma(values, period=5) is None


class TestStrategist:
    def test_above_sma(self):
        # Price trending up, well above SMA(10)
        closes = list(range(1, 21))  # 1 to 20
        val = compute_strategist(closes, sma_period=10, sensitivity=3.0)
        assert val is not None
        assert val > 0  # Price above SMA

    def test_below_sma(self):
        # Price trending down
        closes = list(range(20, 0, -1))  # 20 to 1
        val = compute_strategist(closes, sma_period=10, sensitivity=3.0)
        assert val is not None
        assert val < 0  # Price below SMA

    def test_at_sma(self):
        # Flat price = at SMA
        closes = [100.0] * 30
        val = compute_strategist(closes, sma_period=10, sensitivity=3.0)
        assert val is not None
        assert abs(val) < 0.01  # Very close to zero

    def test_insufficient_data(self):
        closes = [100.0] * 5
        assert compute_strategist(closes, sma_period=200) is None


# =============================================================================
# Aggregate Pillars
# =============================================================================

class TestAggregate:
    def test_basic(self):
        result = aggregate_pillars(
            0.5, 0.3, -0.2,
            {'tactician': 0.3, 'operator': 0.4, 'strategist': 0.3},
        )
        expected = 0.5 * 0.3 + 0.3 * 0.4 + (-0.2) * 0.3
        assert result == pytest.approx(expected, abs=1e-10)

    def test_none_pillar_returns_none(self):
        assert aggregate_pillars(None, 0.3, 0.5, {'tactician': 0.3, 'operator': 0.4, 'strategist': 0.3}) is None
        assert aggregate_pillars(0.5, None, 0.5, {'tactician': 0.3, 'operator': 0.4, 'strategist': 0.3}) is None
        assert aggregate_pillars(0.5, 0.3, None, {'tactician': 0.3, 'operator': 0.4, 'strategist': 0.3}) is None

    def test_all_zero(self):
        result = aggregate_pillars(0.0, 0.0, 0.0, {'tactician': 0.3, 'operator': 0.4, 'strategist': 0.3})
        assert result == pytest.approx(0.0)

    def test_default_weights(self):
        # When keys missing, should use defaults (0.3, 0.4, 0.3)
        result = aggregate_pillars(1.0, 1.0, 1.0, {})
        expected = 1.0 * 0.3 + 1.0 * 0.4 + 1.0 * 0.3
        assert result == pytest.approx(expected)


# =============================================================================
# PillarState
# =============================================================================

class TestPillarState:
    def test_initial_state(self):
        state = PillarState()
        assert state.all_ready is False
        assert state.tactician is None
        assert state.operator is None
        assert state.strategist is None
        assert state.pillar_sum is None

    def test_all_ready(self):
        state = PillarState()
        state.tactician_ready = True
        state.operator_ready = True
        state.strategist_ready = True
        assert state.all_ready is True

    def test_partial_ready(self):
        state = PillarState()
        state.tactician_ready = True
        state.operator_ready = True
        # strategist_ready = False
        assert state.all_ready is False

    def test_deque_append(self):
        state = PillarState()
        for i in range(100):
            state.m15_closes.append(float(i))
        assert len(state.m15_closes) == 100

    def test_backfill_result(self):
        """Test BackfillResult properties."""
        from apps.reference.domains.feature_engineering.pillar_backfill import (
            BackfillResult, CandleBar,
        )
        candles = [
            CandleBar(open_time_ms=0, open=100, high=105, low=95, close=102, volume=1000),
            CandleBar(open_time_ms=1, open=102, high=106, low=96, close=104, volume=1100),
        ]
        result = BackfillResult(symbol="BTCUSDT", timeframe_sec=86400, candles=candles,
                                success=True, fetched_count=2)
        assert result.closes == [102, 104]
        assert result.highs == [105, 106]
        assert result.lows == [95, 96]
