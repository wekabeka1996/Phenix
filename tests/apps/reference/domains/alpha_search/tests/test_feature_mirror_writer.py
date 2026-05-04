"""
T4: Feature Mirror Writer Tests
=================================

Tests for apps/reference/domains/alpha_search/runtime/feature_mirror_writer.py
10 tests covering event handling, regime cache, symbol filter, and stats.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

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
    return writer, output


@pytest.mark.unit
class TestOnFeatures:
    """Tests for _on_features event handler."""

    def test_writes_jsonl(self, tmp_path):
        """Feature event -> JSONL record."""
        writer, output = _make_writer(tmp_path)
        event = {
            "pld": {
                "symbol": "BTCUSDT",
                "features": {"obi": 0.12, "close": 96000.0},
                "tf_sec": 300,
                "ts": 1740000000000,
            }
        }
        writer._on_features(event)

        assert output.exists()
        record = json.loads(output.read_text(encoding="utf-8").strip())
        assert record["symbol"] == "BTCUSDT"
        assert record["features"]["obi"] == 0.12

    def test_regime_cache_included(self, tmp_path):
        """Cached regime appears in output record."""
        writer, output = _make_writer(tmp_path)

        # Set regime via cache
        writer._regime_cache["BTCUSDT"] = "TRENDING"

        event = {
            "pld": {
                "symbol": "BTCUSDT",
                "features": {"obi": 0.12, "close": 96000.0},
                "tf_sec": 300,
                "ts": 1740000000000,
            }
        }
        writer._on_features(event)

        record = json.loads(output.read_text(encoding="utf-8").strip())
        assert record["regime"] == "TRENDING"

    def test_symbol_filter_applied(self, tmp_path):
        """Unallowed symbols skipped."""
        writer, output = _make_writer(tmp_path, symbols=["BTCUSDT"])

        # Emit for allowed symbol
        writer._on_features({
            "pld": {
                "symbol": "BTCUSDT",
                "features": {"obi": 0.12, "close": 96000.0},
                "tf_sec": 300,
                "ts": 1740000000000,
            }
        })

        # Emit for disallowed symbol
        writer._on_features({
            "pld": {
                "symbol": "ETHUSDT",
                "features": {"obi": 0.15, "close": 3000.0},
                "tf_sec": 300,
                "ts": 1740000000001,
            }
        })

        assert writer._snapshots_written == 1
        assert writer._snapshots_skipped == 1

    def test_empty_features_skipped(self, tmp_path):
        """No features -> no record."""
        writer, output = _make_writer(tmp_path)
        writer._on_features({
            "pld": {
                "symbol": "BTCUSDT",
                "features": {},
                "tf_sec": 300,
                "ts": 1740000000000,
            }
        })
        assert writer._snapshots_skipped == 1
        assert writer._snapshots_written == 0


@pytest.mark.unit
class TestOnRegime:
    """Tests for _on_regime event handler."""

    def test_caches_per_symbol(self, tmp_path):
        """Different symbols have independent regime cache."""
        writer, _ = _make_writer(tmp_path)

        writer._on_regime({"pld": {"symbol": "BTCUSDT", "regime": "TRENDING"}})
        writer._on_regime({"pld": {"symbol": "ETHUSDT", "regime": "MEAN_REVERTING"}})

        assert writer._regime_cache["BTCUSDT"] == "TRENDING"
        assert writer._regime_cache["ETHUSDT"] == "MEAN_REVERTING"


@pytest.mark.unit
class TestExtractPrice:
    """Tests for _extract_price static method."""

    def test_priority_order(self):
        """price > close > last_price > mark_price."""
        assert FeatureMirrorWriter._extract_price(
            {"price": 100, "close": 200}
        ) == 100.0

        assert FeatureMirrorWriter._extract_price(
            {"close": 200, "last_price": 300}
        ) == 200.0

        assert FeatureMirrorWriter._extract_price(
            {"last_price": 300, "mark_price": 400}
        ) == 300.0

        assert FeatureMirrorWriter._extract_price(
            {"mark_price": 400}
        ) == 400.0

        assert FeatureMirrorWriter._extract_price({}) == 0.0


@pytest.mark.unit
class TestExtractPayload:
    """Tests for _extract_payload static method."""

    def test_dict_event(self):
        """Dict-based event handled."""
        result = FeatureMirrorWriter._extract_payload(
            {"pld": {"symbol": "BTCUSDT"}, "rid": "123"}
        )
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

    def test_output_dir_created(self, tmp_path):
        """Output parent dir created on init."""
        output = tmp_path / "deep" / "nested" / "output.jsonl"
        bus = MagicMock()
        bus.listen = MagicMock()
        writer = FeatureMirrorWriter(
            event_bus=bus, output_path=output, symbols=None
        )
        assert output.parent.exists()

    def test_stats_counters(self, tmp_path):
        """snapshots_written, snapshots_skipped correct."""
        writer, _ = _make_writer(tmp_path)

        writer._on_features({
            "pld": {
                "symbol": "BTCUSDT",
                "features": {"obi": 0.12, "close": 96000.0},
                "tf_sec": 300,
                "ts": 1740000000000,
            }
        })
        writer._on_features({
            "pld": {"symbol": "BTCUSDT", "features": {}, "tf_sec": 300, "ts": 0}
        })

        stats = writer.stats
        assert stats["snapshots_written"] == 1
        assert stats["snapshots_skipped"] == 1
