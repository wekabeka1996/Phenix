"""
PriceService: Single Source of Truth for prices across domains.

Provides unified price access with caching, fallback chain, and metrics.
Eliminates fragmentation between mark/last/mid price sources.
"""

from __future__ import annotations
import asyncio
from typing import Optional, Literal
import time
from dataclasses import dataclass
from typing import Optional, Dict, Tuple, Literal
from decimal import Decimal
import logging

LOG = logging.getLogger(__name__)


@dataclass
class PriceQuote:
    symbol: str
    mark: Optional[float]
    last: Optional[float]
    mid: Optional[float]
    ts: int  # epoch milliseconds
    source: Literal["MARK", "LAST", "MID", "NONE"]


class FallbackExhaustedError(Exception):
    """All price sources (MARK/LAST/MID) returned None."""
    pass


class PriceService:
    """
    Single Source of Truth for prices.

    Additive implementation: in Wave 0 provides caching, TTL, lazy-fetch, and fallback.
    """

    def __init__(self, adapter, max_cache_size: int = 100):
        self._adapter = adapter
        self._cache: Dict[str, Tuple[PriceQuote, float]] = {}
        self._lock = asyncio.Lock()
        self._max_cache_size = max_cache_size
        LOG.info(
            f"PriceService initialized with max_cache_size={max_cache_size}")

    async def get_mark(self, symbol: str, ttl_ms: int = 250) -> PriceQuote:
        # Prefer cache if not expired and contains mark
        start_time = time.time()
        current_ts = int(start_time * 1000)
        async with self._lock:
            if symbol in self._cache:
                quote, expire_ts = self._cache[symbol]
                if ttl_ms != 0 and current_ts < expire_ts and quote.mark is not None:
                    return PriceQuote(**{**quote.__dict__, "source": "MARK"})

        # Try to fetch mark directly; in case of adapter exception, return stale cache if available
        try:
            mark_result = await self._adapter.get_mark_price(symbol)
            mark = float(mark_result) if mark_result is not None else None
        except Exception as e:
            LOG.warning(f"[{symbol}] mark fetch failed: {e}")
            # stale-while-revalidate: return expired cache if available
            async with self._lock:
                if symbol in self._cache:
                    quote, _ = self._cache[symbol]
                    if quote.mark is not None:
                        LOG.warning(
                            f"[{symbol}] Returning stale mark cache due to adapter error")
                        return PriceQuote(**{**quote.__dict__, "source": "MARK"})
            # No stale cache available
            raise

        if mark is not None:
            quote = PriceQuote(symbol=symbol, mark=mark, last=None,
                               mid=None, ts=current_ts, source="MARK")
            expire_ts = current_ts + ttl_ms
            async with self._lock:
                self._cache[symbol] = (quote, expire_ts)
                # LRU eviction if cache too large
                if len(self._cache) > self._max_cache_size:
                    oldest_symbol = min(self._cache.keys(),
                                        key=lambda s: self._cache[s][1])
                    del self._cache[oldest_symbol]
            return quote

        # If mark is None: serve stale if exists, otherwise raise
        async with self._lock:
            if symbol in self._cache:
                quote, _ = self._cache[symbol]
                if quote.mark is not None:
                    return PriceQuote(**{**quote.__dict__, "source": "MARK"})
        raise FallbackExhaustedError(f"No mark price for {symbol}")

    async def get_last(self, symbol: str, ttl_ms: int = 250) -> PriceQuote:
        quote = await self._get_cached_or_fetch(symbol, ttl_ms)
        if quote.last is not None:
            return PriceQuote(**{**quote.__dict__, "source": "LAST"})
        raise FallbackExhaustedError(f"No last price for {symbol}")

    async def get_mid(self, symbol: str, ttl_ms: int = 250) -> PriceQuote:
        quote = await self._get_cached_or_fetch(symbol, ttl_ms)
        if quote.mid is not None:
            return PriceQuote(**{**quote.__dict__, "source": "MID"})
        raise FallbackExhaustedError(f"No mid price for {symbol}")

    async def get_current(self, symbol: str, working_type: str = "MARK", ttl_ms: int = 250) -> PriceQuote:
        quote = await self._get_cached_or_fetch(symbol, ttl_ms)
        fallback_orders = {
            "MARK": ("mark", "last", "mid"),
            "LAST": ("last", "mark", "mid"),
            "MID": ("mid", "mark", "last"),
        }
        order = fallback_orders.get(working_type, ("mark", "last", "mid"))
        for attr in order:
            value = getattr(quote, attr)
            if value is not None:
                LOG.debug(f"[{symbol}] Fallback: {working_type} -> {attr}")
                return PriceQuote(**{**quote.__dict__, "source": attr.upper()})
        raise FallbackExhaustedError(f"No price available for {symbol}")

    async def _get_cached_or_fetch(self, symbol: str, ttl_ms: int) -> PriceQuote:
        start_time = time.time()
        current_ts = int(start_time * 1000)
        async with self._lock:
            if symbol in self._cache:
                quote, expire_ts = self._cache[symbol]
                if ttl_ms != 0 and current_ts < expire_ts:
                    LOG.debug(f"[{symbol}] Cache HIT")
                    return quote
        try:
            quote = await self._fetch_from_adapter(symbol)
            expire_ts = current_ts + ttl_ms
            async with self._lock:
                self._cache[symbol] = (quote, expire_ts)
                if len(self._cache) > self._max_cache_size:
                    # evict oldest
                    oldest = min(self._cache.keys(),
                                 key=lambda s: self._cache[s][1])
                    del self._cache[oldest]
            return quote
        except Exception as e:
            LOG.error(f"[{symbol}] Adapter fetch error: {e}")
            # stale-while-revalidate
            async with self._lock:
                if symbol in self._cache:
                    quote, _ = self._cache[symbol]
                    LOG.warning(
                        f"[{symbol}] Using stale cache due to adapter error")
                    return quote
            raise

    async def _fetch_from_adapter(self, symbol: str) -> PriceQuote:
        try:
            mark = None
            last = None
            try:
                mark_result = await self._adapter.get_mark_price(symbol)
                mark = float(mark_result) if mark_result is not None else None
            except Exception as e:
                LOG.warning(f"[{symbol}] mark fetch failed: {e}")
            if mark is None:
                try:
                    last_result = await self._adapter.get_last_price(symbol)
                    last = float(
                        last_result) if last_result is not None else None
                except Exception as e:
                    LOG.warning(f"[{symbol}] last fetch failed: {e}")
            mid = None
            return PriceQuote(symbol=symbol, mark=mark, last=last, mid=mid, ts=int(time.time() * 1000), source=("MARK" if mark else ("LAST" if last else "NONE")))
        except Exception:
            raise

    def clear_cache(self, symbol: Optional[str] = None):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                LOG.warning(
                    "clear_cache called from running loop, may cause deadlock")
        except RuntimeError:
            pass
        if symbol:
            self._cache.pop(symbol, None)
            LOG.debug(f"Cache cleared for {symbol}")
        else:
            self._cache.clear()
            LOG.debug("Cache cleared for all symbols")


"""
PriceService (v0, additive-only)

Single Source of Truth for prices across domains. Provides read-through
cache semantics over exchange adapters and exposes a consistent contract.

Note: This is a skeleton for Wave 0. No runtime wiring yet.
"""


PriceSource = Literal["MARK", "LAST", "MID"]


@dataclass(frozen=True)
class PriceQuote:
    symbol: str
    mark: Optional[float]
    last: Optional[float]
    mid: Optional[float]
    ts: int  # epoch ms
    source: PriceSource


class PriceServiceSync:
    """Synchronous wrapper around async PriceService for use in synchronous
    code paths (Wave 0). This will run async methods in a blocking fashion.

    Contract:
      - get_mark(symbol, ttl_ms=250) -> PriceQuote
      - get_last(symbol, ttl_ms=250) -> PriceQuote
      - get_mid(symbol, ttl_ms=250) -> PriceQuote
      - get_current(symbol, working_type="MARK", ttl_ms=250) -> PriceQuote
    """

    def __init__(self, async_service: Optional[PriceService] = None, adapter=None, max_cache_size: int = 100) -> None:
        # In-memory cache: symbol -> (PriceQuote, expiry_ms)
        # If an async service is provided, reuse it; otherwise build one
        if async_service is not None:
            self._async = async_service
        else:
            # If adapter provided, initialize async PriceService
            self._async = PriceService(adapter, max_cache_size=max_cache_size)

    # Public API -----------------------------------------------------------
    def get_mark(self, symbol: str, ttl_ms: int = 250) -> PriceQuote:
        return asyncio.run(self._async.get_mark(symbol, ttl_ms=ttl_ms))

    def get_last(self, symbol: str, ttl_ms: int = 250) -> PriceQuote:
        return asyncio.run(self._async.get_last(symbol, ttl_ms=ttl_ms))

    def get_mid(self, symbol: str, ttl_ms: int = 250) -> PriceQuote:
        return asyncio.run(self._async.get_mid(symbol, ttl_ms=ttl_ms))

    def get_current(self, symbol: str, working_type: PriceSource = "MARK", ttl_ms: int = 250) -> PriceQuote:
        """
        Retrieve a price according to policy. Fallback order (v0): MARK -> LAST -> MID.
        """
        try_order: tuple[PriceSource, ...] = {
            "MARK": ("MARK", "LAST", "MID"),
            "LAST": ("LAST", "MARK", "MID"),
            "MID": ("MID", "MARK", "LAST"),
        }[working_type]
        last_exc: Optional[Exception] = None
        # Blocking call to async get_current using the desired type
        return asyncio.run(self._async.get_current(symbol, working_type=working_type, ttl_ms=ttl_ms))
        if last_exc:
            raise last_exc
        # No data found; return an empty quote with current timestamp
        return PriceQuote(symbol=symbol, mark=None, last=None, mid=None, ts=_now_ms(), source=working_type)

    # Internal ------------------------------------------------------------
    def _get(self, symbol: str, kind: PriceSource, ttl_ms: int) -> PriceQuote:
        # Serve from cache if not expired and source matches requested kind
        cached = self._cache.get(symbol)
        now_ms = _now_ms()
        if cached is not None:
            quote, expiry = cached
            if now_ms <= expiry and quote is not None:
                return quote

        # Placeholder: fetch from adapter (to be wired in Wave 0)
        # For now, return an empty quote noting the requested kind.
        quote = PriceQuote(symbol=symbol, mark=None, last=None,
                           mid=None, ts=now_ms, source=kind)
        self._cache[symbol] = (quote, now_ms + ttl_ms)
        return quote


def _now_ms() -> int:
    return int(time.time() * 1000)
