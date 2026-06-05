from __future__ import annotations

import decimal
import logging
from typing import Any, Dict

from vfoundation.dr import wal

from apps.reference.config_models import AuroraConfig
from apps.reference.domains.objective_engine.posttrade_evaluator import evaluate_realized_quality
from apps.reference.domains.objective_engine.snapshot_registry import ObjectiveSnapshotRegistry


LOG = logging.getLogger(__name__)


class ObjectiveEngineRuntime:
    def __init__(self, *, fsm: Any, config: AuroraConfig) -> None:
        self.fsm = fsm
        self.config = config
        self.logger = LOG.getChild("ObjectiveEngineRuntime")
        self.registry = ObjectiveSnapshotRegistry()

        if not bool(getattr(config.domains.objective_engine, "enabled", False)):
            return
        self.fsm.listen("EVT:TRADE_INTENT_PROPOSED", self._on_trade_intent_proposed)
        self.fsm.listen("EVT:TRADE_EXECUTED", self._on_trade_executed)
        self.fsm.listen("EVT:REGIME_DETECTED", self._on_regime_detected)
        self.fsm.listen("EVT:MARKET_TICK_RECEIVED", self._on_market_tick)

    def _extract_payload(self, event: Any) -> Dict[str, Any]:
        if hasattr(event, "pld"):
            payload = event.pld
        else:
            payload = event
        return payload if isinstance(payload, dict) else {}

    def _on_trade_intent_proposed(self, event: Any) -> None:
        payload = self._extract_payload(event)
        self.registry.register_trade_intent(payload)

    def _on_regime_detected(self, event: Any) -> None:
        payload = self._extract_payload(event)
        symbol = str(payload.get("symbol") or "")
        regime = str(payload.get("regime") or payload.get("overall_regime") or "")
        if symbol and regime:
            self.registry.note_regime(symbol=symbol, regime=regime)

    def _on_market_tick(self, event: Any) -> None:
        payload = self._extract_payload(event)
        symbol = str(payload.get("symbol") or "")
        price_raw = payload.get("price") or payload.get("mid")
        if not symbol or price_raw in (None, "", "0", 0):
            return
        try:
            price = decimal.Decimal(str(price_raw))
        except Exception:
            return
        if price <= 0:
            return
        self.registry.note_market_tick(symbol=symbol, price=price)

    def _on_trade_executed(self, event: Any) -> None:
        payload = self._extract_payload(event)
        realized_candidates = self.registry.on_trade_executed(payload)
        for active, close_qty, exit_price, ts_ms, close_reason in realized_candidates:
            close_rid = str(payload.get("rid") or payload.get("order_id") or f"close-{active.snapshot.entry_rid}-{ts_ms}")
            realized = evaluate_realized_quality(
                active=active,
                close_rid=close_rid,
                exit_price=exit_price,
                close_ts_ms=ts_ms,
                closed_qty=close_qty,
                close_reason=close_reason,
            )
            event_payload = realized.model_dump()
            try:
                wal.append(
                    {
                        "op": "EVT",
                        "verb": "OBJECTIVE_REALIZED_V1",
                        "pld": event_payload,
                        "src": "objective_engine",
                        "dst": "*",
                        "timestamp": int(ts_ms),
                    }
                )
            except Exception as exc:
                self.logger.warning("Failed to write objective realized WAL: %s", exc)
            self.fsm.emit(
                "EVT:OBJECTIVE_REALIZED_V1",
                payload=event_payload,
                why="objective_realized",
            )
