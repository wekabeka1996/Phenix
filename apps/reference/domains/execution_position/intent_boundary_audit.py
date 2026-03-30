"""
Execution-boundary audit for TRADE_INTENT_PROPOSED.

Tracks whether intents are routed into execution and whether execution emits
downstream order/reject progress events. Silent drops are converted into the
existing EVT:TRADE_INTENT_REJECTED contract.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

from apps.reference.core.time import get_clock
from apps.reference.domains.execution_position.trade_intent_reject_contracts import (
    emit_canonical_trade_intent_rejected_event,
)

LOG = logging.getLogger(__name__)


@dataclass
class PendingTradeIntent:
    rid: str
    symbol: str
    strategy_id: Optional[str]
    side: Optional[str]
    created_ts_ms: int
    routed_ts_ms: Optional[int] = None
    routed_via: Optional[str] = None


class IntentBoundaryAudit:
    """Audits TRADE_INTENT_PROPOSED -> execution progress."""

    def __init__(
        self,
        *,
        bus: Any,
        config: Any = None,
        logger: logging.Logger | None = None,
        lifecycle: Any = None,
        write_wal: bool = False,
    ) -> None:
        self._bus = bus
        self._logger = logger or LOG
        self._trade_lifecycle = lifecycle
        self._write_wal = bool(write_wal)
        self._enabled = self._coerce_bool(
            getattr(config, "enabled", True) if config is not None else True,
            default=True,
        )
        self._route_ttl_ms = self._coerce_int(
            getattr(config, "route_ttl_ms", 2000) if config is not None else 2000,
            default=2000,
        )
        self._downstream_ttl_ms = self._coerce_int(
            getattr(config, "downstream_ttl_ms", 5000) if config is not None else 5000,
            default=5000,
        )
        base_interval_ms = max(100, min(self._route_ttl_ms, self._downstream_ttl_ms) // 4)
        self._sleep_interval_sec = min(base_interval_ms, 1000) / 1000.0
        self._pending: dict[str, PendingTradeIntent] = {}
        self._stop_requested = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def get_pending(self, rid: str) -> PendingTradeIntent | None:
        return self._pending.get(str(rid))

    def register_bus_listeners(self) -> None:
        if not self._enabled or not hasattr(self._bus, "listen"):
            return
        self._bus.listen("EVT:TRADE_INTENT_PROPOSED", self._on_trade_intent_proposed)
        self._bus.listen("EVT:TRADE_INTENT_REJECTED", self._on_terminal_event)
        self._bus.listen("EVT:ORDER_PLACED", self._on_terminal_event)
        self._bus.listen("EVT:ORDER_REJECTED", self._on_terminal_event)
        self._bus.listen("EVT:ORDER_STATE_CHANGED", self._on_terminal_event)
        self._bus.listen("EVT:ORDER_ACK", self._on_terminal_event)
        self._bus.listen("EVT:ORDER_FILL", self._on_terminal_event)
        self._bus.listen("EVT:TRADE_EXECUTED", self._on_terminal_event)

    def mark_routed(
        self,
        *,
        rid: str,
        symbol: str,
        route: str,
        strategy_id: str | None = None,
        side: str | None = None,
    ) -> None:
        if not self._enabled:
            return
        rid_str = str(rid or "").strip()
        symbol_str = str(symbol or "").strip()
        if not rid_str or not symbol_str:
            return
        now_ms = get_clock().now_ms()
        entry = self._pending.get(rid_str)
        if entry is None:
            entry = PendingTradeIntent(
                rid=rid_str,
                symbol=symbol_str,
                strategy_id=str(strategy_id) if strategy_id else None,
                side=self._normalize_side(side),
                created_ts_ms=now_ms,
            )
            self._pending[rid_str] = entry
        if strategy_id and not entry.strategy_id:
            entry.strategy_id = str(strategy_id)
        if side:
            entry.side = self._normalize_side(side)
        entry.routed_ts_ms = now_ms
        entry.routed_via = str(route)

    async def run_forever(self) -> None:
        if not self._enabled:
            return
        self._logger.info(
            "IntentBoundaryAudit started route_ttl_ms=%d downstream_ttl_ms=%d",
            self._route_ttl_ms,
            self._downstream_ttl_ms,
        )
        while not self._stop_requested:
            self.sweep()
            await asyncio.sleep(self._sleep_interval_sec)

    def stop(self) -> None:
        self._stop_requested = True

    def sweep(self, now_ms: int | None = None) -> None:
        if not self._enabled:
            return
        current_ts = int(now_ms or get_clock().now_ms())
        expirations: list[tuple[PendingTradeIntent, str, str]] = []
        for entry in list(self._pending.values()):
            if entry.routed_ts_ms is None:
                if current_ts - entry.created_ts_ms >= self._route_ttl_ms:
                    expirations.append(
                        (
                            entry,
                            "NRR-EXECUTION-BRIDGE-TIMEOUT",
                            "trade_intent_boundary_audit:bridge_timeout",
                        )
                    )
                continue
            if current_ts - entry.routed_ts_ms >= self._downstream_ttl_ms:
                expirations.append(
                    (
                        entry,
                        "NRR-EXECUTION-NO-DOWNSTREAM-EVENT",
                        "trade_intent_boundary_audit:no_downstream_event",
                    )
                )

        for entry, reason_code, why in expirations:
            if self._pending.pop(entry.rid, None) is None:
                continue
            self._emit_execution_reject(
                entry=entry,
                reason_code=reason_code,
                why=why,
                ts_ms=current_ts,
            )

    def _on_trade_intent_proposed(self, event: Any) -> None:
        if not self._enabled:
            return
        pld = self._extract_payload(event)
        if not isinstance(pld, dict):
            return
        rid = str(pld.get("rid") or getattr(event, "rid", "") or "").strip()
        symbol = str(pld.get("symbol") or pld.get("instrument") or "").strip()
        if not rid or not symbol:
            return
        self._pending[rid] = PendingTradeIntent(
            rid=rid,
            symbol=symbol,
            strategy_id=self._extract_strategy_id(pld),
            side=self._normalize_side(pld.get("side")),
            created_ts_ms=self._extract_ts_ms(pld, event),
        )

    def _on_terminal_event(self, event: Any) -> None:
        if not self._enabled:
            return
        pld = self._extract_payload(event)
        if not isinstance(pld, dict):
            return
        rid = str(pld.get("rid") or getattr(event, "rid", "") or "").strip()
        if rid:
            self._pending.pop(rid, None)

    def _emit_execution_reject(
        self,
        *,
        entry: PendingTradeIntent,
        reason_code: str,
        why: str,
        ts_ms: int,
    ) -> None:
        details = {
            "route_ttl_ms": self._route_ttl_ms,
            "downstream_ttl_ms": self._downstream_ttl_ms,
            "created_ts_ms": entry.created_ts_ms,
            "routed_ts_ms": entry.routed_ts_ms,
            "routed_via": entry.routed_via,
        }
        payload: dict[str, Any] = {
            "ts_ms": ts_ms,
            "symbol": entry.symbol,
            "reason_code": reason_code,
            "stage": "EXECUTION",
            "why": why,
            "context": "trade_intent_boundary_audit",
            "why_chain": [
                "trade_intent_boundary_audit",
                f"rid:{entry.rid}",
                f"reason:{reason_code}",
            ],
            "rid": entry.rid,
            "details": details,
        }
        if entry.strategy_id:
            payload["strategy_id"] = entry.strategy_id
        if entry.side in {"buy", "sell"}:
            payload["side"] = entry.side
        self._logger.warning(
            "[%s] IntentBoundaryAudit terminal reject rid=%s reason=%s route=%s",
            entry.symbol,
            entry.rid,
            reason_code,
            entry.routed_via,
        )
        emit_canonical_trade_intent_rejected_event(
            fsm=self._bus,
            payload=payload,
            rid=entry.rid,
            src="execution_position",
            why=why,
            logger=self._logger,
            lifecycle=self._trade_lifecycle,
            write_wal=self._write_wal,
            fallback_symbol=entry.symbol,
            fallback_reason_code=reason_code,
            fallback_stage="EXECUTION",
            fallback_why=why,
            data_ref=["trade_intent_boundary_audit", reason_code],
        )

    @staticmethod
    def _extract_payload(event: Any) -> Any:
        if isinstance(event, dict):
            return event
        return getattr(event, "pld", None)

    @staticmethod
    def _extract_ts_ms(pld: dict[str, Any], event: Any) -> int:
        raw_ts = pld.get("ts_ms") or pld.get("bar_close_ts") or getattr(event, "ts", None)
        try:
            ts_ms = int(raw_ts)
        except Exception:
            ts_ms = 0
        return ts_ms if ts_ms > 0 else int(get_clock().now_ms())

    @staticmethod
    def _extract_strategy_id(pld: dict[str, Any]) -> str | None:
        raw = pld.get("strategy_id") or pld.get("strategy")
        if raw is None:
            return None
        text = str(raw).strip()
        return text or None

    @staticmethod
    def _normalize_side(side: Any) -> str | None:
        if side is None:
            return None
        text = str(side).strip().lower()
        return text if text in {"buy", "sell"} else None

    @staticmethod
    def _coerce_bool(value: Any, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        return default

    @staticmethod
    def _coerce_int(value: Any, *, default: int) -> int:
        if isinstance(value, bool):
            return default
        if not isinstance(value, (int, float, str)):
            return default
        try:
            parsed = int(value)
        except Exception:
            return default
        return parsed if parsed > 0 else default
