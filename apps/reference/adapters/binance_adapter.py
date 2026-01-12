"""
Binance Futures Exchange Adapter (Reference Implementation)

Implements AbstractExchangeAdapter for Binance Futures (USDM).
Handles API key signing, endpoint selection (live/testnet), and error handling.
This adapter is instantiated by domain services with specific environment config.

Inherits from vfoundation.core.adapters.base.AbstractExchangeAdapter to ensure
compatibility with the generic FSM interface.
"""

from __future__ import annotations

import json as _json
import asyncio
import hashlib
import hmac
import logging
import time
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, quote_plus

try:
    import httpx  # type: ignore
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

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
        if httpx is None:
            raise ImportError(
                "Optional dependency missing: `httpx` is required for BinanceAdapter. "
                "Install test/runtime extras or add `httpx` to requirements."
            )

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

    async def _find_symbol_by_order_id(
        self,
        order_id: Optional[str],
        client_order_id: Optional[str],
    ) -> str:
        """Best-effort resolve symbol for an order.

        Binance cancel/get endpoints typically require `symbol`. In some retry/repair
        paths we only have `orderId`/`clientOrderId`. We first consult the local
        ClientOrderId ledger, then fall back to scanning open orders.

        Returns empty string when symbol can't be resolved.
        """
        order_id_str = str(order_id).strip() if order_id is not None else ""
        client_order_id_str = str(client_order_id).strip() if client_order_id is not None else ""

        if client_order_id_str:
            entry = self._clientorderid_ledger.get(client_order_id_str)
            if entry:
                return str(entry[2] or "").strip()

        if order_id_str:
            for _, (_, ledger_order_id, ledger_symbol) in self._clientorderid_ledger.items():
                if str(ledger_order_id).strip() == order_id_str:
                    return str(ledger_symbol or "").strip()

        try:
            raw = await self._request("GET", "/fapi/v1/openOrders", {}, signed=True)
            if isinstance(raw, list):
                for o in raw:
                    if not isinstance(o, dict):
                        continue
                    if order_id_str and str(o.get("orderId", "")).strip() == order_id_str:
                        return str(o.get("symbol", "")).strip()
                    if client_order_id_str and str(o.get("clientOrderId", "")).strip() == client_order_id_str:
                        return str(o.get("symbol", "")).strip()
        except Exception as e:
            LOG.warning(f"[_find_symbol_by_order_id] openOrders scan failed: {e}")

        return ""

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

    def _normalize_algo_order_response(self, resp: dict) -> dict:
        """Normalize Binance Algo Order responses to look like regular order responses.

        Binance migrated conditional orders (STOP/TAKE_PROFIT/TRAILING_STOP) to Algo Service.
        The Algo endpoints may return `algoId` instead of `orderId`. Downstream code expects
        `orderId` in many places, so we provide a compatibility alias.
        """
        if isinstance(resp, dict) and "orderId" not in resp and "algoId" in resp:
            resp = dict(resp)
            resp["orderId"] = resp["algoId"]
        return resp

    async def _post_order_with_algo_fallback(self, params: dict) -> dict:
        """POST an order, retrying conditional types via Algo Order API when required.

        As of Dec 2025, Binance USDM Futures migrates conditional order types
        (STOP_MARKET/TAKE_PROFIT_MARKET/STOP/TAKE_PROFIT/TRAILING_STOP_MARKET)
        from `POST /fapi/v1/order` to `POST /fapi/v1/algoOrder`.
        """
        try:
            return await self._request("POST", "/fapi/v1/order", params)
        except BinanceAPIError as e:
            # -4120 STOP_ORDER_SWITCH_ALGO: conditional orders must be placed via Algo endpoints
            if e.code == -4120:
                algo_params = dict(params)
                # Binance Algo Order API requires algoType for conditional orders.
                algo_params.setdefault("algoType", "CONDITIONAL")

                # Algo Order uses triggerPrice instead of stopPrice.
                if "stopPrice" in algo_params and "triggerPrice" not in algo_params:
                    algo_params["triggerPrice"] = algo_params.pop("stopPrice")

                # If closePosition=true, Binance forbids quantity/reduceOnly for conditional orders.
                close_pos = algo_params.get("closePosition")
                if isinstance(close_pos, str):
                    close_pos_true = close_pos.strip().lower() == "true"
                else:
                    close_pos_true = bool(close_pos)
                if close_pos_true:
                    algo_params.pop("quantity", None)
                    algo_params.pop("reduceOnly", None)

                resp = await self._request("POST", "/fapi/v1/algoOrder", algo_params)
                return self._normalize_algo_order_response(resp)
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

    async def get_exchange_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get exchange information for a symbol or all symbols if None.
        Implements AbstractExchangeAdapter.get_exchange_info()
        """
        path = "/fapi/v1/exchangeInfo"
        params = {}
        if symbol:
            params["symbol"] = symbol
        # exchangeInfo is public/market_data, no auth required usually, but adapter handles key injection?
        # Typically exchangeInfo is NONE security type.
        return await self._request("GET", path, params, signed=False)

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

    # =========================================================================
    # TASK47c-B: Leverage and Margin Mode Methods
    # =========================================================================
    # 
    # CRITICAL: Hedge Mode Handling (TASK47c-B-FIX-01)
    # 
    # Binance positionRisk returns multiple entries per symbol in Hedge mode:
    # - positionSide: BOTH (One-way mode) or LONG/SHORT (Hedge mode)
    # 
    # Strategy (fail-closed):
    # 1. Collect ALL entries for the symbol
    # 2. If ONE entry with positionSide=BOTH → use it (One-way mode)
    # 3. If MULTIPLE entries (LONG/SHORT) → verify they have SAME leverage/marginType
    #    - If consistent → return the value
    #    - If inconsistent → FAIL-CLOSED (NRR-024)
    # 4. If NO entries → FAIL (NRR-024)
    # =========================================================================

    def _extract_position_entries(self, result: list, symbol: str) -> list:
        """Extract all position risk entries for a symbol.
        
        Returns list of dicts with symbol, positionSide, leverage, marginType.
        Note: isolated is preserved as-is (None if missing) for fail-closed detection.
        """
        entries = []
        for pos in result:
            if pos.get("symbol") == symbol:
                entries.append({
                    "positionSide": pos.get("positionSide", "BOTH"),
                    "leverage": int(float(pos.get("leverage", 1))),
                    "marginType": pos.get("marginType", ""),
                    # Preserve None if not present (for fail-closed detection)
                    "isolated": pos.get("isolated"),  # None if missing
                })
        return entries

    async def get_current_leverage(self, symbol: str) -> int:
        """Get current leverage for a symbol from exchange.
        
        TASK47c-B: LeverageService L0 support.
        Uses /fapi/v2/positionRisk to get current leverage.
        
        TASK47c-B-FIX-01: Hedge mode determinism (fail-closed)
        - One-way mode (BOTH): single entry, use directly
        - Hedge mode (LONG/SHORT): verify all entries have SAME leverage
        - Inconsistent leverage across sides → NRR-024 fail-closed
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            
        Returns:
            Current leverage as integer (1-125)
            
        Raises:
            BinanceAPIError: On any ambiguity or error (fail-closed)
        """
        path = "/fapi/v2/positionRisk"
        params = {"symbol": symbol}
        result = await self._request("GET", path, params)
        
        if not isinstance(result, list) or len(result) == 0:
            raise BinanceAPIError(
                code=-1,
                msg=f"No position risk data for {symbol}",
                nrr_code="NRR-024"
            )
        
        entries = self._extract_position_entries(result, symbol)
        
        if len(entries) == 0:
            raise BinanceAPIError(
                code=-1,
                msg=f"Symbol {symbol} not found in position risk",
                nrr_code="NRR-024"
            )
        
        # Collect all unique leverage values
        leverage_values = set(e["leverage"] for e in entries)
        
        if len(leverage_values) != 1:
            # FAIL-CLOSED: Inconsistent leverage across position sides (Hedge mode issue)
            sides = [f"{e['positionSide']}={e['leverage']}x" for e in entries]
            raise BinanceAPIError(
                code=-1,
                msg=f"Inconsistent leverage for {symbol} across sides: {', '.join(sides)}",
                nrr_code="NRR-024"
            )
        
        leverage = leverage_values.pop()
        LOG.debug(f"LEVERAGE_GET: {symbol} = {leverage}x (entries: {len(entries)})")
        return leverage

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol on exchange.
        
        TASK47c-B: LeverageService L0 support.
        Uses /fapi/v1/leverage endpoint.
        
        Note: Binance sets leverage for ALL position sides with one call.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            leverage: Leverage to set (1-125)
            
        Returns:
            True on success
            
        Raises:
            BinanceAPIError: On failure
        """
        path = "/fapi/v1/leverage"
        params = {
            "symbol": symbol,
            "leverage": leverage,
        }
        result = await self._request("POST", path, params)
        actual = result.get("leverage")
        LOG.info(f"LEVERAGE_SET: {symbol} -> {leverage}x (response: {actual})")
        
        # Verify the set took effect
        if actual is not None and int(actual) != leverage:
            raise BinanceAPIError(
                code=-1,
                msg=f"Leverage set mismatch: requested {leverage}, got {actual}",
                nrr_code="NRR-022"
            )
        return True

    def _normalize_margin_type(self, entry: dict) -> str:
        """Normalize margin type from positionRisk entry.
        
        TASK47c-B-FIX-02: Stable marginType mapping
        
        Handles:
        - marginType: "isolated" | "cross" | "crossed" (string, case-insensitive)
        - isolated: true/false (boolean fallback)
        
        Returns:
            "isolated" or "cross"
        """
        # Primary: marginType field (case-insensitive)
        margin_type = str(entry.get("marginType", "")).strip().lower()
        
        if margin_type == "isolated":
            return "isolated"
        elif margin_type in ("cross", "crossed"):
            return "cross"
        
        # Fallback: isolated boolean field
        isolated_flag = entry.get("isolated")
        if isinstance(isolated_flag, bool):
            return "isolated" if isolated_flag else "cross"
        if isinstance(isolated_flag, str):
            return "isolated" if isolated_flag.lower() == "true" else "cross"
        
        # FAIL-CLOSED: Unknown margin type
        raise BinanceAPIError(
            code=-1,
            msg=f"Unknown marginType: '{entry.get('marginType')}' (isolated={entry.get('isolated')})",
            nrr_code="NRR-024"
        )

    async def get_margin_mode(self, symbol: str) -> str:
        """Get current margin mode for a symbol from exchange.
        
        TASK47c-B: LeverageService L0 support.
        Uses /fapi/v2/positionRisk to get marginType.
        
        TASK47c-B-FIX-01: Hedge mode determinism (fail-closed)
        - One-way mode (BOTH): single entry, use directly
        - Hedge mode (LONG/SHORT): verify all entries have SAME marginType
        - Inconsistent margin mode across sides → NRR-024 fail-closed
        
        TASK47c-B-FIX-02: Stable marginType mapping
        - Handles marginType string (cross/crossed/isolated)
        - Handles isolated boolean fallback
        - Unknown values → fail-closed
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            
        Returns:
            Margin mode: "isolated" or "cross"
            
        Raises:
            BinanceAPIError: On any ambiguity or error (fail-closed)
        """
        path = "/fapi/v2/positionRisk"
        params = {"symbol": symbol}
        result = await self._request("GET", path, params)
        
        if not isinstance(result, list) or len(result) == 0:
            raise BinanceAPIError(
                code=-1,
                msg=f"No position risk data for {symbol}",
                nrr_code="NRR-024"
            )
        
        entries = self._extract_position_entries(result, symbol)
        
        if len(entries) == 0:
            raise BinanceAPIError(
                code=-1,
                msg=f"Symbol {symbol} not found in position risk",
                nrr_code="NRR-024"
            )
        
        # Normalize and collect all unique margin modes
        margin_modes = set()
        for entry in entries:
            mode = self._normalize_margin_type(entry)
            margin_modes.add(mode)
        
        if len(margin_modes) != 1:
            # FAIL-CLOSED: Inconsistent margin mode across position sides
            sides = [f"{e['positionSide']}={self._normalize_margin_type(e)}" for e in entries]
            raise BinanceAPIError(
                code=-1,
                msg=f"Inconsistent margin mode for {symbol} across sides: {', '.join(sides)}",
                nrr_code="NRR-024"
            )
        
        margin_mode = margin_modes.pop()
        LOG.debug(f"MARGIN_MODE_GET: {symbol} = {margin_mode} (entries: {len(entries)})")
        return margin_mode

    async def set_margin_mode(self, symbol: str, mode: str) -> bool:
        """Set margin mode for a symbol on exchange.
        
        TASK47c-B: LeverageService L0 support.
        Uses /fapi/v1/marginType endpoint.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            mode: Margin mode ("isolated" or "cross")
            
        Returns:
            True on success
            
        Raises:
            BinanceAPIError: On failure (except -4046: no need to change)
        """
        # Binance uses ISOLATED and CROSSED for marginType values
        margin_type = "ISOLATED" if mode.lower() == "isolated" else "CROSSED"
        
        path = "/fapi/v1/marginType"
        params = {
            "symbol": symbol,
            "marginType": margin_type,
        }
        
        try:
            result = await self._request("POST", path, params)
            LOG.info(f"MARGIN_MODE_SET: {symbol} -> {mode} ({margin_type})")
            return True
        except BinanceAPIError as e:
            # -4046: No need to change margin type (already correct)
            if e.code == -4046:
                LOG.debug(f"MARGIN_MODE_SET: {symbol} already {mode} (no change needed)")
                return True
            raise


    async def create_stop_market_order(self, order_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a STOP_MARKET order.

        Args:
            order_params: Order parameters.

        Returns:
            Order response.
        """
        return await self._post_order_with_algo_fallback(order_params)

    async def place_market_entry(
        self, symbol: str, side: str, quantity: str, new_client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a market entry order.

        Args:
            symbol: Trading pair.
            side: BUY or SELL.
            quantity: Order quantity (MUST be pre-normalized by caller via normalize_qty).
            new_client_order_id: Optional client order ID.

        Returns:
            Order response.
        
        TASK50: Removed quantize_quantity call - qty normalization is now done
        at dispatch boundary (fsm.py) with fail-closed semantics. No double rounding.
        """
        # TASK50: qty is already normalized by caller, pass directly to exchange
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": quantity,  # Pre-normalized, no bump-up
        }
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id
        return await self._request("POST", "/fapi/v1/order", params)

    async def place_limit_entry(
        self,
        symbol: str,
        side: str,
        price: str,
        quantity: str,
        time_in_force: str = "GTC",
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        EP-01.4-INT-A: Place a LIMIT entry order with configurable time_in_force.

        Args:
            symbol: Trading pair.
            side: BUY or SELL.
            price: Limit price.
            quantity: Order quantity (pre-normalized).
            time_in_force: GTC (default), GTX (post-only/maker-only), IOC, or FOK.
            new_client_order_id: Optional client order ID.

        Returns:
            Order response.

        Notes:
            GTX = Post-Only / Maker-Only. Will be rejected if it would cross the book.
            On Binance USDS-M Futures, GTX orders may come as NEW -> EXPIRED via WS
            if they cannot be maker.
        """
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": time_in_force,
            "price": price,
            "quantity": quantity,
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
            resp = await self._post_order_with_algo_fallback(params)
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
            resp = await self._post_order_with_algo_fallback(params)
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
        time_in_force: str = "GTC",  # EP-01.4-INT-A: Parametrized, supports GTX
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
            time_in_force: Time in force (GTC, GTX/post-only, IOC, FOK). Default GTC.

        Returns:
            Order response.
        """
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": time_in_force,  # EP-01.4-INT-A: Use parameter, not hardcoded
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
        # httpx.Response.json() is synchronous, but some tests mock it as async.
        return await _coerce_json(resp)
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
