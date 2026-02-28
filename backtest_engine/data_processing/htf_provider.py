import logging
import json
import hashlib
from pathlib import Path
from typing import List, Optional
import aiohttp
import asyncio

logger = logging.getLogger(__name__)

class HTFHistoryProvider:
    """
    Lightweight, unauthenticated REST client for pulling historical HTF klines
    directly from Binance fAPI (Futures). Includes local file caching to prevent
    DDoS-ing the Binance API on repeated runs.
    """
    
    BASE_URL = "https://fapi.binance.com"
    
    def __init__(self, cache_dir: str = "data/processed/htf_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
    def _tf_sec_to_interval(self, tf_sec: int) -> str:
        mapping = {
            60: "1m", 180: "3m", 300: "5m", 900: "15m", 1800: "30m",
            3600: "1h", 7200: "2h", 14400: "4h", 28800: "8h",
            43200: "12h", 86400: "1d"
        }
        interval = mapping.get(tf_sec)
        if not interval:
            raise ValueError(f"Unsupported timeframe in HTFHistoryProvider: {tf_sec}")
        return interval

    def _get_cache_path(self, symbol: str, interval: str, end_time_ms: int, limit: int) -> Path:
        key_str = f"{symbol}_{interval}_{end_time_ms}_{limit}"
        hashed = hashlib.md5(key_str.encode()).hexdigest()
        return self.cache_dir / f"{symbol}_{interval}_{hashed}.json"

    def _read_cache(self, cache_path: Path) -> Optional[List[dict]]:
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read HTF cache {cache_path}: {e}")
        return None

    def _write_cache(self, cache_path: Path, data: List[dict]) -> None:
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to write HTF cache {cache_path}: {e}")

    async def get_klines(self, symbol: str, tf_sec: int, end_time_ms: int, limit: int) -> List[dict]:
        """
        Fetch historical klines from Binance and return them in a parsed dict format.
        Returns empty list if API fails.
        """
        interval = self._tf_sec_to_interval(tf_sec)
        cache_path = self._get_cache_path(symbol, interval, end_time_ms, limit)
        
        cached_data = self._read_cache(cache_path)
        if cached_data is not None:
            logger.debug(f"HTFHistoryProvider: Cache hit for {symbol} {interval} ending at {end_time_ms}")
            return cached_data
            
        url = f"{self.BASE_URL}/fapi/v1/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "endTime": end_time_ms,
            "limit": limit
        }
        
        logger.info(f"HTFHistoryProvider: Fetching {limit} {interval} bars for {symbol} ending at {end_time_ms}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        err_txt = await response.text()
                        logger.error(f"Binance API error {response.status}: {err_txt}")
                        return []
                    
                    raw_klines = await response.json()
                    
                    # Parse to standard dict
                    parsed = []
                    for k in raw_klines:
                        parsed.append({
                            "open_ts": int(k[0]),
                            "o": float(k[1]),
                            "h": float(k[2]),
                            "l": float(k[3]),
                            "c": float(k[4]),
                            "v": float(k[5])
                        })
                        
                    self._write_cache(cache_path, parsed)
                    return parsed
        except Exception as e:
            logger.error(f"HTFHistoryProvider: exception fetching {symbol} {interval}: {e}")
            return []
