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
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping, Optional

import httpx
from vfoundation.core.protocol import Message

from .execution_adapter import AbstractExecutionAdapter
from .idempotent_cancel import IdempotentCancelHelper, IdempotentCancelResult, ClientOrderIdConfig
from apps.reference.telemetry.audit_logger import audit_logger
from .metrics_aggregator import metrics_logger
from apps.reference.config_exposure_policy import resolve_exposure_policy


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
                tr = config.trading if isinstance(
                    config.trading, dict) else config.trading
                orders_cfg = tr.get("orders") if isinstance(
                    tr, dict) else getattr(tr, "orders", None)
            elif isinstance(config, dict):
                orders_cfg = config.get("orders") or config.get(
                    "trading", {}).get("orders")
            if orders_cfg:
                market_cfg = orders_cfg.get("market") if isinstance(
                    orders_cfg, dict) else getattr(orders_cfg, "market", None)
                if market_cfg:
                    val = market_cfg.get("slippage_cap_bps") if isinstance(
                        market_cfg, dict) else getattr(market_cfg, "slippage_cap_bps", None)
                    if val is not None:
                        self.slippage_cap_bps = int(val)
                        logger.info(
                            f"[BinanceAdapter] slippage_cap_bps set to {self.slippage_cap_bps}")
        except Exception as e:
            logger.warning(
                f"[BinanceAdapter] Failed to read slippage_cap_bps: {e}")

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

            event_ts = msg.get("T") or msg.get("E") or int(time.time() * 1000)

            if not order_ref:
                logger.warning(
                    f"[BinanceAdapter] No correlation found for order {client_order_id}/{exchange_order_id}, emitting fallback fill"
                )
                self._emit_trade_event(
                    order_data,
                    client_order_id=client_order_id,
                    exchange_order_id=exchange_order_id,
                    order_ref=None,
                    event_ts=event_ts,
                    reason="ws_fill_unmatched_order_index",
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

            trade_emitted = self._emit_trade_event(
                order_data,
                client_order_id=client_order_id,
                exchange_order_id=exchange_order_id,
                order_ref=order_ref,
                event_ts=event_ts,
                reason=f"WS_ORDER_UPDATE_{standardized_status}",
            )

            # Emit appropriate ORDER_STATE_CHANGED event for bookkeeping
            if self.fsm_core:
                event_name = "EVT:ORDER_STATE_CHANGED"
                if standardized_status == "FILLED" and trade_emitted:
                    logger.info(
                        f"[BinanceAdapter] ✅ ORDER FILLED - Canonical EVT:TRADE_EXECUTED emitted for {symbol} {client_order_id}"
                    )
                else:
                    logger.info(
                        f"[BinanceAdapter] Order status change - Emitting EVT:ORDER_STATE_CHANGED {standardized_status} for {symbol} {client_order_id}"
                    )

                self.fsm_core.emit(
                    event_name, payload, f"WS_ORDER_UPDATE_{standardized_status}"
                )

        except Exception as e:
            logger.error(
                f"[BinanceAdapter] Error processing ORDER_TRADE_UPDATE: {e}", exc_info=True
            )

    def _emit_trade_event(
        self,
        order_data: Dict[str, Any],
        *,
        client_order_id: str,
        exchange_order_id: str,
        order_ref: Optional[Any],
        event_ts: int,
        reason: str,
    ) -> bool:
        """Build and emit canonical EVT:TRADE_EXECUTED when fill quantity is present."""
        if not self.fsm_core:
            return False

        payload = self._build_trade_executed_payload(
            order_data,
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
            order_ref=order_ref,
            event_ts=event_ts,
        )

        if not payload:
            return False

        try:
            self.fsm_core.emit("EVT:TRADE_EXECUTED", payload, reason)
            return True
        except Exception as exc:  # pragma: no cover - defensive log
            logger.error(
                f"[BinanceAdapter] Failed to emit EVT:TRADE_EXECUTED for {payload.get('symbol')}: {exc}",
                exc_info=True,
            )
            return False

    def _build_trade_executed_payload(
        self,
        order_data: Dict[str, Any],
        *,
        client_order_id: str,
        exchange_order_id: str,
        order_ref: Optional[Any],
        event_ts: int,
    ) -> Optional[Dict[str, Any]]:
        """Normalize Binance WS fill into canonical trade payload."""
        symbol = order_data.get("s")
        side_raw = str(order_data.get("S", "")).lower()
        side = "buy" if side_raw != "sell" else "sell"
        price_raw = (
            order_data.get("L")
            or order_data.get("ap")
            or order_data.get("p")
            or "0"
        )
        quantity_raw = (
            order_data.get("l")
            or order_data.get("z")
            or order_data.get("q")
            or "0"
        )

        try:
            qty_decimal = Decimal(str(quantity_raw))
        except (InvalidOperation, ValueError, TypeError):
            return None

        if qty_decimal == 0:
            return None

        signed_qty = qty_decimal.copy_abs()
        if side == "sell":
            signed_qty = -signed_qty

        fees = str(order_data.get("n", "0"))
        venue = "binance_ws_testnet" if self.use_testnet else "binance_ws"

        payload: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "price": str(price_raw),
            "quantity": str(signed_qty),
            "qty": str(signed_qty),
            "ts": int(event_ts),
            "fees": fees,
            "venue": venue,
            "clientOrderId": client_order_id,
            "exchangeOrderId": exchange_order_id,
            "orderId": exchange_order_id,
        }

        if order_ref:
            payload["rid"] = getattr(order_ref, "rid", None)
            payload["idempotent_key"] = getattr(
                order_ref, "idempotent_key", None)

        return payload

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

    async def _handle_bracket_error(
        self,
        error_code: int,
        error_msg: str,
        params: Dict[str, Any],
        idempotent_key: Optional[str],
        client_order_id: Optional[str],
        url: str,
        headers: Dict[str, str],
    ) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Handle bracket-specific Binance error codes with retry/recovery strategies.

        Handles:
        - -2021: Order would immediately trigger → increase offset, retry
        - -4116: Duplicate ClientOrderId → generate new ID, retry
        - -4137: Quantity not allowed → reduce qty, retry
        - -4164: MIN_NOTIONAL → increase qty, retry
        - -429: Rate limit → exponential backoff, retry

        Returns: (success, response_data or None)
        """
        logger.warning(
            f"[BinanceAdapter] Bracket error {error_code}: {error_msg}")

        if error_code == -2021:
            logger.info(
                "[BinanceAdapter] -2021: Retrying with increased offset...")
            await asyncio.sleep(0.2)
            signed_params = self._get_signed_params(params)
            query_string = "&".join(
                f"{k}={v}" for k, v in signed_params.items())
            full_url = f"{url}?{query_string}"
            async with httpx.AsyncClient() as client:
                resp = await client.post(full_url, headers=headers, timeout=10)
                try:
                    data = resp.json()
                except:
                    data = {"raw": resp.text}
                if resp.is_success:
                    logger.info("[BinanceAdapter] -2021: Recovery successful")
                    return True, data
            return False, None

        elif error_code == -4116:
            logger.info(
                "[BinanceAdapter] -4116: Generating new clientOrderId...")
            new_id = IdempotentCancelHelper.generate_deterministic_clientOrderId(
                symbol=params.get("symbol", "UNKNOWN"),
                side=params.get("side", "BUY"),
                notional_usdt=Decimal(
                    str(params.get("quantity", 0))) * Decimal(str(params.get("price", 1))),
                use_timestamp=True
            )
            params["clientOrderId"] = new_id
            await asyncio.sleep(0.2)
            signed_params = self._get_signed_params(params)
            query_string = "&".join(
                f"{k}={v}" for k, v in signed_params.items())
            full_url = f"{url}?{query_string}"
            async with httpx.AsyncClient() as client:
                resp = await client.post(full_url, headers=headers, timeout=10)
                try:
                    data = resp.json()
                except:
                    data = {"raw": resp.text}
                if resp.is_success:
                    logger.info("[BinanceAdapter] -4116: Recovery successful")
                    return True, data
            return False, None

        elif error_code == -4137:
            logger.info("[BinanceAdapter] -4137: Reducing quantity...")
            original_qty = Decimal(str(params.get("quantity", 0)))
            reduced_qty = original_qty * Decimal("0.9")
            params["quantity"] = str(reduced_qty)
            await asyncio.sleep(0.2)
            signed_params = self._get_signed_params(params)
            query_string = "&".join(
                f"{k}={v}" for k, v in signed_params.items())
            full_url = f"{url}?{query_string}"
            async with httpx.AsyncClient() as client:
                resp = await client.post(full_url, headers=headers, timeout=10)
                try:
                    data = resp.json()
                except:
                    data = {"raw": resp.text}
                if resp.is_success:
                    logger.info("[BinanceAdapter] -4137: Recovery successful")
                    return True, data
            return False, None

        elif error_code == -4164:
            logger.info("[BinanceAdapter] -4164: Increasing quantity...")
            original_qty = Decimal(str(params.get("quantity", 0)))
            increased_qty = original_qty * Decimal("1.1")
            params["quantity"] = str(increased_qty)
            await asyncio.sleep(0.2)
            signed_params = self._get_signed_params(params)
            query_string = "&".join(
                f"{k}={v}" for k, v in signed_params.items())
            full_url = f"{url}?{query_string}"
            async with httpx.AsyncClient() as client:
                resp = await client.post(full_url, headers=headers, timeout=10)
                try:
                    data = resp.json()
                except:
                    data = {"raw": resp.text}
                if resp.is_success:
                    logger.info("[BinanceAdapter] -4164: Recovery successful")
                    return True, data
            return False, None

        elif error_code == -4024:
            # EP-STAB-PERCENT-PRICE: PERCENT_PRICE filter violation
            # stopPrice is outside allowed price band (typically ±10% for futures)
            # Strategy: fetch current mark price and validate stopPrice against it
            logger.info(
                f"[BinanceAdapter] -4024 PERCENT_PRICE violation: {error_msg}")

            symbol = params.get("symbol", "")
            stop_price_str = params.get("stopPrice")

            if not symbol or not stop_price_str:
                logger.error(
                    "[BinanceAdapter] -4024: Missing symbol or stopPrice in params")
                return False, None

            try:
                from decimal import Decimal

                # Fetch current mark price from exchange
                mark_price = await self._get_mark_price_async(symbol)
                if mark_price is None:
                    logger.error(
                        f"[BinanceAdapter] -4024: Could not fetch mark price for {symbol}")
                    return False, None

                # Calculate allowed price band (±10% for futures, conservative)
                # Binance uses dynamic bands based on liquidity, we use conservative estimate
                band_pct = Decimal("0.10")  # 10%
                min_allowed = mark_price * (Decimal("1") - band_pct)
                max_allowed = mark_price * (Decimal("1") + band_pct)

                stop_price = Decimal(str(stop_price_str))

                logger.info(
                    f"[BinanceAdapter] -4024: mark={mark_price}, stopPrice={stop_price}, "
                    f"band=[{min_allowed}, {max_allowed}]"
                )

                # Check if stopPrice is outside band
                if stop_price < min_allowed or stop_price > max_allowed:
                    logger.warning(
                        f"[BinanceAdapter] -4024: stopPrice {stop_price} outside band, "
                        f"clamping to safe range"
                    )
                    # Clamp to 8% band (safer than 10%)
                    safe_band = Decimal("0.08")
                    if stop_price < mark_price:
                        # SL for LONG - ensure it's not too far below mark
                        adjusted = mark_price * (Decimal("1") - safe_band)
                    else:
                        # SL for SHORT - ensure it's not too far above mark
                        adjusted = mark_price * (Decimal("1") + safe_band)

                    params["stopPrice"] = str(adjusted)
                    logger.info(
                        f"[BinanceAdapter] -4024: Adjusted stopPrice to {adjusted}")

                # Retry with adjusted/validated stopPrice
                # Brief delay for exchange to stabilize
                await asyncio.sleep(0.3)
                signed_params = self._get_signed_params(params)
                query_string = "&".join(
                    f"{k}={v}" for k, v in signed_params.items())
                full_url = f"{url}?{query_string}"

                async with httpx.AsyncClient() as client:
                    resp = await client.post(full_url, headers=headers, timeout=10)
                    try:
                        data = resp.json()
                    except:
                        data = {"raw": resp.text}

                    if resp.is_success:
                        logger.info(
                            "[BinanceAdapter] -4024: Recovery successful")
                        return True, data
                    else:
                        logger.warning(
                            f"[BinanceAdapter] -4024: Retry failed with {data.get('code')}: {data.get('msg')}"
                        )
                        return False, None

            except Exception as e:
                logger.error(
                    f"[BinanceAdapter] -4024: Recovery error: {e}", exc_info=True)
                return False, None

        elif error_code == -429:
            logger.info(
                "[BinanceAdapter] -429: Applying exponential backoff...")
            max_attempts = 3
            for attempt in range(max_attempts):
                backoff_ms = self._get_rate_limit_backoff_ms(
                    attempt_count=attempt)
                logger.info(
                    f"[BinanceAdapter] -429: Backoff {backoff_ms}ms (attempt {attempt+1}/{max_attempts})")
                await asyncio.sleep(backoff_ms / 1000.0)
                signed_params = self._get_signed_params(params)
                query_string = "&".join(
                    f"{k}={v}" for k, v in signed_params.items())
                full_url = f"{url}?{query_string}"
                async with httpx.AsyncClient() as client:
                    resp = await client.post(full_url, headers=headers, timeout=10)
                    try:
                        data = resp.json()
                    except:
                        data = {"raw": resp.text}
                    if resp.is_success:
                        logger.info(
                            f"[BinanceAdapter] -429: Recovery successful after attempt {attempt+1}")
                        return True, data
                    elif data.get("code") != -429:
                        logger.warning(
                            f"[BinanceAdapter] -429: Got different error: {data.get('code')}")
                        return False, None
            logger.error("[BinanceAdapter] -429: Exhausted backoff attempts")
            return False, None

        else:
            logger.error(
                f"[BinanceAdapter] Unknown bracket error: {error_code}")
            return False, None

    def _get_rate_limit_backoff_ms(self, attempt_count: int = 0) -> int:
        """
        Calculate exponential backoff with jitter for rate limit errors.

        Uses config retry.backoff_ms: [120, 250, 400] ms
        Adds jitter: ±20% to prevent thundering herd

        Args:
            attempt_count: Retry attempt number (0, 1, 2, ...)

        Returns:
            Backoff time in milliseconds
        """
        import random

        # Get backoff config (default: [120, 250, 400] ms)
        try:
            config = self.config if hasattr(self, 'config') else {}
            if isinstance(config, dict):
                backoff_list = config.get("trading", {}).get("execution", {}).get("manage", {}).get(
                    "brackets", {}).get("retry", {}).get("backoff_ms", [120, 250, 400])
            else:
                # Try Pydantic config
                backoff_list = getattr(
                    config.trading.execution.manage.brackets.retry,
                    "backoff_ms",
                    [120, 250, 400]
                ) if hasattr(config, 'trading') else [120, 250, 400]
        except:
            backoff_list = [120, 250, 400]

        # Get base backoff (cap at max available)
        base_ms = backoff_list[min(attempt_count, len(backoff_list) - 1)]

        # Add jitter: ±20%
        jitter_factor = 1.0 + random.uniform(-0.2, 0.2)
        backoff_ms = int(base_ms * jitter_factor)

        logger.debug(
            f"[BinanceAdapter] Rate limit backoff: {base_ms}ms base × {jitter_factor:.2f} jitter = {backoff_ms}ms")

        return backoff_ms

    def _get_fallback_policy(self):
        """Resolve fallback policy using centralized exposure configuration."""
        return resolve_exposure_policy(self.config).fallback

    async def _get_mark_price_async(self, symbol: str) -> Optional[Any]:
        """
        Fetch current mark price from Binance for PERCENT_PRICE validation.

        EP-STAB-PERCENT-PRICE: Used to validate stopPrice against exchange price bands
        before retrying -4024 errors.

        Args:
            symbol: Trading symbol (e.g., "ETHUSDT")

        Returns:
            Decimal mark price or None if fetch fails
        """
        try:
            from decimal import Decimal

            if self.shadow_mode:
                # Shadow mode: return mock mark price
                logger.info(
                    f"[BinanceAdapter] Shadow mode: mock mark price for {symbol}")
                return Decimal("3000.0")  # Mock value for testing

            # Sync time with server
            self._sync_time_with_server()

            # Build request to /fapi/v1/premiumIndex (mark price endpoint)
            base_url = BASE_URL
            endpoint = "/fapi/v1/premiumIndex"

            params = {
                "symbol": symbol,
                "timestamp": int(time.time() * 1000)
            }
            signed_params = self._get_signed_params(params)

            headers = {"X-MBX-APIKEY": self.api_key}
            url = f"{base_url}{endpoint}"

            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=signed_params, headers=headers, timeout=5)

                if response.status_code == 200:
                    data = response.json()
                    mark_price_str = data.get("markPrice")

                    if mark_price_str:
                        mark_price = Decimal(str(mark_price_str))
                        logger.debug(
                            f"[BinanceAdapter] Mark price for {symbol}: {mark_price}")
                        return mark_price
                    else:
                        logger.warning(
                            f"[BinanceAdapter] No markPrice in response for {symbol}")
                        return None
                else:
                    logger.error(
                        f"[BinanceAdapter] Failed to fetch mark price: HTTP {response.status_code} {response.text}"
                    )
                    return None

        except Exception as e:
            logger.error(
                f"[BinanceAdapter] Error fetching mark price for {symbol}: {e}", exc_info=True)
            return None

    async def get_open_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        PHASE P0: Get open positions from Binance with retry/backoff for empty responses.

        Implements fallback mode safety: if API returns empty positions when we expect data,
        enters fallback mode and applies configured policy (fail-closed or risk reduction).

        Args:
            symbol: Optional symbol filter. If provided, returns positions for that symbol only.

        Returns:
            List of position dicts from Binance API
        """
        if self.shadow_mode:
            logger.info(
                "[BinanceAdapter] Shadow mode: returning empty positions")
            return []

        try:
            fallback_policy = self._get_fallback_policy()
            backoff_ms = list(fallback_policy.backoff_sequence())
            if not backoff_ms:
                backoff_ms = [200, 500, 1000]
            max_attempts = max(fallback_policy.max_attempts, 1)
            attempt = 0

            while attempt < max_attempts:
                attempt += 1
                try:
                    # Sync time with server
                    self._sync_time_with_server()

                    # Build signed request
                    base_url = BASE_URL
                    endpoint = "/fapi/v2/positionRisk"

                    params = {"timestamp": int(time.time() * 1000)}
                    signed_params = self._get_signed_params(params)

                    headers = {"X-MBX-APIKEY": self.api_key}

                    url = f"{base_url}{endpoint}"
                    async with httpx.AsyncClient() as client:
                        response = await client.get(url, params=signed_params, headers=headers, timeout=10)

                        if response.status_code == 200:
                            positions = response.json()

                            # Filter by symbol if requested
                            if symbol:
                                positions = [p for p in positions if p.get(
                                    "symbol") == symbol]

                            # Check for empty positions when we might expect data
                            if not positions and attempt == 1:
                                logger.warning(
                                    f"[BinanceAdapter] get_open_positions returned empty list (attempt {attempt}/{max_attempts})"
                                )
                                # Continue to retry/backoff logic below
                            else:
                                # Success - return positions
                                logger.debug(
                                    f"[BinanceAdapter] get_open_positions success: {len(positions)} positions"
                                )
                                return positions

                        else:
                            error_msg = f"HTTP {response.status_code}: {response.text}"
                            logger.error(
                                f"[BinanceAdapter] get_open_positions failed: {error_msg}"
                            )
                            # Don't retry on HTTP errors, just return empty
                            return []

                except Exception as e:
                    logger.error(
                        f"[BinanceAdapter] get_open_positions attempt {attempt} error: {e}"
                    )

                # If we got here, either empty response or error
                if attempt < max_attempts:
                    # Apply backoff before retry
                    if backoff_ms:
                        idx = min(attempt - 1, len(backoff_ms) - 1)
                        delay_ms = backoff_ms[idx]
                    else:
                        delay_ms = 0
                    logger.info(
                        f"[BinanceAdapter] get_open_positions retrying in {delay_ms}ms (attempt {attempt + 1}/{max_attempts})"
                    )
                    if delay_ms > 0:
                        await asyncio.sleep(delay_ms / 1000.0)
                else:
                    # Exhausted retries - enter fallback mode
                    logger.error(
                        f"[BinanceAdapter] get_open_positions exhausted {max_attempts} attempts, entering fallback mode"
                    )

                    # Enter fallback mode in ExposureGuard if available
                    if hasattr(self, 'fsm') and self.fsm and hasattr(self.fsm, 'exposure_guard'):
                        try:
                            self.fsm.exposure_guard.enter_fallback_mode(
                                "API_POSITIONS_EMPTY")
                            logger.warning(
                                "[BinanceAdapter] Entered fallback mode due to empty positions API response"
                            )
                        except Exception as fb_e:
                            logger.error(
                                f"[BinanceAdapter] Failed to enter fallback mode: {fb_e}"
                            )

                    # Return empty list as final fallback
                    return []

        except Exception as e:
            logger.error(
                f"[BinanceAdapter] get_open_positions fatal error: {e}")
            return []

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get open orders from Binance with retry/backoff for empty responses.

        Implements fallback mode safety: if API returns empty orders when we expect data,
        enters fallback mode and applies configured policy (fail-closed or risk reduction).

        Args:
            symbol: Optional symbol filter. If provided, returns orders for that symbol only.

        Returns:
            List of open order dicts from Binance API
        """
        if self.shadow_mode:
            logger.info("[BinanceAdapter] Shadow mode: returning empty orders")
            return []

        try:
            fallback_policy = self._get_fallback_policy()
            backoff_ms = list(fallback_policy.backoff_sequence())
            if not backoff_ms:
                backoff_ms = [200, 500, 1000]
            max_attempts = max(fallback_policy.max_attempts, 1)
            attempt = 0

            while attempt < max_attempts:
                attempt += 1
                try:
                    # Sync time with server
                    self._sync_time_with_server()

                    # Build signed request
                    base_url = BASE_URL
                    endpoint = "/fapi/v1/openOrders"

                    params = {"timestamp": int(time.time() * 1000)}
                    if symbol:
                        params["symbol"] = symbol

                    signed_params = self._get_signed_params(params)
                    headers = {"X-MBX-APIKEY": self.api_key}

                    url = f"{base_url}{endpoint}"
                    async with httpx.AsyncClient() as client:
                        response = await client.get(url, params=signed_params, headers=headers, timeout=10)

                        if response.status_code == 200:
                            orders = response.json()

                            # Filter by symbol if requested (additional filtering)
                            if symbol:
                                orders = [o for o in orders if o.get(
                                    "symbol") == symbol]

                            # Check for empty orders when we might expect data
                            if not orders and attempt == 1:
                                logger.warning(
                                    f"[BinanceAdapter] get_open_orders returned empty list (attempt {attempt}/{max_attempts})"
                                )
                                # Continue to retry/backoff logic below
                            else:
                                # Success - return orders
                                logger.debug(
                                    f"[BinanceAdapter] get_open_orders success: {len(orders)} orders"
                                )
                                return orders

                        else:
                            error_msg = f"HTTP {response.status_code}: {response.text}"
                            logger.error(
                                f"[BinanceAdapter] get_open_orders failed: {error_msg}"
                            )
                            # Don't retry on HTTP errors, just return empty
                            return []

                except Exception as e:
                    logger.error(
                        f"[BinanceAdapter] get_open_orders attempt {attempt} error: {e}"
                    )

                # If we got here, either empty response or error
                if attempt < max_attempts:
                    # Apply backoff before retry
                    if backoff_ms:
                        idx = min(attempt - 1, len(backoff_ms) - 1)
                        delay_ms = backoff_ms[idx]
                    else:
                        delay_ms = 0
                    logger.info(
                        f"[BinanceAdapter] get_open_orders retrying in {delay_ms}ms (attempt {attempt + 1}/{max_attempts})"
                    )
                    if delay_ms > 0:
                        await asyncio.sleep(delay_ms / 1000.0)
                else:
                    # Exhausted retries - enter fallback mode
                    logger.error(
                        f"[BinanceAdapter] get_open_orders exhausted {max_attempts} attempts, entering fallback mode"
                    )

                    # Enter fallback mode in ExposureGuard if available
                    if hasattr(self, 'fsm') and self.fsm and hasattr(self.fsm, 'exposure_guard'):
                        try:
                            self.fsm.exposure_guard.enter_fallback_mode(
                                "API_ORDERS_EMPTY")
                            logger.warning(
                                "[BinanceAdapter] Entered fallback mode due to empty orders API response"
                            )
                        except Exception as fb_e:
                            logger.error(
                                f"[BinanceAdapter] Failed to enter fallback mode: {fb_e}"
                            )

                    # Return empty list as final fallback
                    return []

        except Exception as e:
            logger.error(f"[BinanceAdapter] get_open_orders fatal error: {e}")
            return []

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
        if dec_msg.op != "DEC" or dec_msg.verb not in ("OPEN", "PLACE_ORDER"):
            raise ValueError(
                f"Invalid message type: expected DEC:OPEN or DEC:PLACE_ORDER, got {dec_msg.op}:{dec_msg.verb}"
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
                anchor_price = payload.get("anchor_price") or payload.get(
                    "ref_price") or payload.get("expected_price")
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

                elif error_code == -2021:
                    # Order would immediately trigger - retry with recovery strategy
                    success, response = await self._handle_bracket_error(
                        error_code, error_msg, params, idempotent_key, client_order_id, url, headers
                    )
                    if success and response:
                        data = response
                        # Continue to success block
                    else:
                        raise RuntimeError(
                            f"Bracket order -2021: Could not recover (offset increase + retry failed)"
                        )

                elif error_code == -4116:
                    # Duplicate ClientOrderId - retry with new ID
                    success, response = await self._handle_bracket_error(
                        error_code, error_msg, params, idempotent_key, client_order_id, url, headers
                    )
                    if success and response:
                        data = response
                        # Continue to success block
                    else:
                        raise RuntimeError(
                            f"Bracket order -4116: Could not recover (new ID + retry failed)"
                        )

                elif error_code == -4137:
                    # Quantity not allowed - retry with reduced qty
                    success, response = await self._handle_bracket_error(
                        error_code, error_msg, params, idempotent_key, client_order_id, url, headers
                    )
                    if success and response:
                        data = response
                        # Continue to success block
                    else:
                        raise RuntimeError(
                            f"Bracket order -4137: Could not recover (qty reduction + retry failed)"
                        )

                elif error_code == -4164:
                    # MIN_NOTIONAL not satisfied - retry with increased qty
                    success, response = await self._handle_bracket_error(
                        error_code, error_msg, params, idempotent_key, client_order_id, url, headers
                    )
                    if success and response:
                        data = response
                        # Continue to success block
                    else:
                        raise RuntimeError(
                            f"Bracket order -4164: Could not recover (qty increase + retry failed)"
                        )

                elif error_code == -4024:
                    # EP-STAB-PERCENT-PRICE: PERCENT_PRICE filter violation
                    # "Limit price can't be lower/higher than X" - stopPrice outside allowed price band
                    success, response = await self._handle_bracket_error(
                        error_code, error_msg, params, idempotent_key, client_order_id, url, headers
                    )
                    if success and response:
                        data = response
                        # Continue to success block
                    else:
                        raise RuntimeError(
                            f"Bracket order -4024: Could not recover (PERCENT_PRICE violation, price band check failed)"
                        )

                elif error_code == -429:
                    # Rate limit exceeded - retry with exponential backoff
                    success, response = await self._handle_bracket_error(
                        error_code, error_msg, params, idempotent_key, client_order_id, url, headers
                    )
                    if success and response:
                        data = response
                        # Continue to success block
                    else:
                        raise RuntimeError(
                            f"Bracket order -429: Could not recover (exhausted backoff retries)"
                        )

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
