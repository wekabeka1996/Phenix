"""
Technical Indicators for Bar-Based Strategies.

Phase B2: Bollinger Bands and other indicators for 1m Mean Reversion.

These indicators work with OHLCV bars (from BarResampler) and provide
signals for bar-based strategies.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List, Tuple
import math


@dataclass
class BollingerBands:
    """
    Bollinger Bands values for a single bar.

    Attributes:
        upper: Upper band (mid + num_std * std)
        lower: Lower band (mid - num_std * std)
        mid: Middle band (SMA)
        width: Band width as percentage of mid ((upper - lower) / mid)
        pct_b: %B indicator ((close - lower) / (upper - lower))
    """
    upper: Decimal
    lower: Decimal
    mid: Decimal
    width: float
    pct_b: float

    @property
    def is_price_above_upper(self) -> bool:
        """True if %B > 1 (price above upper band)."""
        return self.pct_b > 1.0

    @property
    def is_price_below_lower(self) -> bool:
        """True if %B < 0 (price below lower band)."""
        return self.pct_b < 0.0


def compute_sma(values: List[Decimal], window: int) -> Optional[Decimal]:
    """
    Compute Simple Moving Average.

    Args:
        values: List of values (oldest first)
        window: Window size

    Returns:
        SMA value or None if insufficient data
    """
    if len(values) < window:
        return None

    window_values = values[-window:]
    return sum(window_values) / Decimal(window)


def compute_std(values: List[Decimal], window: int, mean: Optional[Decimal] = None) -> Optional[Decimal]:
    """
    Compute Standard Deviation.

    Args:
        values: List of values (oldest first)
        window: Window size
        mean: Pre-computed mean (optional, will calculate if not provided)

    Returns:
        Standard deviation or None if insufficient data
    """
    if len(values) < window:
        return None

    window_values = values[-window:]

    if mean is None:
        mean = sum(window_values) / Decimal(window)

    # Variance
    variance = sum((x - mean) ** 2 for x in window_values) / Decimal(window)

    # Standard deviation
    return Decimal(str(math.sqrt(float(variance))))


def compute_bollinger_bands(
    closes: List[Decimal],
    window: int = 20,
    num_std: float = 2.0,
    current_price: Optional[Decimal] = None,
) -> Optional[BollingerBands]:
    """
    Compute Bollinger Bands from close prices.

    Args:
        closes: List of close prices (oldest first)
        window: Window size for SMA (default 20)
        num_std: Number of standard deviations for bands (default 2.0)
        current_price: Current price for %B calculation (default: last close)

    Returns:
        BollingerBands dataclass or None if insufficient data

    Example:
        closes = [Decimal("100"), Decimal("102"), ...]  # at least 'window' values
        bb = compute_bollinger_bands(closes, window=20, num_std=2.0)
        if bb:
            print(f"Upper: {bb.upper}, Lower: {bb.lower}, Mid: {bb.mid}")
    """
    if len(closes) < window:
        return None

    # SMA (middle band)
    mid = compute_sma(closes, window)
    if mid is None:
        return None

    # Standard deviation
    std = compute_std(closes, window, mean=mid)
    if std is None or std == 0:
        # Zero std means all values are the same - bands collapse
        return BollingerBands(
            upper=mid,
            lower=mid,
            mid=mid,
            width=0.0,
            pct_b=0.5,  # Price at middle
        )

    # Upper and lower bands
    std_decimal = Decimal(str(num_std))
    upper = mid + std_decimal * std
    lower = mid - std_decimal * std

    # Width as percentage
    width = float((upper - lower) / mid) if mid != 0 else 0.0

    # %B indicator
    price = current_price if current_price is not None else closes[-1]
    band_range = upper - lower
    if band_range != 0:
        pct_b = float((price - lower) / band_range)
    else:
        pct_b = 0.5

    return BollingerBands(
        upper=upper,
        lower=lower,
        mid=mid,
        width=width,
        pct_b=pct_b,
    )


def compute_atr(
    highs: List[Decimal],
    lows: List[Decimal],
    closes: List[Decimal],
    window: int = 14,
) -> Optional[Decimal]:
    """
    Compute Average True Range (ATR).

    Args:
        highs: List of high prices (oldest first)
        lows: List of low prices (oldest first)
        closes: List of close prices (oldest first)
        window: Window size for averaging (default 14)

    Returns:
        ATR value or None if insufficient data
    """
    n = len(closes)
    if n < window + 1:  # Need one extra for prev close
        return None

    if len(highs) != n or len(lows) != n:
        return None

    # Calculate True Range for last 'window' bars
    true_ranges = []
    for i in range(n - window, n):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]

        # True Range = max(high - low, |high - prev_close|, |low - prev_close|)
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        true_ranges.append(tr)

    # Average True Range
    return sum(true_ranges) / Decimal(len(true_ranges))


def compute_rsi(
    closes: List[Decimal],
    window: int = 14,
) -> Optional[Decimal]:
    """
    Compute Relative Strength Index (RSI).

    Args:
        closes: List of close prices (oldest first)
        window: Window size (default 14)

    Returns:
        RSI value (0-100) or None if insufficient data
    """
    if len(closes) < window + 1:  # Need one extra for first change
        return None

    # Calculate price changes
    changes = []
    for i in range(1, len(closes)):
        changes.append(closes[i] - closes[i - 1])

    # Use last 'window' changes
    window_changes = changes[-window:]

    # Separate gains and losses
    gains = [c for c in window_changes if c > 0]
    losses = [-c for c in window_changes if c < 0]

    # Average gain and loss
    avg_gain = sum(gains) / Decimal(window) if gains else Decimal("0")
    avg_loss = sum(losses) / Decimal(window) if losses else Decimal("0")

    if avg_loss == 0:
        return Decimal("100")  # No losses = RSI 100

    rs = avg_gain / avg_loss
    rsi = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

    return rsi


def compute_stochastic(
    highs: List[Decimal],
    lows: List[Decimal],
    closes: List[Decimal],
    k_period: int = 14,
    d_period: int = 3,
) -> Optional[Tuple[float, float]]:
    """
    Compute Stochastic Oscillator %K and %D.

    %K = (close - lowest_low_K) / (highest_high_K - lowest_low_K) * 100
    %D = SMA(%K, d_period)

    Args:
        highs: List of high prices (oldest first)
        lows: List of low prices (oldest first)
        closes: List of close prices (oldest first)
        k_period: Look-back window for %K (default 14)
        d_period: Smoothing window for %D (default 3)

    Returns:
        (stoch_k, stoch_d) tuple or None if insufficient data.
        Both values are in [0, 100] range.
    """
    required = k_period + d_period - 1
    if len(closes) < required or len(highs) < required or len(lows) < required:
        return None

    k_values: List[float] = []
    for i in range(d_period):
        # Index of the bar whose %K we compute (working backwards for d_period bars)
        end_idx = len(closes) - (d_period - 1 - i)
        start_idx = end_idx - k_period
        window_highs = highs[start_idx:end_idx]
        window_lows = lows[start_idx:end_idx]
        current_close = closes[end_idx - 1]

        highest = max(window_highs)
        lowest = min(window_lows)
        denom = float(highest - lowest)
        if denom == 0.0:
            k_values.append(50.0)
        else:
            k_values.append(float(current_close - lowest) / denom * 100.0)

    stoch_k = k_values[-1]
    stoch_d = sum(k_values) / len(k_values)
    return stoch_k, stoch_d


@dataclass
class IndicatorState:
    """
    State container for bar-based indicators.

    Holds calculated indicator values for a single symbol/timeframe.
    """
    symbol: str
    timeframe_sec: int

    # Bollinger Bands
    bb: Optional[BollingerBands] = None
    bb_window: int = 20
    bb_num_std: float = 2.0

    # ATR
    atr: Optional[Decimal] = None
    atr_window: int = 14

    # RSI (optional)
    rsi: Optional[Decimal] = None
    rsi_window: int = 14

    def update_bollinger(self, closes: List[Decimal], current_price: Optional[Decimal] = None) -> None:
        """Update Bollinger Bands from closes."""
        self.bb = compute_bollinger_bands(
            closes, self.bb_window, self.bb_num_std, current_price)

    def update_atr(self, highs: List[Decimal], lows: List[Decimal], closes: List[Decimal]) -> None:
        """Update ATR."""
        self.atr = compute_atr(highs, lows, closes, self.atr_window)

    def update_rsi(self, closes: List[Decimal]) -> None:
        """Update RSI."""
        self.rsi = compute_rsi(closes, self.rsi_window)

    @property
    def has_bollinger(self) -> bool:
        """True if Bollinger Bands are calculated."""
        return self.bb is not None

    @property
    def has_atr(self) -> bool:
        """True if ATR is calculated."""
        return self.atr is not None

    @property
    def bb_width_pct(self) -> float:
        """Bollinger Band width as percentage (0 if not calculated)."""
        return self.bb.width if self.bb else 0.0

    @property
    def is_price_at_lower_band(self) -> bool:
        """True if price is at or below lower Bollinger Band."""
        return self.bb.is_price_below_lower if self.bb else False

    @property
    def is_price_at_upper_band(self) -> bool:
        """True if price is at or above upper Bollinger Band."""
        return self.bb.is_price_above_upper if self.bb else False
