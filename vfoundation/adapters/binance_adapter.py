"""
vFoundation Binance Adapter

A centralized, asynchronous adapter for interacting with the Binance Futures REST API.
It handles API key signing, endpoint selection (live/testnet), and error handling.
This adapter is designed to be instantiated by domain services with a specific
environment configuration, ensuring a clean separation of concerns.
"""

import json as _json
import asyncio
import hashlib
import hmac
import logging
import time
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, quote_plus

import httpx

LOG = logging.getLogger(__name__)
# забезпечуємо саме таку змінну, яку патчить тест
log = logging.getLogger(__name__)


# +++ add near imports


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


class BinanceAdapter:
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

        # NEW: time sync state
        self._time_offset_ms = 0
        self._last_time_sync_monotonic = 0.0
        self._time_sync_lock = asyncio.Lock()
        # recvWindow (ms). Для ф'ючерсів максимум 60000.
        self._recv_window_ms = int(self.config.get("recv_window_ms", 20000))

        # Сумісність із тестами: публічне поле .session завжди існує
        self.session: httpx.AsyncClient = session or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self._timeout,
            headers={"X-MBX-APIKEY": self.api_key},
        )

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
        ttl_sec = int(self.config.get("time_sync_ttl_sec", 120))
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

        # Готуємо одразу "базові" params (без підпису) для можливого ретраю
        base_params = dict(params)

        async def _do(method: str, base_params: dict):
            if signed:
                await self._sync_time(False)
                qs, final_params = self._sign_build(base_params)
                # ВИКОРИСТОВУЄМО self.session — щоб тести могли мокати її
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
                return await _coerce_json(r)        # 1-й запит
        try:
            return await _do(method, base_params)
        except Exception as e:
            # Якщо -1021 → жорстка синхронізація і другий запит з НОВОГО base_params
            msg = str(e)
            if "code': -1021" in msg or "-1021" in msg:
                await self._sync_time(True)
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

    # --- Public API Methods ---

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

    async def create_order(self, order_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new order.

        Args:
            order_params: A dictionary containing order parameters like
                          symbol, side, type, quantity, price, etc.

        Returns:
            The response from the order creation endpoint.
        """
        path = "/fapi/v1/order"
        return await self._request("POST", path, order_params)

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

    async def quantize_quantity(self, symbol: str, qty: Any) -> str:
        """
        Quantize quantity to symbol's LOT_SIZE stepSize and validate MIN_NOTIONAL.
        Returns string suitable for API submission.
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
        return await self.create_order(params)

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
        return await self.create_order(params)

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
        return await self.create_order(params)

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
        return await self.create_order(params)

    async def get_account_balance(self) -> list:
        """
        Get account balance information.

        Returns:
            A list of asset balances.
        """
        path = "/fapi/v2/balance"
        return await self._request("GET", path)

    async def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """
        Get open orders.

        Args:
            symbol: Optional symbol filter.

        Returns:
            List of open orders.
        """
        path = "/fapi/v1/openOrders"
        params = {}
        if symbol:
            params["symbol"] = symbol
        return await self._request("GET", path, params)

    async def get_mark_price(self, symbol: str, ttl_ms: int = 250) -> float:
        """
        Get the mark price for a symbol with TTL cache.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT').
            ttl_ms: Time-to-live in milliseconds for cache.

        Returns:
            The mark price as float.
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

    async def get_exchange_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get exchange information for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT').

        Returns:
            Exchange info dict containing filters.
        """
        path = "/fapi/v1/exchangeInfo"
        params = {"symbol": symbol}
        return await self._request("GET", path, params)

    async def get_last_price(self, symbol: str) -> float:
        """
        Get the last price for a symbol (fallback for mark price).

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT').

        Returns:
            The last price as float.
        """
        path = "/fapi/v1/ticker/price"
        params = {"symbol": symbol}
        response = await self._request("GET", path, params)
        return float(response["price"])

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

    async def create_take_profit_market_order(self, order_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a TAKE_PROFIT_MARKET order.

        Args:
            order_params: Order parameters.

        Returns:
            Order response.
        """
        path = "/fapi/v1/order"
        return await self._request("POST", path, order_params)

    async def get_open_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        USDT-M Futures: повертає тільки відкриті (non-zero) позиції.
        Працює і в ONE_WAY (positionSide='BOTH'), і в HEDGE (LONG/SHORT).

        Args:
            symbol: Optional trading pair symbol (e.g., 'BTCUSDT').

        Returns:
            A list of open position data.
        """
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol

        # signed GET /fapi/v2/positionRisk
        raw = await self._request("GET", "/fapi/v2/positionRisk", params)

        positions: List[Dict[str, Any]] = []
        for p in raw:
            # Binance віддає числа як строки — зберігаємо precision, конвертуємо тільки коли потрібно
            amt_str = p.get("positionAmt", "0")
            amt = float(amt_str)
            if abs(amt) <= 0.0:
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

            positions.append(
                {
                    "symbol": p.get("symbol"),
                    "positionSide": pos_side,  # BOTH/LONG/SHORT
                    "side": side,  # LONG/SHORT (зручно для бізнес-логіки)
                    "positionAmt": amt_str,  # зберігаємо string для precision
                    "entryPrice": entry_str,  # зберігаємо string для precision
                    "markPrice": mark_str,  # зберігаємо string для precision
                    "unRealizedProfit": upnl_str,  # зберігаємо string для precision
                    "leverage": lev,
                    # CROSS/ISOLATED
                    "marginType": p.get("marginType", "cross").upper(),
                    "isolatedMargin": float(p.get("isolatedMargin", "0") or 0),
                    "updateTime": int(p.get("updateTime", 0) or 0),
                    # можна додати інші поля за потреби
                }
            )

        return positions


# ---- helpers ----


async def _safe_read_err(resp):
    try:
        return await resp.json()
    except Exception:
        try:
            return {"code": resp.status_code, "msg": resp.text}
        except Exception:
            return {"code": resp.status_code, "msg": "unknown"}


def _is_code_1021(err) -> bool:
    try:
        return int(err.get("code")) == -1021
    except Exception:
        return False


def _make_binance_error(resp_or_code: Any, msg_or_err: Any = None) -> BinanceAPIError:
    # support both call styles: (_resp, err) and (code, msg)
    if isinstance(resp_or_code, int):
        code = int(resp_or_code)
        msg = str(msg_or_err or "")
    else:
        # try to extract from err/json payload
        err = msg_or_err or {}
        code = None
        if hasattr(err, "get"):
            code = err.get("code") or err.get("errno")
            msg = err.get("msg") or err.get("message") or str(err)
        else:
            msg = str(err)
        try:
            code = int(code) if code is not None else -1
        except Exception:
            code = -1

    # normalized NRR for exchange rejections
    rejection_codes = {-1013, -1021, -2010}
    nrr = "NRR-018" if code in rejection_codes else None

    # ГАРАНТОВАНО для rejection-кодів: викликаємо через модульну змінну log
    if nrr == "NRR-018":
        log.warning(
            "Exchange rejected order: code=%s, msg=%s, nrr_code=%s", code, msg, nrr)

    return BinanceAPIError(code=code, msg=msg, nrr_code=nrr)
