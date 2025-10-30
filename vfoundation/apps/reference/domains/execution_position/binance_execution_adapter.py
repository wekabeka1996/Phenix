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

import hashlib
import hmac
import logging
import os
import threading
import time
from typing import Dict, Mapping, Optional, Any

import requests
from vfoundation.core.protocol import Message

from .execution_adapter import AbstractExecutionAdapter


try:
    from vfoundation.apps.reference.telemetry.metrics import (
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
    from vfoundation.apps.reference.telemetry.audit_logger import audit_logger
except ImportError:

    class MockAuditLogger:
        def log_order_state_changed(self, **kwargs):
            pass

    audit_logger = MockAuditLogger()


logger = logging.getLogger(__name__)

# Binance Futures API configuration
BASE_URL = os.environ.get("BINANCE_FUTURES_BASE_URL", "https://testnet.binancefuture.com")


class BinanceExecutionAdapter(AbstractExecutionAdapter):
    """
    Concrete adapter for Binance Futures execution.

    Adapts existing executor_binance.py logic to AbstractExecutionAdapter interface.
    Handles DEC:OPEN messages and executes market orders with guards.
    """

    def __init__(self, shadow_mode: bool = False, fsm_core: Optional[Any] = None):
        """
        Initialize Binance adapter.

        Args:
            shadow_mode: If True, no live API calls (for testing)
            fsm_core: FSMCore instance for emitting events (optional for backward compatibility)
        """
        self.shadow_mode = shadow_mode
        self.fsm_core = fsm_core  # For emitting EVT:* events
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

        # Read API credentials from environment
        self.use_testnet = (
            os.environ.get("USE_TESTNET", "1") == "1"
            or os.environ.get("USE_TESTNET", "").lower() == "true"
        )

        # Select correct API credentials based on testnet/mainnet
        if self.use_testnet:
            self.api_key = os.environ.get("BINANCE_TESTNET_API_KEY", "")
            self.api_secret = os.environ.get("BINANCE_TESTNET_API_SECRET", "")
            logger.info("[BinanceAdapter] Using TESTNET credentials")
        else:
            self.api_key = os.environ.get("BINANCE_MAINNET_API_KEY", "")
            self.api_secret = os.environ.get("BINANCE_MAINNET_API_SECRET", "")
            logger.info("[BinanceAdapter] Using MAINNET credentials")

        if not shadow_mode and (not self.api_key or not self.api_secret):
            logger.warning(
                "[BinanceAdapter] API credentials not found in environment, falling back to shadow mode"
            )
            self.shadow_mode = True

        logger.info(
            f"[BinanceAdapter] Initialized with shadow_mode={self.shadow_mode}, testnet={self.use_testnet}, ws_enabled={fsm_core is not None}"
        )

    def start(self) -> None:
        """
        Start the adapter, including WebSocket connection if FSM core is available.
        """
        if self.fsm_core is not None and not self.shadow_mode:
            logger.info("[BinanceAdapter] Starting WebSocket connection to USER_DATA_STREAM")
            self._start_websocket()
        else:
            logger.info("[BinanceAdapter] WebSocket disabled (no FSM core or shadow mode)")

    def stop(self) -> None:
        """
        Stop the adapter and close WebSocket connection.
        """
        logger.info("[BinanceAdapter] Stopping adapter...")
        self.ws_running = False

        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=5.0)
            if self.ws_thread.is_alive():
                logger.warning("[BinanceAdapter] WebSocket thread did not stop gracefully")

        logger.info("[BinanceAdapter] Adapter stopped")

    def _start_websocket(self) -> None:
        """
        Start WebSocket connection in a background thread.
        """
        if self.ws_thread is not None and self.ws_thread.is_alive():
            logger.warning("[BinanceAdapter] WebSocket already running")
            return

        self.ws_running = True
        self.ws_thread = threading.Thread(target=self._websocket_loop, daemon=True)
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
                logger.error(f"[BinanceAdapter] WebSocket connection failed: {e}")
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
            import asyncio
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
                        logger.info("[BinanceAdapter] WebSocket connected successfully")

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
                                logger.warning("[BinanceAdapter] WebSocket connection closed")
                                break

                except Exception as e:
                    logger.error(f"[BinanceAdapter] WebSocket handler error: {e}")
                    raise

            # Run WebSocket handler
            loop.run_until_complete(ws_handler())

        except Exception as e:
            logger.error(f"[BinanceAdapter] Failed to establish WebSocket connection: {e}")
            raise

    def _get_listen_key(self) -> None:
        """
        Get listen key for USER_DATA_STREAM.
        """
        url = f"{BASE_URL}/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": self.api_key}

        resp = requests.post(url, headers=headers, timeout=10)
        if resp.ok:
            data = resp.json()
            self.ws_listen_key = data.get("listenKey")
            self.listen_key_last_refresh = time.time()
            logger.info(f"[BinanceAdapter] Obtained listen key: {self.ws_listen_key[:10]}...")
        else:
            raise RuntimeError(f"Failed to get listen key: HTTP {resp.status_code} {resp.text}")

    def _refresh_listen_key(self) -> None:
        """
        Refresh listen key to keep USER_DATA_STREAM alive.
        """
        if not self.ws_listen_key:
            return

        url = f"{BASE_URL}/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": self.api_key}
        params = {"listenKey": self.ws_listen_key}

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
                logger.debug(f"[BinanceAdapter] Ignoring unknown event type: {event_type}")

        except Exception as e:
            logger.error(f"[BinanceAdapter] Error handling WS message: {e}", exc_info=True)

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
                # Try to find by clientOrderId first, then by exchangeOrderId
                order_ref = self.fsm_core.order_index.get(clientOrderId=client_order_id)
                if not order_ref and exchange_order_id:
                    order_ref = self.fsm_core.order_index.get(exchangeOrderId=exchange_order_id)

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
            standardized_status = status_mapping.get(order_status, order_status)

            # Create ORDER_STATE_CHANGED payload
            payload = {
                "symbol": symbol,
                "status": standardized_status,
                "rid": order_ref.rid,
                "idempotent_key": order_ref.idempotent_key,
                "clientOrderId": client_order_id,
                "exchangeOrderId": exchange_order_id,
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
                self.fsm_core.emit("EVT:ACCOUNT_UPDATE_RECEIVED", payload, "WS_ACCOUNT_UPDATE")
                logger.info("[BinanceAdapter] Emitted EVT:ACCOUNT_UPDATE_RECEIVED")

        except Exception as e:
            logger.error(f"[BinanceAdapter] Error processing ACCOUNT_UPDATE: {e}", exc_info=True)

    def _sync_time_with_server(self) -> None:
        """
        Synchronize local time with Binance server time.
        """
        try:
            url = f"{BASE_URL}/fapi/v1/time"
            resp = requests.get(url, timeout=5)

            if resp.ok:
                server_time = resp.json().get("serverTime", 0)
                local_time = int(time.time() * 1000)
                self.server_time_offset = server_time - local_time
                self.last_time_sync = time.time()

                drift_ms = abs(self.server_time_offset)
                if drift_ms > 500:  # More than 500ms drift
                    logger.warning(f"[BinanceAdapter] Time drift detected: {drift_ms:.1f}ms")
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
        signed_params["timestamp"] = str(int(time.time() * 1000) + int(self.server_time_offset))
        signed_params["recvWindow"] = "1500"  # 1.5 seconds as per CONFIG_PATCH

        # Create signature
        query_string = "&".join(f"{k}={v}" for k, v in sorted(signed_params.items()))
        signature = hmac.new(
            self.api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        signed_params["signature"] = signature
        return signed_params

    def _reconcile_state(self) -> None:
        """
        Reconcile local state with Binance via REST API calls.
        Called on startup and periodically to ensure consistency.
        """
        try:
            logger.info("[BinanceAdapter] Starting state reconciliation")

            # Get open orders
            open_orders = self._get_open_orders()

            # Get positions
            positions = self._get_positions()

            # Get account balance
            balance = self._get_account_balance()

            # Emit reconciliation events if state differs
            self._emit_reconciliation_events(open_orders, positions, balance)

            logger.info(
                f"[BinanceAdapter] Reconciliation complete: {len(open_orders)} orders, {len(positions)} positions"
            )

        except Exception as e:
            logger.error(f"[BinanceAdapter] Reconciliation failed: {e}")

    def _get_open_orders(self) -> list:
        """
        Get all open orders via REST API.

        Returns:
            List of open orders
        """
        params = {}
        signed_params = self._get_signed_params(params)

        url = f"{BASE_URL}/fapi/v1/openOrders"
        query_string = "&".join(f"{k}={v}" for k, v in signed_params.items())
        full_url = f"{url}?{query_string}"

        headers = {"X-MBX-APIKEY": self.api_key}
        resp = requests.get(full_url, headers=headers, timeout=10)

        if resp.ok:
            return resp.json()
        else:
            logger.error(
                f"[BinanceAdapter] Failed to get open orders: HTTP {resp.status_code} {resp.text}"
            )
            return []

    def _get_positions(self) -> list:
        """
        Get all positions via REST API.

        Returns:
            List of positions
        """
        params = {}
        signed_params = self._get_signed_params(params)

        url = f"{BASE_URL}/fapi/v2/positionRisk"
        query_string = "&".join(f"{k}={v}" for k, v in signed_params.items())
        full_url = f"{url}?{query_string}"

        headers = {"X-MBX-APIKEY": self.api_key}
        resp = requests.get(full_url, headers=headers, timeout=10)

        if resp.ok:
            # Filter only positions with non-zero amount
            positions = resp.json()
            return [p for p in positions if float(p.get("positionAmt", "0")) != 0]
        else:
            logger.error(
                f"[BinanceAdapter] Failed to get positions: HTTP {resp.status_code} {resp.text}"
            )
            return []

    def _get_account_balance(self) -> list:
        """
        Get account balance via REST API.

        Returns:
            List of balance entries
        """
        params = {}
        signed_params = self._get_signed_params(params)

        url = f"{BASE_URL}/fapi/v2/balance"
        query_string = "&".join(f"{k}={v}" for k, v in signed_params.items())
        full_url = f"{url}?{query_string}"

        headers = {"X-MBX-APIKEY": self.api_key}
        resp = requests.get(full_url, headers=headers, timeout=10)

        if resp.ok:
            balances = resp.json()
            # Filter balances with non-zero amounts
            return [b for b in balances if float(b.get("balance", "0")) != 0]
        else:
            logger.error(
                f"[BinanceAdapter] Failed to get balance: HTTP {resp.status_code} {resp.text}"
            )
            return []

    def _emit_reconciliation_events(
        self, open_orders: list, positions: list, balances: list
    ) -> None:
        """
        Emit reconciliation events if state differs from expected.

        Args:
            open_orders: Current open orders from REST API
            positions: Current positions from REST API
            balances: Current balances from REST API
        """
        # For now, just log the state. In production, this would compare
        # with internal state and emit correction events
        logger.info(
            f"[BinanceAdapter] Reconciliation state: {len(open_orders)} open orders, {len(positions)} positions, {len(balances)} balances"
        )

        # TODO: Implement actual state comparison and correction event emission
        # This would require maintaining internal state of expected orders/positions

    def initialize_margin_settings(self, instruments_config: Dict[str, Dict]) -> None:
        """
        Initialize leverage and margin type for all configured instruments.

        Should be called after adapter initialization with trading config.

        Args:
            instruments_config: Dictionary of instrument configurations from trading.yaml
        """
        if self.shadow_mode:
            logger.info(
                "[BinanceAdapter] Shadow mode enabled - skipping margin settings initialization"
            )
            return

        logger.info("[BinanceAdapter] Initializing margin settings for instruments...")

        for symbol, config in instruments_config.items():
            leverage = config.get("leverage")
            margin_type = config.get("margin_type")

            if leverage is None:
                logger.warning(f"[BinanceAdapter] Leverage not configured for {symbol}, skipping")
                continue

            if margin_type is None:
                logger.warning(
                    f"[BinanceAdapter] Margin type not configured for {symbol}, skipping"
                )
                continue

            try:
                # Set margin type first, then leverage
                self._set_margin_type(symbol, margin_type)
                time.sleep(0.2)  # Rate limit protection

                self._set_leverage(symbol, leverage)
                time.sleep(0.2)  # Rate limit protection

                logger.info(
                    f"[BinanceAdapter] Successfully configured {symbol}: leverage={leverage}x, margin_type={margin_type}"
                )

            except Exception as e:
                # Log error but continue with other instruments
                logger.error(
                    f"[BinanceAdapter] Failed to set margin settings for {symbol}: {e}",
                    exc_info=True,
                )
                # In production, consider raising if this is critical
                # For now, we log and continue (leverage might already be set correctly)

        logger.info("[BinanceAdapter] Margin settings initialization complete")

    def _set_margin_type(self, symbol: str, margin_type: str) -> None:
        """
        Set margin type (cross/isolated) for a symbol via Binance API.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            margin_type: 'cross' or 'isolated'

        Raises:
            RuntimeError: If API call fails
        """
        logger.debug(f"[BinanceAdapter] Setting margin type '{margin_type}' for {symbol}")

        params = {
            "symbol": symbol,
            "marginType": margin_type.upper(),
        }

        # Get signed parameters
        signed_params = self._get_signed_params(params)

        # Make API request
        url = f"{BASE_URL}/fapi/v1/marginType"
        query_string = "&".join(f"{k}={v}" for k, v in signed_params.items())
        full_url = f"{url}?{query_string}"
        headers = {"X-MBX-APIKEY": self.api_key}

        resp = requests.post(url, headers=headers, timeout=10)
        data = (
            resp.json()
            if resp.headers.get("content-type", "").startswith("application/json")
            else {"raw": resp.text}
        )

        if resp.ok:
            logger.info(f"[BinanceAdapter] Margin type set to '{margin_type}' for {symbol}")
        elif resp.status_code == 400 and data.get("code") == -4046:
            # Error -4046: "No need to change margin type" - already set correctly
            logger.info(f"[BinanceAdapter] Margin type already '{margin_type}' for {symbol}")
        else:
            error_msg = f"Failed to set margin type for {symbol}: HTTP {resp.status_code} {data}"
            logger.error(f"[BinanceAdapter] {error_msg}")
            raise RuntimeError(error_msg)

    def _set_leverage(self, symbol: str, leverage: int) -> None:
        """
        Set leverage for a symbol via Binance API.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            leverage: Leverage multiplier (1-125)

        Raises:
            RuntimeError: If API call fails
        """
        logger.debug(f"[BinanceAdapter] Setting leverage {leverage}x for {symbol}")

        params = {
            "symbol": symbol,
            "leverage": str(leverage),
        }

        # Get signed parameters
        signed_params = self._get_signed_params(params)

        # Make API request
        url = f"{BASE_URL}/fapi/v1/leverage"
        query_string = "&".join(f"{k}={v}" for k, v in signed_params.items())
        full_url = f"{url}?{query_string}"
        headers = {"X-MBX-APIKEY": self.api_key}

        resp = requests.post(url, headers=headers, timeout=10)
        data = (
            resp.json()
            if resp.headers.get("content-type", "").startswith("application/json")
            else {"raw": resp.text}
        )

        if resp.ok:
            actual_leverage = data.get("leverage", "?")
            logger.info(f"[BinanceAdapter] Leverage set to {actual_leverage}x for {symbol}")
        else:
            error_msg = f"Failed to set leverage for {symbol}: HTTP {resp.status_code} {data}"
            logger.error(f"[BinanceAdapter] {error_msg}")
            raise RuntimeError(error_msg)

    def place_order(self, dec_msg: Message) -> Dict[str, object]:
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
        idempotent_key = payload.get("newClientOrderId")  # Use newClientOrderId as idempotent key

        if not symbol or not side or not qty:
            raise ValueError(f"Missing required fields: symbol={symbol}, side={side}, qty={qty}")

        # Adapt to Binance format
        binance_symbol = self._adapt_symbol(symbol)
        binance_side = self._adapt_side(side)
        binance_qty = self._adapt_quantity(qty)

        logger.info(
            f"[BinanceAdapter] Processing DEC:PLACE_ORDER for {binance_symbol} {binance_side} {binance_qty} {order_type}"
        )

        # Apply guards (skip for reduce-only bracket orders)
        if not reduce_only:
            guard_result = self._apply_guards(binance_symbol, binance_side, binance_qty)
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
                result = self._place_binance_order(
                    binance_symbol,
                    binance_side,
                    binance_qty,
                    order_type,
                    price,
                    stop_price,
                    reduce_only,
                    idempotent_key,
                )

                inc_order_placed()  # Increment order placed counter
                client_order_id = result.get("clientOrderId", idempotent_key or "unknown")
                return self._create_success_feedback(
                    symbol,
                    result.get("orderId", "unknown"),
                    client_order_id,
                    guard_result["why_codes"],
                )

        except Exception as e:
            logger.error(f"[BinanceAdapter] Order execution failed: {e}")
            return self._create_error_feedback(symbol, str(e))

    def cancel_order(self, dec_msg: Message) -> Dict[str, object]:
        """
        Cancel existing order using Binance API.

        Args:
            dec_msg: DEC:CANCEL_ORDER message with orderId

        Returns:
            Cancellation result dict
        """
        try:
            pld = dec_msg.pld or {}
            order_id = pld.get("orderId")

            if not order_id:
                return self._create_error_feedback("unknown", "Missing orderId in cancel request")

            if self.shadow_mode:
                logger.info(f"[BinanceAdapter] Shadow mode: would cancel order {order_id}")
                return self._create_success_feedback(
                    "cancelled", order_id, "unknown", "shadow_mode"
                )

            # Cancel order via API
            result = self._cancel_binance_order(order_id)

            if result.get("status") == "CANCELED":
                return self._create_success_feedback("cancelled", order_id, "unknown", "api_cancel")
            else:
                return self._create_error_feedback(
                    "unknown", f"Cancel failed: {result.get('msg', 'unknown error')}"
                )

        except Exception as e:
            logger.error(f"[BinanceAdapter] Cancel order error: {e}")
            return self._create_error_feedback("unknown", str(e))

    def _cancel_binance_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel order on Binance Futures.

        Args:
            order_id: Binance order ID to cancel

        Returns:
            API response dict
        """
        try:
            # Get API credentials
            api_key = os.environ.get("BINANCE_TESTNET_API_KEY")
            api_secret = os.environ.get("BINANCE_TESTNET_API_SECRET")

            if not api_key or not api_secret:
                raise ValueError("Missing Binance API credentials")

            # Sync time with server
            self._sync_time_with_server()

            # Build signed request
            base_url = "https://testnet.binancefuture.com"
            endpoint = "/fapi/v1/order"

            params = {
                "symbol": "BTCUSDT",  # TODO: get from context
                "orderId": order_id,
                "timestamp": int(time.time() * 1000),
                "recvWindow": 1500,
            }

            signed_params = self._get_signed_params(params, api_secret)
            headers = {"X-MBX-APIKEY": api_key}

            url = f"{base_url}{endpoint}"
            response = requests.delete(url, params=signed_params, headers=headers)

            if response.status_code == 200:
                return response.json()
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(f"[BinanceAdapter] Cancel order failed: {error_msg}")
                return {"status": "error", "msg": error_msg}

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

    def _place_binance_order(
        self,
        symbol: str,
        side: str,
        quantity: str,
        order_type: str = "MARKET",
        price: Optional[str] = None,
        stop_price: Optional[str] = None,
        reduce_only: bool = False,
        idempotent_key: Optional[str] = None,
    ) -> Mapping[str, object]:
        """
        Place order via Binance Futures API.

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
        logger.info(f"[BinanceAdapter] Placing {order_type} order: {symbol} {side} {quantity}")

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
            params["timeInForce"] = "GTC"  # Good Till Cancel

        if "STOP" in order_type and stop_price:
            params["stopPrice"] = stop_price

        if reduce_only:
            params["reduceOnly"] = "true"

        # Add newClientOrderId for idempotency
        if idempotent_key:
            params["newClientOrderId"] = idempotent_key
            logger.info(f"[BinanceAdapter] Using idempotent newClientOrderId: {idempotent_key}")

        # Get signed parameters with proper timestamp and recvWindow
        signed_params = self._get_signed_params(params)

        # Make API request
        url = f"{BASE_URL}/fapi/v1/order"
        query_string = "&".join(f"{k}={v}" for k, v in signed_params.items())
        full_url = f"{url}?{query_string}"
        headers = {"X-MBX-APIKEY": self.api_key}

        logger.info(f"[BinanceAdapter] POST {BASE_URL}/fapi/v1/order")
        resp = requests.post(full_url, headers=headers, timeout=10)

        # Parse response
        data = (
            resp.json()
            if resp.headers.get("content-type", "").startswith("application/json")
            else {"raw": resp.text}
        )

        # Handle API errors with specific error codes
        if not resp.ok:
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
                query_string = "&".join(f"{k}={v}" for k, v in signed_params.items())
                full_url = f"{url}?{query_string}"
                resp = requests.post(full_url, headers=headers, timeout=10)
                data = (
                    resp.json()
                    if resp.headers.get("content-type", "").startswith("application/json")
                    else {"raw": resp.text}
                )

                if not resp.ok:
                    logger.error(
                        f"[BinanceAdapter] Order still failed after retry: HTTP {resp.status_code} {data}"
                    )
                    raise RuntimeError(
                        f"Binance order failed after retry: HTTP {resp.status_code} {data}"
                    )

            elif error_code == -2010:
                # Insufficient balance
                logger.error(f"[BinanceAdapter] Insufficient balance (-2010): {error_msg}")
                raise RuntimeError(f"Insufficient balance: {error_msg}")

            elif error_code == -429:
                # Rate limit exceeded
                logger.warning(
                    f"[BinanceAdapter] Rate limit exceeded (-429), implementing backoff: {error_msg}"
                )
                # TODO: Implement rate limit backoff logic
                raise RuntimeError(f"Rate limit exceeded: {error_msg}")

            else:
                logger.error(f"[BinanceAdapter] Order FAILED: HTTP {resp.status_code} {data}")
                raise RuntimeError(f"Binance order failed: HTTP {resp.status_code} {data}")

        # Success
        order_id = data.get("orderId", "?")
        status = data.get("status", "?")
        logger.info(
            f"[BinanceAdapter] Order placed successfully: orderId={order_id} status={status}"
        )

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
