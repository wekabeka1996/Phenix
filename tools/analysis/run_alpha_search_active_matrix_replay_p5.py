#!/usr/bin/env python3
"""Deterministic P5 per-scenario alpha_search replay harness.

Runs active scenario_matrix.yaml scenarios one at a time over the replay input.
This is replay infrastructure only: it reuses ScenarioWorker and does not change
strategy configuration or decision authority.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from apps.reference.domains.alpha_search.runtime.config_resolver import (
    persist_effective_config,
    resolve_scenario_config,
)
from apps.reference.domains.alpha_search.runtime.contracts import AlphaInputV1
from apps.reference.domains.alpha_search.runtime.launcher import load_matrix_config
from apps.reference.domains.alpha_search.runtime.scenario_worker import ScenarioWorker
from apps.reference.domains.alpha_search.runtime.shadow_book import ShadowBook


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "alpha_search_cost_truth"
MATRIX_DIR = REPORT_DIR / "p5_matrices"
LOG_ROOT = ROOT / "logs" / "alpha_search_runtime"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _profit_factor(values: Iterable[float]) -> float:
    vals = list(values)
    gross_profit = sum(v for v in vals if v > 0.0)
    gross_loss = abs(sum(v for v in vals if v < 0.0))
    if gross_loss > 0.0:
        return round(gross_profit / gross_loss, 4)
    return 999.0 if gross_profit > 0.0 else 0.0


def _drawdown(values: Iterable[float]) -> float:
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return round(max_dd, 4)


def _breakeven_cost_bps(raw_pnl: float, notional_size: float, trades: int) -> float:
    if notional_size <= 0.0 or trades <= 0:
        return 0.0
    return round((raw_pnl / (notional_size * trades)) * 10000.0, 4)


def _classify(metrics: Dict[str, Any], completed: bool, cost_fields_present: bool) -> str:
    if not completed:
        run_classification = str(metrics.get("run_classification", "INVALID_OUTPUT"))
        if run_classification == "NOT_RUN_DUE_TO_TIMEBOX":
            return "NOT_RUN_DUE_TO_TIMEBOX"
        if run_classification == "TIMED_OUT":
            return "TIMED_OUT"
        return run_classification
    if not cost_fields_present:
        return "INVALID_OUTPUT"
    total_trades = int(metrics.get("total_trades") or 0)
    if total_trades <= 0:
        return "NO_TRADES"
    net_pnl = _safe_float(metrics.get("net_pnl_after_cost"))
    raw_pnl = _safe_float(metrics.get("raw_cumulative_pnl"))
    net_pf = _safe_float(metrics.get("net_profit_factor_after_cost"))
    if net_pnl > 0.0 and total_trades < 100:
        return "LOW_SAMPLE_COST_PROFIT_CANDIDATE"
    if net_pnl > 0.0 and net_pf > 1.05 and total_trades >= 100:
        return "COST_PROFIT_CANDIDATE"
    if raw_pnl > 0.0 and net_pnl < 0.0:
        return "RAW_POSITIVE_COST_NEGATIVE"
    return "RAW_NEGATIVE"


def _load_input(path: Path, max_rows: Optional[int] = None) -> List[AlphaInputV1]:
    snapshots: List[AlphaInputV1] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                snapshots.append(AlphaInputV1.model_validate_json(line))
                if max_rows is not None and len(snapshots) >= max_rows:
                    break
    return snapshots


def _disable_replay_diagnostic_logs(alpha_cfg: Any) -> Any:
    """Disable replay-only judge JSONL sidecars without changing judge decisions."""
    judge_cfg = getattr(alpha_cfg, "judge", None)
    shadow_log = getattr(judge_cfg, "shadow_log", None)
    if judge_cfg is None or shadow_log is None or not getattr(shadow_log, "enabled", False):
        return alpha_cfg
    return alpha_cfg.model_copy(
        update={
            "judge": judge_cfg.model_copy(
                update={"shadow_log": shadow_log.model_copy(update={"enabled": False})}
            )
        }
    )


def _input_meta(snapshots: List[AlphaInputV1], input_path: Path) -> Dict[str, Any]:
    return {
        "input_path": str(input_path),
        "input_rows_expected": len(snapshots),
        "symbols": "|".join(sorted({s.symbol for s in snapshots})),
        "tf_secs": "|".join(str(v) for v in sorted({s.tf_sec for s in snapshots})),
        "timestamp_min": min((s.ts_ms for s in snapshots), default=""),
        "timestamp_max": max((s.ts_ms for s in snapshots), default=""),
    }


def _write_one_scenario_matrix(raw_matrix: Dict[str, Any], scenario_id: str) -> Path:
    MATRIX_DIR.mkdir(parents=True, exist_ok=True)
    matrix = dict(raw_matrix)
    matrix["matrix_id"] = f"p5_single_{scenario_id}"
    matrix["input"] = dict(matrix.get("input") or {})
    matrix["input"]["source_mode"] = "replay"
    matrix["input"]["stream_path"] = "logs/alpha_input/alpha_input_v1.jsonl"
    runtime = dict(matrix.get("runtime") or {})
    runtime["max_scenarios"] = 1
    runtime["max_concurrent_scenarios"] = 1
    runtime["parallelism"] = "sequential"
    runtime["max_workers"] = 1
    matrix["runtime"] = runtime
    matrix["hot_reload"] = {**dict(matrix.get("hot_reload") or {}), "enabled": False}
    scenarios = [s for s in raw_matrix.get("scenarios", []) if s.get("scenario_id") == scenario_id]
    if len(scenarios) != 1:
        raise ValueError(f"Expected one scenario for {scenario_id}, found {len(scenarios)}")
    matrix["scenarios"] = scenarios
    path = MATRIX_DIR / f"{scenario_id}.yaml"
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(matrix, handle, sort_keys=False, allow_unicode=True)
    return path


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")


def _metrics_from_trades(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    raw_values = [_safe_float(t.get("raw_pnl", t.get("pnl"))) for t in trades]
    net_values = [_safe_float(t.get("net_pnl_after_cost")) for t in trades]
    fee_values = [_safe_float(t.get("fee_cost", t.get("fees"))) for t in trades]
    slippage_values = [_safe_float(t.get("slippage_cost", t.get("slippage"))) for t in trades]
    total_cost_values = [_safe_float(t.get("total_cost")) for t in trades]
    cost_fields_present = all("net_pnl_after_cost" in t for t in trades) if trades else True
    raw_sum = round(sum(raw_values), 4)
    notional_values = sorted({_safe_float(t.get("notional_size")) for t in trades if t.get("notional_size")})
    notional_size = notional_values[0] if notional_values else 5000.0
    cost_model_ids = sorted({str(t.get("cost_model_id")) for t in trades if t.get("cost_model_id")})
    cost_model_sources = sorted({str(t.get("cost_model_source")) for t in trades if t.get("cost_model_source")})
    return {
        "total_trades": len(trades),
        "raw_cumulative_pnl": raw_sum,
        "cumulative_fee_cost": round(sum(fee_values), 4),
        "cumulative_slippage_cost": round(sum(slippage_values), 4),
        "cumulative_total_cost": round(sum(total_cost_values), 4),
        "net_pnl_after_cost": round(sum(net_values), 4),
        "raw_profit_factor": _profit_factor(raw_values),
        "net_profit_factor_after_cost": _profit_factor(net_values),
        "raw_max_drawdown": _drawdown(raw_values),
        "net_max_drawdown": _drawdown(net_values),
        "win_rate": round(sum(1 for v in raw_values if v > 0.0) / max(len(raw_values), 1), 4),
        "breakeven_cost_bps_per_cycle": _breakeven_cost_bps(raw_sum, notional_size, len(trades)),
        "cost_model_id": "|".join(cost_model_ids),
        "cost_model_source": "|".join(cost_model_sources),
        "notional_size": notional_size,
        "cost_fields_present": str(cost_fields_present).lower(),
    }


def _run_scenario(
    *,
    scenario_id: str,
    matrix_path: Path,
    snapshots: List[AlphaInputV1],
    session_root: Path,
    scenario_timeout_sec: Optional[float],
    disable_replay_diagnostic_logs: bool,
) -> Dict[str, Any]:
    start = time.monotonic()
    config = load_matrix_config(matrix_path, registry_source_mode="replay")
    spec = config.scenarios[0]
    scenario_dir = session_root / scenario_id
    scenario_dir.mkdir(parents=True, exist_ok=True)
    alpha_cfg, system_cfg, strategy_cfg = resolve_scenario_config(spec, ROOT)
    if disable_replay_diagnostic_logs:
        alpha_cfg = _disable_replay_diagnostic_logs(alpha_cfg)
    persist_effective_config(
        scenario_id=scenario_id,
        alpha_search_config=alpha_cfg,
        system_config=system_cfg,
        strategy_config=strategy_cfg,
        output_dir=scenario_dir,
    )
    shadow_book = ShadowBook(scenario_id=scenario_id, notional_size=alpha_cfg.virtual_trader.notional_size)
    worker = ScenarioWorker(
        spec=spec,
        alpha_search_config=alpha_cfg,
        system_config=system_cfg,
        strategy_config=strategy_cfg,
        log_dir=scenario_dir,
        shadow_book=shadow_book,
    )

    processed = 0
    run_classification = "COMPLETED"
    graceful_shutdown = False
    try:
        for snapshot in snapshots:
            worker.process_snapshot(snapshot)
            processed += 1
            if scenario_timeout_sec and time.monotonic() - start > scenario_timeout_sec:
                run_classification = "TIMED_OUT"
                break
        if run_classification == "COMPLETED":
            graceful_shutdown = True
    finally:
        worker.shutdown()

    trades: List[Dict[str, Any]] = []
    if run_classification == "COMPLETED":
        for provider_id, rows in worker.closed_positions.items():
            for row in rows:
                trades.append({"scenario_id": scenario_id, "provider_id": provider_id, **row})
        _write_jsonl(scenario_dir / "trades.jsonl", trades)
    else:
        _write_jsonl(scenario_dir / "trades_incomplete_not_economic.jsonl", [])

    duration = round(time.monotonic() - start, 3)
    metrics = _metrics_from_trades(trades) if run_classification == "COMPLETED" else {
        "total_trades": "",
        "raw_cumulative_pnl": "",
        "cumulative_fee_cost": "",
        "cumulative_slippage_cost": "",
        "cumulative_total_cost": "",
        "net_pnl_after_cost": "",
        "raw_profit_factor": "",
        "net_profit_factor_after_cost": "",
        "raw_max_drawdown": "",
        "net_max_drawdown": "",
        "win_rate": "",
        "breakeven_cost_bps_per_cycle": "",
        "cost_model_id": "alpha_search_runtime_judge_equivalent_v1",
        "cost_model_source": "config/alpha_search.yaml#alpha_search.virtual_trader.runtime_cost",
        "notional_size": float(alpha_cfg.virtual_trader.notional_size),
        "cost_fields_present": "false",
    }
    completed = run_classification == "COMPLETED"
    classification = _classify(metrics, completed, metrics.get("cost_fields_present") == "true")
    return {
        "scenario_id": scenario_id,
        "matrix_path_used": str(matrix_path),
        "command": f"in-process ScenarioWorker replay via {Path(__file__).as_posix()} --scenario {scenario_id}",
        "exit_status": 0 if completed else 124,
        "duration_sec": duration,
        "session_path": str(scenario_dir),
        "input_rows_expected": len(snapshots),
        "input_rows_processed": processed,
        "graceful_shutdown": str(graceful_shutdown).lower(),
        "trades_jsonl_present": str((scenario_dir / "trades.jsonl").exists()).lower(),
        "cost_fields_present": metrics.get("cost_fields_present", "false"),
        "run_classification": run_classification,
        **metrics,
        "classification": classification,
    }


def _write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", default="config/alpha_search/scenario_matrix.yaml")
    parser.add_argument("--input", default="logs/alpha_input/alpha_input_v1.jsonl")
    parser.add_argument("--scenario", action="append", default=None)
    parser.add_argument("--max-scenarios", type=int, default=None)
    parser.add_argument("--scenario-timeout-sec", type=float, default=None)
    parser.add_argument("--overall-timebox-sec", type=float, default=None)
    parser.add_argument("--max-input-rows", type=int, default=None)
    parser.add_argument(
        "--keep-replay-diagnostic-logs",
        action="store_true",
        help="Keep high-volume judge sidecar JSONL logs during replay profiling.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    matrix_path = ROOT / args.matrix
    input_path = ROOT / args.input
    with matrix_path.open("r", encoding="utf-8") as handle:
        raw_matrix = yaml.safe_load(handle)
    config = load_matrix_config(matrix_path, registry_source_mode="replay")
    active_ids = [s.scenario_id for s in config.scenarios if s.enabled]
    selected = [sid for sid in active_ids if args.scenario is None or sid in set(args.scenario)]
    if args.max_scenarios is not None:
        selected = selected[: args.max_scenarios]

    matrix_paths = {sid: _write_one_scenario_matrix(raw_matrix, sid) for sid in selected}
    if args.dry_run:
        for sid in selected:
            print(f"{sid},{matrix_paths[sid]}")
        return 0

    snapshots = _load_input(input_path, max_rows=args.max_input_rows)
    meta = _input_meta(snapshots, input_path)
    session_root = LOG_ROOT / f"p5_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    session_root.mkdir(parents=True, exist_ok=True)
    (session_root / "input_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    manifest: List[Dict[str, Any]] = []
    overall_start = time.monotonic()
    for sid in selected:
        if args.overall_timebox_sec and time.monotonic() - overall_start > args.overall_timebox_sec:
            manifest.append({
                "scenario_id": sid,
                "matrix_path_used": str(matrix_paths[sid]),
                "command": f"not run; overall timebox {args.overall_timebox_sec}s exhausted",
                "exit_status": "",
                "duration_sec": "",
                "session_path": "",
                "input_rows_expected": len(snapshots),
                "input_rows_processed": 0,
                "graceful_shutdown": "false",
                "trades_jsonl_present": "false",
                "cost_fields_present": "false",
                "run_classification": "NOT_RUN_DUE_TO_TIMEBOX",
            })
            continue
        result = _run_scenario(
            scenario_id=sid,
            matrix_path=matrix_paths[sid],
            snapshots=snapshots,
            session_root=session_root,
            scenario_timeout_sec=args.scenario_timeout_sec,
            disable_replay_diagnostic_logs=not args.keep_replay_diagnostic_logs,
        )
        manifest.append(result)
        print(json.dumps(result, ensure_ascii=False))

    manifest_fields = [
        "scenario_id", "matrix_path_used", "command", "exit_status", "duration_sec",
        "session_path", "input_rows_expected", "input_rows_processed", "graceful_shutdown",
        "trades_jsonl_present", "cost_fields_present", "run_classification",
    ]
    metric_fields = [
        "scenario_id", "total_trades", "raw_cumulative_pnl", "cumulative_fee_cost",
        "cumulative_slippage_cost", "cumulative_total_cost", "net_pnl_after_cost",
        "raw_profit_factor", "net_profit_factor_after_cost", "raw_max_drawdown",
        "net_max_drawdown", "win_rate", "breakeven_cost_bps_per_cycle",
        "cost_model_id", "cost_model_source", "notional_size", "classification",
    ]
    _write_csv(REPORT_DIR / "alpha_search_p5_scenario_run_manifest.csv", manifest, manifest_fields)
    completed = [r for r in manifest if r.get("run_classification") == "COMPLETED"]
    _write_csv(REPORT_DIR / "alpha_search_p5_completed_metrics.csv", completed, metric_fields)
    ranked = sorted(completed, key=lambda r: _safe_float(r.get("net_pnl_after_cost")), reverse=True)
    for index, row in enumerate(ranked, start=1):
        row["rank_after_cost"] = index
    _write_csv(REPORT_DIR / "alpha_search_p5_ranking_after_cost.csv", ranked, ["rank_after_cost", *metric_fields])
    incomplete = [r for r in manifest if r.get("run_classification") != "COMPLETED"]
    _write_csv(REPORT_DIR / "alpha_search_p5_incomplete_or_failed.csv", incomplete, manifest_fields)
    print(json.dumps({"session_root": str(session_root), "selected": selected, "completed": len(completed)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
