"""
OrderGuardian Service - Metadata Registry Only.

Responsibilities:
- Owns mapping (clientOrderId <-> orderId) and bracket linkage per entry.
- Tracks active positions and associated orders metadata.
- NO active cleanup (polling/cancellation removed).
- Writes audit trail to logs/order_guardian.log

Architecture:
- Adapter: transport layer (place/cancel/get/openOrders/positionRisk)
- OrderGuardian: metadata store only.
- Runtime V2: business logic & active management.
"""

import os
import logging
import time
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Protocol, Sequence, Tuple, Set, Iterable
import threading

from apps.reference.domains.execution_position.infra.utils import (
    ClientOrderIntent,
    ClientOrderIdMeta,
    parse_client_order_id,
)

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


class StoreProtocol(Protocol):
    """Protocol for pluggable storage"""

    def get(self, key: str) -> Any: ...
    def put(self, key: str, value: Any) -> None: ...
    def delete(self, key: str) -> None: ...


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


class OrderGuardian:
    """
    Centralized order/position metadata registry.

    Refactored to be PASSIVE (metadata only).
    All active logic (polling, cleanup, cancellation) has been removed.
    """

    def __init__(
        self,
        adapter: Optional[Any] = None,  # Kept for signature compatibility but unused
        clock=None,
        store: Optional[StoreProtocol] = None,
        poll_interval_ms: int = 0,  # Ignored
        bus: Optional[Any] = None,  # Ignored
        config: Optional[Any] = None,  # Ignored
        aggregated_oco_cfg: Optional[Any] = None,  # Ignored
    ):
        self.clock = clock or time
        self.store = store or InMemoryStore()
        self._bracket_sets: Dict[tuple[str, str], BracketSetMeta] = {}
        self._known_symbols: Set[str] = set()

        LOG.info("OrderGuardian initialized (Metadata Only Mode)")

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
            meta = None
            try:
                meta = parse_client_order_id(client_id)
            except Exception:
                meta = None
            base_id = self._extract_bracket_base_from_client_meta(
                meta, client_id)
            if not base_id:
                continue

            entry = grouped.setdefault(
                base_id,
                {"base_id": base_id, "sl": None, "tp": None, "ts": 0.0},
            )

            if meta and meta.intent == ClientOrderIntent.STOP_LOSS:
                entry["sl"] = normalized
            elif meta and meta.intent == ClientOrderIntent.TAKE_PROFIT:
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
    def _extract_bracket_base_from_client_meta(
        client_meta: Optional[ClientOrderIdMeta],
        client_order_id: Optional[str],
    ) -> Optional[str]:
        if client_meta:
            bundle = client_meta.bundle_key()
            if bundle:
                return bundle
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
        """Add configured symbols to internal registry."""
        try:
            normalized = {str(sym).upper() for sym in symbols if sym}
            if normalized:
                self._known_symbols.update(normalized)
        except Exception:
            pass

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
                from dataclasses import asdict, is_dataclass
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

    # ---- Query API ----

    def get_brackets_for_entry(self, parent_order_id: str) -> Dict[str, Any]:
        """Get bracket orders for entry"""
        entry_key = f"entry:{parent_order_id}"
        entry_data: Optional[Dict[str, Any]] = self.store.get(entry_key)
        if entry_data:
            return entry_data.get("brackets", {})
        return {}

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
