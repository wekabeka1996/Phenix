"""
Shadow ExecPos Runtime V2
=========================

The main entry point and orchestrator for the modular Execution Position domain.
This class composes all the sub-services into a coherent runtime.
"""
from typing import Any, Dict, Optional, List, Callable, Awaitable
import asyncio
import logging
import time
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor

from apps.reference.domains.execution_position.config import ExecutionPositionConfig, SnapshotConfig
from apps.reference.config.execution_position import (
    compute_sl_tp_from_roi,
    resolve_effective_leverage,
)
from .async_manager import ExecPosAsyncManager
from .execution_service import ExecutionService
from .watchdog import AggOcoWatchdogService
from .gatekeeper import ExecPosGatekeeper
from .idempotency import FillIdempotency
from .wal_writer import ExecPosWALWriter
from .exposure_bridge import ExposureBridge
from .types import RuntimeEvent, ExecutionCommand, WatchdogAction
from . import logging_v2
from .position_model import PositionState, apply_fill, POSITION_ZERO_TOLERANCE
from dataclasses import replace, dataclass
from .close_flow import CloseFlowService, CloseContext, CloseConfig

# Phase 11: Import view types and cleanup from contract layer (no BracketService)
from ..aggregator_oco.view_types import (
    PositionView as BracketPositionView,
    OrderView as BracketOrderView,
    BracketRulesConfig,
    make_bracket_client_order_id,
)
from ..aggregator_oco.contracts import BracketPlan, BracketConfig
from ..aggregator_oco.cleanup import plan_orphan_cleanup, plan_reverse_cleanup, plan_position_size_cleanup

from ..aggregator_oco.engine import compute_bracket_plan_from_views
from .converters import normalize_orders
from .executor_pool import ExecutorPoolV2
from vfoundation.apps.reference.domains.execution_position import bracket_aggregator
from apps.reference.domains.execution_position.infra.order_index import OrderIndex

# Import WAL infrastructure
from vfoundation.dr import wal

logger = logging.getLogger(__name__)


# =============================================================================
# LEGACY COMPATIBILITY WRAPPER (for tests using _open_orders_by_symbol)
# =============================================================================
class _LegacyOrdersWrapper:
    """
    Dict-like interface wrapping OrderIndex for backward compatibility.

    Maps: symbol → List[Dict] of orders (legacy format)
    Delegates to order_index internally.

    DEPRECATED: New code should use order_index directly.
    """

    def __init__(self, order_index: OrderIndex):
        self._oi = order_index

    def _refs_to_dicts(self, refs) -> List[Dict[str, Any]]:
        """Convert OrderRef list to legacy dict format."""
        return [{"clientOrderId": r.clientOrderId, "orderId": r.exchangeOrderId,
                 "symbol": r.symbol, "side": r.side, "type": r.order_type,
                 "status": r.status, "origQty": str(r.quantity) if r.quantity else None,
                 "stopPrice": str(r.stop_price) if r.stop_price else None,
                 "reduceOnly": r.reduce_only} for r in refs]

    def __getitem__(self, symbol: str) -> List[Dict[str, Any]]:
        refs = self._oi.get_by_symbol(symbol)
        return self._refs_to_dicts(refs)

    def __setitem__(self, symbol: str, orders: List[Dict[str, Any]]) -> None:
        # Legacy tests set orders directly - sync to OrderIndex
        self._oi.reconcile_snapshot(symbol, orders)

    def get(self, symbol: str, default: Any = None) -> Any:
        refs = self._oi.get_by_symbol(symbol)
        if not refs:
            return default if default is not None else []
        return self._refs_to_dicts(refs)


@dataclass
class BracketStatus:
    """Per-symbol state to prevent double-apply of guard_loop vs trade_executed."""
    last_reason: str = ""  # "trade_executed", "guard_loop", etc.
    last_started_ts: float = 0.0  # When _apply_bracket_plan started
    in_flight: bool = False  # True during _apply_bracket_plan execution
    # True after plan applied, False after snapshot confirms orders
    awaiting_snapshot: bool = False


@dataclass
class BracketEvalContext:
    """Context for bracket evaluation."""
    symbol: str
    position: PositionState
    cfg: BracketRulesConfig
    reason: str


class ExecPosRuntimeV2:
    """
    The modular runtime for Execution Position management.

    This class replaces the monolithic `ExecPosFSM`.
    It is responsible for:
    - Wiring together dependencies.
    - Routing events to appropriate handlers.
    - Managing the lifecycle of the domain (start, stop, hydrate).
    """

    # Configuration Constants (fallback defaults)
    STALE_RECOVERY_INTERVAL_SEC = 10.0
    WATCHDOG_LOG_THROTTLE_SEC = 30.0
    # RC-1 FIX: Increased throttle to prevent bracket churn
    # Previous value 2.0 was too aggressive, causing CANCEL→PLACE cycles
    BRACKET_THROTTLE_SEC = 10.0  # Cooldown between bracket evaluations per symbol
    BRACKET_SUPPRESSION_SEC = 10.0  # was 30.0 - faster default for scalping
    SNAPSHOT_REQUEST_INTERVAL_SEC = 5.0
    GUARD_LOOP_INTERVAL_SEC = 1.0
    GUARD_RECOVERY_INTERVAL_SEC = 5.0
    POSITION_POLLING_INTERVAL_SEC = 2.0  # Poll positions every 2 seconds
    ORDER_INDEX_PERSISTENCE_FILE = "data/order_index_persistence.json"

    def __init__(
        self,
        config: Dict[str, Any],
        adapter: Any,
        price_service: Any,
        emit_fn: Optional[Any] = None,
        clock: Optional[Any] = None,  # EP-RUNTIME-CONCURRENCY-SAFETY-S1
        guardian: Optional[Any] = None,
        ep_config: Optional[ExecutionPositionConfig] = None,
    ):
        self.config = config
        self.clock = clock  # For deterministic testing
        self._ep_cfg: Optional[ExecutionPositionConfig] = ep_config

        # Core Infrastructure
        self.async_manager = ExecPosAsyncManager()

        # Services
        self.execution_service = ExecutionService(adapter)
        self.gatekeeper = ExecPosGatekeeper(config)
        self.close_flow_service = CloseFlowService()
        # Phase 11: BracketService REMOVED — cleanup via aggregator_oco.cleanup module
        self.bracket_service = None  # DEPRECATED: kept for test compatibility
        self.guardian = guardian

        # ═══════════════════════════════════════════════════════════════════
        # EXECUTOR POOL V2: Pure execution layer, NO bracket decision logic
        # Phase 11: Bracket planning via aggregator_oco.engine (core planner)
        # ═══════════════════════════════════════════════════════════════════
        fill_timeout = config.get("execution_position", {}).get(
            "fill_timeout_sec", 60.0)

        # ExecutorPoolV2: Per-symbol parallel execution (production path)
        # CRITICAL: No sl_pct/tp_rr - brackets handled by core planner only
        self.executor_pool = ExecutorPoolV2(
            adapter=adapter,
            gatekeeper=self.gatekeeper,
            fill_timeout_sec=fill_timeout,
            # Allow slightly higher local rate to reduce drops (testnet-safe)
            max_orders_per_second=12,
        )

        # ExecutorPool is enabled by default (production path)
        # Can be disabled for testing via config from either location
        exec_domain_cfg = config.get("execution", {}).get("executor_pool", {})
        ep_cfg = config.get("execution_position", {})

        # Both config paths must allow ExecutorPool (use AND for fail-safe disable)
        # If either explicitly sets enabled=False, ExecutorPool is disabled
        exec_enabled = exec_domain_cfg.get("enabled", True)
        ep_enabled = ep_cfg.get("executor_pool_enabled", True)
        self._use_executor_pool = exec_enabled and ep_enabled
        # TEMP: ENABLE executor_pool for testing
        # self._use_executor_pool = False

        logger.info(
            f"[ExecPosV2] ExecutorPoolV2 {'ENABLED' if self._use_executor_pool else 'DISABLED'}: "
            f"per-symbol parallel execution, fill_timeout={fill_timeout}s, "
            f"BracketService=SINGLE_SOURCE_OF_TRUTH"
        )

        # Dedicated thread pool for ExecutorPool per-symbol execution
        # max_workers=8 allows parallel execution for up to 8 symbols simultaneously
        self._executor_thread_pool = ThreadPoolExecutor(
            max_workers=8, thread_name_prefix="exec_pool")

        # State & Logic
        self.fill_idempotency = FillIdempotency()

        # Watchdogs
        self.watchdog = AggOcoWatchdogService()

        # WAL & Exposure (EP-RUNTIME-WAL-EXPOSURE-S1)
        self.wal_writer = ExecPosWALWriter(wal_append_fn=wal.append)
        self.exposure_bridge = ExposureBridge(
            emit_fn=emit_fn or self._default_emit)

        # Runtime state
        self._positions_by_symbol: Dict[str, PositionState] = {}
        # R2-B: Track previous side for reverse detection
        self._prev_positions_by_symbol: Dict[str, PositionState] = {}

        # Order Index (replaces _open_orders_by_symbol)
        self.order_index = OrderIndex()

        # Load persisted order index state
        persistence_file = self.ORDER_INDEX_PERSISTENCE_FILE
        loaded_count = self.order_index.load_from_file(persistence_file)
        if loaded_count > 0:
            logger.info(
                f"[ExecPosV2] Loaded {loaded_count} persisted orders from {persistence_file}")

        # DEPRECATED: Legacy compatibility wrapper for tests
        # Returns OrderIndex-backed dict-like interface for symbol → orders list
        self._open_orders_by_symbol = _LegacyOrdersWrapper(self.order_index)

        # "UNKNOWN" | "STALE" | "FRESH"
        self._orders_snapshot_state: Dict[str, str] = {}
        self._recovery_completed = False
        self._last_orders_snapshot_ts: Dict[str, float] = {}
        self._last_position_snapshot_ts: Dict[str, float] = {}
        self._brackets_suppressed: Dict[str, float] = {}
        self._snapshot_request_hook: Optional[Callable[[
            str], Awaitable[None]]] = None
        self._position_snapshot_hook: Optional[Callable[[
        ], Awaitable[None]]] = None

        # =================================================================
        # TIMEOUT RESILIENCE STATE
        # =================================================================
        # Tracks whether the last API call for a symbol failed due to timeout.
        # When True, new trades/decisions are blocked until successful resync.
        # This prevents "blind trading" when we don't know the exchange state.
        self._open_orders_stale: Dict[str, bool] = {}
        # Timestamp when stale mode was entered (for logging/metrics)
        self._stale_entered_ts: Dict[str, float] = {}
        # Recovery task to periodically attempt resync
        self._stale_recovery_task: Optional[asyncio.Task] = None
        self._stale_recovery_interval_sec = self.STALE_RECOVERY_INTERVAL_SEC

        # R3-D1: Per-symbol bracket status to prevent double-apply
        self._bracket_status: Dict[str, BracketStatus] = {}

        # LEVERAGE-FIX: Cache leverage from Binance API per symbol for accurate ROI calculation
        # Key: symbol -> leverage (int). Updated from ACCOUNT_UPDATE/position snapshot.
        self._leverage_by_symbol: Dict[str, int] = {}

        # E-004: Watchdog log throttling to prevent spam
        # Key: (symbol, kind) -> last_log_ts
        self._watchdog_log_throttle: Dict[tuple, float] = {}
        # Don't log same violation twice within 30s
        self._watchdog_log_throttle_sec = self.WATCHDOG_LOG_THROTTLE_SEC

        # TASK 3: Throttling state for bracket spam prevention
        self._last_brackets_apply_ts: Dict[str, float] = {}
        # Minimum seconds between bracket evaluations per symbol (from config or default)
        if ep_config and hasattr(ep_config, 'aggregated_oco'):
            self._bracket_throttle_sec = ep_config.aggregated_oco.bracket_throttle_sec
            self._bracket_suppression_sec = ep_config.aggregated_oco.bracket_suppression_sec
        else:
            self._bracket_throttle_sec = self.BRACKET_THROTTLE_SEC
            self._bracket_suppression_sec = self.BRACKET_SUPPRESSION_SEC
        self._snapshot_request_interval_sec = self.SNAPSHOT_REQUEST_INTERVAL_SEC

        # Guard loop state
        self._guard_loop_interval_sec = self.GUARD_LOOP_INTERVAL_SEC
        self._guard_recovery_interval_sec = self.GUARD_RECOVERY_INTERVAL_SEC
        self._guard_loop_running = False
        self._guard_loop_task: Optional[asyncio.Task] = None
        self._last_guard_recovery_ts: Dict[str, float] = {}
        self._last_snapshot_request_ts: Dict[str, float] = {}

        # Position polling state
        self._position_polling_interval_sec = self.POSITION_POLLING_INTERVAL_SEC
        self._position_polling_running = False
        self._position_polling_task: Optional[asyncio.Task] = None
        self._last_position_poll_ts: float = 0.0

        # Concurrency control - per-symbol locks for parallel execution
        # NOTE: Locks are created lazily in _get_symbol_lock() to bind to the correct event loop
        self._symbol_locks: Dict[str, asyncio.Lock] = {}
        self._symbol_locks_loop: Optional[asyncio.AbstractEventLoop] = None
        # Keep global lock only for non-symbol operations (snapshot-all, etc)
        self._global_lock: Optional[asyncio.Lock] = None
        self._global_lock_loop: Optional[asyncio.AbstractEventLoop] = None

        # Metrics
        self._metrics = {
            "events_total": 0,
            "events_by_kind": {},
            "gatekeeper_allowed": 0,
            "gatekeeper_rejected": 0,
            "execution_success": 0,
            "execution_failed": 0,
            "fills_processed": 0,
            "fills_duplicate": 0,
            # R2-G: Total fills seen (including zero/duplicate)
            "fills_total": 0,
            # R2-G: Fills where qty was normalized from negative
            "fills_abs_normalized_total": 0,
            # R2-G: Fills with zero qty (ignored)
            "fills_zero_ignored_total": 0,
            "fills_signed_qty_seen_total": 0,  # R2-G: Fills with negative raw qty
            "watchdog_violations": 0,
            "watchdog_violations_by_kind": {},
            "wal_trades_written": 0,
            "wal_positions_written": 0,
            "exposure_updates_emitted": 0,
            "brackets_evaluated": 0,
            "brackets_alerts": 0,
            "brackets_throttled": 0,
            # TIMEOUT RESILIENCE metrics
            "stale_mode_entered": 0,
            "stale_mode_exited": 0,
            "stale_mode_blocked_intents": 0,
            "stale_recovery_attempts": 0,
            "stale_recovery_success": 0,
        }

    def set_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Set the event loop for async operations.

        Propagates to async_manager for general async operations.
        """
        self.async_manager.set_async_loop(loop)
        logger.debug(f"[ExecPosV2] Event loop set: {id(loop)}")

    def hydrate(self, snapshot: Dict[str, Any]) -> None:
        """Restore state from a snapshot (WAL or DB)."""
        if "positions" in snapshot:
            for pos in snapshot["positions"]:
                symbol = pos.get("symbol")
                if symbol:
                    self._positions_by_symbol[symbol] = PositionState(
                        symbol=symbol,
                        qty=float(pos.get("qty", 0.0)),
                        avg_entry_price=float(
                            pos.get("avg_entry_price") or pos.get("entry_price") or 0.0),
                        realized_pnl=float(pos.get("realized_pnl", 0.0)),
                        unrealized_pnl=float(pos.get("unrealized_pnl", 0.0)),
                        open_time=pos.get("open_time"),
                        last_update_time=pos.get("last_update_time"),
                        scale_in_count=int(pos.get("scale_in_count", 0)),
                        scale_out_count=int(pos.get("scale_out_count", 0)),
                    )

        if "orders" in snapshot:
            # Group by symbol for reconciliation
            orders_by_symbol = {}
            for order in snapshot["orders"]:
                sym = order.get("symbol")
                if sym:
                    orders_by_symbol.setdefault(sym, []).append(order)

            for sym, orders in orders_by_symbol.items():
                self.order_index.reconcile_snapshot(sym, orders)

    def get_metrics_snapshot(self) -> Dict[str, Any]:
        """Get a complete snapshot of V2 runtime metrics."""
        return self.get_metrics()

    def _get_symbol_lock(self, symbol: str) -> asyncio.Lock:
        """
        Get or create per-symbol lock bound to current event loop.

        This enables parallel processing of different symbols while
        serializing operations within the same symbol.
        If the loop changes, we recreate all locks to avoid RuntimeError.
        """
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop - create lock anyway, will be recreated when loop starts
            if symbol not in self._symbol_locks:
                self._symbol_locks[symbol] = asyncio.Lock()
            return self._symbol_locks[symbol]

        # Check if locks need to be recreated for current loop
        if self._symbol_locks_loop is not current_loop:
            self._symbol_locks = {}
            self._symbol_locks_loop = current_loop
            logger.debug(
                f"[ExecPosV2] Cleared _symbol_locks for new loop {id(current_loop)}")

        # Create lock for symbol if needed
        if symbol not in self._symbol_locks:
            self._symbol_locks[symbol] = asyncio.Lock()
            logger.debug(
                f"[ExecPosV2] Created _symbol_lock for {symbol} in loop {id(current_loop)}")

        return self._symbol_locks[symbol]

    def _get_global_lock(self) -> asyncio.Lock:
        """
        Get or create global lock for non-symbol operations.

        Use sparingly - only for operations that affect all symbols
        (e.g., full snapshot processing).
        """
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            if self._global_lock is None:
                self._global_lock = asyncio.Lock()
            return self._global_lock

        if self._global_lock is None or self._global_lock_loop is not current_loop:
            self._global_lock = asyncio.Lock()
            self._global_lock_loop = current_loop
            logger.debug(
                f"[ExecPosV2] Created new _global_lock for loop {id(current_loop)}")

        return self._global_lock

    def _get_evaluation_lock(self) -> asyncio.Lock:
        """
        DEPRECATED: Use _get_symbol_lock(symbol) for per-symbol operations.
        Kept for backward compatibility, returns global lock.
        """
        return self._get_global_lock()

    async def start(self) -> None:
        """
        Start the runtime.
        """
        logger.info("Starting ExecPosRuntimeV2...")

        # Ensure evaluation lock is bound to current event loop
        self._get_evaluation_lock()

        # Phase 1: Force initial orders snapshot sync with exchange
        await self._force_initial_orders_sync()

        # Phase 2: Load Algo Orders Snapshot
        if hasattr(self.execution_service.adapter, "load_open_algo_orders_snapshot"):
            try:
                await self.execution_service.adapter.load_open_algo_orders_snapshot()
            except Exception as e:
                logger.error(
                    f"Failed to load Algo Orders snapshot: {e}", exc_info=True)

    async def shutdown(self) -> None:
        """Gracefully shutdown the runtime."""
        logger.info("Shutting down ExecPosRuntimeV2...")
        # Shutdown executor thread pool
        if hasattr(self, '_executor_thread_pool') and self._executor_thread_pool:
            self._executor_thread_pool.shutdown(wait=False)
            logger.info("Executor thread pool shutdown requested")
        # Close any resources if needed
        pass

    async def _force_initial_orders_sync(self) -> None:
        """
        Force initial synchronization of open orders from exchange.
        Critical for V2 runtime to know about existing brackets.
        """
        try:
            logger.info(
                "[ExecPosV2] Starting initial orders sync with exchange...")

            # Check if adapter has required methods
            if not hasattr(self.execution_service.adapter, "get_open_positions"):
                logger.warning(
                    "[ExecPosV2] Adapter does not have get_open_positions method, skipping sync")
                return

            if not hasattr(self.execution_service.adapter, "get_open_orders"):
                logger.warning(
                    "[ExecPosV2] Adapter does not have get_open_orders method, skipping sync")
                return

            # Get all open positions first
            positions = []
            try:
                positions = await self.execution_service.adapter.get_open_positions()
                logger.info(
                    f"[ExecPosV2] Found {len(positions)} open positions on exchange")
            except Exception as e:
                logger.error(
                    f"[ExecPosV2] Failed to get positions: {e}", exc_info=True)
                return

            # Filter to active positions (non-zero qty)
            active_symbols = set()
            for pos in positions:
                amt = float(getattr(pos, "position_amount", 0)
                            or getattr(pos, "positionAmt", 0) or 0)
                if abs(amt) > 1e-9:
                    symbol = getattr(pos, "symbol", "")
                    if symbol:
                        active_symbols.add(symbol)
                        logger.info(
                            f"[ExecPosV2] Active position: {symbol} qty={amt}")

            if not active_symbols:
                logger.info(
                    "[ExecPosV2] No active positions found, skipping orders sync")
                return

            # Get open orders for active symbols
            all_orders = []
            for symbol in active_symbols:
                try:
                    orders = await self.execution_service.adapter.get_open_orders(symbol=symbol)
                    logger.info(
                        f"[ExecPosV2] {symbol}: {len(orders)} open orders")
                    all_orders.extend(orders)
                except Exception as exc:
                    logger.warning(
                        f"[ExecPosV2] Failed to get orders for {symbol}: {exc}")
                    continue

            # Emit ORDERS_SNAPSHOT to sync order_index
            if all_orders:
                orders_event = {
                    "kind": "ORDERS_SNAPSHOT",
                    "payload": {"orders": all_orders}
                }
                await self.handle(orders_event)
                logger.info(
                    f"[ExecPosV2] ✅ Initial orders sync complete: {len(all_orders)} orders synced")
            else:
                logger.info("[ExecPosV2] No open orders found on exchange")

        except Exception as exc:
            logger.error(
                f"[ExecPosV2] ❌ Initial orders sync failed: {exc}", exc_info=True)

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get runtime metrics.

        Returns:
            Dictionary of metrics
        """
        metrics = dict(self._metrics)

        # Add dynamic metrics
        metrics["positions_tracked"] = len(self._positions_by_symbol)
        metrics["symbols_active"] = list(self._positions_by_symbol.keys())
        # Count total orders across all symbols in index
        # Note: OrderIndex doesn't expose total count directly, so we sum up
        metrics["open_orders_tracked"] = sum(
            len(self.order_index.get_by_symbol(s)) for s in self._positions_by_symbol.keys()
        )
        metrics["status"] = "healthy"

        # Merge component metrics
        if self.exposure_bridge:
            metrics.update(self.exposure_bridge.get_metrics())

        return metrics

    def get_positions_snapshot(self, symbol: Optional[str] = None, side: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get snapshot of all tracked positions for debug/observability.

        Args:
            symbol: Optional filter by symbol
            side: Optional filter by side (BUY/SELL or LONG/SHORT)

        Returns:
            List of position dictionaries with full state
        """
        positions = []
        for sym, pos in self._positions_by_symbol.items():
            if symbol and sym.upper() != symbol.upper():
                continue
            if side:
                pos_side = pos.side.upper() if pos.side else ""
                side_upper = side.upper()
                # Normalize side comparison (LONG=BUY, SHORT=SELL)
                if side_upper in ("LONG", "BUY") and pos_side not in ("LONG", "BUY"):
                    continue
                if side_upper in ("SHORT", "SELL") and pos_side not in ("SHORT", "SELL"):
                    continue
            if abs(pos.qty) > POSITION_ZERO_TOLERANCE:
                positions.append(self._position_to_dict(pos))
        return positions

    def _default_emit(self, event_kind: str, payload: Dict[str, Any]) -> None:
        """No-op event emitter for testing."""
        logger.debug(f"Event: {event_kind}")

    def set_snapshot_refresh_hook(self, hook: Callable[[str], Awaitable[None]]) -> None:
        """Register hook to request fresh ORDERS_SNAPSHOT (facade/adapter-backed)."""
        self._snapshot_request_hook = hook

    def set_position_snapshot_hook(self, hook: Callable[[], Awaitable[None]]) -> None:
        """Register hook to request fresh POSITION_SNAPSHOT (facade/adapter-backed)."""
        self._position_snapshot_hook = hook

    def _get_snapshot_cfg(self) -> SnapshotConfig:
        """
        Resolve snapshot TTL configuration with typed config preferred.
        """
        if self._ep_cfg and isinstance(self._ep_cfg, ExecutionPositionConfig):
            return getattr(self._ep_cfg, "snapshot", SnapshotConfig())

        cfg_root = self.config.get("execution_position", self.config) if isinstance(
            self.config, dict) else {}
        snapshot_cfg = cfg_root.get("snapshot", {}) if isinstance(
            cfg_root, dict) else {}
        try:
            return SnapshotConfig(
                orders_ttl_sec=float(snapshot_cfg.get("orders_ttl_sec", 3.0)),
                position_ttl_sec=float(
                    snapshot_cfg.get("position_ttl_sec", 10.0)),
            )
        except Exception:
            return SnapshotConfig()

    def _is_orders_snapshot_fresh(self, symbol: str) -> bool:
        """
        Check if we have a recent ORDERS_SNAPSHOT for the symbol.
        """
        ts = self._last_orders_snapshot_ts.get(symbol)
        if ts is None:
            return False
        ttl = self._get_snapshot_cfg().orders_ttl_sec
        return (time.monotonic() - ts) <= ttl

    def _is_position_snapshot_fresh(self, symbol: str) -> bool:
        """
        Check if we have a recent POSITION_SNAPSHOT/POSITION_SYNC for the symbol.
        """
        ts = self._last_position_snapshot_ts.get(symbol)
        if ts is None:
            return False
        ttl = self._get_snapshot_cfg().position_ttl_sec
        return (time.monotonic() - ts) <= ttl

    # =========================================================================
    # TIMEOUT RESILIENCE - Stale Mode Management
    # =========================================================================

    def is_orders_stale(self, symbol: str) -> bool:
        """
        Check if symbol is in stale mode (API timeout occurred).

        When stale=True, no new trades should be opened for this symbol
        until successful resync with exchange.

        Args:
            symbol: Trading symbol to check

        Returns:
            True if symbol is in stale mode
        """
        return self._open_orders_stale.get(symbol, False)

    def _enter_stale_mode(self, symbol: str, reason: str = "timeout") -> None:
        """
        Enter stale mode for a symbol after API failure.

        Blocks new trades and starts recovery process.

        Args:
            symbol: Trading symbol
            reason: Why we're entering stale mode (for logging)
        """
        was_stale = self._open_orders_stale.get(symbol, False)
        self._open_orders_stale[symbol] = True
        self._stale_entered_ts[symbol] = time.monotonic()
        self._orders_snapshot_state[symbol] = "STALE"

        if not was_stale:
            self._metrics["stale_mode_entered"] += 1
            logger.warning(
                f"[ExecPosV2] STALE_MODE_ENTERED: symbol={symbol} reason={reason}. "
                f"No new trades will be opened until successful resync."
            )
            # Start recovery task if not running
            self._ensure_stale_recovery_running()
        else:
            logger.debug(
                f"[ExecPosV2] STALE_MODE_STILL_ACTIVE: symbol={symbol} reason={reason}"
            )

    def _exit_stale_mode(self, symbol: str, reason: str = "resync_success") -> None:
        """
        Exit stale mode for a symbol after successful API call.

        Args:
            symbol: Trading symbol
            reason: Why we're exiting stale mode (for logging)
        """
        was_stale = self._open_orders_stale.get(symbol, False)
        self._open_orders_stale[symbol] = False
        self._orders_snapshot_state[symbol] = "FRESH"

        if was_stale:
            stale_duration = time.monotonic() - self._stale_entered_ts.get(symbol, 0)
            self._metrics["stale_mode_exited"] += 1
            self._metrics["stale_recovery_success"] += 1
            logger.info(
                f"[ExecPosV2] STALE_MODE_EXITED: symbol={symbol} reason={reason} "
                f"duration={stale_duration:.1f}s. Trading resumed."
            )
            # Clear entry timestamp
            self._stale_entered_ts.pop(symbol, None)

    def get_stale_symbols(self) -> List[str]:
        """
        Get list of symbols currently in stale mode.

        Returns:
            List of symbols with stale order state
        """
        return [s for s, is_stale in self._open_orders_stale.items() if is_stale]

    async def _try_stale_recovery(self, symbol: str) -> bool:
        """
        Attempt single recovery for a stale symbol.

        Args:
            symbol: Symbol to recover

        Returns:
            True if recovery succeeded (exited stale mode), False otherwise
        """
        self._metrics["stale_recovery_attempts"] = self._metrics.get(
            "stale_recovery_attempts", 0) + 1
        logger.info(f"[ExecPosV2] STALE_RECOVERY_ATTEMPT: symbol={symbol}")

        try:
            await self._request_orders_snapshot(symbol, force=True)
            # _request_orders_snapshot will call _exit_stale_mode on success
            return not self.is_orders_stale(symbol)
        except Exception as e:
            logger.warning(
                f"[ExecPosV2] STALE_RECOVERY_FAILED: symbol={symbol} error={e}"
            )
            return False

    def _ensure_stale_recovery_running(self) -> None:
        """Start stale recovery task if not already running."""
        if self._stale_recovery_task and not self._stale_recovery_task.done():
            return

        loop = self.async_manager.get_async_loop()
        coro = self._stale_recovery_loop()
        if loop:
            try:
                self._stale_recovery_task = loop.create_task(coro)
            except Exception:
                self._stale_recovery_task = None
        else:
            try:
                self._stale_recovery_task = asyncio.create_task(coro)
            except Exception:
                self._stale_recovery_task = None

    async def _stale_recovery_loop(self) -> None:
        """
        Periodically attempt to recover from stale mode.

        Runs until all symbols exit stale mode.
        """
        while True:
            # Check if any symbols still stale
            stale_symbols = [
                s for s, is_stale in self._open_orders_stale.items() if is_stale]
            if not stale_symbols:
                logger.debug(
                    "[ExecPosV2] STALE_RECOVERY_COMPLETE: No more stale symbols")
                break

            for symbol in stale_symbols:
                self._metrics["stale_recovery_attempts"] += 1
                logger.info(
                    f"[ExecPosV2] STALE_RECOVERY_ATTEMPT: symbol={symbol}")

                try:
                    # Request fresh snapshot
                    await self._request_orders_snapshot(symbol, force=True)
                    # Note: _exit_stale_mode is called in _handle_orders_snapshot if successful
                except Exception as e:
                    logger.warning(
                        f"[ExecPosV2] STALE_RECOVERY_FAILED: symbol={symbol} error={e}"
                    )

            await asyncio.sleep(self._stale_recovery_interval_sec)

    def _mark_orders_snapshot(self, symbol: str, ts: Optional[float] = None) -> None:
        self._last_orders_snapshot_ts[symbol] = ts or time.monotonic()
        self._orders_snapshot_state[symbol] = "FRESH"
        # Exit stale mode on successful snapshot
        if self._open_orders_stale.get(symbol, False):
            self._exit_stale_mode(symbol, reason="orders_snapshot_received")

    def _mark_position_snapshot(self, symbol: str, ts: Optional[float] = None) -> None:
        self._last_position_snapshot_ts[symbol] = ts or time.monotonic()

    def _remove_order_from_mirror(self, symbol: str, order_id: str) -> None:
        """
        R2-B: Remove order from local mirror after CANCEL action.

        This ensures tests checking order_index see updated state
        without waiting for next ORDERS_SNAPSHOT.

        Args:
            symbol: Trading symbol
            order_id: Exchange order ID to remove
        """
        ref = self.order_index.get(exchangeOrderId=str(order_id))
        if ref:
            self.order_index.mark_terminal(ref)
            self.order_index.expire()  # Clean up immediately

        logger.debug(
            f"[ExecPosV2] MIRROR_UPDATE symbol={symbol} "
            f"removed_order={order_id}"
        )

    async def _request_orders_snapshot(self, symbol: str, *, force: bool = False) -> None:
        """
        Invoke hook to refresh orders snapshot with per-symbol throttle.

        On timeout/network error, enters stale mode for the symbol.
        """
        if not self._snapshot_request_hook:
            return
        now = time.monotonic()
        last = self._last_snapshot_request_ts.get(symbol, 0.0)
        if not force and now - last < self._snapshot_request_interval_sec:
            logger.debug(
                f"[ExecPosV2] FORCE_SNAPSHOT_THROTTLED symbol={symbol} "
                f"elapsed={now - last:.2f}s < interval={self._snapshot_request_interval_sec}s"
            )
            return

        self._last_snapshot_request_ts[symbol] = now
        reason = "force" if force else "watchdog"
        logger.info(
            "[ExecPosV2] FORCE_SNAPSHOT_REQUEST",
            extra={"symbol": symbol, "reason": reason},
        )
        try:
            await self._snapshot_request_hook(symbol)
            # Note: _exit_stale_mode is called in _handle_orders_snapshot if successful
        except Exception as e:
            exception_type = type(e).__name__

            # Check if this is a timeout exception
            timeout_types = ("ReadTimeout", "ConnectTimeout", "WriteTimeout",
                             "PoolTimeout", "TimeoutException")
            network_types = ("ConnectError", "RemoteProtocolError", "NetworkError",
                             "ConnectionError", "OSError")

            if exception_type in timeout_types:
                logger.warning(
                    f"[ExecPosV2] SNAPSHOT_REQUEST_TIMEOUT: symbol={symbol} "
                    f"error={exception_type}: {str(e)[:80]}. Entering stale mode."
                )
                self._enter_stale_mode(
                    symbol, reason=f"snapshot_timeout_{exception_type}")
            elif exception_type in network_types:
                logger.warning(
                    f"[ExecPosV2] SNAPSHOT_REQUEST_NETWORK_ERROR: symbol={symbol} "
                    f"error={exception_type}: {str(e)[:80]}. Entering stale mode."
                )
                self._enter_stale_mode(
                    symbol, reason=f"snapshot_network_{exception_type}")
            else:
                logger.error(
                    "[ExecPosV2] FORCE_SNAPSHOT_REQUEST_FAILED",
                    exc_info=True,
                    extra={"symbol": symbol},
                )

    async def handle(self, event):
        """Main event dispatcher. Accepts dict or RuntimeEvent."""
        self._metrics["events_total"] += 1

        # Support both dict and RuntimeEvent
        if isinstance(event, dict):
            kind = event.get("kind")
            symbol = event.get("symbol")
            payload = event.get("payload", event)
        else:
            kind = event.kind
            symbol = event.symbol
            payload = event.payload

        self._metrics["events_by_kind"][kind] = \
            self._metrics["events_by_kind"].get(kind, 0) + 1

        try:
            if kind == "ENTRY_INTENT":
                await self._handle_entry_intent(symbol, payload)
            elif kind == "CANCEL_INTENT":
                await self._handle_cancel_intent(symbol, payload)
            elif kind == "CLOSE_INTENT":
                await self._handle_close_intent(symbol, payload)
            elif kind == "TRADE_EXECUTED":
                await self._handle_trade_executed(symbol, payload)
            elif kind == "POSITION_SYNC":
                await self._handle_position_sync(symbol, payload)
            elif kind == "POSITION_SNAPSHOT":
                await self._handle_position_snapshot(payload)
            elif kind == "ORDERS_SNAPSHOT":
                await self._handle_orders_snapshot(payload)
            elif kind == "EVT:ALGO_ORDER_UPDATED":
                await self._handle_algo_order_updated(payload)
            else:
                logger.warning(f"Unknown event kind: {kind}")

        except Exception as e:
            logger.error(f"Error handling event {kind}: {e}", exc_info=True)

    async def _handle_entry_intent(self, symbol: str, payload: Dict[str, Any]):
        """Handle entry request through gatekeeper -> execution service."""
        # Canonical ENTRY_INTENT payload expected by runtime:
        # {
        #   "symbol": str,
        #   "side": "BUY" | "SELL",
        #   "quantity": float | str,
        #   "price": Optional[float|str],
        #   "source": Optional[str],
        #   "rid": Optional[str],
        #   "idempotent_key": Optional[str],
        # }
        logger.info(
            "[ExecPosV2-S5] ENTRY_INTENT received: symbol=%s side=%s qty=%s",
            payload.get("symbol"),
            payload.get("side"),
            payload.get("qty") or payload.get("quantity"),
        )

        # =================================================================
        # DUPLICATE ENTRY GUARD: Block if already have position or pending entry
        # =================================================================
        # Check 1: Already have an open position for this symbol
        existing_pos = self._positions_by_symbol.get(symbol)
        if existing_pos and abs(existing_pos.qty) > POSITION_ZERO_TOLERANCE:
            logger.info(
                f"[ExecPosV2] ENTRY_BLOCKED_HAS_POSITION: symbol={symbol} "
                f"existing_qty={existing_pos.qty}. Ignoring duplicate ENTRY_INTENT."
            )
            return

        # Check 2: Already have a pending LIMIT entry order with SAME price
        order_refs = self.order_index.get_by_symbol(symbol)
        for ref in order_refs:
            order = ref.to_dict() if hasattr(ref, 'to_dict') else ref
            order_type = order.get("type") or order.get(
                "order_type") or order.get("origType", "")
            order_status = order.get("status", "")
            reduce_only = order.get("reduceOnly") or order.get(
                "reduce_only", False)
            # Pending entry = LIMIT order that is NEW and NOT reduce_only (not TP/SL)
            if (order_type == "LIMIT" and
                order_status in ("NEW", "PARTIALLY_FILLED") and
                    not reduce_only):
                # Allow multiple LIMIT orders if they have DIFFERENT prices
                existing_price = order.get("price")
                new_price = payload.get("price")
                if existing_price is not None and new_price is not None:
                    if abs(float(existing_price) - float(new_price)) > 1e-8:  # Different price
                        continue  # Allow this new order
                logger.info(
                    f"[ExecPosV2] ENTRY_BLOCKED_PENDING_ORDER: symbol={symbol} "
                    f"order_id={order.get('order_id') or order.get('orderId') or order.get('exchangeOrderId')} "
                    f"existing_price={existing_price} new_price={new_price} status={order_status}. Ignoring duplicate ENTRY_INTENT."
                )
                return

        # =================================================================
        # TIMEOUT RESILIENCE: Block new entries when in stale mode
        # =================================================================
        # If we recently had a timeout fetching exchange state, we're "blind"
        # and should not open new positions until we successfully resync.
        if self.is_orders_stale(symbol):
            self._metrics["stale_mode_blocked_intents"] += 1
            stale_duration = time.monotonic() - self._stale_entered_ts.get(symbol, 0)
            logger.warning(
                f"[ExecPosV2] ENTRY_BLOCKED_STALE_MODE: symbol={symbol} "
                f"stale_duration={stale_duration:.1f}s. "
                f"Waiting for successful API resync before trading."
            )
            logging_v2.log_runtime_event(
                event_kind="ENTRY_INTENT",
                symbol=symbol,
                action="blocked",
                result="stale_mode",
                why="orders_snapshot_stale_timeout",
                extra={
                    "stale_duration_sec": round(stale_duration, 1),
                    "side": payload.get("side"),
                    "quantity": str(payload.get("quantity") or payload.get("qty")),
                }
            )
            return

        side = payload.get("side")
        quantity = payload.get("quantity")
        price = payload.get("price")
        order_type = payload.get("order_type", "MARKET")

        # Guard check
        gate_decision = self.gatekeeper.check_entry(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type
        )

        if not gate_decision["allowed"]:
            self._metrics["gatekeeper_rejected"] += 1
            logger.info(
                f"SHADOW_ENTRY_REJECTED",
                extra={"symbol": symbol, "reason": gate_decision["reason"]}
            )
            # Structured logging
            logging_v2.log_runtime_event(
                event_kind="ENTRY_INTENT",
                symbol=symbol,
                action="rejected",
                result="blocked",
                why=gate_decision["reason"],
                extra={"side": side, "quantity": str(
                    quantity), "order_type": order_type}
            )
            return

        self._metrics["gatekeeper_allowed"] += 1

        # Use adjusted params from gatekeeper
        adjusted_qty = gate_decision["modified_params"].get(
            "quantity", quantity)
        adjusted_price = gate_decision["modified_params"].get("price", price)

        # ═══════════════════════════════════════════════════════════════════
        # EXECUTOR POOL V2: Entry ONLY, no automatic brackets
        # BracketService will handle SL/TP after TRADE_EXECUTED event
        # CRITICAL: Run in thread pool to avoid blocking main event loop!
        # ═══════════════════════════════════════════════════════════════════
        if self._use_executor_pool:
            # Generate client_order_id if not provided
            client_order_id = payload.get(
                "client_order_id") or f"AUR-{symbol}-{int(time.time()*1000)}"

            # ExecutorPoolV2.execute_entry() - ENTRY ONLY, no brackets
            # Brackets will be handled by BracketService after TRADE_EXECUTED
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                self._executor_thread_pool,
                lambda: self.executor_pool.execute_entry(
                    symbol=symbol,
                    side=side,
                    quantity=str(adjusted_qty),
                    price=str(adjusted_price) if adjusted_price else None,
                    client_order_id=client_order_id,
                    order_type=order_type,
                    rate_limit_timeout=5.0,
                )
            )

            if result["success"]:
                self._metrics["execution_success"] += 1
                # Add to open orders via OrderIndex
                self.order_index.upsert_from_open(
                    rid=payload.get(
                        "rid") or f"rid_{result.get('order_id')}",
                    idempotent_key=payload.get("idempotent_key"),
                    clientOrderId=client_order_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    price=float(adjusted_price) if adjusted_price else None,
                    quantity=float(adjusted_qty),
                )
                # Attach exchange ID
                if result.get("order_id"):
                    self.order_index.attach_exchange_id(
                        clientOrderId=client_order_id,
                        exchangeOrderId=str(result["order_id"])
                    )

                # Update position from fill (if immediately filled)
                fill_price = result.get("fill_price")
                fill_qty = result.get("fill_qty") or adjusted_qty
                if fill_price:
                    position = self._positions_by_symbol.get(
                        symbol, PositionState(symbol=symbol))
                    new_position = apply_fill(
                        position,
                        side=side,
                        quantity=float(fill_qty),
                        price=float(fill_price),
                    )
                    self._positions_by_symbol[symbol] = new_position

                    # Check if this is a new position (was flat, now has position)
                    is_new_position = abs(position.qty) < POSITION_ZERO_TOLERANCE and abs(
                        new_position.qty) > POSITION_ZERO_TOLERANCE
                    if is_new_position:
                        logger.debug(
                            f"[ExecPosV2] NEW_POSITION_DETECTED: Requesting initial snapshot for {symbol}")
                        await self._request_orders_snapshot(symbol)

                    # CRITICAL: Trigger brackets after fill (testnet WebSocket fallback)
                    # On testnet, ACCOUNT_UPDATE/TRADE_EXECUTED may not arrive via WS
                    logger.info(
                        f"[ExecPosV2] ENTRY_FILLED_POLLING: {symbol} qty={fill_qty} @ {fill_price} - evaluating brackets"
                    )
                    await self._evaluate_brackets(symbol, new_position, reason="polling_fill")

                logging_v2.log_runtime_event(
                    event_kind="ENTRY_INTENT",
                    symbol=symbol,
                    action="executed",
                    result="success",
                    why="executor_pool_v2_entry_only",
                    extra={
                        "order_id": result.get("order_id"),
                        "fill_price": str(result.get("fill_price")),
                        "latency_ms": result.get("latency_ms"),
                        "brackets": "via_core_planner",  # Phase 11: Brackets via aggregator_oco core
                    }
                )
            else:
                self._metrics["execution_failed"] += 1
                error_msg = result.get("error", "executor_pool_failed")

                # Log appropriately based on error type
                if "busy" in error_msg.lower():
                    logger.info(
                        f"[ExecPosV2] EXECUTOR_BUSY: {symbol} - {error_msg}")
                elif "rate limit" in error_msg.lower():
                    logger.warning(
                        f"[ExecPosV2] RATE_LIMITED: {symbol} - {error_msg}")
                else:
                    logger.error(
                        f"[ExecPosV2] EXECUTION_FAILED: {symbol} - {error_msg}")

                logging_v2.log_runtime_event(
                    event_kind="ENTRY_INTENT",
                    symbol=symbol,
                    action="executed",
                    result="failed",
                    why=error_msg,
                    extra={"side": side, "quantity": str(adjusted_qty)}
                )
            return

        # ─────────────────────────────────────────────────────────────────────
        # FALLBACK: Direct async execution via ExecutionService
        # Used when ExecutorPool is disabled (testing/special cases)
        # No auto-brackets - BracketService handles brackets via TRADE_EXECUTED
        # ─────────────────────────────────────────────────────────────────────
        logger.info(
            f"[ExecPosV2] ASYNC_EXECUTION_PATH: {symbol} - ExecutorPool disabled"
        )
        result = await self.execution_service.place_order(
            symbol=symbol,
            side=side,
            quantity=adjusted_qty,
            order_type=order_type,
            price=adjusted_price,
            client_order_id=payload.get("client_order_id"),
        )

        if result.get("success"):
            self._metrics["execution_success"] += 1
            order_id = result.get("order_id")
            self.order_index.upsert_from_open(
                rid=payload.get("rid") or f"rid_{order_id}",
                idempotent_key=payload.get("idempotent_key"),
                clientOrderId=payload.get("client_order_id"),
                symbol=symbol,
                side=side,
                order_type=order_type,
                price=float(adjusted_price) if adjusted_price else None,
                quantity=float(adjusted_qty),
            )
            if order_id:
                self.order_index.attach_exchange_id(
                    clientOrderId=payload.get("client_order_id"),
                    exchangeOrderId=str(order_id)
                )

            # TESTNET FALLBACK: For LIMIT orders, poll for fill since WebSocket may not work
            status = result.get("status", "")
            if order_type == "LIMIT" and status != "FILLED" and order_id:
                logger.info(
                    f"[ExecPosV2] ASYNC_PATH_POLLING: Polling for LIMIT fill {symbol} order_id={order_id}"
                )
                fill_data = await self._poll_order_until_filled(symbol, order_id, timeout_sec=55.0)
                if fill_data:
                    # Update position and evaluate brackets
                    fill_price = fill_data.get("fill_price")
                    fill_qty = fill_data.get("fill_qty") or adjusted_qty
                    if fill_price:
                        position = self._positions_by_symbol.get(
                            symbol, PositionState(symbol=symbol))
                        new_position = apply_fill(
                            position,
                            side=side,
                            quantity=float(fill_qty),
                            price=float(fill_price),
                        )
                        self._positions_by_symbol[symbol] = new_position

                        # Check if this is a new position (was flat, now has position)
                        is_new_position = abs(position.qty) < POSITION_ZERO_TOLERANCE and abs(
                            new_position.qty) > POSITION_ZERO_TOLERANCE
                        if is_new_position:
                            logger.debug(
                                f"[ExecPosV2] NEW_POSITION_DETECTED: Requesting initial snapshot for {symbol}")
                            await self._request_orders_snapshot(symbol)

                        logger.info(
                            f"[ExecPosV2] ASYNC_FILL_POLLING: {symbol} qty={fill_qty} @ {fill_price} - evaluating brackets"
                        )
                        await self._evaluate_brackets(symbol, new_position, reason="async_polling_fill")
                else:
                    logger.warning(
                        f"[ExecPosV2] ASYNC_PATH_POLL_TIMEOUT: {symbol} order_id={order_id} - no fill detected"
                    )
            elif status == "FILLED":
                # Immediate fill (MARKET order) - update position
                fill_price = result.get("avgPrice") or result.get(
                    "price") or adjusted_price
                fill_qty = result.get("executedQty") or adjusted_qty
                if fill_price:
                    position = self._positions_by_symbol.get(
                        symbol, PositionState(symbol=symbol))
                    new_position = apply_fill(
                        position,
                        side=side,
                        quantity=float(fill_qty),
                        price=float(fill_price),
                    )
                    self._positions_by_symbol[symbol] = new_position

                    # Check if this is a new position (was flat, now has position)
                    is_new_position = abs(position.qty) < POSITION_ZERO_TOLERANCE and abs(
                        new_position.qty) > POSITION_ZERO_TOLERANCE
                    if is_new_position:
                        logger.debug(
                            f"[ExecPosV2] NEW_POSITION_DETECTED: Requesting initial snapshot for {symbol}")
                        await self._request_orders_snapshot(symbol)

                    await self._evaluate_brackets(symbol, new_position, reason="immediate_fill")
        else:
            self._metrics["execution_failed"] += 1
        return

    async def _poll_order_until_filled(
        self,
        symbol: str,
        order_id: str,
        timeout_sec: float = 55.0,
        poll_interval_sec: float = 1.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Poll order status via REST API until filled or timeout.

        Fallback for testnet where WebSocket USER_DATA_STREAM may not work.

        Returns:
            Dict with fill data if FILLED, None if timeout/error/cancelled
        """
        # Get adapter from execution_service
        adapter = getattr(self.execution_service, 'adapter', None)
        if not adapter or not hasattr(adapter, 'get_order'):
            logger.warning(
                f"[ExecPosV2] No adapter available for polling {symbol}")
            return None

        start_time = time.monotonic()
        poll_count = 0
        logger.info(
            f"[ExecPosV2] Starting polling for {symbol} order_id={order_id}, timeout={timeout_sec}s")

        while time.monotonic() - start_time < timeout_sec:
            poll_count += 1
            try:
                # Query order status via adapter
                order_status = await adapter.get_order(
                    symbol=symbol,
                    order_id=int(order_id),
                )

                status = order_status.get("status", "")

                if status == "FILLED":
                    fill_price = order_status.get(
                        "avgPrice") or order_status.get("price")
                    fill_qty = order_status.get(
                        "executedQty") or order_status.get("origQty")
                    logger.info(
                        f"[ExecPosV2] Order {order_id} FILLED qty={fill_qty} @ {fill_price} (poll #{poll_count})"
                    )
                    return {
                        "status": "FILLED",
                        "fill_price": str(fill_price) if fill_price else None,
                        "fill_qty": str(fill_qty) if fill_qty else None,
                    }
                elif status in ("CANCELED", "EXPIRED", "REJECTED"):
                    logger.warning(
                        f"[ExecPosV2] Order {order_id} {status} (poll #{poll_count})"
                    )
                    return None

                logger.debug(
                    f"[ExecPosV2] Order {order_id} status={status} (poll #{poll_count})"
                )

            except Exception as e:
                logger.warning(
                    f"[ExecPosV2] Poll error for {symbol}: {e} (poll #{poll_count})"
                )

            await asyncio.sleep(poll_interval_sec)

        logger.warning(
            f"[ExecPosV2] Poll timeout for {symbol} order_id={order_id} after {poll_count} attempts"
        )
        return None

    async def _handle_cancel_intent(self, symbol: str, payload: Dict[str, Any]):
        """Handle cancel request."""
        order_id = payload.get("order_id")

        result = await self.execution_service.cancel_order(
            symbol=symbol,
            order_id=order_id
        )

        if result["success"]:
            self._metrics["execution_success"] += 1
            # Remove from open orders
            self._remove_order_from_mirror(symbol, str(order_id))
        else:
            self._metrics["execution_failed"] += 1

    async def _handle_close_intent(self, symbol: str, payload: Dict[str, Any]):
        """Handle close position request via CloseFlowService."""
        position = self._positions_by_symbol.get(
            symbol, PositionState(symbol=symbol))
        ctx = CloseContext(
            reason=payload.get("reason", "MANUAL"),
            requested_qty=payload.get("quantity"),
            price=payload.get("price"),
            timestamp=payload.get("timestamp") or payload.get("ts"),
        )
        try:
            decision = self.close_flow_service.plan_close(
                position, ctx, self._get_close_config())
        except Exception as exc:
            logger.warning(
                "CloseFlowService error, ignoring close intent", exc_info=True)
            decision = None

        if not decision or decision.action in ("NOOP", "IGNORE"):
            logging_v2.log_runtime_event(
                event_kind="CLOSE_INTENT",
                symbol=symbol,
                action="ignored",
                result="noop",
                why=getattr(decision, "reason_code", "NO_DECISION"),
                extra={"requested_qty": payload.get("quantity")},
            )
            return

        raw_target = payload.get("quantity", decision.target_qty)
        if raw_target is None:
            raw_target = decision.target_qty
        target_qty = raw_target if isinstance(
            raw_target, str) else float(raw_target or 0.0)
        close_side = "SELL" if position.qty > 0 else (
            "BUY" if position.qty < 0 else None)

        result = await self.execution_service.close_position(
            symbol=symbol,
            quantity=target_qty,
            side=close_side
        )

        if result["success"]:
            self._metrics["execution_success"] += 1
            # For full close, clear position state
            if decision.action == "CLOSE_FULL":
                self._positions_by_symbol[symbol] = PositionState(
                    symbol=symbol)
        else:
            self._metrics["execution_failed"] += 1

    async def _handle_trade_executed(self, symbol: str, payload: Dict[str, Any]):
        """
        Handle fill/trade event.

        Ordering (EP-RUNTIME-WAL-EXPOSURE-S1):
        1. Idempotency check
        2. Price enrichment
        3. Update internal position state (CRITICAL: do this first)
        4. Write WAL (EXEC_TRADE + EXEC_POSITION)
        5. Emit exposure update
        6. Trigger watchdog
        7. Evaluate brackets via BracketService
        """
        # Route fill event to ExecutorPool for blocking executor threads
        if self._use_executor_pool:
            order_id = payload.get("order_id") or payload.get("orderId") or ""
            fill_price = str(payload.get("price")
                             or payload.get("last_price") or "0")
            fill_qty = str(payload.get("quantity")
                           or payload.get("qty") or "0")
            self.executor_pool.on_fill(
                symbol=symbol,
                fill_price=fill_price,
                fill_qty=fill_qty,
                order_id=str(order_id),
            )

        # Serialize execution per-symbol to prevent race conditions on partial fills
        async with self._get_symbol_lock(symbol):
            # FIX: Ignore TRADE_EXECUTED for non-fills (e.g. NEW orders mapped incorrectly)
            status = payload.get("status")
            if status in ("NEW", "CANCELED", "EXPIRED", "REJECTED", "PENDING_CANCEL"):
                logger.warning(
                    f"TRADE_EXECUTED ignored for non-fill status: {symbol} status={status}",
                    extra={"payload": payload}
                )
                return

            # 1. Check idempotency
            if not self.fill_idempotency.should_process_fill(payload, symbol=symbol):
                self._metrics["fills_duplicate"] += 1
                return

            self._metrics["fills_processed"] += 1

            # 2. Update position state (CRITICAL: do this before WAL/exposure)
            raw_qty = float(payload.get("quantity", 0)
                            or payload.get("qty", 0))
            # R2-F: Normalize to abs (adapter should already do this, but defense-in-depth)
            qty = abs(raw_qty)
            side = payload.get("side", "").upper()

            # R2-G: Track fill metrics
            self._metrics["fills_total"] += 1
            if raw_qty < 0:
                self._metrics["fills_signed_qty_seen_total"] += 1
            if qty != raw_qty:
                self._metrics["fills_abs_normalized_total"] += 1

            if side not in ("BUY", "SELL"):
                logger.warning("TRADE_EXECUTED missing/invalid side; skipping fill",
                               extra={"symbol": symbol, "payload": payload})
                return
            if qty == 0:
                # R2-G: Track zero fills
                self._metrics["fills_zero_ignored_total"] += 1
                logger.warning("TRADE_EXECUTED zero quantity; skipping fill",
                               extra={"symbol": symbol, "payload": payload})
                return

            current_state = self._positions_by_symbol.get(
                symbol) or PositionState(symbol=symbol)
            is_new_position = abs(current_state.qty) < POSITION_ZERO_TOLERANCE

            # R2-B: Save previous position state for reverse detection
            if abs(current_state.qty) > POSITION_ZERO_TOLERANCE:
                self._prev_positions_by_symbol[symbol] = current_state

            # Apply fill via PositionState
            new_state = apply_fill(
                current_state,
                side=side,
                quantity=qty,
                price=float(payload.get("price", 0)
                            or payload.get("last_price", 0) or 0.0),
                ts=payload.get("timestamp") or payload.get("ts"),
            )

            # R2-D: Increment cycle_id on new position or reverse
            prev_side = current_state.side
            new_side = new_state.side

            is_prev_flat = abs(current_state.qty) < POSITION_ZERO_TOLERANCE
            is_new_flat = abs(new_state.qty) < POSITION_ZERO_TOLERANCE

            if is_prev_flat and not is_new_flat:
                # New position opened from FLAT
                new_cycle_id = current_state.cycle_id + 1
                new_state = replace(new_state, cycle_id=new_cycle_id)
                logger.debug(
                    f"[ExecPosV2] POSITION_CYCLE_NEW: {symbol} cycle_id {current_state.cycle_id} → {new_cycle_id}",
                    extra={"symbol": symbol, "prev_side": prev_side,
                           "new_side": new_side}
                )
            elif not is_prev_flat and not is_new_flat and prev_side != new_side:
                # Reverse LONG↔SHORT without intermediate FLAT
                new_cycle_id = current_state.cycle_id + 1
                new_state = replace(new_state, cycle_id=new_cycle_id)
                logger.debug(
                    f"[ExecPosV2] POSITION_CYCLE_REVERSE: {symbol} cycle_id {current_state.cycle_id} → {new_cycle_id}",
                    extra={"symbol": symbol, "prev_side": prev_side,
                           "new_side": new_side}
                )
            else:
                # Same cycle, carry over cycle_id
                new_state = replace(new_state, cycle_id=current_state.cycle_id)

            self._positions_by_symbol[symbol] = new_state
            self._mark_position_snapshot(symbol)
            self._ensure_guard_loop_running()
            self._ensure_position_polling_running()

            # FIX-NEW-SYMBOL-SNAPSHOT: Request initial orders snapshot for new positions
            # This ensures guard_loop can evaluate brackets for symbols that start with positions
            # but have UNKNOWN snapshot state (new symbols never get snapshot requests otherwise)
            if is_new_position:
                logger.debug(
                    f"[ExecPosV2] NEW_POSITION_DETECTED: Requesting initial snapshot for {symbol}")
                await self._request_orders_snapshot(symbol)

            # 4. Write WAL records (fail-closed)
            # EXEC_TRADE record
            position_ctx = {
                "position_id": f"{symbol}_{int(time.time())}",
                "is_new_position": is_new_position,
                "realized_pnl": new_state.realized_pnl,
                "fee": 0,  # TODO: extract from payload
            }
            if self.wal_writer.write_trade_wal(payload, position_ctx):
                self._metrics["wal_trades_written"] += 1

            # EXEC_POSITION record (if position changed)
            if self.wal_writer.write_position_wal(self._position_to_dict(new_state)):
                self._metrics["wal_positions_written"] += 1

            # 5. Emit exposure update (fail-closed)
            if self.exposure_bridge.emit_exposure_update(self._position_to_dict(new_state)):
                self._metrics["exposure_updates_emitted"] += 1

            # 6. Trigger watchdog after all state/WAL/exposure updates
            await self._run_watchdog_analysis()

            # 7. Detect reverse (LONG→SHORT or SHORT→LONG) and cleanup old side brackets
            await self._handle_reverse_cleanup(symbol, new_state)

            # 7.5. Detect FLAT position and cleanup orphan brackets
            if abs(new_state.qty) < POSITION_ZERO_TOLERANCE:
                logger.info(
                    f"[ExecPosV2] POSITION_FLAT_DETECTED: Cleaning up orphan brackets for {symbol}")
                await self._cleanup_orphan_brackets_for_flat(symbol)

            # 7.6. Check for position size changes requiring bracket cleanup
            await self._cleanup_brackets_for_position_size_change(symbol, new_state)

            # 8. Evaluate brackets (execute BracketPlan actions)
            await self._evaluate_brackets(symbol, new_state, reason="trade_executed")
            self._maybe_stop_guard_loop()
            self._maybe_stop_position_polling()

    async def _handle_position_sync(self, symbol: str, payload: Dict[str, Any]):
        """
        Handle POSITION_SYNC event from ACCOUNT_UPDATE.
        Triggers bracket evaluation for positions that may have been filled
        but didn't emit proper TRADE_EXECUTED events.

        CRITICAL: Also handles orphan cleanup when position becomes FLAT.
        """
        async with self._get_symbol_lock(symbol):
            positions = payload.get("positions", [])

            for pos in positions:
                pos_symbol = pos.get("symbol")
                if not pos_symbol or pos_symbol != symbol:
                    continue

                # Update position state
                await self._handle_single_position_update(pos)

                # Get current state
                current_state = self._positions_by_symbol.get(pos_symbol)

                if current_state and abs(current_state.qty) > POSITION_ZERO_TOLERANCE:
                    # Non-zero position -> evaluate brackets (place TP/SL)
                    logger.info(
                        f"📊 POSITION_SYNC: Evaluating brackets for {pos_symbol} qty={current_state.qty}")
                    await self._evaluate_brackets(pos_symbol, current_state, reason="account_update_sync")
                else:
                    # FLAT position -> cleanup orphan TP/SL orders
                    logger.info(
                        f"📊 POSITION_SYNC: Position {pos_symbol} is FLAT (qty=0), checking for orphan brackets")
                    await self._cleanup_orphan_brackets_for_flat(pos_symbol)

    async def _handle_position_snapshot(self, payload: Dict[str, Any]):
        """Handle position snapshot from exchange."""
        # Global lock for full snapshot (affects multiple symbols)
        async with self._get_global_lock():
            # Handle list of positions (e.g. from REST snapshot)
            if "positions" in payload:
                for pos in payload["positions"]:
                    await self._handle_single_position_update(pos)
                return

            # Handle single position (e.g. from WS update)
            await self._handle_single_position_update(payload)

    async def _handle_single_position_update(self, payload: Dict[str, Any]):
        """Update state for a single position."""
        # E-004 FIX: Support both WS normalized keys (symbol, positionAmt, entryPrice)
        # and REST keys (symbol, qty, entry_price)
        symbol = payload.get("symbol") or payload.get("s")
        if not symbol:
            return

        # Map fields from various sources (REST vs WS normalized vs legacy)
        # Priority: REST fields → WS normalized → legacy
        qty_val = payload.get("qty") or payload.get(
            "positionAmt") or payload.get("position_size") or payload.get("pa") or 0
        entry_val = payload.get(
            "entry_price") or payload.get("entryPrice") or payload.get("ep") or 0
        qty = float(qty_val or 0)
        entry_price = float(entry_val or 0)

        # LEVERAGE-FIX: Extract and cache leverage from API response
        # Keys: "leverage" (REST/ExchangePosition), "l" (WS shorthand)
        lev_val = payload.get("leverage") or payload.get("l")
        if lev_val is not None:
            try:
                lev_int = int(float(lev_val))
                if lev_int > 0:
                    self._leverage_by_symbol[symbol] = lev_int
                    logger.debug(
                        f"[ExecPosV2] LEVERAGE_CACHED: {symbol} leverage={lev_int}")
            except (TypeError, ValueError):
                pass

        # E-004: Log if we have qty but no entry price (contract violation from adapter)
        if abs(qty) > POSITION_ZERO_TOLERANCE and entry_price <= 0:
            logger.warning(
                f"[ExecPosV2] POSITION_UPDATE_MISSING_ENTRY_PRICE: {symbol} qty={qty}, "
                f"entryPrice={entry_price}. Payload keys: {list(payload.keys())}. "
                "Watchdog may trigger REST snapshot recovery."
            )

        # Check if this is a new position (was flat, now has position)
        prev_position = self._positions_by_symbol.get(symbol)
        is_new_position = (
            prev_position is None or abs(
                prev_position.qty) <= POSITION_ZERO_TOLERANCE
        ) and abs(qty) > POSITION_ZERO_TOLERANCE

        self._positions_by_symbol[symbol] = PositionState(
            symbol=symbol,
            qty=qty,
            avg_entry_price=entry_price,
            realized_pnl=float(payload.get("realized_pnl") or 0.0),
            unrealized_pnl=float(payload.get("unrealized_pnl") or 0.0),
            open_time=payload.get("open_time"),
            last_update_time=payload.get("update_time") or payload.get("ts"),
            scale_in_count=0,
            scale_out_count=0,
        )
        self._mark_position_snapshot(symbol)
        self._ensure_guard_loop_running()
        self._ensure_position_polling_running()

        # Request initial snapshot for new positions to enable bracket evaluation
        if is_new_position:
            logger.debug(
                f"[ExecPosV2] NEW_POSITION_DETECTED: Requesting initial snapshot for {symbol}")
            await self._request_orders_snapshot(symbol, force=True)

        # Trigger watchdog
        await self._run_watchdog_analysis()
        self._maybe_stop_guard_loop()
        self._maybe_stop_position_polling()

    async def _handle_orders_snapshot(self, payload: Dict[str, Any]):
        """Handle orders snapshot from exchange."""
        orders = payload.get("orders", [])

        # EP-ORDERS-SYNC: Log incoming snapshot for debugging
        logger.info(
            "[ExecPosV2] ORDERS_SNAPSHOT_RECEIVED count=%d types=%s",
            len(orders) if orders else 0,
            [getattr(o, 'order_type', None) or (o.get('type') if isinstance(
                o, dict) else None) for o in (orders or [])][:5]
        )

        # R2-C fix: Empty snapshot is single source of truth
        # If exchange says "no orders", clear mirror for all symbols
        if not orders:
            logging_v2.log_runtime_event(
                event_kind="ORDERS_SNAPSHOT",
                symbol="*",
                action="apply",
                result="empty_snapshot_clears_mirror",
                why="r2c_empty_snapshot_truth",
            )

            # Clear mirror for all symbols with positions (exchange truth: no orders)
            for sym in self._positions_by_symbol.keys():
                self.order_index.reconcile_snapshot(sym, [])
                self._orders_snapshot_state[sym] = "FRESH"
                self._mark_orders_snapshot(sym)
                logger.debug(
                    f"[ExecPosV2] EMPTY_ORDERS_SNAPSHOT cleared mirror for {sym}",
                    extra={"symbol": sym, "snapshot_state": "FRESH"}
                )

            # Persist after clearing empty snapshot
            self.order_index.save_to_file(self.ORDER_INDEX_PERSISTENCE_FILE)

            # Stale existing FRESH states for symbols without positions
            for sym, state in list(self._orders_snapshot_state.items()):
                if state == "FRESH" and sym not in self._positions_by_symbol:
                    self._orders_snapshot_state[sym] = "STALE"
            return

        now = time.monotonic()

        # Group by symbol
        orders_by_symbol = {}
        for order in orders:
            # Handle both dict and ExchangeOrderResponse objects
            if hasattr(order, "to_dict"):
                order_dict = order.to_dict()
                sym = order.symbol
            elif isinstance(order, dict):
                order_dict = order
                sym = order.get("symbol")
            else:
                continue  # Skip unknown order types
            if sym:
                orders_by_symbol.setdefault(sym, []).append(order_dict)

        # EP-ORDERS-SYNC: Log grouped orders for each symbol
        for sym, sym_orders in orders_by_symbol.items():
            logger.info(
                "[ExecPosV2] ORDERS_SNAPSHOT_BY_SYMBOL symbol=%s count=%d types=%s",
                sym, len(sym_orders),
                [o.get('type') or o.get('origType') for o in sym_orders]
            )

        for sym, sym_orders in orders_by_symbol.items():
            self.order_index.reconcile_snapshot(sym, sym_orders)
            self._mark_orders_snapshot(sym, now)
            self._orders_snapshot_state[sym] = "FRESH"

            # R3-D1: Clear awaiting_snapshot after orders confirmed
            if sym in self._bracket_status:
                self._bracket_status[sym].awaiting_snapshot = False

        # Periodic cleanup of idempotency store to prevent memory leak
        self.fill_idempotency.cleanup()
        # Also expire old orders in index
        self.order_index.expire()

        # Persist order index state after snapshot processing
        self.order_index.save_to_file(self.ORDER_INDEX_PERSISTENCE_FILE)

        # Trigger watchdog
        await self._run_watchdog_analysis()
        if not self._recovery_completed:
            await self._run_bracket_recovery_pass()

    async def _run_watchdog_analysis(self):
        """Run watchdog to detect and heal invariant violations."""
        # Collect all positions and orders
        all_positions = [self._position_to_dict(
            p) for p in self._positions_by_symbol.values()]

        all_orders = []
        # Iterate all symbols we know about
        known_symbols = set(self._positions_by_symbol.keys()) | set(
            self._orders_snapshot_state.keys())
        for sym in known_symbols:
            refs = self.order_index.get_by_symbol(sym)
            all_orders.extend([r.to_dict() for r in refs])

        # Call watchdog with correct API
        recommendations = self.watchdog.analyze(
            open_orders=all_orders,
            positions=all_positions
        )

        # Track violations
        if recommendations:
            now = time.monotonic()
            for rec in recommendations:
                kind = rec.kind  # Changed from rec.violation_kind to rec.kind
                symbol = rec.symbol
                self._metrics["watchdog_violations"] += 1
                self._metrics["watchdog_violations_by_kind"][kind] = \
                    self._metrics["watchdog_violations_by_kind"].get(
                        kind, 0) + 1

                # E-004: Throttle watchdog logs to prevent spam
                # Same (symbol, kind) violation should not log more than once per 30s
                throttle_key = (symbol, kind)
                last_log = self._watchdog_log_throttle.get(throttle_key, 0)
                should_log = (
                    now - last_log) >= self._watchdog_log_throttle_sec

                if should_log:
                    self._watchdog_log_throttle[throttle_key] = now
                    logger.warning(
                        f"WATCHDOG_VIOLATION_DETECTED",
                        extra={"symbol": symbol,
                               "kind": kind, "recommendation": rec}
                    )

                # Apply runtime-level actions based on watchdog recommendation
                action = getattr(rec, "action", None)

                # HOTFIX: Disable SUPPRESS_BRACKETS - it's too aggressive
                # Instead, allow brackets to be created to FIX the violation
                if action == WatchdogAction.SUPPRESS_BRACKETS:
                    # E-004: Only log if not throttled
                    if should_log:
                        logger.warning(
                            "[ExecPosV2] WATCHDOG_VIOLATION_DETECTED (suppression disabled)",
                            extra={"symbol": symbol, "kind": kind,
                                   "note": "Brackets will be created to heal violation"}
                        )
                    # Force snapshot refresh to ensure we have current state
                    await self._request_orders_snapshot(symbol)
                elif action == WatchdogAction.FORCE_SNAPSHOT:
                    if should_log:
                        logger.info(
                            "[ExecPosV2] WATCHDOG_REQUEST_SNAPSHOT_REFRESH",
                            extra={"symbol": symbol}
                        )
                    await self._request_orders_snapshot(symbol)

    def _position_to_dict(self, pos: PositionState) -> Dict[str, Any]:
        leverage_used = None
        sl_pct = None
        tp_rr = None
        try:
            # LEVERAGE-FIX: Use cached API leverage with fallback to config
            cached_lev = self._leverage_by_symbol.get(pos.symbol)
            if cached_lev and cached_lev > 0:
                leverage_used = float(cached_lev)
            else:
                leverage_used = resolve_effective_leverage(
                    pos.symbol, self.config)
            if self._ep_cfg:
                sl_pct_val, tp_rr_val = compute_sl_tp_from_roi(
                    self._ep_cfg, pos.symbol, leverage_used)
                sl_pct = sl_pct_val
                tp_rr = tp_rr_val
        except Exception:
            pass

        target_sl_price = None
        target_tp_price = None
        try:
            entry = float(pos.avg_entry_price)
            if entry > 0 and sl_pct and tp_rr:
                if pos.side == "LONG":
                    target_sl_price = entry * (1 - sl_pct)
                    target_tp_price = entry * (1 + sl_pct * tp_rr)
                elif pos.side == "SHORT":
                    target_sl_price = entry * (1 + sl_pct)
                    target_tp_price = entry * (1 - sl_pct * tp_rr)
        except Exception:
            pass

        return {
            "symbol": pos.symbol,
            "qty": pos.qty,
            "side": pos.side,
            "position_size": pos.qty,
            "direction": pos.side,
            "entry_price": pos.avg_entry_price,
            "avg_entry_price": pos.avg_entry_price,
            "realized_pnl": pos.realized_pnl,
            "unrealized_pnl": pos.unrealized_pnl,
            "open_time": pos.open_time,
            "last_update_time": pos.last_update_time,
            "leverage_used": leverage_used,
            "sl_pct": sl_pct,
            "tp_rr": tp_rr,
            "target_sl_price": target_sl_price,
            "target_tp_price": target_tp_price,
        }

    def _is_brackets_suppressed(self, symbol: str) -> bool:
        """
        Check if brackets are suppressed for the symbol.
        Currently always returns False as suppression is disabled.
        """
        return False

    def _ensure_guard_loop_running(self) -> None:
        """Start guard loop when we have any non-flat positions."""
        if self._guard_loop_running:
            return
        if not any(abs(p.qty) > 0 for p in self._positions_by_symbol.values()):
            return
        self._guard_loop_running = True
        loop = self.async_manager.get_async_loop()
        coro = self._guard_loop()
        if loop:
            try:
                self._guard_loop_task = loop.create_task(coro)
            except Exception:
                self._guard_loop_task = None
        else:
            self._guard_loop_task = asyncio.create_task(coro)

    def _maybe_stop_guard_loop(self) -> None:
        """Stop guard loop when all positions are flat."""
        if any(abs(p.qty) > 0 for p in self._positions_by_symbol.values()):
            return
        self._guard_loop_running = False
        if self._guard_loop_task and not self._guard_loop_task.done():
            self._guard_loop_task.cancel()
        self._guard_loop_task = None

    async def _guard_loop(self) -> None:
        """Periodic invariant checks without hitting REST."""
        while self._guard_loop_running:
            try:
                await self._run_guard_iteration()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("ExecPosV2 guard loop iteration error",
                               exc_info=True)
            await asyncio.sleep(self._guard_loop_interval_sec)

    async def _run_guard_iteration(self) -> None:
        active_positions = {
            sym: pos for sym, pos in self._positions_by_symbol.items() if abs(pos.qty) > 0
        }
        if not active_positions:
            self._guard_loop_running = False
            return

        # DUPID-FIX-5: If any symbol is awaiting_snapshot, skip entire guard iteration
        # This prevents guard loop from evaluating other symbols while waiting for snapshot sync
        any_awaiting = any(
            self._bracket_status.get(sym, BracketStatus()).awaiting_snapshot
            for sym in active_positions.keys()
        )
        if any_awaiting:
            logger.debug(
                f"[ExecPosV2] GUARD_LOOP_SKIP_AWAITING_SNAPSHOT - waiting for snapshot sync"
            )
            return

        for symbol, pos in active_positions.items():
            try:
                # 1. Check snapshot freshness
                if not self._is_orders_snapshot_fresh(symbol):
                    logger.debug(
                        f"[ExecPosV2] GUARD_LOOP_SNAPSHOT_STALE symbol={symbol} - requesting refresh")
                    # Trigger refresh (throttled by _request_orders_snapshot logic)
                    await self._request_orders_snapshot(symbol)
                    # Skip evaluation this time, wait for snapshot
                    continue

                # 2. Check guard interval
                last_ts = self._last_guard_recovery_ts.get(symbol, 0.0)
                now = time.monotonic()
                if now - last_ts < self._guard_recovery_interval_sec:
                    continue

                # 3. Evaluate
                await self._evaluate_brackets(symbol, pos, reason="guard_loop")
                self._last_guard_recovery_ts[symbol] = time.monotonic()

                # 4. Throttle between symbols to prevent burst load (User request)
                await asyncio.sleep(0.2)

            except Exception as e:
                logger.error(
                    f"[ExecPosV2] Error in guard loop for {symbol}: {e}", exc_info=True)
                # Continue to next symbol to ensure isolation

    def _ensure_position_polling_running(self) -> None:
        """Start position polling when we have any positions or orders."""
        if self._position_polling_running:
            return
        self._position_polling_running = True
        loop = self.async_manager.get_async_loop()
        coro = self._position_polling_loop()
        if loop:
            try:
                self._position_polling_task = loop.create_task(coro)
            except Exception:
                self._position_polling_task = None
        else:
            self._position_polling_task = asyncio.create_task(coro)

    def _maybe_stop_position_polling(self) -> None:
        """Stop position polling when no positions and no orders."""
        if self._positions_by_symbol or any(self.order_index.get_by_symbol(s) for s in self._orders_snapshot_state.keys()):
            return
        self._position_polling_running = False
        if self._position_polling_task and not self._position_polling_task.done():
            self._position_polling_task.cancel()
        self._position_polling_task = None

    async def _position_polling_loop(self) -> None:
        """Periodic position polling to ensure we have fresh position data."""
        while self._position_polling_running:
            try:
                await self._run_position_poll()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("ExecPosV2 position polling iteration error",
                               exc_info=True)
            await asyncio.sleep(self._position_polling_interval_sec)

    async def _run_position_poll(self) -> None:
        """Poll positions from exchange to ensure freshness."""
        now = time.monotonic()
        if now - self._last_position_poll_ts < self._position_polling_interval_sec:
            return

        self._last_position_poll_ts = now

        # Request position snapshot if we have a hook
        if self._position_snapshot_hook:
            try:
                logger.debug("[ExecPosV2] POSITION_POLL_REQUEST")
                await self._position_snapshot_hook()
            except Exception as e:
                logger.warning(f"[ExecPosV2] POSITION_POLL_ERROR: {e}")
        else:
            logger.debug("[ExecPosV2] POSITION_POLL_SKIP - no hook configured")

    def _snapshot_allows_brackets(self, symbol: str, reason: str) -> tuple[bool, Optional[str]]:
        """
        Check if snapshot state allows bracket evaluation.
        Returns (allowed, reason_if_not_allowed).

        FIX-SNAPSHOT-BLOCKING: trade_executed should be fail-open to allow immediate
        bracket placement after fills. Only block periodic checks (guard_loop, account_update_sync).
        """
        if self._is_brackets_suppressed(symbol):
            return False, "watchdog_suppressed"

        snapshot_state = self._orders_snapshot_state.get(symbol, "UNKNOWN")
        has_snapshot_ts = symbol in self._last_orders_snapshot_ts

        # Check freshness
        if snapshot_state == "FRESH" and not self._is_orders_snapshot_fresh(symbol):
            snapshot_state = "STALE"
            self._orders_snapshot_state[symbol] = "STALE"

        # FIX-SNAPSHOT-BLOCKING: trade_executed and polling fills are ALWAYS fail-open
        # Rationale: When a fill comes, we MUST place brackets immediately, regardless of snapshot state.
        # Waiting for snapshot could delay brackets by seconds, leaving position unprotected.
        # The bracket plan will be evaluated with whatever orders we currently know about.
        if reason in ("trade_executed", "async_polling_fill"):
            if snapshot_state == "UNKNOWN":
                logger.debug(
                    f"[ExecPosV2] SNAPSHOT_FAIL_OPEN symbol={symbol} reason={reason} "
                    f"snapshot_state={snapshot_state} has_ts={has_snapshot_ts}"
                )
            return True, None

        # Fail-closed for periodic checks (guard_loop, account_update_sync)
        if snapshot_state != "FRESH":
            return False, f"snapshot_state={snapshot_state}"

        return True, None

    def _build_bracket_context(self, symbol: str, position: PositionState, reason: str) -> Optional[BracketEvalContext]:
        """Build context for bracket evaluation."""
        # R2-CHURN-FIX: Universal throttle for ALL bracket reasons (not just account_update_sync)
        # This prevents excessive CANCEL/PLACE cycles from guard_loop (1s) and trade_executed events
        last_ts = self._last_brackets_apply_ts.get(symbol, 0)
        now = time.time()
        elapsed = now - last_ts

        # trade_executed gets very short throttle (0.1s) for responsive bracket placement
        # guard_loop and account_update_sync use full throttle (5s) to reduce churn
        effective_throttle = 0.1 if reason == "trade_executed" else self._bracket_throttle_sec

        if elapsed < effective_throttle:
            self._metrics["brackets_throttled"] += 1
            logger.debug(
                f"[ExecPosV2] BRACKETS_THROTTLED symbol={symbol} reason={reason} "
                f"elapsed={elapsed:.1f}s < throttle={effective_throttle}s"
            )
            return None

        cfg = self._get_bracket_cfg(symbol)
        if not cfg.enabled:
            return None

        return BracketEvalContext(
            symbol=symbol,
            position=position,
            cfg=cfg,
            reason=reason
        )

    def _get_order_views(self, symbol: str) -> List[BracketOrderView]:
        """Convert raw open orders to OrderView objects."""
        refs = self.order_index.get_by_symbol(symbol)
        raw_orders = [r.to_dict() for r in refs]
        # Use shared converter which handles cycle_id parsing and normalization
        return normalize_orders(raw_orders)

    async def _evaluate_and_apply_brackets_for_symbol(self, ctx: BracketEvalContext) -> None:
        """Evaluate and apply brackets using the provided context."""
        symbol = ctx.symbol
        position = ctx.position
        reason = ctx.reason
        cfg = ctx.cfg

        # R2-ORPHAN-FIX: Handle FLAT position orphan cleanup
        if position.side not in ("LONG", "SHORT"):
            # Position is FLAT - check for orphan brackets and cancel them
            await self._cleanup_orphan_brackets_for_flat(symbol)
            return

        # EXEC-R2-K: Validate avg_entry_price before creating PositionView
        # E-004 invariant: qty > 0 requires avg_entry_price > 0
        entry_price_raw = position.avg_entry_price or 0
        if abs(position.qty) > POSITION_ZERO_TOLERANCE and entry_price_raw <= 0:
            # Fail-closed: log WARNING, skip bracket evaluation this cycle
            # Watchdog/next TRADE_EXECUTED/snapshot may recover
            logger.warning(
                f"BRACKETS_SKIPPED_NO_VALID_ENTRY_PRICE: {symbol} qty={position.qty:.4f}, "
                f"avg_entry_price={entry_price_raw}. Cannot create PositionView. "
                f"Skipping bracket evaluation this cycle (watchdog may recover).",
                extra={
                    "symbol": symbol,
                    "qty": position.qty,
                    "avg_entry_price": entry_price_raw,
                    "side": position.side,
                    "reason": reason,
                    "error_code": "E-004"
                }
            )
            self._metrics.setdefault("brackets_skipped_no_entry_price", 0)
            self._metrics["brackets_skipped_no_entry_price"] += 1
            # Do NOT raise exception - allow runtime to continue
            # Watchdog/snapshot/next fill may provide valid entry_price
            return

        # Build PositionView
        pos_view = BracketPositionView(
            symbol=symbol,
            side=position.side,
            qty=Decimal(abs(position.qty)),
            avg_entry_price=Decimal(entry_price_raw),  # Now guaranteed > 0
            realized_pnl=Decimal(position.realized_pnl or 0),
            unrealized_pnl=Decimal(position.unrealized_pnl or 0),
            update_ts=position.last_update_time or time.time(),
            cycle_id=position.cycle_id,  # R2-D: Include cycle_id for bracket filtering
        )

        # Map open orders to OrderView
        order_views = self._get_order_views(symbol)

        try:
            # Phase 10: Route through contract engine (core planner only)
            # bracket_service no longer passed — uses core planner directly
            plan = compute_bracket_plan_from_views(
                pos_view=pos_view,
                order_views=order_views,
                cfg=cfg,
                symbol=symbol,
                side=position.side,
            )
            if plan is None:
                return

            # R3-C2: Log BRACKET_EVAL_SNAPSHOT for replay analysis
            try:
                open_brackets_list = [
                    {
                        "orderId": o.order_id,
                        "side": o.side,
                        "type": o.order_type,
                        "qty": float(o.qty),
                        "price": float(o.price) if o.price else (float(o.stop_price) if o.stop_price else 0.0),
                        "clientOrderId": o.client_order_id
                    }
                    for o in order_views
                ]

                bracket_plan_list = [
                    {
                        "action_type": a.action_type,
                        "qty": float(a.qty) if a.qty is not None else None,
                        "price": float(a.price) if a.price is not None else None,
                        "why": a.why
                    }
                    for a in plan.actions
                ]

                logging_v2.log_bracket_eval_snapshot(
                    symbol=symbol,
                    side=position.side,
                    position_qty=float(position.qty),
                    position_cycle_id=position.cycle_id or 0,
                    snapshot_state=self._orders_snapshot_state.get(
                        symbol, "UNKNOWN"),
                    open_brackets=open_brackets_list,
                    bracket_plan=bracket_plan_list
                )
            except Exception as e:
                logger.debug(f"Failed to log BRACKET_EVAL_SNAPSHOT: {e}")

        except Exception:
            logger.warning("BracketService evaluation failed",
                           exc_info=True, extra={"symbol": symbol})
            return

        self._metrics["brackets_evaluated"] += 1
        if plan.severity in ("WARN", "ALERT"):
            self._metrics["brackets_alerts"] += 1

        actions = [a.action_type for a in plan.actions]
        logging_v2.log_runtime_event(
            event_kind="BRACKETS",
            symbol=symbol,
            action="plan",
            result=plan.severity.lower(),
            why=plan.why,
            extra={"actions": actions},
        )

        # Execute plan (fail-closed)
        try:
            await self._apply_bracket_plan(symbol, position, plan, reason=reason)
            # TASK 3: Update throttle timestamp after successful bracket application
            self._last_brackets_apply_ts[symbol] = time.time()
        except Exception:
            logger.error("Bracket plan application failed", exc_info=True, extra={
                         "symbol": symbol, "reason": reason})
            # R3-D1: Clear in_flight on exception
            if symbol in self._bracket_status:
                self._bracket_status[symbol].in_flight = False

    async def _evaluate_brackets(self, symbol: str, position: PositionState, *, reason: str = "runtime_eval") -> None:
        """
        Invoke BracketService in observe-only mode. No adapter/guardian mutations.
        """
        # DUPID-FIX-3: Skip guard_loop bracket evaluation until recovery completes.
        # This prevents guard_loop from creating duplicate brackets while recovery
        # is still waiting for FRESH snapshot state.
        if not self._recovery_completed and reason == "guard_loop":
            logger.debug(
                f"[ExecPosV2] BRACKETS_SKIP_RECOVERY_PENDING symbol={symbol} reason={reason}"
            )
            return

        allowed, rejection_reason = self._snapshot_allows_brackets(
            symbol, reason)
        if not allowed:
            if rejection_reason != "watchdog_suppressed":
                logging_v2.log_runtime_event(
                    event_kind="BRACKETS",
                    symbol=symbol,
                    action="skip",
                    result="snapshot_blocked",
                    why=rejection_reason or "unknown",
                    extra={"reason": reason},
                )
            else:
                logger.warning(
                    f"[ExecPosV2] BRACKETS_SUPPRESSED symbol={symbol} reason=watchdog")
            return

        ctx = self._build_bracket_context(symbol, position, reason)
        if ctx is None:
            return

        await self._evaluate_and_apply_brackets_for_symbol(ctx)

    async def _cleanup_orphan_brackets_for_flat(self, symbol: str) -> None:
        """
        R2-ORPHAN-FIX: Cancel orphan brackets when position is FLAT.
        Phase 11: Uses aggregator_oco.cleanup.plan_orphan_cleanup (no BracketService).
        """
        order_views = self._get_order_views(symbol)
        logger.info(
            f"[ExecPosV2] ORPHAN_CLEANUP_CHECK symbol={symbol} order_views_count={len(order_views)}")

        if not order_views:
            logger.debug(
                f"[ExecPosV2] ORPHAN_CLEANUP_SKIP symbol={symbol} - no orders")
            return

        # Phase 11: Use cleanup module instead of BracketService
        plan = plan_orphan_cleanup(symbol, order_views)
        logger.info(
            f"[ExecPosV2] ORPHAN_CLEANUP_PLAN symbol={symbol} actions_count={len(plan.actions)}")

        if not plan.actions:
            logger.debug(
                f"[ExecPosV2] ORPHAN_CLEANUP_SKIP symbol={symbol} - no orphan actions")
            return

        # Use _apply_bracket_plan for consistent retry logic and error handling
        # Create a virtual FLAT position for the plan
        from .position_state import PositionState
        flat_position = PositionState(symbol=symbol, qty=0.0, side="FLAT")

        await self._apply_bracket_plan(symbol, flat_position, plan, reason="orphan_cleanup")

    async def _cleanup_brackets_for_position_size_change(self, symbol: str, new_state: PositionState) -> None:
        """
        R2-POSITION-SIZE-FIX: Cancel brackets that become inappropriate due to position size changes.
        Phase 11: Uses aggregator_oco.cleanup.plan_position_size_cleanup (no BracketService).
        """
        # Skip if position is too small or flat
        if abs(new_state.qty) < POSITION_ZERO_TOLERANCE:
            return

        order_views = self._get_order_views(symbol)
        if not order_views:
            return

        cfg = self._get_bracket_cfg(symbol)
        if not cfg.enabled:
            return

        # Get entry price for calculations
        entry_price = new_state.avg_entry_price or 0
        if entry_price <= 0:
            logger.debug(
                f"[ExecPosV2] POSITION_SIZE_CLEANUP_SKIP: No valid entry price for {symbol}")
            return

        plan = plan_position_size_cleanup(
            symbol, order_views, Decimal(
                str(new_state.qty)), Decimal(str(entry_price)), cfg
        )

        logger.info(
            f"[ExecPosV2] POSITION_SIZE_CLEANUP_PLAN symbol={symbol} actions_count={len(plan.actions)}")

        if not plan.actions:
            logger.debug(
                f"[ExecPosV2] POSITION_SIZE_CLEANUP_SKIP symbol={symbol} - no inappropriate brackets")
            return

        # Use _apply_bracket_plan for consistent retry logic and error handling
        await self._apply_bracket_plan(symbol, new_state, plan, reason="position_size_cleanup")

    async def _handle_reverse_cleanup(self, symbol: str, new_state: PositionState) -> None:
        """
        R2-B: Detect side flip (LONG→SHORT or SHORT→LONG) and cancel old side brackets.
        Phase 11: Uses aggregator_oco.cleanup.plan_reverse_cleanup (no BracketService).
        """
        prev_state = self._prev_positions_by_symbol.get(symbol)

        # Only proceed if we have prev state and both are LONG/SHORT
        if not prev_state:
            return

        if prev_state.side not in ("LONG", "SHORT") or new_state.side not in ("LONG", "SHORT"):
            return

        # Detect reverse: side changed
        if prev_state.side == new_state.side:
            return

        # Reverse detected!
        logger.info(
            f"[ExecPosV2] REVERSE_DETECTED symbol={symbol} "
            f"prev_side={prev_state.side} new_side={new_state.side} "
            f"prev_qty={prev_state.qty} new_qty={new_state.qty}"
        )

        order_views = self._get_order_views(symbol)
        # Phase 11: Use cleanup module instead of BracketService
        plan = plan_reverse_cleanup(
            symbol, prev_state.side, new_state.side, order_views
        )

        if not plan.actions:
            return

        cancelled_count = 0
        for action in plan.actions:
            if action.action == "CANCEL":
                order_id = action.order_ref or action.client_order_id
                logger.info(
                    f"[ExecPosV2] CANCEL_OLD_BRACKET symbol={symbol} "
                    f"reverse={prev_state.side}→{new_state.side} "
                    f"order_id={order_id} reason={action.why}"
                )
                try:
                    await self.execution_service.cancel_order(
                        symbol=symbol,
                        order_id=action.order_ref,
                        client_order_id=action.client_order_id,
                    )
                    cancelled_count += 1
                    # R2-B: Update local mirror after CANCEL to reflect exchange state
                    self._remove_order_from_mirror(symbol, action.order_ref)
                except Exception as exc:
                    logger.warning(
                        f"[ExecPosV2] Failed to cancel old bracket during reverse: {exc}",
                        extra={"symbol": symbol, "order_id": order_id}
                    )

        if cancelled_count > 0:
            logger.info(
                f"[ExecPosV2] REVERSE_CLEANUP_COMPLETE symbol={symbol} "
                f"cancelled_brackets={cancelled_count}"
            )
            # Force snapshot refresh to sync mirror with exchange
            await self._request_orders_snapshot(symbol, force=True)

    async def _apply_bracket_plan(
        self,
        symbol: str,
        position: PositionState,
        plan: BracketPlan,
        reason: str,
    ) -> None:
        """
        Execute BracketPlan actions via ExecutionService or ExecutorPoolV2.
        Includes retry logic for rate limits.
        """
        # R3-D1: Guard-loop anti-double-apply protection
        status = self._bracket_status.get(symbol)
        if not status:
            status = BracketStatus()
            self._bracket_status[symbol] = status

        # R3-D1 FIX: Block guard_loop AND account_update_sync when awaiting_snapshot
        low_priority_reasons = ("guard_loop", "account_update_sync")
        if (status.in_flight or status.awaiting_snapshot) and reason in low_priority_reasons:
            elapsed = time.time() - status.last_started_ts
            logger.info(
                f"[ExecPosV2] SKIP_BRACKETS_LOW_PRIORITY symbol={symbol} "
                f"blocked_reason={reason} in_flight_reason={status.last_reason} dt={elapsed:.3f}s "
                f"in_flight={status.in_flight} awaiting_snapshot={status.awaiting_snapshot}"
            )
            self._metrics.setdefault(
                "brackets_skipped_guard_loop_in_flight", 0)
            self._metrics["brackets_skipped_guard_loop_in_flight"] += 1
            return

        # Mark in_flight, record reason and timestamp
        status.in_flight = True
        status.last_reason = reason
        status.last_started_ts = time.time()

        # DIAGNOSTIC: Log full bracket plan details
        logger.info(
            f"[ExecPosV2] APPLY_BRACKETS symbol={symbol} reason={reason} "
            f"actions_count={len(plan.actions)} "
            f"actions={[(a.action_type, getattr(a, 'price', None)) for a in plan.actions]}"
        )

        # RC-1 FIX: Early-exit when plan has no actions
        # This prevents unnecessary adapter calls and log noise
        if not plan.actions:
            logger.debug(
                f"[ExecPosV2] NO_BRACKET_ACTIONS symbol={symbol} reason={reason} - brackets_ok"
            )
            status.in_flight = False
            return

        actions_summary = []
        side = position.side
        exit_side = "SELL" if side == "LONG" else (
            "BUY" if side == "SHORT" else None)

        logger.info(
            f"[ExecPosV2] APPLY_BRACKETS position_side={side} exit_side={exit_side} qty={position.qty}"
        )

        placed_orders = []
        place_actions: List[Any] = []

        # RC-1 FIX: REMOVED _cancel_existing_close_brackets() call
        # The bracket engine (compute_bracket_plan_from_views) already handles:
        # - Detecting existing TP/SL via get_active_sl/get_active_tp
        # - Generating CANCEL actions only for excess/orphan brackets
        # - Returning empty actions when brackets are already correct
        # Pre-canceling ALL brackets was causing infinite CANCEL→PLACE churn.
        #
        # async def _cancel_existing_close_brackets():
        #     """Best-effort cancel existing closePosition SL/TP to avoid duplicates."""
        #     ...
        # await _cancel_existing_close_brackets()  # REMOVED - causes bracket churn

        for action in plan.actions:
            actions_summary.append(action.action_type)

            # DIAGNOSTIC: Log each action processing
            logger.info(
                f"[ExecPosV2] BRK_ACTION symbol={symbol} action_type={action.action_type} "
                f"price={getattr(action, 'price', None)} qty={getattr(action, 'qty', None)}"
            )

            # Helper to execute with retry
            # FIX-BRACKET-RETRY: Unified retry logic for both ExecutorPool and legacy paths
            async def _execute_with_retry(act_type, **kwargs):
                max_retries = 3
                base_backoff_ms = 100  # Start with 100ms, exponential backoff

                for i in range(max_retries + 1):
                    res = None

                    if self._use_executor_pool:
                        loop = asyncio.get_running_loop()
                        res = await loop.run_in_executor(
                            self._executor_thread_pool,
                            lambda: self.executor_pool.execute_bracket(
                                symbol=symbol,
                                action_type=act_type,
                                side=exit_side,
                                **kwargs
                            )
                        )
                    else:
                        # Legacy path with retry support
                        try:
                            if act_type == "CANCEL":
                                res = await self.execution_service.cancel_order(
                                    symbol=symbol,
                                    order_id=kwargs.get("order_id"),
                                    client_order_id=kwargs.get(
                                        "client_order_id")
                                )
                            else:
                                # Map PLACE_SL/TP to place_order
                                o_type = "STOP_MARKET" if act_type == "PLACE_SL" else "TAKE_PROFIT_MARKET"
                                res = await self.execution_service.place_order(
                                    symbol=symbol,
                                    side=exit_side,
                                    order_type=o_type,
                                    quantity=None,
                                    stop_price=kwargs.get("stop_price"),
                                    client_order_id=kwargs.get(
                                        "client_order_id"),
                                    reduce_only=False,
                                    close_position=True
                                )
                        except Exception as e:
                            res = {"success": False, "error": str(
                                e), "error_kind": "EXCEPTION"}

                    # Check if we should retry
                    if res and not res.get("success"):
                        error = res.get("error", "")
                        error_kind = res.get("error_kind", "")

                        # Retryable errors: Rate limit, Network errors, Timeouts (not ADAPTER_ERROR_TIMEOUT which needs snapshot)
                        is_rate_limited = error == "Rate limited" or "-429" in str(
                            error)
                        is_network_error = error_kind in (
                            "ADAPTER_ERROR_NETWORK", "EXCEPTION") or "network" in str(error).lower()
                        is_retryable_timeout = "timeout" in str(
                            error).lower() and error_kind != "ADAPTER_ERROR_TIMEOUT"
                        is_duplicate_id = "-4116" in str(error) or "duplicated" in str(
                            error).lower() or str(res.get("error_code", "")).strip() == "-4116"

                        # DUPID-FIX-4: For bracket orders (PLACE_SL/PLACE_TP), -4116 means order already exists
                        # This is effectively SUCCESS - the bracket is in place, just not in our local index
                        # Do NOT retry with new clientOrderId as that would create duplicates!
                        # Instead, trigger snapshot refresh to sync order_index with exchange state.
                        if is_duplicate_id and act_type in ("PLACE_SL", "PLACE_TP"):
                            logger.warning(
                                f"[ExecPosV2] BRACKET_ALREADY_EXISTS symbol={symbol} action={act_type} "
                                f"clientOrderId={kwargs.get('client_order_id')} - treating as success, requesting snapshot"
                            )
                            # Mark snapshot as stale to force refresh
                            self._orders_snapshot_state[symbol] = "STALE"
                            self._last_orders_snapshot_ts[symbol] = 0.0
                            # Set awaiting_snapshot to prevent further bracket evaluations
                            status.awaiting_snapshot = True
                            # Request fresh snapshot to sync order_index (fire and forget)
                            asyncio.create_task(
                                self._request_orders_snapshot(symbol, force=True))
                            # Return success since bracket exists on exchange
                            return {"success": True, "already_exists": True, "client_order_id": kwargs.get("client_order_id")}

                        # For non-bracket orders, retry with new clientOrderId (original behavior)
                        if is_duplicate_id and i < max_retries:
                            base_cid = kwargs.get("client_order_id") or "cid"
                            new_cid = f"{base_cid}_R{i+1}"
                            # Binance Futures limit 36 chars; truncate defensively
                            kwargs["client_order_id"] = new_cid[:32]
                            logger.warning(
                                f"[ExecPosV2] BRACKET_DUP_CID_RETRY symbol={symbol} action={act_type} "
                                f"retry={i+1}/{max_retries} error={error[:50]} new_cid={kwargs['client_order_id']}"
                            )
                            await asyncio.sleep(base_backoff_ms / 1000.0)
                            continue

                        if (is_rate_limited or is_network_error or is_retryable_timeout) and i < max_retries:
                            wait_ms = res.get(
                                "retry_after_ms", base_backoff_ms * (2 ** i))
                            logger.warning(
                                f"[ExecPosV2] BRACKET_RETRY symbol={symbol} action={act_type} "
                                f"retry={i+1}/{max_retries} wait={wait_ms}ms error={error[:50]}"
                            )
                            await asyncio.sleep(wait_ms / 1000.0)
                            continue

                    return res or {"success": False, "error": "No result"}

                return {"success": False, "error": "Max retries exceeded"}

            if action.action_type == "CANCEL":
                result = await _execute_with_retry(
                    "CANCEL",
                    order_id=action.order_id,
                    client_order_id=action.client_order_id
                )

                # Handle timeout
                if isinstance(result, dict) and result.get("error_kind") == "ADAPTER_ERROR_TIMEOUT":
                    logger.warning(
                        "[ExecPosV2] Timeout canceling bracket for %s order_id=%s, forcing ORDERS_SNAPSHOT",
                        symbol, action.order_id
                    )
                    self._orders_snapshot_state[symbol] = "UNKNOWN"
                    self._last_orders_snapshot_ts[symbol] = 0.0
                    await self._request_orders_snapshot(symbol, force=True)
                    status.in_flight = False
                    status.awaiting_snapshot = True
                    continue

                # R2-B: Update local mirror
                if result.get("success") or (isinstance(result, dict) and result.get("error") == "UNKNOWN_ORDER"):
                    self._remove_order_from_mirror(symbol, action.order_id)

            elif action.action_type in ("PLACE_SL", "PLACE_TP") and exit_side:
                place_actions.append(action)

            elif action.action_type == "ADJUST" and exit_side:
                # Cancel first
                if action.order_id:
                    await _execute_with_retry(
                        "CANCEL",
                        order_id=action.order_id,
                        client_order_id=None
                    )
                    self._remove_order_from_mirror(symbol, action.order_id)

                # Then place
                qty = float(action.qty) if action.qty is not None else abs(
                    position.qty)
                client_order_id = make_bracket_client_order_id(
                    symbol, action.action_type, exit_side, qty, action.price, position=position)

                # Determine type based on reason code
                sub_type = "PLACE_SL" if action.reason_code in (
                    "MISSING_SL", "STALE_LEVELS") else "PLACE_TP"

                result = await _execute_with_retry(
                    sub_type,
                    stop_price=str(
                        action.price) if action.price is not None else None,
                    client_order_id=client_order_id
                )

                # Handle timeout
                if isinstance(result, dict) and result.get("error_kind") == "ADAPTER_ERROR_TIMEOUT":
                    logger.warning(
                        "[ExecPosV2] Timeout placing bracket for %s, forcing ORDERS_SNAPSHOT", symbol)
                    self._orders_snapshot_state[symbol] = "UNKNOWN"
                    self._last_orders_snapshot_ts[symbol] = 0.0
                    await self._request_orders_snapshot(symbol, force=True)
                    status.in_flight = False
                    status.awaiting_snapshot = True
                    continue

                if not result.get("success"):
                    continue

                # Mirror update
                order_id_placed = result.get(
                    "order_id") or result.get("orderId")
                if order_id_placed:
                    order_type = "STOP_MARKET" if sub_type == "PLACE_SL" else "TAKE_PROFIT_MARKET"
                    self.order_index.upsert_from_open(
                        rid=f"brk_adj_{order_id_placed}_{time.time()}",
                        idempotent_key=None,
                        clientOrderId=result.get(
                            "client_order_id") or client_order_id,
                        symbol=symbol,
                        side=exit_side,
                        order_type=order_type,
                        price=float(
                            action.price) if action.price is not None else None,
                        quantity=0.0,
                        stop_price=float(
                            action.price) if action.price is not None else None,
                        reduce_only=False,
                        close_position=True,
                    )
                    self.order_index.attach_exchange_id(
                        clientOrderId=result.get(
                            "client_order_id") or client_order_id,
                        exchangeOrderId=str(order_id_placed)
                    )
                    logger.info(
                        f"[ExecPosV2] MIRROR_UPDATE_ADD (ADJUST) symbol={symbol} order_id={order_id_placed} "
                        f"client_order_id={result.get('client_order_id') or client_order_id} closePosition=true"
                    )

                placed_orders.append(
                    {
                        "order_id": order_id_placed,
                        "client_order_id": result.get("client_order_id") or client_order_id,
                        "order_type": "STOP_MARKET" if sub_type == "PLACE_SL" else "TAKE_PROFIT_MARKET",
                        "side": exit_side,
                        "close_position": True,
                        "price": float(action.price) if action.price is not None else None,
                    }
                )

        # Run deferred PLACE_SL/PLACE_TP concurrently to reduce latency
        if place_actions:
            async def _process_place(action):
                qty = float(action.qty) if action.qty is not None else abs(
                    position.qty)
                client_order_id = make_bracket_client_order_id(
                    symbol, action.action_type, exit_side, qty, action.price, position=position)

                result = await _execute_with_retry(
                    action.action_type,
                    stop_price=str(
                        action.price) if action.price is not None else None,
                    client_order_id=client_order_id
                )
                return action, client_order_id, result

            results = await asyncio.gather(*[_process_place(a) for a in place_actions])

            for action, client_order_id, result in results:
                if isinstance(result, dict) and result.get("error_kind") == "ADAPTER_ERROR_TIMEOUT":
                    logger.warning(
                        "[ExecPosV2] Timeout placing bracket for %s, forcing ORDERS_SNAPSHOT", symbol)
                    self._orders_snapshot_state[symbol] = "UNKNOWN"
                    self._last_orders_snapshot_ts[symbol] = 0.0
                    await self._request_orders_snapshot(symbol, force=True)
                    status.in_flight = False
                    status.awaiting_snapshot = True
                    continue

                if not result.get("success"):
                    continue

                order_id_placed = result.get(
                    "order_id") or result.get("orderId")
                if order_id_placed:
                    order_type = "STOP_MARKET" if action.action_type == "PLACE_SL" else "TAKE_PROFIT_MARKET"
                    self.order_index.upsert_from_open(
                        rid=f"brk_{order_id_placed}_{time.time()}",
                        idempotent_key=None,
                        clientOrderId=result.get(
                            "client_order_id") or client_order_id,
                        symbol=symbol,
                        side=exit_side,
                        order_type=order_type,
                        price=float(
                            action.price) if action.price is not None else None,
                        quantity=0.0,
                        stop_price=float(
                            action.price) if action.price is not None else None,
                        reduce_only=False,
                        close_position=True,
                    )
                    self.order_index.attach_exchange_id(
                        clientOrderId=result.get(
                            "client_order_id") or client_order_id,
                        exchangeOrderId=str(order_id_placed)
                    )
                    logger.info(
                        f"[ExecPosV2] MIRROR_UPDATE_ADD symbol={symbol} order_id={order_id_placed} "
                        f"client_order_id={result.get('client_order_id') or client_order_id} closePosition=true"
                    )

                placed_orders.append(
                    {
                        "order_id": order_id_placed,
                        "client_order_id": result.get("client_order_id") or client_order_id,
                        "order_type": "STOP_MARKET" if action.action_type == "PLACE_SL" else "TAKE_PROFIT_MARKET",
                        "side": exit_side,
                        "close_position": True,
                        "price": float(action.price) if action.price is not None else None,
                    }
                )

        logging_v2.log_runtime_event(
            event_kind="BRACKETS_EXEC",
            symbol=symbol,
            action="apply",
            result=plan.severity.lower(),
            why=f"brackets_{reason}"[:80],
            extra={"actions": actions_summary, "rid": plan.rid},
        )

        # Guardian metadata update (query-only)
        if self.guardian:
            guardian_side = side if side in ("LONG", "SHORT") else "FLAT"
            if placed_orders:
                register = getattr(self.guardian, "register_bracket_set", None)
                if callable(register):
                    res = register(
                        symbol=symbol, side=guardian_side, orders=placed_orders)
                    if hasattr(res, "__await__"):
                        await res
            else:
                clear_fn = getattr(self.guardian, "clear_bracket_set", None)
                if callable(clear_fn):
                    res = clear_fn(symbol=symbol, side=guardian_side)
                    if hasattr(res, "__await__"):
                        await res

        # R3-D1: Mark in_flight=False, awaiting_snapshot=True after plan applied
        status = self._bracket_status.get(symbol)
        if status:
            status.in_flight = False
            status.awaiting_snapshot = True

        # DUPID-FIX-3: If brackets were successfully placed by account_update_sync or guard_loop,
        # mark recovery as completed. This prevents recovery from trying to place the same
        # brackets again with duplicate clientOrderId errors.
        if placed_orders and not reason.startswith("brackets_recovery"):
            if not self._recovery_completed:
                self._recovery_completed = True
                logger.info(
                    f"[ExecPosV2] RECOVERY_SKIPPED_BRACKETS_PLACED: symbol={symbol} reason={reason} "
                    f"placed_count={len(placed_orders)} - marking recovery as completed"
                )

    async def _run_bracket_recovery_pass(self) -> None:
        """
        Single-shot DR/rehydrate recovery using BracketService plans (no loops).

        DUPID-FIX: Wait for all position symbols to have FRESH snapshot state
        before evaluating brackets. This prevents creating duplicate brackets
        when mirror hasn't been updated from snapshot yet.
        """
        if self._recovery_completed:
            return

        # Use the first symbol with position to derive ROI-aware config (best effort)
        first_symbol = None
        if self._positions_by_symbol:
            for pos in self._positions_by_symbol.values():
                if abs(pos.qty) >= 1e-9 and pos.side in ("LONG", "SHORT"):
                    first_symbol = pos.symbol
                    break
        cfg = self._get_bracket_cfg(first_symbol)
        if not cfg.enabled:
            self._recovery_completed = True
            return

        # DUPID-FIX: Check that all symbols with positions have FRESH snapshot state
        # before proceeding with recovery. This prevents duplicate clientOrderId errors.
        symbols_with_positions = [
            pos.symbol for pos in self._positions_by_symbol.values()
            if abs(pos.qty) >= 1e-9 and pos.side in ("LONG", "SHORT")
        ]

        for sym in symbols_with_positions:
            snapshot_state = self._orders_snapshot_state.get(sym, "UNKNOWN")
            if snapshot_state != "FRESH":
                # Not all snapshots are ready yet - wait for next guard_loop cycle
                logger.debug(
                    f"[ExecPosV2] RECOVERY_DEFERRED: symbol={sym} snapshot_state={snapshot_state}, "
                    f"waiting for FRESH state before bracket recovery"
                )
                return  # Don't set _recovery_completed, will retry on next cycle

        # DUPID-FIX-2: Set _recovery_completed = True EARLY to prevent guard_loop
        # from running parallel bracket evaluations while recovery is in progress.
        # This is critical to avoid duplicate clientOrderId errors.
        self._recovery_completed = True
        logger.info(
            "[ExecPosV2] RECOVERY_STARTED: _recovery_completed set to True early to prevent parallel evaluation")

        # Build PositionView list (only non-flat)
        pos_views: List[BracketPositionView] = []
        for pos in self._positions_by_symbol.values():
            if abs(pos.qty) < 1e-9:
                continue
            if pos.side not in ("LONG", "SHORT"):
                continue
            try:
                pos_views.append(
                    BracketPositionView(
                        symbol=pos.symbol,
                        side=pos.side,
                        qty=Decimal(abs(pos.qty)),
                        avg_entry_price=Decimal(pos.avg_entry_price or 0),
                        realized_pnl=Decimal(pos.realized_pnl or 0),
                        unrealized_pnl=Decimal(pos.unrealized_pnl or 0),
                        update_ts=pos.last_update_time or time.time(),
                        cycle_id=pos.cycle_id,  # R2-D: Include cycle_id for bracket filtering
                    )
                )
            except Exception:
                continue

        # Map open orders to OrderView
        order_views: List[BracketOrderView] = []

        # Iterate all symbols in index
        known_symbols = set(self._positions_by_symbol.keys()) | set(
            self._orders_snapshot_state.keys())
        for sym in known_symbols:
            refs = self.order_index.get_by_symbol(sym)
            orders = [r.to_dict() for r in refs]

            for order in orders:
                try:
                    client_order_id_str = str(
                        order.get("client_order_id") or order.get("clientOrderId") or "")
                    # R2-D: Parse cycle_id from clientOrderId
                    # Phase 11: Import from view_types instead of bracket_service
                    from ..aggregator_oco.view_types import parse_cycle_id_from_client_order_id
                    cycle_id_parsed = parse_cycle_id_from_client_order_id(
                        client_order_id_str)

                    order_views.append(
                        BracketOrderView(
                            order_id=str(order.get("order_id")
                                         or order.get("orderId") or ""),
                            client_order_id=client_order_id_str,
                            symbol=order.get("symbol", sym),
                            side=str(order.get("side") or "").upper() or "BUY",
                            order_type=order.get("type") or order.get(
                                "order_type") or "LIMIT",
                            qty=Decimal(str(order.get("quantity") or order.get(
                                "origQty") or order.get("qty") or 0)),
                            price=Decimal(str(order.get("price"))) if order.get(
                                "price") not in (None, "") else None,
                            stop_price=Decimal(str(order.get("stop_price") or order.get(
                                "stopPrice"))) if order.get("stop_price") or order.get("stopPrice") else None,
                            reduce_only=bool(
                                order.get("reduce_only") or order.get("reduceOnly", False)),
                            close_position=bool(
                                order.get("close_position") or order.get("closePosition", False)),
                            status=str(order.get("status") or "NEW"),
                            created_ts=float(order.get("created_ts") or order.get(
                                "time") or time.time()),
                            update_ts=float(order.get("update_ts") or order.get(
                                "updateTime") or time.time()),
                            cycle_id=cycle_id_parsed,
                        )
                    )
                except Exception:
                    continue

        try:
            # Phase 11: Use core planner instead of BracketService.evaluate_all
            # Evaluate each position individually using compute_bracket_plan_from_views
            plans = []
            bracket_cfg = BracketConfig(
                sl_pct=Decimal(str(cfg.sl_pct)),
                tp_rr=Decimal(str(cfg.tp_rr)),
            )
            for pos_view in pos_views:
                symbol_orders = [
                    o for o in order_views if o.symbol == pos_view.symbol]
                try:
                    plan = compute_bracket_plan_from_views(
                        pos_view=pos_view,
                        order_views=symbol_orders,
                        cfg=bracket_cfg,
                        symbol=pos_view.symbol,
                        side=pos_view.side,
                    )
                    if plan.actions:  # Only include plans with actions
                        plans.append(plan)
                except Exception:
                    continue

            # Also check for orphan brackets (symbols with orders but no position)
            order_symbols = set(o.symbol for o in order_views)
            pos_symbols = set(p.symbol for p in pos_views)
            orphan_symbols = order_symbols - pos_symbols
            for orphan_sym in orphan_symbols:
                orphan_orders = [
                    o for o in order_views if o.symbol == orphan_sym]
                orphan_plan = plan_orphan_cleanup(orphan_sym, orphan_orders)
                if orphan_plan.actions:
                    plans.append(orphan_plan)

        except Exception:
            logger.error("Bracket recovery evaluation failed", exc_info=True)
            self._recovery_completed = True
            return

        for plan in plans or []:
            reason = "brackets_recovery"
            if any(a.action in ("ADJUST", "ADJUST_SL", "ADJUST_TP") for a in plan.actions):
                reason = "brackets_recovery_adjust_mismatch"
            elif any(a.action in ("PLACE_SL", "PLACE_TP") for a in plan.actions):
                reason = "brackets_recovery_seed_protection"
            elif plan.side == "FLAT" and plan.actions:
                reason = "brackets_recovery_orphan_cleanup"

            logging_v2.log_runtime_event(
                event_kind="BRACKETS_RECOVERY_PLAN",
                symbol=plan.symbol,
                action="plan",
                result=plan.severity.lower(),
                why=reason[:80],
                extra={"actions": [
                    a.action for a in plan.actions], "rid": plan.rid},
            )

            try:
                pos_state = self._positions_by_symbol.get(
                    plan.symbol) or PositionState(symbol=plan.symbol)
                await self._apply_bracket_plan(plan.symbol, pos_state, plan, reason=reason)
            except Exception:
                logger.error("Bracket recovery application failed",
                             exc_info=True, extra={"symbol": plan.symbol})

        self._recovery_completed = True

    def _get_close_config(self) -> CloseConfig:
        """
        Retrieve close config, preferring typed ExecutionPositionConfig when available.
        Legacy dict path remains as fallback with defaults preserved.
        """
        if self._ep_cfg and getattr(self._ep_cfg, "close", None):
            close_cfg = self._ep_cfg.close
            try:
                return CloseConfig(
                    allow_partial=self._coerce_bool(
                        getattr(close_cfg, "allow_partial", None), True),
                    min_close_qty=self._coerce_float(
                        getattr(close_cfg, "min_close_qty", None), 0.0),
                    max_hold_time_sec=self._coerce_optional_float(
                        getattr(close_cfg, "max_hold_time_sec", None), None),
                    allow_time_exit=self._coerce_bool(
                        getattr(close_cfg, "allow_time_exit", None), True),
                )
            except Exception:
                pass

        cfg_root = self.config.get("execution_position", self.config) if isinstance(
            self.config, dict) else {}
        close_node = {}
        if isinstance(cfg_root, dict):
            manage = cfg_root.get("manage", {})
            if isinstance(manage, dict):
                close_node = manage.get("close", {}) or {}
            close_node = close_node or cfg_root.get("close", {}) or {}

        return CloseConfig(
            allow_partial=self._coerce_bool(
                self._pluck(close_node, "allow_partial"), True),
            min_close_qty=self._coerce_float(
                self._pluck(close_node, "min_close_qty"), 0.0),
            max_hold_time_sec=self._coerce_optional_float(
                self._pluck(close_node, "max_hold_time_sec"), None),
            allow_time_exit=self._coerce_bool(
                self._pluck(close_node, "allow_time_exit"), True),
        )

    @staticmethod
    def _coerce_float(val: Any, default: float) -> float:
        try:
            if val is None:
                return default
            return float(val)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_optional_float(val: Any, default: Optional[float]) -> Optional[float]:
        try:
            if val is None:
                return default
            return float(val)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_bool(val: Any, default: bool) -> bool:
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            lowered = val.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
        try:
            return bool(val)
        except Exception:
            return default

    @staticmethod
    def _pluck(obj: Any, *path: str) -> Any:
        current = obj
        for key in path:
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(key)
                continue
            try:
                current = getattr(current, key)
            except Exception:
                return None
        return current

    def _get_bracket_cfg(self, symbol: Optional[str] = None) -> BracketRulesConfig:
        # Preferred typed config path
        if self._ep_cfg and getattr(self._ep_cfg, "aggregated_oco", None):
            agg = self._ep_cfg.aggregated_oco
            try:
                # LEVERAGE-FIX: Use cached leverage from Binance API (priority)
                # Fallback to config max_leverage only if API leverage not available
                sym = symbol or ""
                cached_lev = self._leverage_by_symbol.get(sym)
                if cached_lev and cached_lev > 0:
                    lev = float(cached_lev)
                    logger.debug(
                        f"[ExecPosV2] BRACKET_CFG: Using cached API leverage={lev} for {sym}")
                else:
                    lev = resolve_effective_leverage(sym, self.config)
                    logger.debug(
                        f"[ExecPosV2] BRACKET_CFG: Using config leverage={lev} for {sym} (API cache miss)")

                sl_pct_price, tp_rr_val = compute_sl_tp_from_roi(
                    self._ep_cfg, sym, lev)
                sl_pct_cfg = sl_pct_price if sl_pct_price else agg.sl_pct
                tp_rr_cfg = tp_rr_val if tp_rr_val else agg.tp_rr

                # LEVERAGE-FIX: Log actual values for debugging ROI calculation
                logger.debug(
                    f"[ExecPosV2] BRACKET_CFG: {sym} lev={lev} sl_pct={sl_pct_cfg:.4f} tp_rr={tp_rr_cfg:.4f}")

                return BracketRulesConfig(
                    enabled=agg.enabled,
                    allow_unprotected_position=agg.allow_unprotected_position,
                    recalc_on_partial_close=agg.recalc_on_partial_close,
                    recalc_on_scale_in=agg.recalc_on_scale_in,
                    ttl_protect_new_bracket_ms=agg.ttl_protect_new_bracket_ms,
                    max_tp_legs=agg.max_tp_legs,
                    max_sl_legs=agg.max_sl_legs,
                    sl_pct=sl_pct_cfg,
                    tp_rr=tp_rr_cfg,
                    recreate_missing_brackets=agg.recreate_missing_brackets,  # R2-E
                )
            except Exception:
                # Fail-closed to legacy path below
                pass

        # Legacy dict path (unchanged defaults)
        cfg_root = self.config.get("execution_position", self.config) if isinstance(
            self.config, dict) else {}
        agg_cfg = cfg_root.get("aggregated_oco", {}) if isinstance(
            cfg_root, dict) else {}
        try:
            return BracketRulesConfig(
                enabled=agg_cfg.get("enabled", True),
                allow_unprotected_position=agg_cfg.get(
                    "allow_unprotected_position", False),
                recalc_on_partial_close=agg_cfg.get(
                    "recalc_on_partial_close", True),
                recalc_on_scale_in=agg_cfg.get("recalc_on_scale_in", True),
                ttl_protect_new_bracket_ms=agg_cfg.get(
                    "ttl_protect_new_bracket_ms", 5000),
                max_tp_legs=agg_cfg.get("max_tp_legs", 1),
                max_sl_legs=agg_cfg.get("max_sl_legs", 1),
                sl_pct=agg_cfg.get("sl_pct", 0.02),
                tp_rr=agg_cfg.get("tp_rr", 2.0),
                recreate_missing_brackets=agg_cfg.get(
                    "recreate_missing_brackets", True),  # R2-E (default=True, fail-closed)
            )
        except Exception:
            return BracketRulesConfig()
