"""
FIX-LIFECYCLE-01: Trade Lifecycle Logger — Source of Truth per Trade.

Aggregates intent → order → fill → brackets (SL/TP) → close → PnL
into a single JSONL record per trade, keyed by `rid` (request ID).

Usage:
    from apps.reference.telemetry.trade_lifecycle_logger import trade_lifecycle

    # On intent emission:
    trade_lifecycle.on_intent(rid=rid, symbol=symbol, side=side, regime=regime,
                              confidence=confidence, strategy_id=strategy_id,
                              signal_score=signal_score, entry_type=entry_type)

    # On order placed:
    trade_lifecycle.on_order_placed(rid=rid, order_id=order_id, price=price)

    # On fill:
    trade_lifecycle.on_fill(rid=rid, fill_price=fill_price, fill_qty=fill_qty, fees=fees)

    # On SL/TP set:
    trade_lifecycle.on_brackets_set(rid=rid, sl_price=sl_price, tp_price=tp_price,
                                     sl_pct=sl_pct, tp_pct=tp_pct)

    # On close (SL hit, TP hit, manual, regime flip, etc.):
    trade_lifecycle.on_close(rid=rid, close_price=close_price, close_reason=close_reason,
                             pnl_pct=pnl_pct, pnl_usdt=pnl_usdt)

    # On cancel (order never filled):
    trade_lifecycle.on_cancel(rid=rid, cancel_reason=cancel_reason)

Output: logs/trade_lifecycle.jsonl — one line per trade with full lifecycle.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Optional

LOG = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Single trade lifecycle record — source of truth."""

    # Identity
    rid: str = ""
    symbol: str = ""
    strategy_id: str = ""

    # Intent
    side: str = ""               # LONG / SHORT
    regime: str = ""
    regime_confidence: Optional[float] = None
    signal_score: Optional[float] = None
    entry_type: str = ""         # LIMIT / MARKET
    intent_ts_ms: int = 0

    # Order
    order_id: str = ""
    order_price: Optional[float] = None
    order_ts_ms: int = 0

    # Fill
    fill_price: Optional[float] = None
    fill_qty: Optional[float] = None
    fill_fees: Optional[float] = None
    fill_ts_ms: int = 0

    # Brackets
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    sl_pct: Optional[float] = None
    tp_pct: Optional[float] = None

    # Close
    close_price: Optional[float] = None
    close_reason: str = ""       # SL_HIT, TP_HIT, REGIME_FLIP, MANUAL, CANCEL, TTL_EXPIRED
    close_ts_ms: int = 0
    pnl_pct: Optional[float] = None
    pnl_usdt: Optional[float] = None

    # Status
    status: str = "INTENT"       # INTENT → ORDERED → FILLED → CLOSED / CANCELLED

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Drop None values for compact JSONL
        return {k: v for k, v in d.items() if v is not None and v != "" and v != 0}


class TradeLifecycleLogger:
    """
    In-memory aggregator + JSONL writer for trade lifecycle records.

    Each trade is tracked by `rid`. Lifecycle events update the record.
    On close/cancel, the final record is flushed to JSONL and removed from memory.
    """

    def __init__(self, log_file: str = "logs/trade_lifecycle.jsonl"):
        self._log_file = Path(log_file)
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        self._trades: Dict[str, TradeRecord] = {}

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def _get_or_create(self, rid: str) -> TradeRecord:
        if rid not in self._trades:
            self._trades[rid] = TradeRecord(rid=rid)
        return self._trades[rid]

    def _flush(self, rid: str) -> None:
        """Write final record to JSONL and remove from memory."""
        rec = self._trades.pop(rid, None)
        if rec is None:
            return
        try:
            line = json.dumps(rec.to_dict(), ensure_ascii=False, default=str)
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            LOG.warning(f"TradeLifecycleLogger: failed to flush rid={rid}: {e}")

    # ─── Lifecycle events ──────────────────────────────────────

    def on_intent(
        self,
        rid: str,
        symbol: str = "",
        side: str = "",
        regime: str = "",
        confidence: Optional[float] = None,
        signal_score: Optional[float] = None,
        strategy_id: str = "",
        entry_type: str = "",
    ) -> None:
        """Record trade intent emission."""
        rec = self._get_or_create(rid)
        rec.symbol = symbol
        rec.side = side
        rec.regime = regime
        rec.regime_confidence = confidence
        rec.signal_score = signal_score
        rec.strategy_id = strategy_id
        rec.entry_type = entry_type
        rec.intent_ts_ms = self._now_ms()
        rec.status = "INTENT"

    def on_order_placed(
        self,
        rid: str,
        order_id: str = "",
        price: Optional[float] = None,
    ) -> None:
        """Record order placement."""
        rec = self._get_or_create(rid)
        rec.order_id = order_id
        rec.order_price = price
        rec.order_ts_ms = self._now_ms()
        rec.status = "ORDERED"

    def on_fill(
        self,
        rid: str,
        fill_price: Optional[float] = None,
        fill_qty: Optional[float] = None,
        fees: Optional[float] = None,
    ) -> None:
        """Record order fill."""
        rec = self._get_or_create(rid)
        rec.fill_price = fill_price
        rec.fill_qty = fill_qty
        rec.fill_fees = fees
        rec.fill_ts_ms = self._now_ms()
        rec.status = "FILLED"

    def on_brackets_set(
        self,
        rid: str,
        sl_price: Optional[float] = None,
        tp_price: Optional[float] = None,
        sl_pct: Optional[float] = None,
        tp_pct: Optional[float] = None,
    ) -> None:
        """Record SL/TP brackets."""
        rec = self._get_or_create(rid)
        if sl_price is not None:
            rec.sl_price = sl_price
        if tp_price is not None:
            rec.tp_price = tp_price
        if sl_pct is not None:
            rec.sl_pct = sl_pct
        if tp_pct is not None:
            rec.tp_pct = tp_pct

    def on_close(
        self,
        rid: str,
        close_price: Optional[float] = None,
        close_reason: str = "",
        pnl_pct: Optional[float] = None,
        pnl_usdt: Optional[float] = None,
    ) -> None:
        """Record trade close and flush to JSONL."""
        rec = self._get_or_create(rid)
        rec.close_price = close_price
        rec.close_reason = close_reason
        rec.close_ts_ms = self._now_ms()
        rec.pnl_pct = pnl_pct
        rec.pnl_usdt = pnl_usdt
        rec.status = "CLOSED"
        self._flush(rid)

    def on_cancel(
        self,
        rid: str,
        cancel_reason: str = "",
    ) -> None:
        """Record order cancellation and flush to JSONL."""
        rec = self._get_or_create(rid)
        rec.close_reason = cancel_reason
        rec.close_ts_ms = self._now_ms()
        rec.status = "CANCELLED"
        self._flush(rid)

    def flush_all(self) -> int:
        """Flush all remaining open records (e.g. at shutdown). Returns count."""
        rids = list(self._trades.keys())
        for rid in rids:
            rec = self._trades[rid]
            if rec.status not in ("CLOSED", "CANCELLED"):
                rec.status = "ORPHANED"
            self._flush(rid)
        return len(rids)

    @property
    def open_trades(self) -> int:
        """Number of currently tracked (unflushed) trades."""
        return len(self._trades)


# ─── Module-level singleton (like order_logger) ─────────────────
trade_lifecycle = TradeLifecycleLogger()
