"""
Pillar Backfill Service — D1/H4 Historical Candle Fetch for Live Trading.

Aurora Phase 9: "The Quadratic Brain" — Phase 1.

Problem:
  D1 SMA(200) needs 200 D1 candles. Normal M15 tick warmup of ~1000 bars = 10 days,
  so the Strategist pillar would never become ready in live mode.

Solution:
  In LIVE mode, fetch D1 and H4 historical candles from the exchange API at startup.
  In BACKTEST mode, the resampler handles it from the full dataset (no fetch needed).

If warmup not ready → pillar returns NOT_READY → fail-closed (no trading).

NO FSM, NO events — pure data service.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Sequence

logger = logging.getLogger(__name__)


@dataclass
class CandleBar:
    """Single OHLCV candle bar."""
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class BackfillResult:
    """Result of a backfill fetch operation."""
    symbol: str
    timeframe_sec: int
    candles: list[CandleBar] = field(default_factory=list)
    success: bool = False
    error: Optional[str] = None
    fetched_count: int = 0

    @property
    def closes(self) -> list[float]:
        return [c.close for c in self.candles]

    @property
    def highs(self) -> list[float]:
        return [c.high for c in self.candles]

    @property
    def lows(self) -> list[float]:
        return [c.low for c in self.candles]


class PillarBackfillService:
    """
    Fetches historical D1/H4 candles from exchange API at startup.

    Used ONLY in LIVE mode. Backtest uses resampler on full dataset.

    Usage:
        service = PillarBackfillService(exchange_adapter)
        d1_result = await service.fetch_candles("BTCUSDT", 86400, 200)
        h4_result = await service.fetch_candles("BTCUSDT", 14400, 100)
    """

    def __init__(self, exchange_adapter=None):
        """
        Initialize backfill service.

        Args:
            exchange_adapter: Exchange client with klines/candles API.
                Must implement: get_klines(symbol, interval, limit) -> list[dict]
                If None, backfill is disabled (backtest mode).
        """
        self._exchange = exchange_adapter
        self._cache: dict[tuple[str, int], BackfillResult] = {}

    @property
    def is_available(self) -> bool:
        """Whether backfill is available (exchange adapter present)."""
        return self._exchange is not None

    def _tf_sec_to_interval(self, tf_sec: int) -> str:
        """Convert timeframe seconds to exchange interval string."""
        mapping = {
            60: "1m",
            180: "3m",
            300: "5m",
            900: "15m",
            1800: "30m",
            3600: "1h",
            7200: "2h",
            14400: "4h",
            28800: "8h",
            43200: "12h",
            86400: "1d",
        }
        interval = mapping.get(tf_sec)
        if interval is None:
            raise ValueError(f"Unsupported timeframe: {tf_sec}s")
        return interval

    async def fetch_candles(
        self,
        symbol: str,
        timeframe_sec: int,
        count: int,
    ) -> BackfillResult:
        """
        Fetch historical candles from exchange.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").
            timeframe_sec: Candle timeframe in seconds.
            count: Number of candles to fetch.

        Returns:
            BackfillResult with candles or error.
        """
        cache_key = (symbol, timeframe_sec)

        # Return cached result if available
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if cached.success and cached.fetched_count >= count:
                logger.info(
                    "PILLAR_BACKFILL: Cache hit for %s/%ds (%d candles)",
                    symbol, timeframe_sec, cached.fetched_count,
                )
                return cached

        result = BackfillResult(symbol=symbol, timeframe_sec=timeframe_sec)

        if not self.is_available:
            result.error = "exchange_adapter_not_available"
            logger.warning(
                "PILLAR_BACKFILL: Exchange adapter not available for %s/%ds",
                symbol, timeframe_sec,
            )
            return result

        interval = self._tf_sec_to_interval(timeframe_sec)
        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(
                    "PILLAR_BACKFILL: Fetching %d %s candles for %s (attempt=%d/%d)...",
                    count,
                    interval,
                    symbol,
                    attempt,
                    max_attempts,
                )

                raw_klines = await self._exchange.get_klines(
                    symbol=symbol,
                    interval=interval,
                    limit=count,
                )

                if not raw_klines:
                    result.error = "empty_response"
                    if attempt < max_attempts:
                        logger.warning(
                            "PILLAR_BACKFILL: Empty response for %s/%s (attempt=%d/%d) - retrying",
                            symbol,
                            interval,
                            attempt,
                            max_attempts,
                        )
                        continue
                    logger.warning(
                        "PILLAR_BACKFILL: Empty response for %s/%s",
                        symbol,
                        interval,
                    )
                    return result

                candles = []
                for kline in raw_klines:
                    try:
                        candle = self._parse_kline(kline)
                        candles.append(candle)
                    except (KeyError, ValueError, TypeError) as e:
                        logger.warning(
                            "PILLAR_BACKFILL: Skipping malformed kline: %s", e,
                        )
                        continue

                result.candles = candles
                result.fetched_count = len(candles)
                result.success = len(candles) >= count * 0.9
                result.error = None if result.success else (
                    f"insufficient_candles:{len(candles)}/{count}"
                )

                if result.success:
                    self._cache[cache_key] = result
                    logger.info(
                        "PILLAR_BACKFILL: Fetched %d/%d %s candles for %s (success=%s attempts=%d)",
                        len(candles),
                        count,
                        interval,
                        symbol,
                        result.success,
                        attempt,
                    )
                    return result

                if attempt < max_attempts:
                    logger.warning(
                        "PILLAR_BACKFILL: Insufficient candles for %s/%s (%d/%d attempt=%d/%d) - retrying",
                        symbol,
                        interval,
                        len(candles),
                        count,
                        attempt,
                        max_attempts,
                    )
                    continue

                logger.warning(
                    "PILLAR_BACKFILL: Fetched %d/%d %s candles for %s (success=%s)",
                    len(candles),
                    count,
                    interval,
                    symbol,
                    result.success,
                )
                return result

            except Exception as e:
                result.error = f"fetch_error: {e}"
                if attempt < max_attempts:
                    logger.warning(
                        "PILLAR_BACKFILL: Fetch attempt %d/%d failed for %s/%ds: %s - retrying",
                        attempt,
                        max_attempts,
                        symbol,
                        timeframe_sec,
                        e,
                    )
                    continue
                logger.error(
                    "PILLAR_BACKFILL: Failed to fetch %s/%ds: %s",
                    symbol,
                    timeframe_sec,
                    e,
                    exc_info=True,
                )

        return result

    async def warmup_pillars(
        self,
        symbol: str,
        *,
        d1_candles: int = 200,
        h4_candles: int = 100,
        m15_candles: int = 50,
    ) -> dict[str, BackfillResult]:
        """
        Fetch all pillar candle data at startup.

        Args:
            symbol: Trading pair.
            d1_candles: D1 candles needed for Strategist (SMA200 = 200).
            h4_candles: H4 candles needed for Operator (LinReg+ADX).
            m15_candles: M15 candles needed for Tactician (ROC14).

        Returns:
            Dict with keys "d1", "h4", "m15" → BackfillResult.
        """
        results = {}

        results["d1"] = await self.fetch_candles(symbol, 86400, d1_candles)
        results["h4"] = await self.fetch_candles(symbol, 14400, h4_candles)
        results["m15"] = await self.fetch_candles(symbol, 900, m15_candles)

        # Summary
        ready = all(r.success for r in results.values())
        logger.info(
            "PILLAR_BACKFILL: Warmup for %s complete. D1=%d/%d H4=%d/%d M15=%d/%d ready=%s",
            symbol,
            results["d1"].fetched_count, d1_candles,
            results["h4"].fetched_count, h4_candles,
            results["m15"].fetched_count, m15_candles,
            ready,
        )

        return results

    @staticmethod
    def _parse_kline(kline) -> CandleBar:
        """
        Parse exchange kline response to CandleBar.

        Supports both list format (Binance raw) and dict format.
        """
        if isinstance(kline, (list, tuple)):
            # Binance format: [open_time, open, high, low, close, volume, ...]
            return CandleBar(
                open_time_ms=int(kline[0]),
                open=float(kline[1]),
                high=float(kline[2]),
                low=float(kline[3]),
                close=float(kline[4]),
                volume=float(kline[5]),
            )
        elif isinstance(kline, dict):
            return CandleBar(
                open_time_ms=int(kline.get("open_time", kline.get("openTime", 0))),
                open=float(kline.get("open", 0)),
                high=float(kline.get("high", 0)),
                low=float(kline.get("low", 0)),
                close=float(kline.get("close", 0)),
                volume=float(kline.get("volume", 0)),
            )
        else:
            raise TypeError(f"Unsupported kline format: {type(kline)}")
