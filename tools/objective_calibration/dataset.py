from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from .extract_ledger import load_order_ledger
from .extract_recorder import load_recorder_rows
from .extract_wal import load_wal_events
from .features import build_attempted_entry_frame, build_realized_objective_frame


@dataclass(slots=True)
class CalibrationDataset:
    attempted_entries: pd.DataFrame
    realized_trades: pd.DataFrame
    manifest: dict

    def write(self, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        self.attempted_entries.to_csv(out_dir / "attempted_entries.csv", index=False)
        self.realized_trades.to_csv(out_dir / "realized_trades.csv", index=False)
        (out_dir / "manifest.json").write_text(
            json.dumps(self.manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return out_dir


def build_objective_dataset(
    *,
    recorder_dir: Path,
    wal_dir: Path,
    ledger_path: Path,
    symbols: Iterable[str],
    start: date | None,
    end: date | None,
    tf_sec: int,
) -> CalibrationDataset:
    recorder_df = load_recorder_rows(
        recorder_dir,
        start=start,
        end=end,
        symbols=symbols,
        tf_sec=tf_sec,
    )
    wal_df = load_wal_events(wal_dir, start=start, end=end)
    ledger_df = load_order_ledger(ledger_path)

    attempted = build_attempted_entry_frame(
        recorder_df=recorder_df,
        wal_df=wal_df,
        default_tf_sec=tf_sec,
    )
    realized = build_realized_objective_frame(
        wal_df=wal_df,
        ledger_df=ledger_df,
    )

    manifest = {
        "built_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "symbols": [str(symbol).upper() for symbol in symbols],
        "start": start.isoformat() if start is not None else None,
        "end": end.isoformat() if end is not None else None,
        "tf_sec": int(tf_sec),
        "attempted_entry_rows": int(len(attempted)),
        "realized_trade_rows": int(len(realized)),
        "sources": {
            "recorder_dir": str(recorder_dir),
            "wal_dir": str(wal_dir),
            "ledger_path": str(ledger_path),
        },
    }
    return CalibrationDataset(
        attempted_entries=attempted,
        realized_trades=realized,
        manifest=manifest,
    )


def load_objective_dataset(dataset_dir: Path) -> CalibrationDataset:
    attempted_path = dataset_dir / "attempted_entries.csv"
    realized_path = dataset_dir / "realized_trades.csv"
    manifest_path = dataset_dir / "manifest.json"
    attempted = pd.read_csv(attempted_path) if attempted_path.exists() else pd.DataFrame()
    realized = pd.read_csv(realized_path) if realized_path.exists() else pd.DataFrame()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return CalibrationDataset(attempted_entries=attempted, realized_trades=realized, manifest=manifest)
