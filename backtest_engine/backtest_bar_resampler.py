"""
Backtest Bar Resampler — 5m → M15/H4/D1 aggregation for Pillar Warmup.

Aurora Phase 9: Pillars Warmup Pipeline.

Problem:
  BacktestEngine emits only EVT:BAR_CLOSED with tf_sec=300 (5m).
  FE Pillars (Tactician/Operator/Strategist) need M15/H4/D1 bars.
  BarAggregator is live-only (not instantiated in backtest).

Solution:
  Aggregate 5m bars into higher timeframes using OHLCV accumulation.
  When an HTF bar closes (boundary crossed), emit EVT:BAR_CLOSED
  with the correct tf_sec so FE can update pillar state.

Design:
  - Pure data aggregation, no strategy/signal logic.
  - D1 bars aligned to UTC 00:00 boundary.
  - OHLCV integrity: high=max(highs), low=min(lows).
  - emit_events control delegated to FE (via emit_timeframes gating).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

LOG = logging.getLogger(__name__)


@dataclass
class _HTFBarAccumulator:
    """Accumulates 5m bars into a single higher-timeframe OHLCV bar."""
    tf_sec: int
    open: Optional[float] = None
    high: float = float("-inf")
    low: float = float("inf")
    close: float = 0.0
    volume: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    buy_notional: float = 0.0
    sell_notional: float = 0.0
    bar_start_ts_ms: Optional[int] = None
    bar_count: int = 0  # Number of 5m bars accumulated

    def reset(self) -> None:
        self.open = None
        self.high = float("-inf")
        self.low = float("inf")
        self.close = 0.0
        self.volume = 0.0
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.buy_count = 0
        self.sell_count = 0
        self.buy_notional = 0.0
        self.sell_notional = 0.0
        self.bar_start_ts_ms = None
        self.bar_count = 0

    def update(self, bar: dict) -> None:
        """Accumulate one 5m bar into this HTF bar."""
        close = float(bar.get("close", 0))
        high = float(bar.get("high", close))
        low = float(bar.get("low", close))
        open_px = float(bar.get("open", close))
        volume = float(bar.get("volume", 0))

        if self.open is None:
            self.open = open_px
            self.bar_start_ts_ms = int(bar.get("start_ts_ms") or bar.get("end_ts_ms", 0))

        if high > self.high:
            self.high = high
        if low < self.low:
            self.low = low
        self.close = close
        self.volume += volume
        self.buy_volume += float(bar.get("buy_volume", 0))
        self.sell_volume += float(bar.get("sell_volume", 0))
        self.buy_count += int(bar.get("buy_count", 0))
        self.sell_count += int(bar.get("sell_count", 0))
        self.buy_notional += float(bar.get("buy_notional", 0))
        self.sell_notional += float(bar.get("sell_notional", 0))
        self.bar_count += 1

    def to_bar_payload(self, symbol: str, end_ts_ms: int) -> dict:
        """Convert accumulated state to EVT:BAR_CLOSED payload."""
        return {
            "symbol": symbol,
            "ts_ms": end_ts_ms,
            "tf_sec": self.tf_sec,
            "bar_close_ts": end_ts_ms,
            "bar": {
                "symbol": symbol,
                "timeframe_sec": self.tf_sec,
                "start_ts_ms": self.bar_start_ts_ms or (end_ts_ms - self.tf_sec * 1000),
                "end_ts_ms": end_ts_ms,
                "open": str(self.open or self.close),
                "high": str(self.high if self.high != float("-inf") else self.close),
                "low": str(self.low if self.low != float("inf") else self.close),
                "close": str(self.close),
                "volume": str(self.volume),
                "buy_volume": str(self.buy_volume),
                "sell_volume": str(self.sell_volume),
                "buy_count": int(self.buy_count),
                "sell_count": int(self.sell_count),
                "buy_notional": str(self.buy_notional),
                "sell_notional": str(self.sell_notional),
                "bid_size": "0",
                "ask_size": "0",
                "bid": str(self.close),
                "ask": str(self.close),
            },
            "bar_meta": {
                "source": "backtest_resampler",
                "close_reason": "htf_boundary",
                "basis_bars": self.bar_count,
            },
            "why": "backtest_htf_resampled",
        }

    @property
    def is_empty(self) -> bool:
        return self.open is None


def _align_to_boundary(ts_ms: int, tf_sec: int) -> int:
    """Floor-align timestamp to timeframe boundary (UTC).

    Returns the bar boundary start time (ms) that ts_ms belongs to.
    """
    tf_ms = tf_sec * 1000
    return (ts_ms // tf_ms) * tf_ms


class BacktestBarResampler:
    """Resample 5m bars → M15/H4/D1 for pillar warmup in backtest.

    Accumulates 5m bar OHLCV data into higher timeframe bars.
    When a new 5m bar crosses an HTF bar boundary, the previous
    HTF bar is closed and emitted as EVT:BAR_CLOSED.

    Usage:
        resampler = BacktestBarResampler(
            emit_fn=fsm.emit,
            pillar_timeframes_sec=[900, 14400, 86400],
        )
        # In backtest loop, after each 5m bar:
        resampler.on_5m_bar(symbol="BTCUSDT", bar_data=bar_dict, ts_ms=ts_ms)
    """

    def __init__(
        self,
        emit_fn: Callable[..., Any],
        pillar_timeframes_sec: List[int],
    ):
        """Initialize resampler.

        Args:
            emit_fn: FSM emit function (event_name, payload, why).
            pillar_timeframes_sec: List of HTF periods in seconds (e.g. [900, 14400, 86400]).
        """
        self.emit_fn = emit_fn
        self.pillar_timeframes_sec = sorted(pillar_timeframes_sec)

        # Per-(symbol, tf_sec) accumulator state
        self._accumulators: Dict[tuple[str, int], _HTFBarAccumulator] = {}
        # Per-(symbol, tf_sec) last bar boundary
        self._last_boundary: Dict[tuple[str, int], int] = {}

        # Metrics
        self._bars_emitted: Dict[int, int] = {tf: 0 for tf in pillar_timeframes_sec}
        self._total_5m_bars_processed: int = 0

        LOG.info(
            "BacktestBarResampler initialized",
            extra={"pillar_timeframes_sec": self.pillar_timeframes_sec},
        )

    def on_5m_bar(self, symbol: str, bar_data: dict, ts_ms: int) -> List[dict]:
        """Process a closed 5m bar and emit HTF bars if boundaries crossed.

        Args:
            symbol: Trading pair (e.g. "BTCUSDT").
            bar_data: The 5m bar dict (must have open/high/low/close/volume).
            ts_ms: Bar close timestamp in milliseconds.

        Returns:
            List of emitted HTF bar payloads (for testing/debugging).
        """
        self._total_5m_bars_processed += 1
        emitted: List[dict] = []

        for tf_sec in self.pillar_timeframes_sec:
            key = (symbol, tf_sec)

            # Get or create accumulator
            if key not in self._accumulators:
                self._accumulators[key] = _HTFBarAccumulator(tf_sec=tf_sec)

            acc = self._accumulators[key]
            current_boundary = _align_to_boundary(ts_ms, tf_sec)
            prev_boundary = self._last_boundary.get(key)

            if prev_boundary is not None and current_boundary != prev_boundary:
                # Boundary crossed — close the previous HTF bar
                if not acc.is_empty:
                    bar_end_ts_ms = prev_boundary + tf_sec * 1000
                    payload = acc.to_bar_payload(symbol, bar_end_ts_ms)
                    self.emit_fn(
                        event_name="EVT:BAR_CLOSED",
                        payload=payload,
                        why="backtest_htf_resampled",
                    )
                    emitted.append(payload)
                    self._bars_emitted[tf_sec] = self._bars_emitted.get(tf_sec, 0) + 1

                    if self._bars_emitted[tf_sec] <= 3 or self._bars_emitted[tf_sec] % 50 == 0:
                        LOG.info(
                            f"📊 HTF bar closed: {symbol} tf={tf_sec}s "
                            f"O={acc.open:.2f} H={acc.high:.2f} L={acc.low:.2f} C={acc.close:.2f} "
                            f"({acc.bar_count} basis bars, total={self._bars_emitted[tf_sec]})"
                        )

                # Reset accumulator for new period
                acc.reset()

            # Accumulate current 5m bar into HTF
            acc.update(bar_data)
            self._last_boundary[key] = current_boundary

        return emitted

    def get_metrics(self) -> dict:
        """Get resampler metrics for logging/debugging."""
        return {
            "total_5m_bars_processed": self._total_5m_bars_processed,
            "htf_bars_emitted": dict(self._bars_emitted),
            "active_accumulators": len(self._accumulators),
        }
