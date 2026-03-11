"""
Bar Aggregator: Multi-symbol, multi-timeframe SSOT for bar construction.

BAR-SSOT-001: SSOT Bar Aggregator + EVT:BAR_CLOSED

Responsibilities:
- Aggregate ticks into OHLCV bars for multiple symbols and timeframes
- Emit EVT:BAR_CLOSED when bar period closes
- Handle out-of-order ticks gracefully (drop, don't corrupt)
- Thread-safe for concurrent symbol updates

This is the SSOT for bar data in market_data domain. FE and strategies
subscribe to EVT:BAR_CLOSED events rather than building their own bars.

Usage:
    aggregator = BarAggregator(
        timeframes_sec=[180, 300],  # 3m and 5m bars
        emit_fn=fsm.emit
    )
    
    # In tick handler:
    aggregator.on_tick(symbol, price, volume, ts_ms)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import asdict
from decimal import Decimal
from threading import Lock
from typing import Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

# T2B-04: Time abstraction for deterministic testing
from apps.reference.core.time import get_clock
from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    attach_canonical_bar_payload,
    build_canonical_bar_identity,
)
from apps.reference.contracts.runtime_gap_policy import (
    attach_gap_status_payload,
    extract_gap_status,
)

# Re-use existing Bar model from FE (single source of truth for Bar structure)
from apps.reference.domains.feature_engineering.bar_resampler import Bar
from vfoundation.core.protocol import Message, truncate_why
from vfoundation.dr import wal

if TYPE_CHECKING:
    from vfoundation.core.fsm_core import FSMCore

LOG = logging.getLogger(__name__)


class BarAggregator:
    """
    Multi-symbol, multi-timeframe bar aggregator with event emission.
    
    SSOT for bar construction. Emits EVT:BAR_CLOSED when bars complete.
    
    Thread-safety: Uses per-key locking for concurrent access.
    
    Out-of-order policy:
    - If ts_ms <= last_ts_ms for (symbol, tf): tick is dropped
    - Metrics are incremented for dropped ticks
    - No bar corruption occurs
    """
    
    def __init__(
        self,
        timeframes_sec: Optional[List[int]] = None,
        emit_fn: Optional[Callable[[str, dict], None]] = None,
        max_bars_per_key: int = 100,
    ):
        """
        Initialize bar aggregator.
        
        Args:
            timeframes_sec: List of bar durations in seconds (default [180, 300])
            emit_fn: Function to emit events (FSM emit or mock)
            max_bars_per_key: Max completed bars to keep per (symbol, tf) pair
        """
        self.timeframes_sec = timeframes_sec or [180, 300]  # 3m and 5m default
        self.emit_fn = emit_fn
        self.max_bars_per_key = max_bars_per_key
        
        # Validate timeframes
        for tf in self.timeframes_sec:
            if tf <= 0:
                raise ValueError(f"timeframe_sec must be positive, got {tf}")
        
        # State per (symbol, timeframe_sec) key
        # key -> current incomplete bar
        self._current_bars: Dict[Tuple[str, int], Bar] = {}
        
        # key -> list of completed bars (most recent last)
        self._completed_bars: Dict[Tuple[str, int], List[Bar]] = defaultdict(list)
        
        # key -> last tick timestamp (for out-of-order detection)
        self._last_ts: Dict[Tuple[str, int], int] = {}
        
        # Locks per key for thread safety
        self._locks: Dict[Tuple[str, int], Lock] = defaultdict(Lock)
        
        # Metrics
        self._ticks_processed: int = 0
        self._ticks_dropped_ooo: int = 0  # out-of-order drops
        self._bars_completed: int = 0
        self._events_emitted: int = 0
        
        LOG.info(
            "BarAggregator initialized",
            extra={"timeframes_sec": self.timeframes_sec, "max_bars": max_bars_per_key}
        )
    
    def on_tick(
        self,
        symbol: str,
        price: Decimal,
        volume: Decimal = Decimal("0"),
        ts_ms: Optional[int] = None,
    ) -> List[Bar]:
        """
        Process a tick for all configured timeframes.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            price: Tick price
            volume: Tick volume (default 0)
            ts_ms: Tick timestamp in milliseconds (default: current time)
        
        Returns:
            List of completed bars (one per timeframe that closed)
        """
        if ts_ms is None:
            ts_ms = get_clock().now_ms()
        
        completed = []
        
        for tf_sec in self.timeframes_sec:
            bar = self._process_tick_for_tf(symbol, tf_sec, price, volume, ts_ms)
            if bar is not None:
                completed.append(bar)
        
        return completed
    
    def _process_tick_for_tf(
        self,
        symbol: str,
        tf_sec: int,
        price: Decimal,
        volume: Decimal,
        ts_ms: int,
    ) -> Optional[Bar]:
        """
        Process tick for a specific timeframe.
        
        Returns completed Bar if bar period ended, None otherwise.
        """
        key = (symbol, tf_sec)
        
        with self._locks[key]:
            self._ticks_processed += 1
            
            # Out-of-order check (fail-closed: drop, don't corrupt)
            last_ts = self._last_ts.get(key, 0)
            if ts_ms <= last_ts:
                self._ticks_dropped_ooo += 1
                LOG.debug(
                    "OOO tick dropped",
                    extra={
                        "symbol": symbol,
                        "tf_sec": tf_sec,
                        "tick_ts": ts_ms,
                        "last_ts": last_ts,
                    }
                )
                return None
            
            self._last_ts[key] = ts_ms
            tf_ms = tf_sec * 1000
            
            current = self._current_bars.get(key)
            
            # First tick for this key
            if current is None:
                bar_start = self._align_to_boundary(ts_ms, tf_ms)
                self._current_bars[key] = Bar(
                    symbol=symbol,
                    timeframe_sec=tf_sec,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=volume,
                    trade_count=1,
                    start_ts_ms=bar_start,
                    end_ts_ms=ts_ms,
                )
                return None
            
            # Check if tick belongs to new bar period
            bar_end_ts = current.start_ts_ms + tf_ms
            
            if ts_ms >= bar_end_ts:
                # Close current bar
                current.end_ts_ms = bar_end_ts - 1
                closed_bar = current
                
                # Store completed bar
                completed_list = self._completed_bars[key]
                completed_list.append(closed_bar)
                if len(completed_list) > self.max_bars_per_key:
                    completed_list.pop(0)
                
                self._bars_completed += 1
                
                # Emit EVT:BAR_CLOSED
                self._emit_bar_closed(closed_bar, ts_ms)
                
                # Detect gap
                new_bar_start = self._align_to_boundary(ts_ms, tf_ms)
                expected_next = bar_end_ts
                gap_bars = (new_bar_start - expected_next) // tf_ms
                is_gap = gap_bars > 0
                
                # Start new bar
                self._current_bars[key] = Bar(
                    symbol=symbol,
                    timeframe_sec=tf_sec,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=volume,
                    trade_count=1,
                    start_ts_ms=new_bar_start,
                    end_ts_ms=ts_ms,
                    gap_bars_skipped=int(gap_bars),
                    is_gap_bar=is_gap,
                )
                
                return closed_bar
            
            # Update current bar
            current.close = price
            current.high = max(current.high, price)
            current.low = min(current.low, price)
            current.volume += volume
            current.trade_count += 1
            current.end_ts_ms = ts_ms
            
            return None
    
    def _align_to_boundary(self, ts_ms: int, tf_ms: int) -> int:
        """Align timestamp to bar boundary (floor to timeframe)."""
        return (ts_ms // tf_ms) * tf_ms
    
    def _emit_bar_closed(self, bar: Bar, event_ts_ms: int) -> None:
        """Emit EVT:BAR_CLOSED event."""
        identity = build_canonical_bar_identity(
            symbol=bar.symbol,
            timeframe_sec=int(bar.timeframe_sec),
            bar_start_ts_ms=int(bar.start_ts_ms),
            bar_end_ts_ms=int(bar.end_ts_ms),
            close_boundary_ts_ms=int(bar.start_ts_ms) + int(bar.timeframe_sec) * 1000,
            source_mode=RuntimeBarSourceMode.LIVE,
        )

        # Serialize bar to dict with string decimals (JSON-safe)
        bar_dict = {
            "symbol": bar.symbol,
            "timeframe_sec": bar.timeframe_sec,
            "start_ts_ms": bar.start_ts_ms,
            "end_ts_ms": bar.end_ts_ms,
            "open": str(bar.open),
            "high": str(bar.high),
            "low": str(bar.low),
            "close": str(bar.close),
            "volume": str(bar.volume),
            "trade_count": bar.trade_count,
            "gap_bars_skipped": bar.gap_bars_skipped,
            "is_gap_bar": bar.is_gap_bar,
        }

        # OBS-03-INT: WAL-SSOT for bars
        # Contract: ts_ms, symbol, tf_sec, bar_close_ts, bar{open,high,low,close,volume}, bar_meta(optional)
        wal_payload = {
            "ts_ms": int(event_ts_ms),
            "symbol": bar.symbol,
            "tf_sec": int(bar.timeframe_sec),
            "bar_close_ts": int(bar.end_ts_ms),
            "bar": bar_dict,
            "bar_meta": {
                "source": "bar_aggregator",
                "close_reason": "time_boundary",
                "ticks_in_bar": int(bar.trade_count),
            },
        }
        attach_canonical_bar_payload(
            wal_payload,
            identity=identity,
            replay_generation=0,
        )
        gap_status = extract_gap_status(
            wal_payload,
            default_source="market_data:bar_aggregator",
            default_source_mode=RuntimeBarSourceMode.LIVE,
        )
        if gap_status is not None:
            attach_gap_status_payload(wal_payload, gap=gap_status)

        try:
            msg = Message(
                op="EVT",
                verb="BAR_CLOSED",
                src="market_data",
                dst="any",
                rid=f"bar:{bar.symbol}:{bar.timeframe_sec}:{bar.end_ts_ms}",
                ts=int(event_ts_ms),
                why=truncate_why(f"bar_closed:{bar.timeframe_sec}s:{bar.symbol}"),
                pld=wal_payload,
            )
            wal.append(msg.model_dump())
        except Exception as e:
            LOG.warning(
                "Failed to write BAR_CLOSED to WAL",
                extra={"symbol": bar.symbol, "tf_sec": bar.timeframe_sec, "error": str(e)},
            )

        if self.emit_fn is None:
            return

        # Keep event payload backward compatible for in-process consumers (FE/MR).
        payload = {
            "symbol": bar.symbol,
            "ts_ms": int(event_ts_ms),
            "tf_sec": int(bar.timeframe_sec),
            "bar_close_ts": int(bar.end_ts_ms),
            "bar": bar_dict,
        }
        attach_canonical_bar_payload(
            payload,
            identity=identity,
            replay_generation=0,
        )
        if gap_status is not None:
            attach_gap_status_payload(payload, gap=gap_status)

        why = f"Bar {bar.timeframe_sec}s closed for {bar.symbol}"

        try:
            self.emit_fn("EVT:BAR_CLOSED", payload, why=why)
            self._events_emitted += 1
            LOG.debug(
                "EVT:BAR_CLOSED emitted",
                extra={"symbol": bar.symbol, "tf_sec": bar.timeframe_sec},
            )
        except Exception as e:
            LOG.error(
                f"Failed to emit EVT:BAR_CLOSED: {e}",
                extra={"error": str(e), "symbol": bar.symbol},
                exc_info=True,
            )
    
    # =========================================================================
    # Query methods (for testing and debugging)
    # =========================================================================
    
    def get_current_bar(self, symbol: str, tf_sec: int) -> Optional[Bar]:
        """Get current incomplete bar for (symbol, tf)."""
        return self._current_bars.get((symbol, tf_sec))
    
    def get_completed_bars(
        self, symbol: str, tf_sec: int, n: Optional[int] = None
    ) -> List[Bar]:
        """Get last N completed bars for (symbol, tf)."""
        bars = self._completed_bars.get((symbol, tf_sec), [])
        if n is None:
            return list(bars)
        return bars[-n:]
    
    def get_metrics(self) -> dict:
        """Get aggregator metrics."""
        return {
            "ticks_processed": self._ticks_processed,
            "ticks_dropped_ooo": self._ticks_dropped_ooo,
            "bars_completed": self._bars_completed,
            "events_emitted": self._events_emitted,
            "active_keys": len(self._current_bars),
        }
    
    def reset(self, symbol: Optional[str] = None, tf_sec: Optional[int] = None) -> None:
        """
        Reset aggregator state.
        
        Args:
            symbol: Reset only this symbol (None = all)
            tf_sec: Reset only this timeframe (None = all)
        """
        if symbol is None and tf_sec is None:
            self._current_bars.clear()
            self._completed_bars.clear()
            self._last_ts.clear()
            LOG.info("BarAggregator reset (all)")
            return
        
        keys_to_remove = [
            k for k in self._current_bars.keys()
            if (symbol is None or k[0] == symbol)
            and (tf_sec is None or k[1] == tf_sec)
        ]
        
        for key in keys_to_remove:
            self._current_bars.pop(key, None)
            self._completed_bars.pop(key, None)
            self._last_ts.pop(key, None)
        
        LOG.info(
            "BarAggregator reset (partial)",
            extra={"symbol": symbol, "tf_sec": tf_sec, "keys_removed": len(keys_to_remove)}
        )
    
    # =========================================================================
    # FSM event handler for wiring
    # =========================================================================
    
    def on_market_tick(self, event) -> None:
        """
        FSM event handler for EVT:MARKET_TICK_RECEIVED.
        
        BAR-SSOT-002: Wiring as passive observer on tick stream.
        
        Args:
            event: FSM Message with payload containing tick data
        """
        try:
            pld = event.pld if hasattr(event, 'pld') else event.get('payload', event)
            
            symbol = pld.get('symbol')
            # Payload uses 'ts' (not 'ts_ms'), fallback to 'ts_ms' and 'timestamp'
            ts_ms = pld.get('ts') or pld.get('ts_ms') or pld.get('timestamp')
            
            # Price: prefer mid, fallback to bid/ask average, then last
            price_raw = pld.get('mid') or pld.get('price')
            if price_raw is None:
                bid = pld.get('bid')
                ask = pld.get('ask')
                if bid is not None and ask is not None:
                    price_raw = (Decimal(str(bid)) + Decimal(str(ask))) / 2
                else:
                    price_raw = pld.get('last_price') or pld.get('close')
            
            if symbol is None or ts_ms is None or price_raw is None:
                LOG.debug("BarAggregator: incomplete tick, skipping", extra={"pld": pld})
                return
            
            price = Decimal(str(price_raw))
            volume = Decimal(str(pld.get('volume', 0) or 0))
            
            self.on_tick(symbol, price, volume, int(ts_ms))
            
        except Exception as e:
            LOG.warning(f"BarAggregator.on_market_tick error: {e}", exc_info=True)
