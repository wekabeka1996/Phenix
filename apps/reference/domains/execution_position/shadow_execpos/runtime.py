"""
Shadow ExecPos Runtime V2
=========================

The main entry point and orchestrator for the modular Execution Position domain.
This class composes all the sub-services into a coherent runtime.
"""
from typing import Any, Dict, Optional, List, Callable, Awaitable
import asyncio
import hashlib
import logging
import time
from decimal import Decimal

from apps.reference.domains.execution_position.config import ExecutionPositionConfig, SnapshotConfig
from .async_manager import ExecPosAsyncManager
from .execution_service import ExecutionService
from .watchdog import AggOcoWatchdogService
from .gatekeeper import ExecPosGatekeeper
from .price_enricher import PriceEnricher
from .idempotency import FillIdempotency, EventIdempotency
from .wal_writer import ExecPosWALWriter
from .exposure_bridge import ExposureBridge
from .types import RuntimeEvent, ExecutionCommand, WatchdogAction
from . import logging_v2
from .position_model import PositionState, apply_fill
from dataclasses import replace, dataclass
from .close_flow import CloseFlowService, CloseContext, CloseConfig
from .trailing import TrailingStopService, TrailingState, TrailingConfig
from .bracket_service import (
    BracketService,
    BracketRulesConfig,
    BracketPlan,
    PositionView as BracketPositionView,
    OrderView as BracketOrderView,
)
from vfoundation.apps.reference.domains.execution_position import bracket_aggregator

# Import WAL infrastructure
from vfoundation.dr import wal

logger = logging.getLogger(__name__)


@dataclass
class BracketStatus:
    """Per-symbol state to prevent double-apply of guard_loop vs trade_executed."""
    last_reason: str = ""  # "trade_executed", "guard_loop", etc.
    last_started_ts: float = 0.0  # When _apply_bracket_plan started
    in_flight: bool = False  # True during _apply_bracket_plan execution
    # True after plan applied, False after snapshot confirms orders
    awaiting_snapshot: bool = False


class ExecPosRuntimeV2:
    """
    The modular runtime for Execution Position management.

    This class replaces the monolithic `ExecPosFSM`.
    It is responsible for:
    - Wiring together dependencies.
    - Routing events to appropriate handlers.
    - Managing the lifecycle of the domain (start, stop, hydrate).
    """

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
        self.price_enricher = PriceEnricher()
        self.close_flow_service = CloseFlowService()
        self.trailing_service = TrailingStopService()
        self.bracket_service = BracketService(
            aggregator=bracket_aggregator,
            guardian=guardian,
            watchdog=None,
        )
        self.guardian = guardian

        # State & Logic
        self.fill_idempotency = FillIdempotency()
        self.event_idempotency = EventIdempotency()

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
        self._open_orders_by_symbol: Dict[str, list] = {}
        # "UNKNOWN" | "STALE" | "FRESH"
        self._orders_snapshot_state: Dict[str, str] = {}
        self._trailing_state_by_symbol: Dict[str, TrailingState] = {}
        self._recovery_completed = False
        self._last_orders_snapshot_ts: Dict[str, float] = {}
        self._last_position_snapshot_ts: Dict[str, float] = {}
        self._brackets_suppressed: Dict[str, float] = {}
        self._snapshot_request_hook: Optional[Callable[[
            str], Awaitable[None]]] = None

        # R3-D1: Per-symbol bracket status to prevent double-apply
        self._bracket_status: Dict[str, BracketStatus] = {}

        # E-004: Watchdog log throttling to prevent spam
        # Key: (symbol, kind) -> last_log_ts
        self._watchdog_log_throttle: Dict[tuple, float] = {}
        # Don't log same violation twice within 30s
        self._watchdog_log_throttle_sec = 30.0

        # TASK 3: Throttling state for bracket spam prevention
        self._last_brackets_apply_ts: Dict[str, float] = {}
        # Minimum seconds between bracket evaluations per symbol
        self._bracket_throttle_sec = 3.0
        self._bracket_suppression_sec = 30.0
        self._snapshot_request_interval_sec = 5.0

        # Guard loop state
        self._guard_loop_interval_sec = 1.0
        self._guard_recovery_interval_sec = 5.0
        self._guard_loop_running = False
        self._guard_loop_task: Optional[asyncio.Task] = None
        self._last_guard_recovery_ts: Dict[str, float] = {}
        self._last_snapshot_request_ts: Dict[str, float] = {}

        # Concurrency control
        self._evaluation_lock = asyncio.Lock()

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
            "trailing_evaluations": 0,
            "trailing_exit_signals": 0,
            "brackets_evaluated": 0,
            "brackets_alerts": 0,
            "brackets_throttled": 0,
        }

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
            for order in snapshot["orders"]:
                symbol = order.get("symbol")
                if symbol:
                    if symbol not in self._open_orders_by_symbol:
                        self._open_orders_by_symbol[symbol] = []
                    self._open_orders_by_symbol[symbol].append(order)

    def get_metrics_snapshot(self) -> Dict[str, Any]:
        """Get a complete snapshot of V2 runtime metrics."""
        return self.get_metrics()

    async def start(self) -> None:
        """
        Start the runtime.
        """
        logger.info("Starting ExecPosRuntimeV2...")

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
        # Close any resources if needed
        pass

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
        metrics["open_orders_tracked"] = sum(
            len(orders) for orders in self._open_orders_by_symbol.values())
        metrics["status"] = "healthy"

        # Merge component metrics
        if self.exposure_bridge:
            metrics.update(self.exposure_bridge.get_metrics())

        return metrics

    def _default_emit(self, event_kind: str, payload: Dict[str, Any]) -> None:
        """No-op event emitter for testing."""
        logger.debug(f"Event: {event_kind}")

    def set_snapshot_refresh_hook(self, hook: Callable[[str], Awaitable[None]]) -> None:
        """Register hook to request fresh ORDERS_SNAPSHOT (facade/adapter-backed)."""
        self._snapshot_request_hook = hook

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
                orders_ttl_sec=float(snapshot_cfg.get("orders_ttl_sec", 10.0)),
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

    def _mark_orders_snapshot(self, symbol: str, ts: Optional[float] = None) -> None:
        self._last_orders_snapshot_ts[symbol] = ts or time.monotonic()
        self._orders_snapshot_state[symbol] = "FRESH"

    def _mark_position_snapshot(self, symbol: str, ts: Optional[float] = None) -> None:
        self._last_position_snapshot_ts[symbol] = ts or time.monotonic()

    def _remove_order_from_mirror(self, symbol: str, order_id: str) -> None:
        """
        R2-B: Remove order from local mirror after CANCEL action.

        This ensures tests checking _open_orders_by_symbol see updated state
        without waiting for next ORDERS_SNAPSHOT.

        Args:
            symbol: Trading symbol
            order_id: Exchange order ID to remove
        """
        orders = self._open_orders_by_symbol.get(symbol, [])
        updated_orders = [
            o for o in orders
            if str(o.get("orderId") or o.get("order_id") or "") != str(order_id)
        ]
        self._open_orders_by_symbol[symbol] = updated_orders

        logger.debug(
            f"[ExecPosV2] MIRROR_UPDATE symbol={symbol} "
            f"removed_order={order_id} remaining_orders={len(updated_orders)}"
        )

    async def _request_orders_snapshot(self, symbol: str, *, force: bool = False) -> None:
        """Invoke hook to refresh orders snapshot with per-symbol throttle."""
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
        except Exception:
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

        # Execute via ExecutionService
        result = await self.execution_service.place_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=adjusted_qty,
            price=adjusted_price,
            client_order_id=payload.get("client_order_id"),
            time_in_force=payload.get("tif") or payload.get("time_in_force"),
        )

        if result["success"]:
            self._metrics["execution_success"] += 1
            # Add to open orders
            if symbol not in self._open_orders_by_symbol:
                self._open_orders_by_symbol[symbol] = []
            self._open_orders_by_symbol[symbol].append({
                "order_id": result["order_id"],
                "symbol": symbol,
                "side": side,
                "quantity": adjusted_qty,
                "price": adjusted_price,
                "type": order_type
            })
            # Structured logging
            logging_v2.log_runtime_event(
                event_kind="ENTRY_INTENT",
                symbol=symbol,
                action="executed",
                result="success",
                why="order_placed",
                extra={
                    "order_id": result["order_id"],
                    "side": side,
                    "quantity": str(adjusted_qty),
                    "price": str(adjusted_price) if adjusted_price else None,
                    "order_type": order_type
                }
            )
        else:
            self._metrics["execution_failed"] += 1
            # Log failure
            logging_v2.log_runtime_event(
                event_kind="ENTRY_INTENT",
                symbol=symbol,
                action="executed",
                result="failed",
                why=result.get("error", "unknown_error"),
                extra={"side": side, "quantity": str(adjusted_qty)}
            )

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
            if symbol in self._open_orders_by_symbol:
                self._open_orders_by_symbol[symbol] = [
                    o for o in self._open_orders_by_symbol[symbol]
                    if o.get("order_id") != order_id
                ]
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
        """
        # Serialize execution to prevent race conditions on partial fills
        async with self._evaluation_lock:
            # 1. Check idempotency
            if not self.fill_idempotency.should_process_fill(payload, symbol=symbol):
                self._metrics["fills_duplicate"] += 1
                return

            self._metrics["fills_processed"] += 1

            # 2. Enrich price if needed
            enriched = self.price_enricher.enrich_trade(
                trade_payload=payload,
                position_entry_price=None,  # Could fetch from position
                current_price_quote=None
            )

            # 3. Update position state (CRITICAL: do this before WAL/exposure)
            raw_qty = float(payload.get("quantity", 0) or payload.get("qty", 0))
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
            is_new_position = abs(current_state.qty) < 0.0001

            # R2-B: Save previous position state for reverse detection
            if abs(current_state.qty) > 0.0001:
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

            is_prev_flat = abs(current_state.qty) < 0.0001
            is_new_flat = abs(new_state.qty) < 0.0001

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
            # 7. Evaluate trailing (log-only for now)
            self._evaluate_trailing(symbol, new_state, float(
                payload.get("price", 0) or payload.get("last_price", 0) or 0.0))

            # R2-B: Detect reverse (LONG→SHORT or SHORT→LONG) and cleanup old side brackets
            await self._handle_reverse_cleanup(symbol, new_state)

            # 8. Evaluate brackets (execute BracketPlan actions)
            await self._evaluate_brackets(symbol, new_state, reason="trade_executed")
            self._maybe_stop_guard_loop()

    async def _handle_position_sync(self, symbol: str, payload: Dict[str, Any]):
        """
        Handle POSITION_SYNC event from ACCOUNT_UPDATE.
        Triggers bracket evaluation for positions that may have been filled
        but didn't emit proper TRADE_EXECUTED events.
        """
        async with self._evaluation_lock:
            positions = payload.get("positions", [])

            for pos in positions:
                pos_symbol = pos.get("symbol")
                if not pos_symbol or pos_symbol != symbol:
                    continue

                # Update position state
                await self._handle_single_position_update(pos)

                # Get current state and evaluate brackets
                current_state = self._positions_by_symbol.get(pos_symbol)
                if current_state and abs(current_state.qty) > 0.0001:
                    logger.info(
                        f"📊 POSITION_SYNC: Evaluating brackets for {pos_symbol} qty={current_state.qty}")
                    await self._evaluate_brackets(pos_symbol, current_state, reason="account_update_sync")

    async def _handle_position_snapshot(self, payload: Dict[str, Any]):
        """Handle position snapshot from exchange."""
        async with self._evaluation_lock:
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

        # E-004: Log if we have qty but no entry price (contract violation from adapter)
        if abs(qty) > 0.0001 and entry_price <= 0:
            logger.warning(
                f"[ExecPosV2] POSITION_UPDATE_MISSING_ENTRY_PRICE: {symbol} qty={qty}, "
                f"entryPrice={entry_price}. Payload keys: {list(payload.keys())}. "
                "Watchdog may trigger REST snapshot recovery."
            )

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

        # Trigger watchdog
        await self._run_watchdog_analysis()
        self._maybe_stop_guard_loop()

    async def _handle_orders_snapshot(self, payload: Dict[str, Any]):
        """Handle orders snapshot from exchange."""
        orders = payload.get("orders", [])

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
                self._open_orders_by_symbol[sym] = []
                self._orders_snapshot_state[sym] = "FRESH"
                self._mark_orders_snapshot(sym)
                logger.debug(
                    f"[ExecPosV2] EMPTY_ORDERS_SNAPSHOT cleared mirror for {sym}",
                    extra={"symbol": sym, "snapshot_state": "FRESH"}
                )

            # Stale existing FRESH states for symbols without positions
            for sym, state in list(self._orders_snapshot_state.items()):
                if state == "FRESH" and sym not in self._positions_by_symbol:
                    self._orders_snapshot_state[sym] = "STALE"
            return

        now = time.monotonic()

        for order in orders:
            symbol = order.get("symbol")
            if not symbol:
                continue
            if symbol not in self._open_orders_by_symbol:
                self._open_orders_by_symbol[symbol] = []
            # Replace per-symbol list to avoid partial duplication
            # (build fresh list for each symbol)
        # Build new mapping per symbol
        new_mapping: Dict[str, list] = {}
        for order in orders:
            sym = order.get("symbol")
            if not sym:
                continue
            new_mapping.setdefault(sym, []).append(order)

        for sym, sym_orders in new_mapping.items():
            self._open_orders_by_symbol[sym] = sym_orders
            self._mark_orders_snapshot(sym, now)
            self._orders_snapshot_state[sym] = "FRESH"

            # R3-D1: Clear awaiting_snapshot after orders confirmed
            if sym in self._bracket_status:
                self._bracket_status[sym].awaiting_snapshot = False

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
        for orders in self._open_orders_by_symbol.values():
            all_orders.extend(orders)

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
        }

    def _is_brackets_suppressed(self, symbol: str) -> bool:
        # HOTFIX: Always return False - suppression disabled
        # Watchdog violations should trigger bracket CREATION, not suppression
        return False

        # Old logic kept for reference:
        # expires_at = self._brackets_suppressed.get(symbol)
        # if expires_at is None:
        #     return False
        # if time.monotonic() > expires_at:
        #     self._brackets_suppressed.pop(symbol, None)
        #     return False
        # return True

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

        for symbol, pos in active_positions.items():
            if not self._is_orders_snapshot_fresh(symbol):
                logger.debug(
                    f"[ExecPosV2] GUARD_LOOP_SKIP_NO_FRESH_ORDERS symbol={symbol}")
                continue

            last_ts = self._last_guard_recovery_ts.get(symbol, 0.0)
            now = time.monotonic()
            if now - last_ts < self._guard_recovery_interval_sec:
                continue

            await self._evaluate_brackets(symbol, pos, reason="guard_loop")
            self._last_guard_recovery_ts[symbol] = time.monotonic()

    def _build_position_id(self, symbol: str, position: PositionState) -> str:
        """
        Build deterministic position fingerprint for bracket clientOrderId.
        """
        qty_tag = f"{abs(position.qty):.4f}"
        price_tag = f"{position.avg_entry_price:.2f}" if position.avg_entry_price else "0"
        return f"{qty_tag}-{price_tag}"

    def _make_bracket_client_order_id(
        self,
        symbol: str,
        action_type: str,
        exit_side: Optional[str],
        qty: float,
        price: Optional[Decimal],
        position: Optional[PositionState] = None,
    ) -> str:
        """
        Generate deterministic clientOrderId for bracket orders to improve idempotency.
        R2-D: Includes cycle_id suffix for position lifecycle separation.
        """
        if position is not None:
            # R2-D: Include cycle_id in clientOrderId
            cycle_suffix = f"C{position.cycle_id}"
            position_id = self._build_position_id(symbol, position)
            base = f"AUR-{symbol}-{position.side}-{action_type}-{cycle_suffix}-{position_id}"

            # Binance limit: 32 chars
            if len(base) > 32:
                # Truncate position_id to fit
                max_pos_id_len = 32 - \
                    len(f"AUR-{symbol}-{position.side}-{action_type}-{cycle_suffix}-")
                if max_pos_id_len > 0:
                    position_id = position_id[:max_pos_id_len]
                    base = f"AUR-{symbol}-{position.side}-{action_type}-{cycle_suffix}-{position_id}"
                else:
                    # Extreme case: truncate symbol if needed
                    base = base[:32]

            return base
        seed = f"{symbol}|{action_type}|{exit_side}|{qty}|{price}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
        return f"AUR-BRK-{digest}"

    def _has_equivalent_bracket(self, symbol: str, exit_side: Optional[str], action: Any) -> bool:
        """
        Check if an equivalent reduce-only SL/TP already exists locally.
        """
        if not exit_side:
            return False

        target_qty = float(action.qty) if getattr(
            action, "qty", None) is not None else None
        target_price = getattr(action, "price", None)

        for order in self._open_orders_by_symbol.get(symbol, []):
            reduce_only = bool(order.get("reduce_only") or order.get(
                "reduceOnly", False) or order.get("close_position") or order.get("closePosition"))
            if not reduce_only:
                continue

            order_side = str(order.get("side") or "").upper()
            if order_side != exit_side:
                continue

            order_type = str(order.get("type") or order.get(
                "order_type") or "").upper()
            if action.action_type == "PLACE_SL" and order_type not in ("STOP_MARKET", "STOP"):
                continue
            if action.action_type == "PLACE_TP" and order_type not in ("TAKE_PROFIT_MARKET", "TAKE_PROFIT"):
                continue

            order_qty_raw = order.get("quantity") or order.get(
                "origQty") or order.get("qty")
            order_price_raw = order.get("stop_price") or order.get(
                "stopPrice") or order.get("price")

            try:
                if target_qty is not None and order_qty_raw is not None:
                    order_qty = Decimal(str(order_qty_raw))
                    desired_qty = Decimal(str(target_qty))
                    qty_diff = abs(order_qty - desired_qty)
                    qty_ref = max(desired_qty.copy_abs(),
                                  Decimal("0.00000001"))
                    if qty_diff / qty_ref > Decimal("0.05"):
                        continue
                if target_price is not None and order_price_raw is not None:
                    order_price = Decimal(str(order_price_raw))
                    desired_price = Decimal(str(target_price))
                    price_diff = abs(order_price - desired_price)
                    price_ref = max(desired_price.copy_abs(),
                                    Decimal("0.00000001"))
                    price_tolerance = max(
                        price_ref * Decimal("0.001"), Decimal("0.0001"))
                    if price_diff > price_tolerance:
                        continue
            except Exception:
                continue

            return True

        return False

    def _evaluate_trailing(self, symbol: str, position: PositionState, price: float) -> None:
        """
        Invoke trailing evaluation (log-only). No side effects on adapter.
        """
        if price <= 0:
            return
        state = self._trailing_state_by_symbol.get(symbol, TrailingState())
        try:
            decision = self.trailing_service.eval_trailing(
                position=position,
                price=price,
                trail_state=state,
                cfg=self._get_trailing_config(),
                now=self.clock.now() if self.clock else None,
            )
        except Exception:
            logger.warning(
                "TrailingStopService error; skipping trailing evaluation", exc_info=True)
            return

        self._trailing_state_by_symbol[symbol] = decision.trail_state
        self._metrics["trailing_evaluations"] += 1

        if decision.exit:
            self._metrics["trailing_exit_signals"] += 1
            logging_v2.log_runtime_event(
                event_kind="TRAILING",
                symbol=symbol,
                action="exit_signal",
                result="signal",
                why=decision.reason_code,
                extra={"sl_price": decision.sl_price,
                       "trail_status": decision.trail_state.status},
            )
        else:
            logging_v2.log_runtime_event(
                event_kind="TRAILING",
                symbol=symbol,
                action="updated",
                result="ok",
                why=decision.reason_code,
                extra={"sl_price": decision.sl_price,
                       "trail_status": decision.trail_state.status},
            )

    async def _evaluate_brackets(self, symbol: str, position: PositionState, *, reason: str = "runtime_eval") -> None:
        """
        Invoke BracketService in observe-only mode. No adapter/guardian mutations.
        """
        if self._is_brackets_suppressed(symbol):
            logger.warning(
                f"[ExecPosV2] BRACKETS_SUPPRESSED symbol={symbol} reason=watchdog")
            return

        snapshot_state = self._orders_snapshot_state.get(symbol, "UNKNOWN")
        has_snapshot_ts = symbol in self._last_orders_snapshot_ts
        if snapshot_state == "FRESH" and not self._is_orders_snapshot_fresh(symbol):
            snapshot_state = "STALE"
            self._orders_snapshot_state[symbol] = "STALE"

        if reason == "trade_executed" and snapshot_state == "UNKNOWN" and not has_snapshot_ts:
            # Allow bracket evaluation immediately after first fill even without snapshot
            snapshot_state = "FRESH"

        if reason in ("account_update_sync", "guard_loop") and snapshot_state != "FRESH":
            logging_v2.log_runtime_event(
                event_kind="BRACKETS",
                symbol=symbol,
                action="skip",
                result="snapshot_blocked",
                why=f"snapshot_state={snapshot_state}",
                extra={"reason": reason},
            )
            return

        should_block_unknown = snapshot_state == "UNKNOWN" and reason in (
            "trade_executed",
            "account_update_sync",
            "guard_loop",
        )
        if should_block_unknown:
            logging_v2.log_runtime_event(
                event_kind="BRACKETS",
                symbol=symbol,
                action="skip",
                result="snapshot_blocked",
                why=f"snapshot_state={snapshot_state}",
                extra={"reason": reason},
            )
            return

        # TASK 3: Throttle repeated bracket evaluations from account_update_sync
        if reason == "account_update_sync":
            last_ts = self._last_brackets_apply_ts.get(symbol, 0)
            now = time.time()
            elapsed = now - last_ts

            if elapsed < self._bracket_throttle_sec:
                self._metrics["brackets_throttled"] += 1
                logger.debug(
                    f"[ExecPosV2] BRACKETS_THROTTLED symbol={symbol} reason={reason} "
                    f"elapsed={elapsed:.1f}s < throttle={self._bracket_throttle_sec}s"
                )
                return

        cfg = self._get_bracket_cfg()
        if not cfg.enabled:
            return

        if position.side not in ("LONG", "SHORT"):
            return

        # EXEC-R2-K: Validate avg_entry_price before creating PositionView
        # E-004 invariant: qty > 0 requires avg_entry_price > 0
        entry_price_raw = position.avg_entry_price or 0
        if abs(position.qty) > 0.0001 and entry_price_raw <= 0:
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
        order_views: List[BracketOrderView] = []
        for order in self._open_orders_by_symbol.get(symbol, []):
            try:
                client_order_id_str = str(
                    order.get("client_order_id") or order.get("clientOrderId") or "")
                # R2-D: Parse cycle_id from clientOrderId
                from .bracket_service import parse_cycle_id_from_client_order_id
                cycle_id_parsed = parse_cycle_id_from_client_order_id(
                    client_order_id_str)

                order_views.append(
                    BracketOrderView(
                        order_id=str(order.get("order_id")
                                     or order.get("orderId") or ""),
                        client_order_id=client_order_id_str,
                        symbol=order.get("symbol", symbol),
                        side=str(order.get("side") or "").upper() or "BUY",
                        order_type=order.get("type") or order.get(
                            "order_type") or "LIMIT",
                        qty=Decimal(str(order.get("quantity") or order.get(
                            "origQty") or order.get("qty") or 0)),
                        price=Decimal(str(order.get("price"))) if order.get(
                            "price") not in (None, "") else None,
                        stop_price=Decimal(str(order.get("stop_price") or order.get(
                            "stopPrice"))) if order.get("stop_price") or order.get("stopPrice") else None,
                        reduce_only=bool(order.get("reduce_only")
                                         or order.get("reduceOnly", False)),
                        close_position=bool(
                            order.get("close_position") or order.get("closePosition", False)),
                        status=str(order.get("status") or "NEW"),
                        created_ts=float(order.get("created_ts")
                                         or order.get("time") or time.time()),
                        update_ts=float(order.get("update_ts") or order.get(
                            "updateTime") or time.time()),
                        cycle_id=cycle_id_parsed,
                    )
                )
            except Exception as exc:
                logger.debug("Skipping order for bracket evaluation", extra={
                             "symbol": symbol, "error": str(exc), "order": order})
                continue

        try:
            state_map = self.bracket_service.build_state(
                positions=[pos_view],
                orders=order_views,
                symbol=symbol,
                side=position.side,
            )
            state = state_map.get((symbol, position.side))
            if not state:
                return
            plan = self.bracket_service.evaluate(state, cfg)

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
                    snapshot_state=snapshot_state,
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

    async def _handle_reverse_cleanup(self, symbol: str, new_state: PositionState) -> None:
        """
        R2-B: Detect side flip (LONG→SHORT or SHORT→LONG) and cancel old side brackets.

        This is a minimal, fail-closed implementation for TEST-OCO-R1-003.
        Full position_id versioning will be added in R2-C.

        Args:
            symbol: Trading symbol
            new_state: New position state after fill

        Behavior:
            - Checks if prev_side != new_side (and both are LONG/SHORT)
            - If reverse detected, cancels all brackets from old side
            - Uses _open_orders_by_symbol mirror to find old brackets
            - Logs reverse detection for audit

        Example:
            - prev: LONG qty=2.0 with SL/TP (SELL reduceOnly)
            - new: SHORT qty=2.0 after SELL 4.0 fill
            - Action: CANCEL all SELL reduceOnly orders (old LONG brackets)
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

        # Determine old side exit orders (brackets to cancel)
        # LONG position → SL/TP are SELL reduceOnly
        # SHORT position → SL/TP are BUY reduceOnly
        old_exit_side = "SELL" if prev_state.side == "LONG" else "BUY"

        # Find and cancel all old side brackets
        old_orders = self._open_orders_by_symbol.get(symbol, [])
        cancelled_count = 0

        for order in old_orders:
            order_side = order.get("side", "").upper()
            reduce_only = order.get("reduceOnly") or order.get("reduce_only")
            order_type = order.get("type", "")

            # Match old exit side brackets (SL/TP)
            if (order_side == old_exit_side and
                reduce_only and
                    order_type in ("STOP_MARKET", "TAKE_PROFIT_MARKET", "STOP", "TAKE_PROFIT")):

                order_id = order.get("orderId") or order.get("order_id")
                client_order_id = order.get(
                    "clientOrderId") or order.get("client_order_id")

                logger.info(
                    f"[ExecPosV2] CANCEL_OLD_BRACKET symbol={symbol} "
                    f"reverse={prev_state.side}→{new_state.side} "
                    f"order_id={order_id} type={order_type} side={order_side}"
                )

                try:
                    await self.execution_service.cancel_order(
                        symbol=symbol,
                        order_id=str(order_id),
                        client_order_id=str(
                            client_order_id) if client_order_id else None,
                    )
                    cancelled_count += 1
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
        Execute BracketPlan actions via ExecutionService (no auto-heal loops).
        """
        # R3-D1: Guard-loop anti-double-apply protection
        status = self._bracket_status.get(symbol)
        if not status:
            status = BracketStatus()
            self._bracket_status[symbol] = status

        # R3-D1 FIX: Block guard_loop AND account_update_sync when awaiting_snapshot
        # Only trade_executed and brackets_recovery can proceed when awaiting confirmation
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

        actions_summary = []
        side = position.side
        exit_side = "SELL" if side == "LONG" else (
            "BUY" if side == "SHORT" else None)

        logger.info(
            f"[ExecPosV2] APPLY_BRACKETS position_side={side} exit_side={exit_side} qty={position.qty}"
        )

        placed_orders = []

        for action in plan.actions:
            actions_summary.append(action.action_type)

            # DIAGNOSTIC: Log each action processing
            logger.info(
                f"[ExecPosV2] BRK_ACTION symbol={symbol} action_type={action.action_type} "
                f"price={getattr(action, 'price', None)} qty={getattr(action, 'qty', None)}"
            )

            if action.action_type == "CANCEL":
                cancel_result = await self.execution_service.cancel_order(
                    symbol=symbol,
                    order_id=action.order_id,
                    client_order_id=action.client_order_id,
                )
                # Handle cancel timeout - force snapshot to sync with exchange
                if isinstance(cancel_result, dict) and cancel_result.get("error_kind") == "ADAPTER_ERROR_TIMEOUT":
                    logger.warning(
                        "[ExecPosV2] Timeout canceling bracket for %s order_id=%s, forcing ORDERS_SNAPSHOT",
                        symbol, action.order_id
                    )
                    self._orders_snapshot_state[symbol] = "UNKNOWN"
                    self._last_orders_snapshot_ts[symbol] = 0.0
                    await self._request_orders_snapshot(symbol, force=True)
                    # Don't update mirror - let snapshot reconcile actual state
                    status.in_flight = False
                    status.awaiting_snapshot = True
                    return
                # R2-B: Update local mirror after CANCEL to reflect exchange state
                self._remove_order_from_mirror(symbol, action.order_id)
            elif action.action_type in ("PLACE_SL", "PLACE_TP") and exit_side:
                order_type = "STOP_MARKET" if action.action_type == "PLACE_SL" else "TAKE_PROFIT_MARKET"
                qty = float(action.qty) if action.qty is not None else abs(
                    position.qty)
                if self._has_equivalent_bracket(symbol, exit_side, action):
                    logger.info(
                        f"[ExecPosV2] SKIP_PLACE_DUPLICATE_BRACKET symbol={symbol} action={action.action_type} side={exit_side} qty={qty} price={action.price}"
                    )
                    continue
                client_order_id = self._make_bracket_client_order_id(
                    symbol, action.action_type, exit_side, qty, action.price, position=position)

                # DIAGNOSTIC: Log before execution
                logger.info(
                    f"[ExecPosV2] EXEC_BRACKET symbol={symbol} action_type={action.action_type} "
                    f"order_type={order_type} side={exit_side} qty={qty} "
                    f"stop_price={action.price}"
                )
                result = await self.execution_service.place_order(
                    symbol=symbol,
                    side=exit_side,
                    order_type=order_type,
                    quantity=qty,
                    stop_price=str(
                        action.price) if action.price is not None else None,
                    client_order_id=client_order_id,
                    reduce_only=True,
                )
                if isinstance(result, dict) and result.get("success") is False and result.get("error_kind") == "ADAPTER_ERROR_TIMEOUT":
                    logger.warning(
                        "[ExecPosV2] Timeout placing bracket for %s, forcing ORDERS_SNAPSHOT", symbol)
                    self._orders_snapshot_state[symbol] = "UNKNOWN"
                    self._last_orders_snapshot_ts[symbol] = 0.0
                    await self._request_orders_snapshot(symbol, force=True)
                    return
                if isinstance(result, dict) and result.get("success") is False:
                    continue

                # R2-B FIX: Immediately update local mirror with new bracket order
                if isinstance(result, dict) and result.get("success"):
                    mock_order = {
                        "orderId": result.get("order_id") or result.get("orderId"),
                        "clientOrderId": result.get("client_order_id") or client_order_id,
                        "symbol": symbol,
                        "side": exit_side,
                        "type": order_type,
                        "quantity": str(qty),
                        "price": str(action.price) if action.price is not None else None,
                        "stopPrice": str(action.price) if action.price is not None else None,
                        "reduceOnly": True,
                        "status": "NEW",
                        "created_ts": time.time() * 1000,
                        "update_ts": time.time() * 1000
                    }
                    if symbol not in self._open_orders_by_symbol:
                        self._open_orders_by_symbol[symbol] = []
                    self._open_orders_by_symbol[symbol].append(mock_order)
                    logger.info(
                        f"[ExecPosV2] MIRROR_UPDATE_ADD symbol={symbol} order_id={mock_order['orderId']} "
                        f"client_order_id={mock_order['clientOrderId']}"
                    )

                placed_orders.append(
                    {
                        "order_id": result.get("order_id") if isinstance(result, dict) else None,
                        "client_order_id": result.get("client_order_id") if isinstance(result, dict) else client_order_id,
                        "order_type": order_type,
                        "side": exit_side,
                        "qty": qty,
                        "price": float(action.price) if action.price is not None else None,
                        "reduce_only": True,
                    }
                )
            elif action.action_type == "ADJUST" and exit_side:
                if action.order_id:
                    await self.execution_service.cancel_order(symbol=symbol, order_id=action.order_id)
                order_type = "STOP_MARKET" if action.reason_code in (
                    "MISSING_SL", "STALE_LEVELS") else "TAKE_PROFIT_MARKET"
                qty = float(action.qty) if action.qty is not None else abs(
                    position.qty)
                client_order_id = self._make_bracket_client_order_id(
                    symbol, action.action_type, exit_side, qty, action.price, position=position)
                result = await self.execution_service.place_order(
                    symbol=symbol,
                    side=exit_side,
                    order_type=order_type,
                    quantity=qty,
                    stop_price=str(
                        action.price) if action.price is not None else None,
                    client_order_id=client_order_id,
                    reduce_only=True,
                )
                if isinstance(result, dict) and result.get("success") is False and result.get("error_kind") == "ADAPTER_ERROR_TIMEOUT":
                    logger.warning(
                        "[ExecPosV2] Timeout placing bracket for %s, forcing ORDERS_SNAPSHOT", symbol)
                    self._orders_snapshot_state[symbol] = "UNKNOWN"
                    self._last_orders_snapshot_ts[symbol] = 0.0
                    await self._request_orders_snapshot(symbol, force=True)
                    return
                if isinstance(result, dict) and result.get("success") is False:
                    continue

                # R2-B FIX: Immediately update local mirror with new bracket order
                if isinstance(result, dict) and result.get("success"):
                    mock_order = {
                        "orderId": result.get("order_id") or result.get("orderId"),
                        "clientOrderId": result.get("client_order_id") or client_order_id,
                        "symbol": symbol,
                        "side": exit_side,
                        "type": order_type,
                        "quantity": str(qty),
                        "price": str(action.price) if action.price is not None else None,
                        "stopPrice": str(action.price) if action.price is not None else None,
                        "reduceOnly": True,
                        "status": "NEW",
                        "created_ts": time.time() * 1000,
                        "update_ts": time.time() * 1000
                    }
                    if symbol not in self._open_orders_by_symbol:
                        self._open_orders_by_symbol[symbol] = []
                    self._open_orders_by_symbol[symbol].append(mock_order)
                    logger.info(
                        f"[ExecPosV2] MIRROR_UPDATE_ADD (ADJUST) symbol={symbol} order_id={mock_order['orderId']} "
                        f"client_order_id={mock_order['clientOrderId']}"
                    )

                placed_orders.append(
                    {
                        "order_id": result.get("order_id") if isinstance(result, dict) else None,
                        "client_order_id": result.get("client_order_id") if isinstance(result, dict) else client_order_id,
                        "order_type": order_type,
                        "side": exit_side,
                        "qty": qty,
                        "price": float(action.price) if action.price is not None else None,
                        "reduce_only": True,
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

    async def _run_bracket_recovery_pass(self) -> None:
        """
        Single-shot DR/rehydrate recovery using BracketService plans (no loops).
        """
        if self._recovery_completed:
            return

        cfg = self._get_bracket_cfg()
        if not cfg.enabled:
            self._recovery_completed = True
            return

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
        for sym, orders in self._open_orders_by_symbol.items():
            for order in orders:
                try:
                    client_order_id_str = str(
                        order.get("client_order_id") or order.get("clientOrderId") or "")
                    # R2-D: Parse cycle_id from clientOrderId
                    from .bracket_service import parse_cycle_id_from_client_order_id
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
            bf = getattr(self.bracket_service,
                         "evaluate_all_for_recovery", None)
            plans = None
            if callable(bf):
                plans = bf(positions=pos_views, orders=order_views, cfg=cfg)
            else:
                plans = self.bracket_service.evaluate_all(
                    positions=pos_views, orders=order_views, cfg=cfg)
            if hasattr(plans, "__await__"):
                plans = await plans  # type: ignore
        except Exception:
            logger.error("Bracket recovery evaluation failed", exc_info=True)
            self._recovery_completed = True
            return

        for plan in plans or []:
            reason = "brackets_recovery"
            if any(a.action_type == "ADJUST" for a in plan.actions):
                reason = "brackets_recovery_adjust_mismatch"
            elif any(a.action_type in ("PLACE_SL", "PLACE_TP") for a in plan.actions):
                reason = "brackets_recovery_seed_protection"
            elif plan.state.is_flat and plan.actions:
                reason = "brackets_recovery_orphan_cleanup"

            logging_v2.log_runtime_event(
                event_kind="BRACKETS_RECOVERY_PLAN",
                symbol=plan.symbol,
                action="plan",
                result=plan.severity.lower(),
                why=reason[:80],
                extra={"actions": [
                    a.action_type for a in plan.actions], "rid": plan.rid},
            )

            try:
                pos_state = self._positions_by_symbol.get(
                    plan.symbol) or PositionState(symbol=plan.symbol)
                await self._apply_bracket_plan(plan.symbol, pos_state, plan, reason=reason)
            except Exception:
                logger.error("Bracket recovery application failed",
                             exc_info=True, extra={"symbol": plan.symbol})

        self._recovery_completed = True

    def _get_trailing_config(self) -> TrailingConfig:
        """
        Retrieve trailing config, preferring typed ExecutionPositionConfig when available.
        Falls back to legacy dict-based config (defaults preserved).
        """
        if self._ep_cfg and getattr(self._ep_cfg, "trailing", None):
            trailing_cfg = self._ep_cfg.trailing
            try:
                return TrailingConfig(
                    trail_distance_bps=self._coerce_float(
                        getattr(trailing_cfg, "trail_distance_bps", None), 100.0),
                    activate_after_bps=self._coerce_float(
                        getattr(trailing_cfg, "activate_after_bps", None), 0.0),
                    breakeven_rr=self._coerce_float(
                        getattr(trailing_cfg, "breakeven_rr", None), 0.0),
                    hard_time_exit_sec=self._coerce_optional_float(
                        getattr(trailing_cfg, "hard_time_exit_sec", None),
                        None,
                    ),
                )
            except Exception:
                # fall through to legacy path on any unexpected structure issues
                pass

        cfg_root = self.config.get("execution_position", self.config) if isinstance(
            self.config, dict) else {}
        trailing_node = {}
        if isinstance(cfg_root, dict):
            manage = cfg_root.get("manage", {})
            if isinstance(manage, dict):
                trailing_node = manage.get("trailing", {}) or {}
            trailing_node = trailing_node or cfg_root.get("trailing", {}) or {}

        return TrailingConfig(
            trail_distance_bps=self._coerce_float(self._pluck(
                trailing_node, "trail_distance_bps"), 100.0),
            activate_after_bps=self._coerce_float(
                self._pluck(trailing_node, "activate_after_bps"), 0.0),
            breakeven_rr=self._coerce_float(
                self._pluck(trailing_node, "breakeven_rr"), 0.0),
            hard_time_exit_sec=self._coerce_optional_float(
                self._pluck(trailing_node, "hard_time_exit_sec"), None),
        )

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
                    reason_policy=str(
                        getattr(close_cfg, "reason_policy", "default") or "default"),
                    allow_time_exit=self._coerce_bool(
                        getattr(close_cfg, "allow_time_exit", None), True),
                    allow_profit_exit=self._coerce_bool(
                        getattr(close_cfg, "allow_profit_exit", None), True),
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
            reason_policy=str(self._pluck(
                close_node, "reason_policy") or "default"),
            allow_time_exit=self._coerce_bool(
                self._pluck(close_node, "allow_time_exit"), True),
            allow_profit_exit=self._coerce_bool(
                self._pluck(close_node, "allow_profit_exit"), True),
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

    def _get_bracket_cfg(self) -> BracketRulesConfig:
        # Preferred typed config path
        if self._ep_cfg and getattr(self._ep_cfg, "aggregated_oco", None):
            agg = self._ep_cfg.aggregated_oco
            try:
                return BracketRulesConfig(
                    enabled=agg.enabled,
                    allow_unprotected_position=agg.allow_unprotected_position,
                    recalc_on_partial_close=agg.recalc_on_partial_close,
                    recalc_on_scale_in=agg.recalc_on_scale_in,
                    ttl_protect_new_bracket_ms=agg.ttl_protect_new_bracket_ms,
                    max_tp_legs=agg.max_tp_legs,
                    max_sl_legs=agg.max_sl_legs,
                    sl_pct=agg.sl_pct,
                    tp_rr=agg.tp_rr,
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
