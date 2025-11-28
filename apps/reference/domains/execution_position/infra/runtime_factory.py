from typing import Any, Dict, List, Optional
import logging
import time
import asyncio

# Import shadow runtime and adapter
from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.types import RuntimeEvent
from .adapter_factory import build_execution_adapter
from apps.reference.domains.execution_position.contracts import TradeIntentPayload, OpenCommandPayload, resolve_order_defaults
from apps.reference.domains.execution_position.internal_types import RuntimeEntryIntent
from pydantic import ValidationError

LOG = logging.getLogger(__name__)


def build_execution_runtime(
    config: Any,
    fsm: Any,
    adapter: Any = None,
    price_service: Any = None
) -> Any:
    """
    Factory to create the execution runtime.
    """
    # Extract config dict
    config_dict = config.to_dict() if hasattr(config, "to_dict") else config

    # Resolve runtime mode
    exec_cfg = config_dict.get("execution_position", config_dict)
    runtime_mode = exec_cfg.get("runtime_mode", "v2")

    # Normalize
    if not isinstance(runtime_mode, str):
        runtime_mode = "v2"
    runtime_mode = runtime_mode.lower()

    # Enforce V2-only
    if runtime_mode == "legacy":
        raise ValueError(
            "ExecPosFSM (legacy mode) has been removed. "
            "Please remove 'runtime_mode: legacy' from your configuration."
        )

    LOG.info("Initializing ExecPosRuntimeV2 (Shadow Mode)...")
    exec_adapter = adapter if adapter is not None else build_execution_adapter(
        config, fsm=fsm)

    facade = V2RuntimeFacade(
        config=config_dict,
        adapter=exec_adapter,
        price_service=price_service,
        fsm=fsm
    )

    # Subscribe to WebSocket trade events
    if fsm:
        fsm.listen("EVT:TRADE_EXECUTED", facade.on_trade_executed)
        fsm.listen("EVT:ACCOUNT_UPDATE_RECEIVED", facade.on_account_update)

        enable_direct_intents = exec_cfg.get(
            "enable_direct_trade_intent_listener", False)
        if enable_direct_intents:
            fsm.listen("EVT:TRADE_INTENT_PROPOSED",
                       facade.on_trade_intent_proposed)
            LOG.info(
                "✅ V2RuntimeFacade subscribed to EVT:TRADE_INTENT_PROPOSED (direct intent path enabled)")
        else:
            LOG.info(
                "V2RuntimeFacade direct TRADE_INTENT_PROPOSED listener disabled (Bridge is gatekeeper)")

    return facade


class V2RuntimeFacade:
    """
    Facade that adapts ExecPosRuntimeV2 to the legacy ExecPosFSM interface.
    Mainly responsible for converting Messages to RuntimeEvents.
    """

    def __init__(self, config: Dict[str, Any], adapter: Any = None, price_service: Any = None, fsm: Any = None, loop: Optional[asyncio.AbstractEventLoop] = None):
        self.adapter = adapter  # Store adapter reference for WebSocket startup
        self.fsm = fsm  # Store FSM for event subscription
        # Will be lazily attached via _ensure_loop()
        self._loop: Optional[asyncio.AbstractEventLoop] = loop
        self.runtime = ExecPosRuntimeV2(
            config=config,
            adapter=adapter,
            price_service=price_service
        )
        self.logger = logging.getLogger("ExecPosRuntimeV2Facade")
        self.runtime.set_snapshot_refresh_hook(self.request_orders_snapshot)
        # Use constant from runtime to avoid drift
        self._snapshot_request_interval_sec = ExecPosRuntimeV2.SNAPSHOT_REQUEST_INTERVAL_SEC
        self._last_snapshot_request_ts: Dict[str, float] = {}

    def _ensure_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """
        Ensure we have a running event loop.
        If loop was passed at construction and is still running - use it.
        Otherwise, try to attach to current running loop.
        Returns None if no running loop is available.
        """
        # 1) If we already have a living and running loop - use it
        if self._loop and not self._loop.is_closed() and self._loop.is_running():
            return self._loop

        # 2) Try to attach to current running loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self.logger.error(
                "ExecPosRuntimeV2Facade: no running event loop available; "
                "cannot schedule runtime event"
            )
            return None

        # 3) Cache it for future calls
        self._loop = loop
        self.logger.info(
            "ExecPosRuntimeV2Facade: attached to running loop %r", loop)
        return loop

    def _submit_to_loop(self, coro: Any, source: str = "unknown") -> Any:
        """
        Submit coroutine to event loop using run_coroutine_threadsafe.
        Will attach to running loop if not already attached.
        """
        loop = self._ensure_loop()
        if not loop:
            self.logger.error(
                "Runtime loop is not running; dropping event source=%s",
                source
            )
            return None

        try:
            # If we're already inside this loop, create task directly
            try:
                running = asyncio.get_running_loop()
                if running is loop:
                    return loop.create_task(coro)
            except RuntimeError:
                pass

            # Otherwise schedule from another thread
            return asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError as e:
            self.logger.error(
                "Failed to schedule coroutine: %s", e, exc_info=True)
            return None

    def handle(self, message: Any) -> Any:
        """
        Handle legacy vFoundation Message.
        """
        # Log incoming message for debugging
        op = getattr(message, "op", None)
        verb = getattr(message, "verb", None)
        payload = getattr(message, "pld", {}) or {}
        timestamp = getattr(message, "ts", 0.0)
        symbol = payload.get("symbol") if isinstance(payload, dict) else None

        self.logger.debug(
            f"V2RuntimeFacade.handle() received: op={op}, verb={verb}, symbol={symbol}")

        # Inline Adapter Logic
        runtime_event = None

        if op == "CMD" and verb == "OPEN":
            runtime_event = self._map_legacy_open(payload, message, timestamp)
        elif op == "CMD" and verb in ["CANCEL", "CANCEL_ORDER"]:
            runtime_event = self._map_legacy_cancel(payload, timestamp)
        elif op == "CMD" and verb in ["CLOSE", "FORCE_CLOSE"]:
            runtime_event = self._map_legacy_close(payload, verb, timestamp)
        elif verb in ["TRADE_EXECUTED", "FILL", "PARTIAL_FILL"]:
            runtime_event = self._map_legacy_trade(payload, timestamp)
        elif verb in ["PORTFOLIO_STATE_UPDATED", "POSITION_SNAPSHOT", "ACCOUNT_UPDATE", "outboundAccountPosition"]:
            runtime_event = self._map_legacy_position_snapshot(payload, timestamp)
        elif verb in ["OPEN_ORDERS_UPDATED", "ORDERS_SNAPSHOT"]:
            runtime_event = self._map_legacy_orders_snapshot(payload, timestamp)

        if runtime_event:
            # RuntimeEvent is a dataclass - access fields as attributes
            self.logger.info(
                f"✅ Converted to RuntimeEvent: kind={runtime_event.kind}, symbol={runtime_event.symbol}")
            self.logger.info("[RuntimeFacade-S5] scheduling event: kind=%s source=handle",
                             getattr(runtime_event, "kind", None))
            self._submit_to_loop(self.runtime.handle(
                runtime_event), source="handle")
            return None
        else:
            # Only warn if it looked like a command we should have handled
            if op == "CMD":
                self.logger.warning(
                    f"⚠️ Facade could not map message op={op}, verb={verb}, symbol={symbol}")
            return None

    def _map_legacy_open(self, payload: Dict[str, Any], msg: Any, timestamp: float) -> Optional[RuntimeEvent]:
        try:
            ocp = OpenCommandPayload.model_validate(payload)
        except ValidationError as exc:
            self.logger.warning(
                "RuntimeEventAdapter: invalid CMD:OPEN payload; skipping",
                extra={"errors": exc.errors(), "payload": payload},
            )
            return None

        resolved_order_type, resolved_tif = resolve_order_defaults(
            ocp.price, ocp.order_type, ocp.time_in_force
        )

        rid = getattr(msg, "rid", None) or ocp.rid
        entry_intent = RuntimeEntryIntent(
            symbol=ocp.symbol,
            side=ocp.side,
            quantity=ocp.quantity,
            price=ocp.price,
            price_ref=ocp.price_ref,
            order_type=resolved_order_type,
            time_in_force=resolved_tif,
            rid=rid,
            strategy_id=ocp.strategy_id,
            idempotent_key=ocp.idempotent_key,
            client_order_id=ocp.client_order_id,
            why=ocp.why,
        )

        return RuntimeEvent(
            kind="ENTRY_INTENT",
            symbol=entry_intent.symbol,
            timestamp=timestamp,
            payload={
                "symbol": entry_intent.symbol,
                "side": entry_intent.side,
                "quantity": entry_intent.quantity,
                "price": entry_intent.price,
                "price_ref": entry_intent.price_ref,
                "order_type": entry_intent.order_type,
                "tif": entry_intent.time_in_force,
                "idempotent_key": entry_intent.idempotent_key,
                "strategy_id": entry_intent.strategy_id,
                "client_order_id": entry_intent.client_order_id,
                "rid": rid,
                "why": entry_intent.why,
            }
        )

    def _map_legacy_cancel(self, payload: Dict[str, Any], timestamp: float) -> RuntimeEvent:
        return RuntimeEvent(
            kind="CANCEL_INTENT",
            symbol=payload.get("symbol"),
            timestamp=timestamp,
            payload={
                "order_id": payload.get("order_id"),
                "client_order_id": payload.get("client_order_id"),
            }
        )

    def _map_legacy_close(self, payload: Dict[str, Any], verb: str, timestamp: float) -> RuntimeEvent:
        return RuntimeEvent(
            kind="CLOSE_INTENT",
            symbol=payload.get("symbol"),
            timestamp=timestamp,
            payload={
                "quantity": payload.get("qty"), # Optional, full close if missing
                "reason": payload.get("reason", "force_close" if verb == "FORCE_CLOSE" else "manual"),
                "is_force": verb == "FORCE_CLOSE",
            }
        )

    def _map_legacy_trade(self, payload: Dict[str, Any], timestamp: float) -> RuntimeEvent:
        return RuntimeEvent(
            kind="TRADE_EXECUTED",
            symbol=payload.get("symbol"),
            timestamp=timestamp,
            payload={
                "order_id": payload.get("order_id"),
                "client_order_id": payload.get("client_order_id"),
                "side": payload.get("side"),
                "quantity": payload.get("last_qty") or payload.get("qty"),
                "price": payload.get("last_price") or payload.get("price"),
                "fee": payload.get("fee"),
                "fee_asset": payload.get("fee_asset"),
                "role": payload.get("role"), # MAKER/TAKER
                "cum_qty": payload.get("cum_qty"),
                "cum_quote": payload.get("cum_quote"),
                "trade_id": payload.get("trade_id"),
            }
        )

    def _map_legacy_position_snapshot(self, payload: Dict[str, Any], timestamp: float) -> RuntimeEvent:
        raw_positions = payload.get("positions", [])
        normalized_positions = []
        for pos in raw_positions:
            p_symbol = pos.get("symbol")
            if not p_symbol:
                continue

            p_amt = pos.get("positionAmt") or pos.get("position_amount") or pos.get("qty") or pos.get("amount")
            p_entry = pos.get("entryPrice") or pos.get("avgPrice") or pos.get("avg_price") or pos.get("entry_price")
            p_side = pos.get("positionSide") or pos.get("side") or pos.get("position_side")

            normalized_positions.append({
                "symbol": p_symbol,
                "qty": float(p_amt) if p_amt is not None else 0.0,
                "entry_price": float(p_entry) if p_entry is not None else 0.0,
                "side": p_side,
                "unrealized_pnl": pos.get("unRealizedProfit") or pos.get("unrealized_pnl"),
                "update_time": pos.get("updateTime") or timestamp
            })

        return RuntimeEvent(
            kind="POSITION_SNAPSHOT",
            symbol=None, # Snapshot is often global or multi-symbol
            timestamp=timestamp,
            payload={
                "positions": normalized_positions,
                "source": payload.get("source", "portfolio")
            }
        )

    def _map_legacy_orders_snapshot(self, payload: Dict[str, Any], timestamp: float) -> RuntimeEvent:
        raw_orders = payload.get("orders", [])
        normalized_orders = []
        for order in raw_orders:
            o_symbol = order.get("symbol")
            if not o_symbol:
                continue

            normalized_orders.append({
                "order_id": order.get("orderId") or order.get("order_id"),
                "client_order_id": order.get("clientOrderId") or order.get("client_order_id"),
                "symbol": o_symbol,
                "side": order.get("side"),
                "type": order.get("type") or order.get("order_type"),
                "quantity": order.get("origQty") or order.get("qty") or order.get("quantity"),
                "price": order.get("price"),
                "stop_price": order.get("stopPrice") or order.get("stop_price"),
                "reduce_only": order.get("reduceOnly") or order.get("reduce_only", False),
                "status": order.get("status"),
            })

        return RuntimeEvent(
            kind="ORDERS_SNAPSHOT",
            symbol=payload.get("symbol"), # Often per-symbol
            timestamp=timestamp,
            payload={
                "orders": normalized_orders,
                "source": payload.get("source", "adapter")
            }
        )

    def hydrate(self, position_data: Dict[str, Any]) -> None:
        self.runtime.hydrate(position_data)

    def get_agg_oco_state_snapshot(self, symbol: str = None, side: str = None, as_dict: bool = True) -> List[Dict[str, Any]]:
        """
        Get aggregated OCO state snapshot for debug API.

        Delegates to runtime's get_positions_snapshot() method.
        Returns list of position dicts with full state info.
        """
        return self.runtime.get_positions_snapshot(symbol=symbol, side=side)

    def on_trade_executed(self, message: Any) -> None:
        """
        Handler for EVT:TRADE_EXECUTED from WebSocket.
        Converts to TRADE_EXECUTED event and forwards to Runtime V2.

        Args:
            message: Message object from FSMCore.emit()
        """
        # Extract payload from Message
        payload = message.pld if hasattr(message, 'pld') else message
        symbol = payload.get("symbol")

        # Create RuntimeEvent for TRADE_EXECUTED
        runtime_event = {
            "kind": "TRADE_EXECUTED",
            "symbol": symbol,
            "payload": payload
        }

        self.logger.info(
            f"📥 Received TRADE_EXECUTED from WebSocket: {symbol} qty={payload.get('quantity')}")

        # CRITICAL FIX (S23): Request ORDERS_SNAPSHOT after TRADE_EXECUTED
        # This ensures runtime has order state before evaluating brackets
        self.logger.info(
            "[RuntimeFacade-S5] scheduling event: kind=TRADE_EXECUTED source=ws")
        self._submit_to_loop(self._sync_orders_and_handle_trade(
            symbol, runtime_event), source="ws_trade_executed")

    def on_account_update(self, message: Any) -> None:
        """
        Handler for EVT:ACCOUNT_UPDATE_RECEIVED from WebSocket.
        Ensures ORDERS_SNAPSHOT is applied before POSITION_SYNC.
        """
        payload = message.pld if hasattr(message, 'pld') else message
        self.logger.info(
            "[RuntimeFacade-S5] scheduling event: kind=ACCOUNT_UPDATE_RECEIVED source=ws")
        self._submit_to_loop(self._process_account_update(
            payload), source="ws_account_update")

    def on_trade_intent_proposed(self, message: Any) -> Any:
        """
        Handler for EVT:TRADE_INTENT_PROPOSED from DecisionMaking.
        Maps decision trade intent to ENTRY_INTENT for ExecPosRuntimeV2.
        """
        trade_intent = getattr(message, "pld", None) or getattr(
            message, "payload", None) or message
        order = trade_intent.get("order") or {}
        metadata = trade_intent.get("metadata") or trade_intent.get("meta") or {}
        mapped_payload = {
            "symbol": trade_intent.get("symbol") or trade_intent.get("instrument"),
            "side": trade_intent.get("side"),
            "quantity": trade_intent.get("quantity") or trade_intent.get("qty") or order.get("qty"),
            "price": trade_intent.get("price") or trade_intent.get("limit_price") or order.get("price"),
            "price_ref": trade_intent.get("price_ref") or order.get("price_ref"),
            "order_type": trade_intent.get("order_type") or order.get("order_type") or order.get("type"),
            "time_in_force": trade_intent.get("time_in_force") or trade_intent.get("tif") or order.get("time_in_force") or order.get("tif"),
            "rid": trade_intent.get("rid") or trade_intent.get("request_id"),
            "strategy_id": trade_intent.get("strategy_id") or metadata.get("strategy_id"),
            "idempotent_key": trade_intent.get("idempotent_key") or metadata.get("idempotent_key"),
            "metadata": metadata,
            "why": trade_intent.get("why"),
        }

        try:
            intent_model = TradeIntentPayload(**mapped_payload)
        except ValidationError as exc:
            self.logger.warning(
                "[RuntimeFacade-S4] Invalid TRADE_INTENT_PROPOSED; skipping",
                extra={"errors": exc.errors()},
            )
            return None

        try:
            resolved_order_type, resolved_tif = resolve_order_defaults(
                intent_model.price, intent_model.order_type, intent_model.time_in_force
            )
            open_cmd = OpenCommandPayload(
                rid=intent_model.rid,
                symbol=intent_model.symbol,
                side=intent_model.side,
                quantity=intent_model.quantity,
                price=intent_model.price,
                price_ref=intent_model.price_ref,
                order_type=resolved_order_type,
                time_in_force=resolved_tif,
                idempotent_key=intent_model.idempotent_key,
                strategy_id=intent_model.strategy_id,
                why=intent_model.why if isinstance(intent_model.why, str) else None,
            )
        except ValidationError as exc:
            self.logger.warning(
                "[RuntimeFacade-S4] Failed to build OpenCommandPayload; skipping",
                extra={"errors": exc.errors()},
            )
            return None

        entry_intent = RuntimeEntryIntent(
            symbol=open_cmd.symbol,
            side=open_cmd.side,
            quantity=open_cmd.quantity,
            price=open_cmd.price,
            price_ref=open_cmd.price_ref,
            order_type=resolved_order_type,
            time_in_force=resolved_tif,
            rid=open_cmd.rid,
            strategy_id=open_cmd.strategy_id,
            idempotent_key=open_cmd.idempotent_key,
            client_order_id=open_cmd.client_order_id,
            why=open_cmd.why,
        )

        runtime_event = {
            "kind": "ENTRY_INTENT",
            "symbol": entry_intent.symbol,
            "payload": {
                "symbol": entry_intent.symbol,
                "side": entry_intent.side,
                "quantity": entry_intent.quantity,
                "price": entry_intent.price,
                "price_ref": entry_intent.price_ref,
                "order_type": entry_intent.order_type,
                "tif": entry_intent.time_in_force,
                "source": "DecisionMaking",
                "rid": entry_intent.rid,
                "idempotent_key": entry_intent.idempotent_key,
                "client_order_id": entry_intent.client_order_id,
                "why": entry_intent.why,
            },
        }

        self.logger.info("[RuntimeFacade-S4] scheduling event: kind=ENTRY_INTENT source=decision symbol=%s",
                         entry_intent.symbol)
        return self._submit_to_loop(self.runtime.handle(runtime_event), source="decision_intent")

    async def _sync_orders_and_handle_trade(self, symbol: str, runtime_event: Dict[str, Any]) -> None:
        """
        Fetch orders snapshot and then handle TRADE_EXECUTED.
        This ensures runtime has order state before bracket evaluation.
        """
        orders = []
        if self.adapter and hasattr(self.adapter, "get_open_orders"):
            try:
                orders = await self.adapter.get_open_orders(symbol=symbol)
            except Exception as exc:
                self.logger.error(
                    f"Failed to fetch open orders for {symbol}: {exc}", exc_info=True)
                orders = []

        # Emit ORDERS_SNAPSHOT first
        await self.runtime.handle({
            "kind": "ORDERS_SNAPSHOT",
            "payload": {"orders": orders}
        })

        # Then handle TRADE_EXECUTED
        await self.runtime.handle(runtime_event)

    async def _process_account_update(self, payload: Dict[str, Any]) -> None:
        positions = payload.get("positions", []) or []

        orders = []
        if self.adapter and hasattr(self.adapter, "get_open_orders"):
            try:
                orders = await self.adapter.get_open_orders()
            except Exception as exc:
                self.logger.error(
                    f"Failed to fetch open orders: {exc}", exc_info=True)
                orders = []

        await self.runtime.handle({
            "kind": "ORDERS_SNAPSHOT",
            "payload": {"orders": orders}
        })

        for pos in positions:
            symbol = pos.get("symbol")
            if not symbol:
                continue
            await self.runtime.handle({
                "kind": "POSITION_SYNC",
                "symbol": symbol,
                "payload": {"positions": [pos]}
            })

    async def request_orders_snapshot(self, symbol: str) -> None:
        """
        Fetch open orders for symbol and emit ORDERS_SNAPSHOT to runtime.
        Throttled per symbol to avoid REST spam.
        """
        now = time.monotonic()
        last = self._last_snapshot_request_ts.get(symbol, 0.0)
        if now - last < self._snapshot_request_interval_sec:
            self.logger.debug(
                f"[ExecPosV2] FORCE_SNAPSHOT_THROTTLED symbol={symbol} "
                f"elapsed={now - last:.2f}s < interval={self._snapshot_request_interval_sec}s"
            )
            return

        self._last_snapshot_request_ts[symbol] = now
        self.logger.info(
            f"[ExecPosV2] FORCE_SNAPSHOT_REQUEST symbol={symbol} reason=watchdog")

        orders = []
        if hasattr(self.adapter, "get_open_orders"):
            try:
                orders = await self.adapter.get_open_orders(symbol=symbol)
            except Exception as exc:
                self.logger.error(
                    f"Failed to refresh orders snapshot for {symbol}: {exc}", exc_info=True)
                return

        orders_event = {
            "kind": "ORDERS_SNAPSHOT",
            "payload": {"orders": orders}
        }
        await self.runtime.handle(orders_event)
        self.logger.info(
            f"[ExecPosV2] FORCE_SNAPSHOT_APPLIED symbol={symbol} orders={len(orders)}")

    def start(self) -> None:
        """
        Start the runtime.
        """
        self.logger.info("Starting V2RuntimeFacade...")
        # Schedule runtime.start() on the loop
        self._submit_to_loop(self.runtime.start(), source="facade_start")

    def stop(self) -> None:
        """
        Stop the runtime.
        """
        self.logger.info("Stopping V2RuntimeFacade...")
        self._submit_to_loop(self.runtime.shutdown(), source="facade_stop")
