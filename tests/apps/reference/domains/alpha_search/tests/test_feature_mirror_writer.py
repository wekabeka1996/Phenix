"""
T4: Feature Mirror Writer Tests
=================================

Tests for apps/reference/domains/alpha_search/runtime/feature_mirror_writer.py
covering TA-plane merge, regime cache, symbol filter, and stats.
"""

import json
from unittest.mock import MagicMock

import pytest

from apps.reference.domains.alpha_search.runtime.feature_mirror_writer import (
    FeatureMirrorWriter,
)


def _make_writer(tmp_path, symbols=None):
    """Create a FeatureMirrorWriter with a mock bus."""
    bus = MagicMock()
    bus.listen = MagicMock()
    output = tmp_path / "alpha_input_v1.jsonl"
    writer = FeatureMirrorWriter(
        event_bus=bus,
        output_path=output,
        symbols=symbols,
    )
    return writer, output, bus


def _feature_event(symbol: str, ts_ms: int, bar_close_ts: int):
    return {
        "pld": {
            "symbol": symbol,
            "features": {"obi": 0.12, "close": 96000.0},
            "tf_sec": 300,
            "bar_close_ts": bar_close_ts,
            "ts": ts_ms,
        }
    }


def _ta_event(symbol: str, ts_ms: int, bar_close_ts: int, *, is_warm: bool = True):
    return {
        "pld": {
            "symbol": symbol,
            "tf_sec": 300,
            "bar_close_ts": bar_close_ts,
            "ts": ts_ms,
            "close": 96000.0,
            "bb_position": 0.3,
            "bb_width": 0.02,
            "rsi_14": 45.0,
            "macd_signal": 0.1,
            "is_warm": is_warm,
        }
    }


@pytest.mark.unit
class TestOnFeatures:
    """Tests for feature/TA merge behaviour."""

    def test_writes_jsonl_after_ta_merge_when_feature_arrives_first(self, tmp_path):
        """Feature event is buffered until the matching TA event arrives."""
        writer, output, _ = _make_writer(tmp_path)

        writer._on_features(_feature_event("BTCUSDT", 1740000000000, 1740000000000))
        assert writer._snapshots_written == 0

        writer._on_ta_features(_ta_event("BTCUSDT", 1740000000000, 1740000000000))

        record = json.loads(output.read_text(encoding="utf-8").strip())
        assert record["symbol"] == "BTCUSDT"
        assert record["features"]["obi"] == 0.12
        assert record["features"]["rsi_14"] == 45.0
        assert record["warmup_status"]["ta_features"] is True

    def test_writes_jsonl_after_ta_merge_when_ta_arrives_first(self, tmp_path):
        """TA-first ordering still produces a merged snapshot."""
        writer, output, _ = _make_writer(tmp_path)

        writer._on_ta_features(_ta_event("BTCUSDT", 1740000000000, 1740000000000, is_warm=False))
        writer._on_features(_feature_event("BTCUSDT", 1740000000000, 1740000000000))

        record = json.loads(output.read_text(encoding="utf-8").strip())
        assert record["features"]["macd_signal"] == 0.1
        assert record["warmup_status"]["ta_features"] is False

    def test_regime_cache_included(self, tmp_path):
        """Cached regime appears in merged output record."""
        writer, output, _ = _make_writer(tmp_path)
        writer._regime_cache["BTCUSDT"] = "TRENDING"

        writer._on_ta_features(_ta_event("BTCUSDT", 1740000000000, 1740000000000))
        writer._on_features(_feature_event("BTCUSDT", 1740000000000, 1740000000000))

        record = json.loads(output.read_text(encoding="utf-8").strip())
        assert record["regime"] == "TRENDING"

    def test_symbol_filter_applied(self, tmp_path):
        """Unallowed symbols skipped on either event plane."""
        writer, _, _ = _make_writer(tmp_path, symbols=["BTCUSDT"])

        writer._on_ta_features(_ta_event("BTCUSDT", 1740000000000, 1740000000000))
        writer._on_features(_feature_event("BTCUSDT", 1740000000000, 1740000000000))
        writer._on_features(_feature_event("ETHUSDT", 1740000000001, 1740000000001))

        assert writer._snapshots_written == 1
        assert writer._snapshots_skipped == 1

    def test_empty_features_skipped(self, tmp_path):
        """No base features means no snapshot."""
        writer, _, _ = _make_writer(tmp_path)
        writer._on_features(
            {
                "pld": {
                    "symbol": "BTCUSDT",
                    "features": {},
                    "tf_sec": 300,
                    "bar_close_ts": 1740000000000,
                    "ts": 1740000000000,
                }
            }
        )
        assert writer._snapshots_skipped == 1
        assert writer._snapshots_written == 0


@pytest.mark.unit
class TestOnRegime:
    """Tests for _on_regime event handler."""

    def test_caches_per_symbol(self, tmp_path):
        """Different symbols have independent regime cache."""
        writer, _, _ = _make_writer(tmp_path)

        writer._on_regime({"pld": {"symbol": "BTCUSDT", "regime": "TRENDING"}})
        writer._on_regime({"pld": {"symbol": "ETHUSDT", "regime": "MEAN_REVERTING"}})

        assert writer._regime_cache["BTCUSDT"] == "TRENDING"
        assert writer._regime_cache["ETHUSDT"] == "MEAN_REVERTING"


@pytest.mark.unit
class TestExtractPrice:
    """Tests for _extract_price static method."""

    def test_priority_order(self):
        """price > close > last_price > mark_price."""
        assert FeatureMirrorWriter._extract_price({"price": 100, "close": 200}) == 100.0
        assert FeatureMirrorWriter._extract_price({"close": 200, "last_price": 300}) == 200.0
        assert FeatureMirrorWriter._extract_price({"last_price": 300, "mark_price": 400}) == 300.0
        assert FeatureMirrorWriter._extract_price({"mark_price": 400}) == 400.0
        assert FeatureMirrorWriter._extract_price({}) == 0.0


@pytest.mark.unit
class TestExtractPayload:
    """Tests for _extract_payload static method."""

    def test_dict_event(self):
        """Dict-based event handled."""
        result = FeatureMirrorWriter._extract_payload({"pld": {"symbol": "BTCUSDT"}, "rid": "123"})
        assert result == {"symbol": "BTCUSDT"}

    def test_object_event(self):
        """Object with .pld handled."""
        event = MagicMock()
        event.pld = {"symbol": "ETHUSDT"}
        result = FeatureMirrorWriter._extract_payload(event)
        assert result == {"symbol": "ETHUSDT"}


@pytest.mark.unit
class TestWriterLifecycle:
    """Tests for writer setup and stats."""

    def test_registers_ta_listener(self, tmp_path):
        """Writer subscribes to base features, TA features, and regime events."""
        _, _, bus = _make_writer(tmp_path)
        listened = [call.args[0] for call in bus.listen.call_args_list]
        assert "EVT:FEATURES_CALCULATED" in listened
        assert "EVT:TA_FEATURES_CALCULATED" in listened
        assert "EVT:REGIME_DETECTED" in listened

    def test_output_dir_created(self, tmp_path):
        """Output parent dir created on init."""
        output = tmp_path / "deep" / "nested" / "output.jsonl"
        bus = MagicMock()
        bus.listen = MagicMock()
        FeatureMirrorWriter(event_bus=bus, output_path=output, symbols=None)
        assert output.parent.exists()

    def test_stats_counters(self, tmp_path):
        """snapshots_written, snapshots_skipped, and pending caches are correct."""
        writer, _, _ = _make_writer(tmp_path)

        writer._on_ta_features(_ta_event("BTCUSDT", 1740000000000, 1740000000000))
        writer._on_features(_feature_event("BTCUSDT", 1740000000000, 1740000000000))
        writer._on_features(
            {
                "pld": {
                    "symbol": "BTCUSDT",
                    "features": {},
                    "tf_sec": 300,
                    "bar_close_ts": 1740000000001,
                    "ts": 0,
                }
            }
        )

        stats = writer.stats
        assert stats["snapshots_written"] == 1
        assert stats["snapshots_skipped"] == 1
        assert stats["pending_feature_snapshots"] == 0
        assert stats["pending_ta_snapshots"] == 0
