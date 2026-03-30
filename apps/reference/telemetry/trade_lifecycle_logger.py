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
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from vfoundation.obs.xai_store import append_why
except Exception:
    append_why = None

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
    reject_reason_code: str = ""
    reject_stage: str = ""

    # Status
    status: str = "INTENT"       # INTENT → ORDERED → FILLED → CLOSED / CANCELLED
    created_ts_ms: int = 0
    updated_ts_ms: int = 0
    prior_terminal_status: str = ""
    prior_terminal_reason: str = ""
    reconciliation_source: str = ""
    reconciliation_ts_ms: int = 0

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

    def __init__(
        self,
        log_file: str = "logs/trade_lifecycle.jsonl",
        orphan_ttl_sec: int = 3600,
        max_open_trades: int = 5000,
        auto_sweep_interval_sec: int = 60,
    ):
        self._log_file = Path(log_file)
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        self._orphan_ttl_sec = max(0, int(orphan_ttl_sec))
        self._max_open_trades = max(1, int(max_open_trades))
        self._auto_sweep_interval_sec = max(1, int(auto_sweep_interval_sec))
        self._next_sweep_at = time.time() + self._auto_sweep_interval_sec
        self._trades: "OrderedDict[str, TradeRecord]" = OrderedDict()
        self._recent_terminal: "OrderedDict[str, TradeRecord]" = OrderedDict()

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def _create_record(self, rid: str) -> TradeRecord:
        now_ms = self._now_ms()
        rec = TradeRecord(
            rid=rid,
            created_ts_ms=now_ms,
            updated_ts_ms=now_ms,
        )
        self._trades[rid] = rec
        return rec

    def _reopen_terminal_if_needed(self, rid: str, *, source: str) -> Optional[TradeRecord]:
        prior = self._recent_terminal.get(rid)
        if prior is None or prior.status != "REJECTED":
            return None
        now_ms = self._now_ms()
        restored = TradeRecord(**asdict(prior))
        restored.status = "INTENT"
        restored.close_price = None
        restored.close_reason = ""
        restored.close_ts_ms = 0
        restored.pnl_pct = None
        restored.pnl_usdt = None
        restored.updated_ts_ms = now_ms
        restored.prior_terminal_status = prior.status
        restored.prior_terminal_reason = prior.close_reason
        restored.reconciliation_source = source
        restored.reconciliation_ts_ms = now_ms
        self._trades[rid] = restored
        self._trades.move_to_end(rid)
        return restored

    def _get_or_create(self, rid: str, *, source: str = "") -> TradeRecord:
        self._maybe_sweep()
        if rid not in self._trades:
            reopened = None
            if source in {"order_placed", "fill", "close"}:
                reopened = self._reopen_terminal_if_needed(rid, source=source)
            if reopened is None:
                self._create_record(rid)
        rec = self._trades[rid]
        rec.updated_ts_ms = self._now_ms()
        self._trades.move_to_end(rid)
        self._enforce_capacity()
        return rec

    def _remember_terminal(self, rec: TradeRecord) -> None:
        self._recent_terminal[rec.rid] = TradeRecord(**asdict(rec))
        self._recent_terminal.move_to_end(rec.rid)
        while len(self._recent_terminal) > self._max_open_trades:
            self._recent_terminal.popitem(last=False)

    def _maybe_sweep(self) -> None:
        now = time.time()
        if now >= self._next_sweep_at:
            self.sweep_expired()
            self._next_sweep_at = now + self._auto_sweep_interval_sec

    def _enforce_capacity(self) -> None:
        while len(self._trades) > self._max_open_trades:
            oldest_rid = next(iter(self._trades.keys()))
            rec = self._trades.get(oldest_rid)
            if rec is not None and rec.status not in ("CLOSED", "CANCELLED"):
                rec.status = "ORPHANED_LRU"
                rec.close_reason = "LRU_EVICTED"
                rec.close_ts_ms = self._now_ms()
            self._flush(oldest_rid)

    def sweep_expired(self) -> int:
        """Flush stale open records older than orphan_ttl_sec. Returns count."""
        if self._orphan_ttl_sec <= 0:
            return 0
        now_ms = self._now_ms()
        cutoff_ms = now_ms - (self._orphan_ttl_sec * 1000)
        expired_rids = [
            rid
            for rid, rec in list(self._trades.items())
            if rec.status not in ("CLOSED", "CANCELLED") and rec.updated_ts_ms > 0 and rec.updated_ts_ms <= cutoff_ms
        ]
        for rid in expired_rids:
            rec = self._trades.get(rid)
            if rec is not None:
                rec.status = "ORPHANED_TTL"
                rec.close_reason = f"TTL_EXPIRED_{self._orphan_ttl_sec}s"
                rec.close_ts_ms = now_ms
            self._flush(rid)
        return len(expired_rids)

    def _flush(self, rid: str) -> None:
        """Write final record to JSONL and remove from memory."""
        rec = self._trades.pop(rid, None)
        if rec is None:
            return
        self._remember_terminal(rec)
        try:
            line = json.dumps(rec.to_dict(), ensure_ascii=False, default=str)
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            if append_why is not None:
                lifecycle_verb = "CANCEL" if rec.status == "CANCELLED" else "CLOSE"
                append_why(
                    rid=rec.rid,
                    verb=lifecycle_verb,
                    why=rec.close_reason or rec.status,
                    payload_summary=f"{rec.symbol}:{rec.side}",
                    meta={
                        "status": rec.status,
                        "strategy_id": rec.strategy_id,
                        "entry_type": rec.entry_type,
                    },
                )
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
        rec = self._get_or_create(rid, source="intent")
        rec.symbol = symbol
        rec.side = side
        rec.regime = regime
        rec.regime_confidence = confidence
        rec.signal_score = signal_score
        rec.strategy_id = strategy_id
        rec.entry_type = entry_type
        rec.intent_ts_ms = self._now_ms()
        rec.updated_ts_ms = rec.intent_ts_ms
        rec.status = "INTENT"

    def on_order_placed(
        self,
        rid: str,
        order_id: str = "",
        price: Optional[float] = None,
    ) -> None:
        """Record order placement."""
        rec = self._get_or_create(rid, source="order_placed")
        rec.order_id = order_id
        rec.order_price = price
        rec.order_ts_ms = self._now_ms()
        rec.updated_ts_ms = rec.order_ts_ms
        rec.status = "ORDERED"

    def on_fill(
        self,
        rid: str,
        fill_price: Optional[float] = None,
        fill_qty: Optional[float] = None,
        fees: Optional[float] = None,
    ) -> None:
        """Record order fill."""
        rec = self._get_or_create(rid, source="fill")
        rec.fill_price = fill_price
        rec.fill_qty = fill_qty
        rec.fill_fees = fees
        rec.fill_ts_ms = self._now_ms()
        rec.updated_ts_ms = rec.fill_ts_ms
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
        rec = self._get_or_create(rid, source="brackets")
        if sl_price is not None:
            rec.sl_price = sl_price
        if tp_price is not None:
            rec.tp_price = tp_price
        if sl_pct is not None:
            rec.sl_pct = sl_pct
        if tp_pct is not None:
            rec.tp_pct = tp_pct
        rec.updated_ts_ms = self._now_ms()

    def on_close(
        self,
        rid: str,
        close_price: Optional[float] = None,
        close_reason: str = "",
        pnl_pct: Optional[float] = None,
        pnl_usdt: Optional[float] = None,
    ) -> None:
        """Record trade close and flush to JSONL."""
        rec = self._get_or_create(rid, source="close")
        rec.close_price = close_price
        rec.close_reason = close_reason
        rec.close_ts_ms = self._now_ms()
        rec.updated_ts_ms = rec.close_ts_ms
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
        rec = self._get_or_create(rid, source="cancel")
        rec.close_reason = cancel_reason
        rec.close_ts_ms = self._now_ms()
        rec.updated_ts_ms = rec.close_ts_ms
        rec.status = "CANCELLED"
        self._flush(rid)

    def on_reject(
        self,
        rid: str,
        reject_reason: str = "",
        reject_reason_code: str = "",
        reject_stage: str = "",
    ) -> None:
        """Record trade intent rejection and flush to JSONL."""
        rec = self._get_or_create(rid, source="reject")
        rec.close_reason = reject_reason
        rec.reject_reason_code = reject_reason_code
        rec.reject_stage = reject_stage
        rec.close_ts_ms = self._now_ms()
        rec.updated_ts_ms = rec.close_ts_ms
        rec.status = "REJECTED"
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
