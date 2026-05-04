from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .search import ObjectiveCandidate


def render_objective_calibration_report(
    out_dir: Path,
    *,
    scope: str,
    dataset_manifest: dict[str, Any],
    best_candidate: ObjectiveCandidate,
    candidate_count: int,
    overlay_paths: dict[str, str],
) -> Path:
    report = f"""# Objective Calibration Report

## Context
- Scope: {scope}
- Built at: {datetime.utcnow().isoformat(timespec="seconds")}Z
- Symbols: {dataset_manifest.get("symbols")}
- Range: {dataset_manifest.get("start")} -> {dataset_manifest.get("end")}
- TF: {dataset_manifest.get("tf_sec")}
- Attempted entry rows: {dataset_manifest.get("attempted_entry_rows")}
- Realized trade rows: {dataset_manifest.get("realized_trade_rows")}
- Candidate count: {candidate_count}

## Best Summary
- Composite score: {best_candidate.summary.get("score")}
- Realized quality score: {best_candidate.summary.get("realized_quality_score")}
- Net pnl efficiency: {best_candidate.summary.get("net_pnl_efficiency")}
- Inverse cost drag: {best_candidate.summary.get("inverse_cost_drag")}
- Gate precision on good trades: {best_candidate.summary.get("gate_precision_on_good_trades")}
- Inverse churn: {best_candidate.summary.get("inverse_churn")}
- Regime stability: {best_candidate.summary.get("regime_stability")}
- Accepted trade count: {best_candidate.summary.get("accepted_trade_count")}
- Candidate block rate: {best_candidate.summary.get("candidate_block_rate")}
- Missing input rate: {best_candidate.summary.get("missing_input_rate")}
- Duplicate veto rate: {best_candidate.summary.get("duplicate_veto_rate")}
- Close path regression rate: {best_candidate.summary.get("close_path_regression_rate")}
- Max drawdown: {best_candidate.summary.get("max_drawdown")}

## Output Artifacts
- Best trial: `{out_dir / "best_trial.json"}`
- Candidate bundle: `{out_dir / "candidate_bundle.json"}`
- Domain overlay: `{overlay_paths.get("domain_overlay")}`
- Aurora overlay: `{overlay_paths.get("aurora_overlay")}`
- MD-AMR overlay: `{overlay_paths.get("md_amr_overlay")}`
- Mean Reversion overlay: `{overlay_paths.get("mean_reversion_overlay")}`

## Rollout Reminder
- These artifacts are overlays only.
- They do not mutate canonical YAML automatically.
- Promote to hybrid `OBSERVE` first, then `MULTIPLY`, then `GATE`.
"""
    report_path = out_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path
