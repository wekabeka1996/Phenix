from __future__ import annotations

import decimal
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Optional

from apps.reference.domains.objective_engine.realized_types import (
    ActiveObjectivePosition,
    ObjectiveSnapshot,
)
from apps.reference.domains.objective_engine.types import ObjectiveTrace


class ObjectiveSnapshotRegistry:
    def __init__(self) -> None:
        self._pending_by_symbol: Dict[str, Deque[ObjectiveSnapshot]] = defaultdict(deque)
        self._active_by_symbol: Dict[str, ActiveObjectivePosition] = {}
        self._latest_regime_by_symbol: Dict[str, str] = {}
        self._close_reason_by_symbol: Dict[str, str] = {}

    def register_trade_intent(self, payload: Dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        strategy_id = str(payload.get("strategy") or "")
        if strategy_id not in {"aurora", "md_amr"}:
            return
        symbol = str(payload.get("instrument") or "")
        trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
        objective_raw = trace.get("objective")
        order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
        if bool(order.get("reduce_only")):
            self._close_reason_by_symbol[symbol] = str((payload.get("why") or ["UNKNOWN_CLOSE"])[-1])
            return
        if not symbol or not isinstance(objective_raw, dict):
            return

        objective_trace = ObjectiveTrace(**objective_raw)
        stop_price_raw = payload.get("stop_price")
        target_price_raw = payload.get("target_price")
        signal_id = None
        if isinstance(trace.get("alpha_search"), dict):
            signal_id = trace["alpha_search"].get("signal_id")

        snapshot = ObjectiveSnapshot(
            strategy_id=strategy_id,
            symbol=symbol,
            entry_rid=str(payload.get("rid") or ""),
            entry_side=str(payload.get("side") or "").upper(),
            intent_ts_ms=int(payload.get("decision_ts_ms") or payload.get("ts_ms") or 0),
            entry_price=decimal.Decimal(str(order.get("price_ref") or order.get("price"))),
            stop_price=decimal.Decimal(str(stop_price_raw)) if stop_price_raw not in (None, "", "None") else None,
            target_price=decimal.Decimal(str(target_price_raw)) if target_price_raw not in (None, "", "None") else None,
            tf_sec=int(payload.get("tf_sec")) if payload.get("tf_sec") is not None else None,
            regime_entry=str(payload.get("regime") or "UNKNOWN"),
            pretrade_objective_trace=objective_trace,
            signal_id=signal_id,
        )
        self._pending_by_symbol[symbol].append(snapshot)

    def note_regime(self, *, symbol: str, regime: str) -> None:
        if not symbol or not regime:
            return
        self._latest_regime_by_symbol[symbol] = regime
        active = self._active_by_symbol.get(symbol)
        if active is None:
            return
        if active.last_regime is None:
            active.last_regime = regime
            active.regime_exit = regime
            return
        if regime != active.last_regime:
            active.regime_path_changes += 1
            active.last_regime = regime
            active.regime_exit = regime

    def note_market_tick(self, *, symbol: str, price: decimal.Decimal) -> None:
        active = self._active_by_symbol.get(symbol)
        if active is None:
            return
        active.highest_price = max(active.highest_price, price)
        active.lowest_price = min(active.lowest_price, price)

    def on_trade_executed(self, payload: Dict[str, Any]) -> list[tuple[ActiveObjectivePosition, decimal.Decimal, decimal.Decimal, int, str]]:
        if not isinstance(payload, dict):
            return []
        symbol = str(payload.get("symbol") or "")
        side = str(payload.get("side") or "").lower()
        if not symbol or side not in {"buy", "sell"}:
            return []
        qty = decimal.Decimal(str(payload.get("quantity") or "0"))
        price = decimal.Decimal(str(payload.get("price") or "0"))
        fees = decimal.Decimal(str(payload.get("fees") or "0"))
        ts_ms = int(payload.get("ts") or payload.get("ts_ms") or 0)
        if qty <= 0 or price <= 0 or ts_ms <= 0:
            return []

        signed_trade_qty = qty if side == "buy" else -qty
        active = self._active_by_symbol.get(symbol)
        if active is None:
            pending = self._pending_by_symbol.get(symbol)
            if not pending:
                return []
            snapshot = pending.popleft()
            active = ActiveObjectivePosition(
                snapshot=snapshot,
                signed_qty=signed_trade_qty,
                avg_entry_price=price,
                open_ts_ms=ts_ms,
                last_fill_ts_ms=ts_ms,
                highest_price=price,
                lowest_price=price,
                accrued_fees=fees,
                regime_exit=self._latest_regime_by_symbol.get(symbol, snapshot.regime_entry),
                last_regime=self._latest_regime_by_symbol.get(symbol, snapshot.regime_entry),
            )
            self._active_by_symbol[symbol] = active
            return []

        active.last_fill_ts_ms = ts_ms
        active.accrued_fees += fees
        active.highest_price = max(active.highest_price, price)
        active.lowest_price = min(active.lowest_price, price)

        if active.signed_qty == 0:
            active.signed_qty = signed_trade_qty
            active.avg_entry_price = price
            return []

        if active.signed_qty * signed_trade_qty > 0:
            prior_abs = abs(active.signed_qty)
            new_abs = abs(active.signed_qty + signed_trade_qty)
            if new_abs > 0:
                active.avg_entry_price = (
                    (active.avg_entry_price * prior_abs) + (price * abs(signed_trade_qty))
                ) / new_abs
            active.signed_qty += signed_trade_qty
            return []

        close_qty = min(abs(active.signed_qty), abs(signed_trade_qty))
        close_reason = self._close_reason_by_symbol.get(symbol, "POSITION_UPDATE")
        realized_payload = [(active, close_qty, price, ts_ms, close_reason)]
        active.signed_qty += signed_trade_qty
        if abs(active.signed_qty) <= decimal.Decimal("1e-9"):
            del self._active_by_symbol[symbol]
            self._close_reason_by_symbol.pop(symbol, None)
        else:
            active.highest_price = price
            active.lowest_price = price
            active.open_ts_ms = ts_ms
            active.avg_entry_price = price
            active.accrued_fees = decimal.Decimal("0")
        return realized_payload
