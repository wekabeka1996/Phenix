from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .cli import run_backtest
from .reconstruct import reconstruct_canonical_entries
from .reporting import write_json


LIMITATIONS = [
    "Diagnostic scenario harness is a retained-trace diagnostic substrate, not parity proof.",
    "It does not simulate adapters, async races, websocket ordering, or portfolio mutation side effects end-to-end.",
    "Threshold provenance is limited to retained entry/runtime surfaces available in reconstructed canonical entries and scenario artifacts.",
]


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _summarize_reject_families(report_root: Path, scenario_ids: Iterable[str]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str, str], int] = Counter()
    for scenario_id in scenario_ids:
        blocked_rows = _load_csv_rows(report_root / scenario_id / "blocked_entries.csv")
        for row in blocked_rows:
            key = (
                str(scenario_id),
                str(row.get("gate_id") or "UNKNOWN"),
                str(row.get("reason") or "UNKNOWN"),
            )
            counts[key] += 1
    return [
        {"scenario_id": scenario_id, "gate_id": gate_id, "reason": reason, "count": count}
        for (scenario_id, gate_id, reason), count in sorted(counts.items())
    ]


def _threshold_provenance(entries: list[Any]) -> dict[str, Any]:
    min_sources = Counter()
    max_sources = Counter()
    for entry in entries:
        min_sources[str(entry.resolved_min_regime_confidence_source or "missing")] += 1
        max_sources[str(entry.resolved_max_regime_confidence_source or "missing")] += 1
    return {
        "resolved_min_regime_confidence_source_counts": dict(sorted(min_sources.items())),
        "resolved_max_regime_confidence_source_counts": dict(sorted(max_sources.items())),
        "entries_with_min_threshold": sum(1 for entry in entries if entry.resolved_min_regime_confidence is not None),
        "entries_with_max_threshold": sum(1 for entry in entries if entry.resolved_max_regime_confidence is not None),
    }


def _actual_vs_counterfactual_table(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    scenario_summaries = manifest.get("scenario_summaries", {}) or {}
    baseline = scenario_summaries.get("tp_sl_only", {}) or {}
    rows: list[dict[str, Any]] = []
    for scenario_id, summary in sorted(scenario_summaries.items()):
        rows.append(
            {
                "scenario_id": scenario_id,
                "trades": int(summary.get("trades", 0)),
                "blocked_entries": int(summary.get("blocked_entries", 0)),
                "wins": int(summary.get("wins", 0)),
                "losses": int(summary.get("losses", 0)),
                "avg_net_roi": float(summary.get("avg_net_roi", 0.0)),
                "total_net_roi": float(summary.get("total_net_roi", 0.0)),
                "delta_trades_vs_tp_sl_only": int(summary.get("trades", 0)) - int(baseline.get("trades", 0)),
                "delta_total_net_roi_vs_tp_sl_only": round(
                    float(summary.get("total_net_roi", 0.0)) - float(baseline.get("total_net_roi", 0.0)),
                    8,
                ),
            }
        )
    return rows


def _diagnostic_summary(
    manifest: dict[str, Any],
    entries: list[Any],
    reject_matrix: list[dict[str, Any]],
    *,
    mode: str,
    tolerance_pct: float,
) -> dict[str, Any]:
    scenario_summaries = manifest.get("scenario_summaries", {}) or {}
    actual_summary = scenario_summaries.get("tp_sl_only", {}) or {}
    opened_by_symbol = Counter(entry.symbol for entry in entries)
    reject_counts_by_scenario = defaultdict(int)
    for row in reject_matrix:
        reject_counts_by_scenario[str(row["scenario_id"])] += int(row["count"])
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "status": str(manifest.get("status", "")),
        "canonical_entries": int(manifest.get("canonical_entries", 0)),
        "actual_opened_count": len(entries),
        "actual_realized_count": int(actual_summary.get("resolved_trades", 0)),
        "opened_by_symbol": dict(sorted(opened_by_symbol.items())),
        "reject_counts_by_scenario": dict(sorted(reject_counts_by_scenario.items())),
        "tolerance_pct": tolerance_pct,
        "threshold_provenance_retained": True,
        "limitations": LIMITATIONS,
    }


def write_limitations(report_root: Path) -> None:
    path = report_root / "diagnostic_limitations.md"
    lines = ["# Diagnostic Scenario Harness Limitations", ""]
    lines.extend(f"- {item}" for item in LIMITATIONS)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_diagnostic_scenario_harness(
    *,
    workspace_root: Path,
    runtime_root: Path,
    report_root: Path,
    recorder_root: Path,
    extra_recorder_roots: Iterable[Path | str] | None = None,
    scenarios: str = "all",
    strict: bool = True,
    mode: str = "both",
    tolerance_pct: float = 0.10,
) -> dict[str, Any]:
    manifest = run_backtest(
        workspace_root=workspace_root,
        runtime_root=runtime_root,
        report_root=report_root,
        recorder_root=recorder_root,
        extra_recorder_roots=extra_recorder_roots,
        scenarios=scenarios,
        strict=strict,
    )
    entries, _, _ = reconstruct_canonical_entries(workspace_root, runtime_root, report_root)
    scenario_ids = (manifest.get("scenario_summaries") or {}).keys()
    reject_matrix = _summarize_reject_families(report_root, scenario_ids)
    provenance = _threshold_provenance(entries)
    comparison_rows = _actual_vs_counterfactual_table(manifest)
    summary = _diagnostic_summary(
        manifest,
        entries,
        reject_matrix,
        mode=mode,
        tolerance_pct=tolerance_pct,
    )

    write_json(report_root / "diagnostic_summary.json", summary)
    write_json(report_root / "diagnostic_reject_family_matrix.json", {"rows": reject_matrix})
    write_json(report_root / "diagnostic_threshold_provenance.json", provenance)
    write_json(report_root / "diagnostic_actual_vs_counterfactual_results.json", {"rows": comparison_rows})
    write_limitations(report_root)
    return {
        "manifest": manifest,
        "diagnostic_summary": summary,
        "diagnostic_reject_family_matrix": reject_matrix,
        "diagnostic_threshold_provenance": provenance,
        "diagnostic_actual_vs_counterfactual_results": comparison_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default="logs")
    parser.add_argument("--report-root", default="reports/order_log_diagnostic_harness")
    parser.add_argument("--recorder-root", default="data/recorder")
    parser.add_argument("--extra-recorder-root", action="append", default=["data/recorder_backfill_1m"])
    parser.add_argument("--scenarios", default="all")
    parser.add_argument("--strict", default="true")
    parser.add_argument("--mode", default="both", choices=["actual_trace_replay", "counterfactual_param_replay", "both"])
    parser.add_argument("--tolerance-pct", type=float, default=0.10)
    args = parser.parse_args(argv)

    workspace_root = Path.cwd()
    result = run_diagnostic_scenario_harness(
        workspace_root=workspace_root,
        runtime_root=(workspace_root / args.runtime_root).resolve(),
        report_root=(workspace_root / args.report_root).resolve(),
        recorder_root=(workspace_root / args.recorder_root).resolve(),
        extra_recorder_roots=[
            (workspace_root / item).resolve() if not Path(item).is_absolute() else Path(item)
            for item in args.extra_recorder_root
        ],
        scenarios=args.scenarios,
        strict=str(args.strict).strip().lower() not in {"0", "false", "no", "off"},
        mode=args.mode,
        tolerance_pct=float(args.tolerance_pct),
    )
    print(json.dumps(result["diagnostic_summary"], ensure_ascii=False, indent=2))
    return 0 if result["manifest"].get("status") == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
