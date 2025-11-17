"""
PositionTracking domain component.

Tracks positions, calculates P&L, and emits EVT:PORTFOLIO_STATE_UPDATED events.
"""

import copy
import decimal
import hashlib
import json
import math
import threading
import logging
import time
from collections import OrderedDict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, TYPE_CHECKING, Callable

import asyncio
from contextlib import asynccontextmanager

try:
    from unittest.mock import Mock
except ImportError:  # pragma: no cover - Mock always available in stdlib
    Mock = None  # type: ignore

from vfoundation.core.protocol import Message
from vfoundation.dr import wal  # WAL module for disaster recovery

from apps.reference.config_exposure_policy import resolve_exposure_policy
from apps.reference.telemetry.metrics import (
    update_position_sync_last_account_update_age,
    inc_position_sync_drift_total,
    set_position_sync_current_drift,
    inc_position_sync_trade_dedup_hit,
    inc_position_sync_resync_total,
)

# Import AlertManager for manual intervention alerts
try:
    from apps.reference.telemetry.alerts import AlertManager
    ALERT_MANAGER_AVAILABLE = True
except ImportError:
    ALERT_MANAGER_AVAILABLE = False
    AlertManager = None  # type: ignore

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


logger = logging.getLogger(__name__)


def _d(value: Any, default: decimal.Decimal = decimal.Decimal("0")) -> decimal.Decimal:
    """
    Safe Decimal parsing function.

    Converts value to Decimal safely, returning default on failure.
    """
    try:
        if isinstance(value, decimal.Decimal):
            return value
        return decimal.Decimal(str(value))
    except (ValueError, TypeError, decimal.InvalidOperation):
        return default


class PositionTracking:
    """
    Position tracking component that processes trades and calculates portfolio state.

    Subscribes to EVT:TRADE_EXECUTED and emits EVT:PORTFOLIO_STATE_UPDATED.
    """

    def __init__(self, fsm: "FSMCore", config: dict[str, Any]) -> None:
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")
        self._exposure_policy = resolve_exposure_policy(config)

        self.logger.info(
            "Resolved exposure policy",
            extra={
                "source": self._exposure_policy.source,
                "max_equity_utilization_pct": self._exposure_policy.caps.max_equity_utilization_ratio,
                "max_portfolio_fraction": self._exposure_policy.caps.max_portfolio_fraction,
                "max_side_utilization_pct": self._exposure_policy.caps.max_side_utilization_ratio,
                "max_directional_ratio": self._exposure_policy.caps.max_directional_ratio,
            },
        )

        # Subscribe to events
        self.fsm.listen("EVT:TRADE_EXECUTED", self.on_trade_executed)
        self.fsm.listen("EVT:ACCOUNT_UPDATE_RECEIVED", self.on_account_update)
        self.fsm.listen("EVT:BALANCE_UPDATE_RECEIVED", self.on_balance_update)
        self.fsm.listen("CMD:POSITION_FORCE_RESYNC",
                        self.on_force_resync_command)

        # Initialize AlertManager for manual intervention alerts
        self.alert_manager: Optional[AlertManager] = None
        if ALERT_MANAGER_AVAILABLE:
            alert_manager_config = self._build_alert_manager_config()
            try:
                self.alert_manager = AlertManager(
                    config=alert_manager_config, logger=self.logger)
                self.logger.info(
                    "AlertManager initialized in PositionTracking")
            except Exception as e:
                self.logger.warning(f"Failed to initialize AlertManager: {e}")

        # State tracking
        # symbol -> position data
        self._positions: Dict[str, Dict[str, Any]] = {}
        self._realized_pnl: decimal.Decimal = decimal.Decimal("0")
        self._equity: decimal.Decimal = decimal.Decimal(
            "0"
        )  # Will be loaded from account
        self._initial_balance: Optional[decimal.Decimal] = (
            None  # Initial wallet balance (AURORA_STATE_SYNC_V1)
        )

        # Manual intervention metrics
        self.manual_intervention_detected_total = 0
        # Thread-safety for sync handlers (Wave 0: threading.RLock)
        self._lock = threading.RLock()
        # Async lock for atomic position/balance updates
        self._state_lock = asyncio.Lock()
        self._strict_wal = self._resolve_strict_wal_flag()
        if not self._strict_wal:
            self.logger.warning(
                "PositionTracking strict_wal disabled: WAL failures will log but processing continues"
            )
        # Trade deduplication / reconciliation config
        self._trade_dedup_window_sec = self._coerce_float(
            self._get_config_value(
                ["trading", "position_sync", "trade_dedup_window_sec"]
            ),
            default=600.0,
        )
        self._trade_dedup_max_entries = self._coerce_int(
            self._get_config_value(
                ["trading", "position_sync", "trade_dedup_max_entries"]
            ),
            default=2000,
        )
        self._recent_trade_uids: "OrderedDict[str, float]" = OrderedDict()
        self._dedup_lock = threading.Lock()
        self.trade_dedup_hits_total = 0
        self.snapshot_reconciliation_drift_total = 0
        self._last_account_update_ts_ms: Optional[int] = None
        self._quantity_epsilon = decimal.Decimal("1e-9")
        self._snapshot_fetcher: Optional[Callable[[
            Optional[str], str, Optional[str]], Dict[str, Any]]] = None

    @asynccontextmanager
    async def _atomic_update(self):
        """Атомарне оновлення позицій і балансів з rollback при помилці."""
        # Зберігаємо snapshot для rollback
        positions_snapshot = dict(self._positions)
        realized_pnl_snapshot = self._realized_pnl
        equity_snapshot = self._equity
        try:
            yield
        except Exception:
            # Rollback на snapshot при помилці
            self._positions = positions_snapshot
            self._realized_pnl = realized_pnl_snapshot
            self._equity = equity_snapshot
            raise

    def _resolve_strict_wal_flag(self) -> bool:
        """Read strict WAL flag from config with sensible fallbacks."""
        candidate_paths = [
            ["trading", "dr", "strict_wal"],
            ["dr", "strict_wal"],
            ["position_tracking", "strict_wal"],
            ["system", "dr", "strict_wal"],
        ]
        for path in candidate_paths:
            value = self._get_config_value(path)
            if value is not None:
                return self._coerce_bool(value, True)
        return True

    def _get_config_value(self, path: List[str]) -> Any:
        """Traverse nested dict/object config using path segments."""
        node: Any = self.config
        for segment in path:
            if node is None:
                return None
            if isinstance(node, dict):
                node = node.get(segment)
                continue
            try:
                node = getattr(node, segment)
            except AttributeError:
                return None
        return node

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
            return default
        try:
            return bool(value)
        except Exception:
            return default

    def _first_config_value(self, paths: List[List[str]]) -> Any:
        for path in paths:
            value = self._get_config_value(path)
            if value is not None:
                return value
        return None

    def _coerce_alert_numeric(self, raw_value: Any, default: float, field_name: str) -> float:
        if raw_value is None:
            return default
        if Mock is not None and isinstance(raw_value, Mock):
            self.logger.error(
                "Invalid AlertManager config value for %s: received mock object",
                field_name,
            )
            raise ValueError(
                f"Invalid AlertManager config value for {field_name}: mock object"
            )
        try:
            coerced = float(raw_value)
        except (TypeError, ValueError):
            self.logger.error(
                "Invalid AlertManager config value for %s: %r (type=%s)",
                field_name,
                raw_value,
                type(raw_value).__name__,
            )
            raise ValueError(
                f"Invalid AlertManager config value for {field_name}: {raw_value!r}"
            )
        if not math.isfinite(coerced):
            self.logger.error(
                "Invalid AlertManager config value for %s: non-finite %r",
                field_name,
                raw_value,
            )
            raise ValueError(
                f"Invalid AlertManager config value for {field_name}: {raw_value!r}"
            )
        return coerced

    def _build_alert_manager_config(self) -> Dict[str, Any]:
        dedup_window = self._coerce_alert_numeric(
            self._first_config_value(
                [
                    ["alerting", "dedup_window_s"],
                    ["alerts", "deduplication_window_sec"],
                    ["alerts", "dedup_window_s"],
                ]
            ),
            default=300.0,
            field_name="alerting.dedup_window_s",
        )

        risk_threshold = self._coerce_alert_numeric(
            self._first_config_value(
                [
                    ["alerting", "risk_threshold_pct"],
                    ["alerts", "thresholds", "risk_gate_percent"],
                    ["alerts", "risk_threshold_pct"],
                ]
            ),
            default=80.0,
            field_name="alerting.risk_threshold_pct",
        )

        wal_threshold = self._coerce_alert_numeric(
            self._first_config_value(
                [
                    ["alerting", "wal_threshold_mb"],
                    ["alerts", "thresholds", "wal_size_mb"],
                ]
            ),
            default=500.0,
            field_name="alerting.wal_threshold_mb",
        )

        raw_alerts = self._get_config_value(["alerts"])
        if raw_alerts is None:
            sanitized_alerts: Dict[str, Any] = {}
        elif isinstance(raw_alerts, Mapping):
            sanitized_alerts = copy.deepcopy(raw_alerts)
        else:
            self.logger.error(
                "Invalid alerts config type: expected mapping, got %s",
                type(raw_alerts).__name__,
            )
            raise ValueError("Invalid alerts config: expected mapping")

        sanitized_alerts["deduplication_window_sec"] = dedup_window

        thresholds_raw = sanitized_alerts.get("thresholds")
        if thresholds_raw is None:
            thresholds: Dict[str, Any] = {}
        elif isinstance(thresholds_raw, Mapping):
            thresholds = dict(thresholds_raw)
        else:
            self.logger.error(
                "Invalid alerts.thresholds type: expected mapping, got %s",
                type(thresholds_raw).__name__,
            )
            raise ValueError(
                "Invalid alerts.thresholds config: expected mapping")

        thresholds["risk_gate_percent"] = risk_threshold
        thresholds["wal_size_mb"] = wal_threshold
        sanitized_alerts["thresholds"] = thresholds

        return {"alerts": sanitized_alerts}

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_rid(rid: Optional[Any]) -> Optional[str]:
        """Convert arbitrary RID objects (Mocks, UUIDs, etc.) to strings for logging/WAL."""
        if rid is None:
            return None
        try:
            return str(rid)
        except Exception:
            return repr(rid)

    def _append_event_to_wal(self, label: str, payload: Dict[str, Any], rid: Optional[str]) -> bool:
        """Append event to WAL, respecting strict/non-strict modes."""
        rid_str = self._normalize_rid(rid)
        try:
            wal_hash = wal.append(payload)
        except Exception as exc:  # pragma: no cover - exercised via tests
            return self._handle_wal_failure(
                label,
                rid_str,
                reason="exception",
                exc=exc,
            )

        if wal_hash is None:
            return self._handle_wal_failure(
                label,
                rid_str,
                reason="lock timeout (append returned None)",
            )

        self.logger.debug(
            "WAL: Appended %s with hash=%s",
            label,
            str(wal_hash)[:8],
        )
        return True

    def _handle_wal_failure(
        self,
        label: str,
        rid: Optional[str],
        *,
        reason: Optional[str] = None,
        exc: Optional[Exception] = None,
    ) -> bool:
        """Handle WAL failure according to strict_wal flag; return True to continue."""
        rid_str = f"RID={rid}" if rid is not None else "RID=UNKNOWN"
        reason_suffix = f": {reason}" if reason else ""
        base_msg = f"Failed to append {label} to WAL ({rid_str}){reason_suffix}"

        if self._strict_wal:
            if exc:
                self.logger.critical(base_msg, exc_info=True)
            else:
                self.logger.critical(base_msg)
            return False

        continuation_msg = base_msg + " -- strict_wal=False, continuing"
        if exc:
            self.logger.error(continuation_msg, exc_info=True)
        else:
            self.logger.error(continuation_msg)
        return True

    def _reconcile_positions_from_snapshot(
        self, account_positions: List[Dict[str, Any]]
    ) -> tuple[set[str], Dict[str, Dict[str, Any]]]:
        """Apply snapshot as ground truth; return changed symbols and manual closes."""
        changed_symbols: set[str] = set()
        manual_closes: Dict[str, Dict[str, Any]] = {}
        normalized_snapshot: Dict[str, Dict[str, Any]] = {}
        binance_symbols: set[str] = set()
        zero_symbols: set[str] = set()

        for pos in account_positions:
            symbol = pos.get("symbol")
            if not symbol:
                continue
            binance_symbols.add(symbol)
            quantity = _d(pos.get("positionAmt", 0))
            avg_price = _d(pos.get("entryPrice", 0))
            if abs(quantity) > self._quantity_epsilon:
                normalized_snapshot[symbol] = {
                    "quantity": quantity,
                    "avg_price": avg_price,
                    "venues": ["binance"],
                }
            else:
                zero_symbols.add(symbol)

        with self._lock:
            prev_positions = {
                sym: data.copy() if isinstance(data, dict) else data
                for sym, data in self._positions.items()
            }

            for symbol, snapshot_entry in normalized_snapshot.items():
                old_entry = self._positions.get(symbol)
                if (
                    old_entry is None
                    or old_entry.get("quantity") != snapshot_entry["quantity"]
                    or old_entry.get("avg_price") != snapshot_entry["avg_price"]
                ):
                    changed_symbols.add(symbol)
                self._positions[symbol] = snapshot_entry

            for symbol in zero_symbols:
                if symbol in self._positions:
                    changed_symbols.add(symbol)
                    self._positions.pop(symbol, None)

            removed_symbols = set(prev_positions.keys()) - binance_symbols
            for symbol in removed_symbols:
                manual_closes[symbol] = prev_positions.get(symbol, {})
                changed_symbols.add(symbol)
                self._positions.pop(symbol, None)

        return changed_symbols, manual_closes

    def _extract_trade_uid(self, payload: Dict[str, Any]) -> str:
        """Derive a stable trade UID from payload data."""
        candidate_keys = (
            "dedup_uid",
            "trade_uid",
            "trade_id",
            "tradeId",
            "id",
            "execution_id",
            "executionId",
            "order_trade_id",
            "orderTradeId",
            "orderId",
        )
        for key in candidate_keys:
            value = payload.get(key)
            if value:
                return str(value)

        parts: List[str] = []
        for key in ("symbol", "side", "clientOrderId", "orderId"):
            value = payload.get(key)
            if value is not None:
                parts.append(str(value))
        qty = payload.get("quantity") or payload.get("qty")
        price = payload.get("price")
        ts = payload.get("ts")
        if qty is not None:
            parts.append(str(qty))
        if price is not None:
            parts.append(str(price))
        if ts is not None:
            parts.append(str(ts))
        fallback = "|".join(parts)
        if not fallback:
            fallback = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(fallback.encode("utf-8")).hexdigest()

    def _trade_is_duplicate(self, trade_uid: str, ts_seconds: Optional[float]) -> bool:
        """Return True if trade UID already processed within dedup window."""
        now = self._now()
        event_ts = ts_seconds if ts_seconds is not None else now
        cutoff = now - max(self._trade_dedup_window_sec, 0)

        # If incoming timestamp is stale (e.g., historical ms), anchor to now so we do not prune immediately
        if event_ts < cutoff:
            event_ts = now

        with self._dedup_lock:
            self._prune_trade_cache(cutoff)

            if trade_uid in self._recent_trade_uids:
                self._recent_trade_uids.move_to_end(trade_uid)
                return True

            self._recent_trade_uids[trade_uid] = event_ts
            if len(self._recent_trade_uids) > max(1, self._trade_dedup_max_entries):
                self._recent_trade_uids.popitem(last=False)
            return False

    def _prune_trade_cache(self, cutoff_ts: float) -> None:
        while self._recent_trade_uids:
            uid, ts_val = next(iter(self._recent_trade_uids.items()))
            if ts_val >= cutoff_ts:
                break
            self._recent_trade_uids.popitem(last=False)

    @staticmethod
    def _extract_ts_seconds(payload: Dict[str, Any]) -> Optional[float]:
        ts = payload.get("ts")
        if ts is None:
            return None
        try:
            ts_float = float(ts)
        except (TypeError, ValueError):
            return None
        # Incoming ts often ms; normalize to seconds if ts is large
        if ts_float > 1e12:  # microseconds
            return ts_float / 1_000_000
        if ts_float > 1e9:  # milliseconds
            return ts_float / 1_000
        return ts_float

    @staticmethod
    def _now() -> float:
        return time.time()

    async def update_position(self, symbol: str, qty: decimal.Decimal, entry_price: decimal.Decimal):
        """Оновити позицію атомарно з перевіркою балансу."""
        async with self._atomic_update():
            # Перевірка достатності балансу ПЕРЕД змінами
            cost = abs(qty) * entry_price
            if cost > self._equity:
                raise ValueError("Insufficient balance")

            # Застосувати зміни
            self._positions[symbol] = {
                "quantity": qty,
                "avg_price": entry_price,
                "unrealized_pnl": decimal.Decimal("0")
            }
            self._equity -= cost

    def start(self) -> None:
        """Start the position tracking component and emit initial portfolio state."""
        # Emit initial portfolio state with zero positions
        positions_last_ts_ms = int(time.time() * 1000)

        portfolio_payload = {
            "ts": positions_last_ts_ms,
            "equity": "0",  # No equity data yet
            "realized_pnl": "0",
            "unrealized_pnl": "0",
            "available_balance": "0",
            "positions": [],  # Empty positions list
            "open_positions_usd": "0",
            "open_positions_margin_usd": "0",
            # EXP-DIRECTION: Initial zero margin by side
            "positions_by_side": {
                "long_margin": "0",
                "short_margin": "0"
            },
            "positions_last_ts_ms": positions_last_ts_ms,
        }

        self.logger.info("Emitting initial EVT:PORTFOLIO_STATE_UPDATED...")
        self.fsm.emit(
            "EVT:PORTFOLIO_STATE_UPDATED",
            payload=portfolio_payload,
            why="Initial portfolio state with no positions.",
        )

    def on_trade_executed(self, event: Message) -> None:
        """
        Handle incoming trade executed event and update portfolio state.

        Args:
            event: FSM event with trade payload
        """
        self.logger.info("Handling EVT:TRADE_EXECUTED...")

        payload = event.pld
        trade_uid = self._extract_trade_uid(payload)
        payload.setdefault("dedup_uid", trade_uid)
        trade_ts_seconds = self._extract_ts_seconds(payload)
        if self._trade_is_duplicate(trade_uid, trade_ts_seconds):
            self.trade_dedup_hits_total += 1
            inc_position_sync_trade_dedup_hit()
            self.logger.info(
                "TRADE_DEDUP_HIT: uid=%s symbol=%s side=%s", trade_uid, payload.get(
                    "symbol"), payload.get("side")
            )
            return

        # --- WAL INTEGRATION (FSMP-RESILIENCE-T03-A) ---
        # Write event to WAL BEFORE processing to ensure disaster recovery
        rid_str = self._normalize_rid(event.rid)
        event_dict = {
            "op": event.op,
            "verb": event.verb,
            "pld": payload,
            "src": event.src,
            "dst": event.dst,
            # Convert RID to string for JSON serialization
            "rid": rid_str,
            "timestamp": time.time(),
            "dedup_uid": trade_uid,
        }
        if not self._append_event_to_wal("EVT:TRADE_EXECUTED", event_dict, rid_str):
            return
        # --- END WAL INTEGRATION ---

        # Extract required fields from payload
        symbol = payload["symbol"]
        side = payload["side"]
        price = _d(payload["price"])
        quantity = _d(payload["quantity"])
        ts = payload["ts"]
        fees = _d(payload.get("fees", 0))
        venue = payload["venue"]

        # Convert side to quantity sign
        if side == "buy":
            qty = abs(quantity)
        elif side == "sell":
            qty = -abs(quantity)
        else:
            raise ValueError(f"Invalid side: {side}")

        # Update position and calculate P&L
        # Protect mutation with lock to avoid races in Wave 0
        with self._lock:
            self._update_position(symbol, qty, price, fees, venue)

        # Calculate open positions notional (EXP-FIX: Portfolio Notional Hard Gate)
        open_positions_usd = self._calculate_open_positions_notional()
        # EXP-LEVERAGE-001: Calculate margin used (backward compatible)
        open_positions_margin_usd = self._calc_margin_used_usd([])
        # EXP-DIRECTION: Calculate margin by side
        margin_by_side = self._calculate_margin_by_side([])
        positions_last_ts_ms = int(time.time() * 1000)

        # Emit portfolio state updated event
        portfolio_payload = {
            "ts": ts,
            # Preserve Decimal precision as string
            "equity": str(self._equity),
            "realized_pnl": str(
                self._realized_pnl
            ),  # Preserve Decimal precision as string
            "unrealized_pnl": str(
                self._calculate_unrealized_pnl()
            ),  # Preserve Decimal precision as string
            "positions": self._get_positions_snapshot(),
            "open_positions_usd": str(
                open_positions_usd
            ),  # EXP-FIX: Notional for exposure gate
            "open_positions_margin_usd": str(
                open_positions_margin_usd
            ),  # EXP-LEVERAGE-001: Margin for exposure gate
            # EXP-DIRECTION: Per-side margin for directional checks
            "positions_by_side": {
                "long_margin": str(margin_by_side["long_margin"]),
                "short_margin": str(margin_by_side["short_margin"])
            },
            # EXP-FIX: Timestamp for staleness check
            "positions_last_ts_ms": positions_last_ts_ms,
        }

        # Emit portfolio state updated event
        self.logger.info("Emitting EVT:PORTFOLIO_STATE_UPDATED...")
        self.fsm.emit(
            "EVT:PORTFOLIO_STATE_UPDATED",
            payload=portfolio_payload,
            why=f"Portfolio updated after trade execution for {symbol}.",
        )

        self.logger.info(f"Emitted portfolio update after trade for {symbol}.")

    def on_account_update(self, event: Message) -> None:
        """
        Handle incoming account update event from Binance API.

        Args:
            event: FSM event with account payload
        """
        self.logger.info("Handling EVT:ACCOUNT_UPDATE_RECEIVED...")

        payload_clean = dict(event.pld or {})
        force_resync = bool(payload_clean.pop("_force_resync", False))
        force_reason = payload_clean.pop("_force_resync_reason", None)
        force_rid = payload_clean.pop("_force_resync_rid", None)
        requested_symbol = payload_clean.pop("_force_resync_symbol", None)

        if not force_resync:
            # --- WAL INTEGRATION (FSMP-RESILIENCE-T03-A) ---
            # Write event to WAL BEFORE processing to ensure disaster recovery
            rid_str = self._normalize_rid(event.rid)
            event_dict = {
                "op": event.op,
                "verb": event.verb,
                "pld": payload_clean,
                "src": event.src,
                "dst": event.dst,
                # Convert RID to string for JSON serialization
                "rid": rid_str,
                "timestamp": time.time(),
            }
            if not self._append_event_to_wal("EVT:ACCOUNT_UPDATE_RECEIVED", event_dict, rid_str):
                return
            # --- END WAL INTEGRATION ---
        else:
            self.logger.warning(
                "Skipping WAL append for force_resync snapshot (reason=%s, symbol=%s, rid=%s)",
                force_reason,
                requested_symbol,
                force_rid or event.rid,
            )

        payload = payload_clean
        self._last_account_update_ts_ms = payload.get(
            "ts") or int(time.time() * 1000)
        self._record_last_account_update_age()

        # Update equity from account data
        total_wallet_balance = _d(payload.get("totalWalletBalance", 0))
        total_unrealized_profit = _d(payload.get("totalUnrealizedProfit", 0))
        total_cross_wallet_balance = _d(
            payload.get(
                "totalCrossWalletBalance",
                total_wallet_balance - total_unrealized_profit,
            )
        )

        self._equity = total_wallet_balance

        # === AURORA_STATE_SYNC_V1: Recalculate realized_pnl from ACCOUNT_UPDATE ===
        # totalCrossWalletBalance = balance without unrealized PnL
        # realized_pnl = totalCrossWalletBalance - initial_balance
        if self._initial_balance is None:
            # First account update - set initial balance
            self._initial_balance = total_cross_wallet_balance
            self._realized_pnl = decimal.Decimal("0")
            self.logger.info(
                f"[STATE_SYNC] Initial balance set: ${self._initial_balance}"
            )
        else:
            # Recalculate realized_pnl from cross wallet balance
            old_realized_pnl = self._realized_pnl
            self._realized_pnl = total_cross_wallet_balance - self._initial_balance

            if old_realized_pnl != self._realized_pnl:
                self.logger.debug(
                    "[STATE_SYNC] Realized PnL recalculated: "
                    f"${old_realized_pnl} → ${self._realized_pnl} "
                    f"(cross_balance=${total_cross_wallet_balance}, initial=${self._initial_balance})"
                )

        # Update positions from account data using snapshot reconciliation helper
        account_positions = payload.get("positions", [])
        self.logger.info(
            f"📊 SYNC: Received {len(account_positions)} positions from Binance")

        changed_symbols, manual_closes = self._reconcile_positions_from_snapshot(
            account_positions
        )

        if changed_symbols:
            drift_count = len(changed_symbols)
            self.snapshot_reconciliation_drift_total += drift_count
            inc_position_sync_drift_total(drift_count)
            set_position_sync_current_drift(drift_count)
            self.logger.info(
                "📊 SYNC: Snapshot reconciliation applied to symbols: %s",
                sorted(changed_symbols),
            )
        else:
            set_position_sync_current_drift(0)

        if manual_closes:
            symbols = set(manual_closes.keys())
            self.logger.warning(
                f"⚠️  SYNC: Detected manually closed positions: {symbols}")
            self.manual_intervention_detected_total += len(symbols)
            for symbol, position_details in manual_closes.items():
                if self.alert_manager:
                    try:
                        self.alert_manager.check_manual_intervention(
                            symbol=symbol,
                            position_details=position_details,
                        )
                    except Exception as alert_err:
                        self.logger.warning(
                            f"Failed to send manual intervention alert for {symbol}: {alert_err}"
                        )

                self.logger.info(
                    f"🧹 SYNC: Removing {symbol} from internal state (closed manually)")

        # Calculate open positions notional (EXP-FIX: Portfolio Notional Hard Gate)
        open_positions_usd = self._calculate_open_positions_notional()
        # EXP-LEVERAGE-001: Calculate margin used with positionRisk data if available
        open_positions_margin_usd = self._calc_margin_used_usd(
            account_positions)
        # EXP-DIRECTION: Calculate margin by side for directional ratio checks
        margin_by_side = self._calculate_margin_by_side(account_positions)
        positions_last_ts_ms = int(time.time() * 1000)

        # Emit portfolio state updated event with real account data
        portfolio_payload = {
            "ts": int(time.time() * 1000),
            "equity": str(self._equity),  # Legacy field for compatibility
            # EXP-FIX: Always include equity_free_usdt
            "equity_free_usdt": str(self._equity),
            "realized_pnl": str(
                self._realized_pnl
            ),  # Preserve Decimal precision as string
            "unrealized_pnl": str(
                _d(payload.get("totalUnrealizedProfit", 0))
            ),  # Preserve Decimal precision as string
            "available_balance": str(
                _d(payload.get("maxWithdrawAmount", self._equity))
            ),  # Available margin for new positions
            "positions": self._get_positions_snapshot(),
            "open_positions_usd": str(
                open_positions_usd
            ),  # EXP-FIX: Notional for exposure gate
            "open_positions_margin_usd": str(
                open_positions_margin_usd
            ),  # EXP-LEVERAGE-001: Margin for exposure gate
            # EXP-DIRECTION: Per-side margin for directional checks
            "positions_by_side": {
                "long_margin": str(margin_by_side["long_margin"]),
                "short_margin": str(margin_by_side["short_margin"])
            },
            # EXP-FIX: Timestamp for staleness check
            "positions_last_ts_ms": positions_last_ts_ms,
        }

        # Add additional equity fields if USDT present in balance data (from account update)
        # Note: account updates may not include full asset list, so equity computation might be limited
        if "assets" in payload:
            equity_data = self._compute_equity_from_balance(
                payload["assets"], payload)
            if equity_data:
                portfolio_payload.update(
                    {
                        "equity_cross_usdt": equity_data["equity_cross_usdt"],
                        "equity_ts": equity_data["equity_ts"],
                    }
                )

        self.logger.info("Emitting EVT:PORTFOLIO_STATE_UPDATED...")
        self.fsm.emit(
            "EVT:PORTFOLIO_STATE_UPDATED",
            payload=portfolio_payload,
            why="Portfolio updated from Binance account data.",
        )

        self.logger.info(
            f"Updated portfolio from account: equity={self._equity}, positions={len(self._positions)}"
        )

    def _record_last_account_update_age(self) -> None:
        """Update observability gauge describing account snapshot freshness."""
        if self._last_account_update_ts_ms is None:
            return
        now_ms = int(time.time() * 1000)
        age_seconds = max(
            0.0, (now_ms - self._last_account_update_ts_ms) / 1000.0)
        update_position_sync_last_account_update_age(age_seconds)

    def on_balance_update(self, event: Message) -> None:
        """
        Handle incoming balance update event from Binance API.

        Args:
            event: FSM event with balance payload
        """
        self.logger.info("Handling EVT:BALANCE_UPDATE_RECEIVED...")
        payload = event.pld

        # Balance updates provide asset balances, but equity is tracked via account updates
        # We can use this for additional validation or logging
        assets = payload.get("assets", [])
        self.logger.info(
            f"Balance update received: {len(assets)} assets with balance > 0"
        )

        # Compute equity metrics for USDT-M futures
        equity_data = self._compute_equity_from_balance(assets)
        if not equity_data:
            self.logger.warning(
                "Skipping portfolio update: no USDT in balance data")
            return

        # Update internal equity state
        self._equity = decimal.Decimal(equity_data["equity_free_usdt"])

        # Calculate open positions notional (EXP-FIX: Portfolio Notional Hard Gate)
        open_positions_usd = self._calculate_open_positions_notional()
        # EXP-LEVERAGE-001: Calculate margin used (fallback to config leverage)
        open_positions_margin_usd = self._calc_margin_used_usd([])
        # EXP-DIRECTION: Calculate margin by side
        margin_by_side = self._calculate_margin_by_side([])
        positions_last_ts_ms = int(time.time() * 1000)

        # Emit portfolio state updated event with equity fields for DecisionMaking
        portfolio_payload = {
            "ts": int(time.time() * 1000),
            # Legacy field for compatibility
            "equity": equity_data["equity_free_usdt"],
            "equity_free_usdt": equity_data["equity_free_usdt"],
            "equity_cross_usdt": equity_data["equity_cross_usdt"],
            "equity_ts": equity_data["equity_ts"],
            "realized_pnl": str(
                self._realized_pnl
            ),  # Preserve Decimal precision as string
            "unrealized_pnl": "0",  # Not available in balance update
            "available_balance": equity_data["equity_free_usdt"],
            "positions": self._get_positions_snapshot(),
            "open_positions_usd": str(
                open_positions_usd
            ),  # EXP-FIX: Notional for exposure gate
            "open_positions_margin_usd": str(
                open_positions_margin_usd
            ),  # EXP-LEVERAGE-001: Margin for exposure gate
            # EXP-DIRECTION: Per-side margin for directional checks
            "positions_by_side": {
                "long_margin": str(margin_by_side["long_margin"]),
                "short_margin": str(margin_by_side["short_margin"])
            },
            # EXP-FIX: Timestamp for staleness check
            "positions_last_ts_ms": positions_last_ts_ms,
        }

        self.logger.info(
            "✅ Emitting EVT:PORTFOLIO_STATE_UPDATED from balance update..."
        )
        self.fsm.emit(
            "EVT:PORTFOLIO_STATE_UPDATED",
            payload=portfolio_payload,
            why=equity_data["why"],
        )

    def _compute_equity_from_balance(
        self,
        assets: List[Dict[str, Any]],
        account_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Compute equity metrics for USDT-M futures account.

        Args:
            assets: List of asset balances from BALANCE_UPDATE
            account_data: Optional account data from ACCOUNT_UPDATE

        Returns:
            Dict with equity_free_usdt, equity_cross_usdt, equity_ts, why or None if USDT not present
        """
        # Find USDT asset
        usdt_asset = next(
            (a for a in assets if a.get("asset") == "USDT"), None)
        if not usdt_asset:
            self.logger.warning(
                "Skipping equity computation: USDT not present in balance data"
            )
            return None

        # Compute free equity (available for new positions)
        equity_free_usdt = _d(usdt_asset.get("balance", "0"))

        # Compute cross equity (total wallet balance including unrealized P&L)
        if account_data:
            # From ACCOUNT_UPDATE: use totalCrossWalletBalance + totalUnrealizedProfit
            equity_cross_usdt = _d(
                account_data.get("totalCrossWalletBalance", "0")
            ) + _d(account_data.get("totalUnrealizedProfit", "0"))
            equity_ts = account_data.get("updateTime", int(time.time() * 1000))
            why = "equity_from_account_update"
        else:
            # From BALANCE_UPDATE: use crossWalletBalance + crossUnPnl
            equity_cross_usdt = _d(usdt_asset.get("crossWalletBalance", "0")) + _d(
                usdt_asset.get("crossUnPnl", "0")
            )
            equity_ts = usdt_asset.get("updateTime", int(time.time() * 1000))
            why = "equity_from_balance_update"

        return {
            "equity_free_usdt": str(equity_free_usdt),
            "equity_cross_usdt": str(equity_cross_usdt),
            "equity_ts": equity_ts,
            "why": why,
        }

    def _update_position(
        self,
        symbol: str,
        quantity: decimal.Decimal,
        price: decimal.Decimal,
        fees: decimal.Decimal,
        venue: str,
    ) -> None:
        """
        Update position for a symbol and calculate realized P&L.

        Based on aurora/positions/ logic adapted for FSM events.
        """
        with self._lock:
            existing = self._positions.get(symbol) or {}
            pos_qty = _d(existing.get("quantity", decimal.Decimal("0")))
            avg_px = _d(existing.get("avg_price", decimal.Decimal("0")))

            # Determine position sign based on existing position (+1 long, -1 short)
            pos_sign = (
                decimal.Decimal("1")
                if pos_qty > decimal.Decimal("0")
                else decimal.Decimal("-1")
                if pos_qty < decimal.Decimal("0")
                else decimal.Decimal("0")
            )

            # Realized PnL accrues only when trade reduces/offsets existing position
            realized_delta = decimal.Decimal("0")
            if pos_sign != decimal.Decimal("0") and quantity * pos_qty < decimal.Decimal(
                "0"
            ):
                closed_qty = min(abs(pos_qty), abs(quantity))
                # sign * qty_closed * (fill_px - avg_entry_px) - fees
                realized_delta = pos_sign * \
                    closed_qty * (price - avg_px) - fees

            # Update realized P&L
            self._realized_pnl += realized_delta

            # Update position quantity and average entry price
            new_qty = pos_qty + quantity
            if abs(new_qty) < decimal.Decimal("1e-12"):
                # Flat position resets avg price
                new_avg = decimal.Decimal("0")
                venues = [venue]
            else:
                # Weighted average for same-side accumulation; if crossing through zero,
                # the new avg becomes current trade price for the residual side.
                if pos_qty == decimal.Decimal("0") or (
                    pos_qty * quantity > decimal.Decimal("0")
                ):
                    # Same-side accumulation: recompute weighted average
                    new_avg = (pos_qty * avg_px + quantity * price) / new_qty
                else:
                    # Opposite-side trade
                    if abs(quantity) < abs(pos_qty):
                        # Partial close: keep prior average for remaining open qty
                        new_avg = avg_px
                    elif abs(quantity) == abs(pos_qty):
                        # Fully closed handled by flat branch above, but keep consistency
                        new_avg = decimal.Decimal("0")
                    else:
                        # Crossed through zero (flip): new position avg is current fill price
                        new_avg = price

                # Update venues list
                existing_venues = existing.get("venues", [])
                venues = list(set(existing_venues + [venue]))

            # Update position
            self._positions[symbol] = {
                "quantity": new_qty,
                "avg_price": new_avg,
                "venues": venues,
            }

    def _calculate_unrealized_pnl(self) -> decimal.Decimal:
        """
        Calculate total unrealized P&L for all positions.

        Note: This is a simplified calculation since we don't have current market prices
        in the position tracking domain. In production, this should be calculated using
        current mark prices from market data.

        Returns:
            decimal.Decimal: Total unrealized P&L
        """
        # For now, return 0 since we don't have current market prices
        # In production, this would be: sum((current_price - avg_entry_price) * quantity for each position)
        return decimal.Decimal("0")

    def _calculate_open_positions_notional(self) -> decimal.Decimal:
        """
        Calculate total notional value of open positions in USD.

        EXP-FIX: Used by exposure gate to ensure portfolio positions are accounted for.
        Returns sum of abs(positionAmt) * markPrice for all positions.
        """
        total_notional = decimal.Decimal("0")

        # For now, use entry price as approximation since we don't have mark prices
        # In production, this should use current mark prices from market data
        for symbol, position in self._positions.items():
            quantity = abs(position["quantity"])
            entry_price = position["avg_price"]

            if quantity > decimal.Decimal("1e-9") and entry_price > decimal.Decimal(
                "0"
            ):
                position_notional = quantity * entry_price
                total_notional += position_notional
                self.logger.debug(
                    f"Position notional for {symbol}: {position_notional} USD"
                )

        # Round to 2 decimal places for consistency
        return total_notional.quantize(decimal.Decimal("0.01"))

    def _calc_margin_used_usd(self, positions: list[dict]) -> decimal.Decimal:
        """
        Calculate total margin used by open positions in USD.

        EXP-LEVERAGE-001: Margin-based exposure calculation with leverage.
        If positions list is provided (from positionRisk API), use it.
        Otherwise, fallback to internal position data with leverage from config.
        """
        total_margin = decimal.Decimal("0")

        if positions:
            # Use positionRisk data if available
            self.logger.info(
                f"💚 _calc_margin_used_usd() USING API: {len(positions)} positions from /fapi/v2/positionRisk")
            for p in positions:
                # Extract notional: try positionRisk fields first, fallback to calculation
                notional = _d(p.get("notional") or (
                    _d(p.get("positionAmt", "0")) *
                    _d(p.get("markPrice") or p.get("entryPrice") or "0")
                ))

                # Extract leverage: try positionRisk field, fallback to default
                lev = _d(p.get("leverage") or "1")
                if lev <= 0:
                    lev = decimal.Decimal("1")

                # Calculate margin for this position
                margin = abs(notional) / lev
                total_margin += margin

                self.logger.debug(
                    f"Position margin for {p.get('symbol', 'unknown')}: notional={notional}, lev={lev}, margin={margin}"
                )
        else:
            # Fallback to internal position data with leverage from config
            self.logger.warning(
                f"🔴 _calc_margin_used_usd() FALLBACK MODE: API returned empty, using {len(self._positions)} internal positions from self._positions")
            self.logger.warning(
                f"   Internal positions: {list(self._positions.keys())}")
            leverage_defaults = self._exposure_policy.leverage_defaults
            default_leverage = leverage_defaults.default

            for symbol, position in self._positions.items():
                quantity = abs(position["quantity"])
                entry_price = position["avg_price"]

                if quantity > decimal.Decimal("1e-9") and entry_price > decimal.Decimal("0"):
                    # Calculate notional
                    position_notional = quantity * entry_price

                    symbol_leverage = leverage_defaults.resolve_for(symbol)
                    if symbol_leverage <= 0:
                        symbol_leverage = decimal.Decimal("1")

                    # Calculate margin
                    margin = position_notional / symbol_leverage
                    total_margin += margin

                    self.logger.debug(
                        f"Position margin for {symbol}: notional={position_notional}, lev={symbol_leverage}, margin={margin}"
                    )

        # Round to 2 decimal places for consistency
        self.logger.info(
            f"📊 _calc_margin_used_usd() TOTAL: {total_margin.quantize(decimal.Decimal('0.01'))} USD (API={len(positions) if positions else 'FALLBACK'})")
        return total_margin.quantize(decimal.Decimal("0.01"))

    def _calculate_margin_by_side(self, positions: list[dict]) -> dict:
        """
        Calculate margin used by long and short positions separately.

        EXP-DIRECTION: Per-side margin calculation for directional ratio checks.

        Returns:
            Dict with 'long_margin' and 'short_margin' keys (as Decimal).
        """
        long_margin = decimal.Decimal("0")
        short_margin = decimal.Decimal("0")

        if positions:
            # Use positionRisk data if available
            for p in positions:
                # Extract notional
                notional = _d(p.get("notional") or (
                    _d(p.get("positionAmt", "0")) *
                    _d(p.get("markPrice") or p.get("entryPrice") or "0")
                ))

                # Extract leverage
                lev = _d(p.get("leverage") or "1")
                if lev <= 0:
                    lev = decimal.Decimal("1")

                # Calculate margin for this position
                margin = abs(notional) / lev

                # Determine side from positionAmt sign
                amount = _d(p.get("positionAmt", "0"))
                if amount > 0:
                    long_margin += margin
                elif amount < 0:
                    short_margin += margin
        else:
            # Fallback to internal position data
            leverage_defaults = self._exposure_policy.leverage_defaults
            default_leverage = leverage_defaults.default

            for symbol, position in self._positions.items():
                quantity = position["quantity"]
                entry_price = position["avg_price"]

                if abs(quantity) > decimal.Decimal("1e-9") and entry_price > decimal.Decimal("0"):
                    # Calculate notional
                    position_notional = abs(quantity) * entry_price

                    symbol_leverage = leverage_defaults.resolve_for(symbol)
                    if symbol_leverage <= 0:
                        symbol_leverage = decimal.Decimal("1")

                    # Calculate margin
                    margin = position_notional / symbol_leverage

                    # Determine side
                    if quantity > 0:
                        long_margin += margin
                    else:
                        short_margin += margin

        return {
            "long_margin": long_margin.quantize(decimal.Decimal("0.01")),
            "short_margin": short_margin.quantize(decimal.Decimal("0.01"))
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Get position tracking metrics for monitoring."""
        return {
            "manual_intervention_detected_total": self.manual_intervention_detected_total,
            "positions_tracked": len(self._positions),
            "equity_usd": float(self._equity),
            "realized_pnl_usd": float(self._realized_pnl)
        }

    def _get_positions_snapshot(self) -> List[Dict[str, Any]]:
        """
        Get current positions snapshot in the format expected by portfolio_state_v1.json.
        """
        positions = []
        for symbol, position in self._positions.items():
            if abs(position["quantity"]) > decimal.Decimal(
                "1e-9"
            ):  # Only include non-zero positions
                positions.append(
                    {
                        "symbol": symbol,
                        "net_position": str(
                            position["quantity"]
                        ),  # Preserve Decimal precision as string
                        "avg_entry_price": str(
                            position["avg_price"]
                        ),  # Preserve Decimal precision as string
                        "venues": position["venues"],
                    }
                )
        return positions

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        """Public API: Return current tracked positions as a mapping symbol -> position dict.

        This is used by DR hydration and other components expecting symbol-keyed maps.
        """
        # Return a shallow copy to avoid outside mutation of internal state
        return {s: v.copy() for s, v in self._positions.items()}

    def register_snapshot_fetcher(
        self,
        fetcher: Callable[[Optional[str], str, Optional[str]], Dict[str, Any]],
    ) -> None:
        """Register callable able to produce & emit a fresh account snapshot."""
        self._snapshot_fetcher = fetcher

    def force_full_resync(
        self,
        *,
        reason: str,
        symbol: Optional[str] = None,
        rid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Trigger a manual resync via the registered snapshot fetcher."""
        if not self._snapshot_fetcher:
            raise RuntimeError(
                "Snapshot fetcher not registered for PositionTracking")

        normalized_reason = reason or "manual_resync"
        inc_position_sync_resync_total(normalized_reason)

        try:
            summary = self._snapshot_fetcher(
                symbol,
                normalized_reason,
                rid,
            )
        except Exception as exc:
            self.logger.error(
                "force_full_resync failed (reason=%s, symbol=%s): %s",
                normalized_reason,
                symbol,
                exc,
                exc_info=True,
            )
            return {
                "status": "error",
                "reason": normalized_reason,
                "symbol": symbol,
                "error": str(exc),
            }

        summary.setdefault("status", "ok")
        summary.setdefault("symbol", symbol)
        summary["reason"] = normalized_reason
        return summary

    def on_force_resync_command(self, event: Message) -> None:
        """Handle CMD:POSITION_FORCE_RESYNC events."""
        payload = event.pld or {}
        symbol = payload.get("symbol")
        reason = payload.get("reason") or event.why or "manual_resync"
        rid_override = payload.get("rid") or payload.get("rid_override")
        rid = rid_override or event.rid

        try:
            summary = self.force_full_resync(
                reason=reason,
                symbol=symbol,
                rid=rid,
            )
        except RuntimeError as exc:
            self.logger.error("force_resync command failed: %s", exc)
            summary = {
                "status": "error",
                "reason": reason,
                "symbol": symbol,
                "error": str(exc),
            }

        completion_payload = {
            "symbol": symbol,
            "reason": reason,
            "status": summary.get("status", "unknown"),
            "details": summary,
        }
        self.fsm.emit(
            "EVT:POSITION_FORCE_RESYNC_COMPLETED",
            payload=completion_payload,
            why="position_force_resync_completed",
        )

    def get_snapshot(self) -> dict:
        """
        Serializes the current state of the position_tracking domain for DR purposes.

        Returns a snapshot compliant with snapshot_v1.schema.json for disaster recovery.
        All numeric values are preserved as Decimal-encoded strings to maintain precision.

        Returns:
            dict: DR snapshot with domain state, hash, and metadata
        """
        # Build positions dictionary with Decimal precision preservation
        positions_state = {}
        for symbol, position in self._positions.items():
            if abs(position["quantity"]) > decimal.Decimal(
                "1e-9"
            ):  # Only include non-zero positions
                qty = position["quantity"]
                positions_state[symbol] = {
                    "qty": str(qty),
                    "avg_price": str(position["avg_price"]),
                    "side": "long" if qty > 0 else "short",
                    "unrealized_pnl": "0.0",  # Placeholder - would need current market price
                }

        # Build portfolio state with precision preservation
        portfolio_state = {
            "equity": str(self._equity),
            # Simplified calculation
            "balance": str(self._equity - self._realized_pnl),
            "margin_used": "0.0",  # Placeholder - would need real margin calculation
        }

        # Complete state object
        state_data = {"positions": positions_state,
                      "portfolio": portfolio_state}
        # Compute state hash for integrity verification
        state_str = json.dumps(state_data, sort_keys=True)
        state_hash = hashlib.sha256(state_str.encode("utf-8")).hexdigest()

        # Build snapshot with metadata
        try:
            if hasattr(self.config, 'system') and self.config.system:
                worker_id = self.config.system.worker_id if hasattr(
                    self.config.system, 'worker_id') else "unknown"
            elif isinstance(self.config, dict):
                worker_id = self.config.get(
                    "system", {}).get("worker_id", "unknown")
            else:
                worker_id = "unknown"
        except (AttributeError, TypeError):
            worker_id = "unknown"

        snapshot = {
            "domain": "position_tracking",
            "version": "1.0.0",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "state_hash": f"sha256:{state_hash}",
            "state": state_data,
            "metadata": {
                "worker_id": worker_id,
                "positions_count": len(positions_state),
                "sequence_number": int(
                    time.time() * 1000
                ),  # Use timestamp as sequence for now
            },
        }

        self.logger.info(
            f"DR Snapshot created: {len(positions_state)} positions, "
            f"equity={self._equity}, hash={state_hash[:16]}..."
        )

        return snapshot

    def load_snapshot(self, snapshot_data: dict) -> bool:
        """
        Loads the domain's state from a snapshot dictionary.

        Verifies integrity using the provided state_hash and restores positions
        and portfolio values. Numeric strings are converted back to Decimal to
        preserve precision.

        Args:
            snapshot_data: Snapshot dictionary produced by `get_snapshot()`.

        Returns:
            bool: True if load succeeded, False otherwise.
        """
        try:
            state_to_load = snapshot_data["state"]
            state_hash_field = snapshot_data.get("state_hash", "")
            expected_hash = (
                state_hash_field.split(":")[-1] if state_hash_field else None
            )

            # Verify integrity
            state_str = json.dumps(state_to_load, sort_keys=True)
            actual_hash = hashlib.sha256(state_str.encode("utf-8")).hexdigest()

            if expected_hash and actual_hash != expected_hash:
                self.logger.error(
                    f"Snapshot integrity check failed! Expected hash {expected_hash}, got {actual_hash}."
                )
                return False

            # Restore positions (convert strings back to Decimal)
            positions_loaded: Dict[str, Dict[str, Any]] = {}
            for symbol, pos in state_to_load.get("positions", {}).items():
                try:
                    qty = decimal.Decimal(str(pos.get("qty", "0")))
                    avg_price = decimal.Decimal(str(pos.get("avg_price", "0")))
                except (ValueError, TypeError, decimal.InvalidOperation) as e:
                    self.logger.error(
                        f"Invalid numeric in snapshot for {symbol}: {e}")
                    return False

                positions_loaded[symbol] = {
                    "quantity": qty,
                    "avg_price": avg_price,
                    "venues": pos.get("venues", []),
                }

            # Restore portfolio/equity if present
            portfolio = state_to_load.get("portfolio", {})
            equity_str = portfolio.get("equity")
            balance_str = portfolio.get("balance")

            if equity_str is not None:
                try:
                    self._equity = decimal.Decimal(str(equity_str))
                except (ValueError, TypeError, decimal.InvalidOperation):
                    self.logger.error("Invalid equity value in snapshot")
                    return False

            # Try to reconstruct realized pnl if balance provided: realized = equity - balance
            if balance_str is not None:
                try:
                    balance_dec = decimal.Decimal(str(balance_str))
                    # realized_pnl = equity - balance
                    self._realized_pnl = self._equity - balance_dec
                except (ValueError, TypeError, decimal.InvalidOperation):
                    self.logger.warning(
                        "Invalid balance value in snapshot; leaving realized_pnl unchanged"
                    )

            # Apply restored positions
            self._positions = positions_loaded

            self.logger.info(
                f"Successfully loaded state from snapshot created at {snapshot_data.get('timestamp_utc', 'unknown')}. "
                f"Restored {len(self._positions)} positions."
            )

            return True

        except KeyError as e:
            self.logger.critical(
                f"Failed to load snapshot due to missing key: {e}")
            return False
        except (TypeError, json.JSONDecodeError) as e:
            self.logger.critical(
                f"Failed to load snapshot due to invalid format: {e}")
            return False

    def stop(self) -> None:
        """Stop the position tracking component."""
        self.logger.info("PositionTracking stopped")
