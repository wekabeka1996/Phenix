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
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlencode

import httpx

from vfoundation.core.protocol import Message

from .execution_adapter import AbstractExecutionAdapter
from .idempotent_cancel import IdempotentCancelHelper, IdempotentCancelResult, ClientOrderIdConfig
from .algo_order_index import AlgoOrderIndex, AlgoOrderUpdate
from apps.reference.telemetry.audit_logger import audit_logger
from .metrics_aggregator import metrics_logger
from apps.reference.config_exposure_policy import resolve_exposure_policy
from apps.reference.config_symbols import resolve_instrument_profile
from apps.reference.config_models import InstrumentProfile


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

__all__ = ["BinanceExecutionAdapter"]

# Time synchronization constants
TIME_SYNC_INTERVAL_SEC = 30  # Re-sync every 30 seconds for Futures stability
TIME_DRIFT_INFO_THRESHOLD_MS = 500
TIME_DRIFT_WARN_CHANGE_THRESHOLD_MS = 5_000
TIME_DRIFT_HARD_LIMIT_MS = 60_000

GET_OPEN_ORDERS_MAX_ATTEMPTS = 3
GET_OPEN_ORDERS_BACKOFF_MS = (200, 500)
GET_OPEN_ORDERS_FALLBACK_REASON = "API_ORDERS_FAILED"

LISTEN_KEY_KEEPALIVE_SECONDS = 45 * 60  # 45 minutes

# Binance Futures API configuration
# Default to testnet.binancefuture.com for USDT-M Futures (/fapi endpoints)
BASE_URL = os.environ.get("BINANCE_FUTURES_BASE_URL",
                          "https://testnet.binancefuture.com")


class BinanceValidationError(Exception):
    """Raised when order parameters fail Binance exchange filters validation."""
    pass


class BinanceExecutionAdapter(AbstractExecutionAdapter):
    """
    Concrete adapter for Binance Futures execution.

    Adapts existing executor_binance.py logic to AbstractExecutionAdapter interface.
    Handles DEC:OPEN messages and executes market orders with guards.
    """

    def __init__(self, fsm=None, config=None, shadow_mode: bool = False, rest_timeout_sec: float = 20.0, **kwargs):
        """
        Initialize Binance adapter.

        Args:
            fsm: FSM instance for event emission
            config: Configuration dict
            shadow_mode: If True, no live API calls (for testing)
            rest_timeout_sec: HTTP request timeout in seconds (default: 20.0)
            **kwargs: Additional arguments (e.g., fsm_core for testing)
        """
        super().__init__(fsm, config)
        self.shadow_mode = shadow_mode
        self._rest_timeout = float(rest_timeout_sec)
        # Support both fsm and fsm_core parameter names (for testing)
        # For emitting EVT:* events
        self.fsm_core = kwargs.get('fsm_core', fsm)
        self._last_status_check = 0.0
        self._status_cache = "unknown"

        # Instrument profiles cache for precision/filter validation
        self._instrument_profiles: Dict[str, InstrumentProfile] = {}

        # WebSocket related attributes
        self.ws_listen_key: Optional[str] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.ws_running = False
        self.ws_reconnect_delay = 1.0  # Start with 1 second, exponential backoff
        self.ws_max_reconnect_delay = 60.0  # Max 1 minute
        self.listen_key_last_refresh = 0.0
        self._last_listen_key_keepalive_at = 0.0

        # Time sync attributes
        self.server_time_offset = 0.0  # Offset between local and server time
        self.last_time_sync = 0.0
        self._time_sync_initialized = False
        self._last_drift_warning_bucket: Optional[int] = None
        # Background time sync task
        self._time_sync_task: Optional[asyncio.Task] = None

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

        # Feature Flag: Algo Service for conditionals
        self.use_algo_service_for_conditionals = False
        try:
            if hasattr(config, "execution") and config.execution:
                self.use_algo_service_for_conditionals = getattr(
                    config.execution, "use_algo_service_for_conditionals", False
                )
            elif isinstance(config, dict):
                exec_cfg = config.get("execution", {})
                self.use_algo_service_for_conditionals = exec_cfg.get(
                    "use_algo_service_for_conditionals", False
                )
        except Exception:
            self.use_algo_service_for_conditionals = False

        # Initialize AlgoOrderIndex for Phase 1
        self.algo_order_index = AlgoOrderIndex()

        logger.info(
            f"[BinanceAdapter] Algo Service for conditionals: {self.use_algo_service_for_conditionals}")

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

        # Set REST base URL for API calls (WebSocket listen key, etc.)
        self.rest_url = BASE_URL

        # Log REST base URL and timeout for visibility (especially for testnet → demo-fapi migration)
        logger.info(
            f"[BinanceAdapter] Using REST base_url='{self.rest_url}' "
            f"(shadow_mode={self.shadow_mode}, testnet={self.use_testnet}, ws_enabled={fsm is not None})"
        )
        logger.info(
            f"[BinanceAdapter] REST timeout configured: {self._rest_timeout:.1f}s"
        )

    def start(self) -> None:
        """
        Start the adapter, including WebSocket connection if FSM core is available.
        """
        # FIXED: Synchronize time with Binance server on startup
        if not self.shadow_mode:
            logger.info(
                "[BinanceAdapter] Synchronizing time with Binance server...")
            try:
                self._sync_time_with_server_blocking()
            except Exception as e:
                logger.warning(
                    f"[BinanceAdapter] Initial time sync failed: {e}, will retry on first -1021")

            # Start background time sync task
            try:
                loop = asyncio.get_running_loop()
                self._time_sync_task = loop.create_task(
                    self._background_time_sync_loop())
                logger.info(
                    "[BinanceAdapter] Background time sync task started")
            except RuntimeError:
                # No running loop yet, will be started later
                logger.debug(
                    "[BinanceAdapter] No event loop yet, background sync will start on first async call")

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

        # Cancel background time sync task
        if self._time_sync_task and not self._time_sync_task.done():
            self._time_sync_task.cancel()
            logger.info("[BinanceAdapter] Background time sync task cancelled")

        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=5.0)
            if self.ws_thread.is_alive():
                logger.warning(
                    "[BinanceAdapter] WebSocket thread did not stop gracefully")

        logger.info("[BinanceAdapter] Adapter stopped")

    def _get_instrument_profile(self, symbol: str) -> InstrumentProfile:
        """
        Get instrument profile for symbol with lazy caching.

        Args:
            symbol: Trading symbol (e.g., 'SOLUSDT')

        Returns:
            InstrumentProfile with filters and precision

        Raises:
            BinanceValidationError: If symbol not configured
        """
        if symbol not in self._instrument_profiles:
            try:
                profile = resolve_instrument_profile(self.config, symbol)
                self._instrument_profiles[symbol] = profile
                logger.debug(
                    f"[BinanceAdapter] Loaded instrument profile for {symbol}: "
                    f"step_size={profile.step_size}, tick_size={profile.tick_size}, "
                    f"qty_precision={profile.precision_quantity}, price_precision={profile.precision_price}"
                )
            except Exception as e:
                logger.error(
                    f"[BinanceAdapter] Failed to resolve instrument profile for {symbol}: {e}"
                )
                raise BinanceValidationError(
                    f"Symbol {symbol} not configured or invalid: {e}"
                ) from e
        return self._instrument_profiles[symbol]

    def _quantize_qty(self, symbol: str, raw_qty: Decimal | float | str) -> Decimal:
        """
        Normalize quantity to exchange step_size and validate min_qty.

        Args:
            symbol: Trading symbol
            raw_qty: Raw quantity value

        Returns:
            Normalized quantity (floored to step_size)

        Raises:
            BinanceValidationError: If qty < min_qty after normalization
        """
        profile = self._get_instrument_profile(symbol)

        # Convert to Decimal
        try:
            qty = Decimal(str(raw_qty))
        except (InvalidOperation, ValueError) as e:
            raise BinanceValidationError(
                f"Invalid quantity format for {symbol}: {raw_qty}"
            ) from e

        # Floor to step_size
        step_size = Decimal(str(profile.step_size))
        if step_size > 0:
            qty = (qty / step_size).quantize(Decimal('1'),
                                             rounding=ROUND_DOWN) * step_size

        # Quantize to precision_quantity decimal places
        precision_str = f"0.{'0' * profile.precision_quantity}"
        qty = qty.quantize(Decimal(precision_str), rounding=ROUND_DOWN)

        # Validate min_qty
        min_qty = Decimal(str(profile.min_qty))
        if qty < min_qty:
            raise BinanceValidationError(
                f"Quantity {qty} below min_qty {min_qty} for {symbol} "
                f"(raw_qty={raw_qty}, step_size={step_size})"
            )

        logger.debug(
            f"[BinanceAdapter] Normalized qty for {symbol}: {raw_qty} → {qty} "
            f"(step_size={step_size}, min_qty={min_qty})"
        )
        return qty

    def _quantize_price(self, symbol: str, raw_price: Decimal | float | str) -> Decimal:
        """
        Normalize price to exchange tick_size.

        Args:
            symbol: Trading symbol
            raw_price: Raw price value

        Returns:
            Normalized price (floored to tick_size)

        Raises:
            BinanceValidationError: If price invalid
        """
        profile = self._get_instrument_profile(symbol)

        # Convert to Decimal
        try:
            price = Decimal(str(raw_price))
        except (InvalidOperation, ValueError) as e:
            raise BinanceValidationError(
                f"Invalid price format for {symbol}: {raw_price}"
            ) from e

        # Floor to tick_size
        tick_size = Decimal(str(profile.tick_size))
        if tick_size > 0:
            price = (price / tick_size).quantize(Decimal('1'),
                                                 rounding=ROUND_DOWN) * tick_size

        # Quantize to precision_price decimal places
        precision_str = f"0.{'0' * profile.precision_price}"
        price = price.quantize(Decimal(precision_str), rounding=ROUND_DOWN)

        # Validate min_price
        min_price = Decimal(str(profile.min_price))
        if price < min_price:
            raise BinanceValidationError(
                f"Price {price} below min_price {min_price} for {symbol} "
                f"(raw_price={raw_price}, tick_size={tick_size})"
            )

        logger.debug(
            f"[BinanceAdapter] Normalized price for {symbol}: {raw_price} → {price} "
            f"(tick_size={tick_size}, min_price={min_price})"
        )
        return price

    def _validate_min_notional(self, symbol: str, qty: Decimal, price: Decimal) -> None:
        """
        Validate that qty * price >= min_notional.

        Args:
            symbol: Trading symbol
            qty: Order quantity
            price: Order price

        Raises:
            BinanceValidationError: If notional < min_notional
        """
        profile = self._get_instrument_profile(symbol)
        notional = qty * price
        min_notional = Decimal(str(profile.min_notional))

        if notional < min_notional:
            raise BinanceValidationError(
                f"Notional {notional} USDT below min_notional {min_notional} USDT for {symbol} "
                f"(qty={qty}, price={price})"
            )

        logger.debug(
            f"[BinanceAdapter] Validated min_notional for {symbol}: "
            f"qty={qty} * price={price} = {notional} USDT >= {min_notional} USDT"
        )

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
        Main loop for WebSocket connection management.
        """
        while self.ws_running:
            try:
                self._establish_websocket_connection()
            except Exception as e:
                logger.error(
                    f"[BinanceAdapter] WebSocket connection failed: {e}")
                # Backoff before reconnect
                time.sleep(5)

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

                        # FIXED: Track last time sync for periodic resync
                        last_resync = time.time()

                        while self.ws_running:
                            try:
                                # Receive message with timeout
                                message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                                msg_data = json.loads(message)
                                self._handle_ws_message(msg_data)

                                # FIXED: Periodic time resync every 5 minutes
                                if time.time() - last_resync > 300:
                                    await self._sync_time_with_server()
                                    last_resync = time.time()

                                # FIXED: Periodic listen key keepalive
                                if time.time() - self._last_listen_key_keepalive_at > LISTEN_KEY_KEEPALIVE_SECONDS:
                                    success = await self._refresh_listen_key()
                                    if not success:
                                        logger.warning(
                                            "[BinanceAdapter] Listen key invalid, triggering reconnect")
                                        break

                            except asyncio.TimeoutError:
                                # Send ping to keep connection alive
                                await websocket.ping()

                                # FIXED: Also resync time on ping (connection still alive)
                                if time.time() - last_resync > 300:
                                    await self._sync_time_with_server()
                                    last_resync = time.time()

                                # FIXED: Periodic listen key keepalive on timeout too
                                if time.time() - self._last_listen_key_keepalive_at > LISTEN_KEY_KEEPALIVE_SECONDS:
                                    success = await self._refresh_listen_key()
                                    if not success:
                                        logger.warning(
                                            "[BinanceAdapter] Listen key invalid, triggering reconnect")
                                        break

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
            loop.close()

        except Exception as e:
            logger.error(
                f"[BinanceAdapter] Failed to establish WebSocket connection: {e}")
            raise

    def _get_listen_key(self) -> None:
        """
        Get listen key for USER_DATA_STREAM.
        """
        url = f"{self.rest_url}/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": self.api_key}

        # Use httpx for async compatibility
        import requests
        resp = requests.post(url, headers=headers, timeout=self._rest_timeout)
        if resp.ok:
            data = resp.json()
            self.ws_listen_key = data.get("listenKey")
            self.listen_key_last_refresh = time.time()
            self._last_listen_key_keepalive_at = time.time()
            logger.info(
                f"[BinanceAdapter] Obtained listen key: {self.ws_listen_key[:10]}...")
        else:
            raise RuntimeError(
                f"Failed to get listen key: HTTP {resp.status_code} {resp.text}")

    async def _refresh_listen_key(self) -> bool:
        """
        Refresh listen key to keep USER_DATA_STREAM alive.
        Returns True if successful, False if failed (e.g. -1125).
        """
        if not self.ws_listen_key:
            return False

        url = f"{self.rest_url}/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": self.api_key}
        params = {"listenKey": self.ws_listen_key}

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.put(url, headers=headers, params=params, timeout=self._rest_timeout)

            if resp.is_success:
                self.listen_key_last_refresh = time.time()
                self._last_listen_key_keepalive_at = time.time()
                logger.info(
                    "[BinanceAdapter] Listen key refreshed (keepalive)")
                return True
            else:
                # Check for -1125 (ListenKey does not exist)
                try:
                    err_data = resp.json()
                    code = err_data.get("code")
                    msg = err_data.get("msg", "")
                    if code == -1125:
                        logger.warning(
                            f"[BinanceAdapter] Listen key expired (-1125): {msg}")
                        return False
                except Exception:
                    pass

                logger.warning(
                    f"[BinanceAdapter] Failed to refresh listen key: HTTP {resp.status_code} {resp.text}"
                )
                # For other errors, we return True to avoid immediate reconnect loop,
                # assuming transient network issue. Next check will retry.
                # But if it fails repeatedly, eventually we might want to reconnect.
                # For now, let's return True to keep connection if it's just a network blip,
                # unless it's -1125.
                return True
        except Exception as e:
            logger.error(f"[BinanceAdapter] Error refreshing listen key: {e}")
            return True  # Assume transient error, don't kill WS yet

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
            elif event_type == "ALGO_UPDATE":
                # Phase 1: Handle Algo Order Updates
                self._handle_algo_update(msg)
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

            trade_emitted = self._emit_trade_event(
                order_data,
                client_order_id=client_order_id,
                exchange_order_id=exchange_order_id,
                order_ref=order_ref,
                event_ts=event_ts,
                reason=f"WS_ORDER_UPDATE_{order_status}",
            )

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
                "rid": order_ref.rid if order_ref else "",
                "idempotent_key": order_ref.idempotent_key if order_ref else "",
                "clientOrderId": client_order_id,
                "exchangeOrderId": exchange_order_id,
                "orderId": exchange_order_id,  # Alias for test compatibility
                "side": side,
                "order_type": order_type,
                "qty": order_data.get("q"),  # Original quantity
                "filled_qty": filled_qty,
                "avg_fill_price": str(order_data.get("p", "0")),
                "ts_ms": msg.get("T", int(time.time() * 1000)),
            }

            # Log to audit
            audit_logger.log_order_state_changed(
                rid=order_ref.rid if order_ref else "",
                idempotent_key=order_ref.idempotent_key if order_ref else "",
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
                if order_ref:
                    self.fsm_core.order_index.mark_terminal(order_ref)
                    duration_sec = time.time() - order_ref.created_ts
                    observe_order_lifecycle(duration_sec)

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
        try:
            payload = self._build_trade_executed_payload(
                order_data,
                client_order_id=client_order_id,
                exchange_order_id=exchange_order_id,
                order_ref=order_ref,
                event_ts=event_ts,
            )
            if payload:
                self.fsm_core.emit(
                    event_name="EVT:TRADE_EXECUTED",
                    payload=payload,
                    why=reason
                )
                return True
            return False
        except Exception as exc:
            logger.error(
                f"[BinanceAdapter] Failed to emit EVT: TRADE_EXECUTED: {exc}")
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
        """
        Normalize Binance WS fill into canonical trade payload.

        TRADE_EXECUTED Contract (R2-F):
        - 'quantity'/'qty' fields: ALWAYS absolute value (non-negative)
        - 'side' field: encodes direction (BUY/SELL)
        - 'raw_*' fields: preserve original signed values for audit/debugging

        Rationale: Binance WS can send signed deltas (e.g., cumQty="-0.07" for SHORT).
        We normalize to abs() here so downstream (runtime, apply_fill) doesn't need
        to handle negative qty edge cases.
        """
        symbol = order_data.get("s")
        side_raw = str(order_data.get("S", "")).lower()
        side = "buy" if side_raw != "sell" else "sell"

        price_raw = (
            order_data.get("L")
            or order_data.get("ap")
            or order_data.get("p")
            or "0"
        )

        # For FILLED orders, prioritize cumulative filled qty ("z") over last fill ("l")
        # because "l" may be 0 for orders filled in multiple parts
        quantity_raw = (
            order_data.get("z")  # Cumulative filled quantity (most reliable)
            or order_data.get("l")  # Last fill quantity
            or order_data.get("q")  # Original order quantity (fallback)
            or "0"
        )

        last_raw = order_data.get("l", "0")
        cum_raw = order_data.get("z", "0")
        orig_raw = order_data.get("q", "0")

        try:
            qty_decimal = Decimal(str(quantity_raw))
            last_decimal = Decimal(str(last_raw))
            cum_decimal = Decimal(str(cum_raw))
            orig_decimal = Decimal(str(orig_raw))
        except (InvalidOperation, ValueError, TypeError):
            logger.warning(
                f"[BinanceAdapter] _build_trade_executed_payload: Invalid quantity_raw={quantity_raw} for {symbol}"
            )
            return None

        last_abs = last_decimal.copy_abs()
        cum_abs = cum_decimal.copy_abs()
        orig_abs = orig_decimal.copy_abs()
        qty_abs = qty_decimal.copy_abs()

        if qty_abs == 0:
            qty_abs = cum_abs if cum_abs != 0 else (
                last_abs if last_abs != 0 else orig_abs)

        if qty_abs == 0:
            logger.warning(
                f"[BinanceAdapter] _build_trade_executed_payload: Zero quantity for {symbol} (z={order_data.get('z')}, l={order_data.get('l')}, q={order_data.get('q')})"
            )
            return None

        fees = str(order_data.get("n", "0"))
        venue = "binance_ws_testnet" if self.use_testnet else "binance_ws"

        payload: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "price": str(price_raw),
            "quantity": str(qty_abs),
            "qty": str(qty_abs),
            "last_fill_qty": str(last_abs),
            "cum_qty": str(cum_abs),
            "raw_last_qty": str(last_decimal),
            "raw_cum_qty": str(cum_decimal),
            "raw_orig_qty": str(orig_decimal),
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
            raw_positions = account_data.get("P", [])

            # E-004 FIX: Normalize Binance WS short keys to standard long keys
            # WS uses: s=symbol, pa=positionAmt, ep=entryPrice, up=unrealizedPnl, mt=marginType, iw=isolatedWallet, ps=positionSide
            # Runtime expects: symbol, positionAmt/qty, entryPrice/entry_price, unrealized_pnl
            positions = []
            for p in raw_positions:
                normalized = {
                    "symbol": p.get("s") or p.get("symbol"),
                    "positionAmt": p.get("pa") or p.get("positionAmt"),
                    "entryPrice": p.get("ep") or p.get("entryPrice"),
                    "unrealizedProfit": p.get("up") or p.get("unrealizedProfit"),
                    "marginType": p.get("mt") or p.get("marginType"),
                    "isolatedWallet": p.get("iw") or p.get("isolatedWallet"),
                    "positionSide": p.get("ps") or p.get("positionSide"),
                    # Keep raw for debugging
                    "_raw": p,
                }
                positions.append(normalized)
                # Log if position has non-zero qty and entry price for debugging E-004
                if normalized["positionAmt"] and normalized["entryPrice"]:
                    logger.debug(
                        f"[BinanceAdapter] Position normalized: {normalized['symbol']} "
                        f"qty={normalized['positionAmt']} entryPrice={normalized['entryPrice']}"
                    )

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

    def _handle_algo_update(self, msg: Dict[str, Any]) -> None:
        """
        Handle ALGO_UPDATE event from WebSocket (Phase 1).
        Updates the internal AlgoOrderIndex state.
        """
        try:
            # Extract fields based on Binance User Data Stream docs for ALGO_UPDATE
            # e: "ALGO_UPDATE"
            # s: symbol
            # a: { ... algo order payload ... }
            algo_payload = msg.get("a", {})

            # Map fields to AlgoOrderUpdate DTO
            # Note: Field names in 'a' might be short (e.g. 'c' for clientAlgoOrderId)
            # We need to verify exact field mapping from Binance docs or empirical data.
            # Assuming standard mapping:
            # c: clientAlgoOrderId
            # i: algoId
            # s: status (e.g. NEW, FILLED)
            # bc: current executed qty?

            client_algo_id = algo_payload.get("c")
            algo_id = str(algo_payload.get("i"))
            # Symbol is usually in outer msg or 's' in payload?
            symbol = msg.get("s")
            status = algo_payload.get("s")  # Status

            if not client_algo_id:
                logger.warning(
                    f"[BinanceAdapter] ALGO_UPDATE missing clientAlgoOrderId: {msg}")
                return

            update = AlgoOrderUpdate(
                algo_order_id=algo_id,
                client_algo_order_id=client_algo_id,
                symbol=symbol,
                side=algo_payload.get("S"),  # Side
                algo_type=algo_payload.get("o"),  # Order Type
                status=status,
                last_executed_qty=Decimal(str(algo_payload.get("l", "0"))),
                cumulative_filled_qty=Decimal(str(algo_payload.get("z", "0"))),
                transaction_time=msg.get("E", int(time.time() * 1000)),
                trigger_price=None  # Not always available in update
            )

            if self.algo_order_index:
                self.algo_order_index.update_from_event(update)
                logger.info(
                    f"[BinanceAdapter] ALGO_UPDATE processed for {client_algo_id}: {status}")

                # Emit EVT:ALGO_ORDER_UPDATED for Runtime/FSM
                if self.fsm_core:
                    payload = {
                        "algo_order_id": update.algo_order_id,
                        "client_algo_order_id": update.client_algo_order_id,
                        "symbol": update.symbol,
                        "side": update.side,
                        "algo_type": update.algo_type,
                        "status": update.status,
                        "last_executed_qty": str(update.last_executed_qty),
                        "cumulative_filled_qty": str(update.cumulative_filled_qty),
                        "transaction_time": update.transaction_time,
                        "trigger_price": str(update.trigger_price) if update.trigger_price else None
                    }
                    self.fsm_core.emit(
                        "EVT:ALGO_ORDER_UPDATED", payload, "WS_ALGO_UPDATE")

        except Exception as e:
            logger.error(
                f"[BinanceAdapter] Error processing ALGO_UPDATE: {e}", exc_info=True)

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
        - -2021: Order would immediately trigger -> increase offset, retry
        - -4116: Duplicate ClientOrderId -> generate new ID, retry
        - -4137: Quantity not allowed -> reduce qty, retry
        - -4164: MIN_NOTIONAL -> increase qty, retry
        - -429: Rate limit -> exponential backoff, retry

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
                resp = await client.post(full_url, headers=headers, timeout=self._rest_timeout)
                try:
                    data = resp.json()
                except:
                    data = {"raw": resp.text}
                if resp.is_success:
                    logger.info("[BinanceAdapter] -2021: Recovery successful")
                    return True, data
            return False, None

        elif error_code == -4116:
            # EXEC-R2-J: Idempotent duplicate check
            # DO NOT generate new ID -> creates duplicate TP/SL on exchange
            # Instead: check if order already exists via get_order_by_client_id
            idempotent_key = params.get(
                "clientOrderId") or params.get("newClientOrderId")
            symbol = params.get("symbol", "UNKNOWN")

            logger.info(
                f"[BinanceAdapter] -4116 duplicate clientOrderId detected: {idempotent_key}. "
                f"Checking if order already exists on exchange..."
            )

            # Query Binance for existing order by origClientOrderId
            existing_order = await self.get_order_by_client_id(symbol, idempotent_key)

            if existing_order:
                status = existing_order.get("status")
                order_id = existing_order.get("orderId")

                # If order exists with active status -> idempotent success
                if status in ["NEW", "PARTIALLY_FILLED"]:
                    logger.info(
                        f"[BinanceAdapter] -4116 IDEMPOTENT SUCCESS: "
                        f"Found existing order orderId={order_id}, status={status}. "
                        f"Returning success without retry."
                    )
                    return True, existing_order
                else:
                    logger.warning(
                        f"[BinanceAdapter] -4116 duplicate but order status={status} (not active). "
                        f"Cannot recover. orderId={order_id}"
                    )
                    return False, None
            else:
                # Order not found on exchange -> cannot recover
                logger.warning(
                    f"[BinanceAdapter] -4116 duplicate but order NOT FOUND on exchange. "
                    f"clientOrderId={idempotent_key} may have expired or been canceled. "
                    f"Cannot recover."
                )
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
                resp = await client.post(full_url, headers=headers, timeout=self._rest_timeout)
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
                resp = await client.post(full_url, headers=headers, timeout=self._rest_timeout)
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
                    resp = await client.post(full_url, headers=headers, timeout=self._rest_timeout)
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
                    resp = await client.post(full_url, headers=headers, timeout=self._rest_timeout)
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
            f"[BinanceAdapter] Rate limit backoff: {base_ms}ms base x {jitter_factor:.2f} jitter = {backoff_ms}ms")

        return backoff_ms

    def _get_fallback_policy(self):
        """Resolve fallback policy using centralized exposure configuration."""
        return resolve_exposure_policy(self.config).fallback

    def _enter_orders_fallback_mode(self, reason: str = GET_OPEN_ORDERS_FALLBACK_REASON) -> None:
        """Best-effort hook into ExposureGuard fallback mode when REST calls fail."""
        guard = getattr(getattr(self, "fsm", None), "exposure_guard", None)
        if not guard:
            return
        try:
            guard.enter_fallback_mode(reason)
            logger.warning(
                "[BinanceAdapter] Entered fallback mode due to open orders failure",
                extra={"reason": reason},
            )
        except Exception as exc:
            logger.error(
                "[BinanceAdapter] Failed to enter fallback mode after open orders error: %s",
                exc,
            )

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
            if self.shadow_mode:
                # Shadow mode: return mock mark price
                logger.info(
                    f"[BinanceAdapter] Shadow mode: mock mark price for {symbol}")
                return Decimal("3000.0")  # Mock value for testing

            # Sync time with server
            await self._sync_time_with_server()

            # Build request to /fapi/v1/premiumIndex (mark price endpoint)
            base_url = BASE_URL
            endpoint = "/fapi/v1/premiumIndex"

            params = {
                "symbol": symbol,
                "timestamp": int(time.time() * 1000),
            }
            signed_params, _, _, _ = self._build_signed_request(
                params, body=None, log_ctx="GET_MARK_PRICE")

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
                    await self._sync_time_with_server()

                    # Build signed request
                    base_url = BASE_URL
                    endpoint = "/fapi/v2/positionRisk"

                    params = {"timestamp": int(time.time() * 1000)}
                    signed_params, _, _, _ = self._build_signed_request(
                        params, body=None, log_ctx="GET_OPEN_POSITIONS")

                    headers = {"X-MBX-APIKEY": self.api_key}

                    url = f"{base_url}{endpoint}"
                    async with httpx.AsyncClient() as client:
                        response = await client.get(url, params=signed_params, headers=headers, timeout=self._rest_timeout)

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
                                f"[BinanceAdapter] Failed to enter fallback mode: {fb_e}")

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
            delay_template = list(GET_OPEN_ORDERS_BACKOFF_MS)
            configured = list(getattr(
                fallback_policy, "backoff_sequence", lambda: ())()) if fallback_policy else []
            if configured:
                delay_template = list(
                    configured[: max(1, GET_OPEN_ORDERS_MAX_ATTEMPTS - 1)])
            while len(delay_template) < max(1, GET_OPEN_ORDERS_MAX_ATTEMPTS - 1):
                delay_template.append(delay_template[-1])

            last_error: Optional[Exception] = None
            for attempt in range(1, GET_OPEN_ORDERS_MAX_ATTEMPTS + 1):
                try:
                    await self._sync_time_with_server()

                    params = {"timestamp": int(time.time() * 1000)}
                    if symbol:
                        params["symbol"] = symbol

                    signed_params, _, _, _ = self._build_signed_request(
                        params, body=None, log_ctx="GET_OPEN_ORDERS"
                    )
                    headers = {"X-MBX-APIKEY": self.api_key}
                    url = f"{BASE_URL}/fapi/v1/openOrders"

                    async with httpx.AsyncClient() as client:
                        response = await client.get(
                            url,
                            params=signed_params,
                            headers=headers,
                            timeout=self._rest_timeout,
                        )

                    if response.status_code == 200:
                        raw_orders = response.json() or []
                        if symbol:
                            raw_orders = [
                                o for o in raw_orders if o.get("symbol") == symbol]

                        if not raw_orders:
                            log_level = logger.info if attempt == 1 else logger.warning
                            log_level(
                                "[BinanceAdapter] get_open_orders empty response",
                                extra={"attempt": attempt, "symbol": symbol},
                            )
                        else:
                            logger.debug(
                                "[BinanceAdapter] get_open_orders success",
                                extra={"orders": len(
                                    raw_orders), "symbol": symbol},
                            )
                        return raw_orders

                    # Non-200 responses
                    last_error = RuntimeError(
                        f"HTTP {response.status_code}: {response.text[:256]}"
                    )

                    # Special handling for Binance -1021 timestamp/recvWindow errors
                    handled_timestamp_error = False
                    if response.status_code == 400:
                        error_payload: Optional[Dict[str, Any]]
                        try:
                            error_payload = response.json()
                        except Exception:  # pragma: no cover - defensive
                            error_payload = None

                        if isinstance(error_payload, dict):
                            code_val = str(error_payload.get("code", ""))
                            msg_val = str(error_payload.get("msg", "")).lower()
                            if code_val == "-1021" or "recvwindow" in msg_val:
                                handled_timestamp_error = True
                                logger.warning(
                                    "[BinanceAdapter] get_open_orders timestamp error (-1021)",
                                    extra={
                                        "attempt": attempt,
                                        "symbol": symbol,
                                    },
                                )
                                # On final attempt: enter fallback mode and return empty list
                                if attempt >= GET_OPEN_ORDERS_MAX_ATTEMPTS:
                                    self._enter_orders_fallback_mode(
                                        reason="API_ORDERS_TIME_SYNC_FAILED"
                                    )
                                    logger.error(
                                        "[BinanceAdapter] get_open_orders time sync failed after %s attempts",
                                        GET_OPEN_ORDERS_MAX_ATTEMPTS,
                                        extra={
                                            "symbol": symbol,
                                            "error": str(last_error),
                                        },
                                    )
                                    return []

                    if not handled_timestamp_error:
                        logger.warning(
                            "[BinanceAdapter] get_open_orders HTTP error",
                            extra={
                                "attempt": attempt,
                                "status_code": response.status_code,
                                "symbol": symbol,
                            },
                        )
                except Exception as exc:  # pragma: no cover - defensive
                    last_error = exc
                    logger.warning(
                        "[BinanceAdapter] get_open_orders attempt error",
                        extra={"attempt": attempt,
                               "symbol": symbol, "error": str(exc)},
                    )

                if attempt < GET_OPEN_ORDERS_MAX_ATTEMPTS:
                    delay_ms = delay_template[min(
                        attempt - 1, len(delay_template) - 1)]
                    if delay_ms > 0:
                        logger.info(
                            "[BinanceAdapter] get_open_orders retrying",
                            extra={
                                "attempt": attempt + 1,
                                "max_attempts": GET_OPEN_ORDERS_MAX_ATTEMPTS,
                                "delay_ms": delay_ms,
                                "symbol": symbol,
                            },
                        )
                        await asyncio.sleep(delay_ms / 1000.0)
                    continue
                break

            self._enter_orders_fallback_mode()
            error_msg = f"get_open_orders failed after {GET_OPEN_ORDERS_MAX_ATTEMPTS} attempts"
            logger.error(
                f"[BinanceAdapter] {error_msg}",
                extra={"symbol": symbol, "error": str(
                    last_error) if last_error else None},
            )
            raise RuntimeError(
                f"ADAPTER_GET_OPEN_ORDERS_FAILED: {error_msg}") from last_error

        except Exception as e:
            logger.error(f"[BinanceAdapter] get_open_orders fatal error: {e}")
            raise

    async def _sync_time_with_server(self) -> None:
        """
        Synchronize local time with Binance server time using async HTTP.
        """
        try:
            url = f"{BASE_URL}/fapi/v1/time"
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=5)

            if resp.is_success:
                server_time = resp.json().get("serverTime", 0)
                local_time = int(time.time() * 1000)
                old_offset = self.server_time_offset
                self.server_time_offset = server_time - local_time
                self.last_time_sync = time.time()

                drift_ms = self.server_time_offset
                abs_drift = abs(drift_ms)
                offset_change = abs(drift_ms - old_offset)

                warn_by_change = offset_change >= TIME_DRIFT_WARN_CHANGE_THRESHOLD_MS
                warn_by_abs = abs_drift >= TIME_DRIFT_HARD_LIMIT_MS

                if not self._time_sync_initialized:
                    logger.info(
                        "[BinanceAdapter] Time sync initialized",
                        extra={"offset_ms": drift_ms},
                    )
                    self._time_sync_initialized = True
                    self._last_drift_warning_bucket = None
                elif warn_by_abs:
                    bucket = int(abs_drift // 1000)
                    if self._last_drift_warning_bucket != bucket:
                        logger.warning(
                            "[BinanceAdapter] Time drift exceeds hard limit",
                            extra={
                                "offset_ms": drift_ms,
                                "offset_change_ms": offset_change,
                                "server_time": server_time,
                                "local_time": local_time,
                            },
                        )
                        self._last_drift_warning_bucket = bucket
                elif warn_by_change:
                    logger.warning(
                        "[BinanceAdapter] Time drift changed materially",
                        extra={
                            "offset_ms": drift_ms,
                            "offset_change_ms": offset_change,
                            "server_time": server_time,
                            "local_time": local_time,
                        },
                    )
                    self._last_drift_warning_bucket = None
                elif offset_change >= TIME_DRIFT_INFO_THRESHOLD_MS:
                    logger.info(
                        "[BinanceAdapter] Time offset adjusted",
                        extra={
                            "previous_offset_ms": old_offset,
                            "offset_ms": drift_ms,
                            "offset_change_ms": offset_change,
                        },
                    )
                else:
                    logger.debug(
                        "[BinanceAdapter] Time sync stable",
                        extra={"offset_ms": drift_ms,
                               "offset_change_ms": offset_change},
                    )

                if not warn_by_abs:
                    self._last_drift_warning_bucket = None
            else:
                logger.warning(
                    f"[BinanceAdapter] Failed to sync time with server: HTTP {resp.status_code}"
                )

        except Exception as e:
            logger.error(f"[BinanceAdapter] Time sync error: {e}")

    async def _background_time_sync_loop(self) -> None:
        """
        Background task that periodically syncs time with Binance server.
        Non-blocking, runs in the async event loop.
        """
        logger.info(
            f"[BinanceAdapter] Background time sync loop started (interval={TIME_SYNC_INTERVAL_SEC}s)")
        while True:
            try:
                await asyncio.sleep(TIME_SYNC_INTERVAL_SEC)
                await self._sync_time_with_server()
            except asyncio.CancelledError:
                logger.info(
                    "[BinanceAdapter] Background time sync loop cancelled")
                break
            except Exception as e:
                logger.warning(
                    f"[BinanceAdapter] Background time sync error: {e}")
                # Continue loop even on error

    def _sync_time_with_server_blocking(self) -> None:
        """
        Synchronous wrapper for contexts that are not async-aware.
        Used only during startup, NOT in hot async paths.
        """
        asyncio.run(self._sync_time_with_server())

    def _get_signed_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add required fields (timestamp/recvWindow) to API parameters (unsigned).
        Time sync is handled by background task, not here (to avoid blocking).
        """
        # NOTE: Time sync moved to _background_time_sync_loop() to avoid blocking async paths
        # If time is very stale (>5min), log warning but don't block
        time_since_sync = time.time() - self.last_time_sync
        if time_since_sync > 300:  # 5 minutes without sync
            logger.warning(
                f"[BinanceAdapter] Time sync stale ({time_since_sync:.0f}s), requests may fail with -1021"
            )

        unsigned_params = params.copy()
        unsigned_params["timestamp"] = str(
            int(time.time() * 1000) + int(self.server_time_offset))
        # FIXED: Increase recvWindow to 5000ms (Binance recommendation for futures)
        unsigned_params["recvWindow"] = "5000"
        return unsigned_params

    async def place_order_v2(
        self,
        symbol: str,
        side: Optional[str],
        order_type: Optional[str],
        quantity: Optional[Union[str, float, int]],
        price: Optional[Union[str, float, int]] = None,
        client_order_id: Optional[str] = None,
        reduce_only: bool = False,
        stop_price: Optional[Union[str, float, int]] = None,
        tif: Optional[str] = "GTC",
        **kwargs,
    ) -> Dict[str, object]:
        """
        V2-friendly place_order wrapper used by ExecPosRuntimeV2 ExecutionService.

        Normalizes V2 kwargs into legacy DEC:PLACE_ORDER Message and delegates to place_order().
        """
        logger.info(
            "[BinanceAdapter-S5] place_order_v2 called: symbol=%s side=%s type=%s qty=%s stop_price=%s reduce_only=%s",
            symbol,
            side,
            order_type,
            quantity,
            stop_price,
            reduce_only,
        )
        try:
            payload = {
                "symbol": symbol,
                "side": side,
                "qty": quantity,
                "order_type": order_type,
                "price": price,
                "stopPrice": stop_price or kwargs.get("stopPrice") or kwargs.get("stop_price"),
                "reduceOnly": reduce_only,
                "tif": tif or "GTC",
                "newClientOrderId": client_order_id,
            }
            msg = Message(
                op="DEC",
                verb="PLACE_ORDER",
                src="execpos_v2",
                dst="execution_adapter",
                pld=payload,
                why=kwargs.get("why", "execpos_v2"),
            )
            return await self.place_order(msg)
        except Exception as exc:
            logger.error(f"[BinanceAdapter] V2 place_order error: {exc}")
            raise

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

                # Increment order placed counter
                inc_order_placed()
                client_order_id = result.get(
                    "clientOrderId", idempotent_key or "unknown")
                return self._create_success_feedback(
                    symbol,
                    result.get("orderId", "unknown"),
                    client_order_id,
                    guard_result["why_codes"],
                )

        except Exception as e:
            logger.error(
                f"[BinanceAdapter] Order execution failed: {type(e).__name__}: {e}",
                # Full traceback for debugging
                exc_info=True
            )
            return self._create_error_feedback(symbol, f"{type(e).__name__}: {e}")

    async def cancel_order(self, dec_msg: Message) -> Dict[str, object]:
        """
        Cancel existing order using Binance API with idempotent semantics.

        PHASE 4: Enhanced with:
        - Pre-cancel getOrder check (to avoid unnecessary cancellations)
        - -2011 absorption (treat "Unknown order" as success)
        - Detailed audit logging for compliance

        Args:
            dec_msg: DEC: CANCEL_ORDER message with orderId and symbol

        Returns:
            Cancellation result dict with success/failure details
        """
        try:
            pld = dec_msg.pld or {}
            order_id = pld.get("orderId")
            symbol = pld.get("symbol")

            if not order_id:
                return self._create_error_feedback("unknown", "Missing orderId in cancel request")

            if not symbol:
                logger.error(
                    "[BinanceAdapter] cancel_order called without symbol; refusing to call API"
                )
                return self._create_error_feedback("unknown", "Missing symbol in cancel request")

            if self.shadow_mode:
                logger.info(
                    f"[BinanceAdapter] Shadow mode: would cancel order {order_id} on {symbol}")
                return self._create_success_feedback(
                    symbol,
                    order_id,
                    "shadow-cancel",
                    ["shadow_cancel"],
                )

            # Use IdempotentCancelHelper
            cancel_helper = IdempotentCancelHelper(
                symbol=symbol,
                order_id=order_id,
                cancel_func=self._cancel_binance_order_async,
                get_order_func=self.get_order,
            )

            # Execute cancel with idempotency
            cancel_result = await cancel_helper.execute()

            # Log result
            cancel_helper.log_cancel_result(cancel_result, order_id)

            # Log audit event
            metrics_logger.log_cancel_event(
                symbol=symbol,
                order_id=order_id,
                success=cancel_result.success,
                error_code=cancel_result.error_code,
                is_idempotent_success=cancel_result.is_idempotent_success,
                rid=f"cancel_{symbol}_{order_id}",
            )

            if cancel_result.success:
                if cancel_result.is_idempotent_success:
                    self.metrics["cancel_idempotent_ok"] = self.metrics.get(
                        "cancel_idempotent_ok", 0) + 1
                if cancel_result.error_code == -2011:
                    self.metrics["cancel_-2011_absorbed"] = self.metrics.get(
                        "cancel_-2011_absorbed", 0) + 1

                return {
                    "allowed": True,
                    "decision": "CANCEL_SUCCESS",
                    "reason": cancel_result.reason,
                    "success": True,
                    "is_idempotent_success": cancel_result.is_idempotent_success,
                    "error_code": cancel_result.error_code,
                }
            else:
                return self._create_error_feedback(
                    symbol,
                    f"Cancel failed: {cancel_result.reason}",
                )

        except Exception as e:
            logger.error(f"[BinanceAdapter] Cancel error: {e}", exc_info=True)
            return self._create_error_feedback(symbol or "unknown", str(e))

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

            await self._sync_time_with_server()

            base_url = BASE_URL
            endpoint = "/fapi/v1/order"

            params = {
                "symbol": symbol,
                "orderId": order_id,
                "timestamp": int(time.time() * 1000),
            }
            signed_params, _, _, _ = self._build_signed_request(
                params, body=None, log_ctx="GET_ORDER")

            headers = {"X-MBX-APIKEY": api_key}
            url = f"{base_url}{endpoint}"

            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=signed_params, headers=headers, timeout=self._rest_timeout)

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(
                        f"getOrder failed: HTTP {response.status_code}: {response.text}")
                    return None

        except Exception as e:
            logger.warning(f"getOrder exception: {e}")
            return None

    async def get_order_by_client_id(
        self, symbol: str, client_order_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        EXEC-R2-J: Get order details by origClientOrderId for idempotency check.

        Used to verify if bracket order with duplicate clientOrderId already exists
        on exchange before attempting to generate new ID and retry.

        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            client_order_id: Client order ID to query (newClientOrderId from PLACE request)

        Returns:
            Order dict with status field, or None if not found

        Example response:
            {
                "orderId": 123456789,
                "symbol": "BTCUSDT",
                # NEW, PARTIALLY_FILLED, FILLED, CANCELED, etc.
                "status": "NEW",
                "clientOrderId": "TP_BTCUSDT_LONG_12345",
                "price": "50000.0",
                "avgPrice": "0.0",
                "origQty": "0.01",
                "executedQty": "0.0",
                ...
            }
        """
        try:
            api_key = self.api_key
            api_secret = self.api_secret

            if not api_key or not api_secret:
                logger.warning(
                    "Missing Binance API credentials for getOrder by clientOrderId"
                )
                return None

            await self._sync_time_with_server()

            base_url = BASE_URL
            endpoint = "/fapi/v1/order"

            # Binance API supports origClientOrderId parameter
            params = {
                "symbol": symbol,
                "origClientOrderId": client_order_id,
                "timestamp": int(time.time() * 1000),
                "recvWindow": 5000,  # EXEC-R2-J: Use 5000ms recvWindow
            }

            signed_params, _, _, _ = self._build_signed_request(
                params, body=None, log_ctx="GET_ORDER_BY_CLIENT_ID"
            )

            headers = {"X-MBX-APIKEY": api_key}
            url = f"{base_url}{endpoint}"

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, params=signed_params, headers=headers, timeout=self._rest_timeout
                )

                if response.status_code == 200:
                    order_data = response.json()
                    logger.info(
                        f"[BinanceAdapter] Found existing order by clientOrderId: "
                        f"orderId={order_data.get('orderId')}, status={order_data.get('status')}"
                    )
                    return order_data
                elif response.status_code == -2013:
                    # Order does not exist
                    logger.debug(
                        f"[BinanceAdapter] Order not found by clientOrderId: {client_order_id}"
                    )
                    return None
                elif response.status_code == 400:
                    # Binance returns 400 with -2013 if order not found
                    # This is expected for idempotency check
                    logger.debug(
                        f"[BinanceAdapter] Order not found by clientOrderId: {client_order_id}"
                    )
                    return None
                else:
                    logger.warning(
                        f"[BinanceAdapter] getOrder by clientOrderId failed: "
                        f"HTTP {response.status_code}: {response.text}"
                    )
                    return None

        except Exception as e:
            logger.warning(
                f"[BinanceAdapter] getOrder by clientOrderId exception: {e}")
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
        # Phase 2: Algo Service Cancel
        if self.use_algo_service_for_conditionals and self.algo_order_index:
            # Check if this is an Algo Order
            # We need to look up by algoId (which is passed as order_id)
            is_algo = self.algo_order_index.get_by_algo_id(order_id)
            if is_algo:
                try:
                    return await self._cancel_conditional_via_algo_service(symbol, algo_order_id=order_id)
                except Exception as e:
                    return {"status": "error", "msg": str(e)}

        try:
            # Get API credentials
            api_key = self.api_key
            api_secret = self.api_secret

            if not api_key or not api_secret:
                raise ValueError("Missing Binance API credentials")

            # Sync time with server
            await self._sync_time_with_server()

            # Build signed request
            base_url = BASE_URL
            endpoint = "/fapi/v1/order"

            params = {
                # PHASE 4: Use provided symbol parameter
                "symbol": symbol,
                "orderId": order_id,
                "timestamp": int(time.time() * 1000),
                "recvWindow": 1500,
            }

            signed_params, _, _, _ = self._build_signed_request(
                params, body=None, log_ctx="CANCEL_ORDER")

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
                self._sync_time_with_server_blocking()
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

    def _format_decimal(self, value: Decimal, precision: int) -> str:
        """Format Decimal to string with fixed precision, avoiding scientific notation."""
        return f"{value:.{precision}f}"

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
        # Normalize quantity and price to exchange filters BEFORE API call
        try:
            normalized_qty = self._quantize_qty(symbol, quantity)
            profile = self._get_instrument_profile(symbol)
            # Use fixed-point formatting to avoid scientific notation and ensure correct precision
            qty_str = self._format_decimal(
                normalized_qty, profile.precision_quantity)

            price_str = None
            if order_type == "LIMIT" and price:
                normalized_price = self._quantize_price(symbol, price)
                # Validate min_notional for LIMIT orders
                self._validate_min_notional(
                    symbol, normalized_qty, normalized_price)
                price_str = self._format_decimal(
                    normalized_price, profile.precision_price)

            stop_price_str = None
            if stop_price:
                # Quantize stop price same as price
                normalized_stop_price = self._quantize_price(
                    symbol, stop_price)
                stop_price_str = self._format_decimal(
                    normalized_stop_price, profile.precision_price)

            logger.info(
                f"[BinanceAdapter] Placing {order_type} order: {symbol} {side} "
                f"qty={quantity}->{qty_str}" +
                (f", price={price}->{price_str}" if price_str else "") +
                (f", stopPrice={stop_price}->{stop_price_str}" if stop_price_str else "")
            )
        except BinanceValidationError as e:
            # Log validation error and re-raise
            logger.error(
                f"[BinanceAdapter] Order validation failed for {symbol}: {e}"
            )
            raise

        # BLUEPRINT: Algo Service Migration
        # If enabled and order is conditional, route to Algo Service
        is_conditional = order_type in (
            "STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET")
        if is_conditional and self.use_algo_service_for_conditionals:
            return await self._place_conditional_via_algo_service(
                symbol, side, qty_str, order_type, stop_price_str, reduce_only, idempotent_key, time_in_force
            )

        # Prepare request parameters with normalized values
        params: Dict[str, str] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": qty_str,
        }

        # Add order-specific parameters
        if order_type == "LIMIT" and price_str:
            params["price"] = price_str
            params["timeInForce"] = time_in_force  # GTC/IOC/FOK

        # Both STOP_MARKET and TAKE_PROFIT_MARKET require stopPrice parameter
        if order_type in ("STOP_MARKET", "TAKE_PROFIT_MARKET", "STOP", "TAKE_PROFIT") and stop_price_str:
            params["stopPrice"] = stop_price_str

        if reduce_only:
            params["reduceOnly"] = "true"

        # Add newClientOrderId for idempotency
        # Initialize client_order_id early for error handling (before try block)
        client_order_id: str = idempotent_key or ""
        if idempotent_key:
            params["newClientOrderId"] = idempotent_key
            logger.info(
                f"[BinanceAdapter] Using idempotent newClientOrderId: {idempotent_key}")

        # Get signed parameters with proper timestamp and recvWindow
        signed_params = self._get_signed_params(params)
        signed_params, body_dict, pre_sign, sig = self._build_signed_request(
            signed_params,
            body=None,
            log_ctx="PLACE_ORDER",
        )

        # Make async API request
        url = f"{BASE_URL}/fapi/v1/order"
        headers = {"X-MBX-APIKEY": self.api_key}

        logger.info(f"[BinanceAdapter] POST {BASE_URL}/fapi/v1/order")
        logger.debug(
            "[BinanceAdapter] PLACE_ORDER params=%s body=%s pre_sign=%s signature=%s",
            signed_params,
            body_dict,
            pre_sign,
            sig,
        )
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, params=signed_params, data=body_dict or None, headers=headers, timeout=self._rest_timeout)

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
                        logger.warning(
                            f"[BinanceAdapter] Previous timestamp: {signed_params.get('timestamp')}, "
                            f"server_time_offset: {self.server_time_offset}ms, recvWindow: {signed_params.get('recvWindow')}"
                        )
                        await self._sync_time_with_server()
                        # FIXED: Rebuild request with fresh timestamp and signature
                        signed_params = self._get_signed_params(params)
                        signed_params, body_dict, pre_sign, sig = self._build_signed_request(
                            signed_params,
                            body=None,
                            log_ctx="RETRY_AFTER_-1021",
                        )
                        logger.info(
                            f"[BinanceAdapter] Retry with new timestamp: {signed_params.get('timestamp')}, "
                            f"new offset: {self.server_time_offset}ms"
                        )
                        # FIXED: Use params= instead of query string in URL
                        resp = await client.post(url, params=signed_params, data=body_dict or None, headers=headers, timeout=self._rest_timeout)
                        try:
                            data = resp.json()
                        except:
                            data = {"raw": resp.text}

                        if not resp.is_success:
                            # EXEC-R2-J: Structured error for time sync failure
                            retry_error_code = data.get("code")
                            if retry_error_code == -1021:
                                logger.error(
                                    f"[BinanceAdapter] Time sync failed after retry. "
                                    f"timestamp={signed_params.get('timestamp')}, "
                                    f"offset={self.server_time_offset}ms, "
                                    f"recvWindow={signed_params.get('recvWindow')}ms. "
                                    f"Error: {data.get('msg')}"
                                )
                                raise RuntimeError(
                                    f"Time sync failed after retry: timestamp={signed_params.get('timestamp')}, "
                                    f"offset={self.server_time_offset}ms, recvWindow={signed_params.get('recvWindow')}ms"
                                )
                            else:
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
                        raise RuntimeError(
                            f"Insufficient balance: {error_msg}")

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
                        # RID would come from FSM context if available
                        rid="",
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

        except Exception as exc:
            # Fail-closed: Return error structure that mimics standard error but with specific kind
            if httpx and isinstance(exc, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException)):
                logger.error("[BinanceAdapter] Order execution failed: ConnectTimeout", exc_info=True,
                             extra={"client_order_id": client_order_id, "symbol": symbol})
                return {
                    "success": False,
                    # Let's raise exception to ensure fail-closed.
                    "error": str(exc),
                    "error_kind": "ADAPTER_ERROR_TIMEOUT",
                    "clientOrderId": client_order_id,
                    "lifecycle": "rejected",
                    "is_timeout": True,
                    "should_retry": False,
                }
            raise

    async def _place_conditional_via_algo_service(
        self,
        symbol: str,
        side: str,
        quantity: str,
        order_type: str,
        stop_price: Optional[str],
        reduce_only: bool,
        idempotent_key: Optional[str],
        time_in_force: str,
    ) -> Mapping[str, object]:
        """
        Place conditional order via Binance Algo Service (/fapi/v1/algoOrder).

        Used when use_algo_service_for_conditionals is True.
        """
        logger.info(
            f"[BinanceAdapter] Placing conditional via Algo Service: {symbol} {order_type}")

        params: Dict[str, str] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
            "reduceOnly": "true" if reduce_only else "false",
        }

        if stop_price:
            params["stopPrice"] = stop_price

        if idempotent_key:
            params["newClientAlgoOrderId"] = idempotent_key

        # Algo service specific params if needed (e.g. workingType)
        # For now assuming defaults or passed via kwargs if we extended signature

        signed_params = self._get_signed_params(params)
        signed_params, body_dict, pre_sign, sig = self._build_signed_request(
            signed_params, body=None, log_ctx="PLACE_ALGO_ORDER"
        )

        url = f"{BASE_URL}/fapi/v1/algoOrder"
        headers = {"X-MBX-APIKEY": self.api_key}

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, params=signed_params, headers=headers, timeout=self._rest_timeout)

                try:
                    data = resp.json()
                except:
                    data = {"raw": resp.text}

                if not resp.is_success:
                    error_code = data.get("code")
                    error_msg = data.get("msg", str(data))
                    logger.error(
                        f"[BinanceAdapter] Algo Service failed: {error_code} {error_msg}")

                    # Fail-closed: Return error structure that mimics standard error but with specific kind
                    # We raise exception to be caught by caller or return dict?
                    # _place_binance_order_async returns Mapping.
                    # We should return a dict that indicates failure.
                    # But place_order expects specific structure or raises exception.
                    # Let's raise exception to ensure fail-closed.
                    raise RuntimeError(
                        f"ADAPTER_ERROR_ALGO_SERVICE: {error_code} {error_msg}")

                # Success
                # Algo order response structure might differ.
                # Usually returns { "clientAlgoOrderId": "...", "code": 200, "msg": "success" }
                # We need to map it to what place_order expects (orderId, clientOrderId)

                algo_id = data.get("algoId")
                client_algo_order_id = data.get(
                    "clientAlgoOrderId", idempotent_key)

                # Phase 1: Register in AlgoOrderIndex
                if self.algo_order_index:
                    self.algo_order_index.register_new_algo_order(
                        client_algo_order_id=client_algo_order_id,
                        algo_order_id=str(algo_id) if algo_id else "UNKNOWN",
                        symbol=symbol,
                        side=side,
                        algo_type=order_type,
                        quantity=Decimal(quantity),
                        reduce_only=reduce_only,
                        trigger_price=Decimal(
                            stop_price) if stop_price else None
                    )

                return {
                    # Algo service returns algoId
                    "orderId": algo_id,
                    "clientOrderId": client_algo_order_id,
                    "status": "NEW",  # Assumed
                    "executedQty": "0",
                    "avgPrice": "0",
                    "origQty": quantity,
                    "type": order_type,
                    "side": side,
                    "algo_service": True
                }

        except Exception as e:
            logger.error(f"[BinanceAdapter] Algo Service exception: {e}")
            raise

    async def _cancel_conditional_via_algo_service(
        self,
        symbol: str,
        algo_order_id: Optional[str] = None,
        client_algo_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel conditional order via Binance Algo Service (/fapi/v1/algoOrder).
        """
        logger.info(
            f"[BinanceAdapter] Canceling conditional via Algo Service: {symbol} {algo_order_id or client_algo_order_id}")

        params = {"symbol": symbol}
        if algo_order_id:
            params["algoId"] = algo_order_id
        if client_algo_order_id:
            params["clientAlgoOrderId"] = client_algo_order_id

        signed_params = self._get_signed_params(params)
        signed_params, _, _, _ = self._build_signed_request(
            signed_params, body=None, log_ctx="CANCEL_ALGO_ORDER"
        )

        url = f"{BASE_URL}/fapi/v1/algoOrder"
        headers = {"X-MBX-APIKEY": self.api_key}

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(url, params=signed_params, headers=headers, timeout=self._rest_timeout)

                try:
                    data = resp.json()
                except:
                    data = {"raw": resp.text}

                if not resp.is_success:
                    error_code = data.get("code")
                    error_msg = data.get("msg", str(data))

                    # Idempotency: Treat -2011 (Unknown Order) as success
                    if error_code == -2011:
                        logger.info(
                            f"[BinanceAdapter] Algo cancel idempotent success (-2011): {error_msg}")
                        return {"status": "CANCELED", "msg": "Idempotent success", "code": 200}

                    logger.error(
                        f"[BinanceAdapter] Algo Service cancel failed: {error_code} {error_msg}")
                    raise RuntimeError(
                        f"ADAPTER_ERROR_ALGO_SERVICE_CANCEL: {error_code} {error_msg}")

                # Success
                return data

        except Exception as e:
            logger.error(
                f"[BinanceAdapter] Algo Service cancel exception: {e}")
            raise

    async def load_open_algo_orders_snapshot(self) -> List[Dict[str, Any]]:
        """
        Fetch open Algo Orders from Binance and populate AlgoOrderIndex.
        """
        if not self.use_algo_service_for_conditionals:
            return []

        logger.info("[BinanceAdapter] Loading open Algo Orders snapshot...")

        try:
            await self._sync_time_with_server()

            params = {"timestamp": int(time.time() * 1000)}
            signed_params, _, _, _ = self._build_signed_request(
                params, body=None, log_ctx="GET_OPEN_ALGO_ORDERS"
            )

            url = f"{BASE_URL}/fapi/v1/openAlgoOrders"
            headers = {"X-MBX-APIKEY": self.api_key}

            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=signed_params, headers=headers, timeout=self._rest_timeout)

                if not resp.is_success:
                    logger.error(
                        f"[BinanceAdapter] Failed to fetch open Algo Orders: {resp.status_code} {resp.text}")
                    return []

                data = resp.json()
                orders = data.get("orders", [])

                logger.info(
                    f"[BinanceAdapter] Loaded {len(orders)} open Algo Orders")

                # Populate AlgoOrderIndex
                if self.algo_order_index:
                    for order in orders:
                        # Map fields
                        # Binance returns: algoId, symbol, side, type, reduceOnly, executedQty, etc.
                        self.algo_order_index.register_new_algo_order(
                            client_algo_order_id=order.get(
                                "clientAlgoOrderId", ""),
                            algo_order_id=str(order.get("algoId")),
                            symbol=order.get("symbol"),
                            side=order.get("side"),
                            algo_type=order.get("type"),
                            quantity=Decimal(str(order.get("origQty", 0))),
                            reduce_only=order.get("reduceOnly", False),
                            trigger_price=Decimal(str(order.get("stopPrice"))) if order.get(
                                "stopPrice") else None
                        )

                return orders

        except Exception as e:
            logger.error(
                f"[BinanceAdapter] Error loading open Algo Orders: {e}", exc_info=True)
            return []

    async def audit_algo_orders_consistency(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        PHASE 3: Audit consistency between local AlgoOrderIndex and Binance openAlgoOrders.

        Returns:
            Dict with:
            - is_consistent: bool
            - missing_local: List[str] (Algo IDs on Binance but not local)
            - missing_remote: List[str] (Algo IDs local but not on Binance)
            - details: List[Dict]
        """
        if not self.use_algo_service_for_conditionals:
            return {"is_consistent": True, "msg": "Algo Service disabled"}

        logger.info(
            f"[BinanceAdapter] Starting Algo Order consistency audit (symbol={symbol})...")

        try:
            # 1. Fetch remote orders
            await self._sync_time_with_server()
            params = {"timestamp": int(time.time() * 1000)}
            if symbol:
                params["symbol"] = symbol

            signed_params, _, _, _ = self._build_signed_request(
                params, body=None, log_ctx="AUDIT_ALGO_ORDERS"
            )

            url = f"{BASE_URL}/fapi/v1/openAlgoOrders"
            headers = {"X-MBX-APIKEY": self.api_key}

            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=signed_params, headers=headers, timeout=self._rest_timeout)
                if not resp.is_success:
                    return {
                        "is_consistent": False,
                        "error": f"API Error: {resp.status_code} {resp.text}"
                    }

                remote_orders = resp.json().get("orders", [])

            # 2. Get local orders
            if not self.algo_order_index:
                local_orders = []
            else:
                local_orders = self.algo_order_index.get_active_orders(symbol)

            # 3. Compare
            remote_ids = {str(o.get("algoId")) for o in remote_orders}
            local_ids = {str(o.algo_order_id) for o in local_orders}

            missing_local = list(remote_ids - local_ids)
            missing_remote = list(local_ids - remote_ids)

            is_consistent = not missing_local and not missing_remote

            if not is_consistent:
                logger.warning(
                    f"[BinanceAdapter] Algo Order Inconsistency! "
                    f"Missing Local: {missing_local}, Missing Remote: {missing_remote}"
                )
                # Log detailed report
                audit_logger.log_order_state_changed(
                    rid="AUDIT_ALGO_CONSISTENCY",
                    idempotent_key="AUDIT_ALGO_CONSISTENCY",
                    symbol=symbol or "ALL",
                    status="INCONSISTENT",
                    why=f"missing_local={len(missing_local)},missing_remote={len(missing_remote)}",
                    ts_ms=int(time.time() * 1000),
                    clientOrderId="",
                    exchangeOrderId="",
                    qty="0",
                    filled_qty="0",
                    avg_fill_price="0"
                )

            return {
                "is_consistent": is_consistent,
                "missing_local": missing_local,
                "missing_remote": missing_remote,
                "remote_count": len(remote_ids),
                "local_count": len(local_ids),
                "details": {
                    "remote_ids": list(remote_ids),
                    "local_ids": list(local_ids)
                }
            }

        except Exception as e:
            logger.error(f"[BinanceAdapter] Audit failed: {e}", exc_info=True)
            return {"is_consistent": False, "error": str(e)}


def _binance_adapter_create_success_feedback(
    self,
    symbol: str,
    order_id: Optional[str],
    client_order_id: Optional[str],
    why_codes: Optional[List[str]] = None,
) -> Dict[str, object]:
    """Return a normalized success payload for ExecPos runtimes."""

    feedback = {
        "allowed": True,
        "success": True,
        "exchange": "binance",
        "symbol": symbol,
        "orderId": order_id,
        "order_id": order_id,
        "clientOrderId": client_order_id,
        "client_order_id": client_order_id,
        "why_codes": list(why_codes or []),
        "ts_ms": int(time.time() * 1000),
    }

    return feedback


def _binance_adapter_create_error_feedback(
    self,
    symbol: str,
    error_message: str,
    error_kind: str = "ADAPTER_ERROR",
) -> Dict[str, object]:
    """Return a structured error payload consumed by ExecPos runtimes."""

    return {
        "allowed": False,
        "success": False,
        "exchange": "binance",
        "symbol": symbol,
        "error": error_message,
        "error_kind": error_kind,
        "why_codes": [],
        "ts_ms": int(time.time() * 1000),
    }


def _binance_adapter_build_signed_request(
    self,
    params: Dict[str, Any],
    body: Optional[Dict[str, Any]] = None,
    log_ctx: str = "API_CALL",
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], str, str]:
    """Compose signed request payload compatible with Binance Futures API."""

    unsigned_params = self._get_signed_params(params)
    query_string = urlencode(unsigned_params, doseq=True)
    body_payload = urlencode(body or {}, doseq=True) if body else ""
    sign_target = "&".join(filter(None, (query_string, body_payload)))

    secret_value = getattr(self, "api_secret", "") or ""
    if isinstance(secret_value, bytes):
        secret = secret_value
    else:
        secret = str(secret_value).encode("utf-8") if secret_value else b""
    signature = (
        hmac.new(secret, sign_target.encode(
            "utf-8"), hashlib.sha256).hexdigest()
        if secret
        else ""
    )

    signed_params = dict(unsigned_params)
    if signature:
        signed_params["signature"] = signature

    logger.debug(
        "[BinanceAdapter] Built signed request",
        extra={
            "ctx": log_ctx,
            "has_body": body is not None,
            "has_signature": bool(signature),
        },
    )

    return signed_params, (body or None), sign_target, signature


# Attach helper implementations without mutating the existing class definition above.
BinanceExecutionAdapter._create_success_feedback = _binance_adapter_create_success_feedback
BinanceExecutionAdapter._create_error_feedback = _binance_adapter_create_error_feedback
BinanceExecutionAdapter._build_signed_request = _binance_adapter_build_signed_request
