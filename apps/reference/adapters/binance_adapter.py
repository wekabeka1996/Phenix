"""
Binance Futures Exchange Adapter (Unified Implementation)

Implements AbstractExchangeAdapter for Binance Futures (USDM).
Handles API key signing, endpoint selection (live/testnet), error handling,
WebSocket USER_DATA_STREAM for real-time order updates, and FSM integration.

This adapter combines functionality from:
- BinanceAdapter (REST API layer)
- BinanceExecutionAdapter (WebSocket + FSM integration)

Inherits from vfoundation.core.adapters.base.AbstractExchangeAdapter to ensure
compatibility with the generic FSM interface.
"""

import json as _json
import asyncio
import hashlib
import hmac
import logging
import os
import random
import threading
import time
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlencode, quote_plus

import httpx

from vfoundation.core.adapters.base import (
    AbstractExchangeAdapter,
    ExchangeOrderParams,
    ExchangeOrderResponse,
    ExchangePosition,
)

# Optional imports for FSM integration
try:
    from vfoundation.core.protocol import Message
except ImportError:
    Message = None  # type: ignore

# Optional telemetry imports
try:
    from apps.reference.telemetry.metrics import (
        inc_order_placed,
        inc_order_filled,
        inc_order_state,
        observe_order_lifecycle,
    )
except ImportError:
    def inc_order_placed(): pass
    def inc_order_filled(): pass
    def inc_order_state(status: str): pass
    def observe_order_lifecycle(duration_sec: float): pass

try:
    from apps.reference.telemetry.audit_logger import audit_logger
except ImportError:
    class _MockAuditLogger:
        def log_order_state_changed(self, **kwargs): pass
    audit_logger = _MockAuditLogger()

LOG = logging.getLogger(__name__)


async def _coerce_json(obj):
    """
    Повертає dict із httpx.Response / str / bytes / dict.
    Може await json() якщо це coroutine (для тестів).
    """
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "json"):  # httpx.Response
        json_result = obj.json()
        # Handle both sync and async json() for tests
        if hasattr(json_result, '__await__'):
            return await json_result
        return json_result
    if isinstance(obj, (bytes, bytearray)):
        return _json.loads(obj.decode("utf-8"))
    if isinstance(obj, str):
        return _json.loads(obj)
    raise TypeError(f"Unsupported JSON payload type: {type(obj)!r}")


class BinanceValidationError(Exception):
    """
    Raised when order parameters fail Binance validation rules.

    Examples:
    - Quantity below min_qty
    - Price precision exceeds allowed tick_size
    - Notional value below minimum
    """
    pass


class BinanceAPIError(Exception):
    def __init__(
        self,
        code: int,
        msg: str,
        *,
        nrr_code: Optional[str] = None,
        http_status: Optional[int] = None,
        payload: Optional[dict] = None,
    ) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.nrr_code = nrr_code
        self.http_status = http_status
        self.payload = payload or {}

    def __str__(self) -> str:
        return f"[{self.code}] {self.msg} ({self.nrr_code or 'no-nrr'})"


class BinanceAdapter(AbstractExchangeAdapter):
    """
    Binance Futures (USDM) Unified Exchange Adapter.

    Implements AbstractExchangeAdapter to provide a consistent interface
    for vfoundation FSM domains. Combines REST API and WebSocket functionality.

    Features:
    - REST API for orders, positions, market data
    - WebSocket USER_DATA_STREAM for real-time order updates
    - FSM integration via Message-based place_order/cancel_order
    - Bracket error handling with retry strategies
    - Idempotent cancel with -2011 absorption
    - Telemetry and audit logging
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        base_url: str = "https://testnet.binancefuture.com",
        config: dict | None = None,
        *,
        session: Optional[httpx.AsyncClient] = None,
        timeout: float = 30.0,
        fsm=None,
        shadow_mode: bool = False,
        **kwargs,
    ):
        """
        Initialize Binance adapter.

        Args:
            api_key: Binance API key (can also be in config or env)
            api_secret: Binance API secret (can also be in config or env)
            base_url: Binance Futures base URL
            config: Configuration dict or Pydantic config object
            session: Optional httpx.AsyncClient for testing
            timeout: Request timeout in seconds
            fsm: FSM instance for event emission (WebSocket mode)
            shadow_mode: If True, no live API calls (for testing)
            **kwargs: Additional arguments (fsm_core, rest_url)
        """
        rest_url = kwargs.pop("rest_url", None)  # legacy alias
        if rest_url:
            base_url = rest_url

        # Initialize logger first (needed by _resolve_credentials)
        self.logger = logging.getLogger(__name__)

        self.config = config or {}
        self.shadow_mode = shadow_mode
        self.fsm = fsm
        self.fsm_core = kwargs.get('fsm_core', fsm)

        # Resolve API credentials from multiple sources
        self.api_key, self.api_secret, self.base_url = self._resolve_credentials(
            api_key, api_secret, base_url
        )

        self._timeout = timeout

        # Time sync state (threading.Lock works in any context, no event loop binding)
        self._time_offset_ms = 0
        self._last_time_sync_monotonic = 0.0
        self._time_sync_lock = threading.Lock()  # NOT asyncio.Lock!

        # recvWindow (ms). Для ф'ючерсів максимум 60000.
        # Встановлено на максимум для уникнення -1021 на testnet
        self._recv_window_ms = self._get_config_value(
            "recv_window_ms", 60000, int)

        # httpx session - lazy initialization to avoid event loop binding issues
        # Session will be created on first use in the current event loop
        # External session for testing
        self._session: Optional[httpx.AsyncClient] = session
        # Track which loop created the session
        self._session_loop_id: Optional[int] = None

        # ClientOrderId ledger for -4116 idempotency
        self._clientorderid_ledger: Dict[str, Tuple[int, str, str]] = {}

        # Mark price cache
        self._mark_price_cache: Dict[str, Dict[str, Any]] = {}

        # Exchange info cache for precision normalization (PRICE_FILTER, LOT_SIZE)
        # Key: symbol, Value: {"tick_size": Decimal, "step_size": Decimal, "timestamp": float}
        self._exchange_info_cache: Dict[str, Dict[str, Any]] = {}
        self._exchange_info_cache_ttl_sec = 300  # 5 minutes TTL

        # Pre-populate cache from local file (avoids network calls on testnet)
        self._preload_exchange_info_cache()

        # WebSocket state
        self.ws_listen_key: Optional[str] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.ws_running = False
        self.ws_reconnect_delay = 1.0
        self.ws_max_reconnect_delay = 60.0
        self.listen_key_last_refresh = 0.0

        # Status cache
        self._last_status_check = 0.0
        self._status_cache = "unknown"

        # Metrics for tracking
        self.metrics = {
            "cancel_idempotent_ok": 0,
            "cancel_-2011_absorbed": 0,
        }

        # Slippage cap for MARKET orders (optional)
        self.slippage_cap_bps: Optional[int] = self._get_slippage_cap()

        self.logger.info(
            f"[BinanceAdapter] Initialized: shadow_mode={shadow_mode}, "
            f"ws_enabled={fsm is not None}, base_url={self.base_url}"
        )

    @property
    def session(self) -> httpx.AsyncClient:
        """
        Lazy-initialized httpx session that handles event loop changes.

        This prevents "is bound to a different event loop" errors when:
        - Adapter is created before main event loop starts
        - WebSocket callbacks run in different context
        """
        try:
            current_loop = asyncio.get_running_loop()
            current_loop_id = id(current_loop)
        except RuntimeError:
            # No running loop - return existing session or create new one
            current_loop_id = None

        # Check if we need to create/recreate session
        # If _session_loop_id is None, it's an externally injected session (for testing) - keep it!
        need_new_session = (
            self._session is None or
            (self._session_loop_id is not None and
             current_loop_id is not None and
             self._session_loop_id != current_loop_id)
        )

        if need_new_session:
            # Close old session if exists and was created by us (not injected for testing)
            if self._session is not None and self._session_loop_id is not None:
                self.logger.debug(
                    f"[BinanceAdapter] Recreating session: loop changed "
                    f"(old={self._session_loop_id}, new={current_loop_id})"
                )
                # Schedule close in background - don't await here
                try:
                    asyncio.create_task(self._session.aclose())
                except Exception:
                    pass  # Best effort cleanup

            self._session = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self._timeout,
                headers={"X-MBX-APIKEY": self.api_key},
            )
            self._session_loop_id = current_loop_id
            self.logger.debug(
                f"[BinanceAdapter] Created new session for loop {current_loop_id}")

        return self._session

    @session.setter
    def session(self, value: httpx.AsyncClient) -> None:
        """Allow setting session for testing purposes."""
        self._session = value
        self._session_loop_id = None  # External session - don't track loop

    def _resolve_credentials(
        self, api_key: str, api_secret: str, base_url: str
    ) -> Tuple[str, bytes, str]:
        """Resolve API credentials from multiple sources: args, config, env."""
        # Determine testnet/mainnet
        trading_env = self._get_config_value("trading_env", None, str)
        use_testnet = (
            trading_env == "test" or
            os.environ.get("USE_TESTNET", "1") == "1" or
            os.environ.get("USE_TESTNET", "").lower() == "true"
        )

        # Get credentials
        if not api_key:
            api_key = self._get_config_value("binance_ro_api_key", "", str)
        if not api_key:
            env_key = "BINANCE_TESTNET_API_KEY" if use_testnet else "BINANCE_MAINNET_API_KEY"
            api_key = os.environ.get(env_key, "")

        if not api_secret:
            api_secret = self._get_config_value(
                "binance_ro_api_secret", "", str)
        if not api_secret:
            env_key = "BINANCE_TESTNET_API_SECRET" if use_testnet else "BINANCE_MAINNET_API_SECRET"
            api_secret = os.environ.get(env_key, "")

        # Validate credentials if not shadow mode
        if not self.shadow_mode and (not api_key or not api_secret):
            self.logger.warning(
                "[BinanceAdapter] API credentials not found, enabling shadow mode"
            )
            self.shadow_mode = True

        # Encode secret
        api_secret_bytes = api_secret.encode() if isinstance(
            api_secret, str) else api_secret

        return api_key, api_secret_bytes, base_url.rstrip("/")

    def _get_config_value(self, key: str, default: Any, value_type: type) -> Any:
        """Get configuration value from dict or Pydantic config."""
        try:
            if hasattr(self.config, key):
                val = getattr(self.config, key)
            elif isinstance(self.config, dict):
                val = self.config.get(key, default)
            else:
                val = default
            return value_type(val) if val is not None else default
        except (AttributeError, TypeError, ValueError):
            return default

    def _get_slippage_cap(self) -> Optional[int]:
        """Get slippage cap from config."""
        try:
            if isinstance(self.config, dict):
                val = self.config.get("trading", {}).get(
                    "orders", {}).get("market", {}).get("slippage_cap_bps")
            elif hasattr(self.config, 'trading'):
                val = getattr(getattr(getattr(
                    self.config.trading, 'orders', None), 'market', None), 'slippage_cap_bps', None)
            else:
                val = None
            return int(val) if val is not None else None
        except (AttributeError, TypeError, ValueError):
            return None

    # опційно: контекст-менеджер для акуратного закриття
    async def __aenter__(self) -> "BinanceAdapter":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        try:
            if self._session is not None:
                await self._session.aclose()
                self._session = None
                self._session_loop_id = None
        except Exception:
            pass

    async def start(self) -> None:
        """
        Start the adapter.

        Performs initial time synchronization with Binance server
        to avoid -1021 errors on first requests.
        Then starts WebSocket USER_DATA_STREAM for real-time order updates.
        """
        await self._sync_time(force=True)
        LOG.info(
            f"BinanceAdapter started, time_offset={self._time_offset_ms}ms")

        # Start WebSocket for USER_DATA_STREAM (order fills, position updates)
        await self.start_websocket()
        LOG.info("BinanceAdapter WebSocket USER_DATA_STREAM started")

    async def stop(self) -> None:
        """
        Stop the adapter (no-op for REST-only adapter).

        This method exists for compatibility with FSM cleanup
        that expects polling adapters. Since this adapter is REST-only,
        no background polling needs to be stopped.
        """
        LOG.info("BinanceAdapter stopped (REST-only mode, no polling)")

    # PHASE B1: ClientOrderId Ledger Methods
    def register_clientorderid(self, client_order_id: str, order_id: str, symbol: str) -> None:
        """
        Register a successful order in ClientOrderId ledger.

        Args:
            client_order_id: The client order ID (from place_order response)
            order_id: The Binance order ID
            symbol: Trading symbol
        """
        timestamp_ms = int(time.time() * 1000)
        self._clientorderid_ledger[client_order_id] = (
            timestamp_ms, order_id, symbol)
        LOG.debug(
            f"✅ [B1] Registered ClientOrderId {client_order_id} → {order_id} ({symbol})")

    def check_clientorderid_reuse(self, symbol: str, client_order_id: str) -> Optional[str]:
        """
        Check if ClientOrderId can be reused (was successful within 24h).

        Args:
            symbol: Trading symbol
            client_order_id: The client order ID to check

        Returns:
            Original Binance order_id if reusable, None if should generate new ID
        """
        if client_order_id not in self._clientorderid_ledger:
            return None

        timestamp_ms, order_id, ledger_symbol = self._clientorderid_ledger[client_order_id]

        # Check: same symbol and within 24 hours
        age_ms = int(time.time() * 1000) - timestamp_ms
        if ledger_symbol == symbol and age_ms < 24 * 3600 * 1000:
            LOG.info(
                f"🔄 [B1] REUSING ClientOrderId {client_order_id} → {order_id} ({symbol}) - age {age_ms/1000:.0f}s")
            return order_id

        # Stale entry: remove from ledger
        if age_ms >= 24 * 3600 * 1000:
            del self._clientorderid_ledger[client_order_id]
            LOG.debug(
                f"🗑️ [B1] Cleaned stale ClientOrderId {client_order_id} (age {age_ms/3600000:.1f}h)")

        return None

    def _norm_params(self, d: dict) -> dict:
        """Фільтрує None і нормалізує значення до рядків, сумісних з Binance."""
        out = {}
        for k, v in d.items():
            if v is None:
                continue
            if isinstance(v, bool):
                out[k] = "true" if v else "false"
            elif isinstance(v, Decimal):
                s = format(v, "f")
                out[k] = s.rstrip("0").rstrip(".") if "." in s else s
            else:
                out[k] = str(v)
        return out

    async def _server_time(self) -> int:
        # Для USDM futures: /fapi/v1/time
        r = await self.session.get(f"{self.base_url}/fapi/v1/time")
        r.raise_for_status()
        data = await _coerce_json(r)
        # serverTime у мілісекундах
        return int(data["serverTime"])

    async def _sync_time(self, force: bool = False):
        # TTL 10 sec - aggressive sync to avoid -1021 errors on testnet
        try:
            if hasattr(self.config, 'time_sync_ttl_sec'):
                ttl_sec = int(self.config.time_sync_ttl_sec)
            elif isinstance(self.config, dict):
                ttl_sec = int(self.config.get("time_sync_ttl_sec", 10))
            else:
                ttl_sec = 10
        except (AttributeError, TypeError, ValueError):
            ttl_sec = 10

        now_mono = time.monotonic()
        if not force and (now_mono - self._last_time_sync_monotonic) < ttl_sec:
            return
        # Use threading.Lock - works in any context, no event loop binding issues
        with self._time_sync_lock:
            # Могли вже інші синхронізувати
            if not force and (time.monotonic() - self._last_time_sync_monotonic) < ttl_sec:
                return
            # RTT-aware time sync: measure round-trip to account for network latency
            local_before = int(time.time() * 1000)
            server_ms = await self._server_time()
            local_after = int(time.time() * 1000)
            rtt_ms = local_after - local_before
            # Use midpoint for more accurate offset calculation
            local_mid = (local_before + local_after) // 2
            self._time_offset_ms = server_ms - local_mid
            self._last_time_sync_monotonic = time.monotonic()
            LOG.debug(
                f"Time sync: offset={self._time_offset_ms}ms, rtt={rtt_ms}ms, force={force}")

    def _sign_build(self, base_params: dict) -> tuple[str, dict]:
        """
        Приймає 'базові' params (без timestamp/recvWindow/signature),
        повертає (encoded_qs_with_signature, final_params_dict).
        """
        base = self._norm_params(base_params)
        ts = int(time.time() * 1000) + int(self._time_offset_ms)
        base["timestamp"] = str(ts)
        base.setdefault("recvWindow", str(self._recv_window_ms))
        # Строга URL-енкодація й підпис рівно того рядка, що підемо відправляти
        qs = urlencode(base, doseq=True, quote_via=quote_plus)
        sig = hmac.new(self.api_secret, qs.encode(),
                       hashlib.sha256).hexdigest()
        final_qs = f"{qs}&signature={sig}"
        final_params = dict(base)
        final_params["signature"] = sig
        return final_qs, final_params

    async def _request(
        self, method: str, path: str, params: dict | None = None, signed: bool = True
    ):
        url = f"{self.base_url}{path}"
        params = params or {}

        # Готуємо одразу "базові" params (без підпису) для можливого ретраю
        base_params = dict(params)

        async def _do(method: str, base_params: dict):
            if signed:
                await self._sync_time(False)
                qs, final_params = self._sign_build(base_params)
                # ВИКОРИСТОВУЄМО self.session — щоб тести могли мокати її
                r = await self.session.request(method.upper(), url, params=final_params)
                if r.status_code >= 400:
                    err = _safe_read_err(r)  # FIX: now sync
                    raise _make_binance_error(r, err)
                return await _coerce_json(r)
            else:
                r = await self.session.request(
                    method.upper(), url, params=self._norm_params(base_params)
                )
                r.raise_for_status()
                return await _coerce_json(r)        # 1-й запит
        try:
            return await _do(method, base_params)
        except Exception as e:
            # Якщо ReadTimeout або ConnectTimeout або NetworkError → спробуємо ретрай (1 раз)
            import httpx
            import httpcore
            retry_exceptions = (
                httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException,
                httpx.ReadError, httpx.NetworkError,
                httpcore.ReadTimeout, httpcore.ConnectTimeout, httpcore.TimeoutException,
                httpcore.ReadError, httpcore.NetworkError
            )
            if isinstance(e, retry_exceptions):
                LOG.warning(
                    f"Network/Timeout error ({type(e).__name__}) on {method} {path}, retrying once...")
                import asyncio
                await asyncio.sleep(0.5)  # Невелика затримка перед ретраєм
                return await _do(method, base_params)
            # Якщо -1021 → жорстка синхронізація і другий запит з НОВОГО base_params
            msg = str(e)
            if "code': -1021" in msg or "-1021" in msg:
                LOG.warning(
                    f"Time sync error -1021 on {method} {path}, forcing resync...")
                await self._sync_time(True)
                LOG.info(
                    f"Time resync done, new offset={self._time_offset_ms}ms, retrying...")
                return await _do(method, base_params)
            # Якщо -1022 → також спробуємо 1 ретрай з чистої бази (частий кейс "перепідписали")
            if (
                "code': -1022" in msg
                or "-1022" in msg
                or "Signature for this request is not valid" in msg
            ):
                await self._sync_time(True)
                return await _do(method, base_params)
            raise

    # --- Public API Methods (via AbstractExchangeAdapter interface) ---

    async def create_order(self, params: ExchangeOrderParams) -> ExchangeOrderResponse:
        """
        Create an order on Binance.
        Implements AbstractExchangeAdapter.create_order()

        Note: When close_position=True, quantity must NOT be sent to Binance.
        Binance closePosition=true automatically closes the entire position.

        PRECISION NORMALIZATION (EXEC-BINANCE-PRECISION-GUARD):
        - price is normalized to tickSize
        - stopPrice is normalized to tickSize
        - quantity is normalized to stepSize
        """
        LOG.info(
            f"[create_order] ENTRY symbol={params.symbol} type={params.order_type} stop_price={params.stop_price}")
        path = "/fapi/v1/order"
        symbol = params.symbol

        # ═══════════════════════════════════════════════════════════════════════
        # PRECISION NORMALIZATION - EXEC-BINANCE-PRECISION-GUARD-FOR-CONDITIONALS
        # Normalize ALL price/quantity fields BEFORE building order_params
        # ═══════════════════════════════════════════════════════════════════════

        # Get symbol filters for normalization
        filters = await self._get_symbol_filters(symbol)

        # Normalize price (for LIMIT orders)
        normalized_price = None
        if params.price:
            normalized_price = await self._normalize_price(symbol, params.price)
            LOG.info(
                f"[create_order] PRECISION_NORM price: {params.price} -> {normalized_price} (tick={filters.get('tick_size')})")

        # Normalize stopPrice (for STOP_MARKET, TAKE_PROFIT_MARKET)
        normalized_stop_price = None
        if params.stop_price:
            normalized_stop_price = await self._normalize_price(symbol, params.stop_price)
            LOG.info(
                f"[create_order] PRECISION_NORM stopPrice: {params.stop_price} -> {normalized_stop_price} (tick={filters.get('tick_size')})")

        # Normalize quantity (if not using closePosition)
        normalized_quantity = None
        if params.quantity and not params.close_position:
            normalized_quantity = await self._normalize_quantity(symbol, params.quantity)
            LOG.debug(
                f"[create_order] Normalized quantity: {params.quantity} -> {normalized_quantity}")

        # Build order params with normalized values
        order_params = {
            "symbol": symbol,
            "side": params.side.upper(),
            "type": params.order_type.upper(),
        }

        # CRITICAL: closePosition and quantity are mutually exclusive!
        # When closePosition=true, Binance ignores quantity and closes entire position.
        # Sending both causes API error.
        if params.close_position:
            order_params["closePosition"] = "true"
            # Do NOT add quantity when using closePosition
        elif normalized_quantity:
            order_params["quantity"] = normalized_quantity

        if normalized_price:
            order_params["price"] = normalized_price
        if params.time_in_force:
            order_params["timeInForce"] = params.time_in_force
        if params.reduce_only and not params.close_position:
            # reduceOnly and closePosition are also mutually exclusive
            order_params["reduceOnly"] = "true"
        if params.client_order_id:
            order_params["newClientOrderId"] = params.client_order_id
        if params.position_side:
            order_params["positionSide"] = params.position_side
        if normalized_stop_price:
            order_params["stopPrice"] = normalized_stop_price
        if params.working_type:
            order_params["workingType"] = params.working_type

        # ═══════════════════════════════════════════════════════════════════════
        # PRECISION GUARD - Fail-closed validation BEFORE sending to Binance
        # ═══════════════════════════════════════════════════════════════════════
        try:
            self._validate_precision(symbol, order_params, filters)
        except BinanceValidationError as e:
            LOG.error(
                f"[create_order] PRECISION_GUARD_BLOCKED: {symbol} - {e}")
            raise

        try:
            result = await self._request("POST", path, order_params)
        except BinanceAPIError as e:
            # DIAG: Log exception details for debugging
            LOG.warning(
                f"[create_order] BinanceAPIError caught: code={e.code} (type={type(e.code).__name__}) "
                f"msg={e.msg} client_order_id={params.client_order_id}"
            )
            # Handle -4116 (Duplicate ClientOrderId)
            if e.code == -4116 and params.client_order_id:
                LOG.warning(
                    f"[create_order] Got -4116 Duplicate ClientOrderId {params.client_order_id}. Checking status..."
                )
                try:
                    # 1. Check if the order actually exists and is active
                    check_params = {
                        "symbol": params.symbol,
                        "origClientOrderId": params.client_order_id
                    }
                    existing_order = await self._request("GET", "/fapi/v1/order", check_params)
                    status = existing_order.get("status")

                    if status in ("NEW", "PARTIALLY_FILLED"):
                        LOG.info(
                            f"[create_order] Found active duplicate order {params.client_order_id} ({status}). Returning it."
                        )
                        result = existing_order  # Treat as success
                    else:
                        LOG.info(
                            f"[create_order] Duplicate order {params.client_order_id} is {status}. Retrying with new ID..."
                        )
                        # 2. If not active (e.g. CANCELED/FILLED), we must place a NEW order with a new ID
                        new_id = params.client_order_id
                        for i in range(1, 4):  # Try 3 times
                            if "_R" in new_id:
                                # Increment existing suffix
                                try:
                                    base, suffix = new_id.rsplit("_R", 1)
                                    ver = int(suffix) + 1
                                    new_id = f"{base}_R{ver}"
                                except ValueError:
                                    new_id = f"{new_id}_R{i}"
                            else:
                                # Append first suffix
                                new_id = f"{new_id}_R{i}"

                            LOG.info(
                                f"[create_order] Retrying with new ClientOrderId: {new_id}")
                            order_params["newClientOrderId"] = new_id
                            try:
                                result = await self._request("POST", path, order_params)
                                LOG.info(
                                    f"[create_order] Recovery successful with {new_id}")
                                break
                            except BinanceAPIError as retry_err:
                                if retry_err.code == -4116:
                                    LOG.warning(
                                        f"[create_order] New ID {new_id} also duplicated. Retrying..."
                                    )
                                    continue
                                raise retry_err
                        else:
                            # All retries failed
                            LOG.error(
                                f"[create_order] All recovery attempts failed for {params.client_order_id}"
                            )
                            raise e
                except Exception as check_err:
                    LOG.error(
                        f"[create_order] Failed to check/recover duplicate: {check_err}")
                    raise e
            else:
                raise e

        return ExchangeOrderResponse(
            order_id=str(result.get("orderId", "")),
            client_order_id=result.get("clientOrderId"),
            symbol=result.get("symbol", ""),
            side=result.get("side", ""),
            quantity=str(result.get("origQty", "")),
            filled_qty=str(result.get("executedQty", "")),
            price=result.get("price"),
            status=result.get("status", ""),
            timestamp_ms=int(result.get("time", 0) or 0),
        )

    async def cancel_order(
        self, symbol: str, order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> ExchangeOrderResponse:
        """
        Cancel an order on Binance.
        Implements AbstractExchangeAdapter.cancel_order()
        """
        if not order_id and not client_order_id:
            raise ValueError(
                "Either order_id or client_order_id must be provided")

        # Ensure symbol is not empty (fallback if needed)
        if not symbol or symbol.strip() == "":
            LOG.warning(
                f"[cancel_order] Empty symbol, attempting to scan open orders")
            # Fallback: scan open orders to find symbol by order_id/client_order_id
            symbol = await self._find_symbol_by_order_id(order_id, client_order_id)
            if not symbol:
                raise BinanceAPIError(
                    code=-2011,
                    msg="Cannot determine symbol: order not found in open orders",
                    nrr_code="NRR-CANCEL-001"
                )
            LOG.info(f"[cancel_order] Resolved symbol from scan: {symbol}")

        params = {"symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        elif client_order_id:
            params["origClientOrderId"] = client_order_id

        try:
            path = "/fapi/v1/order"
            result = await self._request("DELETE", path, params, signed=True)
            LOG.info(
                f"[cancel_order] Successfully cancelled {symbol} order {order_id or client_order_id}: {result.get('status', '?')}")

            return ExchangeOrderResponse(
                order_id=str(result.get("orderId", "")),
                client_order_id=result.get("clientOrderId"),
                symbol=result.get("symbol", ""),
                side=result.get("side", ""),
                quantity=str(result.get("origQty", "")),
                filled_qty=str(result.get("executedQty", "")),
                price=result.get("price"),
                status=result.get("status", ""),
                timestamp_ms=int(result.get("time", 0) or 0),
            )

        except BinanceAPIError as e:
            # Handle -2011 (Unknown order) with retry after symbol verification
            if e.code == -2011:
                LOG.warning(
                    f"[cancel_order] Got -2011 Unknown order for {symbol} {order_id or client_order_id}, retrying with verified symbol")

                # Verify symbol by scanning open orders
                verified_symbol = await self._find_symbol_by_order_id(order_id, client_order_id)
                if verified_symbol and verified_symbol != symbol:
                    LOG.info(
                        f"[cancel_order] Symbol mismatch: provided={symbol}, scanned={verified_symbol}, retrying...")
                    params["symbol"] = verified_symbol
                    try:
                        result = await self._request("DELETE", path, params, signed=True)
                        LOG.info(
                            f"[cancel_order] Retry succeeded with symbol {verified_symbol}")

                        return ExchangeOrderResponse(
                            order_id=str(result.get("orderId", "")),
                            client_order_id=result.get("clientOrderId"),
                            symbol=result.get("symbol", ""),
                            side=result.get("side", ""),
                            quantity=str(result.get("origQty", "")),
                            filled_qty=str(result.get("executedQty", "")),
                            price=result.get("price"),
                            status=result.get("status", ""),
                            timestamp_ms=int(result.get("time", 0) or 0),
                        )
                    except BinanceAPIError as retry_err:
                        # Log and re-raise if retry fails
                        LOG.error(f"[cancel_order] Retry failed: {retry_err}")
                        raise
                else:
                    # Order truly doesn't exist or not found in scans
                    LOG.warning(
                        f"[cancel_order] Order {order_id or client_order_id} not found in open orders (may already be executed/cancelled)")
                    # Return simulated cancelled response to prevent cascade failures
                    return ExchangeOrderResponse(
                        order_id=order_id or "unknown",
                        client_order_id=client_order_id or "unknown",
                        symbol=symbol,
                        side="",
                        quantity="0",
                        filled_qty="0",
                        price=None,
                        status="CANCELED",
                        timestamp_ms=int(time.time() * 1000),
                        reason="order_not_found_in_scan"
                    )
            else:
                # Other errors: re-raise
                raise

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[ExchangeOrderResponse]:
        """
        Get open orders.
        Implements AbstractExchangeAdapter.get_open_orders()

        EP-STAB-ADAPT-ORD-META: Full metadata extraction for bracket detection.
        Returns all fields needed to identify SL/TP brackets:
        - order_type: STOP_MARKET, TAKE_PROFIT_MARKET, etc.
        - reduce_only: True for exit orders
        - stop_price: Trigger price for conditional orders
        """
        path = "/fapi/v1/openOrders"
        params = {}
        if symbol:
            params["symbol"] = symbol

        result = await self._request("GET", path, params)

        LOG.info(
            "[get_open_orders] RAW_RESPONSE symbol=%s count=%d",
            symbol or "*", len(result) if isinstance(result, list) else 0
        )

        orders = []
        for order in result:
            order_type = order.get("type") or order.get("origType")
            stop_price = order.get("stopPrice")
            reduce_only = order.get("reduceOnly", False)

            LOG.debug(
                "[get_open_orders] PARSING orderId=%s symbol=%s type=%s stopPrice=%s reduceOnly=%s",
                order.get("orderId"), order.get(
                    "symbol"), order_type, stop_price, reduce_only
            )

            orders.append(ExchangeOrderResponse(
                order_id=str(order.get("orderId", "")),
                client_order_id=order.get("clientOrderId"),
                symbol=order.get("symbol", ""),
                side=order.get("side", ""),
                quantity=str(order.get("origQty", "")),
                filled_qty=str(order.get("executedQty", "")),
                price=order.get("price"),
                status=order.get("status", ""),
                timestamp_ms=int(order.get("time", 0) or 0),
                # EP-STAB-ADAPT-ORD-META: Essential fields for bracket detection
                order_type=order_type,
                reduce_only=reduce_only,
                close_position=order.get("closePosition", False),
                stop_price=stop_price,
                working_type=order.get("workingType"),
                position_side=order.get("positionSide"),
            ))

        LOG.info(
            "[get_open_orders] PARSED symbol=%s orders=%d types=%s",
            symbol or "*", len(orders),
            [o.order_type for o in orders]
        )

        return orders

    async def get_open_positions(self, symbol: Optional[str] = None) -> List[ExchangePosition]:
        """
        USDT-M Futures: повертає тільки відкриті (non-zero) позиції.
        Працює і в ONE_WAY (positionSide='BOTH'), і в HEDGE (LONG/SHORT).
        Implements AbstractExchangeAdapter.get_open_positions()

        PHASE P0: Added retry/backoff for empty API responses to handle network/API failures.
        """
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol

        # PHASE P0: Get fallback retry configuration
        fallback_backoff_ms = self._get_fallback_backoff_ms()

        # PHASE P0: Retry logic for empty responses
        max_retries = len(fallback_backoff_ms)
        last_exception = None

        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                # signed GET /fapi/v2/positionRisk
                raw = await self._request("GET", "/fapi/v2/positionRisk", params)

                # 🔴 DIAGNOSTIC: Log raw API response
                self.logger.debug(
                    f"🌐 BinanceAdapter.get_open_positions() attempt={attempt+1}/{max_retries+1} raw response type: {type(raw)}, len: {len(raw) if isinstance(raw, list) else 'N/A'}")
                if not isinstance(raw, list) or len(raw) == 0:
                    if attempt < max_retries:
                        self.logger.warning(
                            f"⚠️ API /fapi/v2/positionRisk returned empty/non-list on attempt {attempt+1}, retrying in {fallback_backoff_ms[attempt]}ms: {raw}")
                        await asyncio.sleep(fallback_backoff_ms[attempt] / 1000.0)
                        continue
                    else:
                        self.logger.error(
                            f"❌ API /fapi/v2/positionRisk still empty after {max_retries+1} attempts, returning empty positions")
                else:
                    if attempt > 0:
                        self.logger.info(
                            f"✅ API /fapi/v2/positionRisk recovered after {attempt+1} attempts, returned {len(raw)} total records")
                    else:
                        self.logger.info(
                            f"✅ API /fapi/v2/positionRisk returned {len(raw)} total records")

                positions: List[ExchangePosition] = []
                for p in raw:
                    # Binance віддає числа як строки — зберігаємо precision, конвертуємо тільки коли потрібно
                    amt_str = p.get("positionAmt", "0")
                    amt = float(amt_str)
                    symbol = p.get('symbol', 'UNKNOWN')

                    # 🔴 DIAGNOSTIC: Log ALL positions from API
                    if abs(amt) > 0.0001:
                        self.logger.info(
                            f"  ✅ API Position: {symbol} {p.get('positionSide', 'BOTH')} {amt} @ entry={p.get('entryPrice', 'N/A')}, mark={p.get('markPrice', 'N/A')}, unPnL={p.get('unRealizedProfit', 'N/A')}")

                    if abs(amt) <= 0.0:
                        # 🔴 DIAGNOSTIC: Log filtered positions
                        self.logger.debug(
                            f"  ❌ Skipping zero position for {symbol}: positionAmt={amt_str}")
                        continue  # пропускаємо нульові

                    entry_str = p.get("entryPrice", "0") or "0"
                    entry = float(entry_str)
                    mark_str = p.get("markPrice", "0") or "0"
                    mark = float(mark_str)
                    upnl_str = p.get("unRealizedProfit", "0") or "0"
                    upnl = float(upnl_str)
                    lev = int(float(p.get("leverage", "0") or 0))

                    # Hedge: 'LONG'/'SHORT'; One-way: 'BOTH'
                    pos_side = p.get("positionSide", "BOTH") or "BOTH"
                    side = "LONG" if (amt > 0 and pos_side in (
                        "BOTH", "LONG")) else "SHORT"

                    pos_obj = ExchangePosition(
                        symbol=p.get("symbol", ""),
                        position_side=pos_side,  # BOTH/LONG/SHORT
                        side=side,  # LONG/SHORT (зручно для бізнес-логіки)
                        position_amount=amt_str,  # зберігаємо string для precision
                        entry_price=entry_str,  # зберігаємо string для precision
                        mark_price=mark_str,  # зберігаємо string для precision
                        unrealized_profit=upnl_str,  # зберігаємо string для precision
                        leverage=lev,
                        margin_type=p.get("marginType", "cross").upper(),
                        isolated_margin=float(
                            p.get("isolatedMargin", "0") or 0),
                        update_time_ms=int(p.get("updateTime", 0) or 0),
                    )
                    positions.append(pos_obj)
                    # 🔴 DIAGNOSTIC: Log accepted position with leverage
                    self.logger.info(
                        f"  ✅ API Position: {pos_obj.symbol} {side} {amt_str} @ entry={entry_str}, mark={mark_str}, unPnL={upnl_str}, leverage={lev}x")

                # 🔴 DIAGNOSTIC: Final summary
                self.logger.info(
                    f"🎯 get_open_positions() returning {len(positions)} non-zero positions")

                # PHASE P0: If we got empty positions after successful API call, enter fallback mode
                if not positions and isinstance(raw, list) and len(raw) == 0:
                    # Log warning about empty position response
                    self.logger.warning(
                        "FALLBACK_TRIGGER: Empty positions response detected - this may trigger fallback mode in ExposureGuard"
                    )

                return positions

            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    self.logger.warning(
                        f"⚠️ get_open_positions() attempt {attempt+1} failed: {e}, retrying in {fallback_backoff_ms[attempt]}ms")
                    await asyncio.sleep(fallback_backoff_ms[attempt] / 1000.0)
                else:
                    self.logger.error(
                        f"❌ get_open_positions() failed after {max_retries+1} attempts: {e}")
                    raise last_exception

        # This should never be reached, but just in case
        raise last_exception

    async def get_mark_price(self, symbol: str, ttl_ms: int = 250) -> float:
        """
        Get the mark price for a symbol with TTL cache.
        Implements AbstractExchangeAdapter.get_mark_price()
        """
        now = time.time() * 1000
        if symbol in self._mark_price_cache:
            cached = self._mark_price_cache[symbol]
            if now - cached["timestamp"] < ttl_ms:
                return cached["price"]

        try:
            path = "/fapi/v1/premiumIndex"
            params = {"symbol": symbol}
            response = await self._request("GET", path, params)
            price = float(response["markPrice"])
        except Exception:
            # Fallback to last price
            LOG.warning(
                f"Failed to get mark price for {symbol}, using last price fallback")
            price = await self.get_last_price(symbol)

        self._mark_price_cache[symbol] = {"price": price, "timestamp": now}
        return price

    async def get_last_price(self, symbol: str) -> float:
        """
        Get the last price for a symbol (fallback for mark price).
        Implements AbstractExchangeAdapter.get_last_price()
        """
        path = "/fapi/v1/ticker/price"
        params = {"symbol": symbol}
        response = await self._request("GET", path, params)
        return float(response["price"])

    async def get_account_balance(self) -> List[Dict[str, Any]]:
        """
        Get account balance information.
        Implements AbstractExchangeAdapter.get_account_balance()
        """
        path = "/fapi/v2/balance"
        return await self._request("GET", path)

    async def get_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """
        Get order information by order ID.

        Args:
            symbol: Trading symbol.
            order_id: Order ID.

        Returns:
            Order information.
        """
        path = "/fapi/v1/order"
        params = {"symbol": symbol, "orderId": order_id}
        return await self._request("GET", path, params)

    async def get_exchange_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get exchange information for a symbol.
        Implements AbstractExchangeAdapter.get_exchange_info()
        """
        path = "/fapi/v1/exchangeInfo"
        params = {"symbol": symbol}
        return await self._request("GET", path, params)

    # ========== PRECISION NORMALIZATION (EXEC-BINANCE-PRECISION-GUARD) ==========

    async def _get_symbol_filters(self, symbol: str) -> Dict[str, Any]:
        """
        Get cached symbol filters (tick_size, step_size) from exchange info.

        Returns:
            Dict with tick_size, step_size, min_qty, min_notional as Decimal.
            Returns default values if symbol not found.
        """
        now = time.time()
        cached = self._exchange_info_cache.get(symbol)

        # Check cache validity
        if cached and (now - cached.get("timestamp", 0)) < self._exchange_info_cache_ttl_sec:
            return cached

        # Fetch fresh exchange info
        try:
            info = await self.get_exchange_info(symbol)
            symbols = info.get("symbols") or []
            sym = None
            for s in symbols:
                if s.get("symbol") == symbol:
                    sym = s
                    break

            if not sym:
                LOG.warning(
                    f"[BinanceAdapter] Exchange info for {symbol} not found, using defaults")
                return self._get_default_filters(symbol)

            filters = {f.get("filterType"): f for f in sym.get("filters", [])}

            # Extract PRICE_FILTER
            price_filter = filters.get("PRICE_FILTER", {})
            tick_size = Decimal(str(price_filter.get("tickSize", "0.01")))

            # Extract LOT_SIZE
            lot_filter = filters.get("LOT_SIZE", {})
            step_size = Decimal(str(lot_filter.get("stepSize", "0.001")))
            min_qty = Decimal(str(lot_filter.get("minQty", "0.001")))

            # Extract MIN_NOTIONAL
            min_notional = None
            for f in sym.get("filters", []):
                if f.get("filterType", "").upper() == "MIN_NOTIONAL":
                    min_notional = Decimal(
                        str(f.get("notional") or f.get("minNotional") or "5"))
                    break

            result = {
                "tick_size": tick_size,
                "step_size": step_size,
                "min_qty": min_qty,
                "min_notional": min_notional or Decimal("5"),
                "timestamp": now,
            }

            self._exchange_info_cache[symbol] = result
            LOG.debug(
                f"[BinanceAdapter] Cached filters for {symbol}: tick={tick_size}, step={step_size}")
            return result

        except Exception as e:
            LOG.warning(
                f"[BinanceAdapter] Failed to get exchange info for {symbol}: {e}")
            # Prefer stale cache over defaults (preloaded data is still valid)
            if cached:
                LOG.info(f"[BinanceAdapter] Using stale cache for {symbol}")
                return cached
            return self._get_default_filters(symbol)

    def _preload_exchange_info_cache(self) -> None:
        """
        Pre-populate exchange info cache from local file.

        This prevents network calls to /fapi/v1/exchangeInfo on testnet,
        which often timeouts and causes create_order to hang.
        """
        # Try multiple paths
        paths = [
            "configs/testnet_exchangeinfo.json",
            "artifacts/testnet_exchangeinfo.json",
        ]

        data = None
        for path in paths:
            try:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = _json.load(f)
                    self.logger.info(
                        f"[BinanceAdapter] Loaded exchange info from {path}")
                    break
            except Exception as e:
                self.logger.debug(
                    f"[BinanceAdapter] Failed to load {path}: {e}")

        if not data:
            self.logger.warning(
                "[BinanceAdapter] No local exchange info found, will fetch from network")
            return

        symbols = data.get("symbols", [])
        now = time.time()
        loaded_count = 0

        for sym in symbols:
            symbol_name = sym.get("symbol")
            if not symbol_name:
                continue

            filters_map = {f.get("filterType")
                                 : f for f in sym.get("filters", [])}

            # Extract PRICE_FILTER
            price_filter = filters_map.get("PRICE_FILTER", {})
            tick_size = Decimal(str(price_filter.get("tickSize", "0.01")))

            # Extract LOT_SIZE
            lot_filter = filters_map.get("LOT_SIZE", {})
            step_size = Decimal(str(lot_filter.get("stepSize", "0.001")))
            min_qty = Decimal(str(lot_filter.get("minQty", "0.001")))

            # Extract MIN_NOTIONAL
            min_notional = Decimal("5")
            for f in sym.get("filters", []):
                ft = f.get("filterType", "").upper()
                if ft == "MIN_NOTIONAL":
                    min_notional = Decimal(
                        str(f.get("notional") or f.get("minNotional") or "5"))
                    break

            self._exchange_info_cache[symbol_name] = {
                "tick_size": tick_size,
                "step_size": step_size,
                "min_qty": min_qty,
                "min_notional": min_notional,
                "timestamp": now,
            }
            loaded_count += 1

        self.logger.info(
            f"[BinanceAdapter] Pre-loaded filters for {loaded_count} symbols")

    def _get_default_filters(self, symbol: str) -> Dict[str, Any]:
        """Get default filter values when exchange info unavailable."""
        # Conservative defaults - will work for most symbols
        defaults = {
            "tick_size": Decimal("0.01"),
            "step_size": Decimal("0.001"),
            "min_qty": Decimal("0.001"),
            "min_notional": Decimal("5"),
            "timestamp": time.time(),
        }

        # Symbol-specific overrides for known high-value assets
        if symbol.startswith("BTC"):
            defaults["tick_size"] = Decimal("0.1")
        elif symbol.startswith("ETH"):
            defaults["tick_size"] = Decimal("0.01")
        elif symbol.startswith("SOL"):
            defaults["tick_size"] = Decimal("0.01")
            defaults["step_size"] = Decimal("1")

        return defaults

    async def _normalize_price(self, symbol: str, price: Any) -> str:
        """
        Normalize price to symbol's PRICE_FILTER tickSize.

        Args:
            symbol: Trading symbol
            price: Price value (str, Decimal, float, int)

        Returns:
            Normalized price as string with correct precision.
        """
        if price is None:
            return None

        filters = await self._get_symbol_filters(symbol)
        tick_size = filters["tick_size"]

        price_d = self._to_decimal(price)
        normalized = self._round_step(price_d, tick_size, ROUND_DOWN)

        # Format without scientific notation
        result = format(normalized.normalize(), "f")
        return result

    async def _normalize_quantity(self, symbol: str, quantity: Any) -> str:
        """
        Normalize quantity to symbol's LOT_SIZE stepSize.

        Args:
            symbol: Trading symbol
            quantity: Quantity value

        Returns:
            Normalized quantity as string with correct precision.
        """
        if quantity is None:
            return None

        filters = await self._get_symbol_filters(symbol)
        step_size = filters["step_size"]

        qty_d = self._to_decimal(quantity)
        normalized = self._round_step(qty_d, step_size, ROUND_DOWN)

        # Format without scientific notation
        result = format(normalized.normalize(), "f")
        return result

    def _validate_precision(self, symbol: str, params: dict, filters: Dict[str, Any]) -> None:
        """
        Fail-closed precision guard: validates that all prices/quantities
        have correct precision BEFORE sending to Binance.

        Raises:
            BinanceValidationError: If any parameter exceeds allowed precision.
        """
        tick_size = filters.get("tick_size", Decimal("0.01"))
        step_size = filters.get("step_size", Decimal("0.001"))

        def check_precision(value: str, allowed_step: Decimal, field_name: str):
            if value is None:
                return
            try:
                val_d = Decimal(str(value))
                # Check if value is divisible by step
                remainder = val_d % allowed_step
                if remainder != 0:
                    raise BinanceValidationError(
                        f"PRECISION_GUARD: {field_name}={value} exceeds allowed precision "
                        f"(step={allowed_step}, remainder={remainder})"
                    )
            except Exception as e:
                if isinstance(e, BinanceValidationError):
                    raise
                LOG.warning(
                    f"[BinanceAdapter] Precision check failed for {field_name}: {e}")

        # Check price fields
        for field in ("price", "stopPrice", "activationPrice"):
            if field in params:
                check_precision(params[field], tick_size, field)

        # Check quantity
        if "quantity" in params and params["quantity"] is not None:
            check_precision(params["quantity"], step_size, "quantity")

    # ========== END PRECISION NORMALIZATION ==========

    async def quantize_quantity(self, symbol: str, qty: Any) -> str:
        """
        Quantize quantity to symbol's LOT_SIZE stepSize and validate MIN_NOTIONAL.
        Implements AbstractExchangeAdapter.quantize_quantity()
        """
        info = await self.get_exchange_info(symbol)
        # exchangeInfo has 'symbols' list
        symbols = info.get("symbols") or []
        sym = None
        for s in symbols:
            if s.get("symbol") == symbol:
                sym = s
                break
        if not sym:
            raise ValueError(f"Exchange info for {symbol} not found")

        filters = {f.get("filterType"): f for f in sym.get("filters", [])}
        lot = filters.get("LOT_SIZE") or filters.get("MINQ") or {}
        step_size = Decimal(str(lot.get("stepSize") or lot.get("step") or "1"))
        if step_size <= 0:
            raise ValueError("Invalid step size from exchange info")

        qty_d = self._to_decimal(qty)
        q = self._round_step(qty_d, step_size, ROUND_DOWN)
        if q <= 0:
            raise ValueError("Quantity rounds to zero with stepSize")

        # check minQty if available
        min_qty = lot.get("minQty")
        if min_qty:
            min_qty_d = Decimal(str(min_qty))
            if q < min_qty_d:
                q = min_qty_d

        # check min notional if available
        # try common key names
        min_notional = None
        for key in ("MIN_NOTIONAL", "MIN_NOTIONAL", "MIN_NOTIONAL"):
            if key in filters:
                fn = filters[key]
                min_notional = fn.get("notional") or fn.get(
                    "minNotional") or fn.get("minNotional")
                break
        # fallback: try 'MIN_NOTIONAL' variations inside filters
        if min_notional is None:
            for f in sym.get("filters", []):
                if f.get("filterType", "").upper() == "MIN_NOTIONAL":
                    min_notional = f.get("notional") or f.get("minNotional")
                    break

        if min_notional:
            mark = await self.get_mark_price(symbol)
            mark_d = self._to_decimal(mark)
            current_notional = q * mark_d
            min_notional_d = Decimal(str(min_notional))
            if current_notional < min_notional_d:
                # increase qty to meet min notional
                q = (min_notional_d / mark_d).quantize(step_size, rounding=ROUND_UP)
                if q <= 0:
                    raise ValueError("Cannot meet MIN_NOTIONAL with stepSize")

        # format without scientific notation
        q_str = format(q.normalize(), "f")
        return q_str

    # --- Additional convenience methods (for backward compatibility) ---

    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> list:
        """
        Get Kline/candlestick data.

        Args:
            symbol: The trading symbol (e.g., BTCUSDT).
            interval: The kline interval (e.g., 1m, 5m, 1h).
            limit: The number of klines to retrieve.

        Returns:
            A list of kline data.
        """
        path = "/fapi/v1/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        return await self._request("GET", path, params)

    def _to_decimal(self, value: Any) -> Decimal:
        """
        Convert value to Decimal, handling dict (price/markPrice), str, int, float, Decimal.
        Raises ValueError if None or invalid.
        """
        if value is None:
            raise ValueError("Value cannot be None")
        if isinstance(value, Decimal):
            return value
        if isinstance(value, dict):
            # For mark price dict, use 'markPrice' or 'price'
            price = value.get("markPrice") or value.get("price")
            if price is None:
                raise ValueError(
                    f"Dict has no 'markPrice' or 'price': {value}")
            return Decimal(str(price))
        if isinstance(value, (str, int, float)):
            return Decimal(str(value))
        raise ValueError(f"Cannot convert {type(value)} to Decimal: {value}")

    def _round_step(
        self, qty: Decimal, step_size: Decimal, round_mode: str = ROUND_DOWN
    ) -> Decimal:
        """
        Round quantity to step size.
        round_mode: ROUND_DOWN (default) or ROUND_UP.
        """
        if step_size == 0:
            return qty
        return (qty / step_size).quantize(Decimal("1"), rounding=round_mode) * step_size

    async def _find_symbol_by_order_id(self, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Optional[str]:
        """
        Find symbol for an order by scanning all open orders (fallback for cancel_order).

        Args:
            order_id: Binance order ID to search for.
            client_order_id: Client order ID to search for.

        Returns:
            Symbol if found, None otherwise.
        """
        if not order_id and not client_order_id:
            return None

        try:
            # Scan all open orders without symbol filter (returns all symbols)
            open_orders = await self._request("GET", "/fapi/v1/openOrders", {})

            for order in open_orders:
                if order_id and str(order.get("orderId", "")) == str(order_id):
                    return order.get("symbol")
                if client_order_id and order.get("clientOrderId") == client_order_id:
                    return order.get("symbol")

            LOG.debug(
                f"[_find_symbol_by_order_id] Order {order_id or client_order_id} not found in {len(open_orders)} open orders")
            return None

        except Exception as e:
            LOG.warning(
                f"[_find_symbol_by_order_id] Error scanning open orders: {e}")
            return None

    async def place_market_entry(
        self, symbol: str, side: str, quantity: str, new_client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a market entry order.

        Args:
            symbol: Trading pair.
            side: BUY or SELL.
            quantity: Order quantity.
            new_client_order_id: Optional client order ID.

        Returns:
            Order response.
        """
        # quantize qty according to exchange filters and validate min notional
        qty = await self.quantize_quantity(symbol, quantity)

        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": qty,
        }
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id
        return await self._request("POST", "/fapi/v1/order", params)

    async def place_stop_market_close_position(
        self,
        symbol: str,
        side: str,
        stop_price: str,
        position_side: Optional[str] = None,
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Place a stop market order to close position.

        Args:
            symbol: Trading pair.
            side: SELL for LONG, BUY for SHORT.
            stop_price: Stop price.
            position_side: For HEDGE mode.
            new_client_order_id: Optional client order ID.

        Returns:
            Order response.
        """
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "STOP_MARKET",
            "stopPrice": stop_price,
            "workingType": "MARK_PRICE",
            "closePosition": "true",
            "priceProtect": "true",
        }
        if position_side:
            params["positionSide"] = position_side
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id

        # PHASE B1: Try to detect -4116 (duplicate ClientOrderId) and reuse
        try:
            resp = await self._request("POST", "/fapi/v1/order", params)
            if new_client_order_id and "orderId" in resp:
                self.register_clientorderid(
                    new_client_order_id, str(resp["orderId"]), symbol)
            return resp
        except BinanceAPIError as e:
            if e.code == -4116 and new_client_order_id:
                # Duplicate ClientOrderId: try to reuse from ledger
                LOG.warning(
                    f"⚠️ [B1] -4116 Duplicate ClientOrderId {new_client_order_id}, checking ledger...")
                existing_order_id = self.check_clientorderid_reuse(
                    symbol, new_client_order_id)
                if existing_order_id:
                    LOG.info(
                        f"✅ [B1] Reusing order {existing_order_id} from ledger")
                    # Fetch the order to return
                    try:
                        order = await self.get_order(symbol, int(existing_order_id))
                        return order
                    except Exception as fetch_err:
                        LOG.warning(
                            f"⚠️ [B1] Could not fetch reused order: {fetch_err}")
                        raise e
                else:
                    LOG.warning(
                        f"⚠️ [B1] -4116 error but no ledger entry for {new_client_order_id}")
                    raise e
            else:
                raise

    async def place_take_profit_market_close_position(
        self,
        symbol: str,
        side: str,
        stop_price: str,
        position_side: Optional[str] = None,
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Place a take profit market order to close position.

        Args:
            symbol: Trading pair.
            side: SELL for LONG, BUY for SHORT.
            stop_price: Stop price.
            position_side: For HEDGE mode.
            new_client_order_id: Optional client order ID.

        Returns:
            Order response.
        """
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": stop_price,
            "workingType": "MARK_PRICE",
            "closePosition": "true",
            "priceProtect": "true",
        }
        if position_side:
            params["positionSide"] = position_side
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id

        # PHASE B1: Try to detect -4116 (duplicate ClientOrderId) and reuse
        try:
            resp = await self._request("POST", "/fapi/v1/order", params)
            if new_client_order_id and "orderId" in resp:
                self.register_clientorderid(
                    new_client_order_id, str(resp["orderId"]), symbol)
            return resp
        except BinanceAPIError as e:
            if e.code == -4116 and new_client_order_id:
                # Duplicate ClientOrderId: try to reuse from ledger
                LOG.warning(
                    f"⚠️ [B1] -4116 Duplicate ClientOrderId {new_client_order_id}, checking ledger...")
                existing_order_id = self.check_clientorderid_reuse(
                    symbol, new_client_order_id)
                if existing_order_id:
                    LOG.info(
                        f"✅ [B1] Reusing order {existing_order_id} from ledger")
                    # Fetch the order to return
                    try:
                        order = await self.get_order(symbol, int(existing_order_id))
                        return order
                    except Exception as fetch_err:
                        LOG.warning(
                            f"⚠️ [B1] Could not fetch reused order: {fetch_err}")
                        raise e
                else:
                    LOG.warning(
                        f"⚠️ [B1] -4116 error but no ledger entry for {new_client_order_id}")
                    raise e
            else:
                raise

    async def place_limit_reduce_only(
        self,
        symbol: str,
        side: str,
        price: str,
        quantity: str,
        position_side: Optional[str] = None,
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Place a limit reduce-only order.

        Args:
            symbol: Trading pair.
            side: SELL for LONG, BUY for SHORT.
            price: Limit price.
            quantity: Order quantity.
            position_side: For HEDGE mode.
            new_client_order_id: Optional client order ID.

        Returns:
            Order response.
        """
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": "GTC",
            "price": price,
            "quantity": quantity,
            "reduceOnly": "true",
        }
        if position_side:
            params["positionSide"] = position_side
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id

        # PHASE B1: Try to detect -4116 (duplicate ClientOrderId) and reuse
        try:
            resp = await self._request("POST", "/fapi/v1/order", params)
            if new_client_order_id and "orderId" in resp:
                self.register_clientorderid(
                    new_client_order_id, str(resp["orderId"]), symbol)
            return resp
        except BinanceAPIError as e:
            if e.code == -4116 and new_client_order_id:
                # Duplicate ClientOrderId: try to reuse from ledger
                LOG.warning(
                    f"⚠️ [B1] -4116 Duplicate ClientOrderId {new_client_order_id}, checking ledger...")
                existing_order_id = self.check_clientorderid_reuse(
                    symbol, new_client_order_id)
                if existing_order_id:
                    LOG.info(
                        f"✅ [B1] Reusing order {existing_order_id} from ledger")
                    # Fetch the order to return
                    try:
                        order = await self.get_order(symbol, int(existing_order_id))
                        return order
                    except Exception as fetch_err:
                        LOG.warning(
                            f"⚠️ [B1] Could not fetch reused order: {fetch_err}")
                        raise e
                else:
                    LOG.warning(
                        f"⚠️ [B1] -4116 error but no ledger entry for {new_client_order_id}")
                    raise e
            else:
                raise

    async def place_market_reduce_only(
        self,
        symbol: str,
        side: str,
        quantity: str,
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Place a MARKET reduce-only order to close (reduce) an existing position.

        Args:
            symbol: Trading pair.
            side: BUY or SELL (opposite of the open position side).
            quantity: Order quantity.
            new_client_order_id: Optional client order ID for idempotency.

        Returns:
            Order response.
        """
        # Quantize qty according to exchange filters and validate min notional
        qty = await self.quantize_quantity(symbol, quantity)

        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": qty,
            "reduceOnly": "true",
        }
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id

        # PHASE B1: Try to detect -4116 (duplicate ClientOrderId) and reuse
        try:
            resp = await self._request("POST", "/fapi/v1/order", params)
            if new_client_order_id and "orderId" in resp:
                self.register_clientorderid(
                    new_client_order_id, str(resp["orderId"]), symbol)
            return resp
        except BinanceAPIError as e:
            if e.code == -4116 and new_client_order_id:
                # Duplicate ClientOrderId: try to reuse from ledger
                LOG.warning(
                    f"⚠️ [B1] -4116 Duplicate ClientOrderId {new_client_order_id}, checking ledger...")
                existing_order_id = self.check_clientorderid_reuse(
                    symbol, new_client_order_id)
                if existing_order_id:
                    LOG.info(
                        f"✅ [B1] Reusing order {existing_order_id} from ledger")
                    # Fetch the order to return
                    try:
                        order = await self.get_order(symbol, int(existing_order_id))
                        return order
                    except Exception as fetch_err:
                        LOG.warning(
                            f"⚠️ [B1] Could not fetch reused order: {fetch_err}")
                        raise e
                else:
                    LOG.warning(
                        f"⚠️ [B1] -4116 error but no ledger entry for {new_client_order_id}")
                    raise e
            else:
                raise

    async def close_session(self):
        """Close the httpx session."""
        try:
            await self.session.aclose()
            LOG.info("BinanceAdapter httpx session closed.")
        except Exception:
            pass

    async def get_book_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get current book ticker (bid/ask prices and sizes).

        Args:
            symbol: The trading symbol (e.g., BTCUSDT).

        Returns:
            Book ticker data with bid/ask prices and sizes.
        """
        path = "/fapi/v1/ticker/bookTicker"
        params = {"symbol": symbol}
        return await self._request("GET", path, params)

    async def get_recent_trades(self, symbol: str, limit: int = 100) -> list:
        """
        Get recent trades for a symbol.

        Args:
            symbol: The trading symbol (e.g., BTCUSDT).
            limit: Number of recent trades to retrieve (max 1000).

        Returns:
            A list of recent trade data.
        """
        path = "/fapi/v1/trades"
        params = {"symbol": symbol, "limit": min(limit, 1000)}
        return await self._request("GET", path, params)

    async def get_mark_price_data(self, symbol: str) -> Dict[str, Any]:
        """
        Get mark price for a symbol.

        Args:
            symbol: The trading symbol (e.g., BTCUSDT).

        Returns:
            Mark price data.
        """
        path = "/fapi/v1/premiumIndex"
        params = {"symbol": symbol}
        return await self._request("GET", path, params)

    async def create_stop_market_order(self, order_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a STOP_MARKET order.

        Args:
            order_params: Order parameters.

        Returns:
            Order response.
        """
        path = "/fapi/v1/order"
        return await self._request("POST", path, order_params)

    def _get_fallback_backoff_ms(self) -> List[int]:
        """
        PHASE P0: Get fallback backoff configuration for retry logic.

        Returns:
            List of backoff delays in milliseconds.
        """
        try:
            if hasattr(self.config, 'trading') and hasattr(self.config.trading, 'execution') and hasattr(self.config.trading.execution, 'fallback'):
                fallback_config = self.config.trading.execution.fallback or {}
            elif isinstance(self.config, dict):
                fallback_config = self.config.get("trading", {}).get(
                    "execution", {}).get("fallback", {})
            else:
                fallback_config = {}
        except (AttributeError, TypeError):
            fallback_config = {}

        # Get backoff_ms with defaults
        backoff_ms = fallback_config.get("backoff_ms", [200, 500, 1000]) if isinstance(
            fallback_config, dict) else getattr(fallback_config, "backoff_ms", [200, 500, 1000])

        if not isinstance(backoff_ms, list):
            backoff_ms = [200, 500, 1000]

        return backoff_ms

    # ========== WebSocket USER_DATA_STREAM ==========

    async def start_websocket(self) -> None:
        """Start WebSocket USER_DATA_STREAM in a background thread."""
        if self.shadow_mode:
            self.logger.info(
                "[BinanceAdapter] Shadow mode, skipping WebSocket start")
            return

        if self.ws_running:
            self.logger.warning("[BinanceAdapter] WebSocket already running")
            return

        # Get listen key
        self.ws_listen_key = await self._get_listen_key()
        if not self.ws_listen_key:
            self.logger.error("[BinanceAdapter] Failed to get listen key")
            return

        self.ws_running = True
        self.ws_thread = threading.Thread(
            target=self._websocket_thread_entry,
            daemon=True,
            name="BinanceWsThread"
        )
        self.ws_thread.start()
        self.logger.info("[BinanceAdapter] WebSocket thread started")

    def _websocket_thread_entry(self) -> None:
        """Entry point for WebSocket thread (runs asyncio loop)."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._websocket_loop())
        except Exception as e:
            self.logger.error(f"[BinanceAdapter] WebSocket loop error: {e}")
        finally:
            loop.close()

    async def _websocket_loop(self) -> None:
        """Main WebSocket loop with reconnection logic."""
        import websockets

        while self.ws_running:
            try:
                ws_url = self._build_ws_url()
                self.logger.info(f"[BinanceAdapter] Connecting to {ws_url}")

                async with websockets.connect(ws_url) as ws:
                    self.ws_reconnect_delay = 1.0  # Reset on success
                    self.logger.info("[BinanceAdapter] WebSocket connected")

                    # Schedule listen key refresh
                    asyncio.create_task(self._listen_key_refresh_loop())

                    async for msg_raw in ws:
                        if not self.ws_running:
                            break
                        try:
                            msg = json.loads(msg_raw)
                            await self._handle_ws_message(msg)
                        except json.JSONDecodeError:
                            self.logger.warning(
                                f"[BinanceAdapter] Invalid JSON: {msg_raw[:100]}")

            except Exception as e:
                if not self.ws_running:
                    break
                self.logger.warning(
                    f"[BinanceAdapter] WebSocket error: {e}, "
                    f"reconnecting in {self.ws_reconnect_delay}s"
                )
                await asyncio.sleep(self.ws_reconnect_delay)
                self.ws_reconnect_delay = min(
                    self.ws_reconnect_delay * 2,
                    self.ws_max_reconnect_delay
                )
                # Refresh listen key on reconnect
                self.ws_listen_key = await self._get_listen_key()

    def _build_ws_url(self) -> str:
        """Build WebSocket URL based on environment."""
        if "testnet" in self.base_url.lower():
            # TESTNET WebSocket URL (note: stream.testnet.* doesn't exist, use testnet.*)
            return f"wss://testnet.binancefuture.com/ws/{self.ws_listen_key}"
        # LIVE WebSocket URL
        return f"wss://fstream.binance.com/ws/{self.ws_listen_key}"

    async def _get_listen_key(self) -> Optional[str]:
        """Get a new listen key for USER_DATA_STREAM."""
        try:
            resp = await self._request("POST", "/fapi/v1/listenKey", {})
            return resp.get("listenKey")
        except Exception as e:
            self.logger.error(
                f"[BinanceAdapter] Failed to get listen key: {e}")
            return None

    async def _refresh_listen_key(self) -> bool:
        """Refresh listen key to keep it alive (must be done every 30 mins)."""
        if not self.ws_listen_key:
            return False
        try:
            await self._request("PUT", "/fapi/v1/listenKey", {})
            self.listen_key_last_refresh = time.time()
            return True
        except Exception as e:
            self.logger.warning(
                f"[BinanceAdapter] Listen key refresh failed: {e}")
            return False

    async def _listen_key_refresh_loop(self) -> None:
        """Periodically refresh listen key every 25 minutes."""
        while self.ws_running and self.ws_listen_key:
            await asyncio.sleep(25 * 60)  # 25 minutes
            await self._refresh_listen_key()

    async def stop_websocket(self) -> None:
        """Stop WebSocket connection."""
        self.ws_running = False
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=5.0)
        self.ws_thread = None
        self.ws_listen_key = None
        self.logger.info("[BinanceAdapter] WebSocket stopped")

    async def _handle_ws_message(self, msg: Dict[str, Any]) -> None:
        """Handle incoming WebSocket message."""
        event_type = msg.get("e")

        if event_type == "ORDER_TRADE_UPDATE":
            await self._handle_order_trade_update(msg)
        elif event_type == "ACCOUNT_UPDATE":
            await self._handle_account_update(msg)
        elif event_type == "listenKeyExpired":
            self.logger.warning(
                "[BinanceAdapter] Listen key expired, refreshing...")
            self.ws_listen_key = await self._get_listen_key()
        else:
            self.logger.debug(
                f"[BinanceAdapter] Unknown WS event: {event_type}")

    async def _handle_order_trade_update(self, msg: Dict[str, Any]) -> None:
        """Handle ORDER_TRADE_UPDATE event from WebSocket USER_DATA_STREAM."""
        order_data = msg.get("o", {})
        normalized = self._normalize_order_event(order_data)
        status = normalized.get("status")

        # Log all order updates
        self.logger.info(
            f"[BinanceAdapter] WS ORDER_TRADE_UPDATE: symbol={normalized.get('symbol')} "
            f"status={status} side={normalized.get('side')} qty={normalized.get('quantity')} "
            f"clientOrderId={normalized.get('clientOrderId')}"
        )

        # Emit ORDER_UPDATE for all updates
        if self.fsm_core:
            try:
                from vfoundation.core.protocol import Message
                event_msg = Message(
                    event_type="ORDER_UPDATE",
                    payload=normalized,
                    source="binance_ws"
                )
                await self.fsm_core.emit(event_msg)
            except ImportError:
                self.logger.warning(
                    "[BinanceAdapter] vfoundation not available for FSM emit")
        elif self.fsm:
            # Legacy FSM support
            if hasattr(self.fsm, 'emit'):
                await self.fsm.emit("ORDER_UPDATE", normalized)

        # FIX-FILL-TIMEOUT: Emit EVT:TRADE_EXECUTED for filled orders
        # This is the WebSocket path that runtime_factory listens to
        if status in ("FILLED", "PARTIALLY_FILLED"):
            trade_executed_payload = {
                "symbol": normalized.get("symbol"),
                "side": normalized.get("side"),
                "quantity": normalized.get("quantity"),
                "price": normalized.get("averagePrice") or normalized.get("price"),
                "orderId": normalized.get("orderId"),
                "clientOrderId": normalized.get("clientOrderId"),
                "status": status,
                "order_type": normalized.get("orderType"),
                "timestamp": normalized.get("updateTime"),
                "source": "websocket",
            }

            self.logger.info(
                f"[BinanceAdapter] ✅ FILL detected via WebSocket: "
                f"symbol={trade_executed_payload['symbol']} side={trade_executed_payload['side']} "
                f"qty={trade_executed_payload['quantity']} price={trade_executed_payload['price']}"
            )

            if self.fsm:
                await self.fsm.emit("EVT:TRADE_EXECUTED", trade_executed_payload)

    async def _handle_account_update(self, msg: Dict[str, Any]) -> None:
        """
        Handle ACCOUNT_UPDATE event (balance/position changes).

        ORPHAN-FIX: Emit EVT:ACCOUNT_UPDATE_RECEIVED to fsm so ExecPosRuntimeV2
        can detect position closures (qty=0) and cancel orphan TP/SL.
        Previously only emitted to fsm_core as POSITION_UPDATE which was not
        connected to ExecPos, causing 30s delay via REST polling.
        """
        account_data = msg.get("a", {})
        positions = account_data.get("P", [])

        # Build normalized positions list for ExecPos
        normalized_positions = []
        for pos in positions:
            normalized = {
                "symbol": pos.get("s"),
                "positionAmt": float(pos.get("pa", 0)),
                "entryPrice": float(pos.get("ep", 0)),
                "unrealizedPnl": float(pos.get("up", 0)),
                "marginType": pos.get("mt"),
                "positionSide": pos.get("ps"),
            }
            normalized_positions.append(normalized)

            # Legacy: also emit to fsm_core for other consumers
            if self.fsm_core:
                try:
                    from vfoundation.core.protocol import Message
                    event_msg = Message(
                        event_type="POSITION_UPDATE",
                        payload=normalized,
                        source="binance_ws"
                    )
                    await self.fsm_core.emit(event_msg)
                except ImportError:
                    pass

        # ORPHAN-FIX: Emit EVT:ACCOUNT_UPDATE_RECEIVED to fsm for ExecPos V2
        # This triggers immediate orphan cleanup when position closes (qty=0)
        if self.fsm and normalized_positions:
            LOG.info(
                f"[BinanceAdapter] WS ACCOUNT_UPDATE: emitting EVT:ACCOUNT_UPDATE_RECEIVED "
                f"positions_count={len(normalized_positions)} "
                f"symbols={[p['symbol'] for p in normalized_positions]}"
            )
            await self.fsm.emit(
                "EVT:ACCOUNT_UPDATE_RECEIVED",
                {"positions": normalized_positions},
            )

    def _normalize_order_event(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize WebSocket ORDER_TRADE_UPDATE event to standard format.

        EP-ORDERS-SYNC: Extended with all fields needed for bracket detection:
        - stopPrice (sp): Trigger price for SL/TP orders
        - closePosition (cp): Whether order closes entire position
        - workingType (wt): MARK_PRICE or CONTRACT_PRICE
        """
        status_map = {
            "NEW": "NEW",
            "PARTIALLY_FILLED": "PARTIALLY_FILLED",
            "FILLED": "FILLED",
            "CANCELED": "CANCELED",
            "EXPIRED": "EXPIRED",
            "REJECTED": "REJECTED",
        }
        raw_status = order_data.get("X", "UNKNOWN")

        # Parse stopPrice - critical for SL/TP identification
        sp_raw = order_data.get("sp")
        stop_price = float(sp_raw) if sp_raw and sp_raw != "0" else None

        return {
            "orderId": order_data.get("i"),
            "clientOrderId": order_data.get("c"),
            "symbol": order_data.get("s"),
            "side": order_data.get("S"),
            "type": order_data.get("o"),
            "positionSide": order_data.get("ps"),
            "status": status_map.get(raw_status, raw_status),
            "price": float(order_data.get("p", 0)),
            "avgPrice": float(order_data.get("ap", 0)),
            "origQty": float(order_data.get("q", 0)),
            "executedQty": float(order_data.get("z", 0)),
            "reduceOnly": order_data.get("R", False),
            "timeInForce": order_data.get("f"),
            "updateTime": order_data.get("T"),
            "realizedProfit": float(order_data.get("rp", 0)),
            "commission": float(order_data.get("n", 0)),
            "commissionAsset": order_data.get("N"),
            # EP-ORDERS-SYNC: Essential fields for bracket detection
            "stopPrice": stop_price,
            "closePosition": order_data.get("cp", False),
            "workingType": order_data.get("wt"),
            "origType": order_data.get("ot"),  # Original order type
            "tradeId": order_data.get("t"),  # Trade ID for fills
        }

    # ========== FSM Message-based Order Methods ==========

    async def place_order_fsm(
        self,
        dec_msg: Any,
        *,
        slippage_cap_bps: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Place order from FSM Message (DEC payload).

        Args:
            dec_msg: vfoundation Message with order decision payload
            slippage_cap_bps: Optional slippage cap override
            **kwargs: Additional order parameters

        Returns:
            Dict with order result and metadata
        """
        # Extract payload from Message
        if hasattr(dec_msg, 'payload'):
            payload = dec_msg.payload
        else:
            payload = dec_msg

        symbol = payload.get("symbol")
        side = payload.get("side")
        qty = str(payload.get("qty") or payload.get("quantity"))
        order_type = payload.get("type", "MARKET")
        price = str(payload.get("price")) if payload.get("price") else None
        client_order_id = payload.get(
            "clientOrderId") or payload.get("client_order_id")

        # Build ExchangeOrderParams
        params = ExchangeOrderParams(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=qty,
            price=price,
            client_order_id=client_order_id,
            time_in_force=payload.get("timeInForce", "GTC"),
            reduce_only=bool(payload.get("reduceOnly")),
            position_side=payload.get("positionSide"),
            stop_price=str(payload.get("stopPrice")) if payload.get(
                "stopPrice") else None
        )

        # Slippage protection for MARKET orders
        effective_slippage = slippage_cap_bps or self.slippage_cap_bps
        if order_type == "MARKET" and effective_slippage and price:
            # Calculate slippage-protected price (not implemented in Binance MARKET)
            pass

        try:
            result = await self.create_order(params)
            return {
                "success": True,
                "orderId": result.order_id,
                "clientOrderId": result.client_order_id,
                "status": result.status,
                "symbol": result.symbol,
                "side": result.side,
                "qty": result.quantity,
                "avgPrice": result.price,
            }
        except BinanceAPIError as e:
            # Handle bracket errors with retry
            if e.code in (-2021, -4016, -4017):
                return await self._handle_bracket_error(e, payload, params)
            raise

    async def _handle_bracket_error(
        self,
        error: BinanceAPIError,
        original_payload: Dict[str, Any],
        params: ExchangeOrderParams,
    ) -> Dict[str, Any]:
        """
        Handle bracket order errors with retry strategies.

        Error codes:
        - -2021: Order would immediately trigger
        - -4016: Invalid price vs position side
        - -4017: ReduceOnly rejected
        """
        self.logger.warning(
            f"[BinanceAdapter] Bracket error {error.code}: {error.msg}, "
            f"symbol={params.symbol}"
        )

        # Strategy: retry with adjusted parameters or convert to MARKET
        if error.code == -2021:
            # Order would trigger - convert SL/TP to MARKET
            self.logger.info(
                "[BinanceAdapter] Converting to MARKET order after -2021")
            params.order_type = "MARKET"
            params.price = None
            params.stop_price = None
            try:
                result = await self.create_order(params)
                return {
                    "success": True,
                    "orderId": result.order_id,
                    "fallback": "MARKET_CONVERSION",
                }
            except BinanceAPIError:
                pass

        # Return error
        return {
            "success": False,
            "error_code": error.code,
            "error_msg": error.msg,
            "nrr_code": error.nrr_code,
        }

    async def cancel_order_fsm(
        self,
        dec_msg: Any,
        *,
        idempotent: bool = True,
    ) -> Dict[str, Any]:
        """
        Cancel order from FSM Message with idempotency support.

        Args:
            dec_msg: vfoundation Message with cancel payload
            idempotent: If True, absorb -2011 (order not found) errors

        Returns:
            Dict with cancel result
        """
        if hasattr(dec_msg, 'payload'):
            payload = dec_msg.payload
        else:
            payload = dec_msg

        symbol = payload.get("symbol")
        order_id = payload.get("orderId") or payload.get("order_id")
        client_order_id = payload.get(
            "clientOrderId") or payload.get("client_order_id")

        try:
            result = await self.cancel_order(
                symbol=symbol,
                order_id=order_id,
                client_order_id=client_order_id,
            )
            self.metrics["cancel_idempotent_ok"] += 1
            return {
                "success": True,
                "orderId": result.get("orderId"),
                "status": "CANCELED",
            }
        except BinanceAPIError as e:
            if idempotent and e.code == -2011:
                # Order already canceled or doesn't exist
                self.metrics["cancel_-2011_absorbed"] += 1
                self.logger.debug(
                    f"[BinanceAdapter] Idempotent cancel: order not found "
                    f"(already canceled?), symbol={symbol}"
                )
                return {
                    "success": True,
                    "orderId": order_id,
                    "status": "ALREADY_CANCELED",
                    "idempotent": True,
                }
            raise


# ---- helpers ----


def _safe_read_err(resp):
    """Extract JSON error body from httpx.Response (sync method).

    FIX DUPID-PARSE-4116: httpx.Response.json() is SYNC, not async.
    Previously 'await resp.json()' caused TypeError, falling back to
    {"code": resp.status_code, "msg": resp.text} — losing the API error code.
    """
    try:
        return resp.json()  # httpx: sync method, returns dict
    except Exception:
        try:
            return {"code": resp.status_code, "msg": resp.text}
        except Exception:
            return {"code": resp.status_code, "msg": "unknown"}


def _make_binance_error(resp_or_code: Any, msg_or_err: Any = None) -> BinanceAPIError:
    # support both call styles: (_resp, err) and (code, msg)
    code: int = -1  # Default value
    if isinstance(resp_or_code, int):
        code = int(resp_or_code)
        msg = str(msg_or_err or "")
    else:
        # try to extract from err/json payload
        err = msg_or_err or {}
        if hasattr(err, "get"):
            code_val = err.get("code") or err.get("errno")
            msg = err.get("msg") or err.get("message") or str(err)
            try:
                code = int(code_val) if code_val is not None else -1
            except Exception:
                code = -1
        else:
            msg = str(err)
            code = -1

    # normalized NRR for exchange rejections
    rejection_codes = {-1013, -1021, -2010}
    nrr = "NRR-018" if code in rejection_codes else None

    # ГАРАНТОВАНО для rejection-кодів: викликаємо через модульну змінну LOG
    if nrr == "NRR-018":
        LOG.warning(
            "Exchange rejected order: code=%s, msg=%s, nrr_code=%s", code, msg, nrr)

    return BinanceAPIError(code=code, msg=msg, nrr_code=nrr)
