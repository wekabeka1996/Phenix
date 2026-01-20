"""
Macro Sync V2 — Time-grid aligned correlation (TASK30-I).

Design goals:
- Exchange timestamp SSOT (ts_ms) only (no wallclock fallbacks).
- Time-grid resampling (bin_ms) and alignment by bin intersection (not index).
- Log-returns and Pearson correlation on aligned vectors.
- Fail-closed with explicit reasons (ready=false + why).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, List, Optional, Tuple
from collections import deque

try:
    from apps.reference.telemetry.metrics import (
        inc_macro_sync_ooo_dropped,
        inc_macro_sync_ooo_reordered,
        set_macro_sync_last_bin_ts_ms,
    )
except Exception:  # telemetry is optional in some test harnesses
    def inc_macro_sync_ooo_dropped(_key: str) -> None:  # type: ignore
        pass

    def inc_macro_sync_ooo_reordered(_key: str) -> None:  # type: ignore
        pass

    def set_macro_sync_last_bin_ts_ms(_key: str, _last_bin_ts_ms: int) -> None:  # type: ignore
        pass


@dataclass
class MacroSyncResult:
    phi: float
    ready: bool
    why: Optional[str]
    bins_used: int
    drops_out_of_order: int
    gaps: int


@dataclass
class TimeGridSeries:
    bin_ms: int
    window_bins: int
    _bins: Deque[Tuple[int, float]] = field(default_factory=deque)
    _by_bin: Dict[int, float] = field(default_factory=dict)
    last_bin_ts: Optional[int] = None
    last_ts_ms: int = 0

    drops_out_of_order_total: int = 0
    reorders_out_of_order_total: int = 0
    gaps_total: int = 0
    _flag_out_of_order: bool = False
    _flag_large_gap: bool = False

    def update(self, *, key: str, ts_ms: int, price: float, max_gap_bins: int, max_late_ms: int) -> None:
        if ts_ms <= 0:
            raise ValueError("ts_ms must be > 0 (exchange timestamp SSOT)")
        if not (price > 0.0):
            return

        old_last_bin_ts = self.last_bin_ts
        bin_ts = (int(ts_ms) // self.bin_ms) * self.bin_ms
        if self.last_bin_ts is not None and bin_ts < self.last_bin_ts:
            # Allow late updates for an existing bin (idempotent corrections).
            if bin_ts in self._by_bin:
                self._by_bin[bin_ts] = float(price)
                for idx in range(len(self._bins) - 1, -1, -1):
                    if self._bins[idx][0] == bin_ts:
                        self._bins[idx] = (bin_ts, float(price))
                        break
                # last_ts_ms tracks latest observed exchange ts for TTL checks.
                self.last_ts_ms = max(int(self.last_ts_ms), int(ts_ms))
                return

            # Reorder/insert late bins within a bounded tolerance.
            late_ms = int(self.last_bin_ts) - int(bin_ts)
            if max_late_ms > 0 and late_ms <= int(max_late_ms):
                self.reorders_out_of_order_total += 1
                inc_macro_sync_ooo_reordered(key)
                bins = list(self._bins)
                inserted = False
                for i, (bts, _p) in enumerate(bins):
                    if bin_ts < bts:
                        bins.insert(i, (bin_ts, float(price)))
                        inserted = True
                        break
                if not inserted:
                    bins.append((bin_ts, float(price)))
                self._bins = deque(bins)
                self._by_bin[bin_ts] = float(price)

                # Keep latest markers unchanged (late insert should not regress last_bin_ts).
                self.last_ts_ms = max(int(self.last_ts_ms), int(ts_ms))

                keep = self.window_bins + 1
                while len(self._bins) > keep:
                    old_bin_ts, _old_price = self._bins.popleft()
                    self._by_bin.pop(old_bin_ts, None)
                return

            # Too-late tick: drop and mark for observability.
            self.drops_out_of_order_total += 1
            self._flag_out_of_order = True
            inc_macro_sync_ooo_dropped(key)
            return

        if self.last_bin_ts is not None and bin_ts > self.last_bin_ts:
            gap_bins = (bin_ts - self.last_bin_ts) // self.bin_ms - 1
            if gap_bins > 0:
                self.gaps_total += int(gap_bins)
                if gap_bins > max_gap_bins:
                    self._flag_large_gap = True

        self.last_bin_ts = bin_ts
        self.last_ts_ms = int(ts_ms)
        if old_last_bin_ts != self.last_bin_ts and self.last_bin_ts is not None:
            set_macro_sync_last_bin_ts_ms(key, int(self.last_bin_ts))

        if bin_ts in self._by_bin:
            self._by_bin[bin_ts] = float(price)
            for idx in range(len(self._bins) - 1, -1, -1):
                if self._bins[idx][0] == bin_ts:
                    self._bins[idx] = (bin_ts, float(price))
                    break
        else:
            self._bins.append((bin_ts, float(price)))
            self._by_bin[bin_ts] = float(price)

        keep = self.window_bins + 1
        while len(self._bins) > keep:
            old_bin_ts, _old_price = self._bins.popleft()
            self._by_bin.pop(old_bin_ts, None)

    def consume_flags(self) -> tuple[bool, bool]:
        out_of_order = self._flag_out_of_order
        large_gap = self._flag_large_gap
        self._flag_out_of_order = False
        self._flag_large_gap = False
        return out_of_order, large_gap

    def returns_by_bin(self) -> Dict[int, float]:
        out: Dict[int, float] = {}
        for bin_ts, price in self._bins:
            prev_ts = bin_ts - self.bin_ms
            prev_price = self._by_bin.get(prev_ts)
            if prev_price is None:
                continue
            if prev_price <= 0.0 or price <= 0.0:
                continue
            out[bin_ts] = math.log(price / prev_price)
        return out


class MacroSyncResampler:
    def __init__(
        self,
        *,
        bin_ms: int,
        window_bins: int,
        min_bins: int,
        ttl_ms: int,
        max_gap_bins: int,
        eps: float,
        max_late_ms: int = 0,
    ) -> None:
        if bin_ms <= 0:
            raise ValueError("bin_ms must be > 0")
        if window_bins <= 0:
            raise ValueError("window_bins must be > 0")
        if min_bins < 2:
            raise ValueError("min_bins must be >= 2")
        if ttl_ms <= 0:
            raise ValueError("ttl_ms must be > 0")
        if max_gap_bins < 0:
            raise ValueError("max_gap_bins must be >= 0")
        if max_late_ms < 0:
            raise ValueError("max_late_ms must be >= 0")
        if not (eps > 0.0):
            raise ValueError("eps must be > 0")

        self._bin_ms = int(bin_ms)
        self._window_bins = int(window_bins)
        self._min_bins = int(min_bins)
        self._ttl_ms = int(ttl_ms)
        self._max_gap_bins = int(max_gap_bins)
        self._max_late_ms = int(max_late_ms)
        self._eps = float(eps)

        self._series: Dict[str, TimeGridSeries] = {}

    def update_symbol(self, symbol: str, *, ts_ms: int, price: float) -> None:
        self._get_series(symbol).update(
            key=symbol,
            ts_ms=int(ts_ms),
            price=float(price),
            max_gap_bins=self._max_gap_bins,
            max_late_ms=self._max_late_ms,
        )

    def update_anchor(self, anchor: str, *, ts_ms: int, price: float) -> None:
        self._get_series(anchor).update(
            key=anchor,
            ts_ms=int(ts_ms),
            price=float(price),
            max_gap_bins=self._max_gap_bins,
            max_late_ms=self._max_late_ms,
        )

    def compute(self, symbol: str, *, anchors: Iterable[str], now_ts_ms: int) -> MacroSyncResult:
        if now_ts_ms <= 0:
            raise ValueError("now_ts_ms must be > 0 (exchange timestamp SSOT)")

        sym_series = self._series.get(symbol)
        if sym_series is None:
            return MacroSyncResult(phi=0.5, ready=False, why="insufficient_bins", bins_used=0, drops_out_of_order=0, gaps=0)

        # Consume flags for observability (but do NOT force NOT_READY).
        # Policy: out-of-order/late ticks are dropped (or reordered within tolerance) and must not
        # make the system perpetually not-ready if enough data exists.
        sym_out_of_order, sym_large_gap = sym_series.consume_flags()
        if sym_large_gap:
            return MacroSyncResult(
                phi=0.5,
                ready=False,
                why="gap_too_large",
                bins_used=0,
                drops_out_of_order=sym_series.drops_out_of_order_total,
                gaps=sym_series.gaps_total,
            )

        sym_returns = sym_series.returns_by_bin()
        if len(sym_returns) < self._min_bins:
            return MacroSyncResult(
                phi=0.5,
                ready=False,
                why="insufficient_bins",
                bins_used=len(sym_returns),
                drops_out_of_order=sym_series.drops_out_of_order_total,
                gaps=sym_series.gaps_total,
            )

        correlations: List[float] = []
        bins_used_max = 0
        saw_any_overlap = False
        saw_any_fresh = False
        saw_any_large_gap = sym_large_gap
        saw_any_out_of_order = sym_out_of_order
        saw_any_sigma_zero = False
        drops_total = sym_series.drops_out_of_order_total
        gaps_total = sym_series.gaps_total

        for anchor in anchors:
            a_series = self._series.get(anchor)
            if a_series is None:
                continue
            drops_total += a_series.drops_out_of_order_total
            gaps_total += a_series.gaps_total

            a_out_of_order, a_large_gap = a_series.consume_flags()
            saw_any_out_of_order = saw_any_out_of_order or a_out_of_order
            saw_any_large_gap = saw_any_large_gap or a_large_gap

            if a_series.last_ts_ms <= 0:
                continue
            if now_ts_ms - a_series.last_ts_ms > self._ttl_ms:
                continue
            saw_any_fresh = True

            a_returns = a_series.returns_by_bin()
            overlap_bins = sorted(set(sym_returns.keys()).intersection(a_returns.keys()))
            if not overlap_bins:
                continue
            saw_any_overlap = True

            if len(overlap_bins) < self._min_bins:
                continue

            n = min(len(overlap_bins), self._window_bins)
            use_bins = overlap_bins[-n:]
            bins_used_max = max(bins_used_max, len(use_bins))

            x = [float(sym_returns[b]) for b in use_bins]
            y = [float(a_returns[b]) for b in use_bins]

            corr = _pearson(x, y, eps=self._eps)
            if corr is None:
                saw_any_sigma_zero = True
                continue
            correlations.append(corr)

        if saw_any_large_gap:
            return MacroSyncResult(
                phi=0.5,
                ready=False,
                why="gap_too_large",
                bins_used=bins_used_max,
                drops_out_of_order=drops_total,
                gaps=gaps_total,
            )

        # Note: out-of-order signals are reflected via counters, but do not force NOT_READY.

        if not correlations:
            if not saw_any_fresh:
                why = "no_fresh_anchor_data"
            elif not saw_any_overlap:
                why = "no_overlap_bins"
            elif saw_any_sigma_zero:
                why = "sigma_zero"
            else:
                why = "insufficient_bins"
            return MacroSyncResult(
                phi=0.5,
                ready=False,
                why=why,
                bins_used=bins_used_max,
                drops_out_of_order=drops_total,
                gaps=gaps_total,
            )

        avg_corr = sum(correlations) / len(correlations)
        phi = (avg_corr + 1.0) / 2.0
        if phi < 0.0:
            phi = 0.0
        if phi > 1.0:
            phi = 1.0
        return MacroSyncResult(
            phi=phi,
            ready=True,
            why=None,
            bins_used=bins_used_max,
            drops_out_of_order=drops_total,
            gaps=gaps_total,
        )

    def _get_series(self, key: str) -> TimeGridSeries:
        s = self._series.get(key)
        if s is None:
            s = TimeGridSeries(bin_ms=self._bin_ms, window_bins=self._window_bins)
            self._series[key] = s
        return s


def _pearson(x: List[float], y: List[float], *, eps: float) -> Optional[float]:
    if len(x) != len(y) or len(x) < 2:
        return None

    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    num = 0.0
    sx = 0.0
    sy = 0.0
    for i in range(len(x)):
        dx = x[i] - mean_x
        dy = y[i] - mean_y
        num += dx * dy
        sx += dx * dx
        sy += dy * dy

    if sx <= eps or sy <= eps:
        return None
    denom = math.sqrt(sx) * math.sqrt(sy)
    if denom <= eps:
        return None
    return num / denom
