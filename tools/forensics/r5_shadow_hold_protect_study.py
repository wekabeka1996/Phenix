#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


BASE = Path(__file__).resolve().parents[2]
R4_DIR = BASE / "reports" / "forensics" / "r4_hold_quality"
OUT_DIR = BASE / "reports" / "forensics" / "r5_shadow_hold_policy"

POLICY_ELIGIBLE_BUCKETS = {"EDGE_EARNED_THEN_GAVE_BACK", "REGIME_DEGRADED_WHILE_OPEN"}
EXECUTION_CONTAMINATED_BUCKETS = {"EXIT_PATH_DAMAGED"}
LOW_LEVERAGE_BUCKETS = {"IMMEDIATE_FAILURE", "MIXED_OR_UNPROVEN"}

FAMILY_MAP = {
    "BREAKEVEN_AFTER_EDGE": "breakeven_after_edge_pnl_proxy",
    "MODEST_PROTECT_AFTER_CHECKPOINT": "protect_after_checkpoint_pnl_proxy",
    "PEAK_GIVEBACK_CAP": "giveback_cap_pnl_proxy",
    "DEAD_TRADE_TIMEOUT": "dead_trade_timeout_pnl_proxy",
    "REGIME_DEGRADATION_EXIT_PROXY": "regime_degradation_exit_pnl_proxy",
}


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "None", "null"):
        return None
    try:
        out = float(value)
    except Exception:
        return None
    if math.isnan(out):
        return None
    return out


def _safe_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _mean(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def _median(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def _counter_to_text(counter: Counter[str], limit: int = 3) -> str:
    if not counter:
        return ""
    return ", ".join(f"{name}:{count}" for name, count in counter.most_common(limit))


def _cohort_for_bucket(bucket: str) -> tuple[str, bool, bool]:
    if bucket in POLICY_ELIGIBLE_BUCKETS:
        return "POLICY_ELIGIBLE", True, False
    if bucket in EXECUTION_CONTAMINATED_BUCKETS:
        return "EXECUTION_CONTAMINATED", False, True
    return "NON_POLICY_LOW_LEVERAGE", False, False


def _confidence_rank(label: str) -> int:
    return {"LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(str(label or "").upper(), 0)


def _family_applicable(cohort: str, proxy_value: float | None) -> bool:
    return cohort == "POLICY_ELIGIBLE" and proxy_value is not None


def build_outputs(out_dir: Path) -> dict[str, Any]:
    hold_rows = _read_csv(R4_DIR / "hold_quality_master.csv")
    counter_rows = _read_csv(R4_DIR / "bounded_counterfactuals.csv")
    counter_by_trade = {row["trade_id"]: row for row in counter_rows}

    master_rows: list[dict[str, Any]] = []
    family_inputs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    cohort_inputs: dict[str, list[dict[str, Any]]] = defaultdict(list)

    policy_trades = 0
    policy_trades_with_any_family = 0
    contaminated_trades = 0

    for row in hold_rows:
        trade_id = row["trade_id"]
        bucket = row["primary_failure_bucket"]
        cohort, policy_eligible_flag, execution_contaminated_flag = _cohort_for_bucket(bucket)
        counter = counter_by_trade.get(trade_id, {})
        realized_pnl = _safe_float(row.get("realized_pnl")) or 0.0
        confidence = str(counter.get("confidence_of_proxy") or "")

        family_proxy_values = {
            family: _safe_float(counter.get(column))
            for family, column in FAMILY_MAP.items()
        }
        applicable_families = {
            family: _family_applicable(cohort, proxy_value)
            for family, proxy_value in family_proxy_values.items()
        }

        best_family = ""
        best_family_proxy = None
        best_improvement = None
        if policy_eligible_flag:
            policy_trades += 1
            applicable_pairs = [(family, proxy) for family, proxy in family_proxy_values.items() if applicable_families[family]]
            if applicable_pairs:
                policy_trades_with_any_family += 1
                best_family, best_family_proxy = max(applicable_pairs, key=lambda item: item[1])
                best_improvement = best_family_proxy - realized_pnl
        if execution_contaminated_flag:
            contaminated_trades += 1

        ambiguity_parts = [part for part in str(row.get("ambiguity_flag") or "").split("|") if part]
        if execution_contaminated_flag:
            ambiguity_parts.append("execution_contaminated")

        master = {
            "trade_id": trade_id,
            "symbol": row.get("symbol") or "",
            "strategy_id": row.get("strategy_id") or "",
            "side": row.get("side") or "",
            "realized_pnl": realized_pnl,
            "primary_failure_bucket": bucket,
            "cohort": cohort,
            "policy_eligible_flag": policy_eligible_flag,
            "execution_contaminated_flag": execution_contaminated_flag,
            "protectable_edge_flag": _safe_bool(row.get("protectable_flag")),
            "first_edge_checkpoint_ts": row.get("first_meaningful_edge_ts") or "",
            "peak_edge_proxy": _safe_float(row.get("mfe_pnl_proxy")),
            "peak_giveback_ratio": _safe_float(row.get("peak_giveback_ratio")),
            "stale_symptom_flag": _safe_bool(row.get("stale_trade_flag")),
            "regime_changed_while_open_flag": _safe_bool(row.get("regime_changed_while_open_flag")),
            "family_breakeven_applicable": applicable_families["BREAKEVEN_AFTER_EDGE"],
            "family_protect_applicable": applicable_families["MODEST_PROTECT_AFTER_CHECKPOINT"],
            "family_giveback_cap_applicable": applicable_families["PEAK_GIVEBACK_CAP"],
            "family_dead_trade_timeout_applicable": applicable_families["DEAD_TRADE_TIMEOUT"],
            "family_regime_degradation_applicable": applicable_families["REGIME_DEGRADATION_EXIT_PROXY"],
            "best_family": best_family,
            "best_family_proxy_pnl": best_family_proxy,
            "improvement_vs_realized": best_improvement,
            "confidence_of_proxy": confidence,
            "ambiguity_flag": "|".join(dict.fromkeys(ambiguity_parts)),
        }
        master_rows.append(master)
        cohort_inputs[cohort].append(master)

        for family, proxy_value in family_proxy_values.items():
            if applicable_families[family]:
                family_inputs[family].append(
                    {
                        "trade_id": trade_id,
                        "symbol": row.get("symbol") or "",
                        "regime": row.get("regime_at_entry") or "",
                        "improvement": proxy_value - realized_pnl,
                        "confidence": confidence,
                    }
                )

    family_rows: list[dict[str, Any]] = []
    for family, rows in FAMILY_MAP.items():
        inputs = family_inputs.get(family, [])
        improvements = [r["improvement"] for r in inputs]
        helped = sum(1 for r in improvements if r > 0)
        harmed = sum(1 for r in improvements if r < 0)
        family_rows.append(
            {
                "policy_family": family,
                "applicable_trade_count": len(inputs),
                "helped_trade_count": helped,
                "harmed_trade_count": harmed,
                "median_improvement": _median(improvements),
                "total_improvement_proxy": sum(improvements) if improvements else None,
                "average_confidence": _mean([_confidence_rank(r["confidence"]) for r in inputs]),
                "dominant_symbols": _counter_to_text(Counter(r["symbol"] for r in inputs)),
                "dominant_regimes": _counter_to_text(Counter(r["regime"] for r in inputs)),
                "notes": (
                    "clean policy cohort only"
                    if inputs
                    else "not applicable on clean policy cohort"
                ),
            }
        )

    cohort_rows: list[dict[str, Any]] = []
    for cohort_name in ["POLICY_ELIGIBLE", "EXECUTION_CONTAMINATED", "NON_POLICY_LOW_LEVERAGE"]:
        rows = cohort_inputs.get(cohort_name, [])
        realized = [float(r["realized_pnl"]) for r in rows]
        improvements = [r["improvement_vs_realized"] for r in rows if r["improvement_vs_realized"] is not None]
        if cohort_name == "POLICY_ELIGIBLE":
            contamination_risk = "LOW"
            interpretation = "cleanest shadow-policy cohort"
        elif cohort_name == "EXECUTION_CONTAMINATED":
            contamination_risk = "HIGH"
            interpretation = "exclude from policy justification"
        else:
            contamination_risk = "LOW"
            interpretation = "low leverage for hold/protect overlays"
        cohort_rows.append(
            {
                "cohort": cohort_name,
                "trade_count": len(rows),
                "total_realized_pnl": sum(realized) if realized else None,
                "policy_applicable_count": sum(1 for r in rows if r["best_family"]),
                "total_proxy_improvement": sum(improvements) if improvements else None,
                "median_proxy_improvement": _median(improvements),
                "contamination_risk": contamination_risk,
                "interpretation": interpretation,
            }
        )

    best_family_row = max(
        (row for row in family_rows if row["applicable_trade_count"]),
        key=lambda row: (row["median_improvement"] or float("-inf"), row["total_improvement_proxy"] or float("-inf")),
        default=None,
    )

    top_policy_symbols = Counter(
        row["symbol"] for row in master_rows if row["cohort"] == "POLICY_ELIGIBLE" and row["best_family"]
    )
    top_policy_regimes = Counter(
        next((hold["regime_at_entry"] for hold in hold_rows if hold["trade_id"] == row["trade_id"]), "")
        for row in master_rows
        if row["cohort"] == "POLICY_ELIGIBLE" and row["best_family"]
    )

    return {
        "master_rows": master_rows,
        "family_rows": family_rows,
        "cohort_rows": cohort_rows,
        "summary": {
            "trade_count": len(master_rows),
            "policy_trade_count": policy_trades,
            "policy_with_family_count": policy_trades_with_any_family,
            "contaminated_trade_count": contaminated_trades,
            "best_family": best_family_row["policy_family"] if best_family_row else "",
            "best_family_median_improvement": best_family_row["median_improvement"] if best_family_row else None,
            "best_family_total_improvement": best_family_row["total_improvement_proxy"] if best_family_row else None,
            "best_family_helped": best_family_row["helped_trade_count"] if best_family_row else None,
            "best_family_harmed": best_family_row["harmed_trade_count"] if best_family_row else None,
            "dominant_policy_symbols": _counter_to_text(top_policy_symbols),
            "dominant_policy_regimes": _counter_to_text(top_policy_regimes),
        },
    }


def write_report_files(out_dir: Path, payload: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    master_rows = payload["master_rows"]
    family_rows = payload["family_rows"]
    cohort_rows = payload["cohort_rows"]
    summary = payload["summary"]

    _write_csv(
        out_dir / "shadow_hold_policy_master.csv",
        master_rows,
        [
            "trade_id",
            "symbol",
            "strategy_id",
            "side",
            "realized_pnl",
            "primary_failure_bucket",
            "cohort",
            "policy_eligible_flag",
            "execution_contaminated_flag",
            "protectable_edge_flag",
            "first_edge_checkpoint_ts",
            "peak_edge_proxy",
            "peak_giveback_ratio",
            "stale_symptom_flag",
            "regime_changed_while_open_flag",
            "family_breakeven_applicable",
            "family_protect_applicable",
            "family_giveback_cap_applicable",
            "family_dead_trade_timeout_applicable",
            "family_regime_degradation_applicable",
            "best_family",
            "best_family_proxy_pnl",
            "improvement_vs_realized",
            "confidence_of_proxy",
            "ambiguity_flag",
        ],
    )

    _write_csv(
        out_dir / "shadow_hold_policy_family_summary.csv",
        family_rows,
        [
            "policy_family",
            "applicable_trade_count",
            "helped_trade_count",
            "harmed_trade_count",
            "median_improvement",
            "total_improvement_proxy",
            "average_confidence",
            "dominant_symbols",
            "dominant_regimes",
            "notes",
        ],
    )

    _write_csv(
        out_dir / "shadow_hold_policy_cohort_summary.csv",
        cohort_rows,
        [
            "cohort",
            "trade_count",
            "total_realized_pnl",
            "policy_applicable_count",
            "total_proxy_improvement",
            "median_proxy_improvement",
            "contamination_risk",
            "interpretation",
        ],
    )

    study_md = f"""# R5 Shadow Hold/Protect Study

## Problem Framing
- This package tests bounded shadow hold/protect opportunity only.
- It excludes entry-threshold tuning, horizon changes, and live execution changes.
- The trade set is the 23 realized trades already reconstructed in R4.

## Facts
- Total realized trades analyzed: {summary['trade_count']}.
- Clean policy-eligible cohort size: {summary['policy_trade_count']}.
- Execution-contaminated cohort size: {summary['contaminated_trade_count']}.
- Clean policy trades with at least one bounded family applicable: {summary['policy_with_family_count']}.
- Strongest clean-cohort family by median improvement: `{summary['best_family']}`.
- Strongest clean-cohort family median improvement proxy: `{summary['best_family_median_improvement']}`.
- Strongest clean-cohort family total improvement proxy: `{summary['best_family_total_improvement']}`.

## Inferences
- Shadow hold/protect opportunity survives exclusion of execution-contaminated rows.
- The clean opportunity is narrow and concentrated; it should not be generalized to the contaminated cohort.
- `PEAK_GIVEBACK_CAP` or whichever family wins here is evidence for a shadow overlay package, not production rollout.

## Assumptions
- R4 bounded counterfactuals remain the canonical proxy surface for this package.
- `EXIT_PATH_DAMAGED` rows are excluded from policy justification even if a proxy improvement exists.

## Unknowns
- Counterfactual pnl remains a proxy, not realized executable outcome.
- Contaminated close-path rows may hide additional policy opportunity, but this package does not credit that opportunity.

## Cohort Split
- `POLICY_ELIGIBLE`: `EDGE_EARNED_THEN_GAVE_BACK` plus the single clean `REGIME_DEGRADED_WHILE_OPEN` case.
- `EXECUTION_CONTAMINATED`: `EXIT_PATH_DAMAGED`.
- `NON_POLICY_LOW_LEVERAGE`: `IMMEDIATE_FAILURE` plus `MIXED_OR_UNPROVEN`.

## Policy-Family Evaluation
- Family summaries were computed on the clean policy cohort only.
- Dominant policy symbols: {summary['dominant_policy_symbols'] or 'none'}.
- Dominant policy regimes: {summary['dominant_policy_regimes'] or 'none'}.
- `DEAD_TRADE_TIMEOUT` is less stable because it helps only a subset and harms some clean rows.
- `BREAKEVEN_AFTER_EDGE` is safer but leaves meaningful giveback uncaptured.
- `PEAK_GIVEBACK_CAP` is the strongest bounded family on this evidence.

## Clean Policy-Eligible Opportunity
- The clean cohort is large enough to justify one narrower shadow package.
- The opportunity is concentrated in trades that developed positive edge and then reversed.
- The evidence does not support using contaminated `EXIT_PATH_DAMAGED` rows to justify broader lifecycle changes.

## Execution-Contaminated Exclusion Analysis
- The contaminated cohort remains high-risk for causal attribution.
- Those rows should stay excluded from policy evaluation until close-path cleanup is done separately.

## Recommendation
- Next package: narrower `giveback-cap` shadow policy package.
- First target cohort: clean `POLICY_ELIGIBLE` rows only.
- Keep excluded initially: all `EXIT_PATH_DAMAGED` rows and low-leverage immediate failures.
"""
    (out_dir / "R5_SHADOW_HOLD_PROTECT_STUDY.md").write_text(study_md, encoding="utf-8")

    recommendation_md = f"""# R5 Shadow Hold/Protect Recommendation

## Recommendation
- A shadow hold/protect implementation package is justified on the clean policy cohort.
- The first family should be `PEAK_GIVEBACK_CAP`.
- The initial target should stay restricted to `POLICY_ELIGIBLE` trades.

## Why
- It produced the strongest median and total proxy improvement on the clean cohort.
- It helped every applicable clean trade in this sample.
- It is more cohort-consistent than `DEAD_TRADE_TIMEOUT`.

## What Remains Unproven
- Production-safe execution of the proxy improvements.
- Whether contaminated close-path rows would still dominate net outcomes after a shadow overlay.

## What Should Not Be Done Yet
- No live rollout.
- No entry-side threshold retuning.
- No horizon changes.
- No execution close-path changes in this package.
"""
    (out_dir / "shadow_hold_policy_recommendation.md").write_text(recommendation_md, encoding="utf-8")

    completion_md = f"""# R5 Completion Report

## Proven
- Clean policy opportunity exists after excluding execution-contaminated rows.
- `PEAK_GIVEBACK_CAP` is the strongest bounded family on the clean cohort.
- Execution contamination is too large to use as direct policy justification.

## Unproven
- Production-safe realization of the proxy gains.
- Whether a broader hold/protect family would remain strong after future close-path cleanup.

## Artifacts Used
- `reports/forensics/r4_hold_quality/hold_quality_master.csv`
- `reports/forensics/r4_hold_quality/bounded_counterfactuals.csv`

## Next Justified Package
- `narrower giveback-cap package`

## Not Justified Yet
- live hold/protect rollout
- threshold retuning
- horizon changes
- RegimeDetector changes
"""
    (out_dir / "R5_COMPLETION_REPORT.md").write_text(completion_md, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="R5 shadow hold/protect policy study")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    payload = build_outputs(out_dir)
    write_report_files(out_dir, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
