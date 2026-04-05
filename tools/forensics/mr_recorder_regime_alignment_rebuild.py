#!/usr/bin/env python3
from __future__ import annotations
from vfoundation.core.fsm_core import FSMCore
from tools.objective_calibration.extract_recorder import load_recorder_rows
from tools.forensics.mr_signal_surface_audit import EARLY_MANIFEST, RECENT_MANIFEST, _load_run_window
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
from apps.reference.domains.data_recorder.recorder import CsvRecorder
from apps.reference.core.time.clock import MockClock, reset_clock, set_clock
from apps.reference.config_loader import ConfigLoader

import argparse
import csv
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _normalize_source_rows(df: pd.DataFrame, *, tf_sec: int) -> pd.DataFrame:
    out = df.copy()
    out["timestamp"] = pd.to_numeric(out["timestamp"], errors="coerce")
    out["tf_sec"] = pd.to_numeric(
        out.get("tf_sec", tf_sec), errors="coerce").fillna(int(tf_sec)).astype(int)
    out = out.dropna(subset=["timestamp"])
    out = out[out["tf_sec"] == int(tf_sec)].copy()
    out["timestamp"] = out["timestamp"].astype("int64")
    out["symbol"] = out["symbol"].astype(str).str.upper()
    out = out.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    out = out.sort_values(["symbol", "timestamp"],
                          kind="mergesort").reset_index(drop=True)
    return out


def _build_features_payload(row: pd.Series) -> dict[str, Any]:
    features: dict[str, str] = {}
    for column, value in row.items():
        column_name = str(column)
        if _is_missing(value):
            continue
        if column_name.startswith("feat_"):
            features[column_name[5:]] = str(value)
            continue
        if column_name in {"price", "spread_bps", "liquidity_kappa", "volatility_state"}:
            features[column_name] = str(value)

    reasons_raw = "" if _is_missing(row.get("not_ready_reasons")) else str(
        row.get("not_ready_reasons") or "")
    ready_raw = row.get("ready")
    ready = False if _is_missing(ready_raw) else str(
        ready_raw).lower() == "true"

    trade_count_raw = row.get("trade_count")
    volume_raw = row.get("volume")

    return {
        "ts": int(row["timestamp"]),
        "symbol": str(row["symbol"]).upper(),
        "tf_sec": int(row["tf_sec"]),
        "features": features,
        "warmup": {
            "full_ready": ready,
            "reasons": [part for part in reasons_raw.split("|") if part],
            "ready": {},
        },
        "price_motion": {
            "pm_norm": None if _is_missing(row.get("pm_norm")) else str(row.get("pm_norm")),
            "pm_raw": None if _is_missing(row.get("pm_raw")) else str(row.get("pm_raw")),
        },
        "bar": {
            "open": str(row.get("open")),
            "high": str(row.get("high")),
            "low": str(row.get("low")),
            "close": str(row.get("close")),
            "volume": "0" if _is_missing(volume_raw) else str(volume_raw),
            "trade_count": 0 if _is_missing(trade_count_raw) else int(float(trade_count_raw)),
            "start_ts_ms": int(row["timestamp"]) - int(row["tf_sec"]) * 1000,
            "end_ts_ms": int(row["timestamp"]),
        },
        "diagnostics": {
            "synthetic_repair": True,
            "source_session_day": "" if _is_missing(row.get("session_day")) else str(row.get("session_day")),
        },
        "source_mode": "synthetic_repair",
        "close_boundary_ts_ms": int(row["timestamp"]),
    }


def _install_timestamped_append(recorder: CsvRecorder, output_root: Path, fieldnames: list[str]) -> None:
    stable_fieldnames = list(fieldnames)

    def _append(symbol: str, tf_sec: int, row_dict: dict[str, Any]) -> None:
        ts_ms = int(row_dict["timestamp"])
        date_str = datetime.fromtimestamp(
            ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
        dir_path = output_root / date_str
        dir_path.mkdir(parents=True, exist_ok=True)
        path = dir_path / f"{symbol}_{int(tf_sec)}.csv"
        write_header = (not path.exists()) or path.stat().st_size == 0
        with path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=stable_fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerow({key: row_dict.get(key, "")
                            for key in stable_fieldnames})
        recorder._rows_written += 1

    recorder._append_to_file = _append  # type: ignore[method-assign]


def _rebuild_window(
    *,
    label: str,
    source_recorder_dir: Path,
    output_recorder_dir: Path,
    symbol: str,
    start: Any,
    end_exclusive: Any,
    tf_sec: int,
) -> dict[str, Any]:
    loaded = load_recorder_rows(
        source_recorder_dir,
        start=start,
        end=end_exclusive,
        symbols=[symbol],
        tf_sec=tf_sec,
    )
    df = _normalize_source_rows(loaded, tf_sec=tf_sec)
    if df.empty:
        return {
            "rows": 0,
            "regime_counts": {},
            "join_status_counts": {},
            "join_mode_counts": {},
        }

    fixed_fieldnames = sorted(
        {
            "timestamp",
            "datetime",
            "symbol",
            "tf_sec",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "trade_count",
            "pm_norm",
            "pm_raw",
            "ready",
            "not_ready_reasons",
            "regime",
            "regime_conf",
            "regime_join_status",
            "regime_join_mode",
            "regime_event_ts_ms",
            "regime_last_update_ts_ms",
            "regime_age_ms",
            "regime_layer",
            "regime_scope",
            "regime_owner",
            "regime_source_model",
            "regime_structural_regime_ref",
            "regime_warmup_full_ready",
            "regime_warmup_reasons",
            "regime_data_drops",
            "regime_data_notes",
            *[str(column)
              for column in df.columns if str(column).startswith("feat_")],
            *[
                f"feat_{column}"
                for column in ("price", "spread_bps", "liquidity_kappa", "volatility_state")
                if column in df.columns
            ],
        }
    )

    clock = MockClock(start_ms=int(df.iloc[0]["timestamp"]))
    set_clock(clock)
    try:
        config = ConfigLoader().load_config(strict_mode=False, is_live_execution=False)
        fsm = FSMCore()
        recorder = CsvRecorder(fsm=fsm, config=config)
        recorder._root_dir = str(output_recorder_dir)
        _install_timestamped_append(
            recorder, output_recorder_dir, fixed_fieldnames)
        detector = RegimeDetector(config=config, fsm=fsm, clock=clock)

        # Preserve the observed live listener order for FEATURES_CALCULATED:
        # RegimeDetector.handle_event runs before CsvRecorder.on_features,
        # which is the exact order that produced orphan regimes pre-fix.
        detector.start()
        fsm.listen("EVT:FEATURES_CALCULATED", recorder.on_features)
        fsm.listen("EVT:REGIME_DETECTED", recorder.on_regime)

        for _, row in df.iterrows():
            clock.set_time_ms(int(row["timestamp"]))
            payload = _build_features_payload(row)
            fsm.emit(
                "EVT:FEATURES_CALCULATED",
                payload,
                why=f"synthetic_recorder_regime_alignment:{label}",
            )
            recorder._flush()

        clock.advance_sec(3.0)
        recorder._flush()
    finally:
        reset_clock()

    rebuilt = load_recorder_rows(
        output_recorder_dir,
        start=start,
        end=end_exclusive,
        symbols=[symbol],
        tf_sec=tf_sec,
    )
    if rebuilt.empty:
        return {
            "rows": 0,
            "regime_counts": {},
            "join_status_counts": {},
            "join_mode_counts": {},
        }

    regime_counts = Counter(rebuilt.get(
        "regime", "").fillna("NONE").astype(str).tolist())
    join_status_counts = Counter(
        rebuilt.get("regime_join_status", "").fillna(
            "NONE").astype(str).tolist()
    )
    join_mode_counts = Counter(
        rebuilt.get("regime_join_mode", "").fillna("NONE").astype(str).tolist()
    )
    return {
        "rows": int(len(rebuilt)),
        "regime_counts": dict(sorted(regime_counts.items(), key=lambda item: (-item[1], item[0]))),
        "join_status_counts": dict(sorted(join_status_counts.items(), key=lambda item: (-item[1], item[0]))),
        "join_mode_counts": dict(sorted(join_mode_counts.items(), key=lambda item: (-item[1], item[0]))),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild DOGEUSDT 300s recorder windows through the repaired recorder/regime join path.")
    parser.add_argument(
        "--source-recorder-dir",
        default=str(REPO_ROOT / "data" / "recorder"),
    )
    parser.add_argument(
        "--output-recorder-dir",
        default=str(REPO_ROOT / "reports" /
                    "mean_reversion_recorder_regime_alignment_v1" / "rebuilt_recorder"),
    )
    parser.add_argument(
        "--output-json",
        default=str(REPO_ROOT / "reports" / "mean_reversion_recorder_regime_alignment_v1" /
                    "recorder_regime_alignment_summary.json"),
    )
    args = parser.parse_args()

    source_recorder_dir = Path(args.source_recorder_dir)
    output_recorder_dir = Path(args.output_recorder_dir)
    output_json = Path(args.output_json)

    if output_recorder_dir.exists():
        shutil.rmtree(output_recorder_dir)
    output_recorder_dir.mkdir(parents=True, exist_ok=True)

    windows = [
        _load_run_window(EARLY_MANIFEST, label="early_clean"),
        _load_run_window(RECENT_MANIFEST, label="recent_clean"),
    ]

    summary: dict[str, Any] = {
        "source_recorder_dir": str(source_recorder_dir),
        "output_recorder_dir": str(output_recorder_dir),
        "symbol": "DOGEUSDT",
        "tf_sec": 300,
        "windows": {},
    }

    combined_regimes: Counter[str] = Counter()
    combined_join_status: Counter[str] = Counter()
    combined_join_mode: Counter[str] = Counter()
    combined_rows = 0

    for window in windows:
        window_summary = _rebuild_window(
            label=window.label,
            source_recorder_dir=source_recorder_dir,
            output_recorder_dir=output_recorder_dir,
            symbol="DOGEUSDT",
            start=window.start,
            end_exclusive=window.end_exclusive,
            tf_sec=window.tf_sec,
        )
        summary["windows"][window.label] = {
            "window": {
                "start": window.start.isoformat(),
                "end_exclusive": window.end_exclusive.isoformat(),
                "tf_sec": int(window.tf_sec),
            },
            **window_summary,
        }
        combined_rows += int(window_summary["rows"])
        combined_regimes.update(window_summary["regime_counts"])
        combined_join_status.update(window_summary["join_status_counts"])
        combined_join_mode.update(window_summary["join_mode_counts"])

    summary["combined"] = {
        "rows": combined_rows,
        "regime_counts": dict(sorted(combined_regimes.items(), key=lambda item: (-item[1], item[0]))),
        "join_status_counts": dict(sorted(combined_join_status.items(), key=lambda item: (-item[1], item[0]))),
        "join_mode_counts": dict(sorted(combined_join_mode.items(), key=lambda item: (-item[1], item[0]))),
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(
        summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
