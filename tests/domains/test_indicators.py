"""
Tests for Technical Indicators (Phase B2).

Tests Bollinger Bands, ATR, RSI calculations.
"""

import pytest
from decimal import Decimal

from apps.reference.domains.feature_engineering.indicators import (
    BollingerBands,
    compute_sma,
    compute_std,
    compute_bollinger_bands,
    compute_atr,
    compute_rsi,
    IndicatorState,
)


class TestSMA:
    """Tests for SMA calculation."""

    def test_sma_basic(self):
        """Test basic SMA calculation."""
        values = [Decimal("10"), Decimal("20"), Decimal("30")]
        sma = compute_sma(values, window=3)
        
        assert sma == Decimal("20")  # (10 + 20 + 30) / 3

    def test_sma_uses_last_n_values(self):
        """Test SMA uses only last N values."""
        values = [Decimal("5"), Decimal("10"), Decimal("20"), Decimal("30")]
        sma = compute_sma(values, window=3)
        
        # Should use last 3: 10, 20, 30
        assert sma == Decimal("20")

    def test_sma_insufficient_data(self):
        """Test SMA returns None with insufficient data."""
        values = [Decimal("10"), Decimal("20")]
        sma = compute_sma(values, window=5)
        
        assert sma is None


class TestStd:
    """Tests for Standard Deviation calculation."""

    def test_std_basic(self):
        """Test basic std calculation."""
        values = [Decimal("2"), Decimal("4"), Decimal("4"), Decimal("4"), Decimal("5"), Decimal("5"), Decimal("7"), Decimal("9")]
        std = compute_std(values, window=8)
        
        # Known std ≈ 2.0
        assert std is not None
        assert float(std) == pytest.approx(2.0, abs=0.01)

    def test_std_all_same(self):
        """Test std of identical values is 0."""
        values = [Decimal("5")] * 5
        std = compute_std(values, window=5)
        
        assert std == Decimal("0")

    def test_std_insufficient_data(self):
        """Test std returns None with insufficient data."""
        values = [Decimal("10")]
        std = compute_std(values, window=5)
        
        assert std is None


class TestBollingerBands:
    """Tests for Bollinger Bands calculation."""

    def test_bollinger_basic(self):
        """Test basic Bollinger Bands calculation."""
        # Create 20 values with mean 100 and some variance
        closes = [Decimal(str(100 + (i % 5) - 2)) for i in range(20)]
        
        bb = compute_bollinger_bands(closes, window=20, num_std=2.0)
        
        assert bb is not None
        assert bb.mid > 0
        assert bb.upper > bb.mid
        assert bb.lower < bb.mid
        assert bb.width > 0

    def test_bollinger_pct_b_at_lower(self):
        """Test %B when price at lower band."""
        closes = [Decimal("100")] * 19 + [Decimal("90")]
        bb = compute_bollinger_bands(closes, window=20, num_std=2.0, current_price=Decimal("90"))
        
        # Price below mean should have low %B
        assert bb is not None
        assert bb.pct_b < 0.5

    def test_bollinger_pct_b_at_upper(self):
        """Test %B when price at upper band."""
        closes = [Decimal("100")] * 19 + [Decimal("110")]
        bb = compute_bollinger_bands(closes, window=20, num_std=2.0, current_price=Decimal("115"))
        
        # Price above mean should have high %B
        assert bb is not None
        assert bb.pct_b > 0.5

    def test_bollinger_width_calculation(self):
        """Test width is calculated correctly."""
        closes = [Decimal(str(100 + i)) for i in range(20)]
        bb = compute_bollinger_bands(closes, window=20, num_std=2.0)
        
        assert bb is not None
        # Width = (upper - lower) / mid
        expected_width = float((bb.upper - bb.lower) / bb.mid)
        assert bb.width == pytest.approx(expected_width)

    def test_bollinger_insufficient_data(self):
        """Test returns None with insufficient data."""
        closes = [Decimal("100")] * 10
        bb = compute_bollinger_bands(closes, window=20)
        
        assert bb is None

    def test_bollinger_zero_std(self):
        """Test handles zero std (all same values)."""
        closes = [Decimal("100")] * 20
        bb = compute_bollinger_bands(closes, window=20)
        
        # Should handle gracefully - bands collapse to mid
        assert bb is not None
        assert bb.upper == bb.lower == bb.mid
        assert bb.width == 0.0
        assert bb.pct_b == 0.5


class TestBollingerBandsDataclass:
    """Tests for BollingerBands dataclass properties."""

    def test_is_price_above_upper(self):
        """Test is_price_above_upper property."""
        bb = BollingerBands(
            upper=Decimal("110"),
            lower=Decimal("90"),
            mid=Decimal("100"),
            width=0.2,
            pct_b=1.5,  # Above upper band
        )
        
        assert bb.is_price_above_upper is True
        assert bb.is_price_below_lower is False

    def test_is_price_below_lower(self):
        """Test is_price_below_lower property."""
        bb = BollingerBands(
            upper=Decimal("110"),
            lower=Decimal("90"),
            mid=Decimal("100"),
            width=0.2,
            pct_b=-0.2,  # Below lower band
        )
        
        assert bb.is_price_above_upper is False
        assert bb.is_price_below_lower is True


class TestATR:
    """Tests for ATR calculation."""

    def test_atr_basic(self):
        """Test basic ATR calculation."""
        # 15 bars of data
        highs = [Decimal("105")] * 15
        lows = [Decimal("95")] * 15
        closes = [Decimal("100")] * 15
        
        atr = compute_atr(highs, lows, closes, window=14)
        
        assert atr is not None
        # True Range is 10 for each bar (105 - 95)
        assert float(atr) == pytest.approx(10.0)

    def test_atr_with_gaps(self):
        """Test ATR includes gaps."""
        # Create data with a gap
        highs = [Decimal("100")] * 14 + [Decimal("110")]
        lows = [Decimal("95")] * 14 + [Decimal("105")]
        closes = [Decimal("98")] * 14 + [Decimal("108")]
        
        atr = compute_atr(highs, lows, closes, window=14)
        
        assert atr is not None
        # Should be higher due to gap
        assert atr > Decimal("5")

    def test_atr_insufficient_data(self):
        """Test ATR returns None with insufficient data."""
        highs = [Decimal("105")] * 10
        lows = [Decimal("95")] * 10
        closes = [Decimal("100")] * 10
        
        atr = compute_atr(highs, lows, closes, window=14)
        
        assert atr is None


class TestRSI:
    """Tests for RSI calculation."""

    def test_rsi_all_gains(self):
        """Test RSI with all gains is 100."""
        closes = [Decimal(str(100 + i)) for i in range(20)]
        rsi = compute_rsi(closes, window=14)
        
        assert rsi is not None
        assert rsi == Decimal("100")

    def test_rsi_all_losses(self):
        """Test RSI with all losses is 0."""
        closes = [Decimal(str(100 - i)) for i in range(20)]
        rsi = compute_rsi(closes, window=14)
        
        assert rsi is not None
        assert float(rsi) == pytest.approx(0.0, abs=0.01)

    def test_rsi_mixed(self):
        """Test RSI with mixed gains/losses."""
        # Alternate up and down
        closes = [Decimal("100")]
        for i in range(20):
            if i % 2 == 0:
                closes.append(closes[-1] + Decimal("1"))
            else:
                closes.append(closes[-1] - Decimal("0.5"))
        
        rsi = compute_rsi(closes, window=14)
        
        assert rsi is not None
        # More gains than losses, should be > 50
        assert rsi > Decimal("50")

    def test_rsi_insufficient_data(self):
        """Test RSI returns None with insufficient data."""
        closes = [Decimal("100")] * 10
        rsi = compute_rsi(closes, window=14)
        
        assert rsi is None


class TestIndicatorState:
    """Tests for IndicatorState container."""

    def test_indicator_state_init(self):
        """Test indicator state initialization."""
        state = IndicatorState(symbol="BTCUSDT", timeframe_sec=60)
        
        assert state.symbol == "BTCUSDT"
        assert state.timeframe_sec == 60
        assert state.bb is None
        assert state.atr is None
        assert state.rsi is None

    def test_indicator_state_update_bollinger(self):
        """Test updating Bollinger Bands."""
        state = IndicatorState(symbol="BTCUSDT", timeframe_sec=60, bb_window=20)
        
        closes = [Decimal(str(100 + (i % 5) - 2)) for i in range(25)]
        state.update_bollinger(closes)
        
        assert state.has_bollinger is True
        assert state.bb is not None

    def test_indicator_state_update_atr(self):
        """Test updating ATR."""
        state = IndicatorState(symbol="BTCUSDT", timeframe_sec=60, atr_window=14)
        
        highs = [Decimal("105")] * 20
        lows = [Decimal("95")] * 20
        closes = [Decimal("100")] * 20
        
        state.update_atr(highs, lows, closes)
        
        assert state.has_atr is True
        assert state.atr is not None

    def test_indicator_state_bb_width_pct(self):
        """Test bb_width_pct property."""
        state = IndicatorState(symbol="BTCUSDT", timeframe_sec=60)
        
        # No BB yet
        assert state.bb_width_pct == 0.0
        
        # Calculate BB
        closes = [Decimal(str(100 + (i % 10) - 5)) for i in range(25)]
        state.update_bollinger(closes)
        
        assert state.bb_width_pct > 0

    def test_indicator_state_band_position(self):
        """Test band position properties."""
        state = IndicatorState(symbol="BTCUSDT", timeframe_sec=60)
        
        # No BB - should be False
        assert state.is_price_at_lower_band is False
        assert state.is_price_at_upper_band is False
        
        # Create BB with price below lower
        closes = [Decimal("100")] * 19 + [Decimal("80")]
        state.update_bollinger(closes, current_price=Decimal("75"))
        
        # Depends on calculated bands, but should be below
        assert state.bb is not None
