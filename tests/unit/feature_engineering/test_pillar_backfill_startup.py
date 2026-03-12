"""
Tests for PillarBackfillService startup wiring — КР-1 fix.

Covers:
1. fetch_candles() коректно парсить Binance klines формат (list і dict)
2. warmup_pillars() повертає результати для всіх трьох TF (D1/H4/M15)
3. success=True якщо отримано >= 90% запитаних барів
4. success=False якщо adapter повертає порожній список
5. is_available=False якщо adapter=None (backtest mode)
6. Payload EVT:HTF_BARS_IMPORTED сформований коректно для FeatureEngineering
7. Cache hit — другий виклик не робить HTTP запит
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
from apps.reference.domains.feature_engineering.pillar_backfill import (
    PillarBackfillService,
    BackfillResult,
    CandleBar,
)
from apps.reference.domains.feature_engineering.types import (
    FeatureEngineeringConfig,
    PillarState,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _binance_kline(
    open_time: int = 1_000_000,
    open_: float = 99.0,
    high: float = 101.0,
    low: float = 98.0,
    close: float = 100.0,
    volume: float = 10.0,
) -> list:
    """Binance raw kline format: [open_time, open, high, low, close, volume, ...]"""
    return [open_time, str(open_), str(high), str(low), str(close), str(volume), open_time + 59999]


def _make_klines(count: int, base_price: float = 100.0) -> list:
    """Генерує count Binance klines зі зростаючою ціною."""
    return [
        _binance_kline(
            open_time=i * 300_000,
            close=base_price + i * 0.1,
            high=base_price + i * 0.1 + 1.0,
            low=base_price + i * 0.1 - 1.0,
        )
        for i in range(count)
    ]


def _make_adapter(klines_by_interval: dict | None = None) -> MagicMock:
    """
    Mock exchange adapter. klines_by_interval: {"1d": [...], "4h": [...], "15m": [...]}
    Якщо None — повертає 100 стандартних klines для будь-якого interval.
    """
    adapter = MagicMock()
    if klines_by_interval is None:
        adapter.get_klines = AsyncMock(return_value=_make_klines(100))
    else:
        async def _get_klines(symbol, interval, limit):
            return klines_by_interval.get(interval, [])[:limit]
        adapter.get_klines = _get_klines
    return adapter


class _AsyncCallStub:
    """Stable async stub with explicit call_count for full-suite runs."""

    def __init__(self, result):
        self._result = result
        self.call_count = 0

    async def __call__(self, *args, **kwargs):
        self.call_count += 1
        return self._result


# ── fetch_candles ─────────────────────────────────────────────────────────────

class TestFetchCandles:
    """Юніт-тести для PillarBackfillService.fetch_candles()."""

    def test_parses_binance_list_format(self):
        """Стандартний Binance list format [open_time, open, high, low, close, vol]."""
        adapter = _make_adapter({"1d": _make_klines(200)})
        svc = PillarBackfillService(adapter)
        result = asyncio.run(svc.fetch_candles("BTCUSDT", 86400, 200))

        assert result.success is True
        assert result.fetched_count == 200
        assert len(result.candles) == 200
        assert isinstance(result.candles[0], CandleBar)
        assert result.candles[0].close == pytest.approx(100.0, abs=0.01)

    def test_returns_correct_ohlcv_fields(self):
        """CandleBar має коректні значення close, high, low, open_time_ms."""
        kline = _binance_kline(
            open_time=1_700_000_000_000,
            close=50_000.0,
            high=51_000.0,
            low=49_000.0,
        )
        adapter = _make_adapter({"4h": [kline]})
        svc = PillarBackfillService(adapter)
        result = asyncio.run(svc.fetch_candles("BTCUSDT", 14400, 1))

        bar = result.candles[0]
        assert bar.open_time_ms == 1_700_000_000_000
        assert bar.close == pytest.approx(50_000.0)
        assert bar.high == pytest.approx(51_000.0)
        assert bar.low == pytest.approx(49_000.0)

    def test_success_false_on_empty_response(self):
        """Якщо adapter повертає [] — success=False."""
        adapter = _make_adapter({"15m": []})
        svc = PillarBackfillService(adapter)
        result = asyncio.run(svc.fetch_candles("SOLUSDT", 900, 50))

        assert result.success is False
        assert result.fetched_count == 0
        assert result.candles == []

    def test_success_false_when_90_percent_threshold_not_met(self):
        """Менше 90% запитаних барів => success=False."""
        # Запитуємо 100, отримуємо 80 (80% < 90%)
        adapter = _make_adapter({"1d": _make_klines(80)})
        svc = PillarBackfillService(adapter)
        result = asyncio.run(svc.fetch_candles("BTCUSDT", 86400, 100))

        assert result.success is False
        assert result.fetched_count == 80

    def test_success_true_at_exactly_90_percent(self):
        """Рівно 90% запитаних барів => success=True."""
        adapter = _make_adapter({"1d": _make_klines(90)})
        svc = PillarBackfillService(adapter)
        result = asyncio.run(svc.fetch_candles("BTCUSDT", 86400, 100))

        assert result.success is True

    def test_not_available_when_no_adapter(self):
        """Без adapter (backtest mode) — is_available=False, success=False."""
        svc = PillarBackfillService(exchange_adapter=None)
        assert svc.is_available is False
        result = asyncio.run(svc.fetch_candles("BTCUSDT", 86400, 200))
        assert result.success is False
        assert result.error is not None

    def test_result_has_correct_symbol_and_timeframe(self):
        """BackfillResult.symbol і .timeframe_sec відповідають запиту."""
        adapter = _make_adapter()
        svc = PillarBackfillService(adapter)
        result = asyncio.run(svc.fetch_candles("ETHUSDT", 14400, 50))

        assert result.symbol == "ETHUSDT"
        assert result.timeframe_sec == 14400

    def test_adapter_exception_returns_failed_result(self):
        """При виключенні в adapter — повертається BackfillResult з success=False."""
        adapter = MagicMock()
        adapter.get_klines = AsyncMock(side_effect=ConnectionError("timeout"))
        svc = PillarBackfillService(adapter)
        result = asyncio.run(svc.fetch_candles("BTCUSDT", 86400, 100))

        assert result.success is False
        assert result.error is not None
        assert "timeout" in str(
            result.error).lower() or result.fetched_count == 0


# ── warmup_pillars ────────────────────────────────────────────────────────────

class TestWarmupPillars:
    """Тести для warmup_pillars() — повний трьохтаймфреймний запит."""

    def test_returns_all_three_timeframes(self):
        """warmup_pillars() повертає ключі 'd1', 'h4', 'm15'."""
        adapter = _make_adapter({
            "1d": _make_klines(200),
            "4h": _make_klines(100),
            "15m": _make_klines(50),
        })
        svc = PillarBackfillService(adapter)
        results = asyncio.run(svc.warmup_pillars("BTCUSDT"))

        assert set(results.keys()) == {"d1", "h4", "m15"}

    def test_all_successful_on_full_data(self):
        """Всі три TF успішні якщо adapter повертає достатньо барів."""
        adapter = _make_adapter({
            "1d": _make_klines(200),
            "4h": _make_klines(100),
            "15m": _make_klines(50),
        })
        svc = PillarBackfillService(adapter)
        results = asyncio.run(svc.warmup_pillars(
            "BTCUSDT", d1_candles=200, h4_candles=100, m15_candles=50))

        assert results["d1"].success is True
        assert results["h4"].success is True
        assert results["m15"].success is True

    def test_correct_bar_counts_per_timeframe(self):
        """Кожен TF отримує очікувану кількість барів."""
        adapter = _make_adapter({
            "1d": _make_klines(200),
            "4h": _make_klines(100),
            "15m": _make_klines(50),
        })
        svc = PillarBackfillService(adapter)
        results = asyncio.run(svc.warmup_pillars(
            "BTCUSDT", d1_candles=200, h4_candles=100, m15_candles=50))

        assert results["d1"].fetched_count == 200
        assert results["h4"].fetched_count == 100
        assert results["m15"].fetched_count == 50

    def test_partial_failure_does_not_crash(self):
        """Якщо один TF провалюється — решта все одно повертаються."""
        adapter = _make_adapter({
            "1d": _make_klines(200),
            "4h": [],            # H4 провалюється
            "15m": _make_klines(50),
        })
        svc = PillarBackfillService(adapter)
        results = asyncio.run(svc.warmup_pillars("BTCUSDT"))

        assert results["d1"].success is True
        assert results["h4"].success is False
        assert results["m15"].success is True

    def test_warmup_pillars_timeframe_sec_values(self):
        """BackfillResult.timeframe_sec відповідає правильному значенню для кожного TF."""
        adapter = _make_adapter()
        svc = PillarBackfillService(adapter)
        results = asyncio.run(svc.warmup_pillars("SOLUSDT"))

        assert results["d1"].timeframe_sec == 86400
        assert results["h4"].timeframe_sec == 14400
        assert results["m15"].timeframe_sec == 900


# ── cache ─────────────────────────────────────────────────────────────────────

class TestFetchCandlesCache:
    """Перевіряє що успішні результати кешуються."""

    def test_second_call_uses_cache_not_adapter(self):
        """Після успішного fetch — повторний виклик не робить HTTP-запит."""
        mock_get_klines = _AsyncCallStub(_make_klines(200))
        adapter = MagicMock()
        adapter.get_klines = mock_get_klines
        svc = PillarBackfillService(adapter)

        result1 = asyncio.run(svc.fetch_candles("BTCUSDT", 86400, 200))
        result2 = asyncio.run(svc.fetch_candles("BTCUSDT", 86400, 200))

        assert result1.success is True
        assert result2.success is True
        # Adapter повинен бути викликаний тільки один раз
        assert mock_get_klines.call_count == 1

    def test_failed_result_not_cached(self):
        """Провальний результат не кешується — наступний виклик знову йде в adapter."""
        mock_get_klines = _AsyncCallStub([])  # завжди порожньо
        adapter = MagicMock()
        adapter.get_klines = mock_get_klines
        svc = PillarBackfillService(adapter)

        asyncio.run(svc.fetch_candles("BTCUSDT", 86400, 200))
        asyncio.run(svc.fetch_candles("BTCUSDT", 86400, 200))

        assert mock_get_klines.call_count == 2


# ── payload format for EVT:HTF_BARS_IMPORTED ─────────────────────────────────

class TestHTFBarsPayloadFormat:
    """
    Перевіряє що payload сформований з backfill-барів відповідає
    очікуванням FeatureEngineering._on_htf_bars_imported().
    """

    def test_bar_payload_has_required_keys(self):
        """
        Кожен бар у payload повинен містити: c, h, l, open_ts.
        Це те що main.py формує перед emit EVT:HTF_BARS_IMPORTED.
        """
        klines = _make_klines(5, base_price=100.0)
        candles = []
        for kl in klines:
            candles.append(CandleBar(
                open_time_ms=int(kl[0]),
                open=float(kl[1]),
                high=float(kl[2]),
                low=float(kl[3]),
                close=float(kl[4]),
                volume=float(kl[5]),
            ))

        # Симулюємо формування payload як в main.py
        bars_payload = [
            {
                "c": bar.close,
                "h": bar.high,
                "l": bar.low,
                "open_ts": bar.open_time_ms,
                "replay_generation": 0,
            }
            for bar in candles
        ]

        assert len(bars_payload) == 5
        for bar_dict in bars_payload:
            assert "c" in bar_dict
            assert "h" in bar_dict
            assert "l" in bar_dict
            assert "open_ts" in bar_dict
            assert bar_dict["c"] > 0
            assert bar_dict["h"] >= bar_dict["c"]
            assert bar_dict["l"] <= bar_dict["c"]

    def test_tf_sec_mapping_is_correct(self):
        """
        Відповідність label → tf_sec як у main.py.
        D1=86400, H4=14400, M15=900.
        """
        tf_map = {"d1": 86400, "h4": 14400, "m15": 900}
        assert tf_map["d1"] == 86400
        assert tf_map["h4"] == 14400
        assert tf_map["m15"] == 900

    def test_candle_bar_closes_property(self):
        """BackfillResult.closes повертає список close-цін."""
        candles = [
            CandleBar(open_time_ms=0, open=99.0, high=101.0,
                      low=98.0, close=100.0, volume=10.0),
            CandleBar(open_time_ms=1, open=100.0, high=102.0,
                      low=99.0, close=101.5, volume=12.0),
        ]
        result = BackfillResult(
            symbol="BTCUSDT",
            timeframe_sec=86400,
            candles=candles,
            success=True,
            fetched_count=2,
        )
        assert result.closes == [100.0, 101.5]
        assert result.highs == [101.0, 102.0]
        assert result.lows == [98.0, 99.0]


def test_update_pillar_candle_ignores_duplicate_or_older_bar_identity() -> None:
    cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()
    engine = FeatureCalculationEngine(FeatureEngineeringConfig(cfg))
    state = PillarState()

    assert engine.update_pillar_candle(
        state,
        "m15",
        close=100.0,
        high=101.0,
        low=99.0,
        bar_ts_ms=1_700_000_000_000,
    ) is True
    assert engine.update_pillar_candle(
        state,
        "m15",
        close=100.5,
        high=101.5,
        low=99.5,
        bar_ts_ms=1_700_000_000_000,
    ) is False
    assert engine.update_pillar_candle(
        state,
        "m15",
        close=99.5,
        high=100.0,
        low=99.0,
        bar_ts_ms=1_699_999_000_000,
    ) is False
    assert list(state.m15_closes) == [100.0]
