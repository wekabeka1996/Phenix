"""
Binance WebSocket Client.

Extracted from the legacy BinanceExecutionAdapter.
Handles WebSocket connection to Binance Futures User Data Stream.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Dict, Optional, Any

# Try to import metrics and audit logger, provide mocks if missing
try:
    from apps.reference.telemetry.metrics import (
        inc_order_state,
        observe_order_lifecycle,
    )
except ImportError:
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

class BinanceWebSocketClient:
    """
    Standalone WebSocket client for Binance Futures User Data Stream.
    """

    def __init__(self, api_key: str, base_url: str, use_testnet: bool, fsm_core: Any):
        """
        Initialize Binance WebSocket Client.

        Args:
            api_key: Binance API Key.
            base_url: Base URL for REST API (to get listen key).
            use_testnet: Whether to use testnet URLs.
            fsm_core: FSM instance for event emission and order correlation.
        """
        self.api_key = api_key
        self.base_url = base_url
        self.use_testnet = use_testnet
        self.fsm_core = fsm_core

        self.ws_listen_key: Optional[str] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.ws_running = False
        self.ws_reconnect_delay = 1.0
        self.ws_max_reconnect_delay = 60.0
        self.listen_key_last_refresh = 0.0

    def start(self) -> None:
        """
        Start WebSocket connection in a background thread.
        """
        if self.ws_thread is not None and self.ws_thread.is_alive():
            logger.warning("[BinanceWS] WebSocket already running")
            return

        logger.info("[BinanceWS] Starting WebSocket connection to USER_DATA_STREAM")
        self.ws_running = True
        self.ws_thread = threading.Thread(target=self._websocket_loop, daemon=True)
        self.ws_thread.start()
        logger.info("[BinanceWS] WebSocket thread started")

    def stop(self) -> None:
        """
        Stop WebSocket connection.
        """
        logger.info("[BinanceWS] Stopping WebSocket...")
        self.ws_running = False

        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=5.0)
            if self.ws_thread.is_alive():
                logger.warning("[BinanceWS] WebSocket thread did not stop gracefully")

        logger.info("[BinanceWS] WebSocket stopped")

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
                logger.error(f"[BinanceWS] WebSocket connection failed: {e}")
                if self.ws_running:
                    logger.info(f"[BinanceWS] Retrying WebSocket connection in {self.ws_reconnect_delay}s")
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

            import websockets
            import json

            ws_url = (
                f"wss://fstream.binance.com/ws/{self.ws_listen_key}"
                if not self.use_testnet
                else f"wss://stream.binancefuture.com/ws/{self.ws_listen_key}"
            )

            logger.info(f"[BinanceWS] Connecting to WebSocket: {ws_url}")

            # Create event loop for async WebSocket
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def ws_handler():
                try:
                    async with websockets.connect(ws_url) as websocket:
                        logger.info("[BinanceWS] WebSocket connected successfully")

                        while self.ws_running:
                            try:
                                # Receive message with timeout
                                message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                                msg_data = json.loads(message)
                                self._handle_ws_message(msg_data)

                            except asyncio.TimeoutError:
                                # Send ping to keep connection alive
                                await websocket.ping()
                                # Also refresh listen key periodically (every 30 mins approx)
                                if time.time() - self.listen_key_last_refresh > 1800:
                                    self._refresh_listen_key()

                            except websockets.exceptions.ConnectionClosed:
                                logger.warning("[BinanceWS] WebSocket connection closed")
                                break

                except Exception as e:
                    logger.error(f"[BinanceWS] WebSocket handler error: {e}")
                    raise

            # Run WebSocket handler
            loop.run_until_complete(ws_handler())

        except Exception as e:
            logger.error(f"[BinanceWS] Failed to establish WebSocket connection: {e}")
            raise

    def _get_listen_key(self) -> None:
        """
        Get listen key for USER_DATA_STREAM.
        """
        url = f"{self.base_url}/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": self.api_key}

        import requests
        resp = requests.post(url, headers=headers, timeout=10)
        if resp.ok:
            data = resp.json()
            self.ws_listen_key = data.get("listenKey")
            self.listen_key_last_refresh = time.time()
            logger.info(f"[BinanceWS] Obtained listen key: {self.ws_listen_key[:10]}...")
        else:
            raise RuntimeError(f"Failed to get listen key: HTTP {resp.status_code} {resp.text}")

    def _refresh_listen_key(self) -> None:
        """
        Refresh listen key to keep USER_DATA_STREAM alive.
        """
        if not self.ws_listen_key:
            return

        url = f"{self.base_url}/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": self.api_key}
        params = {"listenKey": self.ws_listen_key}

        import requests
        try:
            resp = requests.put(url, headers=headers, params=params, timeout=10)
            if resp.ok:
                self.listen_key_last_refresh = time.time()
                logger.debug("[BinanceWS] Listen key refreshed")
            else:
                logger.warning(f"[BinanceWS] Failed to refresh listen key: HTTP {resp.status_code}")
        except Exception as e:
             logger.warning(f"[BinanceWS] Failed to refresh listen key: {e}")

    def _handle_ws_message(self, msg: Dict[str, Any]) -> None:
        """
        Handle incoming WebSocket messages.
        """
        try:
            logger.debug(f"[BinanceWS] WS message received: {msg}")

            event_type = msg.get("e")
            if event_type == "ORDER_TRADE_UPDATE":
                self._handle_order_trade_update(msg)
            elif event_type == "ACCOUNT_UPDATE":
                self._handle_account_update(msg)
            else:
                logger.debug(f"[BinanceWS] Ignoring unknown event type: {event_type}")

        except Exception as e:
            logger.error(f"[BinanceWS] Error handling WS message: {e}", exc_info=True)

    def _handle_order_trade_update(self, msg: Dict[str, Any]) -> None:
        """
        Handle ORDER_TRADE_UPDATE event.
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
                f"[BinanceWS] ORDER_TRADE_UPDATE: {symbol} {client_order_id}/{exchange_order_id} status={order_status}"
            )

            # Correlate order using OrderIndex
            order_ref = None
            if hasattr(self.fsm_core, "order_index") and self.fsm_core.order_index:
                order_ref = self.fsm_core.order_index.get(clientOrderId=client_order_id)
                if not order_ref and exchange_order_id:
                    order_ref = self.fsm_core.order_index.get(exchangeOrderId=exchange_order_id)

            if not order_ref:
                logger.warning(
                    f"[BinanceWS] No correlation found for order {client_order_id}/{exchange_order_id}, skipping"
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

            # Create payload
            payload = {
                "symbol": symbol,
                "status": standardized_status,
                "rid": order_ref.rid,
                "idempotent_key": order_ref.idempotent_key,
                "clientOrderId": client_order_id,
                "exchangeOrderId": exchange_order_id,
                "orderId": exchange_order_id,
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
                qty=order_data.get("q"),
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

            # Emit appropriate event based on status
            if self.fsm_core:
                if standardized_status == "FILLED":
                    event_name = "EVT:TRADE_EXECUTED"
                    logger.info(f"[BinanceWS] ✅ ORDER FILLED - Emitting EVT:TRADE_EXECUTED for {symbol}")
                else:
                    event_name = "EVT:ORDER_STATE_CHANGED"
                    logger.info(f"[BinanceWS] Order status change - Emitting EVT:ORDER_STATE_CHANGED {standardized_status}")

                self.fsm_core.emit(event_name, payload, f"WS_ORDER_UPDATE_{standardized_status}")

        except Exception as e:
            logger.error(f"[BinanceWS] Error processing ORDER_TRADE_UPDATE: {e}", exc_info=True)

    def _handle_account_update(self, msg: Dict[str, Any]) -> None:
        """
        Handle ACCOUNT_UPDATE event.
        """
        try:
            account_data = msg.get("a", {})
            balances = account_data.get("B", [])
            positions = account_data.get("P", [])

            logger.info(f"[BinanceWS] ACCOUNT_UPDATE: {len(balances)} balances, {len(positions)} positions")

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
                logger.info("[BinanceWS] Emitted EVT:ACCOUNT_UPDATE_RECEIVED")

        except Exception as e:
            logger.error(f"[BinanceWS] Error processing ACCOUNT_UPDATE: {e}", exc_info=True)
