"""Tests for BarAggregator.inject_historical_bar() — STARTUP-BASIS-HYDRATION."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from apps.reference.domains.market_data.bar_aggregator import BarAggregator
from apps.reference.domains.feature_engineering.bar_resampler import Bar
from apps.reference.contracts.runtime_bar_identity import RuntimeBarSourceMode


def _make_bar(
    symbol: str = "BTCUSDT",
    tf_sec: int = 300,
    start_ts_ms: int = 1_700_000_000_000,
) -> Bar:
    tf_ms = tf_sec * 1000
    return Bar(
        symbol=symbol,
        timeframe_sec=tf_sec,
        open=Decimal("40000"),
        high=Decimal("40500"),
        low=Decimal("39800"),
        close=Decimal("40200"),
        volume=Decimal("12.5"),
        trade_count=1,
        start_ts_ms=start_ts_ms,
        end_ts_ms=start_ts_ms + tf_ms - 1,
    )


class TestInjectHistoricalBar:
    def test_emits_bar_closed_with_warmup_import_source_mode(self):
        """inject_historical_bar emits EVT:BAR_CLOSED with source_mode=warmup_import."""
        emit_spy = MagicMock()
        agg = BarAggregator(timeframes_sec=[300], emit_fn=emit_spy)
        bar = _make_bar()

        agg.inject_historical_bar(bar)

        assert emit_spy.call_count == 1
        event_name, payload = emit_spy.call_args[0][0], emit_spy.call_args[0][1]
        assert event_name == "EVT:BAR_CLOSED"
        assert payload.get("source_mode") == RuntimeBarSourceMode.WARMUP_IMPORT.value

    def test_does_not_write_to_wal(self):
        """inject_historical_bar must NOT write to WAL — WARMUP_IMPORT bars are not live events."""
        emit_spy = MagicMock()
        agg = BarAggregator(timeframes_sec=[300], emit_fn=emit_spy)
        bar = _make_bar()

        with patch("apps.reference.domains.market_data.bar_aggregator.wal") as wal_mock:
            agg.inject_historical_bar(bar)
            assert wal_mock.append.call_count == 0, (
                "WARMUP_IMPORT bars must not be appended to WAL — "
                "they are historical basis bars, not live events"
            )

    def test_live_bar_closed_still_writes_to_wal(self):
        """WAL guard does not affect normal live BAR_CLOSED writes."""
        emit_spy = MagicMock()
        agg = BarAggregator(timeframes_sec=[300], emit_fn=emit_spy)

        with patch("apps.reference.domains.market_data.bar_aggregator.wal") as wal_mock:
            base_ts = 1_800_000_000_000  # aligned to 300s boundary
            agg.on_tick("BTCUSDT", Decimal("40000"), Decimal("1.0"), base_ts + 1)
            agg.on_tick("BTCUSDT", Decimal("40100"), Decimal("1.0"), base_ts + 300_001)

            assert wal_mock.append.call_count == 1

    def test_stores_bar_in_completed_bars(self):
        """inject_historical_bar stores the bar in _completed_bars for query methods."""
        agg = BarAggregator(timeframes_sec=[300], emit_fn=MagicMock())
        bar = _make_bar()

        agg.inject_historical_bar(bar)

        completed = agg.get_completed_bars("BTCUSDT", 300)
        assert len(completed) == 1
        assert completed[0] is bar

    def test_updates_last_ts_boundary(self):
        """inject_historical_bar advances _last_ts so subsequent live ticks are not OOO."""
        agg = BarAggregator(timeframes_sec=[300], emit_fn=MagicMock())
        bar = _make_bar(start_ts_ms=1_700_000_000_000)

        agg.inject_historical_bar(bar)

        key = ("BTCUSDT", 300)
        assert agg._last_ts.get(key, 0) >= bar.end_ts_ms

    def test_live_tick_after_inject_is_not_ooo_dropped(self):
        """A live tick with ts > bar.end_ts_ms is processed normally after inject."""
        emit_spy = MagicMock()
        agg = BarAggregator(timeframes_sec=[300], emit_fn=emit_spy)
        bar = _make_bar(start_ts_ms=1_700_000_000_000)

        agg.inject_historical_bar(bar)
        emit_spy.reset_mock()

        live_ts = bar.end_ts_ms + 300_000 + 1
        agg.on_tick("BTCUSDT", Decimal("40300"), Decimal("1.0"), live_ts)

        metrics = agg.get_metrics()
        assert metrics["ticks_dropped_ooo"] == 0
