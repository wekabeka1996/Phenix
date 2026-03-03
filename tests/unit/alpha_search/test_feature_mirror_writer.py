"""
Contract tests: FeatureMirrorWriter tf_sec filtering + core behaviour.

FMW-TICK-FILTER-01 (BUG regression):
  FeatureMirrorWriter was writing tick-level EVT:FEATURES_CALCULATED (tf_sec=0)
  to alpha_input_v1.jsonl. The standalone alpha_search runtime replayed those
  records through ScenarioWorker → CMD:PROCESS_STRATEGY with tf_sec=0 →
  ta_ensemble saw missing bar-aggregated TA indicators (bb_position, rsi_14,
  bb_width, stoch_k, …) and emitted a spurious WARNING + skipped scoring for
  XRPUSDT (which is disabled in production Aurora but IS evaluated independently
  by ta_ensemble in the alpha_search environment).

Tests:
  - test_tick_level_skipped          ← BUG regression: tf_sec=0 must NOT be written
  - test_bar_tf_300_written          ← positive path: tf_sec=300 is written
  - test_bar_tf_60_written           ← tf_sec=60 (1m bars) also passes gate
  - test_symbol_filter_blocks        ← existing symbol-allowlist still works
  - test_symbol_filter_none_allows_all  ← symbols=None → all symbols pass
  - test_empty_features_skipped      ← empty features dict → skipped
  - test_regime_injected_from_cache  ← latest regime is co-emitted in record
  - test_stats_counters_accurate     ← _snapshots_written/_skipped track correctly
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from apps.reference.domains.alpha_search.runtime.feature_mirror_writer import (
    FeatureMirrorWriter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockBus:
    """Minimal stand-in for FSMCore / LocalBus (listen-only used by writer)."""

    def listen(self, _event_name: str, _handler) -> None:
        pass  # writer registers listeners; we don't need to fire them here


def _make_writer(
    tmp_path: Path,
    symbols: Optional[List[str]] = None,
) -> tuple[FeatureMirrorWriter, Path]:
    output = tmp_path / "alpha_input_v1.jsonl"
    writer = FeatureMirrorWriter(
        event_bus=_MockBus(),
        output_path=output,
        symbols=symbols,
    )
    return writer, output


def _evt(
    symbol: str = "XRPUSDT",
    tf_sec: int = 300,
    features: Optional[Dict[str, Any]] = None,
    ts: int = 1_740_000_000_000,
    include_bar: bool = True,
) -> Dict[str, Any]:
    """Build a synthetic EVT:FEATURES_CALCULATED event dict."""
    payload: Dict[str, Any] = {
        "symbol": symbol,
        "tf_sec": tf_sec,
        "features": features if features is not None else {"price": "0.5"},
        "ts": ts,
    }
    if include_bar:
        payload["bar"] = {"close_ts": ts + tf_sec * 1000}
    return {"pld": payload}


def _read_records(output: Path) -> List[Dict[str, Any]]:
    if not output.exists():
        return []
    lines = [l for l in output.read_text(
        encoding="utf-8").splitlines() if l.strip()]
    return [json.loads(l) for l in lines]


# ---------------------------------------------------------------------------
# BUG regression
# ---------------------------------------------------------------------------

def test_tick_level_skipped(tmp_path: Path) -> None:
    """FMW-TICK-FILTER-01: tf_sec=0 events MUST NOT reach alpha_input_v1.jsonl.

    Tick-level events lack bar-aggregated TA indicators (bb_position, rsi_14,
    bb_width, stoch_k, …). Writing them causes ta_ensemble to silently skip
    XRPUSDT with a 'missing required features (tf_sec=0)' warning.
    """
    writer, output = _make_writer(tmp_path)
    writer._on_features(_evt(tf_sec=0))

    assert writer._snapshots_skipped == 1, "tick event must be counted as skipped"
    assert writer._snapshots_written == 0, "tick event must NOT be written"
    assert _read_records(
        output) == [], "JSONL must remain empty for tick-level events"


# ---------------------------------------------------------------------------
# Positive paths
# ---------------------------------------------------------------------------

def test_bar_tf_300_written(tmp_path: Path) -> None:
    """Standard 5-minute bar event (tf_sec=300) must be written."""
    writer, output = _make_writer(tmp_path)
    writer._on_features(_evt(symbol="XRPUSDT", tf_sec=300))

    assert writer._snapshots_written == 1
    assert writer._snapshots_skipped == 0
    records = _read_records(output)
    assert len(records) == 1
    assert records[0]["symbol"] == "XRPUSDT"
    assert records[0]["tf_sec"] == 300


def test_bar_tf_60_written(tmp_path: Path) -> None:
    """1-minute bar (tf_sec=60) must pass the gate — minimum valid bar tf_sec."""
    writer, output = _make_writer(tmp_path)
    writer._on_features(_evt(symbol="BTCUSDT", tf_sec=60))

    assert writer._snapshots_written == 1
    records = _read_records(output)
    assert records[0]["tf_sec"] == 60


# ---------------------------------------------------------------------------
# Symbol filter
# ---------------------------------------------------------------------------

def test_symbol_filter_blocks(tmp_path: Path) -> None:
    """Symbols outside the allow-list are still skipped (existing contract)."""
    writer, output = _make_writer(tmp_path, symbols=["BTCUSDT"])
    writer._on_features(_evt(symbol="XRPUSDT", tf_sec=300))

    assert writer._snapshots_skipped == 1
    assert writer._snapshots_written == 0


def test_symbol_filter_none_allows_all(tmp_path: Path) -> None:
    """symbols=None (default) → any symbol is written."""
    writer, output = _make_writer(tmp_path, symbols=None)
    writer._on_features(_evt(symbol="XRPUSDT", tf_sec=300))
    writer._on_features(_evt(symbol="DOGEUSDT", tf_sec=300))

    assert writer._snapshots_written == 2
    symbols_written = {r["symbol"] for r in _read_records(output)}
    assert symbols_written == {"XRPUSDT", "DOGEUSDT"}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_features_skipped(tmp_path: Path) -> None:
    """Empty features dict → event is skipped, JSONL not written."""
    writer, output = _make_writer(tmp_path)
    evt = _evt(tf_sec=300, features={})
    writer._on_features(evt)

    assert writer._snapshots_skipped == 1
    assert writer._snapshots_written == 0


def test_regime_injected_from_cache(tmp_path: Path) -> None:
    """Regime from EVT:REGIME_DETECTED cache must appear in the written record."""
    writer, output = _make_writer(tmp_path)

    # Inject a regime via the regime event handler
    writer._on_regime(
        {"pld": {"symbol": "XRPUSDT", "regime": "MEAN_REVERSION"}})

    # Now write a bar event
    writer._on_features(_evt(symbol="XRPUSDT", tf_sec=300))

    records = _read_records(output)
    assert len(records) == 1
    assert records[0]["regime"] == "MEAN_REVERSION"


# ---------------------------------------------------------------------------
# Stats counters
# ---------------------------------------------------------------------------

def test_stats_counters_accurate(tmp_path: Path) -> None:
    """Written and skipped counters must be accurate after mixed events."""
    writer, output = _make_writer(tmp_path)

    # 2 bar events → written
    writer._on_features(_evt(symbol="BTCUSDT", tf_sec=300))
    writer._on_features(_evt(symbol="XRPUSDT", tf_sec=300))

    # 1 tick event → skipped (tf_sec=0)
    writer._on_features(_evt(symbol="BTCUSDT", tf_sec=0))

    # 1 empty features → skipped
    writer._on_features(_evt(symbol="ETHUSDT", tf_sec=300, features={}))

    stats = writer.stats
    assert stats["snapshots_written"] == 2
    assert stats["snapshots_skipped"] == 2
