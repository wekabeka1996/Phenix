"""
PRICE-MOTION-V1: Multi-window price motion features.

Computes:
- ret_window = (price_now / price_then) - 1
- vol_pct_window: robust realized volatility proxy (fractional, not *100)
- pm_norm_window = clip(ret_window / (k_vol * vol_pct_window), -1, 1)

All outputs are floats or None (for insufficient history / degenerate vol).
"""

from __future__ import annotations

import decimal
import statistics
from typing import Deque, Tuple, Iterable, Optional, Dict


def _to_ts_ms(ts: int) -> int:
    ts_i = int(ts)
    if ts_i <= 0:
        return 0
    # Heuristic: seconds epoch (~1e9) vs ms epoch (~1e12+)
    if ts_i < 1_000_000_000_000:
        return ts_i * 1000
    return ts_i


def _clip(x: float, lo: float, hi: float) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _price_at_or_before(
    history: Deque[Tuple[int, decimal.Decimal]],
    target_ts_ms: int,
) -> Optional[decimal.Decimal]:
    if not history:
        return None
    # Iterate from newest to oldest for speed.
    for ts_ms, price in reversed(history):
        if ts_ms <= target_ts_ms:
            return price
    return None


def _prices_in_window(
    history: Deque[Tuple[int, decimal.Decimal]],
    start_ts_ms: int,
    end_ts_ms: int,
) -> list[decimal.Decimal]:
    # history is chronological; collect prices in [start, end]
    out: list[decimal.Decimal] = []
    for ts_ms, price in history:
        if ts_ms < start_ts_ms:
            continue
        if ts_ms > end_ts_ms:
            break
        out.append(price)
    return out


def _robust_vol_from_prices(prices: Iterable[decimal.Decimal]) -> Optional[float]:
    """
    Robust volatility proxy: median(|ret_i|) where ret_i = p_i/p_{i-1}-1.
    Returns fractional value (e.g., 0.001 = 0.1%).
    """
    prices_list = list(prices)
    if len(prices_list) < 3:
        return None  # need at least 2 returns

    abs_rets: list[float] = []
    prev = prices_list[0]
    if prev is None or prev <= 0:
        return None
    for p in prices_list[1:]:
        if p is None or p <= 0:
            return None
        r = (p / prev) - decimal.Decimal("1")
        abs_rets.append(abs(float(r)))
        prev = p

    if len(abs_rets) < 2:
        return None
    vol = float(statistics.median(abs_rets))
    if not (vol >= 0.0):
        return None
    return vol


def update_price_history(
    history: Deque[Tuple[int, decimal.Decimal]],
    *,
    ts_ms: int,
    price: decimal.Decimal,
    max_window_ms: int,
) -> None:
    ts_ms = _to_ts_ms(ts_ms)
    if ts_ms <= 0:
        return
    if price is None or price <= 0:
        return
    history.append((ts_ms, price))
    # Prune by time (keep a bit extra to support window lookup).
    cutoff = ts_ms - int(max_window_ms)
    while history and history[0][0] < cutoff:
        history.popleft()


def compute_price_motion_block(
    history: Deque[Tuple[int, decimal.Decimal]],
    *,
    ts_ms: int,
    price: decimal.Decimal,
    k_vol: float,
    windows_sec: tuple[int, int, int] = (10, 60, 300),
) -> Dict[str, Optional[float]]:
    ts_ms = _to_ts_ms(ts_ms)
    if ts_ms <= 0 or price is None or price <= 0:
        return {
            "ret_10s": None,
            "ret_60s": None,
            "ret_300s": None,
            "vol_pct_10s": None,
            "vol_pct_60s": None,
            "vol_pct_300s": None,
            "pm_norm_10s": None,
            "pm_norm_60s": None,
            "pm_norm_300s": None,
        }

    max_window_ms = max(int(w) for w in windows_sec) * 1000
    update_price_history(history, ts_ms=ts_ms, price=price, max_window_ms=max_window_ms + 5000)

    out: Dict[str, Optional[float]] = {}
    for w in windows_sec:
        key_ret = f"ret_{w}s"
        key_vol = f"vol_pct_{w}s"
        key_pm = f"pm_norm_{w}s"

        start_ts = ts_ms - int(w) * 1000
        p_then = _price_at_or_before(history, start_ts)
        if p_then is None or p_then <= 0:
            out[key_ret] = None
            out[key_vol] = None
            out[key_pm] = None
            continue

        ret = (price / p_then) - decimal.Decimal("1")
        out[key_ret] = float(ret)

        prices_window = _prices_in_window(history, start_ts, ts_ms)
        vol = _robust_vol_from_prices(prices_window)
        if vol is None or vol <= 0.0:
            out[key_vol] = None
            out[key_pm] = None
            continue

        out[key_vol] = float(vol)
        denom = float(k_vol) * float(vol)
        if denom <= 0.0:
            out[key_pm] = None
            continue

        pm = float(ret) / denom
        out[key_pm] = _clip(pm, -1.0, 1.0)

    # Ensure all required keys exist (even if windows_sec changed).
    for k in (
        "ret_10s",
        "ret_60s",
        "ret_300s",
        "vol_pct_10s",
        "vol_pct_60s",
        "vol_pct_300s",
        "pm_norm_10s",
        "pm_norm_60s",
        "pm_norm_300s",
    ):
        out.setdefault(k, None)

    return out

