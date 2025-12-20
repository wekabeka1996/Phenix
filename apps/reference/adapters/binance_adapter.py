"""
Binance Futures Exchange Adapter (Reference Implementation)

Implements AbstractExchangeAdapter for Binance Futures (USDM).
Handles API key signing, endpoint selection (live/testnet), and error handling.
This adapter is instantiated by domain services with specific environment config.

Inherits from vfoundation.core.adapters.base.AbstractExchangeAdapter to ensure
compatibility with the generic FSM interface.
"""

import json as _json
import asyncio
import hashlib
import hmac
import logging
import time
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, quote_plus

import httpx

from vfoundation.core.adapters.base import (
    AbstractExchangeAdapter,
    ExchangeOrderParams,
    ExchangeOrderResponse,
    ExchangePosition,
)

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
    Binance Futures (USDM) Exchange Adapter.

    Implements AbstractExchangeAdapter to provide a consistent interface
    for vfoundation FSM domains.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://testnet.binancefuture.com",
        config: dict | None = None,
        *,
        session: Optional[httpx.AsyncClient] = None,  # <-- новий аргумент
        timeout: float = 10.0,
        **kwargs,
    ):
        rest_url = kwargs.pop("rest_url", None)  # legacy alias
        if rest_url:
            base_url = rest_url
        self.api_key = api_key
        self.api_secret = api_secret.encode()
        self.base_url = base_url.rstrip("/")
        self.config = config or {}
        self._timeout = timeout
        self.logger = logging.getLogger(__name__)

        # Time sync state
        self._time_offset_ms = 0
        self._last_time_sync_monotonic = 0.0
        self._time_sync_lock = asyncio.Lock()
        
        # recvWindow (ms). Max 60000 for Futures.
        try:
            if hasattr(self.config, 'recv_window_ms'):
                self._recv_window_ms = int(self.config.recv_window_ms)
            elif isinstance(self.config, dict):
                self._recv_window_ms = int(
                    self.config.get("recv_window_ms", 20000))
            else:
                self._recv_window_ms = 20000
        except (AttributeError, TypeError, ValueError):
            self._recv_window_ms = 20000

        # Public session field for compatibility
        self.session: httpx.AsyncClient = session or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self._timeout,
            headers={"X-MBX-APIKEY": self.api_key},
        )

        # ClientOrderId ledger for idempotency
        # Format: {clientOrderId: (timestamp_ms: int, order_id: str, symbol: str)}
        self._clientorderid_ledger: Dict[str, Tuple[int, str, str]] = {}

        self._mark_price_cache: Dict[
            str, Dict[str, Any]
        ] = {}  # symbol -> {'price': float, 'timestamp': float}

    # опційно: контекст-менеджер для акуратного закриття
    async def __aenter__(self) -> "BinanceAdapter":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        try:
            await self.session.aclose()
        except Exception:
            pass

    async def start(self) -> None:
        """
        Start the adapter (no-op for REST-only adapter).

        This method exists for compatibility with FSM initialization
        that expects polling adapters. Since this adapter is REST-only,
        no background polling is started.
        """
        LOG.info("BinanceAdapter started (REST-only mode, no polling)")

    async def stop(self) -> None:
        """
        Stop the adapter (no-op for REST-only adapter).

        This method exists for compatibility with FSM cleanup
        that expects polling adapters. Since this adapter is REST-only,
        no background polling needs to be stopped.
        """
        LOG.info("BinanceAdapter stopped (REST-only mode, no polling)")

    # ClientOrderId Ledger Methods
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
            f"Registered ClientOrderId {client_order_id} -> {order_id} ({symbol})")

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
                f"Reusing ClientOrderId {client_order_id} -> {order_id} ({symbol}) - age {age_ms/1000:.0f}s")
            return order_id

        # Stale entry: remove from ledger
        if age_ms >= 24 * 3600 * 1000:
            del self._clientorderid_ledger[client_order_id]
            LOG.debug(
                f"Cleaned stale ClientOrderId {client_order_id} (age {age_ms/3600000:.1f}h)")

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
        # TTL 2 хв за замовчуванням
        try:
            if hasattr(self.config, 'time_sync_ttl_sec'):
                ttl_sec = int(self.config.time_sync_ttl_sec)
            elif isinstance(self.config, dict):
                ttl_sec = int(self.config.get("time_sync_ttl_sec", 120))
            else:
                ttl_sec = 120
        except (AttributeError, TypeError, ValueError):
            ttl_sec = 120

        now_mono = time.monotonic()
        if not force and (now_mono - self._last_time_sync_monotonic) < ttl_sec:
            return
        async with self._time_sync_lock:
            # Могли вже інші синхронізувати
            if not force and (time.monotonic() - self._last_time_sync_monotonic) < ttl_sec:
                return
            server_ms = await self._server_time()
            local_ms = int(time.time() * 1000)
            self._time_offset_ms = server_ms - local_ms
            self._last_time_sync_monotonic = time.monotonic()

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

        # Prepare base params (without signature) for potential retry
        base_params = dict(params)

        async def _do(method: str, base_params: dict):
            if signed:
                await self._sync_time(False)
                qs, final_params = self._sign_build(base_params)
                # Use self.session to allow mocking in tests
                r = await self.session.request(method.upper(), url, params=final_params)
                if r.status_code >= 400:
                    err = await _safe_read_err(r)
                    raise _make_binance_error(r, err)
                return await _coerce_json(r)
            else:
                r = await self.session.request(
                    method.upper(), url, params=self._norm_params(base_params)
                )
                r.raise_for_status()
                return await _coerce_json(r)

        try:
            return await _do(method, base_params)
        except Exception as e:
            # Retry on timeout
            import httpx
            import httpcore

            def _is_exc_type(obj: object) -> bool:
                return isinstance(obj, type) and issubclass(obj, BaseException)

            timeout_exceptions = tuple(
                t
                for t in (
                    getattr(httpx, "ReadTimeout", None),
                    getattr(httpx, "ConnectTimeout", None),
                    getattr(httpx, "TimeoutException", None),
                    getattr(httpcore, "ReadTimeout", None),
                    getattr(httpcore, "ConnectTimeout", None),
                    getattr(httpcore, "TimeoutException", None),
                )
                if _is_exc_type(t)
            )

            if timeout_exceptions and isinstance(e, timeout_exceptions):
                LOG.warning(f"Timeout on {method} {path}, retrying once...")
                await asyncio.sleep(0.5)
                return await _do(method, base_params)
            
            # Retry on timestamp error (-1021)
            msg = str(e)
            if "code': -1021" in msg or "-1021" in msg:
                await self._sync_time(True)
                return await _do(method, base_params)
            
            # Retry on signature error (-1022)
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
        """
        path = "/fapi/v1/order"
        order_params = {
            "symbol": params.symbol,
            "side": params.side.upper(),
            "type": params.order_type.upper(),
            "quantity": params.quantity,
        }
        if params.price:
            order_params["price"] = params.price
        if params.time_in_force:
            order_params["timeInForce"] = params.time_in_force
        if params.reduce_only:
            order_params["reduceOnly"] = "true"
        if params.close_position:
            order_params["closePosition"] = "true"
        if params.client_order_id:
            order_params["newClientOrderId"] = params.client_order_id
        if params.position_side:
            order_params["positionSide"] = params.position_side
        if params.stop_price:
            order_params["stopPrice"] = params.stop_price
        if params.working_type:
            order_params["workingType"] = params.working_type

        result = await self._request("POST", path, order_params)
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
                "[cancel_order] Empty symbol, attempting to scan open orders")
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
        """
        path = "/fapi/v1/openOrders"
        params = {}
        if symbol:
            params["symbol"] = symbol

        result = await self._request("GET", path, params)
        orders = []
        for order in result:
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
            ))
        return orders

    async def get_open_positions(self, symbol: Optional[str] = None) -> List[ExchangePosition]:
        """
        Retrieve open positions (optionally filtered by symbol).
        Only returns non-zero positions.
        
        Implements AbstractExchangeAdapter.get_open_positions()
        """
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol

        # Get fallback retry configuration
        fallback_backoff_ms = self._get_fallback_backoff_ms()

        # Retry logic for empty responses
        max_retries = len(fallback_backoff_ms)
        last_exception = None

        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                # signed GET /fapi/v2/positionRisk
                raw = await self._request("GET", "/fapi/v2/positionRisk", params)

                if not isinstance(raw, list) or len(raw) == 0:
                    if attempt < max_retries:
                        self.logger.warning(
                            f"API /fapi/v2/positionRisk returned empty/non-list on attempt {attempt+1}, retrying in {fallback_backoff_ms[attempt]}ms: {raw}")
                        await asyncio.sleep(fallback_backoff_ms[attempt] / 1000.0)
                        continue
                    else:
                        self.logger.error(
                            f"API /fapi/v2/positionRisk still empty after {max_retries+1} attempts, returning empty positions")
                else:
                    if attempt > 0:
                        self.logger.info(
                            f"API /fapi/v2/positionRisk recovered after {attempt+1} attempts, returned {len(raw)} total records")

                positions: List[ExchangePosition] = []
                for p in raw:
                    # Binance returns numbers as strings - keep precision
                    amt_str = p.get("positionAmt", "0")
                    amt = float(amt_str)
                    symbol = p.get('symbol', 'UNKNOWN')

                    if abs(amt) <= 0.0:
                        continue  # Skip zero positions

                    entry_str = p.get("entryPrice", "0") or "0"
                    mark_str = p.get("markPrice", "0") or "0"
                    upnl_str = p.get("unRealizedProfit", "0") or "0"
                    lev = int(float(p.get("leverage", "0") or 0))

                    # Hedge: 'LONG'/'SHORT'; One-way: 'BOTH'
                    pos_side = p.get("positionSide", "BOTH") or "BOTH"
                    side = "LONG" if (amt > 0 and pos_side in (
                        "BOTH", "LONG")) else "SHORT"

                    pos_obj = ExchangePosition(
                        symbol=p.get("symbol", ""),
                        position_side=pos_side,  # BOTH/LONG/SHORT
                        side=side,  # LONG/SHORT (convenient for business logic)
                        position_amount=amt_str,
                        entry_price=entry_str,
                        mark_price=mark_str,
                        unrealized_profit=upnl_str,
                        leverage=lev,
                        margin_type=p.get("marginType", "cross").upper(),
                        isolated_margin=float(
                            p.get("isolatedMargin", "0") or 0),
                        update_time_ms=int(p.get("updateTime", 0) or 0),
                    )
                    positions.append(pos_obj)

                # If we got empty positions after successful API call, enter fallback mode
                if not positions and isinstance(raw, list) and len(raw) == 0:
                    self.logger.warning(
                        "FALLBACK_TRIGGER: Empty positions response detected - this may trigger fallback mode in ExposureGuard"
                    )

                return positions

            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    self.logger.warning(
                        f"get_open_positions() attempt {attempt+1} failed: {e}, retrying in {fallback_backoff_ms[attempt]}ms")
                    await asyncio.sleep(fallback_backoff_ms[attempt] / 1000.0)
                else:
                    self.logger.error(
                        f"get_open_positions() failed after {max_retries+1} attempts: {e}")
                    raise last_exception

    async def get_positions_notional_usd_shadow(self) -> float:
        """
        Calculate total notional value (USD) of all open positions directly from exchange.
        Used for shadow/safety checks.
        """
        positions = await self.get_open_positions()
        total_notional = 0.0
        for p in positions:
            # notional = abs(amount * mark_price)
            try:
                notional = abs(float(p.position_amount) * float(p.mark_price))
                total_notional += notional
            except (ValueError, TypeError):
                self.logger.warning(f"Could not calculate notional for position {p.symbol}: amt={p.position_amount}, price={p.mark_price}")
                continue
        return total_notional

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
        
        # Check minQty if available
        min_qty = lot.get("minQty")
        if min_qty:
            min_qty_d = Decimal(str(min_qty))
            if q < min_qty_d:
                # Clamp to minimum quantity to avoid zero-quantity error
                q = min_qty_d

        if q <= 0:
            raise ValueError(f"Quantity {qty_d} rounds to zero with stepSize {step_size}")

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

    def _to_decimal(self, value: Any) -> Decimal:
        """
        Convert value to Decimal, handling dict (price/markPrice), str, int, float.
        Raises ValueError if None or invalid.
        """
        if value is None:
            raise ValueError("Value cannot be None")
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

    def _get_fallback_backoff_ms(self) -> List[int]:
        """
        Get fallback backoff configuration for retry logic.

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

async def _safe_read_err(resp):
    try:
        return await resp.json()
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

    if nrr == "NRR-018":
        LOG.warning(
            "Exchange rejected order: code=%s, msg=%s, nrr_code=%s", code, msg, nrr)

    return BinanceAPIError(code=code, msg=msg, nrr_code=nrr)
