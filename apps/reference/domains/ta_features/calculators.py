"""
TA Features — Pure Math Calculators.

Bar-based technical indicators for ta_features domain.
Zero FSM/config dependencies — all functions are pure (input→output).

Reuses:
  compute_bollinger_bands, compute_rsi, compute_sma
  from apps.reference.domains.feature_engineering.indicators
"""

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
