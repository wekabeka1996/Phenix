import pytest
import asyncio
from pathlib import Path
from backtest_engine.data_processing.htf_provider import HTFHistoryProvider

@pytest.mark.asyncio
async def test_htf_provider_fetch_and_cache(tmp_path):
    provider = HTFHistoryProvider(cache_dir=str(tmp_path))
    
    # Arbitrary anchor: Dec 31, 2023 23:59:59.999 UTC
    anchor_ms = 1704067199999
    
    # 1. Fetch from API
    res1 = await provider.get_klines("BTCUSDT", 86400, anchor_ms, 5)
    assert len(res1) > 0
    assert "open_ts" in res1[0]
    assert "c" in res1[0]
    
    # Ensure cache file is created
    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1
    
    # 2. Fetch again, should hit cache
    res2 = await provider.get_klines("BTCUSDT", 86400, anchor_ms, 5)
    assert len(res2) == len(res1)
    assert res2[-1]["open_ts"] == res1[-1]["open_ts"]
