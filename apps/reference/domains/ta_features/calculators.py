"""
TA Features — Pure Math Calculators.

Bar-based technical indicators for ta_features domain.
Zero FSM/config dependencies — all functions are pure (input→output).

Reuses:
  compute_bollinger_bands, compute_rsi, compute_sma
  from apps.reference.domains.feature_engineering.indicators
"""

import math
from decimal import Decimal
from typing import List, Tuple

from apps.reference.domains.feature_engineering.indicators import (
    compute_bollinger_bands,
    compute_rsi,
    compute_sma,
)

__all__ = [
    "compute_ta_bb",
    "compute_ta_rsi",
    "compute_stochastic",
    "compute_price_sma_deviation",
    "compute_volume_sma_ratio",
    "compute_price_momentum",
    "compute_macd_signal",
    "compute_atr",
    "compute_realized_volatility",
    "compute_volume_momentum",
    "compute_price_range_ratio",
    "compute_bb_width_change",
]

MIN_WARM_BARS = 20  # Minimum bars before any feature is reliable


def compute_ta_bb(
    closes: List[Decimal],
    period: int = 20,
    num_std: float = 2.0,
) -> Tuple[float, float]:
    """
    Bollinger Bands — bb_position (%B) and bb_width.

    Args:
        closes: Close prices (oldest → newest), Decimal list.
        period:  SMA window (default 20).
        num_std: Band multiplier (default 2.0).

    Returns:
        (bb_position, bb_width)
        bb_position: %B = (close - lower) / (upper - lower), can be outside [0,1]
        bb_width:    (upper - lower) / mid  (normalised band width ≥ 0)
    """
    bb = compute_bollinger_bands(closes, window=period, num_std=num_std)
    if bb is None:
        return 0.5, 0.0
    return bb.pct_b, bb.width


def compute_ta_rsi(
    closes: List[Decimal],
    period: int = 14,
) -> float:
    """
    RSI (Wilder's method) — returns value in [0, 100].

    Falls back to 50.0 when insufficient data.
    """
    rsi = compute_rsi(closes, window=period)
    if rsi is None:
        return 50.0
    return float(rsi)


def compute_stochastic(
    highs: List[Decimal],
    lows: List[Decimal],
    closes: List[Decimal],
    k_period: int = 14,
    d_period: int = 3,
) -> Tuple[float, float]:
    """
    Stochastic Oscillator — %K (current bar) and %D (d_period SMA of %K).

    Requires at least k_period + d_period - 1 bars.

    stoch_k[i] = 100 * (close[i] - lowest_low[k_period]) / (highest_high[k_period] - lowest_low[k_period])
    stoch_d    = SMA(stoch_k, d_period)

    Returns (stoch_k, stoch_d), both in [0, 100].
    Falls back to (50.0, 50.0) if insufficient data.
    """
    required = k_period + d_period - 1
    n = len(closes)
    if n < required or len(highs) < required or len(lows) < required:
        return 50.0, 50.0

    k_values: List[float] = []
    for d_off in range(d_period):
        # Rolling window end: d_off=0 → current bar, d_off=1 → one bar ago, etc.
        end_idx = n - d_off
        start_idx = end_idx - k_period

        slice_h = highs[start_idx:end_idx]
        slice_l = lows[start_idx:end_idx]
        i_close = closes[end_idx - 1]  # close of the target bar

        highest = max(slice_h)
        lowest = min(slice_l)
        rng = highest - lowest

        if float(rng) == 0.0:
            k_values.append(50.0)
        else:
            k_val = 100.0 * float(i_close - lowest) / float(rng)
            # Clamp: price can momentarily exceed band (intrabar spike)
            k_values.append(max(0.0, min(100.0, k_val)))

    stoch_k = k_values[0]
    stoch_d = sum(k_values) / len(k_values)
    return stoch_k, stoch_d


def compute_price_sma_deviation(
    closes: List[Decimal],
    period: int = 20,
) -> float:
    """
    Normalised deviation of the latest close from its SMA.

    Formula: (close[-1] - SMA(period)) / SMA(period)

    Returns 0.0 when insufficient data or SMA is zero.
    """
    if len(closes) < period:
        return 0.0
    sma = compute_sma(closes, period)
    if sma is None or sma == 0:
        return 0.0
    return float((closes[-1] - sma) / sma)


def compute_volume_sma_ratio(
    volumes: List[Decimal],
    period: int = 20,
) -> float:
    """
    Ratio of current bar volume to its SMA.

    Formula: volumes[-1] / SMA(volumes, period)

    Returns 1.0 (neutral) when insufficient data or SMA is zero.
    """
    if len(volumes) < period:
        return 1.0
    sma = compute_sma(volumes, period)
    if sma is None or sma == 0:
        return 1.0
    return float(volumes[-1] / sma)


def compute_price_momentum(
    closes: List[Decimal],
    lookback: int = 5,
) -> float:
    """
    Simple price momentum over `lookback` bars.

    Formula: (close[-1] - close[-(lookback+1)]) / close[-(lookback+1)]

    For a 5-minute window:
      - 1m bars → lookback=5  (5 × 60s = 5m)
      - 5m bars → lookback=1  (1 × 300s = 5m)

    Returns 0.0 when insufficient data or base price is zero.
    """
    if len(closes) < lookback + 1:
        return 0.0
    base = closes[-(lookback + 1)]
    if base == 0:
        return 0.0
    return float((closes[-1] - base) / base)


# ---------------------------------------------------------------------------
# EMA helper (private — used by MACD)
# ---------------------------------------------------------------------------

def _compute_ema(values: List[float], period: int) -> List[float]:
    """
    Exponential Moving Average series.

    Seed: SMA of first `period` values.
    Then EMA_i = value_i * k + EMA_{i-1} * (1 - k),  k = 2 / (period + 1).

    Returns list of EMA values (length = len(values) - period + 1).
    Returns empty list if len(values) < period.
    """
    n = len(values)
    if n < period:
        return []
    k = 2.0 / (period + 1)
    sma_seed = sum(values[:period]) / period
    ema = [sma_seed]
    for i in range(period, n):
        ema.append(values[i] * k + ema[-1] * (1 - k))
    return ema


# ---------------------------------------------------------------------------
# New calculators (Step 1 of TA Features 8→18 expansion)
# ---------------------------------------------------------------------------

def compute_macd_signal(
    closes: List[Decimal],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> float:
    """
    MACD signal line = EMA(signal) of MACD line.
    MACD line = EMA(fast) - EMA(slow).

    Requires at least slow + signal - 1 bars for a meaningful value.
    Returns 0.0 when insufficient data.
    """
    n = len(closes)
    if n < slow + signal - 1:
        return 0.0

    floats = [float(c) for c in closes]
    ema_fast = _compute_ema(floats, fast)
    ema_slow = _compute_ema(floats, slow)

    # Align: ema_slow starts at index (slow - 1), ema_fast at (fast - 1).
    # We need them aligned by original index.
    offset = slow - fast
    if offset < 0 or len(ema_fast) <= offset:
        return 0.0

    macd_line = [
        ema_fast[offset + i] - ema_slow[i]
        for i in range(len(ema_slow))
    ]

    signal_line = _compute_ema(macd_line, signal)
    if not signal_line:
        return 0.0
    return signal_line[-1]


def compute_atr(
    highs: List[Decimal],
    lows: List[Decimal],
    closes: List[Decimal],
    period: int = 14,
) -> float:
    """
    Average True Range: SMA of True Range over `period` bars.

    TR = max(high - low, |high - prev_close|, |low - prev_close|)

    Requires at least period + 1 bars (period TRs need period + 1 prices).
    Returns 0.0 when insufficient data.
    """
    n = len(closes)
    if n < period + 1 or len(highs) < period + 1 or len(lows) < period + 1:
        return 0.0

    true_ranges: List[float] = []
    for i in range(n - period, n):
        h = float(highs[i])
        l = float(lows[i])
        pc = float(closes[i - 1])
        tr = max(h - l, abs(h - pc), abs(l - pc))
        true_ranges.append(tr)

    return sum(true_ranges) / len(true_ranges)


def compute_realized_volatility(
    closes: List[Decimal],
    lookback: int,
) -> float:
    """
    Realized volatility: standard deviation of log-returns over `lookback` bars.

    Requires at least lookback + 1 closes (lookback returns need lookback + 1 prices).
    Returns 0.0 when insufficient data or all returns are zero.
    """
    if lookback < 2:
        return 0.0
    n = len(closes)
    if n < lookback + 1:
        return 0.0

    log_returns: List[float] = []
    for i in range(n - lookback, n):
        prev = float(closes[i - 1])
        curr = float(closes[i])
        if prev <= 0 or curr <= 0:
            return 0.0
        log_returns.append(math.log(curr / prev))

    if len(log_returns) < 2:
        return 0.0

    mean = sum(log_returns) / len(log_returns)
    variance = sum((r - mean) ** 2 for r in log_returns) / \
        (len(log_returns) - 1)
    return math.sqrt(variance)


def compute_volume_momentum(
    volumes: List[Decimal],
) -> float:
    """
    Volume momentum: (current_volume - previous_volume) / previous_volume.

    Returns 0.0 when insufficient data or previous volume is zero.
    """
    if len(volumes) < 2:
        return 0.0
    prev = float(volumes[-2])
    if prev == 0:
        return 0.0
    return (float(volumes[-1]) - prev) / prev


def compute_price_range_ratio(
    high: Decimal,
    low: Decimal,
    close: Decimal,
) -> float:
    """
    Price range ratio: (high - low) / close for current bar.

    Returns 0.0 when close is zero.
    """
    c = float(close)
    if c == 0:
        return 0.0
    return (float(high) - float(low)) / c


def compute_bb_width_change(
    closes: List[Decimal],
    period: int = 20,
    num_std: float = 2.0,
) -> float:
    """
    Change in Bollinger Band width vs the previous bar's width.

    Computes BB width for current window and for the window shifted back by 1 bar.
    Returns the delta: width_current - width_previous.

    Returns 0.0 when insufficient data (needs period + 1 bars for two windows).
    """
    if len(closes) < period + 1:
        return 0.0

    bb_current = compute_bollinger_bands(
        closes[-period:], window=period, num_std=num_std)
    bb_prev = compute_bollinger_bands(
        closes[-(period + 1):-1], window=period, num_std=num_std)

    if bb_current is None or bb_prev is None:
        return 0.0

    return bb_current.width - bb_prev.width
