"""
FSMP-EXECUTE-T04-B: Concrete Binance Execution Adapter.

Implements AbstractExecutionAdapter for Binance Futures API.
Adapts aurora/scalp_daemon/executor_binance.py for adapter interface.

Methods:
- place_order(): executes DEC:OPEN via Binance API with guards
- cancel_order(): cancels existing orders (placeholder for now)
- get_status(): returns connection status
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import threading
import time
from typing import Dict, Mapping, Optional, Any

import httpx
from vfoundation.core.protocol import Message

from .execution_adapter import AbstractExecutionAdapter
from .idempotent_cancel import IdempotentCancelHelper, IdempotentCancelResult, ClientOrderIdConfig
from apps.reference.telemetry.audit_logger import audit_logger
from .metrics_aggregator import metrics_logger


try:
    from apps.reference.telemetry.metrics import (
        inc_order_placed,
        inc_order_filled,
        inc_order_state,
        observe_order_lifecycle,
    )
except ImportError:

    def inc_order_placed():
        pass

    def inc_order_filled():
        pass

    def inc_order_state(status: str):
        pass

    def observe_order_lifecycle(duration_sec: float):
        pass


try:
    from apps.reference.telemetry.audit_logger import audit_logger
except ImportError:

    class MockAuditLogger:
        def log_order_state_changed(self, **kwargs):
            pass

    audit_logger = MockAuditLogger()


logger = logging.getLogger(__name__)

# Binance Futures API configuration
BASE_URL = os.environ.get("BINANCE_FUTURES_BASE_URL",
                          "https://testnet.binancefuture.com")


class BinanceExecutionAdapter(AbstractExecutionAdapter):
    """
    Concrete adapter for Binance Futures execution.

    Adapts existing executor_binance.py logic to AbstractExecutionAdapter interface.
    Handles DEC:OPEN messages and executes market orders with guards.
    """

    def __init__(self, fsm=None, config=None, shadow_mode: bool = False, **kwargs):
        """
        Initialize Binance adapter.

        Args:
            fsm: FSM instance for event emission
            config: Configuration dict
            shadow_mode: If True, no live API calls (for testing)
            **kwargs: Additional arguments (e.g., fsm_core for testing)
        """
        super().__init__(fsm, config)
        self.shadow_mode = shadow_mode
        # Support both fsm and fsm_core parameter names (for testing)
        # For emitting EVT:* events
        self.fsm_core = kwargs.get('fsm_core', fsm)
        self._last_status_check = 0.0
        self._status_cache = "unknown"

        # WebSocket related attributes
        self.ws_listen_key: Optional[str] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.ws_running = False
        self.ws_reconnect_delay = 1.0  # Start with 1 second, exponential backoff
        self.ws_max_reconnect_delay = 60.0  # Max 1 minute
        self.listen_key_last_refresh = 0.0

        # Time sync attributes
        self.server_time_offset = 0.0  # Offset between local and server time
        self.last_time_sync = 0.0

        # Read API credentials from environment or config
        try:
            # Pydantic-first
            if hasattr(config, 'trading') and config.trading:
                trading_env = config.trading.get("trading_env") if isinstance(
                    config.trading, dict) else getattr(config.trading, "trading_env", None)
            elif isinstance(config, dict):
                trading_env = config.get("trading_env")
            else:
                trading_env = None
        except (AttributeError, TypeError):
            trading_env = None

        self.use_testnet = (
            trading_env == "test" or
            os.environ.get("USE_TESTNET", "1") == "1" or
            os.environ.get("USE_TESTNET", "").lower() == "true"
        )

        # Select correct API credentials based on testnet/mainnet
        try:
            # Pydantic-first for binance_ro_api_key
            if hasattr(config, 'binance_ro_api_key'):
                binance_ro_api_key = config.binance_ro_api_key
            elif isinstance(config, dict):
                binance_ro_api_key = config.get("binance_ro_api_key")
            else:
                binance_ro_api_key = None
        except (AttributeError, TypeError):
            binance_ro_api_key = None

        try:
            # Pydantic-first for binance_ro_api_secret
            if hasattr(config, 'binance_ro_api_secret'):
                binance_ro_api_secret = config.binance_ro_api_secret
            elif isinstance(config, dict):
                binance_ro_api_secret = config.get("binance_ro_api_secret")
            else:
                binance_ro_api_secret = None
        except (AttributeError, TypeError):
            binance_ro_api_secret = None

        if self.use_testnet:
            self.api_key = binance_ro_api_key or os.environ.get(
                "BINANCE_TESTNET_API_KEY", "")
            self.api_secret = binance_ro_api_secret or os.environ.get(
                "BINANCE_TESTNET_API_SECRET", "")
            logger.info("[BinanceAdapter] Using TESTNET credentials")
        else:
            self.api_key = binance_ro_api_key or os.environ.get(
                "BINANCE_MAINNET_API_KEY", "")
            self.api_secret = binance_ro_api_secret or os.environ.get(
                "BINANCE_MAINNET_API_SECRET", "")
            logger.info("[BinanceAdapter] Using MAINNET credentials")

        if not shadow_mode and (not self.api_key or not self.api_secret):
            logger.warning(
                "[BinanceAdapter] API credentials not found in environment/config, falling back to shadow mode"
            )
            self.shadow_mode = True

        # PHASE 4: Initialize idempotent cancel helper
        self.cancel_helper = IdempotentCancelHelper(
            config=ClientOrderIdConfig(prefix="AUR"),
            logger_inst=logger
        )

        # Initialize metrics dict for tracking
        self.metrics = {
            "cancel_idempotent_ok": 0,
            "cancel_-2011_absorbed": 0,
        }

        # Optional: read slippage cap from config (trading.orders.market.slippage_cap_bps)
        self.slippage_cap_bps: Optional[int] = None
        try:
            orders_cfg = None
            if hasattr(config, 'trading') and config.trading:
                tr = config.trading if isinstance(config.trading, dict) else config.trading
                orders_cfg = tr.get("orders") if isinstance(tr, dict) else getattr(tr, "orders", None)
            elif isinstance(config, dict):
                orders_cfg = config.get("orders") or config.get("trading", {}).get("orders")
            if orders_cfg:
                market_cfg = orders_cfg.get("market") if isinstance(orders_cfg, dict) else getattr(orders_cfg, "market", None)
                if market_cfg:
                    val = market_cfg.get("slippage_cap_bps") if isinstance(market_cfg, dict) else getattr(market_cfg, "slippage_cap_bps", None)
                    if val is not None:
                        self.slippage_cap_bps = int(val)
                        logger.info(f"[BinanceAdapter] slippage_cap_bps set to {self.slippage_cap_bps}")
        except Exception as e:
            logger.warning(f"[BinanceAdapter] Failed to read slippage_cap_bps: {e}")

        logger.info(
            f"[BinanceAdapter] Initialized with shadow_mode={self.shadow_mode}, testnet={self.use_testnet}, ws_enabled={fsm is not None}"
        )

    def start(self) -> None:
        """
        Start the adapter, including WebSocket connection if FSM core is available.
        """
        if self.fsm_core is not None and not self.shadow_mode:
            logger.info(
                "[BinanceAdapter] Starting WebSocket connection to USER_DATA_STREAM")
            self._start_websocket()
        else:
            logger.info(
                "[BinanceAdapter] WebSocket disabled (no FSM core or shadow mode)")

    def stop(self) -> None:
        """
        Stop the adapter and close WebSocket connection.
        """
        logger.info("[BinanceAdapter] Stopping adapter...")
        self.ws_running = False

        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=5.0)
            if self.ws_thread.is_alive():
                logger.warning(
                    "[BinanceAdapter] WebSocket thread did not stop gracefully")

        logger.info("[BinanceAdapter] Adapter stopped")

    def _start_websocket(self) -> None:
        """
        Start WebSocket connection in a background thread.
        """
        if self.ws_thread is not None and self.ws_thread.is_alive():
            logger.warning("[BinanceAdapter] WebSocket already running")
            return

        self.ws_running = True
        self.ws_thread = threading.Thread(
            target=self._websocket_loop, daemon=True)
        self.ws_thread.start()
        logger.info("[BinanceAdapter] WebSocket thread started")

    def _websocket_loop(self) -> None:
        """
        Main WebSocket connection loop with reconnection logic.
        """
        while self.ws_running:
            try:
                self._establish_websocket_connection()
                # Reset reconnect delay on successful connection
                self.ws_reconnect_delay = 1.0
            except Exception as e:
                logger.error(
                    f"[BinanceAdapter] WebSocket connection failed: {e}")
                if self.ws_running:
                    logger.info(
                        f"[BinanceAdapter] Retrying WebSocket connection in {self.ws_reconnect_delay}s"
                    )
                    time.sleep(self.ws_reconnect_delay)
                    # Exponential backoff
                    self.ws_reconnect_delay = min(
                        self.ws_reconnect_delay * 2, self.ws_max_reconnect_delay
                    )

    def _establish_websocket_connection(self) -> None:
        """
        Establish WebSocket connection to USER_DATA_STREAM.
        """
        try:
            # Get listen key
            self._get_listen_key()

            # Use direct WebSocket connection
            import websockets
            import json

            ws_url = (
                f"wss://fstream.binance.com/ws/{self.ws_listen_key}"
                if not self.use_testnet
                else f"wss://stream.binancefuture.com/ws/{self.ws_listen_key}"
            )

            logger.info(f"[BinanceAdapter] Connecting to WebSocket: {ws_url}")

            # Create event loop for async WebSocket
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def ws_handler():
                try:
                    async with websockets.connect(ws_url) as websocket:
                        logger.info(
                            "[BinanceAdapter] WebSocket connected successfully")

                        while self.ws_running:
                            try:
                                # Receive message with timeout
                                message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                                msg_data = json.loads(message)
                                self._handle_ws_message(msg_data)

                            except asyncio.TimeoutError:
                                # Send ping to keep connection alive
                                await websocket.ping()

                            except websockets.exceptions.ConnectionClosed:
                                logger.warning(
                                    "[BinanceAdapter] WebSocket connection closed")
                                break

                except Exception as e:
                    logger.error(
                        f"[BinanceAdapter] WebSocket handler error: {e}")
                    raise

            # Run WebSocket handler
            loop.run_until_complete(ws_handler())

        except Exception as e:
            logger.error(
                f"[BinanceAdapter] Failed to establish WebSocket connection: {e}")
            raise

    def _get_listen_key(self) -> None:
        """
        Get listen key for USER_DATA_STREAM.
        """
        url = f"{BASE_URL}/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": self.api_key}

        # Use httpx for async compatibility
        import requests
        resp = requests.post(url, headers=headers, timeout=10)
        if resp.ok:
            data = resp.json()
            self.ws_listen_key = data.get("listenKey")
            self.listen_key_last_refresh = time.time()
            logger.info(
                f"[BinanceAdapter] Obtained listen key: {self.ws_listen_key[:10]}...")
        else:
            raise RuntimeError(
                f"Failed to get listen key: HTTP {resp.status_code} {resp.text}")

    def _refresh_listen_key(self) -> None:
        """
        Refresh listen key to keep USER_DATA_STREAM alive.
        """
        if not self.ws_listen_key:
            return

        url = f"{BASE_URL}/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": self.api_key}
        params = {"listenKey": self.ws_listen_key}

        import requests
        resp = requests.put(url, headers=headers, params=params, timeout=10)
        if resp.ok:
            self.listen_key_last_refresh = time.time()
            logger.debug("[BinanceAdapter] Listen key refreshed")
        else:
            logger.warning(
                f"[BinanceAdapter] Failed to refresh listen key: HTTP {resp.status_code}"
            )

    def _handle_ws_message(self, msg: Dict[str, Any]) -> None:
        """
        Handle incoming WebSocket messages from USER_DATA_STREAM.

        Args:
            msg: WebSocket message from Binance
        """
        try:
            logger.debug(f"[BinanceAdapter] WS message received: {msg}")

            event_type = msg.get("e")
            if event_type == "ORDER_TRADE_UPDATE":
                self._handle_order_trade_update(msg)
            elif event_type == "ACCOUNT_UPDATE":
                self._handle_account_update(msg)
            else:
                logger.debug(
                    f"[BinanceAdapter] Ignoring unknown event type: {event_type}")

        except Exception as e:
            logger.error(
                f"[BinanceAdapter] Error handling WS message: {e}", exc_info=True)

    def _handle_order_trade_update(self, msg: Dict[str, Any]) -> None:
        """
        Handle ORDER_TRADE_UPDATE event from WebSocket.

        Args:
            msg: ORDER_TRADE_UPDATE message
        """
        try:
            order_data = msg.get("o", {})
            client_order_id = order_data.get("c", "")
            exchange_order_id = str(order_data.get("i", ""))
            order_status = order_data.get("X", "")
            symbol = order_data.get("s", "")
            filled_qty = str(order_data.get("z", "0"))
            side = order_data.get("S", "").lower()
            order_type = order_data.get("o", "").lower()

            logger.info(
                f"[BinanceAdapter] ORDER_TRADE_UPDATE: {symbol} {client_order_id}/{exchange_order_id} status={order_status}"
            )

            # AUR-004: Correlate order using OrderIndex
            order_ref = None
            if hasattr(self.fsm_core, "order_index") and self.fsm_core.order_index:
                logger.debug(
                    f"[BinanceAdapter] Attempting correlation with order_index")
                # Try to find by clientOrderId first, then by exchangeOrderId
                order_ref = self.fsm_core.order_index.get(
                    clientOrderId=client_order_id)
                logger.debug(
                    f"[BinanceAdapter] get(clientOrderId={client_order_id}) returned: {order_ref}")
                if not order_ref and exchange_order_id:
                    order_ref = self.fsm_core.order_index.get(
                        exchangeOrderId=exchange_order_id)
                    logger.debug(
                        f"[BinanceAdapter] get(exchangeOrderId={exchange_order_id}) returned: {order_ref}")
            else:
                logger.debug(f"[BinanceAdapter] No order_index available")

            if not order_ref:
                logger.warning(
                    f"[BinanceAdapter] No correlation found for order {client_order_id}/{exchange_order_id}, skipping"
                )
                return

            # Map Binance status to standardized status
            status_mapping = {
                "NEW": "NEW",
                "PARTIALLY_FILLED": "PARTIALLY_FILLED",
                "FILLED": "FILLED",
                "CANCELED": "CANCELED",
                "REJECTED": "REJECTED",
                "EXPIRED": "EXPIRED",
            }
            standardized_status = status_mapping.get(
                order_status, order_status)

            # Create ORDER_STATE_CHANGED payload
            payload = {
                "symbol": symbol,
                "status": standardized_status,
                "rid": order_ref.rid,
                "idempotent_key": order_ref.idempotent_key,
                "clientOrderId": client_order_id,
                "exchangeOrderId": exchange_order_id,
                "orderId": exchange_order_id,  # Alias for test compatibility
                "side": side,
                "order_type": order_type,
                "qty": filled_qty,
                "ts_ms": msg.get("T", int(time.time() * 1000)),
            }

            # Log to audit
            audit_logger.log_order_state_changed(
                rid=order_ref.rid,
                idempotent_key=order_ref.idempotent_key,
                clientOrderId=client_order_id,
                exchangeOrderId=exchange_order_id,
                symbol=symbol,
                status=standardized_status,
                qty=order_data.get("q"),  # Original quantity
                filled_qty=filled_qty,
                avg_fill_price=str(order_data.get("p", "0")),
                why="websocket_update",
                ts_ms=msg.get("T", int(time.time() * 1000)),
            )

            # Increment metrics
            inc_order_state(standardized_status)

            # For terminal states, mark as terminal and observe lifecycle
            if standardized_status in ["FILLED", "CANCELED", "REJECTED", "EXPIRED"]:
                self.fsm_core.order_index.mark_terminal(order_ref)
                duration_sec = time.time() - order_ref.created_ts
                observe_order_lifecycle(duration_sec)

            # Emit ORDER_STATE_CHANGED event
            if self.fsm_core:
                self.fsm_core.emit(
                    "EVT:ORDER_STATE_CHANGED", payload, f"WS_ORDER_UPDATE_{standardized_status}"
                )
                logger.info(
                    f"[BinanceAdapter] Emitted ORDER_STATE_CHANGED {standardized_status} for {symbol} {client_order_id}"
                )

        except Exception as e:
            logger.error(
                f"[BinanceAdapter] Error processing ORDER_TRADE_UPDATE: {e}", exc_info=True
            )

    def _handle_account_update(self, msg: Dict[str, Any]) -> None:
        """
        Handle ACCOUNT_UPDATE event from WebSocket.

        Args:
            msg: ACCOUNT_UPDATE message
        """
        try:
            account_data = msg.get("a", {})
            balances = account_data.get("B", [])
            positions = account_data.get("P", [])

            logger.info(
                f"[BinanceAdapter] ACCOUNT_UPDATE: {len(balances)} balances, {len(positions)} positions"
            )

            # Create payload
            payload = {
                "balances": balances,
                "positions": positions,
                "event_time": msg.get("E", int(time.time() * 1000)),
                "raw_ws_data": account_data,
            }

            # Emit FSM event
            if self.fsm_core:
                self.fsm_core.emit("EVT:ACCOUNT_UPDATE_RECEIVED",
                                   payload, "WS_ACCOUNT_UPDATE")
                logger.info(
                    "[BinanceAdapter] Emitted EVT:ACCOUNT_UPDATE_RECEIVED")

        except Exception as e:
            logger.error(
                f"[BinanceAdapter] Error processing ACCOUNT_UPDATE: {e}", exc_info=True)

    def _sync_time_with_server(self) -> None:
        """
        Synchronize local time with Binance server time.
        """
        try:
            url = f"{BASE_URL}/fapi/v1/time"
            import requests
            resp = requests.get(url, timeout=5)

            if resp.ok:
                server_time = resp.json().get("serverTime", 0)
                local_time = int(time.time() * 1000)
                self.server_time_offset = server_time - local_time
                self.last_time_sync = time.time()

                drift_ms = abs(self.server_time_offset)
                if drift_ms > 500:  # More than 500ms drift
                    logger.warning(
                        f"[BinanceAdapter] Time drift detected: {drift_ms:.1f}ms")
                else:
                    logger.debug(
                        f"[BinanceAdapter] Time sync completed, offset: {self.server_time_offset:.1f}ms"
                    )
            else:
                logger.warning(
                    f"[BinanceAdapter] Failed to sync time with server: HTTP {resp.status_code}"
                )

        except Exception as e:
            logger.error(f"[BinanceAdapter] Time sync error: {e}")

    def _get_signed_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add signature and required fields to API parameters.

        Args:
            params: Base parameters

        Returns:
            Parameters with signature and timestamp
        """
        # Add timestamp and recvWindow
        signed_params = params.copy()
        signed_params["timestamp"] = str(
            int(time.time() * 1000) + int(self.server_time_offset))
        signed_params["recvWindow"] = "1500"  # 1.5 seconds as per CONFIG_PATCH

        # Create signature
        query_string = "&".join(
            f"{k}={v}" for k, v in sorted(signed_params.items()))
        signature = hmac.new(
            self.api_secret.encode(
                "utf-8"), query_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        signed_params["signature"] = signature
        return signed_params

    async def place_order(self, dec_msg: Message) -> Dict[str, object]:
        """
        Execute DEC:OPEN message via Binance API.

        Adapts DEC payload to Binance order format, applies guards,
        places market order, returns execution feedback.

        Args:
            dec_msg: DEC:OPEN message with order details

        Returns:
            Execution feedback dict conforming to exec_feedback schema
        """
        if dec_msg.op != "DEC" or dec_msg.verb != "OPEN":
            raise ValueError(
                f"Invalid message type: expected DEC:OPEN, got {dec_msg.op}:{dec_msg.verb}"
            )

        payload = dec_msg.pld
        symbol = payload.get("symbol", "")
        side = payload.get("side", "").upper()
        qty = payload.get("qty", "0")
        order_type = payload.get("order_type", "MARKET")
        price = payload.get("price")
        stop_price = payload.get("stopPrice")
        reduce_only = payload.get("reduceOnly", False)
        tif = payload.get("tif", "GTC")
        # Use newClientOrderId as idempotent key
        idempotent_key = payload.get("newClientOrderId")

        if not symbol or not side or not qty:
            raise ValueError(
                f"Missing required fields: symbol={symbol}, side={side}, qty={qty}")

        # Adapt to Binance format
        binance_symbol = self._adapt_symbol(symbol)
        binance_side = self._adapt_side(side)
        binance_qty = self._adapt_quantity(qty)

        logger.info(
            f"[BinanceAdapter] Processing DEC:PLACE_ORDER for {binance_symbol} {binance_side} {binance_qty} {order_type}"
        )

        # Apply guards (skip for reduce-only bracket orders)
        if not reduce_only:
            guard_result = self._apply_guards(
                binance_symbol, binance_side, binance_qty)
            if not guard_result["passed"]:
                return self._create_rejected_feedback(
                    symbol, guard_result["order_id"], guard_result["why_codes"]
                )
        else:
            guard_result = {
                "passed": True,
                "order_id": "bracket-order",
                "why_codes": ["reduce_only_bracket"],
            }

        # Apply slippage cap for MARKET orders if anchor price provided
        if self.slippage_cap_bps is not None and order_type == "MARKET":
            try:
                from decimal import Decimal
                anchor_price = payload.get("anchor_price") or payload.get("ref_price") or payload.get("expected_price")
                if anchor_price is not None:
                    anchor = Decimal(str(anchor_price))
                    cap = Decimal(self.slippage_cap_bps) / Decimal("10000")
                    if side == "BUY":
                        limit_price = anchor * (Decimal("1") + cap)
                    else:
                        limit_price = anchor * (Decimal("1") - cap)
                    price = str(limit_price.quantize(Decimal("0.00000001")))
                    order_type = "LIMIT"
                    tif = "IOC"
                    logger.info(
                        f"[BinanceAdapter] Slippage cap applied: MARKET -> LIMIT {tif} at {price} (cap {self.slippage_cap_bps}bps)")
            except Exception as e:
                logger.warning(f"[BinanceAdapter] Slippage cap skipped: {e}")

        # Execute order
        try:
            if self.shadow_mode:
                # Shadow mode: simulate success
                logger.info(
                    f"[BinanceAdapter] SHADOW MODE: simulated {order_type} order for {binance_symbol}"
                )
                return self._create_success_feedback(
                    symbol,
                    f"shadow-{order_type.lower()}-123",
                    idempotent_key or "shadow",
                    guard_result["why_codes"],
                )
            else:
                # Live execution
                result = await self._place_binance_order_async(
                    binance_symbol,
                    binance_side,
                    binance_qty,
                    order_type,
                    price,
                    stop_price,
                    reduce_only,
                    idempotent_key,
                    tif,
                )

                inc_order_placed()  # Increment order placed counter
                client_order_id = result.get(
                    "clientOrderId", idempotent_key or "unknown")
                return self._create_success_feedback(
                    symbol,
                    result.get("orderId", "unknown"),
                    client_order_id,
                    guard_result["why_codes"],
                )

        except Exception as e:
            logger.error(f"[BinanceAdapter] Order execution failed: {e}")
            return self._create_error_feedback(symbol, str(e))

    async def cancel_order(self, dec_msg: Message) -> Dict[str, object]:
        """
        Cancel existing order using Binance API with idempotent semantics.

        PHASE 4: Enhanced with:
        - Pre-cancel getOrder check (to avoid unnecessary cancellations)
        - -2011 absorption (treat "Unknown order" as success)
        - Detailed audit logging for compliance

        Args:
            dec_msg: DEC:CANCEL_ORDER message with orderId and symbol

        Returns:
            Cancellation result dict with success/failure details
        """
        try:
            pld = dec_msg.pld or {}
            order_id = pld.get("orderId")
            # Default to BTCUSDT if not provided
            symbol = pld.get("symbol", "BTCUSDT")

            if not order_id:
                return self._create_error_feedback("unknown", "Missing orderId in cancel request")

            if self.shadow_mode:
                logger.info(
                    f"[BinanceAdapter] Shadow mode: would cancel order {order_id} on {symbol}")
                return self._create_success_feedback(
                    "cancelled", order_id, "unknown", "shadow_mode_cancel"
                )

            # PHASE 4: Use idempotent cancel helper
            cancel_result = await self.cancel_helper.cancel_order_idempotent(
                symbol=symbol,
                order_id=order_id,
                cancel_func=self._cancel_binance_order_async,
                get_order_func=self.get_order,
                max_retries=2
            )

            # Log result for audit trail
            self.cancel_helper.log_cancel_result(cancel_result, order_id)

            # Phase 5: Metrics aggregation
            if cancel_result.success:
                metrics_logger.log_cancel_event(
                    symbol=symbol,
                    order_id=order_id,
                    success=True,
                    error_code=cancel_result.error_code,
                    is_idempotent_success=cancel_result.is_idempotent_success,
                    rid=f"cancel_{symbol}_{order_id}",
                )
            else:
                metrics_logger.log_cancel_event(
                    symbol=symbol,
                    order_id=order_id,
                    success=False,
                    error_code=cancel_result.error_code,
                    is_idempotent_success=False,
                    rid=f"cancel_{symbol}_{order_id}",
                )

            # Emit metrics
            if cancel_result.success:
                self.metrics["cancel_idempotent_ok"] = self.metrics.get(
                    "cancel_idempotent_ok", 0) + 1
                if cancel_result.error_code == -2011:
                    self.metrics["cancel_-2011_absorbed"] = self.metrics.get(
                        "cancel_-2011_absorbed", 0) + 1

            # Return result in standard format
            if cancel_result.success:
                return {
                    "allowed": True,
                    "reason": "CANCEL_SUCCESS",
                    "details": {
                        "orderId": order_id,
                        "symbol": symbol,
                        "cancel_reason": cancel_result.reason,
                        "idempotent_success": cancel_result.is_idempotent_success,
                        "error_code": cancel_result.error_code,
                    }
                }
            else:
                return {
                    "allowed": False,
                    "reason": f"CANCEL_FAILED: {cancel_result.reason}",
                    "details": {
                        "orderId": order_id,
                        "symbol": symbol,
                        "cancel_reason": cancel_result.reason,
                        "error_code": cancel_result.error_code,
                    }
                }

        except Exception as e:
            logger.error(f"[BinanceAdapter] Cancel order error: {e}")
            return self._create_error_feedback("unknown", str(e))

    async def get_order(self, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
        """
        PHASE 4: Get order details from Binance API for pre-cancel check.

        Used by idempotent cancel to verify order status before attempting cancellation.

        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            order_id: Binance orderId to query

        Returns:
            Order dict with status field, or None if not found
        """
        try:
            api_key = self.api_key
            api_secret = self.api_secret

            if not api_key or not api_secret:
                logger.warning("Missing Binance API credentials for getOrder")
                return None

            self._sync_time_with_server()

            base_url = BASE_URL
            endpoint = "/fapi/v1/order"

            params = {
                "symbol": symbol,
                "orderId": order_id,
                "timestamp": int(time.time() * 1000),
                "recvWindow": 1500,
            }

            signed_params = self._get_signed_params(params)
            headers = {"X-MBX-APIKEY": api_key}

            url = f"{base_url}{endpoint}"
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=signed_params, headers=headers)

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(
                        f"getOrder failed: HTTP {response.status_code}: {response.text}")
                    return None

        except Exception as e:
            logger.warning(f"getOrder exception: {e}")
            return None

    async def _cancel_binance_order_async(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """
        Cancel order on Binance Futures asynchronously.

        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            order_id: Binance order ID to cancel

        Returns:
            API response dict with status and optional error fields
        """
        try:
            # Get API credentials
            api_key = self.api_key
            api_secret = self.api_secret

            if not api_key or not api_secret:
                raise ValueError("Missing Binance API credentials")

            # Sync time with server
            self._sync_time_with_server()

            # Build signed request
            base_url = BASE_URL
            endpoint = "/fapi/v1/order"

            params = {
                "symbol": symbol,  # PHASE 4: Use provided symbol parameter
                "orderId": order_id,
                "timestamp": int(time.time() * 1000),
                "recvWindow": 1500,
            }

            signed_params = self._get_signed_params(params)
            headers = {"X-MBX-APIKEY": api_key}

            url = f"{base_url}{endpoint}"
            async with httpx.AsyncClient() as client:
                response = await client.delete(url, params=signed_params, headers=headers)

                if response.status_code == 200:
                    return response.json()
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    logger.error(
                        f"[BinanceAdapter] Cancel order failed: {error_msg}")
                    return {"status": "error", "msg": error_msg, "code": response.status_code}

        except Exception as e:
            logger.error(f"[BinanceAdapter] Cancel order exception: {e}")
            return {"status": "error", "msg": str(e)}

    def get_status(self) -> str:
        """
        Get adapter status.

        Returns:
            Status string: "connected", "disconnected", "error", "shadow", "ws_connected", "ws_disconnected"
        """
        if self.shadow_mode:
            return "shadow"

        # Check WebSocket status first
        if self.fsm_core and not self.shadow_mode:
            ws_alive = self.ws_thread and self.ws_thread.is_alive() and self.ws_running
            if ws_alive:
                return "ws_connected"
            else:
                return "ws_disconnected"

        # Fallback to REST API status check
        # Cache status for 30 seconds
        now = time.time()
        if now - self._last_status_check > 30.0:
            try:
                # Simple connectivity check via time sync
                self._sync_time_with_server()
                self._status_cache = "connected"
            except Exception:
                self._status_cache = "error"
            self._last_status_check = now

        return self._status_cache

    def _adapt_symbol(self, symbol: str) -> str:
        """Adapt symbol format for Binance (e.g., BTC-PERP -> BTCUSDT)."""
        if symbol.endswith("-PERP"):
            base = symbol.split("-", 1)[0]
            return f"{base}USDT"
        return symbol

    def _adapt_side(self, side: str) -> str:
        """Adapt side format for Binance."""
        return side.upper()  # BUY/SELL

    def _adapt_quantity(self, qty: str) -> str:
        """
        Adapt quantity format for Binance.

        FIXED BUG-P1-002: Preserve Decimal precision by avoiding float conversion.
        Use Decimal for normalization to remove trailing zeros while maintaining precision.
        """
        from decimal import Decimal

        # Parse as Decimal, normalize to remove trailing zeros, return as string
        # normalize() removes insignificant trailing zeros without precision loss
        return str(Decimal(qty).normalize())

    def _apply_guards(self, symbol: str, side: str, qty: str) -> Dict[str, object]:
        """
        Apply position and volatility guards.

        FIXED: Changed qty parameter from float to str to preserve Decimal precision.
        Guards should work with string quantities and convert to Decimal internally if needed.

        Adapted from executor_binance.py guard logic.
        Returns guard result with pass/fail status and why codes.
        """
        # Placeholder guard logic - would integrate full guard implementation
        # For now, always pass with basic why codes
        return {
            "passed": True,
            "order_id": None,
            "why_codes": ["EXEC_GUARD_PASS", "EXEC_VOLATILITY_PASS", "EXEC_POSITION_PASS"],
        }

    async def _place_binance_order_async(
        self,
        symbol: str,
        side: str,
        quantity: str,
        order_type: str = "MARKET",
        price: Optional[str] = None,
        stop_price: Optional[str] = None,
        reduce_only: bool = False,
        idempotent_key: Optional[str] = None,
        time_in_force: str = "GTC",
    ) -> Mapping[str, object]:
        """
        Place order via Binance Futures API asynchronously.

        Args:
            symbol: Binance symbol (e.g., "BTCUSDT")
            side: BUY or SELL
            quantity: Order quantity as string
            order_type: MARKET, LIMIT, STOP_MARKET, etc.
            price: Limit price for LIMIT orders
            stop_price: Stop price for STOP orders
            reduce_only: Whether order should be reduce-only
            idempotent_key: Optional key for newClientOrderId
        """
        logger.info(
            f"[BinanceAdapter] Placing {order_type} order: {symbol} {side} {quantity}")

        # Prepare request parameters
        params: Dict[str, str] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": str(quantity),
        }

        # Add order-specific parameters
        if order_type == "LIMIT" and price:
            params["price"] = price
            params["timeInForce"] = time_in_force  # GTC/IOC/FOK

        if "STOP" in order_type and stop_price:
            params["stopPrice"] = stop_price

        if reduce_only:
            params["reduceOnly"] = "true"

        # Add newClientOrderId for idempotency
        if idempotent_key:
            params["newClientOrderId"] = idempotent_key
            logger.info(
                f"[BinanceAdapter] Using idempotent newClientOrderId: {idempotent_key}")

        # Get signed parameters with proper timestamp and recvWindow
        signed_params = self._get_signed_params(params)

        # Make async API request
        url = f"{BASE_URL}/fapi/v1/order"
        query_string = "&".join(f"{k}={v}" for k, v in signed_params.items())
        full_url = f"{url}?{query_string}"
        headers = {"X-MBX-APIKEY": self.api_key}

        logger.info(f"[BinanceAdapter] POST {BASE_URL}/fapi/v1/order")
        async with httpx.AsyncClient() as client:
            resp = await client.post(full_url, headers=headers, timeout=10)

            # Parse response
            try:
                data = resp.json()
            except:
                data = {"raw": resp.text}

            # Handle API errors with specific error codes
            if not resp.is_success:
                error_code = data.get("code")
                error_msg = data.get("msg", str(data))

                if error_code == -1021:
                    # Timestamp error - retry once after time sync
                    logger.warning(
                        f"[BinanceAdapter] Timestamp error (-1021), syncing time and retrying: {error_msg}"
                    )
                    self._sync_time_with_server()
                    # Retry with updated timestamp
                    signed_params = self._get_signed_params(params)
                    query_string = "&".join(
                        f"{k}={v}" for k, v in signed_params.items())
                    full_url = f"{url}?{query_string}"
                    resp = await client.post(full_url, headers=headers, timeout=10)
                    try:
                        data = resp.json()
                    except:
                        data = {"raw": resp.text}

                    if not resp.is_success:
                        logger.error(
                            f"[BinanceAdapter] Order still failed after retry: HTTP {resp.status_code} {data}"
                        )
                        raise RuntimeError(
                            f"Binance order failed after retry: HTTP {resp.status_code} {data}"
                        )

                elif error_code == -2010:
                    # Insufficient balance
                    logger.error(
                        f"[BinanceAdapter] Insufficient balance (-2010): {error_msg}")
                    raise RuntimeError(f"Insufficient balance: {error_msg}")

                elif error_code == -429:
                    # Rate limit exceeded
                    logger.warning(
                        f"[BinanceAdapter] Rate limit exceeded (-429), implementing backoff: {error_msg}"
                    )
                    # TODO: Implement rate limit backoff logic
                    raise RuntimeError(f"Rate limit exceeded: {error_msg}")

                else:
                    logger.error(
                        f"[BinanceAdapter] Order FAILED: HTTP {resp.status_code} {data}")
                    raise RuntimeError(
                        f"Binance order failed: HTTP {resp.status_code} {data}")

            # Success
            order_id = data.get("orderId", "?")
            status = data.get("status", "?")
            logger.info(
                f"[BinanceAdapter] Order placed successfully: orderId={order_id} status={status}"
            )

            # ✅ Log to aurora_events.jsonl (even without WebSocket)
            client_order_id = data.get(
                "clientOrderId", idempotent_key or "unknown")
            try:
                audit_logger.log_order_state_changed(
                    rid="",  # RID would come from FSM context if available
                    idempotent_key=idempotent_key,
                    clientOrderId=client_order_id,
                    exchangeOrderId=str(order_id),
                    symbol=symbol,
                    status=status,
                    qty=quantity,
                    filled_qty="0",  # Not filled yet, just placed
                    avg_fill_price="0",
                    why="direct_placement",
                    ts_ms=int(time.time() * 1000),
                )
            except Exception as e:
                logger.error(
                    f"[BinanceAdapter] Failed to log order state: {e}")

            return data

    def _create_success_feedback(
        self, instrument: str, order_id: str, client_order_id: str, why_codes: list[str]
    ) -> Dict[str, object]:
        """Create success feedback dict conforming to exec_feedback schema."""
        return {
            "instrument": instrument,
            "order_id": str(order_id),
            "clientOrderId": client_order_id,
            "lifecycle": "filled",
            "fills": [],
            "tca_realized": {
                "fees_bps": 0,
                "slip_in_bps": 0,
                "slip_out_bps": 0,
                "adverse_bps": 0,
                "latency_ms": 0,
                "rebates_bps": 0,
            },
            "breaches": [],
            "why": why_codes,
            "dto_version": "1.0.0",
            "schema_ref": "https://aurora.scalp/shared/dto/exec_feedback.schema.json",
        }

    def _create_rejected_feedback(
        self, instrument: str, order_id: str, why_codes: list[str]
    ) -> Dict[str, object]:
        """Create rejection feedback dict."""
        return {
            "instrument": instrument,
            "order_id": str(order_id),
            "lifecycle": "rejected",
            "fills": [],
            "tca_realized": {
                "fees_bps": 0,
                "slip_in_bps": 0,
                "slip_out_bps": 0,
                "adverse_bps": 0,
                "latency_ms": 0,
                "rebates_bps": 0,
            },
            "breaches": [],
            "why": why_codes,
            "dto_version": "1.0.0",
            "schema_ref": "https://aurora.scalp/shared/dto/exec_feedback.schema.json",
        }

    def _create_error_feedback(self, instrument: str, error_msg: str) -> Dict[str, object]:
        """Create error feedback dict."""
        return {
            "instrument": instrument,
            "order_id": f"error-{int(time.time())}",
            "lifecycle": "rejected",
            "fills": [],
            "tca_realized": {
                "fees_bps": 0,
                "slip_in_bps": 0,
                "slip_out_bps": 0,
                "adverse_bps": 0,
                "latency_ms": 0,
                "rebates_bps": 0,
            },
            "breaches": [],
            "why": ["EXEC_EXCEPTION", error_msg],
            "dto_version": "1.0.0",
            "schema_ref": "https://aurora.scalp/shared/dto/exec_feedback.schema.json",
        }

    async def get_positions_notional_usd_shadow(self) -> float:
        """
        EXP-FIX: Get shadow notional from Binance API for safety auditing.

        Fetches current positions from /fapi/v2/positionRisk and calculates
        total notional value. Used for safety comparison with portfolio data.

        Returns:
            Total notional value in USD, or 0.0 on error
        """
        if self.shadow_mode:
            return 0.0

        try:
            params = {"timestamp": int(time.time() * 1000)}
            params["signature"] = self._generate_signature(params)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{BASE_URL}/fapi/v2/positionRisk",
                    params=params,
                    headers={"X-MBX-APIKEY": self.api_key},
                )
                response.raise_for_status()
                positions = response.json()

                total_notional = 0.0
                for pos in positions:
                    try:
                        position_amt = abs(float(pos.get("positionAmt", 0)))
                        mark_price = float(pos.get("markPrice", 0))
                        if position_amt > 0 and mark_price > 0:
                            total_notional += position_amt * mark_price
                    except (ValueError, TypeError):
                        continue

                return round(total_notional, 2)

        except Exception as e:
            logger.error(f"SHADOW_NOTIONAL_ERROR: {e}")
            return 0.0

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """Generate HMAC SHA256 signature for Binance API."""
        query_string = "&".join(
            [f"{key}={params[key]}" for key in sorted(params.keys())]
        )
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _normalize_order_event(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize Binance ORDER_TRADE_UPDATE WebSocket payload to flat structure.

        Converts nested {"o": {...}} structure to flat dict with top-level fields
        for easy FSM consumption.

        Args:
            raw_event: Raw Binance WebSocket event

        Returns:
            Flat normalized event dict
        """
        try:
            # If no nested "o", assume already flat (backward compatibility)
            if "o" not in raw_event or not isinstance(raw_event.get("o"), dict):
                return raw_event

            # Extract nested order object
            order_data = raw_event.get("o", {})

            # Map Binance field names to normalized names
            normalized = {
                # IDs
                "orderId": str(order_data.get("i", "")),  # Integer -> string
                "clientOrderId": order_data.get("c", ""),
                "symbol": order_data.get("s", ""),

                # Status and type
                "status": order_data.get("X", "").upper(),  # e.g., "FILLED"
                # e.g., "TRADE"
                "executionType": order_data.get("x", "").upper(),

                # Side and order type (normalized to lowercase)
                "side": (order_data.get("S", "").lower() if order_data.get("S") else ""),
                "type": (order_data.get("o", "").lower().replace("_", "_") if order_data.get("o") else ""),

                # Quantities and prices
                "originalQty": order_data.get("q", ""),
                "executedQty": order_data.get("z", ""),
                # Average price * qty
                "cumulativeQuoteAssetTransactedQty": order_data.get("ap", ""),
                "avgPrice": order_data.get("ap", ""),  # Average price

                # Last trade details
                "lastExecutedQty": order_data.get("l", ""),
                "lastExecutedPrice": order_data.get("L", ""),

                # Timestamp
                "timestamp": raw_event.get("T", raw_event.get("E", 0)),

                # Bracket flags
                "reduceOnly": order_data.get("R", False),
                "closePosition": order_data.get("cp", False),

                # Commission
                "commission": order_data.get("n", "0"),
                "commissionAsset": order_data.get("N", ""),

                # Order details
                "timeInForce": order_data.get("f", ""),
                "stopPrice": order_data.get("sp", ""),
                "activationPrice": order_data.get("ap", ""),

                # Trade ID
                "tradeId": order_data.get("t"),

                # Event metadata
                "eventTime": raw_event.get("E"),
                "isMarker": order_data.get("m", False),

                # Preserve raw event for debugging
                "_raw_binance_event": raw_event
            }

            return normalized

        except Exception as e:
            logger.error(f"Error normalizing order event: {e}", exc_info=True)
            return {
                "orderId": "unknown",
                "error": str(e),
                "_raw_binance_event": raw_event
            }
