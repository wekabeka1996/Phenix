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
- unified=True (default): LedgerStoreAdapter over SQLite OrderLedger (SSOT)
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

from apps.reference.adapters.binance_adapter import BinanceAPIError
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
log_dir = os.path.join(os.path.dirname(__file__), "../../../logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "order_guardian.log")

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
    def _resolve_guardian_cfg(cfg: Any) -> Any:
        """Resolve SSOT guardian config block from typed AuroraConfig."""
        if cfg is None:
            return None

        # NOTE: Many tests use MagicMock configs; attribute access on MagicMock
        # auto-creates nested mocks (truthy), which would incorrectly select a
        # non-real config block. Prefer explicitly-set attributes when possible.
        cfg_dict = getattr(cfg, "__dict__", None)

        exec_cfg = None
        if isinstance(cfg_dict, dict) and "execution" in cfg_dict:
            exec_cfg = cfg_dict.get("execution")
        else:
            try:
                exec_cfg = getattr(cfg, "execution", None)
            except Exception:
                exec_cfg = None

        if exec_cfg is not None:
            exec_dict = getattr(exec_cfg, "__dict__", None)
            if isinstance(exec_dict, dict) and "order_guardian" in exec_dict:
                og = exec_dict.get("order_guardian")
            else:
                try:
                    og = getattr(exec_cfg, "order_guardian", None)
                except Exception:
                    og = None
            if og is not None and (isinstance(og, dict) or isinstance(og, str)):
                return og
            if og is not None and not hasattr(cfg, "__getattr__"):
                return og

        trading = None
        if isinstance(cfg_dict, dict) and "trading" in cfg_dict:
            trading = cfg_dict.get("trading")
        else:
            try:
                trading = getattr(cfg, "trading", None)
            except Exception:
                trading = None

        trading_exec = getattr(trading, "execution", None) if trading is not None else None
        if trading_exec is not None:
            og = getattr(trading_exec, "order_guardian", None)
            if og is not None and (isinstance(og, dict) or isinstance(og, str)):
                return og

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
    ):
        if isinstance(config, dict):
            raise TypeError("OrderGuardian requires typed config object, got dict")

        self.adapter = adapter
        self.clock = clock or time
        self.poll_interval_ms = poll_interval_ms
        self.bus = bus
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

        # Resolve store: explicit > config-driven > InMemoryStore fallback
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

        When no config is provided (e.g. tests, shadow mode), defaults to
        InMemoryStore — matching the old services/ behaviour of
        ``store = store or InMemoryStore()``.
        """
        if config is None:
            return InMemoryStore()

        guardian_cfg = self._resolve_guardian_cfg(config)

        unified = True
        if guardian_cfg is not None:
            if isinstance(guardian_cfg, dict):
                unified = bool(guardian_cfg.get("unified", True))
            else:
                unified = bool(aget(guardian_cfg, "unified", True))

        if not unified:
            return InMemoryStore()

        # unified=True: resolve db path and build LedgerStoreAdapter
        db_path = None
        if guardian_cfg is not None:
            if isinstance(guardian_cfg, dict):
                db_path = guardian_cfg.get("ledger_db_path")
            else:
                db_path = aget(guardian_cfg, "ledger_db_path", None)

        if isinstance(db_path, Path):
            db_path = str(db_path)
        if db_path and isinstance(db_path, str) and db_path != ":memory:":
            try:
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        elif not isinstance(db_path, str):
            db_path = None

        try:
            LedgerStoreAdapter, OrderLedger = _get_ledger_store()
            ledger = OrderLedger(db_path or ":memory:")
            return LedgerStoreAdapter(ledger)
        except Exception as exc:
            LOG.warning(
                f"[GUARD] Failed to build LedgerStoreAdapter, falling back to InMemoryStore: {exc}"
            )
            return InMemoryStore()

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
                is_reduce_only = str(is_reduce_only_raw).lower() == "true" if isinstance(
                    is_reduce_only_raw, str) else bool(is_reduce_only_raw)
                is_close_position = str(is_close_position_raw).lower() == "true" if isinstance(
                    is_close_position_raw, str) else bool(is_close_position_raw)
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
                pass

        except Exception as e:
            LOG.error(f"Cleanup before close failed: {e}")

        return cancelled_count

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
            positions = await self.adapter.get_open_positions()
            position_amt = 0.0

            if symbol:
                for pos in positions:
                    if hasattr(pos, 'symbol'):
                        pos_symbol = pos.symbol  # type: ignore[union-attr]
                        pos_amt = float(pos.position_amount)  # type: ignore[union-attr]
                    else:
                        pos_symbol = pos.get("symbol", "")  # type: ignore[union-attr]
                        pos_amt = float(pos.get("position_amount")  # type: ignore[union-attr]
                                        or pos.get("positionAmt") or 0)  # type: ignore[union-attr]

                    if pos_symbol == symbol:
                        position_amt = pos_amt
                        break
            else:
                for pos in positions:
                    if hasattr(pos, 'position_amount'):
                        pos_amt = float(pos.position_amount)  # type: ignore[union-attr]
                    else:
                        pos_amt = float(pos.get("position_amount")  # type: ignore[union-attr]
                                        or pos.get("positionAmt") or 0)  # type: ignore[union-attr]
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
                is_reduce_only = str(is_reduce_only_raw).lower() == "true" if isinstance(
                    is_reduce_only_raw, str) else bool(is_reduce_only_raw)
                is_close_position = str(is_close_position_raw).lower() == "true" if isinstance(
                    is_close_position_raw, str) else bool(is_close_position_raw)
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
                                pos_symbol = pos.symbol  # type: ignore[union-attr]
                                pos_amt = float(pos.position_amount)  # type: ignore[union-attr]
                            else:
                                pos_symbol = pos.get("symbol", "")  # type: ignore[union-attr]
                                pos_amt = float(pos.get("position_amount")  # type: ignore[union-attr]
                                                or pos.get("positionAmt") or 0)  # type: ignore[union-attr]

                            if pos_symbol == symbol:
                                position_amt = pos_amt
                                break
                    else:
                        for pos in positions:
                            if hasattr(pos, 'position_amount'):
                                pos_amt = float(pos.position_amount)  # type: ignore[union-attr]
                            else:
                                pos_amt = float(pos.get("position_amount")  # type: ignore[union-attr]
                                                or pos.get("positionAmt") or 0)  # type: ignore[union-attr]
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
                        self.bus.emit(
                            "EVT:SYMBOL_TIDY",
                            {
                                "symbol": tidy_symbol,
                                "source": "guardian_poll",
                                "ts_ms": int(self.clock.time() * 1000),
                            },
                            why="guardian:orphan_cleanup:tidy",
                        )
                    except Exception as e:
                        LOG.error(
                            f"[{tidy_symbol}] CRITICAL: Failed to emit EVT:SYMBOL_TIDY: {e}"
                        )

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
            LOG.debug("No adapter available, skipping cleanup_other_brackets_for_symbol")
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

                guardian_like = self._is_guardian_client_order_id(client_order_id)

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
                    is_unknown_error = isinstance(e, BinanceAPIError) and getattr(e, "code", None) == -2011
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
            positions = await self.adapter.get_open_positions()
            position_amt = 0.0

            for pos in positions:
                if hasattr(pos, 'symbol'):
                    pos_symbol = pos.symbol  # type: ignore[union-attr]
                    pos_amt = float(pos.position_amount)  # type: ignore[union-attr]
                else:
                    pos_symbol = pos.get("symbol", "")  # type: ignore[union-attr]
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

            cancelled_count = await self.cleanup_orphans(symbol=symbol, hard=True)

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
                    try:
                        self.bus.emit(
                            "EVT:SYMBOL_TIDY",
                            {
                                "symbol": symbol,
                                "rid": rid,
                                "source": "guardian_reconcile",
                                "ts_ms": int(self.clock.time() * 1000),
                            },
                            why=f"guardian:reconcile:tidy:rid={rid}",
                        )
                    except Exception as e:
                        LOG.error(
                            f"[{symbol}] CRITICAL: Failed to emit EVT:SYMBOL_TIDY: {e}"
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
