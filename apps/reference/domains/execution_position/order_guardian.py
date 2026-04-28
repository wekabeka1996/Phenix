"""
OrderGuardian — Canonical implementation within the execution_position domain.

Responsibilities:
- Owns mapping (clientOrderId <-> orderId) and bracket linkage per entry.
- Tracks active positions and associated orders.
- Safe cleanup of bracket orders with ownership validation.
- Writes audit trail to logs/order_guardian.log

Architecture:
- Adapter: transport layer (place/cancel/get/openOrders/positionRisk)
- OrderGuardian: domain logic for ownership/cleanup
- FSM: business signals, delegates cleanup to OrderGuardian

Storage:
- unified=True: LedgerStoreAdapter over SQLite OrderLedger (SSOT)
- unified=False: InMemoryStore (ephemeral, for testing / lightweight use)
"""

import os
import asyncio
import json
import logging
import time
from dataclasses import dataclass, asdict, is_dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional, Protocol, Union, TypeAlias, Iterable, Set

from apps.reference.domains.execution_position.cancel_submission_adapter import (
    CancelSubmissionAdapterError,
    CancelSubmissionPayload,
    build_cancel_submission_trace_ref,
)
from apps.reference.domains.execution_position.guardian_pre_close_cleanup_bridge import (
    GUARDIAN_PRE_CLOSE_CLEANUP_PATH,
    GUARDIAN_PRE_CLOSE_CLEANUP_TRIGGER,
    GuardianPreCloseCleanupBridgeError,
    adapt_guardian_pre_close_cleanup_to_dec_cancel,
    build_guardian_pre_close_cleanup_trace_ref,
)
from apps.reference.domains.execution_position.guardian_old_bracket_cleanup_bridge import (
    GUARDIAN_OLD_BRACKET_CLEANUP_PATH,
    GUARDIAN_OLD_BRACKET_CLEANUP_TRIGGER,
    GuardianOldBracketCleanupBridgeError,
    adapt_guardian_old_bracket_cleanup_to_dec_cancel,
    build_guardian_old_bracket_cleanup_trace_ref,
)
from apps.reference.domains.execution_position.guardian_reconcile_cancel_bridge import (
    GUARDIAN_RECONCILE_CANCEL_PATH,
    GUARDIAN_RECONCILE_CANCEL_TRIGGER,
    GuardianReconcileCancelBridgeError,
    adapt_guardian_reconcile_to_dec_cancel,
    build_guardian_reconcile_cancel_trace_ref,
)
from apps.reference.domains.execution_position.guardian_background_orphan_cancel_bridge import (
    GUARDIAN_BACKGROUND_ORPHAN_CANCEL_PATH,
    GUARDIAN_BACKGROUND_ORPHAN_CANCEL_TRIGGER,
    GuardianBackgroundOrphanCancelBridgeError,
    adapt_guardian_background_orphan_to_dec_cancel,
    build_guardian_background_orphan_cancel_trace_ref,
)
from apps.reference.domains.execution_position.utils import coerce_exchange_bool
from decimal import Decimal
import threading

from apps.reference.utils.accessors import aget

# Lazy imports for infra layer (resolved at first use to avoid circular deps)


def _get_ledger_store():
    from apps.reference.domains.execution_position.infra.ledger_store_adapter import LedgerStoreAdapter
    from apps.reference.domains.execution_position.infra.order_ledger import OrderLedger
    return LedgerStoreAdapter, OrderLedger


# Try to import ExchangePosition for better typing
try:
    from vfoundation.core.adapters.base import ExchangePosition
except ImportError:
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
project_root = Path(__file__).resolve().parents[4]
log_dir = project_root / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "order_guardian.log"

file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
LOG.addHandler(file_handler)


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


class OrderGuardian:
    """
    Centralized order/position monitor & cleanup.

    Owns mapping (clientOrderId <-> orderId) and bracket linkage per entry.
    Writes to logs/order_guardian.log with structured JSON events.

    Store selection (via config):
    - execution.order_guardian.unified=True → LedgerStoreAdapter (SQLite, SSOT)
    - execution.order_guardian.unified=False → InMemoryStore (ephemeral)
    - store= kwarg overrides config entirely (for tests)
    """

    # ------------------------------------------------------------------
    # Config resolution (factory helper, formerly in domain wrapper)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_explicit_guardian_store_value(guardian_cfg: Any, key: str) -> tuple[bool, Any]:
        if guardian_cfg is None:
            return False, None
        if isinstance(guardian_cfg, dict):
            return key in guardian_cfg, guardian_cfg.get(key)

        cfg_dict = getattr(guardian_cfg, "__dict__", None)
        if isinstance(cfg_dict, dict):
            if key in cfg_dict:
                return True, cfg_dict.get(key)
            if hasattr(guardian_cfg, "__getattr__"):
                return False, None

        try:
            return True, getattr(guardian_cfg, key)
        except Exception:
            return False, None

    @staticmethod
    def _resolve_guardian_cfg(cfg: Any) -> Any:
        """Resolve SSOT guardian config block from typed AuroraConfig."""
        if cfg is None:
            return None

        def _get_explicit_member(node: Any, key: str) -> tuple[bool, Any]:
            if node is None:
                return False, None
            if isinstance(node, dict):
                return key in node, node.get(key)

            node_dict = getattr(node, "__dict__", None)
            if isinstance(node_dict, dict):
                if key in node_dict:
                    return True, node_dict.get(key)
                if hasattr(node, "__getattr__"):
                    return False, None

            try:
                return True, getattr(node, key)
            except Exception:
                return False, None

        def _extract_order_guardian(node: Any) -> tuple[bool, Any]:
            _, execution_cfg = _get_explicit_member(node, "execution")
            if execution_cfg is None:
                return False, None

            order_guardian_present, order_guardian_cfg = _get_explicit_member(
                execution_cfg,
                "order_guardian",
            )
            if not order_guardian_present or order_guardian_cfg is None:
                return False, None

            if isinstance(order_guardian_cfg, (dict, str)):
                return True, order_guardian_cfg
            if not hasattr(execution_cfg, "__getattr__"):
                return True, order_guardian_cfg
            return False, None

        # NOTE: Many tests use MagicMock configs; attribute access on MagicMock
        # auto-creates nested mocks (truthy), which would incorrectly select a
        # non-real config block. Prefer explicitly-set attributes when possible.
        cfg_dict = getattr(cfg, "__dict__", None)

        root_present, root_guardian_cfg = _extract_order_guardian(cfg)

        trading = None
        if isinstance(cfg_dict, dict) and "trading" in cfg_dict:
            trading = cfg_dict.get("trading")
        else:
            try:
                trading = getattr(cfg, "trading", None)
            except Exception:
                trading = None

        trading_present, trading_guardian_cfg = _extract_order_guardian(
            trading)

        if root_present and trading_present and root_guardian_cfg != trading_guardian_cfg:
            raise ValueError(
                "Conflicting guardian configuration sources: execution.order_guardian "
                "and trading.execution.order_guardian differ. Keep only one or make them equal."
            )

        if root_present:
            return root_guardian_cfg
        if trading_present:
            return trading_guardian_cfg

        # Legacy (non-SSOT) fallback
        legacy = None
        if isinstance(cfg_dict, dict) and "guardian" in cfg_dict:
            legacy = cfg_dict.get("guardian")
        else:
            try:
                legacy = getattr(cfg, "guardian", None)
            except Exception:
                legacy = None
        return legacy

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(
        self,
        adapter: Optional[AdapterProtocol],
        clock=None,
        store: Optional[StoreProtocol] = None,
        poll_interval_ms: int = 500,
        bus: Optional[Any] = None,
        config: Optional[Any] = None,
        emit_tidy_monitoring_event: bool = True,
    ):
        if isinstance(config, dict):
            raise TypeError(
                "OrderGuardian requires typed config object, got dict")

        self.adapter = adapter
        self.clock = clock or time
        self.poll_interval_ms = poll_interval_ms
        self.bus = bus
        self._cfg = config or {}
        self.emit_tidy_monitoring_event = bool(emit_tidy_monitoring_event)
        self._known_symbols: Set[str] = set()
        self._metrics: Dict[str, Any] = {
            "guardian_orphans_cancelled_total": 0,
            "guardian_cleanup_cycles_total": 0,
            "guardian_linked_from_rest_total": 0,
            "guardian_cleanup_tidy_ms": {},
            "guardian_poll_last_duration_ms": 0,
        }
        self._last_cycle_started_ms: float = 0.0

        # Resolve store: explicit store override > config-driven > explicit config=None compatibility
        if store is not None:
            self.store = store
        else:
            self.store = self._build_store_from_config(config)

        if config:
            try:
                self.update_known_symbols(
                    self._extract_symbols_from_config(config))
            except Exception:
                pass

        # Poller setup (optional, off by default)
        self._poller_task: Optional[asyncio.Task] = None
        if poll_interval_ms > 0:
            pass

        LOG.info("OrderGuardian initialized", extra={
            "event_type": "guardian_init",
            "poll_interval_ms": poll_interval_ms
        })

    def _build_store_from_config(self, config: Any) -> "StoreProtocol":
        """Build LedgerStoreAdapter or InMemoryStore based on config.

        When config=None is passed explicitly (tests/manual mode), default to
        InMemoryStore. When a config object is provided, explicit guardian
        store settings are required; silent store defaults and silent degraded
        store fallback are prohibited.
        """
        if config is None:
            return InMemoryStore()

        guardian_cfg = self._resolve_guardian_cfg(config)
        if guardian_cfg is None:
            raise ValueError(
                "OrderGuardian store config is required when config object is provided. "
                "Set execution.order_guardian or trading.execution.order_guardian explicitly, "
                "or pass config=None/store=... for tests or manual mode."
            )

        unified_present, unified_value = self._get_explicit_guardian_store_value(
            guardian_cfg,
            "unified",
        )
        if not unified_present or unified_value is None:
            raise ValueError(
                "OrderGuardian store config missing required field: order_guardian.unified"
            )

        unified = bool(unified_value)

        if not unified:
            return InMemoryStore()

        # unified=True: resolve db path and build LedgerStoreAdapter
        db_path_present, db_path = self._get_explicit_guardian_store_value(
            guardian_cfg,
            "ledger_db_path",
        )
        if not db_path_present or db_path is None:
            raise ValueError(
                "OrderGuardian store config missing required field: "
                "order_guardian.ledger_db_path when order_guardian.unified=true"
            )

        if isinstance(db_path, Path):
            db_path = str(db_path)
        if not isinstance(db_path, str) or not db_path.strip():
            raise ValueError(
                "OrderGuardian store config requires a non-empty string ledger_db_path "
                "when order_guardian.unified=true"
            )

        if db_path != ":memory:":
            try:
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        try:
            LedgerStoreAdapter, OrderLedger = _get_ledger_store()
            ledger = OrderLedger(db_path)
            return LedgerStoreAdapter(ledger)
        except Exception as exc:
            LOG.error(
                "[GUARD] Failed to build LedgerStoreAdapter for explicit order_guardian config; "
                "refusing InMemoryStore fallback: %s",
                exc,
            )
            raise ValueError(
                "OrderGuardian failed to initialize LedgerStoreAdapter for explicit "
                f"order_guardian config (ledger_db_path={db_path!r}). "
                "No InMemoryStore fallback is allowed when order_guardian.unified=true."
            ) from exc

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
            "corr_id": corr_id,
            "rid": rid
        })

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
        existing_meta = self.store.get(f"order:{internal_order_id}")
        if not existing_meta:
            LOG.warning(
                f"No metadata found for internal order {internal_order_id}, cannot update exchange ID")
            return

        updated_meta = dict(existing_meta)
        updated_meta["exchange_order_id"] = exchange_order_id

        self.store.put(f"order:{exchange_order_id}", updated_meta)
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

    def _normalize_config_symbols(self, raw_symbols: Any) -> Set[str]:
        if isinstance(raw_symbols, dict):
            candidates = raw_symbols.keys()
        elif isinstance(raw_symbols, (list, tuple, set, frozenset)):
            candidates = raw_symbols
        else:
            return set()

        symbols: Set[str] = set()
        for raw_symbol in candidates:
            symbol = str(raw_symbol or "").strip().upper()
            if symbol:
                symbols.add(symbol)
        return symbols

    def _extract_symbols_from_config(self, cfg: Any) -> Set[str]:
        """Extract guardian seed symbols without legacy trading.instruments."""
        symbols: Set[str] = set()

        try:
            if isinstance(cfg, dict):
                trading = cfg.get("trading") or {}
                if isinstance(trading, dict):
                    symbols.update(
                        self._normalize_config_symbols(
                            trading.get("symbols_to_track"))
                    )
                if not symbols:
                    strategies_registry = cfg.get("strategies_registry") or {}
                    if isinstance(strategies_registry, dict):
                        symbols.update(
                            self._normalize_config_symbols(
                                strategies_registry.get("assignments"))
                        )
                if not symbols:
                    symbols.update(self._normalize_config_symbols(
                        cfg.get("instruments")))
            else:
                trading = getattr(cfg, "trading", None)
                if trading:
                    symbols.update(
                        self._normalize_config_symbols(
                            getattr(trading, "symbols_to_track", None))
                    )
                if not symbols:
                    strategies_registry = getattr(
                        cfg, "strategies_registry", None)
                    if strategies_registry:
                        symbols.update(
                            self._normalize_config_symbols(
                                getattr(strategies_registry, "assignments", None))
                        )
                if not symbols:
                    symbols.update(
                        self._normalize_config_symbols(
                            getattr(cfg, "instruments", None))
                    )
        except Exception:
            pass

        return symbols

    def _iter_symbols_for_poll(self) -> List[str]:
        """Resolve symbols for polling loop (config + store fallbacks)."""
        symbols = set(self._known_symbols)

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
        """Fallback heuristic to identify guardian-managed client order ids.

        PREFIX-CANON-01: Delegates to canonical prefix registry.
        """
        from apps.reference.domains.execution_position.utils import is_guardian_managed_prefix
        return is_guardian_managed_prefix(client_order_id)

    async def link_existing_from_rest(self, symbol: str) -> None:
        """Builds mapping from /openOrders for existing orders"""
        if not self.adapter:
            LOG.debug("No adapter available, skipping link_existing_from_rest")
            return

        try:
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

                if self.store.get(f"order:{order_id}"):
                    continue

                is_reduce_only_raw = order.get("reduceOnly", False)
                is_close_position_raw = order.get("closePosition", False)
                is_reduce_only = coerce_exchange_bool(is_reduce_only_raw)
                is_close_position = coerce_exchange_bool(is_close_position_raw)
                order_type = order.get("type", "")

                guardian_like = self._is_guardian_client_order_id(
                    client_order_id)

                if is_reduce_only or is_close_position or order_type in ("STOP_MARKET", "TAKE_PROFIT_MARKET") or guardian_like:
                    self.store.put(f"order:{order_id}", {
                        "symbol": symbol,
                        "type": order_type,
                        "reduce_only": is_reduce_only,
                        "close_position": is_close_position,
                        "parent_entry_id": None
                    })

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

    @staticmethod
    def _normalize_terminal_bracket_kind(order_meta: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(order_meta, dict):
            return None

        explicit_kind = str(order_meta.get("kind") or "").strip().upper()
        if explicit_kind in {"SL", "TP", "TP1", "TP2"}:
            return explicit_kind

        order_type = str(order_meta.get("type") or "").strip().upper()
        if order_type == "STOP_MARKET":
            return "SL"
        if order_type == "TAKE_PROFIT_MARKET":
            return "TP"
        return None

    def resolve_terminal_bracket_context(
        self,
        *,
        client_order_id: Optional[str],
        exchange_order_id: Optional[str],
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Best-effort recovery for close-bearing bracket WS updates.

        This recovers bracket truth from explicit guardian ownership metadata
        when narrow OrderIndex correlation misses on child/algo exchange events.
        Fail closed on symbol mismatch or when metadata does not prove a tracked
        SL/TP path.
        """
        symbol_key = str(symbol or "").strip().upper()

        def _build_context(
            *,
            tracked_order_id: Optional[str],
            order_meta: Optional[Dict[str, Any]],
            correlation_source: str,
        ) -> Optional[Dict[str, Any]]:
            kind = self._normalize_terminal_bracket_kind(order_meta)
            if kind is None or not isinstance(order_meta, dict):
                return None

            meta_symbol = str(order_meta.get("symbol") or "").strip().upper()
            if symbol_key and meta_symbol and meta_symbol != symbol_key:
                return None

            return {
                "symbol": meta_symbol or symbol_key,
                "rid": str(order_meta.get("rid") or "").strip() or None,
                "corr_id": str(order_meta.get("corr_id") or "").strip() or None,
                "parent_entry_order_id": str(
                    order_meta.get("parent_entry_id") or ""
                ).strip() or None,
                "tracked_bracket_order_id": str(
                    tracked_order_id or exchange_order_id or ""
                ).strip() or None,
                "tracked_client_order_id": str(
                    order_meta.get("client_order_id") or client_order_id or ""
                ).strip() or None,
                "bracket_role": kind,
                "order_type": str(order_meta.get("type") or "").strip() or None,
                "reduce_only": bool(order_meta.get("reduce_only", False)),
                "close_position": bool(order_meta.get("close_position", False)),
                "correlation_source": correlation_source,
            }

        if exchange_order_id:
            exact_meta = self.store.get(f"order:{exchange_order_id}")
            exact_context = _build_context(
                tracked_order_id=str(exchange_order_id),
                order_meta=exact_meta,
                correlation_source="order_guardian_exchange_order_id",
            )
            if exact_context is not None:
                return exact_context

        if client_order_id:
            mapped_order_id = self.store.get(f"client:{client_order_id}")
            mapped_order_id_str = str(
                mapped_order_id).strip() if mapped_order_id else ""
            if mapped_order_id_str:
                mapped_meta = self.store.get(f"order:{mapped_order_id_str}")
                mapped_context = _build_context(
                    tracked_order_id=mapped_order_id_str,
                    order_meta=mapped_meta,
                    correlation_source="order_guardian_client_order_id",
                )
                if mapped_context is not None:
                    return mapped_context

        return None

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
            open_orders = await self.adapter.get_open_orders(symbol)

            our_brackets = []
            for raw_order in open_orders:
                order = self._normalize_order_payload(raw_order)
                if not order:
                    continue

                order_id = order.get("orderId")
                if not order_id:
                    continue

                order_meta = self.store.get(f"order:{order_id}")
                if not order_meta:
                    continue

                if order_meta.get("reduce_only") or order_meta.get("close_position"):
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

        NOTE: Position existence is validated upstream by ExecPosFSM._preflight_position_check()
        with retry logic to handle REST API lag. This method only checks for conflicting
        metadata conditions that would prevent bracket placement.
        """
        if not self.adapter:
            LOG.debug(
                "No adapter available, allowing bracket placement by default")
            return True

        try:
            entry_meta = self.store.get(f"order:{entry_order_id}")
            if not entry_meta:
                LOG.debug(
                    f"OrderGuardian: No entry metadata found for order {entry_order_id}, allowing bracket placement")
                return True

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
                brackets = self.get_brackets_for_entry(parent_order_id)
                for bracket_type, bracket_info in brackets.items():
                    order_id = bracket_info["order_id"]
                    typed_cancelled = await self._execute_guardian_pre_close_cleanup_cancel(
                        symbol=symbol,
                        order_id=order_id,
                        bracket_type=str(bracket_type or "UNKNOWN"),
                        parent_order_id=str(parent_order_id),
                    )
                    if typed_cancelled:
                        cancelled_count += 1
            else:
                pass

        except Exception as e:
            LOG.error(f"Cleanup before close failed: {e}")

        return cancelled_count

    def _emit_tidy_events(
        self,
        *,
        symbol: str,
        source: str,
        tidy_reason: str,
        why: str,
        rid: Optional[str] = None,
    ) -> None:
        if not self.bus:
            return
        payload = {
            "symbol": symbol,
            "source": source,
            "ts_ms": int(self.clock.time() * 1000),
            "tidy_reason": tidy_reason,
            "business_close_reconciled": False,
            "why": why,
        }
        if rid is not None:
            payload["rid"] = rid
        try:
            if self.emit_tidy_monitoring_event:
                self.bus.emit(
                    "EVT:EXECUTION_TIDY_PERFORMED",
                    dict(payload),
                    why=why,
                )
            self.bus.emit(
                "EVT:SYMBOL_TIDY",
                dict(payload),
                why=why,
            )
            LOG.info(
                "[GUARD] Execution tidy performed",
                extra={
                    "event_type": "execution_tidy_performed",
                    **payload,
                },
            )
        except Exception as exc:
            LOG.error(
                "[%s] CRITICAL: Failed to emit tidy events: %s", symbol, exc)

    def _emit_close_reconciled_event(
        self,
        *,
        symbol: str,
        rid: Optional[str],
        source: str,
    ) -> None:
        if not self.bus:
            return
        why = "guardian:close_reconciled"
        payload = {
            "symbol": symbol,
            "rid": rid,
            "source": source,
            "ts_ms": int(self.clock.time() * 1000),
            "business_close_reconciled": True,
            "why": why,
        }
        try:
            self.bus.emit(
                "EVT:EXECUTION_CLOSE_RECONCILED",
                payload,
                why=why,
            )
            LOG.info(
                "[GUARD] Execution close reconciled",
                extra={
                    "event_type": "execution_close_reconciled",
                    **payload,
                },
            )
        except Exception as exc:
            LOG.error(
                "[%s] CRITICAL: Failed to emit close reconcile event: %s", symbol, exc)

    def _guardian_pre_close_cleanup_log_reject(
        self,
        *,
        symbol: str,
        order_id: Any,
        bracket_type: str,
        parent_order_id: str,
        reason: str,
        bridge_trace_ref: str,
        package4_trace_ref: Optional[str] = None,
    ) -> None:
        extra = {
            "event_type": "guardian_pre_close_cleanup_bridge_reject",
            "symbol": symbol,
            "order_id": order_id,
            "bracket_type": bracket_type,
            "parent_order_id": parent_order_id,
            "trigger": GUARDIAN_PRE_CLOSE_CLEANUP_TRIGGER,
            "bridge_path": GUARDIAN_PRE_CLOSE_CLEANUP_PATH,
            "bridge_trace_ref": bridge_trace_ref,
            "reason": reason,
        }
        if package4_trace_ref is not None:
            extra["cancel_submission_trace_ref"] = package4_trace_ref
        LOG.warning(
            "[GUARD] Rejecting pre-close cleanup for %s (%s): %s",
            order_id,
            symbol,
            reason,
            extra=extra,
        )

    def _guardian_pre_close_cleanup_log_success(
        self,
        *,
        symbol: str,
        order_id: str,
        parent_order_id: str,
        bracket_type: str,
        bridge_trace_ref: str,
        package4_trace_ref: str,
    ) -> None:
        LOG.info(
            "Bracket cancelled for entry",
            extra={
                "event_type": "cleanup_before_close",
                "symbol": symbol,
                "parent_order_id": parent_order_id,
                "bracket_order_id": order_id,
                "bracket_type": bracket_type,
                "trigger": GUARDIAN_PRE_CLOSE_CLEANUP_TRIGGER,
                "bridge_path": GUARDIAN_PRE_CLOSE_CLEANUP_PATH,
                "bridge_trace_ref": bridge_trace_ref,
                "cancel_submission_trace_ref": package4_trace_ref,
            },
        )

    def _guardian_pre_close_cleanup_log_failure(
        self,
        *,
        symbol: str,
        order_id: str,
        bracket_type: str,
        parent_order_id: str,
        bridge_trace_ref: str,
        package4_trace_ref: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        exc: Optional[Exception] = None,
    ) -> None:
        extra = {
            "event_type": "guardian_pre_close_cleanup_bridge_failure",
            "symbol": symbol,
            "order_id": order_id,
            "bracket_type": bracket_type,
            "parent_order_id": parent_order_id,
            "trigger": GUARDIAN_PRE_CLOSE_CLEANUP_TRIGGER,
            "bridge_path": GUARDIAN_PRE_CLOSE_CLEANUP_PATH,
            "bridge_trace_ref": bridge_trace_ref,
        }
        if package4_trace_ref is not None:
            extra["cancel_submission_trace_ref"] = package4_trace_ref
        if result is not None:
            extra["result"] = result
        if exc is not None:
            extra["error"] = str(exc)
            LOG.warning(
                "Failed to cancel bracket %s for %s: %s",
                order_id,
                symbol,
                exc,
                extra=extra,
            )
            return
        LOG.warning(
            "Failed to cancel bracket %s for %s, result: %s",
            order_id,
            symbol,
            result,
            extra=extra,
        )

    async def _execute_guardian_pre_close_cleanup_cancel(
        self,
        *,
        symbol: str,
        order_id: Any,
        bracket_type: str,
        parent_order_id: str,
    ) -> bool:
        try:
            request, cancel_decision = adapt_guardian_pre_close_cleanup_to_dec_cancel(
                symbol=symbol,
                order_id=order_id,
                bracket_type=bracket_type,
                parent_order_id=parent_order_id,
            )
        except GuardianPreCloseCleanupBridgeError as exc:
            bridge_trace_ref = build_guardian_pre_close_cleanup_trace_ref(
                status="reject",
                bracket_type=str(bracket_type or "UNKNOWN"),
                reason="bridge_validation",
            )
            self._guardian_pre_close_cleanup_log_reject(
                symbol=symbol,
                order_id=order_id,
                bracket_type=str(bracket_type or "UNKNOWN"),
                parent_order_id=parent_order_id,
                reason=str(exc),
                bridge_trace_ref=bridge_trace_ref,
            )
            return False

        bridge_trace_ref = build_guardian_pre_close_cleanup_trace_ref(
            status="success",
            bracket_type=request.bracket_type,
        )
        try:
            submission = CancelSubmissionPayload.from_dec_cancel(
                payload=cancel_decision.pld or {}
            )
        except CancelSubmissionAdapterError as exc:
            package4_trace_ref = build_cancel_submission_trace_ref(
                status="reject",
                reason="adapter_validation",
            )
            self._guardian_pre_close_cleanup_log_reject(
                symbol=request.symbol,
                order_id=request.order_id,
                bracket_type=request.bracket_type,
                parent_order_id=request.parent_order_id,
                reason=str(exc),
                bridge_trace_ref=bridge_trace_ref,
                package4_trace_ref=package4_trace_ref,
            )
            return False

        package4_trace_ref = build_cancel_submission_trace_ref(
            status="success")
        try:
            result = await self.adapter.cancel_order(
                submission.symbol,
                submission.order_id,
            )
            if self._is_successful_cancel(result):
                self._guardian_pre_close_cleanup_log_success(
                    symbol=submission.symbol,
                    order_id=submission.order_id,
                    parent_order_id=parent_order_id,
                    bracket_type=request.bracket_type,
                    bridge_trace_ref=bridge_trace_ref,
                    package4_trace_ref=package4_trace_ref,
                )
                return True
            self._guardian_pre_close_cleanup_log_failure(
                symbol=submission.symbol,
                order_id=submission.order_id,
                bracket_type=request.bracket_type,
                parent_order_id=parent_order_id,
                bridge_trace_ref=bridge_trace_ref,
                package4_trace_ref=package4_trace_ref,
                result=result if isinstance(result, dict) else None,
            )
            return False
        except Exception as exc:
            if not self._is_missing_order_cancel_outcome(exc):
                self._guardian_pre_close_cleanup_log_failure(
                    symbol=submission.symbol,
                    order_id=submission.order_id,
                    bracket_type=request.bracket_type,
                    parent_order_id=parent_order_id,
                    bridge_trace_ref=bridge_trace_ref,
                    package4_trace_ref=package4_trace_ref,
                    exc=exc,
                )
                return False
            LOG.info(
                f"[GUARD] Bracket {submission.order_id} already absent (-2011/-2013) for {submission.symbol}",
                extra={
                    "event_type": "cleanup_before_close",
                    "symbol": submission.symbol,
                    "parent_order_id": parent_order_id,
                    "bracket_order_id": submission.order_id,
                    "bracket_type": request.bracket_type,
                    "trigger": GUARDIAN_PRE_CLOSE_CLEANUP_TRIGGER,
                    "bridge_path": GUARDIAN_PRE_CLOSE_CLEANUP_PATH,
                    "bridge_trace_ref": bridge_trace_ref,
                    "cancel_submission_trace_ref": package4_trace_ref,
                },
            )
            return True

    def _guardian_reconcile_cancel_log_reject(
        self,
        *,
        symbol: str,
        order_id: Any,
        order_type: str,
        rid: Optional[str],
        reason: str,
        bridge_trace_ref: str,
        package4_trace_ref: Optional[str] = None,
    ) -> None:
        extra = {
            "event_type": "guardian_reconcile_cancel_bridge_reject",
            "symbol": symbol,
            "order_id": order_id,
            "order_type": order_type,
            "rid": rid,
            "trigger": GUARDIAN_RECONCILE_CANCEL_TRIGGER,
            "bridge_path": GUARDIAN_RECONCILE_CANCEL_PATH,
            "bridge_trace_ref": bridge_trace_ref,
            "reason": reason,
        }
        if package4_trace_ref is not None:
            extra["cancel_submission_trace_ref"] = package4_trace_ref
        LOG.warning(
            "[GUARD] Rejecting reconcile orphan cancel for %s (%s): %s",
            order_id,
            symbol,
            reason,
            extra=extra,
        )

    def _guardian_reconcile_cancel_log_success(
        self,
        *,
        symbol: str,
        order_id: str,
        order_meta: Dict[str, Any],
        rid: Optional[str],
        position_amt: float,
        bridge_trace_ref: str,
        package4_trace_ref: str,
    ) -> None:
        LOG.info(
            f"[GUARD] Orphan bracket cancelled: {order_id} ({order_meta.get('kind', 'unknown')} for {order_meta.get('parent_entry_id', 'unknown')})",
            extra={
                "event_type": "cleanup_orphans",
                "symbol": symbol,
                "order_id": order_id,
                "client_order_id": order_meta.get("client_order_id"),
                "parent_entry_id": order_meta.get("parent_entry_id"),
                "kind": order_meta.get("kind"),
                "hard": True,
                "position_amt": position_amt,
                "rid": rid,
                "trigger": GUARDIAN_RECONCILE_CANCEL_TRIGGER,
                "bridge_path": GUARDIAN_RECONCILE_CANCEL_PATH,
                "bridge_trace_ref": bridge_trace_ref,
                "cancel_submission_trace_ref": package4_trace_ref,
            },
        )

    def _guardian_reconcile_cancel_log_failure(
        self,
        *,
        symbol: str,
        order_id: str,
        order_type: str,
        rid: Optional[str],
        bridge_trace_ref: str,
        package4_trace_ref: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        exc: Optional[Exception] = None,
    ) -> None:
        extra = {
            "event_type": "guardian_reconcile_cancel_bridge_failure",
            "symbol": symbol,
            "order_id": order_id,
            "order_type": order_type,
            "rid": rid,
            "trigger": GUARDIAN_RECONCILE_CANCEL_TRIGGER,
            "bridge_path": GUARDIAN_RECONCILE_CANCEL_PATH,
            "bridge_trace_ref": bridge_trace_ref,
        }
        if package4_trace_ref is not None:
            extra["cancel_submission_trace_ref"] = package4_trace_ref
        if result is not None:
            extra["result"] = result
        if exc is not None:
            extra["error"] = str(exc)
            LOG.warning(
                "[GUARD] Failed to cancel orphan %s for %s: %s",
                order_id,
                symbol,
                exc,
                extra=extra,
            )
            return
        LOG.warning(
            "[GUARD] Failed to cancel order %s for %s, result: %s",
            order_id,
            symbol,
            result,
            extra=extra,
        )

    async def _execute_guardian_reconcile_cancel(
        self,
        *,
        symbol: str,
        order_id: Any,
        order_type: str,
        order_meta: Dict[str, Any],
        position_amt: float,
        rid: Optional[str],
    ) -> bool:
        try:
            request, cancel_decision = adapt_guardian_reconcile_to_dec_cancel(
                symbol=symbol,
                order_id=order_id,
                order_type=order_type,
                rid=rid,
            )
        except GuardianReconcileCancelBridgeError as exc:
            bridge_trace_ref = build_guardian_reconcile_cancel_trace_ref(
                status="reject",
                order_type=str(order_type or "UNKNOWN"),
                reason="bridge_validation",
            )
            self._guardian_reconcile_cancel_log_reject(
                symbol=symbol,
                order_id=order_id,
                order_type=str(order_type or "UNKNOWN"),
                rid=rid,
                reason=str(exc),
                bridge_trace_ref=bridge_trace_ref,
            )
            return False

        bridge_trace_ref = build_guardian_reconcile_cancel_trace_ref(
            status="success",
            order_type=request.order_type,
        )
        try:
            submission = CancelSubmissionPayload.from_dec_cancel(
                payload=cancel_decision.pld or {}
            )
        except CancelSubmissionAdapterError as exc:
            package4_trace_ref = build_cancel_submission_trace_ref(
                status="reject",
                reason="adapter_validation",
            )
            self._guardian_reconcile_cancel_log_reject(
                symbol=request.symbol,
                order_id=request.order_id,
                order_type=request.order_type,
                rid=rid,
                reason=str(exc),
                bridge_trace_ref=bridge_trace_ref,
                package4_trace_ref=package4_trace_ref,
            )
            return False

        package4_trace_ref = build_cancel_submission_trace_ref(
            status="success")
        try:
            result = await self.adapter.cancel_order(
                submission.symbol,
                submission.order_id,
            )
            if self._is_successful_cancel(result):
                self._guardian_reconcile_cancel_log_success(
                    symbol=submission.symbol,
                    order_id=submission.order_id,
                    order_meta=order_meta,
                    rid=rid,
                    position_amt=position_amt,
                    bridge_trace_ref=bridge_trace_ref,
                    package4_trace_ref=package4_trace_ref,
                )
                return True
            self._guardian_reconcile_cancel_log_failure(
                symbol=submission.symbol,
                order_id=submission.order_id,
                order_type=request.order_type,
                rid=rid,
                bridge_trace_ref=bridge_trace_ref,
                package4_trace_ref=package4_trace_ref,
                result=result if isinstance(result, dict) else None,
            )
            return False
        except Exception as exc:
            if not self._is_missing_order_cancel_outcome(exc):
                self._guardian_reconcile_cancel_log_failure(
                    symbol=submission.symbol,
                    order_id=submission.order_id,
                    order_type=request.order_type,
                    rid=rid,
                    bridge_trace_ref=bridge_trace_ref,
                    package4_trace_ref=package4_trace_ref,
                    exc=exc,
                )
                return False
            LOG.info(
                f"[GUARD] Orphan {submission.order_id} already absent (-2011/-2013) for {submission.symbol}",
                extra={
                    "event_type": "cleanup_orphans",
                    "symbol": submission.symbol,
                    "order_id": submission.order_id,
                    "hard": True,
                    "position_amt": position_amt,
                    "rid": rid,
                    "trigger": GUARDIAN_RECONCILE_CANCEL_TRIGGER,
                    "bridge_path": GUARDIAN_RECONCILE_CANCEL_PATH,
                    "bridge_trace_ref": bridge_trace_ref,
                    "cancel_submission_trace_ref": package4_trace_ref,
                },
            )
            return True

    async def cleanup_orphans(
        self,
        symbol: Optional[str] = None,
        hard: bool = False,
        batch_limit: int = 50,
        rid: Optional[str] = None,
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
            positions = await self.adapter.get_open_positions()
            position_amt = 0.0

            if symbol:
                for pos in positions:
                    if hasattr(pos, 'symbol'):
                        pos_symbol = pos.symbol  # type: ignore[union-attr]
                        # type: ignore[union-attr]
                        pos_amt = float(pos.position_amount)
                    else:
                        # type: ignore[union-attr]
                        pos_symbol = pos.get("symbol", "")
                        pos_amt = float(pos.get("position_amount")  # type: ignore[union-attr]
                                        # type: ignore[union-attr]
                                        or pos.get("positionAmt") or 0)

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
                                        # type: ignore[union-attr]
                                        or pos.get("positionAmt") or 0)
                    position_amt += pos_amt

            has_position = abs(position_amt) >= 1e-10

            if not hard and has_position:
                LOG.debug(
                    f"Position exists ({position_amt}), skipping orphan cleanup")
                return 0

            open_orders = await self.adapter.get_open_orders(symbol)

            has_candidates = False
            for raw_order in open_orders:
                order = self._normalize_order_payload(raw_order)
                if not order:
                    continue

                client_order_id = order.get("clientOrderId")
                is_reduce_only_raw = order.get("reduceOnly", False)
                is_close_position_raw = order.get("closePosition", False)
                is_reduce_only = coerce_exchange_bool(is_reduce_only_raw)
                is_close_position = coerce_exchange_bool(is_close_position_raw)
                guardian_like = self._is_guardian_client_order_id(
                    client_order_id)

                if is_reduce_only or is_close_position or guardian_like:
                    has_candidates = True
                    break

            if not has_candidates:
                return 0

            if not hard and not has_position:
                max_retries = 3
                retry_interval = 8.0

                for i in range(max_retries):
                    LOG.info(
                        f"[GUARD] Position missing for {symbol or 'ALL'}, re-checking in {retry_interval}s (attempt {i+1}/{max_retries})...")
                    await asyncio.sleep(retry_interval)

                    try:
                        positions = await self.adapter.get_open_positions()
                    except Exception as e:
                        LOG.warning(
                            f"[GUARD] Failed to re-fetch positions on attempt {i+1}: {e}")
                        continue

                    position_amt = 0.0

                    if symbol:
                        for pos in positions:
                            if hasattr(pos, 'symbol'):
                                # type: ignore[union-attr]
                                pos_symbol = pos.symbol
                                # type: ignore[union-attr]
                                pos_amt = float(pos.position_amount)
                            else:
                                # type: ignore[union-attr]
                                pos_symbol = pos.get("symbol", "")
                                pos_amt = float(pos.get("position_amount")  # type: ignore[union-attr]
                                                # type: ignore[union-attr]
                                                or pos.get("positionAmt") or 0)

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
                                                # type: ignore[union-attr]
                                                or pos.get("positionAmt") or 0)
                            position_amt += pos_amt

                    has_position = abs(position_amt) >= 1e-10

                    if has_position:
                        LOG.info(
                            f"[GUARD] Position reappeared for {symbol or 'ALL'} on attempt {i+1}! Skipping cleanup.")
                        return 0

                LOG.warning(
                    f"[GUARD] Position confirmed missing for {symbol or 'ALL'} after {max_retries} retries. Proceeding with cleanup.")

            LOG.info("[GUARD] Starting orphan cleanup", extra={
                "event_type": "cleanup_start",
                "symbol": symbol,
                "hard": hard,
                "position_amt": position_amt,
                "open_orders_count": len(open_orders),
                "has_position": has_position
            })

            cancelled_this_batch = 0
            typed_guardian_reconcile_path = bool(symbol and hard)
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
                is_reduce_only = coerce_exchange_bool(is_reduce_only_raw)
                is_close_position = coerce_exchange_bool(is_close_position_raw)
                guardian_like = self._is_guardian_client_order_id(
                    client_order_id)

                if not order_id:
                    continue

                LOG.debug(
                    f"Checking order {order_id} ({order_type}, reduceOnly={is_reduce_only}, closePosition={is_close_position})")

                order_meta = self.store.get(f"order:{order_id}")
                if not order_meta and (is_reduce_only or is_close_position or guardian_like):
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
                        self.store.put(f"client:{client_order_id}", order_id)
                    if inferred_symbol:
                        self.update_known_symbols([inferred_symbol])

                if not order_meta:
                    LOG.debug(f"Order {order_id} not tracked by guardian")
                    continue

                LOG.debug(f"Order {order_id} is tracked: {order_meta}")

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

                    if typed_guardian_reconcile_path:
                        typed_cancelled = await self._execute_guardian_reconcile_cancel(
                            symbol=str(symbol or order_meta["symbol"]),
                            order_id=order_id,
                            order_type=str(order_type or order_meta.get(
                                "type") or "UNKNOWN"),
                            order_meta=order_meta,
                            position_amt=position_amt,
                            rid=rid,
                        )
                        if typed_cancelled:
                            cancelled_count += 1
                            cancelled_this_batch += 1
                            self._metrics["guardian_orphans_cancelled_total"] += 1
                            tracked_symbol = symbol or order_meta["symbol"]
                            if tracked_symbol:
                                tidied_symbols.add(str(tracked_symbol).upper())
                        continue

                    # Package 12 typed seam — background orphan cancel (hard=False)
                    typed_cancelled = await self._execute_guardian_background_orphan_cancel(
                        symbol=str(symbol or order_meta["symbol"]),
                        order_id=order_id,
                        order_type=str(order_type or order_meta.get(
                            "type") or "UNKNOWN"),
                        position_amt=position_amt,
                        order_meta=order_meta,
                    )
                    if typed_cancelled:
                        cancelled_count += 1
                        cancelled_this_batch += 1
                        self._metrics["guardian_orphans_cancelled_total"] += 1
                        tracked_symbol = symbol or order_meta["symbol"]
                        if tracked_symbol:
                            tidied_symbols.add(str(tracked_symbol).upper())
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
                    self._emit_tidy_events(
                        symbol=tidy_symbol,
                        source="guardian_poll",
                        tidy_reason="orphan_cleanup",
                        why="guardian:orphan_cleanup:tidy",
                    )

        except Exception as e:
            LOG.error(f"Orphan cleanup failed: {e}")

        return cancelled_count

    def _guardian_old_bracket_cleanup_log_reject(
        self,
        *,
        symbol: str,
        order_id: Any,
        order_type: str,
        keep_parent_order_id: str,
        reason: str,
        bridge_trace_ref: str,
        package4_trace_ref: Optional[str] = None,
    ) -> None:
        extra = {
            "event_type": "guardian_old_bracket_cleanup_bridge_reject",
            "symbol": symbol,
            "order_id": order_id,
            "order_type": order_type,
            "keep_parent_order_id": keep_parent_order_id,
            "trigger": GUARDIAN_OLD_BRACKET_CLEANUP_TRIGGER,
            "bridge_path": GUARDIAN_OLD_BRACKET_CLEANUP_PATH,
            "bridge_trace_ref": bridge_trace_ref,
            "reason": reason,
        }
        if package4_trace_ref is not None:
            extra["cancel_submission_trace_ref"] = package4_trace_ref
        LOG.warning(
            "[GUARD] Rejecting old bracket cleanup for %s (%s): %s",
            order_id,
            symbol,
            reason,
            extra=extra,
        )

    def _guardian_old_bracket_cleanup_log_success(
        self,
        *,
        symbol: str,
        order_id: str,
        order_meta: Dict[str, Any],
        keep_parent_order_id: str,
        bridge_trace_ref: str,
        package4_trace_ref: str,
    ) -> None:
        LOG.info(
            "[GUARD] Cancelled old bracket for previous entry",
            extra={
                "event_type": "cleanup_other_brackets",
                "symbol": symbol,
                "order_id": order_id,
                "client_order_id": order_meta.get("client_order_id"),
                "parent_entry_id": order_meta.get("parent_entry_id"),
                "keep_parent_order_id": keep_parent_order_id,
                "trigger": GUARDIAN_OLD_BRACKET_CLEANUP_TRIGGER,
                "bridge_path": GUARDIAN_OLD_BRACKET_CLEANUP_PATH,
                "bridge_trace_ref": bridge_trace_ref,
                "cancel_submission_trace_ref": package4_trace_ref,
            },
        )

    def _guardian_old_bracket_cleanup_log_failure(
        self,
        *,
        symbol: str,
        order_id: str,
        order_type: str,
        keep_parent_order_id: str,
        bridge_trace_ref: str,
        package4_trace_ref: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        exc: Optional[Exception] = None,
    ) -> None:
        extra = {
            "event_type": "guardian_old_bracket_cleanup_bridge_failure",
            "symbol": symbol,
            "order_id": order_id,
            "order_type": order_type,
            "keep_parent_order_id": keep_parent_order_id,
            "trigger": GUARDIAN_OLD_BRACKET_CLEANUP_TRIGGER,
            "bridge_path": GUARDIAN_OLD_BRACKET_CLEANUP_PATH,
            "bridge_trace_ref": bridge_trace_ref,
        }
        if package4_trace_ref is not None:
            extra["cancel_submission_trace_ref"] = package4_trace_ref
        if result is not None:
            extra["result"] = result
        if exc is not None:
            extra["error"] = str(exc)
            LOG.warning(
                "[GUARD] Exception cancelling old bracket %s for %s: %s",
                order_id,
                symbol,
                exc,
                extra=extra,
            )
            return
        LOG.warning(
            "[GUARD] Failed to cancel old bracket %s for %s, result: %s",
            order_id,
            symbol,
            result,
            extra=extra,
        )

    # ------------------------------------------------------------------
    # Package 12 — background orphan cancel (hard=False) typed seam
    # ------------------------------------------------------------------

    def _guardian_background_orphan_cancel_log_reject(
        self,
        *,
        symbol: str,
        order_id: Any,
        order_type: str,
        reason: str,
        bridge_trace_ref: str,
        package4_trace_ref: Optional[str] = None,
    ) -> None:
        extra: Dict[str, Any] = {
            "event_type": "guardian_background_orphan_cancel_bridge_reject",
            "symbol": symbol,
            "order_id": order_id,
            "order_type": order_type,
            "trigger": GUARDIAN_BACKGROUND_ORPHAN_CANCEL_TRIGGER,
            "bridge_path": GUARDIAN_BACKGROUND_ORPHAN_CANCEL_PATH,
            "bridge_trace_ref": bridge_trace_ref,
            "reason": reason,
        }
        if package4_trace_ref is not None:
            extra["cancel_submission_trace_ref"] = package4_trace_ref
        LOG.warning(
            "[GUARD] Rejecting background orphan cancel for %s (%s): %s",
            order_id,
            symbol,
            reason,
            extra=extra,
        )

    def _guardian_background_orphan_cancel_log_success(
        self,
        *,
        symbol: str,
        order_id: str,
        order_type: str,
        bridge_trace_ref: str,
        package4_trace_ref: str,
    ) -> None:
        LOG.info(
            "[GUARD] Background orphan bracket cancelled",
            extra={
                "event_type": "guardian_background_orphan_cancel",
                "symbol": symbol,
                "order_id": order_id,
                "order_type": order_type,
                "trigger": GUARDIAN_BACKGROUND_ORPHAN_CANCEL_TRIGGER,
                "bridge_path": GUARDIAN_BACKGROUND_ORPHAN_CANCEL_PATH,
                "bridge_trace_ref": bridge_trace_ref,
                "cancel_submission_trace_ref": package4_trace_ref,
            },
        )

    def _guardian_background_orphan_cancel_log_failure(
        self,
        *,
        symbol: str,
        order_id: str,
        order_type: str,
        bridge_trace_ref: str,
        package4_trace_ref: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        exc: Optional[Exception] = None,
    ) -> None:
        extra: Dict[str, Any] = {
            "event_type": "guardian_background_orphan_cancel_bridge_failure",
            "symbol": symbol,
            "order_id": order_id,
            "order_type": order_type,
            "trigger": GUARDIAN_BACKGROUND_ORPHAN_CANCEL_TRIGGER,
            "bridge_path": GUARDIAN_BACKGROUND_ORPHAN_CANCEL_PATH,
            "bridge_trace_ref": bridge_trace_ref,
        }
        if package4_trace_ref is not None:
            extra["cancel_submission_trace_ref"] = package4_trace_ref
        if result is not None:
            extra["result"] = result
        if exc is not None:
            extra["error"] = str(exc)
            LOG.warning(
                "[GUARD] Exception cancelling background orphan %s for %s: %s",
                order_id,
                symbol,
                exc,
                extra=extra,
            )
            return
        LOG.warning(
            "[GUARD] Failed to cancel background orphan %s for %s, result: %s",
            order_id,
            symbol,
            result,
            extra=extra,
        )

    async def _execute_guardian_background_orphan_cancel(
        self,
        *,
        symbol: str,
        order_id: Any,
        order_type: str,
        position_amt: float,
        order_meta: Dict[str, Any],
    ) -> bool:
        """Typed Package 12 executor for background orphan cancel (hard=False).

        Routes the discovered orphan order through the seam-local typed bridge
        and the existing Package 4 ``CancelSubmissionPayload.from_dec_cancel()``
        typed cancel intake.  Raw direct adapter cancel is NOT the governing
        owner for this path.

        Package 9 ``hard=True`` path is explicitly NOT this method.
        """
        try:
            request, cancel_decision = adapt_guardian_background_orphan_to_dec_cancel(
                symbol=symbol,
                order_id=order_id,
                order_type=order_type,
            )
        except GuardianBackgroundOrphanCancelBridgeError as exc:
            bridge_trace_ref = build_guardian_background_orphan_cancel_trace_ref(
                status="reject",
                order_type=str(order_type or "UNKNOWN"),
                reason="bridge_validation",
            )
            self._guardian_background_orphan_cancel_log_reject(
                symbol=symbol,
                order_id=order_id,
                order_type=str(order_type or "UNKNOWN"),
                reason=str(exc),
                bridge_trace_ref=bridge_trace_ref,
            )
            return False

        bridge_trace_ref = build_guardian_background_orphan_cancel_trace_ref(
            status="success",
            order_type=request.order_type,
        )
        try:
            submission = CancelSubmissionPayload.from_dec_cancel(
                payload=cancel_decision.pld or {}
            )
        except CancelSubmissionAdapterError as exc:
            package4_trace_ref = build_cancel_submission_trace_ref(
                status="reject",
                reason="adapter_validation",
            )
            self._guardian_background_orphan_cancel_log_reject(
                symbol=request.symbol,
                order_id=request.order_id,
                order_type=request.order_type,
                reason=str(exc),
                bridge_trace_ref=bridge_trace_ref,
                package4_trace_ref=package4_trace_ref,
            )
            return False

        package4_trace_ref = build_cancel_submission_trace_ref(
            status="success")
        try:
            result = await self.adapter.cancel_order(
                submission.symbol,
                submission.order_id,
            )
            if self._is_successful_cancel(result):
                self._guardian_background_orphan_cancel_log_success(
                    symbol=submission.symbol,
                    order_id=submission.order_id,
                    order_type=request.order_type,
                    bridge_trace_ref=bridge_trace_ref,
                    package4_trace_ref=package4_trace_ref,
                )
                return True
            self._guardian_background_orphan_cancel_log_failure(
                symbol=submission.symbol,
                order_id=submission.order_id,
                order_type=request.order_type,
                bridge_trace_ref=bridge_trace_ref,
                package4_trace_ref=package4_trace_ref,
                result=result if isinstance(result, dict) else None,
            )
            return False
        except Exception as exc:
            if not self._is_missing_order_cancel_outcome(exc):
                self._guardian_background_orphan_cancel_log_failure(
                    symbol=submission.symbol,
                    order_id=submission.order_id,
                    order_type=request.order_type,
                    bridge_trace_ref=bridge_trace_ref,
                    package4_trace_ref=package4_trace_ref,
                    exc=exc,
                )
                return False
            LOG.info(
                f"[GUARD] Background orphan {submission.order_id} already absent (-2011/-2013) for {submission.symbol}",
                extra={
                    "event_type": "guardian_background_orphan_cancel",
                    "symbol": submission.symbol,
                    "order_id": submission.order_id,
                    "order_type": request.order_type,
                    "position_amt": position_amt,
                    "trigger": GUARDIAN_BACKGROUND_ORPHAN_CANCEL_TRIGGER,
                    "bridge_path": GUARDIAN_BACKGROUND_ORPHAN_CANCEL_PATH,
                    "bridge_trace_ref": bridge_trace_ref,
                    "cancel_submission_trace_ref": package4_trace_ref,
                },
            )
            return True

    async def _execute_guardian_old_bracket_cleanup_cancel(
        self,
        *,
        symbol: str,
        order_id: Any,
        order_type: str,
        keep_parent_order_id: str,
        order_meta: Dict[str, Any],
    ) -> bool:
        try:
            request, cancel_decision = adapt_guardian_old_bracket_cleanup_to_dec_cancel(
                symbol=symbol,
                order_id=order_id,
                order_type=order_type,
                keep_parent_order_id=keep_parent_order_id,
            )
        except GuardianOldBracketCleanupBridgeError as exc:
            bridge_trace_ref = build_guardian_old_bracket_cleanup_trace_ref(
                status="reject",
                order_type=str(order_type or "UNKNOWN"),
                reason="bridge_validation",
            )
            self._guardian_old_bracket_cleanup_log_reject(
                symbol=symbol,
                order_id=order_id,
                order_type=str(order_type or "UNKNOWN"),
                keep_parent_order_id=keep_parent_order_id,
                reason=str(exc),
                bridge_trace_ref=bridge_trace_ref,
            )
            return False

        bridge_trace_ref = build_guardian_old_bracket_cleanup_trace_ref(
            status="success",
            order_type=request.order_type,
        )
        try:
            submission = CancelSubmissionPayload.from_dec_cancel(
                payload=cancel_decision.pld or {}
            )
        except CancelSubmissionAdapterError as exc:
            package4_trace_ref = build_cancel_submission_trace_ref(
                status="reject",
                reason="adapter_validation",
            )
            self._guardian_old_bracket_cleanup_log_reject(
                symbol=request.symbol,
                order_id=request.order_id,
                order_type=request.order_type,
                keep_parent_order_id=request.keep_parent_order_id,
                reason=str(exc),
                bridge_trace_ref=bridge_trace_ref,
                package4_trace_ref=package4_trace_ref,
            )
            return False

        package4_trace_ref = build_cancel_submission_trace_ref(
            status="success")
        try:
            result = await self.adapter.cancel_order(
                submission.symbol,
                submission.order_id,
            )
            if self._is_successful_cancel(result):
                self._guardian_old_bracket_cleanup_log_success(
                    symbol=submission.symbol,
                    order_id=submission.order_id,
                    order_meta=order_meta,
                    keep_parent_order_id=keep_parent_order_id,
                    bridge_trace_ref=bridge_trace_ref,
                    package4_trace_ref=package4_trace_ref,
                )
                return True
            self._guardian_old_bracket_cleanup_log_failure(
                symbol=submission.symbol,
                order_id=submission.order_id,
                order_type=request.order_type,
                keep_parent_order_id=keep_parent_order_id,
                bridge_trace_ref=bridge_trace_ref,
                package4_trace_ref=package4_trace_ref,
                result=result if isinstance(result, dict) else None,
            )
            return False
        except Exception as exc:
            if not self._is_missing_order_cancel_outcome(exc):
                self._guardian_old_bracket_cleanup_log_failure(
                    symbol=submission.symbol,
                    order_id=submission.order_id,
                    order_type=request.order_type,
                    keep_parent_order_id=keep_parent_order_id,
                    bridge_trace_ref=bridge_trace_ref,
                    package4_trace_ref=package4_trace_ref,
                    exc=exc,
                )
                return False
            LOG.info(
                f"[GUARD] Old bracket {submission.order_id} already absent (-2011/-2013) for {submission.symbol}",
                extra={
                    "event_type": "cleanup_other_brackets",
                    "symbol": submission.symbol,
                    "order_id": submission.order_id,
                    "keep_parent_order_id": keep_parent_order_id,
                    "trigger": GUARDIAN_OLD_BRACKET_CLEANUP_TRIGGER,
                    "bridge_path": GUARDIAN_OLD_BRACKET_CLEANUP_PATH,
                    "bridge_trace_ref": bridge_trace_ref,
                    "cancel_submission_trace_ref": package4_trace_ref,
                },
            )
            return True

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

                is_reduce_only_raw = order.get("reduceOnly", False)
                is_close_position_raw = order.get("closePosition", False)
                is_reduce_only = coerce_exchange_bool(is_reduce_only_raw)
                is_close_position = coerce_exchange_bool(is_close_position_raw)

                guardian_like = self._is_guardian_client_order_id(
                    client_order_id)

                order_meta = self.store.get(f"order:{order_id}")
                if not order_meta and (is_reduce_only or is_close_position or guardian_like):
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
                        self.store.put(f"client:{client_order_id}", order_id)
                    if inferred_symbol:
                        self.update_known_symbols([inferred_symbol])

                if not order_meta:
                    continue

                if not (order_meta.get("reduce_only") or order_meta.get("close_position")):
                    continue

                parent_id = order_meta.get("parent_entry_id")
                if parent_id and str(parent_id) == str(keep_parent_order_id):
                    continue

                typed_cancelled = await self._execute_guardian_old_bracket_cleanup_cancel(
                    symbol=symbol,
                    order_id=order_id,
                    order_type=str(order_type or order_meta.get(
                        "type") or "UNKNOWN"),
                    keep_parent_order_id=str(keep_parent_order_id),
                    order_meta=order_meta,
                )
                if typed_cancelled:
                    cancelled_count += 1
                    cancelled_this_batch += 1
                    self._metrics["guardian_orphans_cancelled_total"] += 1

        except Exception as e:
            LOG.error(
                f"cleanup_other_brackets_for_symbol failed for {symbol}: {e}"
            )

        return cancelled_count

    @staticmethod
    def _is_missing_order_cancel_outcome(outcome: Any) -> bool:
        """Treat known Binance missing-order cancel outcomes as idempotent success."""
        if outcome is None:
            return False

        if isinstance(outcome, dict):
            error_code = outcome.get("code")
            message = outcome.get("msg") or ""
        else:
            error_code = getattr(outcome, "code", None)
            message = getattr(outcome, "msg", None) or ""

        message_text = str(message or outcome or "").lower()
        return error_code in (-2011, -2013) or "unknown order" in message_text or "order does not exist" in message_text

    def _is_successful_cancel(self, result: Dict[str, Any]) -> bool:
        """Check if cancel was successful, treating known missing-order cases as success."""
        normalized = self._normalize_order_payload(
            result) if result is not None else None
        payload = normalized if isinstance(normalized, dict) else (
            result if isinstance(result, dict) else {})

        if payload.get("status") == "CANCELED":
            return True

        if self._is_missing_order_cancel_outcome(payload):
            LOG.debug("Treating missing-order cancel as successful cancel")
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
            positions = await self.adapter.get_open_positions()
            position_amt = 0.0

            for pos in positions:
                if hasattr(pos, 'symbol'):
                    pos_symbol = pos.symbol  # type: ignore[union-attr]
                    # type: ignore[union-attr]
                    pos_amt = float(pos.position_amount)
                else:
                    # type: ignore[union-attr]
                    pos_symbol = pos.get("symbol", "")
                    pos_amt = float(pos.get("position_amount")  # type: ignore[union-attr]
                                    # type: ignore[union-attr]
                                    or pos.get("positionAmt") or 0)

                if pos_symbol == symbol:
                    position_amt = pos_amt
                    break

            has_position = abs(position_amt) >= 1e-10

            if has_position:
                LOG.debug(
                    f"Position exists for {symbol} ({position_amt}), skipping reconcile")
                return

            cancelled_count = await self.cleanup_orphans(
                symbol=symbol,
                hard=True,
                rid=rid,
            )

            LOG.info("Symbol reconciled", extra={
                "event_type": "reconcile_symbol",
                "symbol": symbol,
                "position_amt": position_amt,
                "cancelled_count": cancelled_count,
                "rid": rid
            })

            try:
                open_orders = await self.adapter.get_open_orders(symbol) if self.adapter else []
                any_tracked = False
                for o in open_orders:
                    oid = o.get("orderId")
                    meta = self.store.get(f"order:{oid}") if oid else None
                    if meta and (meta.get("reduce_only") or meta.get("close_position")):
                        any_tracked = True
                        break
                if not any_tracked and self.bus:
                    why = f"guardian:reconcile:tidy:rid={rid}"
                    self._emit_tidy_events(
                        symbol=symbol,
                        source="guardian_reconcile",
                        tidy_reason="close_reconcile_tidy",
                        why=why,
                        rid=rid,
                    )
                    self._emit_close_reconciled_event(
                        symbol=symbol,
                        rid=rid,
                        source="guardian_reconcile",
                    )
            except Exception:
                pass

        except Exception as e:
            LOG.error(f"Reconcile failed for {symbol}: {e}")

    # ---- Lifecycle ----

    async def start(self):
        """Start background polling if enabled"""
        if self.poll_interval_ms > 0 and self._poller_task is None:
            await self._startup_relink_known_symbols()
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
