"""
Aggregate Reporter
==================

Cross-scenario comparison metrics written to aggregate CSV and JSONL.
Follows TelemetryLogger pattern from neocortex domain.
"""

import csv
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

CSV_COLUMNS = [
    "timestamp",
    "scenario_id",
    "strategy_type",
    "symbol",
    "ts_ms",
    "score",
    "confidence",
    "threshold",
    "side",
    "provider_id",
    "regime",
]


class AggregateReporter:
    """
    Writes aggregate metrics for cross-scenario analysis.

    Files:
    - aggregate_metrics.csv: per-score CSV for tabular analysis
    - health.jsonl: health events from all scenarios
    - summary.jsonl: periodic scenario-level summaries
    """

    def __init__(self, session_dir: Path):
        self._session_dir = session_dir
        self._agg_dir = session_dir / "aggregate"
        self._agg_dir.mkdir(parents=True, exist_ok=True)

        self._csv_path = self._agg_dir / "aggregate_metrics.csv"
        self._health_path = self._agg_dir / "health.jsonl"
        self._summary_path = self._agg_dir / "summary.jsonl"

        self._csv_initialized = False
        self._rows_written = 0

    def log_result(self, result: Dict[str, Any]) -> None:
        """Append a single score result to aggregate CSV."""
        if not self._csv_initialized:
            self._init_csv()

        row = {col: result.get(col, "") for col in CSV_COLUMNS}
        row["timestamp"] = time.time()

        with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writerow(row)

        self._rows_written += 1

    def log_health(self, event: Dict[str, Any]) -> None:
        """Append health event to aggregate health.jsonl."""
        record = {"ts": time.time(), **event}
        with open(self._health_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def log_summary(self, summaries: Dict[str, Dict[str, Any]]) -> None:
        """Write periodic summary from all scenarios."""
        record = {
            "ts": time.time(),
            "scenarios": summaries,
        }
        with open(self._summary_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def _init_csv(self) -> None:
        """Write CSV header if file is new."""
        if not self._csv_path.exists() or self._csv_path.stat().st_size == 0:
            with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writeheader()
        self._csv_initialized = True

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "csv_rows": self._rows_written,
            "csv_path": str(self._csv_path),
        }
