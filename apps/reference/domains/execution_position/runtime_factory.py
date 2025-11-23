from typing import Any, Dict, Optional, Protocol
import logging
import time
import asyncio

# Import shadow runtime and adapter
from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.event_adapter import MessageToRuntimeEventAdapter
from apps.reference.domains.execution_position.adapter_factory import build_execution_adapter

LOG = logging.getLogger(__name__)


class ExecutionRuntime(Protocol):
    """Protocol that runtimes must satisfy."""

    def handle(self, message: Any) -> Any: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...


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
        fsm.listen("EVT:TRADE_INTENT_PROPOSED",
                   facade.on_trade_intent_proposed)
        LOG.info(
            "✅ V2RuntimeFacade subscribed to EVT:TRADE_EXECUTED and EVT:ACCOUNT_UPDATE_RECEIVED")

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
        self.event_adapter = MessageToRuntimeEventAdapter()
        self.logger = logging.getLogger("ExecPosRuntimeV2Facade")
        self.runtime.set_snapshot_refresh_hook(self.request_orders_snapshot)
        self._snapshot_request_interval_sec = 5.0
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
        symbol = getattr(message, "pld", {}).get(
            "symbol") if hasattr(message, "pld") else None
        self.logger.debug(
            f"V2RuntimeFacade.handle() received: op={op}, verb={verb}, symbol={symbol}")

        # Convert to RuntimeEvent
        runtime_event = self.event_adapter.from_legacy_message(message)

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
            self.logger.warning(
                f"⚠️ Event adapter returned None for op={op}, verb={verb}, symbol={symbol} - message not processed")
            return None

    def hydrate(self, position_data: Dict[str, Any]) -> None:
        self.runtime.hydrate(position_data)

    def get_agg_oco_state_snapshot(self, symbol: str = None, side: str = None, as_dict: bool = True) -> Any:
        return {}

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
        symbol = trade_intent.get("symbol")
        side = str(trade_intent.get("side", "")).upper()
        quantity = trade_intent.get("quantity") or trade_intent.get("qty")
        price = trade_intent.get("price") or trade_intent.get("limit_price")
        rid = trade_intent.get("rid") or trade_intent.get("request_id")
        metadata = trade_intent.get("metadata") or {}
        idempotent_key = trade_intent.get(
            "idempotent_key") or metadata.get("idempotent_key")

        if not symbol or not side or quantity in (None, ""):
            self.logger.warning(
                "[RuntimeFacade-S4] Missing required fields in TRADE_INTENT_PROPOSED; skipping",
                extra={"symbol": symbol, "side": side, "quantity": quantity},
            )
            return None

        runtime_event = {
            "kind": "ENTRY_INTENT",
            "symbol": symbol,
            "payload": {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "source": "DecisionMaking",
                "rid": rid,
                "idempotent_key": idempotent_key,
            },
        }

        self.logger.info("[RuntimeFacade-S4] scheduling event: kind=ENTRY_INTENT source=decision symbol=%s",
                         symbol)
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
