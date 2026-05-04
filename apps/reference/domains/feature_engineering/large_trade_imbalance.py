"""
Large Trade Imbalance V2 (TASK31-I).

Goals:
- Volume-weighted imbalance (no count-weighted fallbacks).
- No lost trade quantity: compute from qty (or notional if enabled).
- Deterministic behavior: explicit out-of-order handling (dropped counter is surfaced).
- Fail-closed: explicit ready=false + reason when data is insufficient/invalid.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LargeTradeImbalanceResult:
    phi: decimal.Decimal
    ready: bool
    why: Optional[str]
    trades_used: int
    dropped_out_of_order: int


def _clamp01(x: decimal.Decimal) -> decimal.Decimal:
    if x < 0:
        return decimal.Decimal("0")
    if x > 1:
        return decimal.Decimal("1")
    return x


class LargeTradeImbalanceCalculator:
    def __init__(
        self,
        *,
        window_ms: int,
        min_trades: int,
        eps: decimal.Decimal,
        neutral_value: decimal.Decimal,
        use_notional: bool,
    ) -> None:
        if window_ms <= 0:
            raise ValueError("window_ms must be > 0")
        if min_trades < 1:
            raise ValueError("min_trades must be >= 1")
        if eps <= 0:
            raise ValueError("eps must be > 0")

        self._window_ms = int(window_ms)
        self._min_trades = int(min_trades)
        self._eps = eps
        self._neutral = neutral_value
        self._use_notional = bool(use_notional)

        self._buy_sum = decimal.Decimal("0")
        self._sell_sum = decimal.Decimal("0")
        self._buy_count = 0
        self._sell_count = 0
        self._last_ts_ms = 0
        self._drops_out_of_order_total = 0
        self._ticks: list[tuple[int, str, decimal.Decimal]] = []  # (ts_ms, side, weight)

    def update_trade(self, *, ts_ms: int, side: str, qty: float, price: Optional[float]) -> None:
        if ts_ms <= 0:
            return
        if ts_ms < self._last_ts_ms:
            self._drops_out_of_order_total += 1
            return
        self._last_ts_ms = int(ts_ms)

        if not (qty > 0):
            return

        if side not in ("buy", "sell"):
            return

        if self._use_notional:
            if price is None or not (price > 0):
                return
            weight = decimal.Decimal(str(qty * price))
        else:
            weight = decimal.Decimal(str(qty))

        self._ticks.append((int(ts_ms), side, weight))
        if side == "buy":
            self._buy_sum += weight
            self._buy_count += 1
        else:
            self._sell_sum += weight
            self._sell_count += 1

        self._evict(now_ts_ms=int(ts_ms))

    def compute(self, *, now_ts_ms: int) -> LargeTradeImbalanceResult:
        self._evict(now_ts_ms=int(now_ts_ms))
        trades_used = self._buy_count + self._sell_count

        if trades_used < self._min_trades:
            return LargeTradeImbalanceResult(
                phi=self._neutral,
                ready=False,
                why="insufficient_trades",
                trades_used=trades_used,
                dropped_out_of_order=self._drops_out_of_order_total,
            )

        total = self._buy_sum + self._sell_sum
        if total <= 0:
            return LargeTradeImbalanceResult(
                phi=self._neutral,
                ready=False,
                why="zero_total_volume",
                trades_used=trades_used,
                dropped_out_of_order=self._drops_out_of_order_total,
            )

        imb = (self._buy_sum - self._sell_sum) / (total + self._eps)
        phi = _clamp01((imb + decimal.Decimal("1")) / decimal.Decimal("2"))
        return LargeTradeImbalanceResult(
            phi=phi,
            ready=True,
            why=None,
            trades_used=trades_used,
            dropped_out_of_order=self._drops_out_of_order_total,
        )

    def _evict(self, *, now_ts_ms: int) -> None:
        if now_ts_ms <= 0:
            return
        cutoff = int(now_ts_ms) - self._window_ms
        if cutoff <= 0:
            return

        idx = 0
        while idx < len(self._ticks) and self._ticks[idx][0] < cutoff:
            ts, side, weight = self._ticks[idx]
            if side == "buy":
                self._buy_sum -= weight
                self._buy_count = max(0, self._buy_count - 1)
            else:
                self._sell_sum -= weight
                self._sell_count = max(0, self._sell_count - 1)
            idx += 1
        if idx > 0:
            self._ticks = self._ticks[idx:]

    def compute_from_tick(self, current_tick: dict) -> LargeTradeImbalanceResult:
        buy_key = "buy_notional" if self._use_notional else "buy_volume"
        sell_key = "sell_notional" if self._use_notional else "sell_volume"

        try:
            buy = decimal.Decimal(str(current_tick[buy_key]))
            sell = decimal.Decimal(str(current_tick[sell_key]))
        except Exception:
            return LargeTradeImbalanceResult(
                phi=self._neutral,
                ready=False,
                why="missing_or_invalid_volume",
                trades_used=0,
                dropped_out_of_order=int(current_tick.get("trades_dropped_out_of_order") or 0),
            )

        buy_count = current_tick.get("buy_count")
        sell_count = current_tick.get("sell_count")
        if buy_count is None or sell_count is None:
            return LargeTradeImbalanceResult(
                phi=self._neutral,
                ready=False,
                why="missing_trade_counts",
                trades_used=0,
                dropped_out_of_order=int(current_tick.get("trades_dropped_out_of_order") or 0),
            )

        try:
            trades_used = int(buy_count) + int(sell_count)
        except Exception:
            return LargeTradeImbalanceResult(
                phi=self._neutral,
                ready=False,
                why="invalid_trade_counts",
                trades_used=0,
                dropped_out_of_order=int(current_tick.get("trades_dropped_out_of_order") or 0),
            )

        dropped_out_of_order = int(current_tick.get("trades_dropped_out_of_order") or 0)

        if trades_used < self._min_trades:
            return LargeTradeImbalanceResult(
                phi=self._neutral,
                ready=False,
                why="insufficient_trades",
                trades_used=trades_used,
                dropped_out_of_order=dropped_out_of_order,
            )

        total = buy + sell
        if total <= 0:
            return LargeTradeImbalanceResult(
                phi=self._neutral,
                ready=False,
                why="zero_total_volume",
                trades_used=trades_used,
                dropped_out_of_order=dropped_out_of_order,
            )

        imb = (buy - sell) / (total + self._eps)  # [-1, 1]
        phi = _clamp01((imb + decimal.Decimal("1")) / decimal.Decimal("2"))  # [0, 1]
        return LargeTradeImbalanceResult(
            phi=phi,
            ready=True,
            why=None,
            trades_used=trades_used,
            dropped_out_of_order=dropped_out_of_order,
        )
