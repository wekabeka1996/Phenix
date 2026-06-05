"""Tests for tools/judge/audit_and_backfill_1m_candles.py (PKG-7).

Ten mandatory tests covering: ms semantics, required-window derivation,
raw cache indexing, missing-range collapse, deterministic outputs, no
silent drops, downloader CLI argument shape, 1000PEPEUSDT inclusion,
report+manifest+jsonl artifact emission, and edge cases.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.judge import audit_and_backfill_1m_candles as mod


def _write_verdict(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _write_raw(path: Path, symbol: str, klines: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"symbol": symbol, "interval": "1m", "klines": klines}
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_kline(open_ms: int) -> list:
    return [open_ms, "1.0", "1.1", "0.9", "1.05", "10.0", open_ms + 60_000 - 1, "10.5", 5]


def test_1_ceil_to_close_ms_snaps_to_bar_close():
    # 12:00:00.000 ms → 12:00:59.999 close
    assert mod.ceil_to_close_ms(0) == 59_999
    assert mod.ceil_to_close_ms(59_999) == 59_999
    assert mod.ceil_to_close_ms(60_000) == 119_999
    # arbitrary ms inside a minute snaps to that minute's close
    assert mod.ceil_to_close_ms(123_456) == 179_999


def test_2_required_window_extends_horizon_past_last_verdict(tmp_path: Path):
    logs = tmp_path / "logs"
    # Verdict at 12:00:59.999 with tf_sec=180
    _write_verdict(logs / "verdict_BTCUSDT_2026-05-17.jsonl",
                   [{"ts_ms": 59_999, "tf_sec": 180}])
    windows = mod.scan_judge_windows(logs)
    assert "BTCUSDT" in windows
    start, end, required = mod.required_close_ms_set(
        windows["BTCUSDT"], horizon_bars=12)
    # 12 bars * 180s = 2160s = 36 minutes past the verdict bar close
    assert start == 59_999
    assert end == 59_999 + 36 * 60_000
    # 37 minute close timestamps inclusive
    assert len(required) == 37


def test_3_raw_cache_indexing_returns_minute_close_set(tmp_path: Path):
    raw = tmp_path / "raw" / "BTCUSDT"
    _write_raw(raw / "BTCUSDT_1m_0_119999.json", "BTCUSDT",
               [_make_kline(0), _make_kline(60_000)])
    present, file_count = mod.index_raw_cache(tmp_path / "raw", "BTCUSDT")
    assert file_count == 1
    assert present == {59_999, 119_999}


def test_4_raw_cache_missing_dir_returns_empty(tmp_path: Path):
    present, file_count = mod.index_raw_cache(
        tmp_path / "no_such", "1000PEPEUSDT")
    assert present == set()
    assert file_count == 0


def test_5_collapse_missing_produces_contiguous_ranges():
    required = {59_999, 119_999, 179_999, 239_999, 299_999}
    present = {119_999}  # one bar present in the middle
    ranges = mod.collapse_missing(required, present)
    # Expect two runs: [59_999..59_999] and [179_999..299_999]
    assert ranges == [(59_999, 59_999), (179_999, 299_999)]


def test_6_no_silent_drop_accounting(tmp_path: Path):
    logs = tmp_path / "logs"
    _write_verdict(logs / "verdict_BTCUSDT_2026-05-17.jsonl",
                   [{"ts_ms": 59_999, "tf_sec": 180}])
    raw = tmp_path / "raw" / "BTCUSDT"
    _write_raw(raw / "BTCUSDT_1m_0_119999.json", "BTCUSDT", [_make_kline(0)])
    windows = mod.scan_judge_windows(logs)
    coverage = mod.build_coverage_rows(
        windows, horizon_bars=12, raw_cache_root=tmp_path / "raw")
    cov = coverage["BTCUSDT"]
    # required + missing must equal required, and present + missing must equal required
    assert cov.present_minutes + cov.missing_minutes == cov.required_minutes
    assert cov.present_minutes == 1
    assert cov.missing_minutes == cov.required_minutes - 1


def test_7_1000pepeusdt_listed_when_in_judge_logs_even_without_raw_cache(tmp_path: Path):
    logs = tmp_path / "logs"
    _write_verdict(logs / "verdict_1000PEPEUSDT_2026-05-17.jsonl",
                   [{"ts_ms": 59_999, "tf_sec": 180}])
    windows = mod.scan_judge_windows(logs)
    coverage = mod.build_coverage_rows(
        windows, horizon_bars=12, raw_cache_root=tmp_path / "no_raw")
    assert "1000PEPEUSDT" in coverage
    cov = coverage["1000PEPEUSDT"]
    assert cov.raw_cache_files == 0
    assert cov.present_minutes == 0
    # All required minutes are missing.
    assert cov.missing_minutes == cov.required_minutes
    assert cov.missing_minutes > 0


def test_8_artifacts_written_and_manifest_shape(tmp_path: Path):
    logs = tmp_path / "logs"
    _write_verdict(logs / "verdict_BTCUSDT_2026-05-17.jsonl",
                   [{"ts_ms": 59_999, "tf_sec": 180}])
    raw = tmp_path / "raw"
    out_report = tmp_path / "report.md"
    out_manifest = tmp_path / "manifest.json"
    out_jsonl = tmp_path / "missing.jsonl"
    out_csv = tmp_path / "windows.csv"
    args = mod.parse_args([
        "--mode", "audit",
        "--judge-logs-root", str(logs),
        "--raw-cache-root", str(raw),
        "--report-out", str(out_report),
        "--manifest-out", str(out_manifest),
        "--missing-windows-jsonl", str(out_jsonl),
        "--windows-csv", str(out_csv),
    ])
    rc = mod.run(args)
    assert rc == 0
    assert out_report.exists()
    assert out_manifest.exists()
    assert out_jsonl.exists()
    assert out_csv.exists()
    manifest = json.loads(out_manifest.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "pkg7_v1"
    assert "BTCUSDT" in manifest["symbols"]
    assert manifest["symbols"]["BTCUSDT"]["missing_minutes"] > 0
    # JSONL has one line per missing range and lines are sorted by symbol then start.
    lines = [l for l in out_jsonl.read_text(
        encoding="utf-8").splitlines() if l]
    assert len(lines) == len(manifest["symbols"]["BTCUSDT"]["missing_ranges"])
    # CSV header matches downloader contract.
    header = out_csv.read_text(encoding="utf-8").splitlines()[0]
    assert header == "symbol,required_start_ms,required_end_ms,entries_covered,reason"


def test_9_deterministic_rerun(tmp_path: Path):
    logs = tmp_path / "logs"
    _write_verdict(logs / "verdict_BTCUSDT_2026-05-17.jsonl",
                   [{"ts_ms": 59_999, "tf_sec": 180}])
    raw = tmp_path / "raw"
    out_csv_a = tmp_path / "a.csv"
    out_csv_b = tmp_path / "b.csv"
    out_jsonl_a = tmp_path / "a.jsonl"
    out_jsonl_b = tmp_path / "b.jsonl"
    out_manifest_a = tmp_path / "a.json"
    out_manifest_b = tmp_path / "b.json"
    for csv_p, jsonl_p, man_p in [
        (out_csv_a, out_jsonl_a, out_manifest_a),
        (out_csv_b, out_jsonl_b, out_manifest_b),
    ]:
        args = mod.parse_args([
            "--mode", "audit",
            "--judge-logs-root", str(logs),
            "--raw-cache-root", str(raw),
            "--report-out", str(tmp_path / f"report_{csv_p.name}.md"),
            "--manifest-out", str(man_p),
            "--missing-windows-jsonl", str(jsonl_p),
            "--windows-csv", str(csv_p),
        ])
        mod.run(args)
    # Files that should be byte-identical across runs (manifest contains generated_at_utc
    # which differs; the windows CSV and missing jsonl should not).
    assert out_csv_a.read_bytes() == out_csv_b.read_bytes()
    assert out_jsonl_a.read_bytes() == out_jsonl_b.read_bytes()
    man_a = json.loads(out_manifest_a.read_text(encoding="utf-8"))
    man_b = json.loads(out_manifest_b.read_text(encoding="utf-8"))
    assert man_a["input_hash_sha256"] == man_b["input_hash_sha256"]
    assert man_a["symbols"] == man_b["symbols"]
    assert man_a["totals"] == man_b["totals"]


def test_10_windows_csv_shape_matches_downloader_loader(tmp_path: Path):
    """Emitted windows CSV must satisfy the canonical downloader's load_windows()."""
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location(
        "dl_module_pkg7",
        Path(mod.ROOT) / "tools" / "data" /
        "download_binance_futures_1m_klines_for_replay.py",
    )
    dl = importlib.util.module_from_spec(spec)
    sys.modules["dl_module_pkg7"] = dl
    spec.loader.exec_module(dl)  # type: ignore[union-attr]

    csv_path = tmp_path / "w.csv"
    mr1 = mod.MissingRange(symbol="BTCUSDT", start_close_ms=59_999,
                           end_close_ms=119_999, missing_minutes=2)
    mr2 = mod.MissingRange(symbol="1000PEPEUSDT", start_close_ms=59_999,
                           end_close_ms=59_999, missing_minutes=1)
    mod.write_windows_csv(csv_path, [mr1, mr2])
    loaded = dl.load_windows(csv_path)
    assert len(loaded) == 2
    symbols = {w.symbol for w in loaded}
    assert symbols == {"BTCUSDT", "1000PEPEUSDT"}
    btc = next(w for w in loaded if w.symbol == "BTCUSDT")
    assert btc.required_start_ms == 59_999
    assert btc.required_end_ms == 119_999
    assert btc.entries_covered == 2
