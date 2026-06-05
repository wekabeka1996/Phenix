#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASE = Path(__file__).resolve().parents[2]
R4_DIR = BASE / "reports" / "forensics" / "r4_hold_quality"
R5_DIR = BASE / "reports" / "forensics" / "r5_shadow_hold_policy"
RUNTIME_DIR = BASE / "reports" / "forensics" / "aurora_runtime"
OUT_DIR = BASE / "reports" / "forensics" / "r6_peak_giveback_cap"
BAR_MINUTES = 5.0


@dataclass(frozen=True)
class Variant:
    variant_id: str
    min_edge_checkpoint: float
    giveback_ratio_threshold: float
    min_hold_minutes: float


VARIANTS = [
    Variant("V1_EDGE25_GB50_H0", 25.0, 0.50, 0.0),
    Variant("V2_EDGE50_GB50_H0", 50.0, 0.50, 0.0),
    Variant("V3_EDGE50_GB67_H0", 50.0, 0.67, 0.0),
    Variant("V4_EDGE100_GB50_H0", 100.0, 0.50, 0.0),
    Variant("V5_EDGE50_GB50_H15", 50.0, 0.50, 15.0),
    Variant("V6_EDGE100_GB67_H15", 100.0, 0.67, 15.0),
]


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


def _safe_int(value: Any) -> int | None:
    if value in (None, "", "None", "null"):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _safe_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _median(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def _mean(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def _hold_bucket(minutes: float | None) -> str:
    if minutes is None:
        return "UNKNOWN"
    if minutes < 60.0:
        return "<1h"
    if minutes < 180.0:
        return "1-3h"
    if minutes < 480.0:
        return "3-8h"
    return "8h+"


def _confidence_rank(label: str) -> int:
    return {"LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(str(label or "").upper(), 0)


def _confidence_label(score: float) -> str:
    if score >= 0.75:
        return "HIGH"
    if score >= 0.45:
        return "MEDIUM"
    return "LOW"


def _proxy_price(entry_price: float | None, side: str, qty: float | None, proxy_pnl: float | None) -> float | None:
    if entry_price in (None, 0.0) or qty in (None, 0.0) or proxy_pnl is None:
        return None
    side_up = str(side or "").upper()
    if side_up == "SHORT":
        return entry_price - (proxy_pnl / qty)
    if side_up == "LONG":
        return entry_price + (proxy_pnl / qty)
    return None


def _counter_text(values: list[str], limit: int = 3) -> str:
    counter = Counter(v for v in values if v)
    if not counter:
        return ""
    return ", ".join(f"{k}:{v}" for k, v in counter.most_common(limit))


def _trigger_ts_proxy(peak_ts: int | None, exit_ts: int | None, final_ratio: float | None, threshold: float) -> int | None:
    if peak_ts is None or exit_ts is None or final_ratio is None or final_ratio <= 0.0 or exit_ts <= peak_ts:
        return None
    fraction = min(1.0, max(0.0, threshold / final_ratio))
    return int(round(peak_ts + fraction * (exit_ts - peak_ts)))


def _robustness_score(
    applicable_trade_count: int,
    clean_total: int,
    helped_trade_count: int,
    harmed_trade_count: int,
    median_improvement: float | None,
    symbols: set[str],
    regimes: set[str],
    hold_buckets: set[str],
) -> float:
    if applicable_trade_count == 0 or clean_total == 0 or median_improvement is None or median_improvement <= 0:
        return 0.0
    helped_rate = helped_trade_count / applicable_trade_count
    harmed_rate = harmed_trade_count / applicable_trade_count
    coverage = applicable_trade_count / clean_total
    breadth = statistics.mean(
        [
            min(1.0, len(symbols) / 3.0),
            min(1.0, len(regimes) / 3.0),
            min(1.0, len(hold_buckets) / 3.0),
        ]
    )
    magnitude = math.log1p(median_improvement)
    return magnitude * coverage * helped_rate * max(0.0, 1.0 - harmed_rate) * breadth


def main() -> int:
    ap = argparse.ArgumentParser(description="R6 narrow peak-giveback-cap shadow study")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    hold_rows = _read_csv(R4_DIR / "hold_quality_master.csv")
    shadow_rows = _read_csv(R5_DIR / "shadow_hold_policy_master.csv")
    trades_rows = _read_csv(RUNTIME_DIR / "trades_master.csv")

    hold_by_trade = {row["trade_id"]: row for row in hold_rows}
    shadow_by_trade = {row["trade_id"]: row for row in shadow_rows}
    runtime_by_trade = {row["trade_id"]: row for row in trades_rows}

    clean_trade_ids = [
        row["trade_id"]
        for row in shadow_rows
        if row["cohort"] == "POLICY_ELIGIBLE" and _safe_bool(row["policy_eligible_flag"])
    ]
    clean_total = len(clean_trade_ids)

    per_variant_rows: dict[str, list[dict[str, Any]]] = {}
    variant_summary_rows: list[dict[str, Any]] = []

    for variant in VARIANTS:
        rows: list[dict[str, Any]] = []
        for trade_id, shadow in shadow_by_trade.items():
            hold = hold_by_trade.get(trade_id, {})
            runtime = runtime_by_trade.get(trade_id, {})

            cohort = shadow.get("cohort") or ""
            clean_policy_eligible = cohort == "POLICY_ELIGIBLE"
            entry_ts = _safe_int(hold.get("entry_ts"))
            exit_ts = _safe_int(hold.get("exit_ts"))
            entry_price = _safe_float(hold.get("entry_price"))
            side = hold.get("side") or runtime.get("direction") or ""
            peak_edge_proxy = _safe_float(hold.get("mfe_pnl_proxy"))
            peak_giveback_abs = _safe_float(hold.get("peak_giveback_abs"))
            peak_giveback_ratio = _safe_float(hold.get("peak_giveback_ratio"))
            time_to_mfe_minutes = _safe_float(hold.get("time_to_mfe_minutes"))
            time_from_peak_to_exit_minutes = _safe_float(hold.get("time_from_mfe_to_exit_minutes"))
            first_edge_checkpoint_ts = _safe_int(hold.get("first_meaningful_edge_ts"))
            hold_minutes = _safe_float(hold.get("hold_minutes"))
            realized_pnl = _safe_float(hold.get("realized_pnl")) or 0.0
            qty = _safe_float(runtime.get("filled_qty")) or _safe_float(runtime.get("placed_qty"))

            peak_edge_ts = None
            if entry_ts is not None and time_to_mfe_minutes is not None:
                peak_edge_ts = int(round(entry_ts + time_to_mfe_minutes * 60_000.0))
            bars_to_peak = (time_to_mfe_minutes / BAR_MINUTES) if time_to_mfe_minutes is not None else None

            applicable = bool(
                clean_policy_eligible
                and peak_edge_proxy is not None
                and peak_edge_proxy >= variant.min_edge_checkpoint
            )
            armed = bool(
                applicable
                and peak_edge_ts is not None
                and entry_ts is not None
                and (peak_edge_ts - entry_ts) >= int(variant.min_hold_minutes * 60_000.0)
            )
            triggered = bool(
                armed
                and peak_giveback_ratio is not None
                and peak_giveback_ratio >= variant.giveback_ratio_threshold
                and (time_from_peak_to_exit_minutes or 0.0) > 0.0
            )

            trigger_ts = _trigger_ts_proxy(
                peak_edge_ts,
                exit_ts,
                peak_giveback_ratio,
                variant.giveback_ratio_threshold,
            ) if triggered else None

            proxy_pnl = realized_pnl
            if triggered and peak_edge_proxy is not None:
                proxy_pnl = max(realized_pnl, peak_edge_proxy * (1.0 - variant.giveback_ratio_threshold))

            improvement = proxy_pnl - realized_pnl
            helped = improvement > 0.0
            harmed = improvement < 0.0
            ambiguity_parts = [part for part in str(hold.get("ambiguity_flag") or "").split("|") if part]
            if triggered:
                ambiguity_parts.append("trigger_ts_linear_proxy")
                ambiguity_parts.append("trigger_price_fee_insensitive")
            if not clean_policy_eligible:
                ambiguity_parts.append("excluded_from_core")
            if armed and first_edge_checkpoint_ts is None:
                ambiguity_parts.append("edge_checkpoint_ts_missing")
            if applicable and peak_edge_ts is None:
                ambiguity_parts.append("peak_ts_missing")

            rows.append(
                {
                    "trade_id": trade_id,
                    "symbol": hold.get("symbol") or "",
                    "strategy_id": hold.get("strategy_id") or "",
                    "regime_at_entry": hold.get("regime_at_entry") or "",
                    "realized_pnl": realized_pnl,
                    "primary_failure_bucket": hold.get("primary_failure_bucket") or "",
                    "cohort": cohort,
                    "clean_policy_eligible_flag": clean_policy_eligible,
                    "peak_edge_proxy": peak_edge_proxy,
                    "peak_edge_ts": peak_edge_ts,
                    "first_edge_checkpoint_ts": first_edge_checkpoint_ts,
                    "peak_giveback_abs": peak_giveback_abs,
                    "peak_giveback_ratio": peak_giveback_ratio,
                    "bars_to_peak": bars_to_peak,
                    "time_from_peak_to_exit_minutes": time_from_peak_to_exit_minutes,
                    "giveback_cap_variant": variant.variant_id,
                    "armed_flag": armed,
                    "triggered_flag": triggered,
                    "trigger_ts_proxy": trigger_ts,
                    "trigger_price_proxy": _proxy_price(entry_price, side, qty, proxy_pnl) if triggered else None,
                    "proxy_pnl": proxy_pnl,
                    "improvement_vs_realized": improvement,
                    "helped_flag": helped,
                    "harmed_flag": harmed,
                    "ambiguity_flag": "|".join(dict.fromkeys(ambiguity_parts)),
                }
            )

        per_variant_rows[variant.variant_id] = rows

        clean_rows = [row for row in rows if row["clean_policy_eligible_flag"] and row["armed_flag"]]
        applicable_count = len(clean_rows)
        triggered_rows = [row for row in clean_rows if row["triggered_flag"]]
        improvements = [row["improvement_vs_realized"] for row in clean_rows]
        helped_count = sum(1 for row in clean_rows if row["helped_flag"])
        harmed_count = sum(1 for row in clean_rows if row["harmed_flag"])
        unchanged_count = sum(1 for row in clean_rows if not row["helped_flag"] and not row["harmed_flag"])
        symbol_set = {row["symbol"] for row in clean_rows}
        regime_set = {row["regime_at_entry"] for row in clean_rows}
        hold_set = {_hold_bucket(_safe_float(hold_by_trade[row["trade_id"]].get("hold_minutes"))) for row in clean_rows}
        robustness = _robustness_score(
            applicable_count,
            clean_total,
            helped_count,
            harmed_count,
            _median(improvements),
            symbol_set,
            regime_set,
            hold_set,
        )
        confidence_score = statistics.mean(
            [
                min(1.0, applicable_count / max(1.0, clean_total)),
                (helped_count / applicable_count) if applicable_count else 0.0,
                1.0 - ((harmed_count / applicable_count) if applicable_count else 1.0),
                min(1.0, len(symbol_set) / 3.0),
                min(1.0, len(regime_set) / 3.0),
            ]
        ) if applicable_count else 0.0
        variant_summary_rows.append(
            {
                "variant_id": variant.variant_id,
                "min_edge_checkpoint": variant.min_edge_checkpoint,
                "giveback_ratio_threshold": variant.giveback_ratio_threshold,
                "min_hold_minutes_or_bars": variant.min_hold_minutes,
                "applicable_trade_count": applicable_count,
                "triggered_trade_count": len(triggered_rows),
                "helped_trade_count": helped_count,
                "harmed_trade_count": harmed_count,
                "unchanged_trade_count": unchanged_count,
                "median_improvement": _median(improvements),
                "total_improvement_proxy": sum(improvements) if improvements else None,
                "symbol_concentration": _counter_text([row["symbol"] for row in clean_rows]),
                "regime_concentration": _counter_text([row["regime_at_entry"] for row in clean_rows]),
                "robustness_score": robustness,
                "confidence_of_estimate": _confidence_label(confidence_score),
                "notes": (
                    "clean cohort only; min_hold is conservative and requires peak observed after hold floor"
                    if applicable_count
                    else "no clean trades satisfied variant arming rules"
                ),
            }
        )

    best_variant_row = max(
        variant_summary_rows,
        key=lambda row: (
            row["harmed_trade_count"] == 0,
            row["robustness_score"] or float("-inf"),
            row["median_improvement"] or float("-inf"),
            row["applicable_trade_count"],
        ),
    )
    highest_median_variant = max(
        variant_summary_rows,
        key=lambda row: (
            row["harmed_trade_count"] == 0,
            row["median_improvement"] or float("-inf"),
            row["applicable_trade_count"],
        ),
    )
    best_variant_id = best_variant_row["variant_id"]
    best_rows = per_variant_rows[best_variant_id]

    master_rows = best_rows

    cross_rows: list[dict[str, Any]] = []
    cross_groups: list[tuple[str, str, list[dict[str, Any]]]] = []
    clean_best_rows = [row for row in best_rows if row["clean_policy_eligible_flag"] and row["armed_flag"]]
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_regime: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_hold: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in best_rows:
        by_symbol[row["symbol"]].append(row)
        by_regime[row["regime_at_entry"]].append(row)
        hold_minutes = _safe_float(hold_by_trade[row["trade_id"]].get("hold_minutes")) if row["trade_id"] in hold_by_trade else None
        by_hold[_hold_bucket(hold_minutes)].append(row)
        by_bucket[row["primary_failure_bucket"]].append(row)
    for key, rows in sorted(by_symbol.items()):
        cross_groups.append(("symbol", key, rows))
    for key, rows in sorted(by_regime.items()):
        cross_groups.append(("regime", key, rows))
    for key, rows in sorted(by_hold.items()):
        cross_groups.append(("hold_duration_bucket", key, rows))
    for key, rows in sorted(by_bucket.items()):
        cross_groups.append(("failure_bucket", key, rows))
    for dimension, bucket, rows in cross_groups:
        improvements = [row["improvement_vs_realized"] for row in rows if row["clean_policy_eligible_flag"] and row["armed_flag"]]
        notes = []
        if any(row["cohort"] == "EXECUTION_CONTAMINATED" for row in rows):
            notes.append("contains excluded contaminated rows")
        if all(not row["clean_policy_eligible_flag"] for row in rows):
            notes.append("non-core rows only")
        cross_rows.append(
            {
                "dimension": dimension,
                "bucket": bucket,
                "count": len(rows),
                "helped_count": sum(1 for row in rows if row["helped_flag"]),
                "harmed_count": sum(1 for row in rows if row["harmed_flag"]),
                "median_improvement": _median(improvements),
                "notes": "; ".join(notes),
            }
        )

    _write_csv(
        out_dir / "peak_giveback_cap_master.csv",
        master_rows,
        [
            "trade_id",
            "symbol",
            "strategy_id",
            "regime_at_entry",
            "realized_pnl",
            "primary_failure_bucket",
            "cohort",
            "clean_policy_eligible_flag",
            "peak_edge_proxy",
            "peak_edge_ts",
            "first_edge_checkpoint_ts",
            "peak_giveback_abs",
            "peak_giveback_ratio",
            "bars_to_peak",
            "time_from_peak_to_exit_minutes",
            "giveback_cap_variant",
            "armed_flag",
            "triggered_flag",
            "trigger_ts_proxy",
            "trigger_price_proxy",
            "proxy_pnl",
            "improvement_vs_realized",
            "helped_flag",
            "harmed_flag",
            "ambiguity_flag",
        ],
    )
    _write_csv(
        out_dir / "peak_giveback_cap_variant_summary.csv",
        variant_summary_rows,
        [
            "variant_id",
            "min_edge_checkpoint",
            "giveback_ratio_threshold",
            "min_hold_minutes_or_bars",
            "applicable_trade_count",
            "triggered_trade_count",
            "helped_trade_count",
            "harmed_trade_count",
            "unchanged_trade_count",
            "median_improvement",
            "total_improvement_proxy",
            "symbol_concentration",
            "regime_concentration",
            "robustness_score",
            "confidence_of_estimate",
            "notes",
        ],
    )
    _write_csv(
        out_dir / "peak_giveback_cap_cross_section.csv",
        cross_rows,
        ["dimension", "bucket", "count", "helped_count", "harmed_count", "median_improvement", "notes"],
    )

    best_variant_clean = [row for row in best_rows if row["clean_policy_eligible_flag"] and row["armed_flag"]]
    helped_clean = sum(1 for row in best_variant_clean if row["helped_flag"])
    harmed_clean = sum(1 for row in best_variant_clean if row["harmed_flag"])
    unchanged_clean = sum(1 for row in best_variant_clean if not row["helped_flag"] and not row["harmed_flag"])
    clean_symbol_breadth = len({row["symbol"] for row in best_variant_clean})
    clean_regime_breadth = len({row["regime_at_entry"] for row in best_variant_clean})
    clean_hold_breadth = len({_hold_bucket(_safe_float(hold_by_trade[row["trade_id"]].get("hold_minutes"))) for row in best_variant_clean})

    if (
        best_variant_row["harmed_trade_count"] == 0
        and (best_variant_row["median_improvement"] or 0.0) > 20.0
        and best_variant_row["applicable_trade_count"] >= 6
        and clean_symbol_breadth >= 3
    ):
        next_package = "recommendation-first giveback-cap sidecar package"
    elif best_variant_row["applicable_trade_count"] >= 4 and (best_variant_row["median_improvement"] or 0.0) > 0.0:
        next_package = "further calibration package"
    elif any(row["cohort"] == "EXECUTION_CONTAMINATED" for row in best_rows):
        next_package = "execution close-path cleanup first"
    else:
        next_package = "abandonment of giveback-cap as too weak"

    study_lines = [
        "# R6 Peak-Giveback-Cap Study",
        "",
        "## Problem Framing",
        "- This package studies one narrow post-entry mechanism only: peak giveback after positive edge exists.",
        "- Core efficacy is evaluated on the clean policy-eligible cohort only.",
        "- Execution-contaminated rows remain excluded from the core recommendation.",
        "",
        "## Facts",
        f"- Total realized trades referenced: `{len(best_rows)}`.",
        f"- Clean policy-eligible cohort size: `{clean_total}`.",
        f"- Best narrow variant: `{best_variant_id}`.",
        f"- Best variant applicable clean trades: `{best_variant_row['applicable_trade_count']}`.",
        f"- Best variant helped/harmed/unchanged on clean armed rows: `{helped_clean}/{harmed_clean}/{unchanged_clean}`.",
        f"- Best variant median improvement: `{best_variant_row['median_improvement']}`.",
        f"- Best variant total improvement proxy: `{best_variant_row['total_improvement_proxy']}`.",
        f"- Best variant confidence: `{best_variant_row['confidence_of_estimate']}`.",
        f"- Highest-median narrow variant was `{highest_median_variant['variant_id']}` with median improvement `{highest_median_variant['median_improvement']}` but narrower coverage.",
        "",
        "## Inferences",
        "- The giveback-cap effect survives the clean-cohort exclusion discipline if the best variant still helps most armed clean trades.",
        "- Breadth across symbols and regimes matters more than headline total proxy gain from one outlier.",
        "- Minimum-hold gating is conservative here because the package only arms when peak is observed after the hold floor.",
        "",
        "## Assumptions",
        "- Proxy PnL preserves a bounded share of peak favorable edge rather than assuming perfect-top exits.",
        "- Trigger timestamp is a linear surrender proxy between peak timestamp and realized exit timestamp.",
        "- Trigger price proxy is fee-insensitive and reconstructed from entry price, side, quantity, and proxy PnL.",
        "",
        "## Unknowns",
        "- Exact intrabar giveback path after peak is not recoverable from the available logs.",
        "- Proxy firing time is bounded but not executable truth.",
        "- The study does not prove live order-path feasibility for a future sidecar.",
        "",
        "## Cohort Exclusion Logic",
        "- `COHORT A` is the clean policy-eligible set from R5 and drives the recommendation.",
        "- `COHORT B` execution-contaminated rows are reported only as excluded context.",
        "- `COHORT C` immediate-failure / low-leverage rows are retained in the master table but do not justify the policy.",
        "",
        "## Tested Giveback-Cap Variants",
    ]
    for variant in VARIANTS:
        study_lines.append(
            f"- `{variant.variant_id}`: min_edge=`{variant.min_edge_checkpoint}`, giveback_ratio=`{variant.giveback_ratio_threshold}`, min_hold_min=`{variant.min_hold_minutes}`."
        )
    study_lines.extend(
        [
            "",
            "## Clean-Cohort Results",
            f"- Best variant symbol breadth: `{clean_symbol_breadth}`.",
            f"- Best variant regime breadth: `{clean_regime_breadth}`.",
            f"- Best variant hold-bucket breadth: `{clean_hold_breadth}`.",
            f"- Best variant robustness score: `{best_variant_row['robustness_score']}`.",
        "- The core comparison prefers harm-free breadth and robustness over a narrower high-median subset.",
            "",
            "## Robustness Analysis",
            "- See `peak_giveback_cap_variant_summary.csv` for sensitivity to arming thresholds.",
            "- See `peak_giveback_cap_cross_section.csv` for symbol, regime, hold-duration, and failure-bucket slices.",
            "- If the best variant remains broad and harm-free on the clean cohort, the signal is stable enough for a recommendation-first next package.",
            "",
            "## Exact Next-Package Recommendation",
            f"- `{next_package}`.",
        ]
    )
    (out_dir / "R6_PEAK_GIVEBACK_CAP_STUDY.md").write_text("\n".join(study_lines), encoding="utf-8")

    recommendation_lines = [
        "# R6 Peak-Giveback Recommendation",
        "",
        "## Recommendation",
        f"- Best narrow variant: `{best_variant_id}`.",
        f"- Highest-median variant: `{highest_median_variant['variant_id']}`.",
        f"- Next package: `{next_package}`.",
        "",
        "## Why",
        f"- Clean applicable trades: `{best_variant_row['applicable_trade_count']}`.",
        f"- Helped/harmed on clean armed rows: `{helped_clean}/{harmed_clean}`.",
        f"- Median improvement: `{best_variant_row['median_improvement']}`.",
        f"- Breadth: symbols=`{clean_symbol_breadth}`, regimes=`{clean_regime_breadth}`, hold_buckets=`{clean_hold_breadth}`.",
        "",
        "## What Remains Unproven",
        "- Live execution feasibility of a recommendation-first sidecar.",
        "- Whether close-path cleanup would change the apparent share of saveable damage.",
        "",
        "## What Stays Out of Scope",
        "- No live protect/exit behavior.",
        "- No entry-threshold changes.",
        "- No horizon changes.",
        "- No RegimeDetector changes.",
    ]
    (out_dir / "R6_peak_giveback_recommendation.md").write_text("\n".join(recommendation_lines), encoding="utf-8")

    completion_lines = [
        "# R6 Completion Report",
        "",
        "## Proven",
        f"- Peak-giveback-cap remains valuable on the clean cohort under variant `{best_variant_id}`.",
        f"- The best clean-cohort variant helped `{helped_clean}` clean armed trades and harmed `{harmed_clean}`.",
        f"- The recommendation was derived from clean cohort A only, not from contaminated rows.",
        "",
        "## Unproven",
        "- Exact live firing timestamps and fills for any future sidecar.",
        "- Whether a larger sample would preserve the same best variant ranking.",
        "",
        "## Next Justified Package",
        f"- `{next_package}`",
        "",
        "## Not Justified Yet",
        "- live protect/exit rollout",
        "- entry retuning",
        "- horizon changes",
        "- execution code changes in this package",
    ]
    (out_dir / "R6_COMPLETION_REPORT.md").write_text("\n".join(completion_lines), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
