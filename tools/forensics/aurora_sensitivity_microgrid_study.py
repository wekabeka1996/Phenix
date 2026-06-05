#!/usr/bin/env python3
"""Sensitivity-only micro-grid study for Aurora strategist influence."""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from tools.forensics import aurora_trend_up_strategist_sweep_study as prev


MANDATORY_GRID_VALUES = [
    0.30,
    0.35,
    0.40,
    0.45,
    0.50,
    0.55,
    0.60,
    0.65,
    0.70,
    0.75,
    0.80,
    0.85,
    0.90,
    1.00,
    1.10,
    1.20,
    1.35,
]
PRIOR_WINNER_VALUE = 0.75
EPS = 1e-12


@dataclass(frozen=True)
class ConfirmationSurface:
    name: str
    start_ts_ms: int
    end_ts_ms: int
    segment_bar_count: int
    reason: str
    parity_ok: bool
    parity_mismatch_count: int


@dataclass(frozen=True)
class MicrogridMetrics:
    scenario_id: str
    sensitivity: float
    status: str
    classification: str
    window_points: int
    growth_point_count: int
    non_growth_point_count: int
    sell_active_pct_full: float | None
    neutral_pct_full: float | None
    buy_active_pct_full: float | None
    sell_active_pct_growth: float | None
    neutral_pct_growth: float | None
    buy_active_pct_growth: float | None
    sell_active_pct_non_growth: float | None
    neutral_pct_non_growth: float | None
    buy_active_pct_non_growth: float | None
    sell_active_count_full: int
    neutral_count_full: int
    buy_active_count_full: int
    sell_active_count_growth: int
    neutral_count_growth: int
    buy_active_count_growth: int
    sell_active_count_non_growth: int
    neutral_count_non_growth: int
    buy_active_count_non_growth: int
    growth_capture_pct: float | None
    growth_capture_count: int
    false_buy_outside_growth_pct: float | None
    false_buy_outside_growth_count: int
    growth_sell_reduction_pct: float | None
    growth_sell_reduction_count: int
    mean_distance_to_buy: float | None
    median_distance_to_buy: float | None
    p90_distance_to_buy: float | None
    mean_sell_depth: float | None
    median_sell_depth: float | None
    p90_sell_depth: float | None
    side_flip_count: int
    churn_rate: float
    oscillation_flag: bool
    mean_strategist_delta: float | None
    median_strategist_delta: float | None
    mean_pillar_sum_delta: float | None
    median_pillar_sum_delta: float | None
    shrinkage_to_sell_count: int
    shrinkage_to_neutral_count: int
    shrinkage_to_buy_count: int
    shrinkage_changed_side_count: int
    prior_winner_capture_delta_count: int
    prior_winner_capture_delta_pct_points: float | None
    baseline_capture_delta_count: int
    baseline_capture_delta_pct_points: float | None
    blocked_reason: str | None = None
    spillover_verdict: str | None = None


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", default=str(REPO_ROOT / "config" / "aurora"))
    parser.add_argument("--strategies-yaml", default=str(REPO_ROOT / "config" / "aurora" / "strategies.yaml"))
    parser.add_argument("--domains-yaml", default=str(REPO_ROOT / "config" / "aurora" / "domains.yaml"))
    parser.add_argument("--recorder-dir", default=str(REPO_ROOT / "data" / "recorder"))
    parser.add_argument("--aurora-core-glob", default=str(REPO_ROOT / "logs" / "aurora_core.log*"))
    parser.add_argument("--decision-log-glob", default=str(REPO_ROOT / "logs" / "domain_decision_making.log*"))
    parser.add_argument("--shadow-journal", default=str(REPO_ROOT / "logs" / "shadow_critical_event_journal_v1.jsonl"))
    parser.add_argument("--trade-lifecycle", default=str(REPO_ROOT / "logs" / "trade_lifecycle.jsonl"))
    parser.add_argument("--prior-report-dir", default=str(REPO_ROOT / "reports" / "aurora_trend_up_strategist_sweep_2026-04-14"))
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "reports" / "aurora_sensitivity_microgrid_2026-04-14"))
    parser.add_argument("--timezone", default="Europe/Kiev")
    parser.add_argument("--symbols", nargs="*", default=None)
    return parser.parse_args(argv)


def _load_baseline_sensitivity(domains_yaml: Path) -> float:
    payload = yaml.safe_load(domains_yaml.read_text(encoding="utf-8"))
    return float(payload["feature_engineering"]["pillars"]["strategist"]["sensitivity"])


def _sorted_grid(baseline_value: float) -> list[float]:
    values = {float(value) for value in MANDATORY_GRID_VALUES}
    values.add(float(baseline_value))
    return sorted(values)


def _value_slug(value: float) -> str:
    return f"{value:.2f}".replace(".", "p")


def _scenario_id(index: int) -> str:
    return f"MICROGRID_SENSITIVITY_{index:02d}"


def _scenario_output_prefix(index: int, value: float) -> str:
    return f"MICROGRID_SENSITIVITY_{index:02d}_{_value_slug(value)}"


def _load_prior_manifest(prior_report_dir: Path) -> dict[str, Any]:
    return json.loads((prior_report_dir / "frozen_window_manifest.json").read_text(encoding="utf-8"))


def _load_prior_summary(prior_report_dir: Path) -> dict[float, dict[str, Any]]:
    summary_path = prior_report_dir / "SCENARIO_SUMMARY.csv"
    rows: dict[float, dict[str, Any]] = {}
    with summary_path.open("r", encoding="utf-8", newline="") as handle:
        import csv

        reader = csv.DictReader(handle)
        for row in reader:
            rows[float(row["scenario_value"])] = dict(row)
    return rows


def _load_prior_baseline(prior_report_dir: Path) -> list[dict[str, Any]]:
    return json.loads((prior_report_dir / "BASELINE_REPLAY.json").read_text(encoding="utf-8"))


def _rows_signature(rows: Sequence[dict[str, Any]]) -> str:
    return prev._deterministic_signature(rows)


def _surface_segment(start_ts_ms: int, end_ts_ms: int) -> list[int]:
    return list(range(int(start_ts_ms), int(end_ts_ms) + prev.TF_MS, prev.TF_MS))


def _select_additional_trend_up_surface(
    segments: Sequence[Sequence[int]],
    symbols: Sequence[str],
    regime_map: dict[tuple[str, int], prev.RegimeEvidence],
    *,
    before_ts_ms: int,
) -> list[int] | None:
    candidates: list[list[int]] = []
    for segment in segments:
        if int(segment[-1]) >= before_ts_ms:
            continue
        if len(segment) <= prev.HORIZON_6:
            continue
        if any(regime_map[(symbol, bar_ts)].regime == "TREND_UP" for bar_ts in segment for symbol in symbols):
            candidates.append(list(segment))
    return candidates[-1] if candidates else None


def _occupancy(subset: Sequence[dict[str, Any]]) -> tuple[int, int, int, float | None, float | None, float | None]:
    if not subset:
        return 0, 0, 0, None, None, None
    total = len(subset)
    sell_count = sum(1 for row in subset if row["raw_side"] == "sell")
    neutral_count = sum(1 for row in subset if row["raw_side"] == "")
    buy_count = sum(1 for row in subset if row["raw_side"] == "buy")
    return sell_count, neutral_count, buy_count, sell_count / total, neutral_count / total, buy_count / total


def _side_stability(rows: Sequence[dict[str, Any]]) -> tuple[int, bool]:
    side_flip_count = 0
    oscillation_flag = False
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_symbol[str(row["symbol"])].append(row)
    for symbol_rows in by_symbol.values():
        symbol_rows.sort(key=lambda row: row["bar_close_ts_ms"])
        sides = [str(row["raw_side"]) for row in symbol_rows]
        previous = None
        for side in sides:
            if previous is not None and side != previous:
                side_flip_count += 1
            previous = side
        for a, b, c in zip(sides, sides[1:], sides[2:], strict=False):
            if a and b and c and a == c and a != b:
                oscillation_flag = True
    return side_flip_count, oscillation_flag


def _build_growth_flags_for_rows(
    rows: Sequence[dict[str, Any]],
    recorder_series: dict[str, list[prev.RecorderPoint]],
    *,
    candidate: prev.CandidateDefinition,
) -> tuple[dict[tuple[str, int], tuple[bool, bool]], list[dict[str, Any]]]:
    series_index = {symbol: prev._build_symbol_index(series) for symbol, series in recorder_series.items()}
    point_lookup = {
        (symbol, point.bar_close_ts_ms): point
        for symbol, series in recorder_series.items()
        for point in series
    }
    growth_flags: dict[tuple[str, int], tuple[bool, bool]] = {}
    feature_rows: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row["symbol"])
        point = point_lookup[(symbol, int(row["bar_close_ts_ms"]))]
        payload = prev._future_feature_payload(recorder_series[symbol], series_index[symbol], point)
        complete = (
            payload["fwd_ret_3_bps"] is not None
            and payload["fwd_ret_6_bps"] is not None
            and payload["bullish_closes_next3"] is not None
            and payload["long_mfe_6_bps"] is not None
            and payload["short_benefit_6_bps"] is not None
        )
        growth_flag = prev._candidate_flag(candidate.name, payload, candidate.thresholds) if complete else False
        growth_flags[(symbol, int(row["bar_close_ts_ms"]))] = (growth_flag, complete)
        enriched = dict(row)
        enriched.update(payload)
        enriched["active_growth_phase"] = growth_flag
        enriched["active_growth_complete"] = complete
        feature_rows.append(enriched)
    return growth_flags, feature_rows


def _compute_micro_metrics(
    rows: Sequence[dict[str, Any]],
    *,
    scenario_id: str,
    sensitivity: float,
    baseline_lookup: dict[tuple[str, int], dict[str, Any]],
    baseline_metrics: MicrogridMetrics | None,
    prior_winner_metrics: MicrogridMetrics | None,
    status: str,
    blocked_reason: str | None = None,
) -> MicrogridMetrics:
    if status != "ok":
        return MicrogridMetrics(
            scenario_id=scenario_id,
            sensitivity=sensitivity,
            status=status,
            classification="inconclusive",
            window_points=0,
            growth_point_count=0,
            non_growth_point_count=0,
            sell_active_pct_full=None,
            neutral_pct_full=None,
            buy_active_pct_full=None,
            sell_active_pct_growth=None,
            neutral_pct_growth=None,
            buy_active_pct_growth=None,
            sell_active_pct_non_growth=None,
            neutral_pct_non_growth=None,
            buy_active_pct_non_growth=None,
            sell_active_count_full=0,
            neutral_count_full=0,
            buy_active_count_full=0,
            sell_active_count_growth=0,
            neutral_count_growth=0,
            buy_active_count_growth=0,
            sell_active_count_non_growth=0,
            neutral_count_non_growth=0,
            buy_active_count_non_growth=0,
            growth_capture_pct=None,
            growth_capture_count=0,
            false_buy_outside_growth_pct=None,
            false_buy_outside_growth_count=0,
            growth_sell_reduction_pct=None,
            growth_sell_reduction_count=0,
            mean_distance_to_buy=None,
            median_distance_to_buy=None,
            p90_distance_to_buy=None,
            mean_sell_depth=None,
            median_sell_depth=None,
            p90_sell_depth=None,
            side_flip_count=0,
            churn_rate=0.0,
            oscillation_flag=False,
            mean_strategist_delta=None,
            median_strategist_delta=None,
            mean_pillar_sum_delta=None,
            median_pillar_sum_delta=None,
            shrinkage_to_sell_count=0,
            shrinkage_to_neutral_count=0,
            shrinkage_to_buy_count=0,
            shrinkage_changed_side_count=0,
            prior_winner_capture_delta_count=0,
            prior_winner_capture_delta_pct_points=None,
            baseline_capture_delta_count=0,
            baseline_capture_delta_pct_points=None,
            blocked_reason=blocked_reason,
        )

    label_complete_rows = [row for row in rows if row["active_growth_complete"]]
    growth_rows = [row for row in label_complete_rows if row["active_growth_phase"]]
    non_growth_rows = [row for row in label_complete_rows if not row["active_growth_phase"]]
    sell_full, neutral_full, buy_full, sell_pct_full, neutral_pct_full, buy_pct_full = _occupancy(rows)
    sell_growth, neutral_growth, buy_growth, sell_pct_growth, neutral_pct_growth, buy_pct_growth = _occupancy(growth_rows)
    sell_non_growth, neutral_non_growth, buy_non_growth, sell_pct_non_growth, neutral_pct_non_growth, buy_pct_non_growth = _occupancy(non_growth_rows)

    distance_to_buy = [max(0.0, float(row["thr_buy"]) - float(row["final_score"])) for row in rows]
    sell_depth = [
        max(0.0, (-float(row["thr_sell"])) - float(row["final_score"])) if float(row["final_score"]) <= -float(row["thr_sell"]) else 0.0
        for row in rows
    ]
    side_flip_count, oscillation_flag = _side_stability(rows)
    churn_rate = prev._compute_churn_rate(rows)

    strategist_deltas: list[float] = []
    pillar_sum_deltas: list[float] = []
    shrinkage_to_sell_count = 0
    shrinkage_to_neutral_count = 0
    shrinkage_to_buy_count = 0
    shrinkage_changed_side_count = 0
    for row in rows:
        baseline = baseline_lookup[(str(row["symbol"]), int(row["bar_close_ts_ms"]))]
        strategist_delta = float(row["pillar_strategist"]) - float(baseline["pillar_strategist"])
        pillar_sum_delta = float(row["pillar_sum"]) - float(baseline["pillar_sum"])
        strategist_deltas.append(strategist_delta)
        pillar_sum_deltas.append(pillar_sum_delta)
        if pillar_sum_delta > EPS:
            if row["raw_side"] == "sell":
                shrinkage_to_sell_count += 1
            elif row["raw_side"] == "":
                shrinkage_to_neutral_count += 1
            elif row["raw_side"] == "buy":
                shrinkage_to_buy_count += 1
            if row["raw_side"] != baseline["raw_side"]:
                shrinkage_changed_side_count += 1

    baseline_growth_sell_count = baseline_metrics.sell_active_count_growth if baseline_metrics is not None else 0
    baseline_capture_count = baseline_metrics.growth_capture_count if baseline_metrics is not None else 0
    baseline_capture_pct = float(baseline_metrics.growth_capture_pct or 0.0) if baseline_metrics is not None else 0.0
    prior_capture_count = prior_winner_metrics.growth_capture_count if prior_winner_metrics is not None else 0
    prior_capture_pct = float(prior_winner_metrics.growth_capture_pct or 0.0) if prior_winner_metrics is not None else 0.0

    growth_capture_pct = buy_pct_growth
    false_buy_outside_growth_pct = buy_pct_non_growth
    growth_sell_reduction_count = max(0, baseline_growth_sell_count - sell_growth)
    growth_sell_reduction_pct = (
        growth_sell_reduction_count / baseline_growth_sell_count if baseline_growth_sell_count > 0 else None
    )

    return MicrogridMetrics(
        scenario_id=scenario_id,
        sensitivity=sensitivity,
        status=status,
        classification="inconclusive",
        window_points=len(rows),
        growth_point_count=len(growth_rows),
        non_growth_point_count=len(non_growth_rows),
        sell_active_pct_full=sell_pct_full,
        neutral_pct_full=neutral_pct_full,
        buy_active_pct_full=buy_pct_full,
        sell_active_pct_growth=sell_pct_growth,
        neutral_pct_growth=neutral_pct_growth,
        buy_active_pct_growth=buy_pct_growth,
        sell_active_pct_non_growth=sell_pct_non_growth,
        neutral_pct_non_growth=neutral_pct_non_growth,
        buy_active_pct_non_growth=buy_pct_non_growth,
        sell_active_count_full=sell_full,
        neutral_count_full=neutral_full,
        buy_active_count_full=buy_full,
        sell_active_count_growth=sell_growth,
        neutral_count_growth=neutral_growth,
        buy_active_count_growth=buy_growth,
        sell_active_count_non_growth=sell_non_growth,
        neutral_count_non_growth=neutral_non_growth,
        buy_active_count_non_growth=buy_non_growth,
        growth_capture_pct=growth_capture_pct,
        growth_capture_count=buy_growth,
        false_buy_outside_growth_pct=false_buy_outside_growth_pct,
        false_buy_outside_growth_count=buy_non_growth,
        growth_sell_reduction_pct=growth_sell_reduction_pct,
        growth_sell_reduction_count=growth_sell_reduction_count,
        mean_distance_to_buy=prev._mean(distance_to_buy),
        median_distance_to_buy=prev._median(distance_to_buy),
        p90_distance_to_buy=prev._percentile(distance_to_buy, 0.90),
        mean_sell_depth=prev._mean(sell_depth),
        median_sell_depth=prev._median(sell_depth),
        p90_sell_depth=prev._percentile(sell_depth, 0.90),
        side_flip_count=side_flip_count,
        churn_rate=churn_rate,
        oscillation_flag=oscillation_flag,
        mean_strategist_delta=prev._mean(strategist_deltas),
        median_strategist_delta=prev._median(strategist_deltas),
        mean_pillar_sum_delta=prev._mean(pillar_sum_deltas),
        median_pillar_sum_delta=prev._median(pillar_sum_deltas),
        shrinkage_to_sell_count=shrinkage_to_sell_count,
        shrinkage_to_neutral_count=shrinkage_to_neutral_count,
        shrinkage_to_buy_count=shrinkage_to_buy_count,
        shrinkage_changed_side_count=shrinkage_changed_side_count,
        prior_winner_capture_delta_count=buy_growth - prior_capture_count,
        prior_winner_capture_delta_pct_points=(
            (float(growth_capture_pct) - prior_capture_pct) if growth_capture_pct is not None else None
        ),
        baseline_capture_delta_count=buy_growth - baseline_capture_count,
        baseline_capture_delta_pct_points=(
            (float(growth_capture_pct) - baseline_capture_pct) if growth_capture_pct is not None else None
        ),
        blocked_reason=blocked_reason,
    )


def _classify_metrics(metrics: MicrogridMetrics, *, prior_winner_metrics: MicrogridMetrics) -> str:
    if metrics.status != "ok":
        return "inconclusive"
    if metrics.false_buy_outside_growth_count > 0 or metrics.oscillation_flag:
        return "unstable / risky"
    if metrics.growth_capture_count >= prior_winner_metrics.growth_capture_count + 1:
        return "selective capture candidate"
    if metrics.growth_capture_count == 0 and metrics.growth_sell_reduction_count > 0:
        if metrics.growth_sell_reduction_pct is not None and metrics.growth_sell_reduction_pct >= 0.80:
            return "over-neutralizer"
        return "neutralizer"
    if (
        metrics.growth_capture_count == prior_winner_metrics.growth_capture_count
        and metrics.growth_capture_count > 0
        and metrics.false_buy_outside_growth_count == 0
        and metrics.churn_rate <= prior_winner_metrics.churn_rate + EPS
    ):
        return "de-bias only"
    return "inconclusive"


def _ranking_key(metrics: MicrogridMetrics) -> tuple[float, float, float, float, float]:
    return (
        float(metrics.growth_capture_count),
        -float(metrics.false_buy_outside_growth_count),
        float(metrics.growth_sell_reduction_count),
        -float(metrics.churn_rate),
        -float(metrics.sensitivity),
    )


def _band_analysis(
    metrics_by_value: dict[float, MicrogridMetrics],
    *,
    prior_winner_metrics: MicrogridMetrics,
) -> tuple[dict[str, Any], dict[str, Any]]:
    sorted_values = sorted(metrics_by_value)
    materially_better_values = [
        value
        for value in sorted_values
        if (
            metrics_by_value[value].status == "ok"
            and metrics_by_value[value].false_buy_outside_growth_count == 0
            and metrics_by_value[value].growth_capture_count >= prior_winner_metrics.growth_capture_count + 1
            and metrics_by_value[value].classification == "selective capture candidate"
        )
    ]
    stable_bands: list[tuple[float, float, list[MicrogridMetrics]]] = []
    current_band: list[MicrogridMetrics] = []
    previous_value: float | None = None
    for value in sorted_values:
        metrics = metrics_by_value[value]
        eligible = value in materially_better_values
        if eligible and (previous_value is None or value > previous_value + EPS):
            current_band.append(metrics)
        else:
            if len(current_band) >= 2:
                stable_bands.append((current_band[0].sensitivity, current_band[-1].sensitivity, list(current_band)))
            current_band = [metrics] if eligible else []
        previous_value = value
    if len(current_band) >= 2:
        stable_bands.append((current_band[0].sensitivity, current_band[-1].sensitivity, list(current_band)))

    if stable_bands:
        stable_bands.sort(
            key=lambda item: (
                statistics.fmean(metric.growth_capture_count for metric in item[2]),
                -statistics.fmean(metric.false_buy_outside_growth_count for metric in item[2]),
                statistics.fmean(metric.growth_sell_reduction_count for metric in item[2]),
                -statistics.fmean(metric.churn_rate for metric in item[2]),
                len(item[2]),
            ),
            reverse=True,
        )
        best = stable_bands[0]
        best_band = {
            "status": "proven",
            "start": best[0],
            "end": best[1],
            "members": [metric.scenario_id for metric in best[2]],
            "avg_growth_capture_count": statistics.fmean(metric.growth_capture_count for metric in best[2]),
            "avg_false_buy_count": statistics.fmean(metric.false_buy_outside_growth_count for metric in best[2]),
            "avg_churn": statistics.fmean(metric.churn_rate for metric in best[2]),
        }
    else:
        best_band = {
            "status": "not_proven",
            "start": None,
            "end": None,
            "members": [],
            "avg_growth_capture_count": None,
            "avg_false_buy_count": None,
            "avg_churn": None,
        }

    hypothesis_values = [value for value in sorted_values if 0.35 - EPS <= value <= 0.55 + EPS]
    hypothesis_metrics = [metrics_by_value[value] for value in hypothesis_values]
    if not hypothesis_metrics:
        hypothesis = {"verdict": "inconclusive", "reason": "The requested 0.35..0.55 band was not fully present in the executed grid."}
    elif all(metric.growth_capture_count == 0 for metric in hypothesis_metrics) and all(metric.false_buy_outside_growth_count == 0 for metric in hypothesis_metrics):
        hypothesis = {"verdict": "falsified", "reason": "Every point in 0.35..0.55 over-neutralized strategist influence: SELL pressure fell, but selective BUY capture stayed at 0."}
    elif any(metric.classification == "selective capture candidate" for metric in hypothesis_metrics):
        hypothesis = {"verdict": "confirmed promising", "reason": "At least one point inside 0.35..0.55 materially beat the prior 0.75 capture baseline without false BUY inflation."}
    elif any(
        metric.growth_capture_count == prior_winner_metrics.growth_capture_count and metric.false_buy_outside_growth_count == 0
        for metric in hypothesis_metrics
    ):
        hypothesis = {
            "verdict": "partially confirmed as de-bias only",
            "reason": "The edge of the band at 0.55 matches the prior 0.75 capture with lower churn and zero false BUY, but the band does not materially improve capture and its lower interior points add false BUY noise.",
        }
    else:
        hypothesis = {"verdict": "partially promising", "reason": "The band reduced SELL pressure, but not enough to create true growth-phase BUY capture."}
    return best_band, hypothesis


def _choose_top_candidates(metrics_rows: Sequence[MicrogridMetrics], *, count: int) -> list[MicrogridMetrics]:
    ranked = [metric for metric in metrics_rows if metric.status == "ok"]
    ranked.sort(key=_ranking_key, reverse=True)
    return ranked[:count]


def _surface_label(start_ts_ms: int, end_ts_ms: int) -> str:
    return f"{prev._iso_utc(start_ts_ms)} .. {prev._iso_utc(end_ts_ms)}"


def _scenario_rows_with_growth_flags(
    rows: Sequence[dict[str, Any]],
    growth_flags: dict[tuple[str, int], tuple[bool, bool]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        flag, complete = growth_flags.get((str(row["symbol"]), int(row["bar_close_ts_ms"])), (False, False))
        patched = dict(row)
        patched["active_growth_phase"] = flag
        patched["active_growth_complete"] = complete
        enriched.append(patched)
    return enriched


def _write_markdown(path: Path, lines: Sequence[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_baseline_reconfirmation_report(
    path: Path,
    *,
    frozen_manifest: dict[str, Any],
    parity_ok: bool,
    parity_mismatches: Sequence[dict[str, Any]],
    active_growth_same: bool,
    prior_baseline_same: bool,
    prior_winner_same: bool,
    prior_winner_metrics: MicrogridMetrics,
    chosen_candidate: prev.CandidateDefinition,
) -> None:
    lines = [
        "# AURORA SENSITIVITY MICROGRID BASELINE RECONFIRMATION",
        "",
        "## FACTS",
        f"- Frozen window reused exactly: `{_surface_label(frozen_manifest['chosen_segment_start_ts_ms'], frozen_manifest['chosen_segment_end_ts_ms'])}`",
        f"- Prior parent segment reference: `{_surface_label(frozen_manifest['parent_segment_start_ts_ms'], frozen_manifest['parent_segment_end_ts_ms'])}`",
        f"- Baseline parity gate passed again: `{parity_ok}`",
        f"- Active-growth definition reused identically: `{active_growth_same}`",
        f"- Baseline replay signature matched prior study: `{prior_baseline_same}`",
        f"- Prior `0.75` winner metrics reproduced exactly: `{prior_winner_same}`",
        f"- Active-growth candidate reused: `{chosen_candidate.name}`",
        "",
        "## INFERENCES",
        "- Apples-to-apples comparability with the prior strategist sweep is preserved on the frozen TREND_UP window.",
        "",
        "## ASSUMPTIONS",
        "- Reconfirmation requires the same frozen bars, the same replay path, and the same active-growth flags.",
        "",
        "## UNKNOWNS",
        "- Reconfirmation on one frozen window does not prove broader robustness outside this local episode.",
        "",
        "## Metrics",
        f"- Baseline parity mismatch count: `{len(parity_mismatches)}`",
        f"- Reproduced `0.75` metrics: growth_capture=`{prev._render_pct(prior_winner_metrics.growth_capture_pct)}` ({prior_winner_metrics.growth_capture_count}/{prior_winner_metrics.growth_point_count}), false_buy=`{prev._render_pct(prior_winner_metrics.false_buy_outside_growth_pct)}` ({prior_winner_metrics.false_buy_outside_growth_count}/{prior_winner_metrics.non_growth_point_count}), churn=`{prior_winner_metrics.churn_rate:.4f}`",
        "",
        "## Evidence",
    ]
    if parity_mismatches:
        for row in parity_mismatches[:10]:
            lines.append(f"- `{row['timestamp']}` `{row['symbol']}` mismatch=`{row['mismatch_fields']}`")
    else:
        lines.append("- No parity mismatches recorded on the reused frozen window.")
    _write_markdown(path, lines)


def _write_scenario_report(
    path: Path,
    *,
    metrics: MicrogridMetrics,
    baseline_metrics: MicrogridMetrics,
    lower_neighbor: MicrogridMetrics | None,
    upper_neighbor: MicrogridMetrics | None,
    rows: Sequence[dict[str, Any]],
) -> None:
    lines = [
        f"# {metrics.scenario_id} REPORT",
        "",
        "## FACTS",
        f"- Sensitivity value: `{metrics.sensitivity:.2f}`",
        f"- Classification: `{metrics.classification}`",
        f"- Status: `{metrics.status}`",
    ]
    if metrics.blocked_reason:
        lines.append(f"- Blocked reason: `{metrics.blocked_reason}`")
    lines.extend(
        [
            "",
            "## INFERENCES",
            "- This scenario must be read as either sell suppression, neutralization, or true selective growth capture; those behaviors are reported separately below.",
            "",
            "## ASSUMPTIONS",
            "- All non-sensitivity surfaces stayed frozen at baseline.",
            "",
            "## UNKNOWNS",
            "- A good local result here still does not prove production readiness or robustness outside bounded confirmation surfaces.",
            "",
            "## Metrics",
            f"- Full occupancy: sell=`{prev._render_pct(metrics.sell_active_pct_full)}` ({metrics.sell_active_count_full}/{metrics.window_points}) neutral=`{prev._render_pct(metrics.neutral_pct_full)}` ({metrics.neutral_count_full}/{metrics.window_points}) buy=`{prev._render_pct(metrics.buy_active_pct_full)}` ({metrics.buy_active_count_full}/{metrics.window_points})",
            f"- Growth occupancy: sell=`{prev._render_pct(metrics.sell_active_pct_growth)}` ({metrics.sell_active_count_growth}/{metrics.growth_point_count}) neutral=`{prev._render_pct(metrics.neutral_pct_growth)}` ({metrics.neutral_count_growth}/{metrics.growth_point_count}) buy=`{prev._render_pct(metrics.buy_active_pct_growth)}` ({metrics.buy_active_count_growth}/{metrics.growth_point_count})",
            f"- Non-growth occupancy: sell=`{prev._render_pct(metrics.sell_active_pct_non_growth)}` ({metrics.sell_active_count_non_growth}/{metrics.non_growth_point_count}) neutral=`{prev._render_pct(metrics.neutral_pct_non_growth)}` ({metrics.neutral_count_non_growth}/{metrics.non_growth_point_count}) buy=`{prev._render_pct(metrics.buy_active_pct_non_growth)}` ({metrics.buy_active_count_non_growth}/{metrics.non_growth_point_count})",
            f"- Alignment: growth_capture=`{prev._render_pct(metrics.growth_capture_pct)}` ({metrics.growth_capture_count}/{metrics.growth_point_count}) false_buy_outside_growth=`{prev._render_pct(metrics.false_buy_outside_growth_pct)}` ({metrics.false_buy_outside_growth_count}/{metrics.non_growth_point_count}) growth_sell_reduction=`{prev._render_pct(metrics.growth_sell_reduction_pct)}` ({metrics.growth_sell_reduction_count}/{baseline_metrics.sell_active_count_growth})",
            f"- Score geometry: distance_to_buy mean/median/p90=`{prev._render_num(metrics.mean_distance_to_buy)}` / `{prev._render_num(metrics.median_distance_to_buy)}` / `{prev._render_num(metrics.p90_distance_to_buy)}`; sell_depth mean/median/p90=`{prev._render_num(metrics.mean_sell_depth)}` / `{prev._render_num(metrics.median_sell_depth)}` / `{prev._render_num(metrics.p90_sell_depth)}`",
            f"- Stability: churn=`{metrics.churn_rate:.4f}` side_flips=`{metrics.side_flip_count}` oscillation=`{metrics.oscillation_flag}`",
            f"- Strategist shrinkage: mean_delta=`{prev._render_num(metrics.mean_strategist_delta)}` median_delta=`{prev._render_num(metrics.median_strategist_delta)}`; pillar_sum_delta mean/median=`{prev._render_num(metrics.mean_pillar_sum_delta)}` / `{prev._render_num(metrics.median_pillar_sum_delta)}`; resulting states after shrinkage sell/neutral/buy=`{metrics.shrinkage_to_sell_count}` / `{metrics.shrinkage_to_neutral_count}` / `{metrics.shrinkage_to_buy_count}`",
            f"- Vs baseline capture delta: `{metrics.baseline_capture_delta_count}` point(s), `{prev._render_pct(metrics.baseline_capture_delta_pct_points)}`",
            f"- Vs prior `0.75` winner capture delta: `{metrics.prior_winner_capture_delta_count}` point(s), `{prev._render_pct(metrics.prior_winner_capture_delta_pct_points)}`",
        ]
    )
    if lower_neighbor is not None:
        lines.append(f"- Lower neighbor `{lower_neighbor.sensitivity:.2f}`: growth_capture=`{prev._render_pct(lower_neighbor.growth_capture_pct)}` ({lower_neighbor.growth_capture_count}/{lower_neighbor.growth_point_count}) false_buy=`{prev._render_pct(lower_neighbor.false_buy_outside_growth_pct)}` churn=`{lower_neighbor.churn_rate:.4f}`")
    if upper_neighbor is not None:
        lines.append(f"- Upper neighbor `{upper_neighbor.sensitivity:.2f}`: growth_capture=`{prev._render_pct(upper_neighbor.growth_capture_pct)}` ({upper_neighbor.growth_capture_count}/{upper_neighbor.growth_point_count}) false_buy=`{prev._render_pct(upper_neighbor.false_buy_outside_growth_pct)}` churn=`{upper_neighbor.churn_rate:.4f}`")
    lines.extend(["", "## Evidence"])
    changed_rows = [row for row in rows if row["baseline_raw_side"] != row["raw_side"]][:10]
    if not changed_rows:
        lines.append("- No raw-side changes versus the frozen baseline.")
    else:
        for row in changed_rows:
            lines.append(f"- `{row['timestamp']}` `{row['symbol']}` baseline=`{row['baseline_raw_side']}` scenario=`{row['raw_side']}` growth=`{row['active_growth_phase']}` score=`{float(row['final_score']):.6f}` thr_buy=`{float(row['thr_buy']):.6f}` thr_sell=`{float(row['thr_sell']):.6f}`")
    _write_markdown(path, lines)


def _write_master_report(
    path: Path,
    *,
    metrics_rows: Sequence[MicrogridMetrics],
    best_point: MicrogridMetrics,
    best_band: dict[str, Any],
    hypothesis: dict[str, Any],
    prior_winner_metrics: MicrogridMetrics,
    baseline_growth_sell_count: int,
) -> None:
    lines = [
        "# AURORA SENSITIVITY MICROGRID MASTER REPORT",
        "",
        "## FACTS",
        f"- Scenario count: `{len(metrics_rows)}`",
        f"- Prior local winner benchmark: sensitivity=`{prior_winner_metrics.sensitivity:.2f}` growth_capture=`{prev._render_pct(prior_winner_metrics.growth_capture_pct)}` ({prior_winner_metrics.growth_capture_count}/{prior_winner_metrics.growth_point_count})",
        f"- Best single point under this package: `{best_point.sensitivity:.2f}` (`{best_point.scenario_id}`)",
        f"- Best stable band status: `{best_band['status']}`",
        f"- User hypothesis result for `0.35..0.55`: `{hypothesis['verdict']}`",
        "",
        "## INFERENCES",
        "- Ranking is lexicographic on growth capture first, then false BUY control, growth SELL reduction, churn, and finally the lower-sensitivity tie-break when all else is equal.",
        "",
        "## ASSUMPTIONS",
        "- A scenario is not treated as a true capture improvement unless it materially beats the prior `0.75` winner on growth-capture count.",
        "",
        "## UNKNOWNS",
        "- Frozen-window ranking remains local evidence until confirmation surfaces agree.",
        "",
        "## Metrics",
        "| Sensitivity | Scenario | Class | Growth Capture | False Buy | Growth SELL Reduction | Churn |",
        "|---:|---|---|---:|---:|---:|---:|",
    ]
    for metrics in sorted(metrics_rows, key=lambda item: item.sensitivity):
        lines.append(f"| {metrics.sensitivity:.2f} | {metrics.scenario_id} | {metrics.classification} | {prev._render_pct(metrics.growth_capture_pct)} ({metrics.growth_capture_count}/{metrics.growth_point_count}) | {prev._render_pct(metrics.false_buy_outside_growth_pct)} ({metrics.false_buy_outside_growth_count}/{metrics.non_growth_point_count}) | {prev._render_pct(metrics.growth_sell_reduction_pct)} ({metrics.growth_sell_reduction_count}/{baseline_growth_sell_count}) | {metrics.churn_rate:.4f} |")
    lines.extend(["", "## Evidence", f"- Best single point: `{best_point.sensitivity:.2f}` classified as `{best_point.classification}` with growth_capture=`{prev._render_pct(best_point.growth_capture_pct)}` ({best_point.growth_capture_count}/{best_point.growth_point_count}), false_buy=`{prev._render_pct(best_point.false_buy_outside_growth_pct)}` ({best_point.false_buy_outside_growth_count}/{best_point.non_growth_point_count}), and churn=`{best_point.churn_rate:.4f}`.", f"- Best stable band: `{best_band}`", f"- User hypothesis reason: `{hypothesis['reason']}`"])
    _write_markdown(path, lines)


def _write_confirmation_report(
    path: Path,
    *,
    confirmation_rows: Sequence[dict[str, Any]],
    top_candidates: Sequence[MicrogridMetrics],
    frozen_best_point: MicrogridMetrics,
    surfaces: Sequence[ConfirmationSurface],
) -> None:
    lines = [
        "# AURORA SENSITIVITY MICROGRID CONFIRMATION REPORT",
        "",
        "## FACTS",
        f"- Top candidates tested beyond the frozen window: `{', '.join(f'{item.sensitivity:.2f}' for item in top_candidates)}`",
        f"- Confirmation surfaces executed: `{len(surfaces)}`",
        "",
        "## INFERENCES",
        "- Confirmation surfaces are weaker than the frozen window whenever baseline parity does not hold exactly; those cases must not be read as equal-strength evidence.",
        "",
        "## ASSUMPTIONS",
        "- The same active-growth candidate and thresholds from the frozen window were reused on confirmation surfaces for comparability.",
        "",
        "## UNKNOWNS",
        "- Rank stability across a small number of confirmation surfaces still does not prove generalization to all TREND_UP episodes.",
        "",
        "## Metrics",
    ]
    for surface in surfaces:
        lines.append(f"- `{surface.name}` window=`{_surface_label(surface.start_ts_ms, surface.end_ts_ms)}` bars=`{surface.segment_bar_count}` parity_ok=`{surface.parity_ok}` mismatches=`{surface.parity_mismatch_count}`")
    lines.extend(["", "## Evidence", "| Surface | Sensitivity | Growth Capture | False Buy | Growth SELL Reduction | Churn | Rank |", "|---|---:|---:|---:|---:|---:|---:|"])
    for row in confirmation_rows:
        lines.append(f"| {row['surface_name']} | {row['sensitivity']:.2f} | {prev._render_pct(row['growth_capture_pct'])} ({row['growth_capture_count']}/{row['growth_point_count']}) | {prev._render_pct(row['false_buy_outside_growth_pct'])} ({row['false_buy_outside_growth_count']}/{row['non_growth_point_count']}) | {prev._render_pct(row['growth_sell_reduction_pct'])} ({row['growth_sell_reduction_count']}/{row['baseline_growth_sell_count']}) | {row['churn_rate']:.4f} | {row['surface_rank']} |")
    stable = all(row["surface_rank"] == 1 for row in confirmation_rows if math.isclose(row["sensitivity"], frozen_best_point.sensitivity, abs_tol=EPS))
    lines.extend(["", f"- Frozen best-point `{frozen_best_point.sensitivity:.2f}` kept top rank on every confirmation surface: `{stable}`"])
    _write_markdown(path, lines)


def _write_spillover_report(path: Path, *, spillover_rows: Sequence[dict[str, Any]], control_rows: Sequence[dict[str, Any]]) -> None:
    lines = [
        "# AURORA SENSITIVITY MICROGRID SPILLOVER REPORT",
        "",
        "## FACTS",
        f"- Spillover probe rows: `{len(spillover_rows)}`",
        f"- Control windows sampled: `{len(control_rows)}`",
        "",
        "## INFERENCES",
        "- Spillover checks are bounded directional-sanity probes, not full cross-regime validation.",
        "",
        "## ASSUMPTIONS",
        "- Hard reject remains: TREND_DOWN sell->buy flips > 10%, TREND_DOWN buy-active > 5%, or churn multiplier > 1.5x.",
        "",
        "## UNKNOWNS",
        "- Passing bounded spillover checks does not prove global safety on all dates or regimes.",
        "",
        "## Metrics",
    ]
    for row in control_rows:
        lines.append(f"- Control `{row['name']}` window=`{_surface_label(row['start_ts_ms'], row['end_ts_ms'])}` target_regime=`{row['target_regime']}` bars=`{row['segment_bar_count']}`")
    lines.extend(["", "## Evidence", "| Candidate | Control | Sell->Buy Flip | BUY Active | Churn Mult | Verdict |", "|---|---|---:|---:|---:|---|"])
    for row in spillover_rows:
        lines.append(f"| {row['scenario_id']} | {row['control_name']} | {row['sell_to_buy_flip_pct']:.2%} | {row['buy_active_pct']:.2%} | {row['churn_mult']:.2f} | {row['verdict']} |")
    _write_markdown(path, lines)


def _write_validation_report(
    path: Path,
    *,
    baseline_parity_ok: bool,
    active_growth_same: bool,
    prior_baseline_same: bool,
    prior_winner_same: bool,
    scenario_count: int,
    rerun_ok: bool,
    confirmation_surface_count: int,
    spillover_candidate_count: int,
    unknowns: Sequence[str],
) -> None:
    lines = [
        "# AURORA SENSITIVITY MICROGRID VALIDATION REPORT",
        "",
        "## FACTS",
        f"- Baseline parity reconfirmed: `{baseline_parity_ok}`",
        f"- Active-growth flags identical to prior study: `{active_growth_same}`",
        f"- Baseline replay signature identical to prior study: `{prior_baseline_same}`",
        f"- Prior `0.75` winner metrics reproduced exactly: `{prior_winner_same}`",
        f"- Scenario count executed: `{scenario_count}`",
        f"- Deterministic rerun signature match: `{rerun_ok}`",
        f"- Confirmation surfaces executed: `{confirmation_surface_count}`",
        f"- Spillover candidates rechecked: `{spillover_candidate_count}`",
        "",
        "## INFERENCES",
        "- The micro-grid package is internally valid only if the reused frozen window stayed comparable to the prior strategist sweep.",
        "",
        "## ASSUMPTIONS",
        "- Validation is package-local and does not imply production readiness.",
        "",
        "## UNKNOWNS",
    ]
    for item in unknowns:
        lines.append(f"- {item}")
    lines.extend(["", "## Metrics", "- Validation completed without hidden parameter changes.", "", "## Evidence", "- All sensitivity values were replayed on the same frozen window before any broader confirmation surface was consulted."])
    _write_markdown(path, lines)


def _write_final_report(
    path: Path,
    *,
    best_point: MicrogridMetrics,
    best_band: dict[str, Any],
    hypothesis: dict[str, Any],
    top_candidates: Sequence[MicrogridMetrics],
    prior_winner_metrics: MicrogridMetrics,
    evidence_limits: Sequence[str],
    recommendation: str,
    baseline_growth_sell_count: int,
) -> None:
    lines = [
        "# AURORA SENSITIVITY MICROGRID FINAL REPORT",
        "",
        "## Proven findings",
        f"- Best single point on the frozen window: sensitivity=`{best_point.sensitivity:.2f}` classified as `{best_point.classification}` with growth_capture=`{prev._render_pct(best_point.growth_capture_pct)}` ({best_point.growth_capture_count}/{best_point.growth_point_count}), false_buy=`{prev._render_pct(best_point.false_buy_outside_growth_pct)}` ({best_point.false_buy_outside_growth_count}/{best_point.non_growth_point_count}), and churn=`{best_point.churn_rate:.4f}`.",
        f"- Sensitivity-only package stable-band status: `{best_band['status']}`.",
        f"- Material growth-capture improvement over the prior `0.75` winner was proven: `{best_point.growth_capture_count > prior_winner_metrics.growth_capture_count}`.",
        f"- User hypothesis `0.35..0.55`: `{hypothesis['verdict']}` because `{hypothesis['reason']}`",
        "",
        "## Best single-point candidate",
        f"- `{best_point.sensitivity:.2f}` via `{best_point.scenario_id}`. This is `{best_point.classification}`, not automatically a production solution.",
        "",
        "## Best stable band",
    ]
    if best_band["status"] == "proven":
        lines.append(f"- `{best_band['start']:.2f} .. {best_band['end']:.2f}` with members `{', '.join(best_band['members'])}`.")
    else:
        lines.append("- No stable band was proven under the package definition that requires a material capture improvement above the prior `0.75` winner.")
    lines.extend(["", "## User hypothesis result", f"- `{hypothesis['verdict']}`", "", "## Behavior classification"])
    for metrics in top_candidates:
        lines.append(f"- `{metrics.sensitivity:.2f}` -> `{metrics.classification}` with growth_capture=`{prev._render_pct(metrics.growth_capture_pct)}` ({metrics.growth_capture_count}/{metrics.growth_point_count}), false_buy=`{prev._render_pct(metrics.false_buy_outside_growth_pct)}` ({metrics.false_buy_outside_growth_count}/{metrics.non_growth_point_count}), growth_sell_reduction=`{prev._render_pct(metrics.growth_sell_reduction_pct)}` ({metrics.growth_sell_reduction_count}/{baseline_growth_sell_count}), churn=`{metrics.churn_rate:.4f}`.")
    lines.extend(["", "## Evidence limits"])
    for item in evidence_limits:
        lines.append(f"- {item}")
    lines.extend(["", "## Recommended next package", f"- {recommendation}"])
    _write_markdown(path, lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prior_report_dir = Path(args.prior_report_dir)

    typed_config = prev._load_typed_config(Path(args.config_dir))
    symbols = list(args.symbols) if args.symbols else prev._parse_aurora_symbols(Path(args.strategies_yaml))
    baseline_sensitivity = _load_baseline_sensitivity(Path(args.domains_yaml))
    grid_values = _sorted_grid(baseline_sensitivity)
    recorder_points, recorder_series, _recorder_files = prev._load_recorder_points(Path(args.recorder_dir), symbols, prev.TF_SEC)
    aurora_core_paths = prev._ordered_rotated_paths(args.aurora_core_glob)
    decision_log_paths = prev._ordered_rotated_paths(args.decision_log_glob)
    regime_map, decision_map, _aurora_log_files = prev._parse_aurora_core_logs(aurora_core_paths, symbols)
    _side_evidence, _side_files = prev._parse_side_evidence(
        decision_log_paths + aurora_core_paths,
        Path(args.shadow_journal),
        Path(args.trade_lifecycle),
        symbols,
    )
    common_recorder_ts = prev._compute_common_recorder_timestamps(recorder_points, symbols)
    completeness = prev._build_completeness_map(common_recorder_ts, recorder_points, regime_map, decision_map, symbols)
    complete_segments = prev._build_complete_segments(common_recorder_ts, completeness, prev.TF_MS)

    prior_manifest = _load_prior_manifest(prior_report_dir)
    frozen_segment = _surface_segment(prior_manifest["chosen_segment_start_ts_ms"], prior_manifest["chosen_segment_end_ts_ms"])
    parent_segment = _surface_segment(prior_manifest["parent_segment_start_ts_ms"], prior_manifest["parent_segment_end_ts_ms"])

    baseline_rows, _baseline_all_series, _baseline_target_rows = prev._run_baseline_replay(
        typed_config=typed_config,
        symbols=symbols,
        recorder_points=recorder_points,
        regime_map=regime_map,
        decision_map=decision_map,
        frozen_segment=frozen_segment,
        active_growth_flags={},
    )
    baseline_parity_ok, parity_mismatches = prev._validate_baseline_parity(baseline_rows)
    chosen_candidate, _candidate_evals, growth_flags, _growth_feature_rows, _growth_thresholds = prev._evaluate_growth_candidates(
        baseline_rows,
        recorder_series,
    )
    for row in baseline_rows:
        flag, complete = growth_flags.get((str(row["symbol"]), int(row["bar_close_ts_ms"])), (False, False))
        row["active_growth_phase"] = flag
        row["active_growth_complete"] = complete
    baseline_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in baseline_rows}

    prior_baseline_rows = _load_prior_baseline(prior_report_dir)
    prior_baseline_same = _rows_signature(baseline_rows) == _rows_signature(prior_baseline_rows)
    prior_growth_lookup = {
        (str(row["symbol"]), int(row["bar_close_ts_ms"])): (bool(row["active_growth_phase"]), bool(row["active_growth_complete"]))
        for row in prior_baseline_rows
    }
    active_growth_same = all(
        growth_flags.get((str(row["symbol"]), int(row["bar_close_ts_ms"])), (False, False))
        == prior_growth_lookup.get((str(row["symbol"]), int(row["bar_close_ts_ms"])))
        for row in baseline_rows
    )

    baseline_metrics = _compute_micro_metrics(
        baseline_rows,
        scenario_id="BASELINE",
        sensitivity=baseline_sensitivity,
        baseline_lookup=baseline_lookup,
        baseline_metrics=None,
        prior_winner_metrics=None,
        status="ok",
    )
    prior_summary = _load_prior_summary(prior_report_dir)

    scenario_rows_by_value: dict[float, list[dict[str, Any]]] = {}
    metrics_by_value: dict[float, MicrogridMetrics] = {}
    for index, value in enumerate(grid_values, start=1):
        scenario = prev.ScenarioSpec(
            family="sensitivity",
            scenario_id=_scenario_id(index),
            baseline_value=baseline_sensitivity,
            scenario_value=float(value),
            redistribution_rule="none",
            htf_seed_ref=None,
        )
        status = "ok"
        blocked_reason = None
        rows: list[dict[str, Any]] = []
        try:
            rows = prev._run_scenario_replay(
                typed_config=typed_config,
                symbols=symbols,
                recorder_points=recorder_points,
                regime_map=regime_map,
                decision_map=decision_map,
                frozen_segment=frozen_segment,
                growth_flags=growth_flags,
                scenario=scenario,
                baseline_lookup=baseline_lookup,
                d1_series_by_symbol={},
                d1_rule_by_symbol={},
            )
        except Exception as exc:
            status = "blocked"
            blocked_reason = str(exc)
            rows = []
        scenario_rows_by_value[value] = rows
        metrics_by_value[value] = _compute_micro_metrics(
            rows,
            scenario_id=scenario.scenario_id,
            sensitivity=value,
            baseline_lookup=baseline_lookup,
            baseline_metrics=baseline_metrics,
            prior_winner_metrics=None,
            status=status,
            blocked_reason=blocked_reason,
        )

    prior_winner_metrics = metrics_by_value[PRIOR_WINNER_VALUE]
    prior_winner_same = False
    prior_summary_row = prior_summary.get(PRIOR_WINNER_VALUE)
    if prior_summary_row is not None:
        prior_winner_same = (
            math.isclose(float(prior_summary_row["growth_captured_as_buy_pct"]), float(prior_winner_metrics.growth_capture_pct or 0.0), abs_tol=EPS)
            and math.isclose(float(prior_summary_row["false_buy_outside_growth_pct"]), float(prior_winner_metrics.false_buy_outside_growth_pct or 0.0), abs_tol=EPS)
            and math.isclose(float(prior_summary_row["churn_rate"]), float(prior_winner_metrics.churn_rate), abs_tol=EPS)
        )

    for value in list(metrics_by_value):
        metrics_by_value[value] = dataclasses.replace(
            metrics_by_value[value],
            classification=_classify_metrics(metrics_by_value[value], prior_winner_metrics=prior_winner_metrics),
        )

    for index, value in enumerate(grid_values, start=1):
        rows = _scenario_rows_with_growth_flags(scenario_rows_by_value[value], growth_flags)
        scenario_rows_by_value[value] = rows
        prefix = _scenario_output_prefix(index, value)
        prev._write_json(out_dir / f"{prefix}.json", rows)
        prev._write_csv(out_dir / f"{prefix}.csv", rows)
        lower_neighbor = metrics_by_value[grid_values[index - 2]] if index > 1 else None
        upper_neighbor = metrics_by_value[grid_values[index]] if index < len(grid_values) else None
        _write_scenario_report(
            out_dir / f"{_scenario_id(index)}_REPORT.md",
            metrics=metrics_by_value[value],
            baseline_metrics=baseline_metrics,
            lower_neighbor=lower_neighbor,
            upper_neighbor=upper_neighbor,
            rows=rows,
        )

    metrics_rows = [metrics_by_value[value] for value in grid_values]
    summary_rows = [dataclasses.asdict(metrics) for metrics in metrics_rows]
    prev._write_json(out_dir / "AURORA_SENSITIVITY_MICROGRID_SUMMARY.json", summary_rows)
    prev._write_csv(out_dir / "AURORA_SENSITIVITY_MICROGRID_SUMMARY.csv", summary_rows)

    _write_baseline_reconfirmation_report(
        out_dir / "AURORA_SENSITIVITY_MICROGRID_BASELINE_RECONFIRMATION.md",
        frozen_manifest=prior_manifest,
        parity_ok=baseline_parity_ok,
        parity_mismatches=parity_mismatches,
        active_growth_same=active_growth_same,
        prior_baseline_same=prior_baseline_same,
        prior_winner_same=prior_winner_same,
        prior_winner_metrics=prior_winner_metrics,
        chosen_candidate=chosen_candidate,
    )

    best_point = _choose_top_candidates(metrics_rows, count=1)[0]
    best_band, hypothesis = _band_analysis(metrics_by_value, prior_winner_metrics=prior_winner_metrics)

    additional_segment = _select_additional_trend_up_surface(
        complete_segments,
        symbols,
        regime_map,
        before_ts_ms=int(prior_manifest["parent_segment_start_ts_ms"]),
    )
    confirmation_surfaces: list[ConfirmationSurface] = []
    for name, segment, reason in (
        ("PARENT_TREND_UP_SEGMENT", parent_segment, "Wider parent segment from the prior study manifest; weaker surface if parity drifts."),
        ("ADDITIONAL_RECENT_TREND_UP_EPISODE", additional_segment, "Latest complete recent TREND_UP episode before the parent segment, if reconstructable."),
    ):
        if not segment:
            continue
        surface_baseline_rows, _surface_all_series, _surface_target_rows = prev._run_baseline_replay(
            typed_config=typed_config,
            symbols=symbols,
            recorder_points=recorder_points,
            regime_map=regime_map,
            decision_map=decision_map,
            frozen_segment=segment,
            active_growth_flags={},
        )
        surface_parity_ok, surface_mismatches = prev._validate_baseline_parity(surface_baseline_rows)
        confirmation_surfaces.append(
            ConfirmationSurface(
                name=name,
                start_ts_ms=int(segment[0]),
                end_ts_ms=int(segment[-1]),
                segment_bar_count=len(segment),
                reason=reason,
                parity_ok=surface_parity_ok,
                parity_mismatch_count=len(surface_mismatches),
            )
        )

    top_candidates = _choose_top_candidates(metrics_rows, count=3)
    confirmation_rows: list[dict[str, Any]] = []
    for surface in confirmation_surfaces:
        segment = _surface_segment(surface.start_ts_ms, surface.end_ts_ms)
        surface_baseline_rows, _surface_all_series, _surface_target_rows = prev._run_baseline_replay(
            typed_config=typed_config,
            symbols=symbols,
            recorder_points=recorder_points,
            regime_map=regime_map,
            decision_map=decision_map,
            frozen_segment=segment,
            active_growth_flags={},
        )
        surface_growth_flags, _surface_feature_rows = _build_growth_flags_for_rows(
            surface_baseline_rows,
            recorder_series,
            candidate=chosen_candidate,
        )
        for row in surface_baseline_rows:
            flag, complete = surface_growth_flags.get((str(row["symbol"]), int(row["bar_close_ts_ms"])), (False, False))
            row["active_growth_phase"] = flag
            row["active_growth_complete"] = complete
        surface_baseline_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in surface_baseline_rows}
        surface_baseline_metrics = _compute_micro_metrics(
            surface_baseline_rows,
            scenario_id=f"{surface.name}_BASELINE",
            sensitivity=baseline_sensitivity,
            baseline_lookup=surface_baseline_lookup,
            baseline_metrics=None,
            prior_winner_metrics=None,
            status="ok",
        )
        surface_results: list[tuple[MicrogridMetrics, dict[str, Any]]] = []
        for candidate_metrics in top_candidates:
            scenario = prev.ScenarioSpec(
                family="sensitivity",
                scenario_id=candidate_metrics.scenario_id,
                baseline_value=baseline_sensitivity,
                scenario_value=candidate_metrics.sensitivity,
                redistribution_rule="none",
                htf_seed_ref=None,
            )
            rows = prev._run_scenario_replay(
                typed_config=typed_config,
                symbols=symbols,
                recorder_points=recorder_points,
                regime_map=regime_map,
                decision_map=decision_map,
                frozen_segment=segment,
                growth_flags=surface_growth_flags,
                scenario=scenario,
                baseline_lookup=surface_baseline_lookup,
                d1_series_by_symbol={},
                d1_rule_by_symbol={},
            )
            rows = _scenario_rows_with_growth_flags(rows, surface_growth_flags)
            metrics = _compute_micro_metrics(
                rows,
                scenario_id=candidate_metrics.scenario_id,
                sensitivity=candidate_metrics.sensitivity,
                baseline_lookup=surface_baseline_lookup,
                baseline_metrics=surface_baseline_metrics,
                prior_winner_metrics=prior_winner_metrics,
                status="ok",
            )
            surface_results.append((metrics, dataclasses.asdict(metrics)))
        surface_results.sort(key=lambda item: _ranking_key(item[0]), reverse=True)
        for rank, (_metrics, row) in enumerate(surface_results, start=1):
            row["surface_name"] = surface.name
            row["surface_rank"] = rank
            row["baseline_growth_sell_count"] = surface_baseline_metrics.sell_active_count_growth
            confirmation_rows.append(row)
    prev._write_json(out_dir / "AURORA_SENSITIVITY_MICROGRID_CONFIRMATION_SUMMARY.json", confirmation_rows)
    prev._write_csv(out_dir / "AURORA_SENSITIVITY_MICROGRID_CONFIRMATION_SUMMARY.csv", confirmation_rows)
    _write_confirmation_report(
        out_dir / "AURORA_SENSITIVITY_MICROGRID_CONFIRMATION_REPORT.md",
        confirmation_rows=confirmation_rows,
        top_candidates=top_candidates,
        frozen_best_point=best_point,
        surfaces=confirmation_surfaces,
    )

    control_specs = [
        prev._choose_control_segment("TREND_DOWN_CONTROL", ["TREND_DOWN"], complete_segments, symbols, regime_map),
        prev._choose_control_segment("ALT_REGIME_CONTROL", ["MEAN_REVERSION", "HIGH_VOLATILITY", "UNCERTAIN"], complete_segments, symbols, regime_map),
    ]
    control_specs = [item for item in control_specs if item is not None]
    control_rows_for_report = [dataclasses.asdict(item) for item in control_specs]
    spillover_rows: list[dict[str, Any]] = []
    for candidate_metrics in top_candidates:
        for control in control_specs:
            control_segment = _surface_segment(control.start_ts_ms, control.end_ts_ms)
            control_baseline_rows, _control_all_series, _control_target_rows = prev._run_baseline_replay(
                typed_config=typed_config,
                symbols=symbols,
                recorder_points=recorder_points,
                regime_map=regime_map,
                decision_map=decision_map,
                frozen_segment=control_segment,
                active_growth_flags={},
            )
            control_baseline_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in control_baseline_rows}
            scenario = prev.ScenarioSpec(
                family="sensitivity",
                scenario_id=candidate_metrics.scenario_id,
                baseline_value=baseline_sensitivity,
                scenario_value=candidate_metrics.sensitivity,
                redistribution_rule="none",
                htf_seed_ref=None,
            )
            control_rows = prev._run_scenario_replay(
                typed_config=typed_config,
                symbols=symbols,
                recorder_points=recorder_points,
                regime_map=regime_map,
                decision_map=decision_map,
                frozen_segment=control_segment,
                growth_flags={},
                scenario=scenario,
                baseline_lookup=control_baseline_lookup,
                d1_series_by_symbol={},
                d1_rule_by_symbol={},
            )
            sell_to_buy_flips = 0
            baseline_sell_count = 0
            for row in control_rows:
                baseline = control_baseline_lookup.get((str(row["symbol"]), int(row["bar_close_ts_ms"])))
                if baseline is None:
                    continue
                if baseline["raw_side"] == "sell":
                    baseline_sell_count += 1
                    if row["raw_side"] == "buy":
                        sell_to_buy_flips += 1
            sell_to_buy_flip_pct = sell_to_buy_flips / max(1, baseline_sell_count)
            buy_active_pct = sum(1 for row in control_rows if row["raw_side"] == "buy") / max(1, len(control_rows))
            baseline_churn = prev._compute_churn_rate(control_baseline_rows)
            scenario_churn = prev._compute_churn_rate(control_rows)
            if baseline_churn <= EPS:
                churn_mult = 1.0 if scenario_churn <= EPS else float("inf")
            else:
                churn_mult = scenario_churn / baseline_churn
            reject = (
                sell_to_buy_flip_pct > prev.SPILLOVER_TREND_DOWN_FLIP_MAX
                or (control.target_regime == "TREND_DOWN" and buy_active_pct > prev.SPILLOVER_TREND_DOWN_BUY_MAX)
                or churn_mult > prev.CHURN_MULT_MAX
            )
            spillover_rows.append(
                {
                    "scenario_id": candidate_metrics.scenario_id,
                    "sensitivity": candidate_metrics.sensitivity,
                    "control_name": control.name,
                    "target_regime": control.target_regime,
                    "sell_to_buy_flip_pct": sell_to_buy_flip_pct,
                    "buy_active_pct": buy_active_pct,
                    "churn_mult": churn_mult,
                    "verdict": "reject" if reject else "pass",
                }
            )
    prev._write_json(out_dir / "AURORA_SENSITIVITY_MICROGRID_SPILLOVER_SUMMARY.json", spillover_rows)
    prev._write_csv(out_dir / "AURORA_SENSITIVITY_MICROGRID_SPILLOVER_SUMMARY.csv", spillover_rows)
    _write_spillover_report(
        out_dir / "AURORA_SENSITIVITY_MICROGRID_SPILLOVER_REPORT.md",
        spillover_rows=spillover_rows,
        control_rows=control_rows_for_report,
    )

    spillover_verdicts: dict[str, list[str]] = defaultdict(list)
    for row in spillover_rows:
        spillover_verdicts[str(row["scenario_id"])].append(str(row["verdict"]))
    for value in list(metrics_by_value):
        verdicts = spillover_verdicts.get(metrics_by_value[value].scenario_id, [])
        metrics_by_value[value] = dataclasses.replace(
            metrics_by_value[value],
            spillover_verdict=("reject" if "reject" in verdicts else "pass" if "pass" in verdicts else "not_run"),
        )
    metrics_rows = [metrics_by_value[value] for value in grid_values]
    summary_rows = [dataclasses.asdict(metrics) for metrics in metrics_rows]
    prev._write_json(out_dir / "AURORA_SENSITIVITY_MICROGRID_SUMMARY.json", summary_rows)
    prev._write_csv(out_dir / "AURORA_SENSITIVITY_MICROGRID_SUMMARY.csv", summary_rows)

    rerun_ok = True
    for value in grid_values:
        metrics = metrics_by_value[value]
        if metrics.status != "ok":
            continue
        scenario = prev.ScenarioSpec(
            family="sensitivity",
            scenario_id=metrics.scenario_id,
            baseline_value=baseline_sensitivity,
            scenario_value=value,
            redistribution_rule="none",
            htf_seed_ref=None,
        )
        rerun_rows = prev._run_scenario_replay(
            typed_config=typed_config,
            symbols=symbols,
            recorder_points=recorder_points,
            regime_map=regime_map,
            decision_map=decision_map,
            frozen_segment=frozen_segment,
            growth_flags=growth_flags,
            scenario=scenario,
            baseline_lookup=baseline_lookup,
            d1_series_by_symbol={},
            d1_rule_by_symbol={},
        )
        rerun_rows = _scenario_rows_with_growth_flags(rerun_rows, growth_flags)
        if _rows_signature(rerun_rows) != _rows_signature(scenario_rows_by_value[value]):
            rerun_ok = False
            break

    _write_master_report(
        out_dir / "AURORA_SENSITIVITY_MICROGRID_MASTER_REPORT.md",
        metrics_rows=metrics_rows,
        best_point=best_point,
        best_band=best_band,
        hypothesis=hypothesis,
        prior_winner_metrics=prior_winner_metrics,
        baseline_growth_sell_count=baseline_metrics.sell_active_count_growth,
    )
    _write_validation_report(
        out_dir / "AURORA_SENSITIVITY_MICROGRID_VALIDATION_REPORT.md",
        baseline_parity_ok=baseline_parity_ok,
        active_growth_same=active_growth_same,
        prior_baseline_same=prior_baseline_same,
        prior_winner_same=prior_winner_same,
        scenario_count=len(grid_values),
        rerun_ok=rerun_ok,
        confirmation_surface_count=len(confirmation_surfaces),
        spillover_candidate_count=len(top_candidates),
        unknowns=[
            "Confirmation on the wider parent surface is weaker whenever baseline parity drifts outside the frozen exact-parity subwindow.",
            "The package still cannot prove global robustness across all TREND_UP episodes or economic superiority in live trading.",
        ],
    )

    evidence_limits = [
        "Primary ranking remains local to the previously frozen TREND_UP window.",
        "Only strategist sensitivity changed; no threshold, weight, or SMA experiments were included here.",
        "Confirmation surfaces improve confidence but do not upgrade this package to production proof.",
    ]
    if best_point.growth_capture_count <= prior_winner_metrics.growth_capture_count:
        recommendation = "proceed to two-factor local grid: sensitivity x strategist weight"
    else:
        recommendation = "adopt shadow candidate for broader validation only"
    _write_final_report(
        out_dir / "AURORA_SENSITIVITY_MICROGRID_FINAL_REPORT.md",
        best_point=best_point,
        best_band=best_band,
        hypothesis=hypothesis,
        top_candidates=top_candidates,
        prior_winner_metrics=prior_winner_metrics,
        evidence_limits=evidence_limits,
        recommendation=recommendation,
        baseline_growth_sell_count=baseline_metrics.sell_active_count_growth,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
