"""
Pillar Indicators — Pure Functions for Multi-Timeframe Pillars.

Aurora Phase 9: "The Quadratic Brain" — Phase 1.

Three pillars extract directional conviction from different timeframes:
  - Tactician (M15): ROC — tactical momentum
  - Operator  (H4):  LinReg Slope + ADX — working vector
  - Strategist (D1): Price vs SMA(200) — global territory

All normalize to [-1.0, +1.0] via tanh-based normalization.

NO FSM imports, NO event handling, NO side effects — pure functions only.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence


# =============================================================================
# NORMALIZATION
# =============================================================================

def normalize_to_pm1(x: float, sensitivity: float = 3.0) -> float:
    """
    tanh-based normalization to [-1, +1].

    Softer than linear normalization — avoids sharp jumps at extremes.
    sensitivity controls how quickly saturation occurs:
      - 1.0 = very gradual (rare saturation)
      - 3.0 = moderate (default, recommended)
      - 5.0 = aggressive (saturates early)

    Args:
        x: Raw value (any range).
        sensitivity: Scaling factor before tanh. Default 3.0.

    Returns:
        Normalized value in [-1.0, +1.0].
    """
    if not math.isfinite(x):
        return 0.0
    return math.tanh(x * sensitivity)


# =============================================================================
# TACTICIAN (M15) — Rate of Change
# =============================================================================

def compute_roc(closes: Sequence[float], period: int = 14) -> Optional[float]:
    """
    Rate of Change (ROC) = (close[-1] - close[-period]) / close[-period].

    Measures momentum over `period` bars.

    Args:
        closes: Sequence of close prices, chronological order.
        period: Lookback period. Default 14.

    Returns:
        ROC as fractional change (e.g., 0.05 = +5%), or None if insufficient data.
    """
    if len(closes) < period + 1:
        return None

    prev_close = closes[-(period + 1)]
    curr_close = closes[-1]

    if prev_close == 0 or not math.isfinite(prev_close):
        return None

    roc = (curr_close - prev_close) / abs(prev_close)

    if not math.isfinite(roc):
        return None

    return roc


def compute_tactician(
    closes: Sequence[float],
    roc_period: int = 14,
    sensitivity: float = 3.0,
) -> Optional[float]:
    """
    Tactician Pillar: ROC(M15) normalized to [-1, +1].

    Args:
        closes: M15 close prices.
        roc_period: ROC lookback period.
        sensitivity: tanh sensitivity.

    Returns:
        Normalized tactician value in [-1, +1], or None if not ready.
    """
    roc = compute_roc(closes, roc_period)
    if roc is None:
        return None
    return normalize_to_pm1(roc, sensitivity)


# =============================================================================
# OPERATOR (H4) — Linear Regression Slope + ADX
# =============================================================================

def compute_linreg_slope(closes: Sequence[float], period: int = 20) -> Optional[float]:
    """
    Linear Regression Slope over `period` bars.

    Ordinary least squares: slope = Σ((x_i - x̄)(y_i - ȳ)) / Σ((x_i - x̄)²)
    where x = bar index, y = close price.

    Result normalized by mean close to make cross-asset comparable:
        normalized_slope = slope / mean_close

    Args:
        closes: Sequence of close prices.
        period: Window for regression.

    Returns:
        Normalized slope (per-bar fractional change), or None if insufficient data.
    """
    if len(closes) < period:
        return None

    window = closes[-period:]
    n = len(window)

    # Mean of x (indices) and y (prices)
    x_mean = (n - 1) / 2.0
    y_mean = sum(window) / n

    if y_mean == 0:
        return None

    numerator = 0.0
    denominator = 0.0

    for i in range(n):
        x_diff = i - x_mean
        y_diff = window[i] - y_mean
        numerator += x_diff * y_diff
        denominator += x_diff * x_diff

    if denominator == 0:
        return None

    slope = numerator / denominator

    # Normalize by mean close for cross-asset comparability
    normalized_slope = slope / abs(y_mean)

    if not math.isfinite(normalized_slope):
        return None

    return normalized_slope


def compute_adx(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> Optional[float]:
    """
    Average Directional Index (ADX).

    Measures trend strength regardless of direction. Range: [0, 100].
    Typically: <20 = weak trend, 20-40 = strong, >40 = very strong.

    Implementation uses Wilder's smoothing (EMA-like with alpha=1/period).

    Args:
        highs: High prices.
        lows: Low prices.
        closes: Close prices.
        period: ADX period.

    Returns:
        ADX value [0, 100], or None if insufficient data.
    """
    n = len(highs)
    if n < period * 2 + 1 or len(lows) != n or len(closes) != n:
        return None

    # Step 1: Calculate True Range, +DM, -DM
    tr_list = []
    plus_dm_list = []
    minus_dm_list = []

    for i in range(1, n):
        high_diff = highs[i] - highs[i - 1]
        low_diff = lows[i - 1] - lows[i]

        plus_dm = max(high_diff, 0.0) if high_diff > low_diff else 0.0
        minus_dm = max(low_diff, 0.0) if low_diff > high_diff else 0.0

        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

        tr_list.append(tr)
        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)

    if len(tr_list) < period * 2:
        return None

    # Step 2: Wilder's smoothing (first value = SMA, then EMA-like)
    alpha = 1.0 / period

    # Initial sums
    atr = sum(tr_list[:period])
    plus_dm_smooth = sum(plus_dm_list[:period])
    minus_dm_smooth = sum(minus_dm_list[:period])

    dx_list = []

    for i in range(period, len(tr_list)):
        # Wilder's smoothing: smoothed = prev - (prev / period) + current
        atr = atr - (atr / period) + tr_list[i]
        plus_dm_smooth = plus_dm_smooth - (plus_dm_smooth / period) + plus_dm_list[i]
        minus_dm_smooth = minus_dm_smooth - (minus_dm_smooth / period) + minus_dm_list[i]

        if atr == 0:
            continue

        plus_di = (plus_dm_smooth / atr) * 100
        minus_di = (minus_dm_smooth / atr) * 100

        di_sum = plus_di + minus_di
        if di_sum == 0:
            dx_list.append(0.0)
        else:
            dx = abs(plus_di - minus_di) / di_sum * 100
            dx_list.append(dx)

    if len(dx_list) < period:
        return None

    # Step 3: ADX = smoothed average of DX
    adx = sum(dx_list[:period]) / period
    for i in range(period, len(dx_list)):
        adx = adx + alpha * (dx_list[i] - adx)

    if not math.isfinite(adx):
        return None

    return adx


def compute_operator(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    linreg_period: int = 20,
    adx_period: int = 14,
    sensitivity: float = 3.0,
) -> Optional[float]:
    """
    Operator Pillar: LinReg(H4) × ADX_weight, normalized to [-1, +1].

    Combines directional slope with trend strength:
      raw = slope × (adx / 50.0)
      - ADX < 25: dampens signal (weak trend)
      - ADX > 50: amplifies signal (strong trend)

    Args:
        closes: H4 close prices.
        highs: H4 high prices.
        lows: H4 low prices.
        linreg_period: LinReg window.
        adx_period: ADX window.
        sensitivity: tanh sensitivity.

    Returns:
        Normalized operator value in [-1, +1], or None if not ready.
    """
    slope = compute_linreg_slope(closes, linreg_period)
    adx = compute_adx(highs, lows, closes, adx_period)

    if slope is None or adx is None:
        return None

    # ADX weight: ADX/50 so that ADX=50 → weight=1.0
    adx_weight = adx / 50.0
    raw = slope * adx_weight

    return normalize_to_pm1(raw, sensitivity)


# =============================================================================
# STRATEGIST (D1) — Price Position vs SMA(200)
# =============================================================================

def compute_sma(values: Sequence[float], period: int) -> Optional[float]:
    """
    Simple Moving Average.

    Args:
        values: Data series.
        period: SMA period.

    Returns:
        SMA value, or None if insufficient data.
    """
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def compute_strategist(
    closes: Sequence[float],
    sma_period: int = 200,
    sensitivity: float = 3.0,
) -> Optional[float]:
    """
    Strategist Pillar: Position of price relative to SMA(200).

    raw = (current_close - SMA200) / SMA200
    Positive = price above SMA (bullish territory)
    Negative = price below SMA (bearish territory)

    Args:
        closes: D1 close prices.
        sma_period: SMA period. Default 200.
        sensitivity: tanh sensitivity.

    Returns:
        Normalized strategist value in [-1, +1], or None if not ready.
    """
    sma = compute_sma(closes, sma_period)
    if sma is None or sma == 0:
        return None

    current_close = closes[-1]
    if not math.isfinite(current_close) or current_close == 0:
        return None

    raw = (current_close - sma) / abs(sma)

    if not math.isfinite(raw):
        return None

    return normalize_to_pm1(raw, sensitivity)


# =============================================================================
# WEIGHTED PILLAR AGGREGATION
# =============================================================================

def aggregate_pillars(
    tactician: Optional[float],
    operator: Optional[float],
    strategist: Optional[float],
    weights: dict[str, float],
) -> Optional[float]:
    """
    Weighted sum of pillar values.

    Used as input to the Quadratic Scoring Kernel:
        weighted_sum = Σ(pillar_i × weight_i)

    If any pillar is None (not ready), returns None (fail-closed).

    Args:
        tactician: Normalized M15 pillar [-1, +1].
        operator: Normalized H4 pillar [-1, +1].
        strategist: Normalized D1 pillar [-1, +1].
        weights: {"tactician": w1, "operator": w2, "strategist": w3}.

    Returns:
        Weighted sum, or None if any pillar is not ready.
    """
    if tactician is None or operator is None or strategist is None:
        return None

    w_t = weights.get("tactician", 0.30)
    w_o = weights.get("operator", 0.40)
    w_s = weights.get("strategist", 0.30)

    total = tactician * w_t + operator * w_o + strategist * w_s

    if not math.isfinite(total):
        return None

    return total
