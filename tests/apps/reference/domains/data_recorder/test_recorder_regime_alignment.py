import csv
from pathlib import Path

from apps.reference.core.time.clock import MockClock, reset_clock, set_clock
from apps.reference.domains.data_recorder.recorder import CsvRecorder
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message


def _feature_event(ts_ms: int) -> Message:
    return Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        src="test",
        dst="recorder",
        pld={
            "ts": ts_ms,
            "symbol": "DOGEUSDT",
            "tf_sec": 300,
            "bar": {
                "open": "0.10",
                "high": "0.11",
                "low": "0.09",
                "close": "0.105",
                "volume": "1000",
                "trade_count": 42,
            },
            "features": {
                "price": "0.105",
                "obi": "0.1",
                "delta_price": "0.0",
            },
            "warmup": {
                "full_ready": True,
                "reasons": [],
            },
            "price_motion": {
                "pm_norm": "0.0",
                "pm_raw": "0.0",
            },
        },
        why="test",
    )


def _regime_event(ts_ms: int, *, regime: str = "LOW_VOLATILITY") -> Message:
    return Message(
        op="EVT",
        verb="REGIME_DETECTED",
        src="test",
        dst="recorder",
        pld={
            "ts": ts_ms,
            "ts_ms": ts_ms,
            "symbol": "DOGEUSDT",
            "regime": regime,
            "confidence": "0.42",
            "source_model": "unit_test_regime",
            "regime_layer": "structural",
            "regime_scope": "per_symbol",
            "regime_owner": "regime_detector",
            "structural_regime_ref": f"structural:DOGEUSDT:{ts_ms}",
            "last_update_ts_ms": ts_ms + 7,
            "warmup": {
                "full_ready": True,
                "reasons": [],
            },
            "data_quality": {
                "drops": [],
                "notes": [],
            },
        },
        why="test",
    )


def _read_single_row(root: Path) -> dict[str, str]:
    csv_files = list(root.rglob("*.csv"))
    assert len(csv_files) == 1
    with csv_files[0].open(encoding="utf-8") as handle:
        return next(csv.DictReader(handle))


def test_regime_exact_match_after_features_uses_buffer_mode(tmp_path: Path) -> None:
    set_clock(MockClock(start_ms=1_000))
    try:
        recorder = CsvRecorder(fsm=FSMCore(), config=object())
        recorder._root_dir = str(tmp_path / "recorder")

        recorder.on_features(_feature_event(1_000))
        recorder.on_regime(_regime_event(1_000))
        recorder._flush()

        row = _read_single_row(tmp_path / "recorder")
        assert row["regime"] == "LOW_VOLATILITY"
        assert row["regime_join_status"] == "MATCHED"
        assert row["regime_join_mode"] == "buffer_exact_ts"
        assert row["regime_event_ts_ms"] == "1000"
        assert row["regime_last_update_ts_ms"] == "1007"
    finally:
        reset_clock()


def test_regime_exact_match_before_features_uses_orphan_mode(tmp_path: Path) -> None:
    set_clock(MockClock(start_ms=2_000))
    try:
        recorder = CsvRecorder(fsm=FSMCore(), config=object())
        recorder._root_dir = str(tmp_path / "recorder")

        recorder.on_regime(_regime_event(2_000, regime="MEAN_REVERSION"))
        recorder.on_features(_feature_event(2_000))
        recorder._flush()

        row = _read_single_row(tmp_path / "recorder")
        assert row["regime"] == "MEAN_REVERSION"
        assert row["regime_join_status"] == "MATCHED"
        assert row["regime_join_mode"] == "orphan_exact_ts"
        assert row["regime_source_model"] == "unit_test_regime"
    finally:
        reset_clock()


def test_missing_regime_times_out_with_explicit_missing_provenance(tmp_path: Path) -> None:
    clock = MockClock(start_ms=3_000)
    set_clock(clock)
    try:
        recorder = CsvRecorder(fsm=FSMCore(), config=object())
        recorder._root_dir = str(tmp_path / "recorder")

        recorder.on_features(_feature_event(3_000))
        clock.advance_sec(3.0)
        recorder._flush()

        row = _read_single_row(tmp_path / "recorder")
        assert row["regime"] == "PENDING"
        assert row["regime_conf"] == "0.0"
        assert row["regime_join_status"] == "MISSING"
        assert row["regime_join_mode"] == "missing_timeout"
        assert row["regime_event_ts_ms"] == ""
    finally:
        reset_clock()
