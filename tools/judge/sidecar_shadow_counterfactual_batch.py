#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.judge.analyze_shadow_plan_file import (  # noqa: E402
    infer_file_context,
    write_csv,
    write_json,
)
from tools.judge.sidecar_shadow_counterfactual import (  # noqa: E402
    TARGET_BUCKETS,
    analyze as analyze_single,
    build_calibration_rows,
    choose_recommendations,
    markdown_table,
)


ADDITIVE_FINANCIAL_KEYS = (
    "rows",
    "filled_rows",
    "win_rows",
    "loss_rows",
    "flat_rows",
    "no_fill_rows",
    "tp_hits",
    "sl_hits",
    "filled_timeout_rows",
    "total_net_pnl_pct",
    "total_gross_positive_pct",
    "total_gross_negative_pct",
)


def safe_pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 4)


def safe_mean(total: float, count: float) -> float | None:
    if count == 0:
        return None
    return round(total / count, 6)


def discover_shadow_plan_files(
    *,
    judge_log_dir: Path,
    symbols: set[str] | None,
    dates: set[str] | None,
    max_files: int | None,
) -> list[Path]:
    files = sorted(judge_log_dir.glob("shadow_entry_plan_*.jsonl"))
    selected: list[Path] = []
    for file_path in files:
        context = infer_file_context(file_path)
        if symbols is not None and context.symbol not in symbols:
            continue
        if dates is not None and context.utc_date not in dates:
            continue
        selected.append(file_path)
    if max_files is not None:
        return selected[:max_files]
    return selected


def parse_csv_set(raw_value: str | None) -> set[str] | None:
    if raw_value is None:
        return None
    values = {part.strip() for part in raw_value.split(",") if part.strip()}
    if not values:
        return None
    return values


def empty_financial_accumulator() -> dict[str, float]:
    return {key: 0.0 for key in ADDITIVE_FINANCIAL_KEYS}


def accumulate_financial(accumulator: dict[str, float], payload: Mapping[str, Any]) -> None:
    for key in ADDITIVE_FINANCIAL_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        accumulator[key] += float(value)


def finalize_financial(accumulator: Mapping[str, float]) -> dict[str, Any]:
    rows = int(round(accumulator["rows"]))
    filled_rows = int(round(accumulator["filled_rows"]))
    win_rows = int(round(accumulator["win_rows"]))
    loss_rows = int(round(accumulator["loss_rows"]))
    flat_rows = int(round(accumulator["flat_rows"]))
    no_fill_rows = int(round(accumulator["no_fill_rows"]))
    tp_hits = int(round(accumulator["tp_hits"]))
    sl_hits = int(round(accumulator["sl_hits"]))
    filled_timeout_rows = int(round(accumulator["filled_timeout_rows"]))
    total_net_pnl_pct = round(accumulator["total_net_pnl_pct"], 6)
    total_gross_positive_pct = round(
        accumulator["total_gross_positive_pct"], 6)
    total_gross_negative_pct = round(
        accumulator["total_gross_negative_pct"], 6)
    gross_loss_abs = abs(total_gross_negative_pct)
    profit_factor = None
    if gross_loss_abs > 0:
        profit_factor = round(total_gross_positive_pct / gross_loss_abs, 6)
    return {
        "rows": rows,
        "filled_rows": filled_rows,
        "win_rows": win_rows,
        "loss_rows": loss_rows,
        "flat_rows": flat_rows,
        "no_fill_rows": no_fill_rows,
        "tp_hits": tp_hits,
        "sl_hits": sl_hits,
        "filled_timeout_rows": filled_timeout_rows,
        "proposal_win_rate_pct": safe_pct(win_rows, rows),
        "filled_trade_win_rate_pct": safe_pct(win_rows, filled_rows),
        "fill_rate_pct": safe_pct(filled_rows, rows),
        "tp_rate_on_proposals_pct": safe_pct(tp_hits, rows),
        "tp_rate_on_filled_pct": safe_pct(tp_hits, filled_rows),
        "total_net_pnl_pct": total_net_pnl_pct,
        "total_gross_positive_pct": total_gross_positive_pct,
        "total_gross_negative_pct": total_gross_negative_pct,
        "expectancy_net_pnl_pct": safe_mean(total_net_pnl_pct, rows),
        "expectancy_filled_net_pnl_pct": safe_mean(total_net_pnl_pct, filled_rows),
        "median_net_pnl_pct": None,
        "median_filled_net_pnl_pct": None,
        "profit_factor": profit_factor,
    }


def scenario_accumulator() -> dict[str, Any]:
    return {
        "spec": None,
        "financial": empty_financial_accumulator(),
        "target_combined": empty_financial_accumulator(),
        "target_by_bucket": {bucket: empty_financial_accumulator() for bucket in TARGET_BUCKETS},
        "managed_exit_rows": 0,
        "file_count": 0,
    }


def build_batch_report(summary: Mapping[str, Any], output_dir: Path) -> str:
    meta = summary["meta"]
    recommendations = summary["recommendations"]
    balanced = recommendations.get("balanced_recommendation")
    current_config = recommendations.get("current_config_leader")
    per_file_rows = summary["per_file_recommendations"]
    lines = [
        "# Sidecar Shadow Counterfactual Batch Report",
        "",
        "## Coverage",
        f"- Files processed: {summary['counts']['files_processed']}",
        f"- Files failed: {summary['counts']['files_failed']}",
        f"- Judge log dir: {meta['judge_log_dir']}",
        f"- Output root: {output_dir.as_posix()}",
        f"- Symbols filter: {meta['symbols_filter']}",
        f"- Dates filter: {meta['dates_filter']}",
        "",
        "## Overall Recommendation",
    ]
    if balanced is None:
        lines.append(
            "- No balanced scenario satisfied the aggregate managed-exit guardrail.")
    else:
        lines.append(
            f"- Balanced recommendation: {balanced['scenario_name']} (arm={balanced['arm_pct']}%, giveback={balanced['giveback_trigger_pct']}%, target_total_net={balanced['target_total_net_pnl_pct']}, managed_exit_rows={balanced['managed_exit_rows']})"
        )
    if current_config is not None:
        lines.append(
            f"- Best current-config scenario: {current_config['scenario_name']} (target_total_net={current_config['target_total_net_pnl_pct']}, managed_exit_rows={current_config['managed_exit_rows']})"
        )
    lines.extend([
        "",
        "## Representative Aggregate Scenarios",
    ])
    scenario_rows = []
    representative_names = [
        meta["baseline_scenario_name"],
        meta["no_timeout_scenario_name"],
        current_config["scenario_name"] if current_config else None,
        balanced["scenario_name"] if balanced else None,
    ]
    seen_names: set[str] = set()
    for name in representative_names:
        if not name or name in seen_names or name not in summary["scenario_summaries"]:
            continue
        seen_names.add(name)
        item = summary["scenario_summaries"][name]
        scenario_rows.append(
            (
                name,
                item["financial"]["rows"],
                item["financial"]["proposal_win_rate_pct"],
                item["financial"]["total_net_pnl_pct"],
                item["target_buckets"]["combined"]["proposal_win_rate_pct"],
                item["target_buckets"]["combined"]["total_net_pnl_pct"],
                item["managed_exit_rows"],
            )
        )
    lines.extend(
        markdown_table(
            (
                "scenario",
                "rows",
                "overall_win_rate",
                "overall_total_net",
                "target_win_rate",
                "target_total_net",
                "managed_exits",
            ),
            scenario_rows,
        )
    )
    lines.extend([
        "",
        "## Top Aggregate Calibration Grid",
    ])
    top_grid = summary["calibration_grid"][:15]
    lines.extend(
        markdown_table(
            (
                "scenario",
                "arm_pct",
                "giveback_pct",
                "managed_exits",
                "target_net",
                "target_win_rate",
                "overall_net",
            ),
            [
                (
                    row["scenario_name"],
                    row["arm_pct"],
                    row["giveback_trigger_pct"],
                    row["managed_exit_rows"],
                    row["target_total_net_pnl_pct"],
                    row["target_win_rate_pct"],
                    row["overall_total_net_pnl_pct"],
                )
                for row in top_grid
            ],
        )
    )
    lines.extend([
        "",
        "## Per-File Balanced Picks",
    ])
    lines.extend(
        markdown_table(
            (
                "symbol",
                "date",
                "balanced_scenario",
                "balanced_target_net",
                "current_config_scenario",
                "current_config_target_net",
            ),
            [
                (
                    row["symbol"],
                    row["utc_date"],
                    row["balanced_scenario_name"],
                    row["balanced_target_total_net_pnl_pct"],
                    row["current_config_scenario_name"],
                    row["current_config_target_total_net_pnl_pct"],
                )
                for row in per_file_rows
            ],
        )
    )
    return "\n".join(lines) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Sidecar shadow counterfactual calibration over all available shadow-plan files.")
    parser.add_argument("--judge-log-dir", type=Path,
                        default=REPO_ROOT / "logs" / "judge_experts")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "reports" /
                        "judge" / "sidecar_shadow_counterfactual_batch_all_available")
    parser.add_argument("--recorder-root", type=Path,
                        default=REPO_ROOT / "data" / "recorder")
    parser.add_argument("--config-dir", type=Path,
                        default=REPO_ROOT / "config" / "aurora")
    parser.add_argument("--baseline-max-bars-after-signal",
                        type=int, default=12)
    parser.add_argument("--intrabar-ambiguity-policy", choices=[
                        "mark_ambiguous", "prioritize_sl", "prioritize_tp"], default="mark_ambiguous")
    parser.add_argument("--fees-bps", type=float, default=2.0)
    parser.add_argument("--slippage-bps", type=float, default=1.0)
    parser.add_argument("--arm-pcts", type=str, default=None)
    parser.add_argument("--giveback-trigger-pcts", type=str, default=None)
    parser.add_argument("--min-managed-exit-rows", type=int, default=40)
    parser.add_argument("--symbols", type=str, default=None)
    parser.add_argument("--dates", type=str, default=None)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--progress-heartbeat-sec", type=int, default=15)
    return parser.parse_args(argv)


def analyze_batch(args: argparse.Namespace) -> dict[str, Any]:
    symbols = parse_csv_set(args.symbols)
    dates = parse_csv_set(args.dates)
    shadow_plan_files = discover_shadow_plan_files(
        judge_log_dir=args.judge_log_dir,
        symbols=symbols,
        dates=dates,
        max_files=args.max_files,
    )
    if not shadow_plan_files:
        raise FileNotFoundError(
            "No shadow_entry_plan files matched the requested filters.")

    print(
        json.dumps(
            {
                "phase": "batch_start",
                "files_requested": len(shadow_plan_files),
                "symbols_filter": sorted(symbols) if symbols is not None else "ALL",
                "dates_filter": sorted(dates) if dates is not None else "ALL",
            },
            ensure_ascii=True,
        ),
        flush=True,
    )

    per_file_output_root = args.output_dir / "per_file"
    scenario_summaries_acc: dict[str, dict[str, Any]
                                 ] = defaultdict(scenario_accumulator)
    per_file_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    baseline_name = f"baseline_timeout_{args.baseline_max_bars_after_signal}"
    no_timeout_name = "no_timeout_hold_to_data_end"
    heartbeat_sec = max(1, int(args.progress_heartbeat_sec))

    for index, shadow_plan_file in enumerate(shadow_plan_files, start=1):
        context = infer_file_context(shadow_plan_file)
        print(
            json.dumps(
                {
                    "phase": "file_start",
                    "file_index": index,
                    "file_count": len(shadow_plan_files),
                    "symbol": context.symbol,
                    "utc_date": context.utc_date,
                    "source_file": shadow_plan_file.as_posix(),
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
        file_args = argparse.Namespace(
            shadow_plan_file=shadow_plan_file,
            recorder_root=args.recorder_root,
            output_dir=per_file_output_root / shadow_plan_file.stem,
            baseline_max_bars_after_signal=args.baseline_max_bars_after_signal,
            intrabar_ambiguity_policy=args.intrabar_ambiguity_policy,
            fees_bps=args.fees_bps,
            slippage_bps=args.slippage_bps,
            config_dir=args.config_dir,
            arm_pcts=args.arm_pcts,
            giveback_trigger_pcts=args.giveback_trigger_pcts,
            min_managed_exit_rows=args.min_managed_exit_rows,
        )
        heartbeat_stop = threading.Event()

        def emit_heartbeat() -> None:
            beat = 0
            while not heartbeat_stop.wait(heartbeat_sec):
                beat += 1
                print(
                    json.dumps(
                        {
                            "phase": "file_heartbeat",
                            "file_index": index,
                            "file_count": len(shadow_plan_files),
                            "symbol": context.symbol,
                            "utc_date": context.utc_date,
                            "heartbeat_index": beat,
                        },
                        ensure_ascii=True,
                    ),
                    flush=True,
                )

        heartbeat_thread = threading.Thread(target=emit_heartbeat, daemon=True)
        heartbeat_thread.start()
        try:
            summary = analyze_single(file_args)
        except Exception as exc:  # noqa: BLE001
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1.0)
            failures.append(
                {
                    "source_file": shadow_plan_file.as_posix(),
                    "symbol": context.symbol,
                    "utc_date": context.utc_date,
                    "error": str(exc),
                }
            )
            print(
                json.dumps(
                    {
                        "phase": "file_failed",
                        "file_index": index,
                        "file_count": len(shadow_plan_files),
                        "symbol": context.symbol,
                        "utc_date": context.utc_date,
                        "error": str(exc),
                    },
                    ensure_ascii=True,
                ),
                flush=True,
            )
            continue
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=1.0)

        recommendations = summary.get("recommendations", {})
        balanced = recommendations.get("balanced_recommendation") or {}
        current_config = recommendations.get("current_config_leader") or {}
        per_file_rows.append(
            {
                "source_file": shadow_plan_file.as_posix(),
                "symbol": context.symbol,
                "utc_date": context.utc_date,
                "balanced_scenario_name": balanced.get("scenario_name"),
                "balanced_target_total_net_pnl_pct": balanced.get("target_total_net_pnl_pct"),
                "balanced_target_win_rate_pct": balanced.get("target_win_rate_pct"),
                "balanced_managed_exit_rows": balanced.get("managed_exit_rows"),
                "current_config_scenario_name": current_config.get("scenario_name"),
                "current_config_target_total_net_pnl_pct": current_config.get("target_total_net_pnl_pct"),
                "current_config_target_win_rate_pct": current_config.get("target_win_rate_pct"),
                "current_config_managed_exit_rows": current_config.get("managed_exit_rows"),
                "no_timeout_target_total_net_pnl_pct": summary["scenario_summaries"][no_timeout_name]["target_buckets"]["combined"]["total_net_pnl_pct"],
            }
        )

        for scenario_name, scenario_summary in summary["scenario_summaries"].items():
            accumulator = scenario_summaries_acc[scenario_name]
            accumulator["spec"] = dict(scenario_summary["spec"])
            accumulate_financial(
                accumulator["financial"], scenario_summary["financial"])
            accumulate_financial(
                accumulator["target_combined"], scenario_summary["target_buckets"]["combined"])
            for bucket_name in TARGET_BUCKETS:
                bucket_summary = scenario_summary["target_buckets"]["by_bucket"].get(
                    bucket_name)
                if bucket_summary is None:
                    continue
                accumulate_financial(
                    accumulator["target_by_bucket"][bucket_name], bucket_summary)
            accumulator["managed_exit_rows"] += int(
                scenario_summary["managed_exit_rows"])
            accumulator["file_count"] += 1

        print(
            json.dumps(
                {
                    "phase": "file_done",
                    "file_index": index,
                    "file_count": len(shadow_plan_files),
                    "symbol": context.symbol,
                    "utc_date": context.utc_date,
                    "balanced_scenario": balanced.get("scenario_name"),
                    "balanced_target_total_net_pnl_pct": balanced.get("target_total_net_pnl_pct"),
                },
                ensure_ascii=True,
            ),
            flush=True,
        )

    finalized_scenario_summaries: dict[str, Any] = {}
    for scenario_name, accumulator in sorted(scenario_summaries_acc.items()):
        finalized_scenario_summaries[scenario_name] = {
            "spec": accumulator["spec"],
            "financial": finalize_financial(accumulator["financial"]),
            "target_buckets": {
                "combined": finalize_financial(accumulator["target_combined"]),
                "by_bucket": {
                    bucket_name: finalize_financial(
                        accumulator["target_by_bucket"][bucket_name])
                    for bucket_name in TARGET_BUCKETS
                },
            },
            "managed_exit_rows": accumulator["managed_exit_rows"],
            "file_count": accumulator["file_count"],
        }

    scaled_min_managed_exit_rows = args.min_managed_exit_rows * \
        max(1, len(per_file_rows))
    calibration_grid = build_calibration_rows(
        finalized_scenario_summaries, no_timeout_name=no_timeout_name)
    recommendations = choose_recommendations(
        calibration_grid,
        min_managed_exit_rows=scaled_min_managed_exit_rows,
        config_arm_pcts=[0.02, 0.05, 0.07],
        default_giveback_trigger_pct=50.0,
    )

    summary = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "judge_log_dir": args.judge_log_dir.as_posix(),
            "output_dir": args.output_dir.as_posix(),
            "recorder_root": args.recorder_root.as_posix(),
            "symbols_filter": sorted(symbols) if symbols is not None else "ALL",
            "dates_filter": sorted(dates) if dates is not None else "ALL",
            "baseline_scenario_name": baseline_name,
            "no_timeout_scenario_name": no_timeout_name,
            "per_file_min_managed_exit_rows": args.min_managed_exit_rows,
            "aggregate_min_managed_exit_rows": scaled_min_managed_exit_rows,
        },
        "counts": {
            "files_requested": len(shadow_plan_files),
            "files_processed": len(per_file_rows),
            "files_failed": len(failures),
            "scenario_count": len(finalized_scenario_summaries),
        },
        "failures": failures,
        "scenario_summaries": finalized_scenario_summaries,
        "calibration_grid": calibration_grid,
        "recommendations": recommendations,
        "per_file_recommendations": per_file_rows,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "summary.json", summary)
    write_csv(args.output_dir / "per_file_recommendations.csv", per_file_rows)
    write_csv(args.output_dir /
              "aggregate_calibration_grid.csv", calibration_grid)
    report = build_batch_report(summary, args.output_dir)
    (args.output_dir / "report.md").write_text(report, encoding="utf-8")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = analyze_batch(args)
    balanced = summary["recommendations"].get("balanced_recommendation") or {}
    print(
        json.dumps(
            {
                "output_dir": args.output_dir.as_posix(),
                "files_processed": summary["counts"]["files_processed"],
                "files_failed": summary["counts"]["files_failed"],
                "balanced_scenario": balanced.get("scenario_name"),
                "balanced_target_total_net_pnl_pct": balanced.get("target_total_net_pnl_pct"),
                "balanced_managed_exit_rows": balanced.get("managed_exit_rows"),
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
