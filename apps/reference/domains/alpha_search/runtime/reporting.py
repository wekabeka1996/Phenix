"""
Aggregate Reporter
==================

Cross-scenario comparison metrics written to aggregate CSV and JSONL.
Follows TelemetryLogger pattern from neocortex domain.
"""

<<<<<<< HEAD
from collections import Counter
=======
>>>>>>> 099d495c4eee1837ba188384663f5ef7ba426a9b
import csv
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

CSV_COLUMNS = [
    "timestamp",
    "scenario_id",
    "strategy_type",
<<<<<<< HEAD
    "version",
    "family",
=======
>>>>>>> 099d495c4eee1837ba188384663f5ef7ba426a9b
    "symbol",
    "ts_ms",
    "score",
    "confidence",
    "threshold",
    "side",
    "provider_id",
<<<<<<< HEAD
    "shadow_only",
    "authority_applied",
    "no_effect",
    "regime",
]

SCENARIO_MATRIX_COLUMNS = [
    "scenario_id",
    "version",
    "family",
    "provider",
    "enabled",
    "shadow_only",
    "authority_applied",
    "no_effect",
    "evaluated_rows",
    "BUY_count",
    "SELL_count",
    "NEUTRAL_count",
    "top_reason_codes",
    "missing_features",
    "init_status",
    "init_error",
]

=======
    "regime",
]

>>>>>>> 099d495c4eee1837ba188384663f5ef7ba426a9b

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
<<<<<<< HEAD
        self._scenario_matrix_path = self._agg_dir / "scenario_runtime_matrix.csv"

        self._csv_initialized = False
        self._rows_written = 0
        self._scenario_runtime: Dict[str, Dict[str, Any]] = {}

    def register_scenarios(self, scenarios: List[Any]) -> None:
        """Pre-register every configured scenario so none disappear silently from runtime outputs."""
        for spec in scenarios:
            self._scenario_runtime[spec.scenario_id] = {
                "scenario_id": spec.scenario_id,
                "version": getattr(spec, "version", None) or "",
                "family": getattr(spec, "family", None) or "",
                "provider": getattr(spec, "provider", None) or "",
                "enabled": bool(getattr(spec, "enabled", True)),
                "shadow_only": bool(getattr(spec, "shadow_only", True)),
                "authority_applied": bool(getattr(spec, "authority_applied", False)),
                "no_effect": bool(getattr(spec, "no_effect", True)),
                "evaluated_rows": 0,
                "BUY_count": 0,
                "SELL_count": 0,
                "NEUTRAL_count": 0,
                "top_reason_codes": "",
                "missing_features": "",
                "init_status": "REGISTERED",
                "init_error": "",
                "_reason_counter": Counter(),
                "_missing_features": set(),
            }
        self._write_scenario_matrix()
=======

        self._csv_initialized = False
        self._rows_written = 0
>>>>>>> 099d495c4eee1837ba188384663f5ef7ba426a9b

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
<<<<<<< HEAD
        self._update_scenario_runtime(result)
        self._write_scenario_matrix()
=======
>>>>>>> 099d495c4eee1837ba188384663f5ef7ba426a9b

    def log_health(self, event: Dict[str, Any]) -> None:
        """Append health event to aggregate health.jsonl."""
        record = {"ts": time.time(), **event}
        with open(self._health_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
<<<<<<< HEAD
        self._update_health_runtime(event)
        self._write_scenario_matrix()
=======
>>>>>>> 099d495c4eee1837ba188384663f5ef7ba426a9b

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

<<<<<<< HEAD
    def _ensure_scenario_runtime(self, scenario_id: str) -> Dict[str, Any]:
        runtime = self._scenario_runtime.setdefault(
            scenario_id,
            {
                "scenario_id": scenario_id,
                "version": "",
                "family": "",
                "provider": "",
                "enabled": True,
                "shadow_only": True,
                "authority_applied": False,
                "no_effect": True,
                "evaluated_rows": 0,
                "BUY_count": 0,
                "SELL_count": 0,
                "NEUTRAL_count": 0,
                "top_reason_codes": "",
                "missing_features": "",
                "init_status": "RESULT_OBSERVED",
                "init_error": "",
                "_reason_counter": Counter(),
                "_missing_features": set(),
            },
        )
        runtime.setdefault("_reason_counter", Counter())
        runtime.setdefault("_missing_features", set())
        return runtime

    def _update_scenario_runtime(self, result: Dict[str, Any]) -> None:
        scenario_id = str(result.get("scenario_id", "")).strip()
        if not scenario_id:
            return
        runtime = self._ensure_scenario_runtime(scenario_id)
        runtime["version"] = result.get("version", runtime["version"])
        runtime["family"] = result.get("family", runtime["family"])
        runtime["provider"] = result.get("provider_id", runtime["provider"])
        runtime["shadow_only"] = bool(result.get("shadow_only", runtime["shadow_only"]))
        runtime["authority_applied"] = bool(result.get("authority_applied", runtime["authority_applied"]))
        runtime["no_effect"] = bool(result.get("no_effect", runtime["no_effect"]))
        runtime["evaluated_rows"] += 1
        side = str(result.get("side", "NEUTRAL")).upper()
        if side in {"BUY", "SELL", "NEUTRAL"}:
            runtime[f"{side}_count"] += 1

        for reason in result.get("why", []) or []:
            runtime["_reason_counter"][str(reason)] += 1
            if "missing" in str(reason).lower() or "not_evaluable" in str(reason).lower():
                runtime["_missing_features"].add(str(reason))

        runtime["top_reason_codes"] = "|".join(
            reason for reason, _ in runtime["_reason_counter"].most_common(3)
        )
        runtime["missing_features"] = "|".join(sorted(runtime["_missing_features"]))
        if runtime["init_status"] == "REGISTERED":
            runtime["init_status"] = "EVALUATED"

    def _update_health_runtime(self, event: Dict[str, Any]) -> None:
        scenario_id = str(event.get("scenario_id", "")).strip()
        if not scenario_id:
            return
        runtime = self._ensure_scenario_runtime(scenario_id)
        runtime["init_status"] = str(event.get("event", runtime["init_status"]))
        runtime["init_error"] = str(event.get("error", runtime["init_error"]))

    def _write_scenario_matrix(self) -> None:
        with open(self._scenario_matrix_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SCENARIO_MATRIX_COLUMNS)
            writer.writeheader()
            for scenario_id in sorted(self._scenario_runtime):
                row = self._scenario_runtime[scenario_id]
                writer.writerow({col: row.get(col, "") for col in SCENARIO_MATRIX_COLUMNS})

=======
>>>>>>> 099d495c4eee1837ba188384663f5ef7ba426a9b
    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "csv_rows": self._rows_written,
            "csv_path": str(self._csv_path),
<<<<<<< HEAD
            "scenario_matrix_path": str(self._scenario_matrix_path),
=======
>>>>>>> 099d495c4eee1837ba188384663f5ef7ba426a9b
        }
