"""
Aggregate Reporter
==================

Cross-scenario comparison metrics written to aggregate CSV and JSONL.
Follows TelemetryLogger pattern from neocortex domain.

Extended with:
- Per-symbol breakdown (symbol_breakdown.csv)
- Per-regime breakdown (regime_breakdown.csv)
- Temporal analysis (temporal_breakdown.csv)
"""

from collections import Counter, defaultdict
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CSV_COLUMNS = [
    "timestamp",
    "scenario_id",
    "strategy_type",
    "version",
    "family",
    "symbol",
    "ts_ms",
    "score",
    "confidence",
    "threshold",
    "side",
    "provider_id",
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

SYMBOL_BREAKDOWN_COLUMNS = [
    "scenario_id",
    "symbol",
    "evaluated_rows",
    "BUY_count",
    "SELL_count",
    "NEUTRAL_count",
    "buy_pct",
    "sell_pct",
]

REGIME_BREAKDOWN_COLUMNS = [
    "scenario_id",
    "regime",
    "evaluated_rows",
    "BUY_count",
    "SELL_count",
    "NEUTRAL_count",
    "buy_pct",
    "sell_pct",
]

TEMPORAL_BREAKDOWN_COLUMNS = [
    "scenario_id",
    "hour_utc",
    "day_of_week",
    "evaluated_rows",
    "BUY_count",
    "SELL_count",
    "NEUTRAL_count",
    "buy_pct",
]


class AggregateReporter:
    """
    Writes aggregate metrics for cross-scenario analysis.

    Files:
    - aggregate_metrics.csv: per-score CSV for tabular analysis
    - health.jsonl: health events from all scenarios
    - summary.jsonl: periodic scenario-level summaries
    - symbol_breakdown.csv: per-scenario per-symbol signal counts
    - regime_breakdown.csv: per-scenario per-regime signal counts
    - temporal_breakdown.csv: per-scenario per-hour/day signal counts
    """

    def __init__(self, session_dir: Path):
        self._session_dir = session_dir
        self._agg_dir = session_dir / "aggregate"
        self._agg_dir.mkdir(parents=True, exist_ok=True)

        self._csv_path = self._agg_dir / "aggregate_metrics.csv"
        self._health_path = self._agg_dir / "health.jsonl"
        self._summary_path = self._agg_dir / "summary.jsonl"
        self._scenario_matrix_path = self._agg_dir / "scenario_runtime_matrix.csv"
        self._symbol_breakdown_path = self._agg_dir / "symbol_breakdown.csv"
        self._regime_breakdown_path = self._agg_dir / "regime_breakdown.csv"
        self._temporal_breakdown_path = self._agg_dir / "temporal_breakdown.csv"

        self._csv_initialized = False
        self._rows_written = 0
        self._scenario_runtime: Dict[str, Dict[str, Any]] = {}

        # Per-symbol counters: scenario_id -> symbol -> Counter({BUY, SELL, NEUTRAL})
        self._symbol_stats: Dict[str, Dict[str, Counter]] = defaultdict(
            lambda: defaultdict(Counter)
        )
        # Per-regime counters: scenario_id -> regime -> Counter({BUY, SELL, NEUTRAL})
        self._regime_stats: Dict[str, Dict[str, Counter]] = defaultdict(
            lambda: defaultdict(Counter)
        )
        # Temporal counters: scenario_id -> (hour, day_name) -> Counter({BUY, SELL, NEUTRAL})
        self._temporal_stats: Dict[str, Dict[Tuple[int, str], Counter]] = defaultdict(
            lambda: defaultdict(Counter)
        )

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
        self._update_scenario_runtime(result)
        self._update_symbol_stats(result)
        self._update_regime_stats(result)
        self._update_temporal_stats(result)
        self._write_scenario_matrix()

    def log_health(self, event: Dict[str, Any]) -> None:
        """Append health event to aggregate health.jsonl."""
        record = {"ts": time.time(), **event}
        with open(self._health_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        self._update_health_runtime(event)
        self._write_scenario_matrix()

    def log_summary(self, summaries: Dict[str, Dict[str, Any]]) -> None:
        """Write periodic summary from all scenarios."""
        record = {
            "ts": time.time(),
            "scenarios": summaries,
        }
        with open(self._summary_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def flush_breakdowns(self) -> None:
        """Write all breakdown CSVs. Called periodically or at shutdown."""
        self._write_symbol_breakdown()
        self._write_regime_breakdown()
        self._write_temporal_breakdown()

    def _init_csv(self) -> None:
        """Write CSV header if file is new."""
        if not self._csv_path.exists() or self._csv_path.stat().st_size == 0:
            with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writeheader()
        self._csv_initialized = True

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

    # -------------------------------------------------------------------------
    # Per-symbol / per-regime / temporal stats
    # -------------------------------------------------------------------------

    def _update_symbol_stats(self, result: Dict[str, Any]) -> None:
        """Increment per-symbol signal counter."""
        scenario_id = str(result.get("scenario_id", "")).strip()
        symbol = str(result.get("symbol", "")).strip()
        side = str(result.get("side", "NEUTRAL")).upper()
        if scenario_id and symbol and side in {"BUY", "SELL", "NEUTRAL"}:
            self._symbol_stats[scenario_id][symbol][side] += 1

    def _update_regime_stats(self, result: Dict[str, Any]) -> None:
        """Increment per-regime signal counter."""
        scenario_id = str(result.get("scenario_id", "")).strip()
        regime = str(result.get("regime", "DEFAULT")).strip()
        side = str(result.get("side", "NEUTRAL")).upper()
        if scenario_id and regime and side in {"BUY", "SELL", "NEUTRAL"}:
            self._regime_stats[scenario_id][regime][side] += 1

    def _update_temporal_stats(self, result: Dict[str, Any]) -> None:
        """Increment per-hour/day signal counter."""
        scenario_id = str(result.get("scenario_id", "")).strip()
        side = str(result.get("side", "NEUTRAL")).upper()
        ts_ms = result.get("ts_ms")
        if not scenario_id or not ts_ms or side not in {"BUY", "SELL", "NEUTRAL"}:
            return
        try:
            dt = datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=timezone.utc)
            hour = dt.hour
            day_name = dt.strftime("%A")
            self._temporal_stats[scenario_id][(hour, day_name)][side] += 1
        except (OSError, OverflowError, ValueError, TypeError):
            pass

    # -------------------------------------------------------------------------
    # Breakdown CSV writers
    # -------------------------------------------------------------------------

    def _write_symbol_breakdown(self) -> None:
        """Write per-scenario per-symbol signal breakdown CSV."""
        with open(self._symbol_breakdown_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SYMBOL_BREAKDOWN_COLUMNS)
            writer.writeheader()
            for scenario_id in sorted(self._symbol_stats):
                for symbol in sorted(self._symbol_stats[scenario_id]):
                    counts = self._symbol_stats[scenario_id][symbol]
                    total = sum(counts.values())
                    writer.writerow({
                        "scenario_id": scenario_id,
                        "symbol": symbol,
                        "evaluated_rows": total,
                        "BUY_count": counts.get("BUY", 0),
                        "SELL_count": counts.get("SELL", 0),
                        "NEUTRAL_count": counts.get("NEUTRAL", 0),
                        "buy_pct": round(counts.get("BUY", 0) / max(total, 1) * 100, 2),
                        "sell_pct": round(counts.get("SELL", 0) / max(total, 1) * 100, 2),
                    })

    def _write_regime_breakdown(self) -> None:
        """Write per-scenario per-regime signal breakdown CSV."""
        with open(self._regime_breakdown_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=REGIME_BREAKDOWN_COLUMNS)
            writer.writeheader()
            for scenario_id in sorted(self._regime_stats):
                for regime in sorted(self._regime_stats[scenario_id]):
                    counts = self._regime_stats[scenario_id][regime]
                    total = sum(counts.values())
                    writer.writerow({
                        "scenario_id": scenario_id,
                        "regime": regime,
                        "evaluated_rows": total,
                        "BUY_count": counts.get("BUY", 0),
                        "SELL_count": counts.get("SELL", 0),
                        "NEUTRAL_count": counts.get("NEUTRAL", 0),
                        "buy_pct": round(counts.get("BUY", 0) / max(total, 1) * 100, 2),
                        "sell_pct": round(counts.get("SELL", 0) / max(total, 1) * 100, 2),
                    })

    def _write_temporal_breakdown(self) -> None:
        """Write per-scenario temporal signal breakdown CSV."""
        with open(self._temporal_breakdown_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=TEMPORAL_BREAKDOWN_COLUMNS)
            writer.writeheader()
            for scenario_id in sorted(self._temporal_stats):
                for (hour, day_name) in sorted(self._temporal_stats[scenario_id]):
                    counts = self._temporal_stats[scenario_id][(hour, day_name)]
                    total = sum(counts.values())
                    writer.writerow({
                        "scenario_id": scenario_id,
                        "hour_utc": hour,
                        "day_of_week": day_name,
                        "evaluated_rows": total,
                        "BUY_count": counts.get("BUY", 0),
                        "SELL_count": counts.get("SELL", 0),
                        "NEUTRAL_count": counts.get("NEUTRAL", 0),
                        "buy_pct": round(counts.get("BUY", 0) / max(total, 1) * 100, 2),
                    })

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

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "csv_rows": self._rows_written,
            "csv_path": str(self._csv_path),
            "scenario_matrix_path": str(self._scenario_matrix_path),
            "symbol_breakdown_path": str(self._symbol_breakdown_path),
            "regime_breakdown_path": str(self._regime_breakdown_path),
            "temporal_breakdown_path": str(self._temporal_breakdown_path),
        }
