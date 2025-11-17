"""
OrderGuardian Service - Centralized order/position monitor & cleanup.

Responsibilities:
- Owns mapping (clientOrderId <-> orderId) and bracket linkage per entry.
- Tracks active positions and associated orders.
- Safe cleanup of bracket orders with ownership validation.
- Writes audit trail to logs/order_guardian.log

Architecture:
- Adapter: transport layer (place/cancel/get/openOrders/positionRisk)
- OrderGuardian: domain logic for ownership/cleanup
- FSM: business signals, delegates cleanup to OrderGuardian
"""

import os
import asyncio
import json
import logging
import time
from dataclasses import dataclass, asdict, is_dataclass
from typing import Dict, Any, List, Optional, Protocol, Union, TypeAlias, Iterable, Set, Sequence, Tuple

from apps.reference.adapters.binance_adapter import BinanceAPIError
from decimal import Decimal
import threading

# Try to import ExchangePosition for better typing
try:
    from vfoundation.core.adapters.base import ExchangePosition
except ImportError:
    # Fallback if vfoundation not available
    ExchangePosition = None  # type: ignore[misc,assignment]

# Define PositionType based on availability
if ExchangePosition is not None:
    PositionType = Union[Dict[str, Any],
                         ExchangePosition]  # type: ignore[misc]
else:
    PositionType = Dict[str, Any]  # type: ignore[misc]

PositionTypeAlias: TypeAlias = PositionType  # type: ignore[misc]

# Setup dedicated logger for OrderGuardian
LOG = logging.getLogger("order_guardian")
LOG.setLevel(logging.INFO)

# Create file handler for order_guardian.log
log_dir = os.path.join(os.path.dirname(__file__), "../../../logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "order_guardian.log")

file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
LOG.addHandler(file_handler)

agg_oco_logger = logging.getLogger("agg_oco")


class AdapterProtocol(Protocol):
    """Protocol for adapter interface required by OrderGuardian"""

    async def get_open_orders(
        self, symbol: Optional[str] = None) -> List[Dict[str, Any]]: ...

    async def get_open_positions(self) -> List[PositionType]: ...

    async def cancel_order(
        self, symbol: str, order_id: str) -> Dict[str, Any]: ...
    async def get_order(self, symbol: str,
                        order_id: str) -> Dict[str, Any]: ...


class StoreProtocol(Protocol):
    """Protocol for pluggable storage"""

    def get(self, key: str) -> Any: ...
    def put(self, key: str, value: Any) -> None: ...
    def delete(self, key: str) -> None: ...


@dataclass
class OrderInfo:
    """Order information stored in guardian"""
    symbol: str
    side: str
    qty: float
    order_type: str
    reduce_only: bool = False
    close_position: bool = False
    parent_entry_id: Optional[str] = None  # orderId of parent entry
    ts: Optional[float] = None

    def __post_init__(self):
        if self.ts is None:
            self.ts = time.time()


class InMemoryStore:
    """Simple in-memory store implementation"""

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data.get(key)

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)


@dataclass
class BracketSetMeta:
    """Metadata describing the aggregated bracket set for (symbol, side)."""

    bracket_set_id: str
    symbol: str
    side: str
    sl_order_id: Optional[str]
    tp_order_id: Optional[str]
    created_ts: float
    version: int = 0


@dataclass
class AggregatedOcoGuardianConfig:
    """Config knob set for aggregated OCO cleanup semantics."""

    enabled: bool = False
    ttl_protect_new_bracket_ms: int = 0
    allow_unprotected_position: bool = False


class OrderGuardian:
    """
    Centralized order/position monitor & cleanup.

    Owns mapping (clientOrderId <-> orderId) and bracket linkage per entry.
    Writes to logs/order_guardian.log with structured JSON events.
    """

    def __init__(
        self,
        adapter: Optional[AdapterProtocol],
        clock=None,
        store: Optional[StoreProtocol] = None,
        poll_interval_ms: int = 500,
        bus: Optional[Any] = None,
        config: Optional[Any] = None,
        aggregated_oco_cfg: Optional[AggregatedOcoGuardianConfig] = None,
    ):
        self.adapter = adapter
        self.clock = clock or time
        self.store = store or InMemoryStore()
        # When adapter is None (shadow mode), set a longer default poll interval
        # to avoid aggressive polling in test environments while keeping a sane
        # default for production. If user explicitly provided a positive
        # poll_interval_ms, respect it. If they provided 0 or negative, set to
        # 5000ms for shadow mode.
        if self.adapter is None and (poll_interval_ms is None or poll_interval_ms <= 0):
            self.poll_interval_ms = 5000
        else:
            self.poll_interval_ms = poll_interval_ms
        self.bus = bus  # Optional event bus for EVT:SYMBOL_TIDY etc.
        self._cfg = config or {}
        self._known_symbols: Set[str] = set()
        self._metrics: Dict[str, Any] = {
            "guardian_orphans_cancelled_total": 0,
            "guardian_cleanup_cycles_total": 0,
            "guardian_linked_from_rest_total": 0,
            "guardian_cleanup_tidy_ms": {},
            "guardian_poll_last_duration_ms": 0,
        }
        self._last_cycle_started_ms: float = 0.0

        self._aggregated_oco_cfg = aggregated_oco_cfg or AggregatedOcoGuardianConfig()

        # Aggregated bracket sets keyed by (symbol, side)
        self._bracket_sets: Dict[tuple[str, str], BracketSetMeta] = {}

        if config:
            try:
                self.update_known_symbols(
                    self._extract_symbols_from_config(config))
            except Exception:
                pass

        # Core storage: entry_id -> {symbol, side, qty, ts, brackets:{sl:..., tp:...}}
        # clientOrderId -> orderId mapping
        # orderId -> metadata (symbol, type, reduceOnly, closePosition, parent_entry_id)

        # Poller setup (optional, off by default)
        self._poller_task: Optional[asyncio.Task] = None
        if poll_interval_ms > 0:
            # Could start poller here, but keeping off by default as requested
            pass

        LOG.info("OrderGuardian initialized", extra={
            "event_type": "guardian_init",
            "poll_interval_ms": poll_interval_ms
        })

    # --- Aggregated OCO state accessors ---

    def register_bracket_set(
        self,
        *,
        bracket_set_id: str,
        symbol: str,
        side: str,
        sl_order_id: Optional[str],
        tp_order_id: Optional[str],
        created_ts: float,
    ) -> BracketSetMeta:
        """Register or update the aggregated bracket set metadata for (symbol, side)."""

        key = self._symbol_side_key(symbol, side)
        prev = self._bracket_sets.get(key)
        version = 0 if prev is None else prev.version + 1

        meta = BracketSetMeta(
            bracket_set_id=bracket_set_id,
            symbol=key[0],
            side=key[1],
            sl_order_id=sl_order_id,
            tp_order_id=tp_order_id,
            created_ts=created_ts,
            version=version,
        )
        self._bracket_sets[key] = meta
        return meta

    def _symbol_side_key(self, symbol: str, side: str) -> tuple[str, str]:
        return (str(symbol or "").upper(), self._normalize_side(side))

    @staticmethod
    def _normalize_side(side: Optional[str]) -> str:
        normalized = (side or "").upper()
        if normalized == "BUY":
            return "LONG"
        if normalized == "SELL":
            return "SHORT"
        return normalized

    def get_active_bracket_set(self, symbol: str, side: str) -> Optional[BracketSetMeta]:
        """Return the active BracketSetMeta for (symbol, side) if registered."""

        return self._bracket_sets.get(self._symbol_side_key(symbol, side))

    def clear_bracket_set_for_position(self, *, symbol: str, side: str) -> None:
        """Remove any tracked bracket set metadata for (symbol, side)."""

        self._bracket_sets.pop(self._symbol_side_key(symbol, side), None)

    def list_all_bracket_sets(self) -> List[BracketSetMeta]:
        """Return a shallow copy list of all known bracket set metadata objects."""

        return list(self._bracket_sets.values())

    def rehydrate_bracket_set_for_position(
        self,
        *,
        symbol: str,
        side: str,
        position_amt: float,
        open_orders: Sequence[Any],
        now_ts: Optional[float] = None,
    ) -> Optional[BracketSetMeta]:
        """Reconstruct aggregated bracket metadata from live open orders."""

        cfg = self._aggregated_oco_cfg
        if not cfg.enabled:
            return None

        try:
            abs_position = abs(float(position_amt or 0.0))
        except (TypeError, ValueError):
            abs_position = 0.0

        if abs_position <= 0:
            return None

        existing = self.get_active_bracket_set(symbol, side)
        if existing:
            return existing

        candidates = self._select_bracket_orders_for_symbol_side(
            symbol=symbol,
            side=side,
            open_orders=open_orders or [],
        )
        if not candidates:
            return None

        grouped: Dict[str, Dict[str, Any]] = {}
        for _raw_order, normalized in candidates:
            client_id = normalized.get("clientOrderId") or ""
            base_id = self._extract_bracket_base_from_client_id(client_id)
            if not base_id:
                continue

            entry = grouped.setdefault(
                base_id,
                {"base_id": base_id, "sl": None, "tp": None, "ts": 0.0},
            )

            client_id_lower = str(client_id).lower()
            if client_id_lower.endswith("_sl"):
                entry["sl"] = normalized
            elif client_id_lower.endswith("_tp"):
                entry["tp"] = normalized
            else:
                continue
            entry["ts"] = max(
                entry["ts"], self._extract_order_timestamp(normalized))

        valid_groups = [g for g in grouped.values() if g.get("sl")
                        or g.get("tp")]
        if not valid_groups:
            return None

        best_group = max(valid_groups, key=lambda group: group.get("ts", 0.0))
        now = now_ts if now_ts is not None else self.clock.time()

        bracket_set_id = best_group.get("base_id") or self._build_rehydrated_bracket_id(
            symbol,
            side,
            now,
        )
        sl_order = best_group.get("sl")
        tp_order = best_group.get("tp")
        sl_order_id = str(sl_order.get("orderId")
                          ) if sl_order and sl_order.get("orderId") else None
        tp_order_id = str(tp_order.get("orderId")
                          ) if tp_order and tp_order.get("orderId") else None

        meta = self.register_bracket_set(
            bracket_set_id=bracket_set_id,
            symbol=symbol,
            side=side,
            sl_order_id=sl_order_id,
            tp_order_id=tp_order_id,
            created_ts=now,
        )

        LOG.info(
            "[GUARD] Rehydrated aggregated bracket set",
            extra={
                "event_type": "agg_oco_rehydrate",
                "symbol": symbol,
                "side": side,
                "bracket_set_id": bracket_set_id,
                "sl_order_id": sl_order_id,
                "tp_order_id": tp_order_id,
            },
        )

        return meta

    @staticmethod
    def _clip_guard_why(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return str(value)[:80]

    def _emit_guard_event(
        self,
        *,
        symbol: str,
        side: str,
        meta: Optional[BracketSetMeta],
        position_amt: float,
        decision: str,
        extra_cancelled: int,
        has_sl_after: Optional[bool],
        why: Optional[str],
        rid: Optional[str] = None,
    ) -> None:
        extra = {
            "event_type": "AGG_OCO_BRACKET_GUARD",
            "symbol": symbol,
            "side": side,
            "bracket_set_id": getattr(meta, "bracket_set_id", None),
            "position_amt": str(position_amt) if position_amt is not None else None,
            "decision": decision,
            "extra_cancelled": extra_cancelled,
            "has_sl_after": bool(has_sl_after),
            "why": self._clip_guard_why(why),
            "rid": rid,
        }
        agg_oco_logger.info("Aggregated OCO guardian decision", extra=extra)

    @staticmethod
    def _extract_bracket_base_from_client_id(client_order_id: Optional[str]) -> Optional[str]:
        if not client_order_id:
            return None
        cid = str(client_order_id)
        lowered = cid.lower()
        if lowered.endswith("_sl") or lowered.endswith("_tp"):
            return cid[:-3]
        return None

    @staticmethod
    def _extract_order_timestamp(normalized: Dict[str, Any]) -> float:
        for key in ("updateTime", "time", "timestamp", "ts"):
            value = normalized.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                try:
                    return float(str(value))
                except (TypeError, ValueError):
                    continue
        return 0.0

    @staticmethod
    def _build_rehydrated_bracket_id(symbol: str, side: str, now_ts: float) -> str:
        suffix = int(max(now_ts, 0) * 1000)
        return f"rehydrated:{symbol.upper()}:{side.upper()}:{suffix}"

    def ensure_single_bracket_set_for_position(
        self,
        *,
        symbol: str,
        side: str,
        position_amt: float,
        open_orders: Sequence[Any],
        now_ts: Optional[float] = None,
    ) -> int:
        """Perform aggregated cleanup ensuring a single bracket set per (symbol, side)."""

        cfg = self._aggregated_oco_cfg
        if not cfg.enabled:
            return 0

        norm_side = self._normalize_side(side)
        key = self._symbol_side_key(symbol, norm_side)
        meta = self._bracket_sets.get(key)
        if not meta:
            self._emit_guard_event(
                symbol=symbol,
                side=norm_side,
                meta=None,
                position_amt=position_amt,
                decision="no_meta_state",
                extra_cancelled=0,
                has_sl_after=False,
                why="no_meta_registered",
            )
            return 0

        try:
            abs_position = abs(float(position_amt or 0.0))
        except (TypeError, ValueError):
            abs_position = 0.0

        candidates = self._select_bracket_orders_for_symbol_side(
            symbol=symbol,
            side=norm_side,
            open_orders=open_orders or [],
        )

        if abs_position == 0:
            cancelled = 0
            for raw_order, normalized in candidates:
                if self._cancel_order_safe(
                    raw_order,
                    reason="agg_oco_cleanup_zero_position",
                    normalized=normalized,
                ):
                    cancelled += 1

            if cancelled:
                LOG.info(
                    "[GUARD] Aggregated zero-position cleanup cancelled brackets",
                    extra={
                        "event_type": "agg_oco_zero_position_cleanup",
                        "symbol": symbol,
                        "side": norm_side,
                        "cancelled": cancelled,
                    },
                )

            self._emit_guard_event(
                symbol=symbol,
                side=norm_side,
                meta=meta,
                position_amt=position_amt,
                decision="cleanup_zero_position",
                extra_cancelled=cancelled,
                has_sl_after=False,
                why="position_amt_zero",
            )
            self.clear_bracket_set_for_position(symbol=symbol, side=norm_side)
            return cancelled

        if not candidates:
            return 0

        now = now_ts if now_ts is not None else self.clock.time()
        if cfg.ttl_protect_new_bracket_ms > 0:
            age_ms = max(0.0, (now - meta.created_ts) * 1000.0)
            if age_ms < cfg.ttl_protect_new_bracket_ms:
                LOG.debug(
                    "[GUARD] Aggregated TTL guard skipping cleanup",
                    extra={
                        "event_type": "agg_oco_ttl_guard",
                        "symbol": symbol,
                        "side": norm_side,
                        "age_ms": age_ms,
                        "ttl_ms": cfg.ttl_protect_new_bracket_ms,
                    },
                )
                self._emit_guard_event(
                    symbol=symbol,
                    side=norm_side,
                    meta=meta,
                    position_amt=position_amt,
                    decision="ttl_skip",
                    extra_cancelled=0,
                    has_sl_after=bool(meta.sl_order_id),
                    why=f"age_ms={int(age_ms)} ttl_ms={cfg.ttl_protect_new_bracket_ms}",
                )
                return 0

        protected_ids = {
            str(meta.sl_order_id) if meta.sl_order_id else None,
            str(meta.tp_order_id) if meta.tp_order_id else None,
        }

        to_cancel: List[Tuple[Any, Dict[str, Any]]] = []
        for raw_order, normalized in candidates:
            order_id = normalized.get("orderId")
            if order_id is None:
                continue
            order_id_str = str(order_id)
            if order_id_str in protected_ids:
                continue
            to_cancel.append((raw_order, normalized))

        if not to_cancel:
            return 0

        if abs_position > 0 and not cfg.allow_unprotected_position:
            remaining_sl = [
                normalized
                for raw_order, normalized in candidates
                if self._is_sl_order(normalized) and (raw_order, normalized) not in to_cancel
            ]
            if not remaining_sl:
                LOG.warning(
                    "[GUARD] Fail-closed guard prevented aggregated cleanup",
                    extra={
                        "event_type": "agg_oco_fail_closed",
                        "symbol": symbol,
                        "side": norm_side,
                        "position_amt": position_amt,
                    },
                )
                self._emit_guard_event(
                    symbol=symbol,
                    side=norm_side,
                    meta=meta,
                    position_amt=position_amt,
                    decision="skip_to_keep_sl",
                    extra_cancelled=0,
                    has_sl_after=False,
                    why="fail_closed_guard",
                )
                return 0

        cancelled = 0
        for raw_order, normalized in to_cancel:
            scheduled = self._cancel_order_safe(
                raw_order,
                reason="agg_oco_cleanup_extra_bracket",
                normalized=normalized,
            )
            if scheduled:
                cancelled += 1

        if cancelled:
            LOG.info(
                "[GUARD] Aggregated cleanup scheduled duplicate brackets",
                extra={
                    "event_type": "agg_oco_cleanup",
                    "symbol": symbol,
                    "side": norm_side,
                    "cancelled": cancelled,
                },
            )
            self._emit_guard_event(
                symbol=symbol,
                side=norm_side,
                meta=meta,
                position_amt=position_amt,
                decision="cleanup_extras",
                extra_cancelled=cancelled,
                has_sl_after=bool(meta.sl_order_id),
                why="cleanup_extra_brackets",
            )

        return cancelled

    def _select_bracket_orders_for_symbol_side(
        self,
        *,
        symbol: str,
        side: str,
        open_orders: Sequence[Any],
    ) -> List[Tuple[Any, Dict[str, Any]]]:
        """Return bracket-like orders for the requested (symbol, side)."""

        selected: List[Tuple[Any, Dict[str, Any]]] = []
        symbol_upper = symbol.upper()
        for raw_order in open_orders:
            normalized = self._normalize_order_payload(raw_order)
            if not normalized:
                continue
            order_symbol = str(normalized.get("symbol") or "").upper()
            if order_symbol and order_symbol != symbol_upper:
                continue
            if not self._is_bracket_candidate(normalized):
                continue
            if not self._matches_requested_position_side(normalized, side):
                continue
            selected.append((raw_order, normalized))
        return selected

    @staticmethod
    def _boolish(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "y"}
        return bool(value)

    def _is_bracket_candidate(self, normalized_order: Dict[str, Any]) -> bool:
        reduce_only = self._boolish(normalized_order.get("reduceOnly"))
        close_position = self._boolish(normalized_order.get("closePosition"))
        return reduce_only or close_position

    def _matches_requested_position_side(self, normalized_order: Dict[str, Any], desired_side: str) -> bool:
        desired = (desired_side or "").upper()
        if not desired:
            return True

        order_side = str(
            normalized_order.get("positionSide")
            or normalized_order.get("side")
            or ""
        ).upper()

        if not order_side:
            return True

        if order_side in {"LONG", "SHORT"}:
            return order_side == desired

        if order_side in {"BUY", "SELL"}:
            if desired == "LONG":
                return order_side == "SELL"
            if desired == "SHORT":
                return order_side == "BUY"

        return True

    def _is_sl_order(self, normalized_order: Dict[str, Any]) -> bool:
        kind = str(normalized_order.get("kind") or "").upper()
        order_type = str(normalized_order.get("type") or "").upper()
        if kind in {"SL", "STOP", "STOP_MARKET", "STOP_LOSS"}:
            return True
        if "STOP" in order_type:
            return True
        return False

    def _cancel_order_safe(
        self,
        order: Any,
        *,
        reason: str,
        normalized: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Best-effort cancellation helper that tolerates missing adapter/state."""

        normalized_payload = normalized or self._normalize_order_payload(order)
        if not normalized_payload:
            return False

        order_id = normalized_payload.get("orderId")
        symbol = normalized_payload.get("symbol")
        if not order_id or not symbol:
            return False

        if not self.adapter:
            LOG.debug(
                "[GUARD] No adapter available for cancel request",
                extra={
                    "event_type": "agg_oco_cancel_skip",
                    "symbol": symbol,
                    "order_id": order_id,
                    "reason": reason,
                },
            )
            return False

        async def _perform_cancel() -> None:
            try:
                result = await self.adapter.cancel_order(str(symbol), str(order_id))
                if self._is_successful_cancel(result):
                    LOG.info(
                        "[GUARD] Cancelled bracket during aggregated cleanup",
                        extra={
                            "event_type": "agg_oco_cancelled",
                            "symbol": symbol,
                            "order_id": order_id,
                            "reason": reason,
                        },
                    )
                else:
                    LOG.warning(
                        "[GUARD] Aggregated cleanup cancel returned non-success",
                        extra={
                            "event_type": "agg_oco_cancel_failed",
                            "symbol": symbol,
                            "order_id": order_id,
                            "reason": reason,
                            "result": result,
                        },
                    )
            except Exception as exc:  # pragma: no cover - network path
                LOG.warning(
                    "[GUARD] Aggregated cleanup cancel errored",
                    extra={
                        "event_type": "agg_oco_cancel_error",
                        "symbol": symbol,
                        "order_id": order_id,
                        "reason": reason,
                        "error": str(exc),
                    },
                )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and not loop.is_closed():
            loop.create_task(_perform_cancel())
        else:  # pragma: no cover - fallback path
            asyncio.run(_perform_cancel())

        return True

    def _extract_position_amount_for_side(
        self,
        *,
        positions: Sequence[PositionTypeAlias],
        symbol: str,
        side: str,
    ) -> float:
        """Best-effort extraction of absolute position amount for a given side."""

        desired = (side or "").upper()
        target_symbol = symbol.upper()

        for pos in positions:
            pos_symbol = None
            pos_side_attr = None
            amount_value: Any = 0.0

            if hasattr(pos, "symbol"):
                pos_symbol = getattr(pos, "symbol")
            elif isinstance(pos, dict):
                pos_symbol = pos.get("symbol")

            if not pos_symbol or str(pos_symbol).upper() != target_symbol:
                continue

            if hasattr(pos, "position_side"):
                pos_side_attr = getattr(pos, "position_side")
            elif hasattr(pos, "positionSide"):
                pos_side_attr = getattr(pos, "positionSide")
            elif isinstance(pos, dict):
                pos_side_attr = pos.get(
                    "positionSide") or pos.get("position_side")

            if hasattr(pos, "position_amount"):
                amount_value = getattr(pos, "position_amount")
            elif hasattr(pos, "positionAmt"):
                amount_value = getattr(pos, "positionAmt")
            elif isinstance(pos, dict):
                amount_value = (
                    pos.get("position_amount")
                    or pos.get("positionAmt")
                    or pos.get("amount")
                )

            try:
                amount = float(amount_value or 0.0)
            except (TypeError, ValueError):
                amount = 0.0

            pos_side = str(pos_side_attr or "").upper()
            if pos_side:
                if pos_side == desired:
                    return abs(amount)
                continue

            if desired == "LONG" and amount > 0:
                return amount
            if desired == "SHORT" and amount < 0:
                return abs(amount)

        return 0.0

    # ---- Registration API ----

    def register_entry(
        self,
        *,
        symbol: str,
        order_id: str,
        client_order_id: str,
        side: str,
        qty: float,
        corr_id: Optional[str] = None,
        rid: Optional[str] = None,
        ts: Optional[float] = None
    ) -> None:
        """Register entry order after successful placement"""
        ts = ts or self.clock.time()

        self.update_known_symbols([symbol])

        # Store entry info
        entry_key = f"entry:{order_id}"
        entry_data: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "filled_qty": 0.0,  # additive: track cumulative fills
            "remaining_qty": float(qty),
            "ts": ts,
            "corr_id": corr_id,
            "rid": rid,
            "brackets": {}
        }
        self.store.put(entry_key, entry_data)

        # Store mappings
        self.store.put(f"client:{client_order_id}", order_id)
        self.store.put(f"order:{order_id}", {
            "symbol": symbol,
            "type": "MARKET",  # Assume MARKET entry
            "reduce_only": False,
            "close_position": False,
            "parent_entry_id": None,
            "corr_id": corr_id,
            "rid": rid
        })

        LOG.info(f"Entry registered: {order_id} ({symbol})", extra={
            "event_type": "register_entry",
            "symbol": symbol,
            "order_id": order_id,
            "client_order_id": client_order_id,
            "side": side,
            "qty": qty,
            "filled_qty": 0.0,
            "corr_id": corr_id,
            "rid": rid
        })

    def on_fill(self, *, symbol: str, parent_order_id: str, filled_qty: float) -> None:
        """Update cumulative fill state for a tracked entry.

        Safe no-op if entry is unknown. Never raises.
        """
        try:
            entry_key = f"entry:{parent_order_id}"
            entry_data: Optional[Dict[str, Any]] = self.store.get(entry_key)
            if not entry_data:
                return

            if str(entry_data.get("symbol", "")).upper() != str(symbol).upper():
                # Symbol mismatch – keep defensive but still update
                pass

            prev_filled = float(entry_data.get("filled_qty", 0.0) or 0.0)
            qty_total = float(entry_data.get("qty", 0.0) or 0.0)
            new_filled = max(0.0, prev_filled + float(filled_qty or 0.0))
            if qty_total > 0:
                new_filled = min(new_filled, qty_total)
            remaining = max(0.0, qty_total - new_filled)

            entry_data["filled_qty"] = new_filled
            entry_data["remaining_qty"] = remaining
            self.store.put(entry_key, entry_data)

            LOG.info("Entry fill updated", extra={
                "event_type": "entry_fill_update",
                "symbol": symbol,
                "parent_order_id": parent_order_id,
                "filled_qty": new_filled,
                "remaining_qty": remaining,
            })
        except Exception:
            # Best-effort only
            pass

    def register_bracket(
        self,
        *,
        symbol: str,
        parent_order_id: str,
        order_id: str,
        client_order_id: str,
        kind: str,  # "SL" or "TP"
        corr_id: Optional[str] = None,
        rid: Optional[str] = None,
        reduce_only: bool = True,
        close_position: bool = True
    ) -> None:
        """Register bracket order with link to parent entry"""
        # Update entry brackets mapping for get_brackets_for_entry compatibility
        entry_key = f"entry:{parent_order_id}"
        entry_data: Optional[Dict[str, Any]] = self.store.get(entry_key)
        if entry_data:
            if "brackets" not in entry_data:
                entry_data["brackets"] = {}
            entry_data["brackets"][kind.lower()] = {
                "order_id": order_id,
                "client_order_id": client_order_id,
                "kind": kind
            }
            self.store.put(entry_key, entry_data)

        self.update_known_symbols([symbol])

        # Store mappings
        self.store.put(f"client:{client_order_id}", order_id)
        self.store.put(f"order:{order_id}", {
            "symbol": symbol,
            "type": "STOP_MARKET" if kind == "SL" else "TAKE_PROFIT_MARKET",
            "reduce_only": reduce_only,
            "close_position": close_position,
            "parent_entry_id": parent_order_id,
            "client_order_id": client_order_id,
            "kind": kind,
            "corr_id": corr_id,
            "rid": rid
        })

        LOG.info(f"Bracket registered: {order_id} ({kind} for {parent_order_id})", extra={
            "event_type": "register_bracket",
            "symbol": symbol,
            "parent_order_id": parent_order_id,
            "order_id": order_id,
            "client_order_id": client_order_id,
            "kind": kind,
            "reduce_only": reduce_only,
            "close_position": close_position,
            "corr_id": corr_id,
            "rid": rid
        })

    def update_order_with_exchange_id(
        self,
        internal_order_id: str,
        exchange_order_id: str,
        symbol: str,
        corr_id: Optional[str] = None
    ) -> None:
        """Update order metadata with exchange order ID after successful placement"""
        # Get existing metadata
        existing_meta = self.store.get(f"order:{internal_order_id}")
        if not existing_meta:
            LOG.warning(
                f"No metadata found for internal order {internal_order_id}, cannot update exchange ID")
            return

        # Update with exchange order ID
        updated_meta = dict(existing_meta)
        updated_meta["exchange_order_id"] = exchange_order_id

        # Store under exchange order ID
        self.store.put(f"order:{exchange_order_id}", updated_meta)

        # Keep mapping from internal to exchange ID
        self.store.put(f"internal:{internal_order_id}", exchange_order_id)

        LOG.info(f"Order updated with exchange ID: {internal_order_id} -> {exchange_order_id} ({symbol})", extra={
            "event_type": "update_exchange_id",
            "internal_order_id": internal_order_id,
            "exchange_order_id": exchange_order_id,
            "symbol": symbol,
            "corr_id": corr_id
        })

    def register_brackets(
        self,
        *,
        symbol: str,
        entry_order_id: str,
        sl_order_id: Optional[str] = None,
        tp_order_id: Optional[str] = None,
        sl_client_id: Optional[str] = None,
        tp_client_id: Optional[str] = None,
        corr_id: Optional[str] = None,
        rid: Optional[str] = None
    ) -> None:
        """Register SL and TP brackets for entry order"""
        if sl_order_id and sl_client_id:
            self.register_bracket(
                symbol=symbol,
                parent_order_id=entry_order_id,
                order_id=sl_order_id,
                client_order_id=sl_client_id,
                kind="SL",
                corr_id=corr_id,
                rid=rid
            )
        if tp_order_id and tp_client_id:
            self.register_bracket(
                symbol=symbol,
                parent_order_id=entry_order_id,
                order_id=tp_order_id,
                client_order_id=tp_client_id,
                kind="TP",
                corr_id=corr_id,
                rid=rid
            )

    def update_known_symbols(self, symbols: Iterable[str]) -> None:
        """Add configured symbols to internal registry for polling."""
        try:
            normalized = {str(sym).upper() for sym in symbols if sym}
            if normalized:
                self._known_symbols.update(normalized)
        except Exception:
            pass

    def _extract_symbols_from_config(self, cfg: Any) -> Set[str]:
        """Best-effort extraction of instrument symbols from config structures."""
        symbols: Set[str] = set()

        try:
            if isinstance(cfg, dict):
                trading = cfg.get("trading") or {}
                if isinstance(trading, dict):
                    instruments = trading.get("instruments") or {}
                    if isinstance(instruments, dict):
                        symbols.update(str(s).upper()
                                       for s in instruments.keys())
            else:
                trading = getattr(cfg, "trading", None)
                if trading:
                    instruments = getattr(trading, "instruments", None)
                    if isinstance(instruments, dict):
                        symbols.update(str(s).upper()
                                       for s in instruments.keys())
        except Exception:
            pass

        return symbols

    def _iter_symbols_for_poll(self) -> List[str]:
        """Resolve symbols for polling loop (config + store fallbacks)."""
        symbols = set(self._known_symbols)

        # Fallback: inspect store for tracked order metadata
        try:
            raw_store = getattr(self.store, "_data", {})
            if isinstance(raw_store, dict):
                for meta in raw_store.values():
                    if isinstance(meta, dict):
                        sym = meta.get("symbol")
                        if sym:
                            symbols.add(str(sym).upper())
        except Exception:
            pass

        return sorted(symbols)

    def _normalize_order_payload(self, raw_order: Any) -> Optional[Dict[str, Any]]:
        """Coerce adapter order payloads into dicts with Binance-style keys."""
        if isinstance(raw_order, dict):
            normalized: Dict[str, Any] = dict(raw_order)
        else:
            normalized: Optional[Dict[str, Any]] = None

            if hasattr(raw_order, "to_dict"):
                try:
                    maybe_dict = raw_order.to_dict()
                    if isinstance(maybe_dict, dict):
                        normalized = dict(maybe_dict)
                except Exception:
                    normalized = None

            if normalized is None:
                if is_dataclass(raw_order):
                    try:
                        normalized = dict(asdict(raw_order))
                    except Exception:
                        normalized = None
                elif hasattr(raw_order, "__dict__"):
                    normalized = dict(vars(raw_order))

            if normalized is None:
                LOG.debug(
                    "[GUARD] Unable to normalize order payload: %s", raw_order)
                return None

            # Work on a copy to avoid mutating shared structures
            normalized = dict(normalized)

        # Align common aliases to Binance REST keys expected by guardian logic
        if "orderId" not in normalized and "order_id" in normalized:
            normalized["orderId"] = normalized.get("order_id")
        if "clientOrderId" not in normalized and "client_order_id" in normalized:
            normalized["clientOrderId"] = normalized.get("client_order_id")
        if "symbol" not in normalized and normalized.get("symbol_id"):
            normalized["symbol"] = normalized.get("symbol_id")
        if "type" not in normalized and "order_type" in normalized:
            normalized["type"] = normalized.get("order_type")
        if "status" not in normalized and "state" in normalized:
            normalized["status"] = normalized.get("state")
        if "time" not in normalized and "timestamp_ms" in normalized:
            normalized["time"] = normalized.get("timestamp_ms")
        if "origQty" not in normalized and "quantity" in normalized:
            normalized["origQty"] = normalized.get("quantity")
        if "executedQty" not in normalized and "filled_qty" in normalized:
            normalized["executedQty"] = normalized.get("filled_qty")
        if "reduceOnly" not in normalized and "reduce_only" in normalized:
            normalized["reduceOnly"] = normalized.get("reduce_only")
        if "closePosition" not in normalized and "close_position" in normalized:
            normalized["closePosition"] = normalized.get("close_position")

        return normalized

    async def _startup_relink_known_symbols(self) -> None:
        """Perform best-effort re-link on startup for all known symbols."""
        if not self.adapter:
            return

        for sym in self._iter_symbols_for_poll():
            try:
                await self.link_existing_from_rest(sym)
            except Exception as exc:
                LOG.warning(f"[GUARD] Startup re-link failed for {sym}: {exc}")

    @staticmethod
    def _is_guardian_client_order_id(client_order_id: Optional[str]) -> bool:
        """Fallback heuristic to identify guardian-managed client order ids."""
        if not client_order_id:
            return False

        cid = str(client_order_id).upper()
        guardian_prefixes = ("SL-", "TP-", "RID-",
                             "ENTRY-", "CLOSE-", "GUARD-")
        return cid.startswith(guardian_prefixes)

    async def link_existing_from_rest(self, symbol: str) -> None:
        """Builds mapping from /openOrders for existing orders"""
        if not self.adapter:
            LOG.debug("No adapter available, skipping link_existing_from_rest")
            return

        try:
            # Get all open orders for symbol
            open_orders = await self.adapter.get_open_orders(symbol)

            linked_count = 0
            for raw_order in open_orders:
                order = self._normalize_order_payload(raw_order)
                if not order:
                    continue

                order_id = order.get("orderId")
                client_order_id = order.get("clientOrderId")

                if not order_id or not client_order_id:
                    continue

                # Skip if already tracked
                if self.store.get(f"order:{order_id}"):
                    continue

                # Determine if this is a bracket order
                is_reduce_only_raw = order.get("reduceOnly", False)
                is_close_position_raw = order.get("closePosition", False)
                is_reduce_only = str(is_reduce_only_raw).lower() == "true" if isinstance(
                    is_reduce_only_raw, str) else bool(is_reduce_only_raw)
                is_close_position = str(is_close_position_raw).lower() == "true" if isinstance(
                    is_close_position_raw, str) else bool(is_close_position_raw)
                order_type = order.get("type", "")

                guardian_like = self._is_guardian_client_order_id(
                    client_order_id)

                if is_reduce_only or is_close_position or order_type in ("STOP_MARKET", "TAKE_PROFIT_MARKET") or guardian_like:
                    # This looks like a bracket - store basic metadata
                    # Note: we can't determine parent_entry_id from order data alone
                    self.store.put(f"order:{order_id}", {
                        "symbol": symbol,
                        "type": order_type,
                        "reduce_only": is_reduce_only,
                        "close_position": is_close_position,
                        "parent_entry_id": None  # Unknown without additional context
                    })

                    # Store client order mapping if available
                    if client_order_id:
                        self.store.put(f"client:{client_order_id}", order_id)

                    linked_count += 1
                    self.update_known_symbols([symbol])

            if linked_count:
                self._metrics["guardian_linked_from_rest_total"] += linked_count

            LOG.info("[GUARD] Linked existing orders from REST", extra={
                "event_type": "link_existing",
                "symbol": symbol,
                "linked_count": linked_count
            })

        except Exception as e:
            LOG.error(f"Failed to link existing orders for {symbol}: {e}")

    # ---- Query API ----

    def get_brackets_for_entry(self, parent_order_id: str) -> Dict[str, Any]:
        """Get bracket orders for entry"""
        entry_key = f"entry:{parent_order_id}"
        entry_data: Optional[Dict[str, Any]] = self.store.get(entry_key)
        if entry_data:
            return entry_data.get("brackets", {})
        return {}

    async def get_our_open_brackets(self, symbol: str) -> List[Dict[str, Any]]:
        """Get our open bracket orders for symbol"""
        if not self.adapter:
            LOG.debug(
                "No adapter available, returning empty list for get_our_open_brackets")
            return []

        try:
            # Get all open orders for symbol
            open_orders = await self.adapter.get_open_orders(symbol)

            our_brackets = []
            for raw_order in open_orders:
                order = self._normalize_order_payload(raw_order)
                if not order:
                    continue

                order_id = order.get("orderId")
                if not order_id:
                    continue

                # Check if this is our tracked order
                order_meta = self.store.get(f"order:{order_id}")
                if not order_meta:
                    continue

                # Check if it's a bracket (reduceOnly or closePosition)
                if order_meta.get("reduce_only") or order_meta.get("close_position"):
                    # Add metadata to order info
                    bracket_info = dict(order)
                    bracket_info.update({
                        "parent_entry_id": order_meta.get("parent_entry_id"),
                        "tracked_by_guardian": True
                    })
                    our_brackets.append(bracket_info)

            return our_brackets

        except Exception as e:
            LOG.error(f"Failed to get open brackets for {symbol}: {e}")
            return []

    async def should_place_brackets(self, symbol: str, entry_order_id: str) -> bool:
        """
        Check if brackets (TP/SL) should be placed for the given entry order.

        Returns True if brackets can be placed, False otherwise.
        This is a safety check to prevent placing brackets when position is closing
        or other conflicting conditions exist.
        """
        if not self.adapter:
            LOG.debug(
                "No adapter available, allowing bracket placement by default")
            return True

        try:
            # Check if position exists for this symbol
            positions = await self.adapter.get_open_positions()
            position_amt = 0.0

            for pos in positions:
                # Handle both dict and ExchangePosition objects
                if hasattr(pos, 'symbol'):
                    pos_symbol = pos.symbol  # type: ignore[union-attr]
                    # type: ignore[union-attr]
                    pos_amt = float(pos.position_amount)
                else:
                    # type: ignore[union-attr]
                    pos_symbol = pos.get("symbol", "")
                    pos_amt = float(pos.get("position_amount")  # type: ignore[union-attr]
                                    or pos.get("positionAmt") or 0)  # type: ignore[union-attr]

                if pos_symbol == symbol:
                    position_amt = pos_amt
                    break

            has_position = abs(position_amt) >= 1e-10

            if not has_position:
                LOG.warning(
                    f"OrderGuardian: No position found for {symbol}, blocking bracket placement")
                return False

            # Check if we have entry order metadata
            entry_meta = self.store.get(f"order:{entry_order_id}")
            if not entry_meta:
                LOG.warning(
                    f"OrderGuardian: No entry metadata found for order {entry_order_id}, allowing bracket placement")
                return True

            # Check for conflicting conditions (e.g., closePosition flag)
            if entry_meta.get("close_position"):
                LOG.warning(
                    f"OrderGuardian: Entry order {entry_order_id} has close_position=True, blocking bracket placement")
                return False

            LOG.debug(
                f"OrderGuardian: Allowing bracket placement for {symbol} entry {entry_order_id}")
            return True

        except Exception as e:
            LOG.error(
                f"OrderGuardian: Error checking bracket placement permission for {symbol}: {e}")
            # On error, allow placement to avoid blocking trades
            return True

    # ---- Cleanup API ----

    async def cleanup_before_close(
        self,
        symbol: str,
        parent_order_id: Optional[str] = None
    ) -> int:
        """
        Cancel only our brackets tied to entry or all ours for symbol.

        Returns count of cancelled orders.
        """
        if not self.adapter:
            LOG.debug("No adapter available, skipping cleanup_before_close")
            return 0

        cancelled_count = 0

        try:
            if parent_order_id:
                # Cancel brackets for specific entry
                brackets = self.get_brackets_for_entry(parent_order_id)
                for bracket_type, bracket_info in brackets.items():
                    order_id = bracket_info["order_id"]
                    try:
                        result = await self.adapter.cancel_order(symbol, order_id)
                        if self._is_successful_cancel(result):
                            cancelled_count += 1
                            LOG.info("Bracket cancelled for entry", extra={
                                "event_type": "cleanup_before_close",
                                "symbol": symbol,
                                "parent_order_id": parent_order_id,
                                "bracket_order_id": order_id,
                                "bracket_type": bracket_type
                            })
                    except Exception as e:
                        LOG.warning(
                            f"Failed to cancel bracket {order_id}: {e}")
            else:
                # Cancel all our brackets for symbol
                # This would need to scan all stored brackets for the symbol
                pass

        except Exception as e:
            LOG.error(f"Cleanup before close failed: {e}")

        return cancelled_count

    async def close_entry(self, *, symbol: str, parent_order_id: str) -> Dict[str, Any]:
        """Cancel brackets for an entry and report remaining qty/side.

        This method does NOT place a close order; caller should place a reduce-only
        order for the returned remaining_qty if > 0.
        """
        cancelled = await self.cleanup_before_close(symbol, parent_order_id)

        entry_key = f"entry:{parent_order_id}"
        entry_data: Optional[Dict[str, Any]] = self.store.get(entry_key)
        side = None
        remaining = 0.0
        if entry_data:
            side = entry_data.get("side")
            try:
                remaining = float(entry_data.get("remaining_qty") or 0.0)
            except Exception:
                remaining = 0.0

        LOG.info("Entry close prepared", extra={
            "event_type": "entry_close_prepare",
            "symbol": symbol,
            "parent_order_id": parent_order_id,
            "cancelled_brackets": cancelled,
            "remaining_qty": remaining,
            "side": side,
        })

        return {
            "cancelled_brackets": cancelled,
            "remaining_qty": remaining,
            "side": side,
        }

    def list_entries(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """List tracked entries, optionally filtered by symbol.

        Returns list of dicts: {"order_id", "symbol", "side", "qty", "filled_qty", "remaining_qty", "ts"}
        """
        out: List[Dict[str, Any]] = []
        try:
            raw_store = getattr(self.store, "_data", {})
            if not isinstance(raw_store, dict):
                return out
            for key, val in raw_store.items():
                if not (isinstance(key, str) and key.startswith("entry:")):
                    continue
                if not isinstance(val, dict):
                    continue
                sym = val.get("symbol")
                if symbol and str(sym).upper() != str(symbol).upper():
                    continue
                order_id = key.split(":", 1)[1]
                out.append({
                    "order_id": order_id,
                    "symbol": sym,
                    "side": val.get("side"),
                    "qty": val.get("qty"),
                    "filled_qty": val.get("filled_qty", 0.0),
                    "remaining_qty": val.get("remaining_qty", val.get("qty", 0.0)),
                    "ts": val.get("ts"),
                })
        except Exception:
            return out
        return out

    async def cleanup_orphans(
        self,
        symbol: Optional[str] = None,
        hard: bool = False,
        batch_limit: int = 50
    ) -> int:
        """
        Cancel our bracket orders when positionAmt==0 or parent missing.

        hard=True cancels all our reduceOnly/closePosition brackets regardless.
        Returns count of cancelled orders.
        """
        if not self.adapter:
            LOG.debug("No adapter available, skipping cleanup_orphans")
            return 0

        cancelled_count = 0
        cycle_symbol = (symbol or "ALL").upper()
        cycle_started_ms = self.clock.time() * 1000.0
        tidied_symbols: Set[str] = set()

        try:
            # Check position
            positions = await self.adapter.get_open_positions()
            position_amt = 0.0

            if symbol:
                # Find position for specific symbol
                for pos in positions:
                    # Handle both dict and ExchangePosition objects
                    if hasattr(pos, 'symbol'):
                        pos_symbol = pos.symbol  # type: ignore[union-attr]
                        # type: ignore[union-attr]
                        pos_amt = float(pos.position_amount)
                    else:
                        # type: ignore[union-attr]
                        pos_symbol = pos.get("symbol", "")
                        pos_amt = float(pos.get("position_amount")  # type: ignore[union-attr]
                                        or pos.get("positionAmt") or 0)  # type: ignore[union-attr]

                    if pos_symbol == symbol:
                        position_amt = pos_amt
                        break
            else:
                for pos in positions:
                    if hasattr(pos, 'position_amount'):
                        # type: ignore[union-attr]
                        pos_amt = float(pos.position_amount)
                    else:
                        pos_amt = float(pos.get("position_amount")  # type: ignore[union-attr]
                                        or pos.get("positionAmt") or 0)  # type: ignore[union-attr]
                    position_amt += pos_amt

            has_position = abs(position_amt) >= 1e-10

            if not hard and has_position:
                LOG.debug(
                    f"Position exists ({position_amt}), skipping orphan cleanup")
                return 0

            # Get open orders to find our brackets
            open_orders = await self.adapter.get_open_orders(symbol)

            LOG.info("[GUARD] Starting orphan cleanup", extra={
                "event_type": "cleanup_start",
                "symbol": symbol,
                "hard": hard,
                "position_amt": position_amt,
                "open_orders_count": len(open_orders),
                "has_position": has_position
            })

            cancelled_this_batch = 0
            for raw_order in open_orders:
                order = self._normalize_order_payload(raw_order)
                if not order:
                    continue

                if cancelled_this_batch >= batch_limit:
                    break

                order_id = order.get("orderId")
                client_order_id = order.get("clientOrderId")
                order_type = order.get("type", "")
                is_reduce_only_raw = order.get("reduceOnly", False)
                is_close_position_raw = order.get("closePosition", False)
                is_reduce_only = str(is_reduce_only_raw).lower() == "true" if isinstance(
                    is_reduce_only_raw, str) else bool(is_reduce_only_raw)
                is_close_position = str(is_close_position_raw).lower() == "true" if isinstance(
                    is_close_position_raw, str) else bool(is_close_position_raw)
                guardian_like = self._is_guardian_client_order_id(
                    client_order_id)

                if not order_id:
                    continue

                LOG.debug(
                    f"Checking order {order_id} ({order_type}, reduceOnly={is_reduce_only}, closePosition={is_close_position})")

                # Check if this is our bracket order
                order_meta = self.store.get(f"order:{order_id}")
                # Do not auto-infer/store metadata for unknown orders unless they
                # appear to be guardian-managed (guardian_like). This prevents
                # cancelling untracked bracket-like orders that belong to other
                # systems or users. Linking should be explicit via link_existing_from_rest.
                if not order_meta:
                    if guardian_like:
                        inferred_symbol = symbol or order.get("symbol")
                        order_meta = {
                            "symbol": inferred_symbol,
                            "type": order_type,
                            "reduce_only": is_reduce_only,
                            "close_position": is_close_position,
                            "parent_entry_id": None,
                            "client_order_id": client_order_id,
                            "kind": order_type.replace("_MARKET", "").upper() if order_type else None,
                        }
                        self.store.put(f"order:{order_id}", order_meta)
                        if client_order_id:
                            self.store.put(
                                f"client:{client_order_id}", order_id)
                        if inferred_symbol:
                            self.update_known_symbols([inferred_symbol])
                    else:
                        LOG.debug(
                            f"Order {order_id} not tracked and not guardian-like; skipping")
                        continue

                if not order_meta:
                    LOG.debug(f"Order {order_id} not tracked by guardian")
                    continue  # Not our order

                LOG.debug(f"Order {order_id} is tracked: {order_meta}")

                # Check if it's a bracket (reduceOnly or closePosition)
                if order_meta.get("reduce_only") or order_meta.get("close_position"):
                    LOG.info(f"[GUARD] Found orphan bracket candidate: {order_id} ({order_meta.get('kind', 'unknown')})", extra={
                        "event_type": "orphan_candidate",
                        "order_id": order_id,
                        "client_order_id": client_order_id,
                        "symbol": symbol or order_meta["symbol"],
                        "kind": order_meta.get("kind"),
                        "parent_entry_id": order_meta.get("parent_entry_id"),
                        "position_amt": position_amt,
                        "hard": hard
                    })

                    try:
                        result = await self.adapter.cancel_order(symbol or order_meta["symbol"], order_id)
                        if self._is_successful_cancel(result):
                            cancelled_count += 1
                            cancelled_this_batch += 1

                            self._metrics["guardian_orphans_cancelled_total"] += 1
                            tracked_symbol = symbol or order_meta["symbol"]
                            if tracked_symbol:
                                tidied_symbols.add(str(tracked_symbol).upper())

                            LOG.info(f"[GUARD] Orphan bracket cancelled: {order_id} ({order_meta.get('kind', 'unknown')} for {order_meta.get('parent_entry_id', 'unknown')})", extra={
                                "event_type": "cleanup_orphans",
                                "symbol": symbol or order_meta["symbol"],
                                "order_id": order_id,
                                "client_order_id": order_meta.get("client_order_id"),
                                "parent_entry_id": order_meta.get("parent_entry_id"),
                                "kind": order_meta.get("kind"),
                                "hard": hard,
                                "position_amt": position_amt
                            })
                        else:
                            LOG.warning(
                                f"[GUARD] Failed to cancel order {order_id}, result: {result}")
                    except Exception as e:
                        is_unknown_error = isinstance(
                            e, BinanceAPIError) and getattr(e, "code", None) == -2011
                        if not is_unknown_error and "unknown order" not in str(e).lower():
                            LOG.warning(
                                f"[GUARD] Failed to cancel orphan {order_id}: {e}")
                        else:
                            cancelled_count += 1
                            cancelled_this_batch += 1
                            self._metrics["guardian_orphans_cancelled_total"] += 1
                            tracked_symbol = symbol or order_meta.get("symbol")
                            if tracked_symbol:
                                tidied_symbols.add(str(tracked_symbol).upper())
                            LOG.info(
                                f"[GUARD] Orphan {order_id} already absent (-2011) for {tracked_symbol}")
                else:
                    LOG.debug(
                        f"Order {order_id} is not a bracket (reduce_only={order_meta.get('reduce_only')}, close_position={order_meta.get('close_position')})")

            LOG.info(f"[GUARD] Orphan cleanup completed: cancelled {cancelled_count} brackets", extra={
                "event_type": "cleanup_complete",
                "symbol": symbol,
                "cancelled_count": cancelled_count,
                "hard": hard
            })

            elapsed_ms = max(
                0.0, (self.clock.time() * 1000.0) - cycle_started_ms)
            self._metrics["guardian_cleanup_cycles_total"] += 1
            cleanup_map = self._metrics.setdefault(
                "guardian_cleanup_tidy_ms", {})
            cleanup_map[cycle_symbol] = elapsed_ms

            if self.bus and tidied_symbols:
                for tidy_symbol in tidied_symbols:
                    try:
                        self.bus.emit("EVT:SYMBOL_TIDY", {
                                      "symbol": tidy_symbol, "source": "guardian_poll"})
                    except Exception:
                        pass

        except Exception as e:
            LOG.error(f"Orphan cleanup failed: {e}")

        return cancelled_count

    async def cleanup_other_brackets_for_symbol(
        self,
        symbol: str,
        keep_parent_order_id: str,
        batch_limit: int = 50,
    ) -> int:
        """
        Cancel our bracket orders for a symbol that are tied to a different
        parent entry than the currently active one (keep_parent_order_id).

        Unlike cleanup_orphans(), this runs even when a position is open.

        Returns count of cancelled orders.
        """
        if not self.adapter:
            LOG.debug(
                "No adapter available, skipping cleanup_other_brackets_for_symbol")
            return 0

        cancelled_count = 0
        cancelled_this_batch = 0

        try:
            open_orders = await self.adapter.get_open_orders(symbol)

            if self._aggregated_oco_cfg.enabled:
                metas = [
                    meta
                    for meta in self._bracket_sets.values()
                    if meta.symbol.upper() == symbol.upper()
                ]
                if metas:
                    positions = await self.adapter.get_open_positions()
                    now_ts = self.clock.time()
                    aggregated_cancelled = 0
                    for meta in metas:
                        pos_amt = self._extract_position_amount_for_side(
                            positions=positions,
                            symbol=meta.symbol,
                            side=meta.side,
                        )
                        aggregated_cancelled += self.ensure_single_bracket_set_for_position(
                            symbol=meta.symbol,
                            side=meta.side,
                            position_amt=pos_amt,
                            open_orders=open_orders,
                            now_ts=now_ts,
                        )
                    return aggregated_cancelled

            for raw_order in open_orders:
                if cancelled_this_batch >= batch_limit:
                    break

                order = self._normalize_order_payload(raw_order)
                if not order:
                    continue

                order_id = order.get("orderId")
                client_order_id = order.get("clientOrderId")
                order_type = order.get("type", "")
                if not order_id:
                    continue

                # Determine reduceOnly/closePosition flags
                is_reduce_only_raw = order.get("reduceOnly", False)
                is_close_position_raw = order.get("closePosition", False)
                is_reduce_only = (
                    str(is_reduce_only_raw).lower() == "true"
                    if isinstance(is_reduce_only_raw, str)
                    else bool(is_reduce_only_raw)
                )
                is_close_position = (
                    str(is_close_position_raw).lower() == "true"
                    if isinstance(is_close_position_raw, str)
                    else bool(is_close_position_raw)
                )

                guardian_like = self._is_guardian_client_order_id(
                    client_order_id)

                # Ensure we have metadata for decision
                order_meta = self.store.get(f"order:{order_id}")
                # Same guard as in cleanup_orphans: only infer metadata for guardian-like
                # orders. This avoids touching untracked reduceOnly/closePosition orders.
                if not order_meta:
                    if guardian_like:
                        inferred_symbol = symbol or order.get("symbol")
                        order_meta = {
                            "symbol": inferred_symbol,
                            "type": order_type,
                            "reduce_only": is_reduce_only,
                            "close_position": is_close_position,
                            "parent_entry_id": None,
                            "client_order_id": client_order_id,
                            "kind": order_type.replace("_MARKET", "").upper() if order_type else None,
                        }
                        self.store.put(f"order:{order_id}", order_meta)
                        if client_order_id:
                            self.store.put(
                                f"client:{client_order_id}", order_id)
                        if inferred_symbol:
                            self.update_known_symbols([inferred_symbol])
                    else:
                        LOG.debug(
                            f"Order {order_id} not tracked and not guardian-like; skipping")
                        continue

                if not order_meta:
                    continue

                # Only act on bracket-like orders
                if not (order_meta.get("reduce_only") or order_meta.get("close_position")):
                    continue

                parent_id = order_meta.get("parent_entry_id")
                if parent_id and str(parent_id) == str(keep_parent_order_id):
                    # Bracket belongs to the current entry, keep it
                    continue

                # Cancel bracket for old/missing parent entry
                try:
                    result = await self.adapter.cancel_order(symbol, order_id)
                    if self._is_successful_cancel(result):
                        cancelled_count += 1
                        cancelled_this_batch += 1
                        self._metrics["guardian_orphans_cancelled_total"] += 1
                        LOG.info(
                            "[GUARD] Cancelled old bracket for previous entry",
                            extra={
                                "event_type": "cleanup_other_brackets",
                                "symbol": symbol,
                                "order_id": order_id,
                                "client_order_id": order_meta.get("client_order_id"),
                                "parent_entry_id": parent_id,
                                "keep_parent_order_id": keep_parent_order_id,
                            },
                        )
                    else:
                        LOG.warning(
                            f"[GUARD] Failed to cancel old bracket {order_id}, result: {result}"
                        )
                except Exception as e:
                    is_unknown_error = isinstance(
                        e, BinanceAPIError) and getattr(e, "code", None) == -2011
                    if not is_unknown_error and "unknown order" not in str(e).lower():
                        LOG.warning(
                            f"[GUARD] Exception cancelling old bracket {order_id}: {e}"
                        )
                    else:
                        cancelled_count += 1
                        cancelled_this_batch += 1
                        self._metrics["guardian_orphans_cancelled_total"] += 1
                        LOG.info(
                            f"[GUARD] Old bracket {order_id} already absent (-2011) for {symbol}"
                        )

        except Exception as e:
            LOG.error(
                f"cleanup_other_brackets_for_symbol failed for {symbol}: {e}"
            )

        return cancelled_count

    def _is_successful_cancel(self, result: Dict[str, Any]) -> bool:
        """Check if cancel was successful, treating -2011 as success"""
        normalized = self._normalize_order_payload(
            result) if result is not None else None
        payload = normalized if isinstance(normalized, dict) else (
            result if isinstance(result, dict) else {})

        if payload.get("status") == "CANCELED":
            return True

        # Handle -2011 (Unknown order) as success
        error_code = payload.get("code") or getattr(result, "code", None)
        message = payload.get("msg") or getattr(result, "msg", "")
        if error_code == -2011 or "Unknown order" in str(message):
            LOG.debug("Treating -2011 as successful cancel")
            return True

        return False

    async def reconcile_symbol(self, symbol: str, rid: Optional[str] = None) -> None:
        """
        Reconcile orders for symbol: cancel orphaned brackets if no position.

        Called on DEC:CLOSE execution and FLAT state transitions.
        """
        if not self.adapter:
            LOG.debug("No adapter available, skipping reconcile_symbol")
            return

        try:
            # Check if position exists
            positions = await self.adapter.get_open_positions()
            position_amt = 0.0

            for pos in positions:
                # Handle both dict and ExchangePosition objects
                if hasattr(pos, 'symbol'):
                    pos_symbol = pos.symbol  # type: ignore[union-attr]
                    # type: ignore[union-attr]
                    pos_amt = float(pos.position_amount)
                else:
                    # type: ignore[union-attr]
                    pos_symbol = pos.get("symbol", "")
                    pos_amt = float(pos.get("position_amount")  # type: ignore[union-attr]
                                    or pos.get("positionAmt") or 0)  # type: ignore[union-attr]

                if pos_symbol == symbol:
                    position_amt = pos_amt
                    break

            has_position = abs(position_amt) >= 1e-10

            if has_position:
                LOG.debug(
                    f"Position exists for {symbol} ({position_amt}), skipping reconcile")
                return

            # No position - run orphan cleanup for this symbol
            cancelled_count = await self.cleanup_orphans(symbol=symbol, hard=True)

            LOG.info("Symbol reconciled", extra={
                "event_type": "reconcile_symbol",
                "symbol": symbol,
                "position_amt": position_amt,
                "cancelled_count": cancelled_count,
                "rid": rid
            })

            # Emit EVT:SYMBOL_TIDY when nothing left (or after cancellations attempt)
            try:
                open_orders = await self.adapter.get_open_orders(symbol) if self.adapter else []
                # Consider tidy if no tracked brackets remain for this symbol
                any_tracked = False
                for o in open_orders:
                    oid = o.get("orderId")
                    meta = self.store.get(f"order:{oid}") if oid else None
                    if meta and (meta.get("reduce_only") or meta.get("close_position")):
                        any_tracked = True
                        break
                if not any_tracked and self.bus:
                    try:
                        self.bus.emit("EVT:SYMBOL_TIDY", {
                                      "symbol": symbol, "rid": rid})
                    except Exception:
                        pass
            except Exception:
                # Silent guard: event emission is best-effort
                pass

        except Exception as e:
            LOG.error(f"Reconcile failed for {symbol}: {e}")

    # ---- Lifecycle ----

    async def start(self):
        """Start background polling if enabled"""
        if self.poll_interval_ms > 0 and self._poller_task is None:
            await self._startup_relink_known_symbols()

            # Emit EVT:SYMBOL_TIDY for all known symbols on startup to prevent first-trade blocking
            if self.bus:
                symbols = self._iter_symbols_for_poll()
                for sym in symbols:
                    try:
                        self.bus.emit("EVT:SYMBOL_TIDY", {
                                      "symbol": sym, "source": "guardian_startup"})
                    except Exception:
                        pass

            self._poller_task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        """Stop background polling"""
        if self._poller_task:
            self._poller_task.cancel()
            try:
                await self._poller_task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self):
        """Background polling loop (if enabled)"""
        LOG.info("[GUARD] OrderGuardian poll loop started", extra={
            "event_type": "poll_loop_start",
            "poll_interval_ms": self.poll_interval_ms
        })
        while True:
            try:
                cycle_started = self.clock.time()
                symbols = self._iter_symbols_for_poll()

                if not symbols:
                    LOG.debug(
                        "[GUARD] Poll cycle skipped - no known symbols yet")
                    await asyncio.sleep(self.poll_interval_ms / 1000.0)
                    continue

                total_cancelled = 0
                for sym in symbols:
                    try:
                        await self.link_existing_from_rest(sym)
                    except Exception as link_exc:
                        LOG.warning(
                            f"[GUARD] link_existing_from_rest failed for {sym}: {link_exc}")
                    cancelled = await self.cleanup_orphans(symbol=sym)
                    total_cancelled += cancelled

                elapsed_ms = int((self.clock.time() - cycle_started) * 1000.0)
                self._metrics["guardian_poll_last_duration_ms"] = max(
                    elapsed_ms, 0)
                self._metrics.setdefault("guardian_cleanup_cycles_total", 0)

                if total_cancelled > 0:
                    LOG.info(
                        f"[GUARD] Poll cleanup cancelled {total_cancelled} orphan brackets across {len(symbols)} symbols")
                LOG.debug(
                    f"[GUARD] Poll iteration finished in {elapsed_ms} ms (symbols={symbols})")
                await asyncio.sleep(self.poll_interval_ms / 1000.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOG.error(f"[GUARD] Poll loop error: {e}")

    def get_metrics(self) -> Dict[str, Any]:
        """Expose guardian metrics for aggregation."""
        snapshot = dict(self._metrics)
        cleanup_map = snapshot.get("guardian_cleanup_tidy_ms") or {}
        snapshot["guardian_cleanup_tidy_ms"] = dict(cleanup_map)
        snapshot["guardian_known_symbols"] = sorted(self._known_symbols)
        snapshot.setdefault("guardian_poll_last_duration_ms", 0)
        return snapshot
