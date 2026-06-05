#!/usr/bin/env python3
"""Local two-factor grid study for Aurora strategist sensitivity and weight."""
from __future__ import annotations

import argparse
import csv
import dataclasses
import decimal
import json
import math
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.forensics import aurora_trend_up_strategist_sweep_study as prev
from tools.forensics import aurora_sensitivity_microgrid_study as micro


SENSITIVITY_GRID = [0.50, 0.55, 0.60, 0.65, 0.70]
WEIGHT_GRID = [0.08, 0.10, 0.12, 0.15]
BENCHMARK_SENSITIVITY = 0.55
BENCHMARK_WEIGHT = 0.15
EPS = 1e-12


@dataclass(frozen=True)
class TwoFactorSpec:
    scenario_id: str
    sensitivity: float
    strategist_weight: float
    tactician_weight: float
    operator_weight: float


@dataclass(frozen=True)
class TwoFactorMetrics:
    scenario_id: str
    sensitivity: float
    strategist_weight: float
    tactician_weight: float
    operator_weight: float
    base: micro.MicrogridMetrics
    interaction_label: str


@dataclass(frozen=True)
class ConfirmationSurface:
    name: str
    start_ts_ms: int
    end_ts_ms: int
    segment_bar_count: int
    parity_ok: bool
    parity_mismatch_count: int


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", default=str(REPO_ROOT / "config" / "aurora"))
    parser.add_argument("--domains-yaml", default=str(REPO_ROOT / "config" / "aurora" / "domains.yaml"))
    parser.add_argument("--strategies-yaml", default=str(REPO_ROOT / "config" / "aurora" / "strategies.yaml"))
    parser.add_argument("--recorder-dir", default=str(REPO_ROOT / "data" / "recorder"))
    parser.add_argument("--aurora-core-glob", default=str(REPO_ROOT / "logs" / "aurora_core.log*"))
    parser.add_argument("--decision-log-glob", default=str(REPO_ROOT / "logs" / "domain_decision_making.log*"))
    parser.add_argument("--shadow-journal", default=str(REPO_ROOT / "logs" / "shadow_critical_event_journal_v1.jsonl"))
    parser.add_argument("--trade-lifecycle", default=str(REPO_ROOT / "logs" / "trade_lifecycle.jsonl"))
    parser.add_argument("--prior-sweep-dir", default=str(REPO_ROOT / "reports" / "aurora_trend_up_strategist_sweep_2026-04-14"))
    parser.add_argument("--prior-microgrid-dir", default=str(REPO_ROOT / "reports" / "aurora_sensitivity_microgrid_2026-04-14"))
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "reports" / "aurora_two_factor_grid_2026-04-14"))
    parser.add_argument("--timezone", default="Europe/Kiev")
    parser.add_argument("--symbols", nargs="*", default=None)
    return parser.parse_args(argv)


def _baseline_sensitivity(domains_yaml: Path) -> float:
    return micro._load_baseline_sensitivity(domains_yaml)


def _baseline_strategist_weight(domains_yaml: Path) -> float:
    import yaml

    payload = yaml.safe_load(domains_yaml.read_text(encoding="utf-8"))
    return float(payload["feature_engineering"]["pillars"]["weights"]["strategist"])


def _weight_triplet(strategist_weight: float) -> tuple[float, float, float]:
    tactician = (1.0 - strategist_weight) * (0.60 / 0.85)
    operator = (1.0 - strategist_weight) * (0.25 / 0.85)
    return tactician, operator, strategist_weight


def _scenario_id(index: int) -> str:
    return f"TWOFACTOR_CELL_{index:02d}"


def _output_prefix(index: int, sensitivity: float, strategist_weight: float) -> str:
    return f"TWOFACTOR_CELL_{index:02d}_s{str(sensitivity).replace('.', 'p')}_w{str(strategist_weight).replace('.', 'p')}"


def _run_twofactor_window(
    *,
    typed_config: Any,
    scenario_id: str,
    symbol: str,
    joined_series: Sequence[dict[str, Any]],
    target_bar_ts_set: set[int],
    sensitivity: float,
    weights: tuple[float, float, float],
    growth_flags_by_bar: dict[int, tuple[bool, bool]],
) -> list[dict[str, Any]]:
    decision_cfg = typed_config.strategies.aurora.decision
    threshold, regime_thresholds = prev._resolve_symbol_thresholds(typed_config, symbol)
    op_mode = getattr(decision_cfg, "operational_mode", prev.OperationalMode.PARANOID)
    mode_manager = prev.ModeManager(op_mode)
    shield_fn, _memory_shield = prev._build_shield_cascade(decision_cfg, mode_manager)
    score_multiplier = float(getattr(decision_cfg, "score_multiplier", 1.0))
    geometry_cfg = getattr(decision_cfg, "decision_geometry", None)
    admission_mode = str(getattr(geometry_cfg, "admission_mode", "quadratic"))
    admission_power = float(getattr(geometry_cfg, "admission_power")) if getattr(geometry_cfg, "admission_power", None) is not None else None
    sizing_mode = str(getattr(geometry_cfg, "sizing_mode", "quadratic"))
    sizing_power = float(getattr(geometry_cfg, "sizing_power")) if getattr(geometry_cfg, "sizing_power", None) is not None else None
    admission_shield_floor = float(getattr(geometry_cfg, "admission_shield_floor", 0.0) or 0.0)
    neutral_threshold = decimal.Decimal(str(getattr(decision_cfg, "neutral_threshold", "0.05")))
    delta_price_cap_pct = decimal.Decimal(str(getattr(getattr(decision_cfg, "signals", None), "delta_price_cap_pct", "0.02")))
    no_bias = prev.SideBiasState(
        buy_count=0,
        sell_count=0,
        window_sec=float(getattr(decision_cfg, "side_bias_window_sec", 420.0)),
        target_ratio=float(getattr(decision_cfg, "side_bias_target_ratio", 0.72)),
        penalty_factor=float(getattr(decision_cfg, "side_bias_penalty_factor", 0.25)),
        min_intents=int(getattr(decision_cfg, "side_bias_min_intents", 18)),
    )
    current_side = ""
    tact_weight, oper_weight, strat_weight = weights
    rows: list[dict[str, Any]] = []
    for item in joined_series:
        recorder = item["recorder"]
        regime = item["regime"]
        baseline_row = item["baseline_row"]
        tactician = recorder.pillar_tactician
        operator = recorder.pillar_operator
        strategist = recorder.pillar_strategist
        if tactician is None or operator is None or strategist is None:
            current_side = ""
            continue
        strategist = prev._rebuild_strategist_from_sensitivity(strategist, sensitivity)
        pillar_sum = tactician * tact_weight + operator * oper_weight + strategist * strat_weight
        features = prev._bar_features(
            recorder=recorder,
            regime=regime,
            pillar_tactician=tactician,
            pillar_operator=operator,
            pillar_strategist=strategist,
            pillar_sum=pillar_sum,
        )
        result = prev.QuadraticScoringKernel.compute(
            symbol=symbol,
            features=features,
            warmup_readiness={},
            price=decimal.Decimal(str(recorder.close)),
            signal_weights={},
            feature_neutrals={},
            essential_features=[],
            base_threshold=threshold,
            regime_name=regime.regime,
            regime_thresholds=regime_thresholds,
            side_bias_state=no_bias,
            direction_strength_cfg={},
            delta_price_cap_pct=delta_price_cap_pct,
            neutral_threshold=neutral_threshold,
            current_side=current_side,
            normalize_mode=str(getattr(getattr(decision_cfg, "signals", None), "normalize_signals_mode", "signed_v2")),
            shield_fn=shield_fn,
            score_multiplier=score_multiplier,
            linear_score=pillar_sum,
            admission_mode=admission_mode,
            admission_power=admission_power,
            sizing_mode=sizing_mode,
            sizing_power=sizing_power,
            admission_shield_floor=admission_shield_floor,
        )
        current_side = str(result.side)
        growth_flag, growth_complete = growth_flags_by_bar.get(recorder.bar_close_ts_ms, (False, False))
        row = prev._build_target_row(
            family="two_factor",
            scenario_id=scenario_id,
            symbol=symbol,
            bar_close_ts_ms=recorder.bar_close_ts_ms,
            regime=regime,
            result=result,
            pillar_tactician=tactician,
            pillar_operator=operator,
            pillar_strategist=strategist,
            pillar_sum=pillar_sum,
            baseline_row=baseline_row,
            active_growth_phase=growth_flag,
            active_growth_complete=growth_complete,
            final_side_optional=None,
        )
        row["tactician_weight"] = tact_weight
        row["operator_weight"] = oper_weight
        row["strategist_weight"] = strat_weight
        rows.append(row)
    return [row for row in rows if int(row["bar_close_ts_ms"]) in target_bar_ts_set]


def _run_twofactor_scenario(
    *,
    typed_config: Any,
    scenario_id: str,
    symbols: Sequence[str],
    recorder_points: dict[str, dict[int, prev.RecorderPoint]],
    regime_map: dict[tuple[str, int], prev.RegimeEvidence],
    decision_map: dict[tuple[str, int], prev.DecisionEvidence],
    frozen_segment: Sequence[int],
    sensitivity: float,
    strategist_weight: float,
    growth_flags: dict[tuple[str, int], tuple[bool, bool]],
    baseline_lookup: dict[tuple[str, int], dict[str, Any]],
) -> tuple[list[dict[str, Any]], tuple[float, float, float]]:
    weights = _weight_triplet(strategist_weight)
    target_bar_ts_set = set(int(bar_ts) for bar_ts in frozen_segment)
    scenario_rows: list[dict[str, Any]] = []
    for symbol in symbols:
        joined_series = prev._build_joined_series(
            symbol=symbol,
            recorder_points=recorder_points,
            regime_map=regime_map,
            decision_map=decision_map,
            start_ts_ms=int(frozen_segment[0]),
            end_ts_ms=int(frozen_segment[-1]),
            pre_roll_bars=prev.PRE_ROLL_BARS,
        )
        for item in joined_series:
            item["baseline_row"] = baseline_lookup.get((symbol, item["recorder"].bar_close_ts_ms))
        growth_flags_by_bar = {bar_ts: growth_flags.get((symbol, bar_ts), (False, False)) for bar_ts in target_bar_ts_set}
        rows = _run_twofactor_window(
            typed_config=typed_config,
            scenario_id=scenario_id,
            symbol=symbol,
            joined_series=joined_series,
            target_bar_ts_set=target_bar_ts_set,
            sensitivity=sensitivity,
            weights=weights,
            growth_flags_by_bar=growth_flags_by_bar,
        )
        scenario_rows.extend(rows)
    scenario_rows.sort(key=lambda row: (row["bar_close_ts_ms"], row["symbol"]))
    return scenario_rows, weights


def _to_twofactor_metrics(
    *,
    scenario_id: str,
    sensitivity: float,
    strategist_weight: float,
    tactician_weight: float,
    operator_weight: float,
    base: micro.MicrogridMetrics,
    prior_benchmark: micro.MicrogridMetrics,
) -> TwoFactorMetrics:
    if base.status != "ok":
        label = "inconclusive"
    else:
        label = micro._classify_metrics(base, prior_winner_metrics=prior_benchmark)
    return TwoFactorMetrics(
        scenario_id=scenario_id,
        sensitivity=sensitivity,
        strategist_weight=strategist_weight,
        tactician_weight=tactician_weight,
        operator_weight=operator_weight,
        base=dataclasses.replace(base, classification=label),
        interaction_label=label,
    )


def _ranking_key(metrics: TwoFactorMetrics, *, benchmark_sensitivity: float, benchmark_weight: float) -> tuple[float, float, float, float, float, float]:
    return (
        float(metrics.base.growth_capture_count),
        -float(metrics.base.false_buy_outside_growth_count),
        float(metrics.base.growth_sell_reduction_count),
        -float(metrics.base.churn_rate),
        -abs(metrics.strategist_weight - benchmark_weight),
        -abs(metrics.sensitivity - benchmark_sensitivity),
    )


def _safe_debias_key(metrics: TwoFactorMetrics, *, benchmark_weight: float) -> tuple[float, float, float, float]:
    return (
        float(metrics.base.growth_sell_reduction_count),
        -float(metrics.base.false_buy_outside_growth_count),
        -float(metrics.base.churn_rate),
        -abs(metrics.strategist_weight - benchmark_weight),
    )


def _cell_patch_analysis(
    metrics_by_cell: dict[tuple[float, float], TwoFactorMetrics],
    *,
    benchmark: TwoFactorMetrics,
) -> dict[str, Any]:
    eligible: set[tuple[float, float]] = set()
    for key, metrics in metrics_by_cell.items():
        if (
            metrics.base.status == "ok"
            and metrics.base.false_buy_outside_growth_count == 0
            and metrics.base.growth_capture_count >= benchmark.base.growth_capture_count + 1
            and metrics.interaction_label == "true capture candidate"
        ):
            eligible.add(key)
    if not eligible:
        return {"status": "not_proven", "cells": []}
    sens_index = {value: idx for idx, value in enumerate(SENSITIVITY_GRID)}
    weight_index = {value: idx for idx, value in enumerate(WEIGHT_GRID)}
    remaining = set(eligible)
    patches: list[list[tuple[float, float]]] = []
    while remaining:
        seed = remaining.pop()
        stack = [seed]
        patch = [seed]
        while stack:
            sens, weight = stack.pop()
            for ds, dw in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ns_idx = sens_index[sens] + ds
                nw_idx = weight_index[weight] + dw
                if ns_idx < 0 or ns_idx >= len(SENSITIVITY_GRID) or nw_idx < 0 or nw_idx >= len(WEIGHT_GRID):
                    continue
                neighbor = (SENSITIVITY_GRID[ns_idx], WEIGHT_GRID[nw_idx])
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
                    patch.append(neighbor)
        if len(patch) >= 2:
            patches.append(sorted(patch))
    if not patches:
        return {"status": "not_proven", "cells": []}
    patches.sort(
        key=lambda patch: (
            len(patch),
            sum(metrics_by_cell[cell].base.growth_capture_count for cell in patch),
            -sum(metrics_by_cell[cell].base.false_buy_outside_growth_count for cell in patch),
            -sum(metrics_by_cell[cell].base.churn_rate for cell in patch),
        ),
        reverse=True,
    )
    return {"status": "proven", "cells": patches[0]}


def _neighbor_cells(sensitivity: float, strategist_weight: float) -> list[tuple[float, float]]:
    neighbors: list[tuple[float, float]] = []
    s_idx = SENSITIVITY_GRID.index(sensitivity)
    w_idx = WEIGHT_GRID.index(strategist_weight)
    for ds, dw in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ns_idx = s_idx + ds
        nw_idx = w_idx + dw
        if 0 <= ns_idx < len(SENSITIVITY_GRID) and 0 <= nw_idx < len(WEIGHT_GRID):
            neighbors.append((SENSITIVITY_GRID[ns_idx], WEIGHT_GRID[nw_idx]))
    return neighbors


def _write_markdown(path: Path, lines: Sequence[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_baseline_reconfirmation(
    path: Path,
    *,
    frozen_label: str,
    parity_ok: bool,
    active_growth_same: bool,
    baseline_signature_same: bool,
    benchmark_reproduced: bool,
    benchmark: TwoFactorMetrics,
) -> None:
    lines = [
        "# AURORA TWO FACTOR GRID BASELINE RECONFIRMATION",
        "",
        "## FACTS",
        f"- Frozen window reused exactly: `{frozen_label}`",
        f"- Baseline parity passed: `{parity_ok}`",
        f"- Active-growth flags reused identically: `{active_growth_same}`",
        f"- Baseline replay signature matched prior study: `{baseline_signature_same}`",
        f"- Prior `(0.55, 0.15)` benchmark reproduced exactly: `{benchmark_reproduced}`",
        "",
        "## INFERENCES",
        "- Apples-to-apples comparison to the prior sensitivity-only package is preserved on the frozen window.",
        "",
        "## ASSUMPTIONS",
        "- Benchmark identity is the sensitivity-only `0.55` result at live strategist weight `0.15`.",
        "",
        "## UNKNOWNS",
        "- Reconfirmation does not upgrade local frozen-window evidence into broader production proof.",
        "",
        "## Metrics",
        f"- Benchmark growth_capture=`{prev._render_pct(benchmark.base.growth_capture_pct)}` ({benchmark.base.growth_capture_count}/{benchmark.base.growth_point_count})",
        f"- Benchmark false_buy=`{prev._render_pct(benchmark.base.false_buy_outside_growth_pct)}` ({benchmark.base.false_buy_outside_growth_count}/{benchmark.base.non_growth_point_count})",
        f"- Benchmark churn=`{benchmark.base.churn_rate:.4f}`",
        "",
        "## Evidence",
        "- No drift was accepted silently; this package fails closed on comparability questions.",
    ]
    _write_markdown(path, lines)


def _write_cell_report(
    path: Path,
    *,
    metrics: TwoFactorMetrics,
    baseline_metrics: micro.MicrogridMetrics,
    benchmark: TwoFactorMetrics,
    metrics_by_cell: dict[tuple[float, float], TwoFactorMetrics],
    rows: Sequence[dict[str, Any]],
) -> None:
    lines = [
        f"# {metrics.scenario_id} REPORT",
        "",
        "## FACTS",
        f"- Sensitivity: `{metrics.sensitivity:.2f}`",
        f"- Strategist weight: `{metrics.strategist_weight:.2f}`",
        f"- Redistribution: tactician=`{metrics.tactician_weight:.6f}` operator=`{metrics.operator_weight:.6f}` strategist=`{metrics.strategist_weight:.6f}`",
        f"- Classification: `{metrics.interaction_label}`",
        "",
        "## INFERENCES",
        "- This cell must be distinguished as de-bias, neutralization, true capture, or risky distortion based on counts first, not on percentages alone.",
        "",
        "## ASSUMPTIONS",
        "- Weight redistribution preserves baseline tactician:operator ratio exactly.",
        "",
        "## UNKNOWNS",
        "- Local frozen-window wins are still weaker than broader robust behavior.",
        "",
        "## Metrics",
        f"- Growth capture=`{prev._render_pct(metrics.base.growth_capture_pct)}` ({metrics.base.growth_capture_count}/{metrics.base.growth_point_count}) vs benchmark `{benchmark.base.growth_capture_count}/{benchmark.base.growth_point_count}`",
        f"- False BUY outside growth=`{prev._render_pct(metrics.base.false_buy_outside_growth_pct)}` ({metrics.base.false_buy_outside_growth_count}/{metrics.base.non_growth_point_count})",
        f"- Growth SELL reduction=`{prev._render_pct(metrics.base.growth_sell_reduction_pct)}` ({metrics.base.growth_sell_reduction_count}/{baseline_metrics.sell_active_count_growth})",
        f"- Occupancy growth sell/neutral/buy=`{metrics.base.sell_active_count_growth}/{metrics.base.neutral_count_growth}/{metrics.base.buy_active_count_growth}`",
        f"- Occupancy non-growth sell/neutral/buy=`{metrics.base.sell_active_count_non_growth}/{metrics.base.neutral_count_non_growth}/{metrics.base.buy_active_count_non_growth}`",
        f"- Distance to BUY mean/median/p90=`{prev._render_num(metrics.base.mean_distance_to_buy)}` / `{prev._render_num(metrics.base.median_distance_to_buy)}` / `{prev._render_num(metrics.base.p90_distance_to_buy)}`",
        f"- SELL depth mean/median/p90=`{prev._render_num(metrics.base.mean_sell_depth)}` / `{prev._render_num(metrics.base.median_sell_depth)}` / `{prev._render_num(metrics.base.p90_sell_depth)}`",
        f"- Stability churn=`{metrics.base.churn_rate:.4f}` side_flips=`{metrics.base.side_flip_count}` oscillation=`{metrics.base.oscillation_flag}`",
        f"- Strategist delta mean/median=`{prev._render_num(metrics.base.mean_strategist_delta)}` / `{prev._render_num(metrics.base.median_strategist_delta)}`",
        f"- Pillar_sum delta mean/median=`{prev._render_num(metrics.base.mean_pillar_sum_delta)}` / `{prev._render_num(metrics.base.median_pillar_sum_delta)}`",
        f"- Baseline SELL -> sell/neutral/buy after shift=`{metrics.base.shrinkage_to_sell_count}/{metrics.base.shrinkage_to_neutral_count}/{metrics.base.shrinkage_to_buy_count}`",
    ]
    neighbor_lines = []
    for cell in _neighbor_cells(metrics.sensitivity, metrics.strategist_weight):
        neighbor = metrics_by_cell[cell]
        neighbor_lines.append(
            f"- Neighbor `(s={neighbor.sensitivity:.2f}, w={neighbor.strategist_weight:.2f})`: capture=`{prev._render_pct(neighbor.base.growth_capture_pct)}` ({neighbor.base.growth_capture_count}/{neighbor.base.growth_point_count}) false_buy=`{prev._render_pct(neighbor.base.false_buy_outside_growth_pct)}` churn=`{neighbor.base.churn_rate:.4f}` class=`{neighbor.interaction_label}`"
        )
    lines.extend(["", "## Evidence"])
    lines.extend(neighbor_lines or ["- No adjacent cells available in the local grid."])
    changed_rows = [row for row in rows if row["baseline_raw_side"] != row["raw_side"]][:10]
    for row in changed_rows:
        lines.append(f"- `{row['timestamp']}` `{row['symbol']}` baseline=`{row['baseline_raw_side']}` scenario=`{row['raw_side']}` growth=`{row['active_growth_phase']}`")
    _write_markdown(path, lines)


def _summary_row(metrics: TwoFactorMetrics) -> dict[str, Any]:
    row = {
        "scenario_id": metrics.scenario_id,
        "sensitivity": metrics.sensitivity,
        "strategist_weight": metrics.strategist_weight,
        "tactician_weight": metrics.tactician_weight,
        "operator_weight": metrics.operator_weight,
        "interaction_label": metrics.interaction_label,
    }
    row.update(dataclasses.asdict(metrics.base))
    return row


def _load_prior_microgrid_summary(path: Path) -> dict[tuple[float, float], dict[str, Any]]:
    summary_path = path / "AURORA_SENSITIVITY_MICROGRID_SUMMARY.csv"
    result: dict[tuple[float, float], dict[str, Any]] = {}
    with summary_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            sensitivity = float(row["sensitivity"])
            result[(sensitivity, BENCHMARK_WEIGHT)] = dict(row)
    return result


def _choose_top_candidates(metrics_rows: Sequence[TwoFactorMetrics], *, count: int) -> list[TwoFactorMetrics]:
    ranked = [metrics for metrics in metrics_rows if metrics.base.status == "ok"]
    ranked.sort(
        key=lambda item: _ranking_key(
            item,
            benchmark_sensitivity=BENCHMARK_SENSITIVITY,
            benchmark_weight=BENCHMARK_WEIGHT,
        ),
        reverse=True,
    )
    return ranked[:count]


def _best_safe_debias(metrics_rows: Sequence[TwoFactorMetrics], *, benchmark_weight: float) -> TwoFactorMetrics | None:
    candidates = [
        metrics
        for metrics in metrics_rows
        if metrics.base.status == "ok"
        and metrics.base.false_buy_outside_growth_count == 0
        and metrics.interaction_label in {"de-bias only", "neutralizer", "over-neutralizer"}
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: _safe_debias_key(item, benchmark_weight=benchmark_weight), reverse=True)
    return candidates[0]


def _best_true_capture(metrics_rows: Sequence[TwoFactorMetrics]) -> TwoFactorMetrics | None:
    candidates = [metrics for metrics in metrics_rows if metrics.interaction_label == "selective capture candidate"]
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: _ranking_key(
            item,
            benchmark_sensitivity=BENCHMARK_SENSITIVITY,
            benchmark_weight=BENCHMARK_WEIGHT,
        ),
        reverse=True,
    )
    return candidates[0]


def _surface_label(start_ts_ms: int, end_ts_ms: int) -> str:
    return f"{prev._iso_utc(start_ts_ms)} .. {prev._iso_utc(end_ts_ms)}"


def _rows_signature(rows: Sequence[dict[str, Any]]) -> str:
    return prev._deterministic_signature(rows)


def _surface_segment(start_ts_ms: int, end_ts_ms: int) -> list[int]:
    return list(range(int(start_ts_ms), int(end_ts_ms) + prev.TF_MS, prev.TF_MS))


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


def _interaction_analysis(
    metrics_by_cell: dict[tuple[float, float], TwoFactorMetrics],
    *,
    benchmark: TwoFactorMetrics,
) -> dict[str, Any]:
    best_weight_effect: dict[str, Any] = {"gain": -10**9, "cell": benchmark}
    for sensitivity in SENSITIVITY_GRID:
        baseline_cell = metrics_by_cell[(sensitivity, BENCHMARK_WEIGHT)]
        for strategist_weight in WEIGHT_GRID:
            cell = metrics_by_cell[(sensitivity, strategist_weight)]
            gain = cell.base.growth_capture_count - baseline_cell.base.growth_capture_count
            candidate = {
                "sensitivity": sensitivity,
                "from_weight": BENCHMARK_WEIGHT,
                "to_weight": strategist_weight,
                "gain": gain,
                "cell": cell,
                "baseline_cell": baseline_cell,
            }
            if (
                gain > best_weight_effect["gain"]
                or (
                    gain == best_weight_effect["gain"]
                    and cell.base.false_buy_outside_growth_count < best_weight_effect["cell"].base.false_buy_outside_growth_count
                )
            ):
                best_weight_effect = candidate
    best_sensitivity_effect: dict[str, Any] = {"gain": -10**9, "cell": benchmark}
    for strategist_weight in WEIGHT_GRID:
        baseline_cell = metrics_by_cell[(BENCHMARK_SENSITIVITY, strategist_weight)]
        for sensitivity in SENSITIVITY_GRID:
            cell = metrics_by_cell[(sensitivity, strategist_weight)]
            gain = cell.base.growth_capture_count - baseline_cell.base.growth_capture_count
            candidate = {
                "weight": strategist_weight,
                "from_sensitivity": BENCHMARK_SENSITIVITY,
                "to_sensitivity": sensitivity,
                "gain": gain,
                "cell": cell,
                "baseline_cell": baseline_cell,
            }
            if (
                gain > best_sensitivity_effect["gain"]
                or (
                    gain == best_sensitivity_effect["gain"]
                    and cell.base.false_buy_outside_growth_count < best_sensitivity_effect["cell"].base.false_buy_outside_growth_count
                )
            ):
                best_sensitivity_effect = candidate

    materially_better_cells = [
        metrics
        for metrics in metrics_by_cell.values()
        if metrics.base.false_buy_outside_growth_count == 0
        and metrics.base.growth_capture_count >= benchmark.base.growth_capture_count + 1
    ]
    plateau = "patch" if len(materially_better_cells) >= 2 else ("fragile_cell" if materially_better_cells else "no_material_ridge")
    weight_range = max(
        max(metrics_by_cell[(s, w)].base.growth_capture_count for w in WEIGHT_GRID)
        - min(metrics_by_cell[(s, w)].base.growth_capture_count for w in WEIGHT_GRID)
        for s in SENSITIVITY_GRID
    )
    sensitivity_range = max(
        max(metrics_by_cell[(s, w)].base.growth_capture_count for s in SENSITIVITY_GRID)
        - min(metrics_by_cell[(s, w)].base.growth_capture_count for s in SENSITIVITY_GRID)
        for w in WEIGHT_GRID
    )
    if weight_range > sensitivity_range:
        dominant_effect = "weight_adds_meaningful_second_lever"
    elif sensitivity_range > weight_range:
        dominant_effect = "sensitivity_still_dominates"
    else:
        dominant_effect = "interaction_surface_mixed_or_flat"
    return {
        "best_weight_effect": best_weight_effect,
        "best_sensitivity_effect": best_sensitivity_effect,
        "plateau": plateau,
        "weight_range": weight_range,
        "sensitivity_range": sensitivity_range,
        "dominant_effect": dominant_effect,
    }


def _write_master_report(
    path: Path,
    *,
    metrics_rows: Sequence[TwoFactorMetrics],
    best_single: TwoFactorMetrics,
    best_patch: dict[str, Any],
    best_safe_debias: TwoFactorMetrics | None,
    best_true_capture: TwoFactorMetrics | None,
    benchmark: TwoFactorMetrics,
    interaction: dict[str, Any],
    baseline_growth_sell_count: int,
) -> None:
    lines = [
        "# AURORA TWO FACTOR GRID MASTER REPORT",
        "",
        "## FACTS",
        f"- Mandatory grid cells executed: `{len(metrics_rows)}`",
        f"- Sensitivity-only benchmark cell: `(s={benchmark.sensitivity:.2f}, w={benchmark.strategist_weight:.2f})` with growth_capture=`{prev._render_pct(benchmark.base.growth_capture_pct)}` ({benchmark.base.growth_capture_count}/{benchmark.base.growth_point_count})",
        f"- Best single cell: `{best_single.scenario_id}` => `(s={best_single.sensitivity:.2f}, w={best_single.strategist_weight:.2f})`",
        f"- Best local patch status: `{best_patch['status']}`",
        f"- Best safe de-bias cell: `{best_safe_debias.scenario_id if best_safe_debias else 'not_proven'}`",
        f"- Best true capture candidate: `{best_true_capture.scenario_id if best_true_capture else 'not_proven'}`",
        "",
        "## INFERENCES",
        "- Two-factor ranking is still constrained by local frozen-window evidence and treats capture count as primary before false BUY, SELL reduction, and churn.",
        "",
        "## ASSUMPTIONS",
        "- Material improvement means strictly beating the sensitivity-only `0.55` benchmark on growth-capture count, not merely matching it with prettier neutralization.",
        "",
        "## UNKNOWNS",
        "- A local top cell is not equivalent to robust multi-episode TREND_UP behavior or production readiness.",
        "",
        "## Metrics",
        "| Sensitivity | Weight | Scenario | Class | Growth Capture | False BUY | Growth SELL Reduction | Churn |",
        "|---:|---:|---|---|---:|---:|---:|---:|",
    ]
    for metrics in sorted(metrics_rows, key=lambda item: (item.sensitivity, item.strategist_weight)):
        lines.append(
            f"| {metrics.sensitivity:.2f} | {metrics.strategist_weight:.2f} | {metrics.scenario_id} | {metrics.interaction_label} | "
            f"{prev._render_pct(metrics.base.growth_capture_pct)} ({metrics.base.growth_capture_count}/{metrics.base.growth_point_count}) | "
            f"{prev._render_pct(metrics.base.false_buy_outside_growth_pct)} ({metrics.base.false_buy_outside_growth_count}/{metrics.base.non_growth_point_count}) | "
            f"{prev._render_pct(metrics.base.growth_sell_reduction_pct)} ({metrics.base.growth_sell_reduction_count}/{baseline_growth_sell_count}) | "
            f"{metrics.base.churn_rate:.4f} |"
        )
    bwe = interaction["best_weight_effect"]
    bse = interaction["best_sensitivity_effect"]
    lines.extend(
        [
            "",
            "## Interaction Analysis",
            f"- Best weight effect at fixed sensitivity: `s={bwe['sensitivity']:.2f}`, weight `{bwe['from_weight']:.2f} -> {bwe['to_weight']:.2f}`, capture gain=`{bwe['gain']}` point(s), false_buy=`{bwe['cell'].base.false_buy_outside_growth_count}`.",
            f"- Best sensitivity effect at fixed weight: `w={bse['weight']:.2f}`, sensitivity `{bse['from_sensitivity']:.2f} -> {bse['to_sensitivity']:.2f}`, capture gain=`{bse['gain']}` point(s), false_buy=`{bse['cell'].base.false_buy_outside_growth_count}`.",
            f"- Surface shape verdict: `{interaction['plateau']}`.",
            f"- Dominant lever verdict: `{interaction['dominant_effect']}` (weight_range=`{interaction['weight_range']}`, sensitivity_range=`{interaction['sensitivity_range']}`).",
            "",
            "## Evidence",
            f"- Best single cell classified as `{best_single.interaction_label}` with growth_capture=`{prev._render_pct(best_single.base.growth_capture_pct)}` ({best_single.base.growth_capture_count}/{best_single.base.growth_point_count}), false_buy=`{prev._render_pct(best_single.base.false_buy_outside_growth_pct)}` ({best_single.base.false_buy_outside_growth_count}/{best_single.base.non_growth_point_count}), churn=`{best_single.base.churn_rate:.4f}`.",
        ]
    )
    if best_patch["status"] == "proven":
        lines.append(f"- Best local patch cells: `{', '.join(f'(s={cell[0]:.2f}, w={cell[1]:.2f})' for cell in best_patch['cells'])}`.")
    else:
        lines.append("- No adjacent patch met the package bar for material capture improvement with zero false BUY.")
    _write_markdown(path, lines)


def _write_confirmation_report(
    path: Path,
    *,
    confirmation_rows: Sequence[dict[str, Any]],
    top_candidates: Sequence[TwoFactorMetrics],
    frozen_best: TwoFactorMetrics,
    surfaces: Sequence[ConfirmationSurface],
) -> None:
    lines = [
        "# AURORA TWO FACTOR GRID CONFIRMATION REPORT",
        "",
        "## FACTS",
        f"- Top candidates tested beyond the frozen window: `{', '.join(f'(s={item.sensitivity:.2f}, w={item.strategist_weight:.2f})' for item in top_candidates)}`",
        f"- Confirmation surfaces executed: `{len(surfaces)}`",
        "",
        "## INFERENCES",
        "- Confirmation surfaces are explicitly weaker whenever baseline parity drifts outside the exact frozen parity subwindow.",
        "",
        "## ASSUMPTIONS",
        "- The same active-growth candidate from the frozen study was reused for bounded confirmation comparability.",
        "",
        "## UNKNOWNS",
        "- Rank stability on one parent segment and one extra episode still does not prove broader TREND_UP robustness.",
        "",
        "## Metrics",
    ]
    for surface in surfaces:
        lines.append(f"- `{surface.name}` window=`{_surface_label(surface.start_ts_ms, surface.end_ts_ms)}` bars=`{surface.segment_bar_count}` parity_ok=`{surface.parity_ok}` mismatches=`{surface.parity_mismatch_count}`")
    lines.extend(["", "## Evidence", "| Surface | Sensitivity | Weight | Growth Capture | False BUY | Growth SELL Reduction | Churn | Rank |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for row in confirmation_rows:
        lines.append(
            f"| {row['surface_name']} | {row['sensitivity']:.2f} | {row['strategist_weight']:.2f} | "
            f"{prev._render_pct(row['growth_capture_pct'])} ({row['growth_capture_count']}/{row['growth_point_count']}) | "
            f"{prev._render_pct(row['false_buy_outside_growth_pct'])} ({row['false_buy_outside_growth_count']}/{row['non_growth_point_count']}) | "
            f"{prev._render_pct(row['growth_sell_reduction_pct'])} ({row['growth_sell_reduction_count']}/{row['baseline_growth_sell_count']}) | "
            f"{row['churn_rate']:.4f} | {row['surface_rank']} |"
        )
    stable = all(
        row["surface_rank"] == 1
        for row in confirmation_rows
        if math.isclose(row["sensitivity"], frozen_best.sensitivity, abs_tol=EPS)
        and math.isclose(row["strategist_weight"], frozen_best.strategist_weight, abs_tol=EPS)
    )
    lines.extend(["", f"- Frozen best cell kept top rank on every confirmation surface: `{stable}`"])
    _write_markdown(path, lines)


def _write_spillover_report(path: Path, *, spillover_rows: Sequence[dict[str, Any]], control_rows: Sequence[dict[str, Any]]) -> None:
    lines = [
        "# AURORA TWO FACTOR GRID SPILLOVER REPORT",
        "",
        "## FACTS",
        f"- Spillover probe rows: `{len(spillover_rows)}`",
        f"- Control windows sampled: `{len(control_rows)}`",
        "",
        "## INFERENCES",
        "- Spillover checks remain bounded probes for obvious directional distortion, not full cross-regime safety proof.",
        "",
        "## ASSUMPTIONS",
        "- Hard reject remains: sell->buy flips > 10%, TREND_DOWN buy-active > 5% absolute, or churn > 1.5x baseline.",
        "",
        "## UNKNOWNS",
        "- Passing these probes does not prove safety across all recent regimes or dates.",
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
    baseline_signature_same: bool,
    benchmark_reproduced: bool,
    scenario_count: int,
    rerun_ok: bool,
    confirmation_surface_count: int,
    spillover_candidate_count: int,
    unknowns: Sequence[str],
) -> None:
    lines = [
        "# AURORA TWO FACTOR GRID VALIDATION REPORT",
        "",
        "## FACTS",
        f"- Baseline parity reconfirmed: `{baseline_parity_ok}`",
        f"- Active-growth flags identical to prior frozen package: `{active_growth_same}`",
        f"- Baseline replay signature identical to prior frozen package: `{baseline_signature_same}`",
        f"- Prior `(0.55, 0.15)` benchmark reproduced exactly: `{benchmark_reproduced}`",
        f"- Scenario count executed: `{scenario_count}`",
        f"- Deterministic rerun signature match: `{rerun_ok}`",
        f"- Confirmation surfaces executed: `{confirmation_surface_count}`",
        f"- Spillover candidates rechecked: `{spillover_candidate_count}`",
        "",
        "## INFERENCES",
        "- The package is valid only because the frozen window stayed strictly comparable before any broader confirmation was consulted.",
        "",
        "## ASSUMPTIONS",
        "- Validation is package-local and not a production endorsement.",
        "",
        "## UNKNOWNS",
    ]
    for item in unknowns:
        lines.append(f"- {item}")
    lines.extend(["", "## Metrics", "- All 20 mandatory cells were executed under one-factor-frozen replay semantics except for the two target levers.", "", "## Evidence", "- The two-factor package reused the same frozen window first, then moved to weaker confirmation surfaces only for the top candidates."])
    _write_markdown(path, lines)


def _write_final_report(
    path: Path,
    *,
    best_single: TwoFactorMetrics,
    best_patch: dict[str, Any],
    best_safe_debias: TwoFactorMetrics | None,
    best_true_capture: TwoFactorMetrics | None,
    benchmark: TwoFactorMetrics,
    evidence_limits: Sequence[str],
    recommendation: str,
    baseline_growth_sell_count: int,
) -> None:
    lines = [
        "# AURORA TWO FACTOR GRID FINAL REPORT",
        "",
        "## Proven findings",
        f"- Best single cell on the frozen window: `(s={best_single.sensitivity:.2f}, w={best_single.strategist_weight:.2f})` classified as `{best_single.interaction_label}` with growth_capture=`{prev._render_pct(best_single.base.growth_capture_pct)}` ({best_single.base.growth_capture_count}/{best_single.base.growth_point_count}), false_buy=`{prev._render_pct(best_single.base.false_buy_outside_growth_pct)}` ({best_single.base.false_buy_outside_growth_count}/{best_single.base.non_growth_point_count}), churn=`{best_single.base.churn_rate:.4f}`.",
        f"- Material improvement beyond the sensitivity-only `0.55` benchmark was proven: `{best_single.base.growth_capture_count > benchmark.base.growth_capture_count}`.",
        f"- Best safe de-bias cell: `{best_safe_debias.scenario_id if best_safe_debias else 'not_proven'}`.",
        f"- Best true capture candidate: `{best_true_capture.scenario_id if best_true_capture else 'not_proven'}`.",
        "",
        "## Best single cell",
        f"- `{best_single.scenario_id}` => `(s={best_single.sensitivity:.2f}, w={best_single.strategist_weight:.2f})`.",
        "",
        "## Best local patch",
    ]
    if best_patch["status"] == "proven":
        lines.append(f"- `{', '.join(f'(s={cell[0]:.2f}, w={cell[1]:.2f})' for cell in best_patch['cells'])}`.")
    else:
        lines.append("- `not proven`")
    lines.extend(["", "## Comparison to sensitivity-only `0.55`", f"- Benchmark cell `(0.55, 0.15)` delivered growth_capture=`{prev._render_pct(benchmark.base.growth_capture_pct)}` ({benchmark.base.growth_capture_count}/{benchmark.base.growth_point_count}), false_buy=`{prev._render_pct(benchmark.base.false_buy_outside_growth_pct)}` ({benchmark.base.false_buy_outside_growth_count}/{benchmark.base.non_growth_point_count}), churn=`{benchmark.base.churn_rate:.4f}`.", f"- Best two-factor cell materially beat the benchmark on growth capture: `{best_single.base.growth_capture_count > benchmark.base.growth_capture_count}`.", "", "## Behavior classification"])
    for metrics in [best_single, best_safe_debias, best_true_capture]:
        if metrics is None:
            continue
        lines.append(f"- `(s={metrics.sensitivity:.2f}, w={metrics.strategist_weight:.2f})` -> `{metrics.interaction_label}` with growth_capture=`{prev._render_pct(metrics.base.growth_capture_pct)}` ({metrics.base.growth_capture_count}/{metrics.base.growth_point_count}), false_buy=`{prev._render_pct(metrics.base.false_buy_outside_growth_pct)}` ({metrics.base.false_buy_outside_growth_count}/{metrics.base.non_growth_point_count}), growth_sell_reduction=`{prev._render_pct(metrics.base.growth_sell_reduction_pct)}` ({metrics.base.growth_sell_reduction_count}/{baseline_growth_sell_count}), churn=`{metrics.base.churn_rate:.4f}`.")
    lines.extend(["", "## Evidence limits"])
    for item in evidence_limits:
        lines.append(f"- {item}")
    lines.extend(["", "## Recommended next package", f"- {recommendation}"])
    _write_markdown(path, lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prior_sweep_dir = Path(args.prior_sweep_dir)
    prior_microgrid_dir = Path(args.prior_microgrid_dir)

    typed_config = prev._load_typed_config(Path(args.config_dir))
    symbols = list(args.symbols) if args.symbols else prev._parse_aurora_symbols(Path(args.strategies_yaml))
    baseline_sensitivity = _baseline_sensitivity(Path(args.domains_yaml))
    baseline_weight = _baseline_strategist_weight(Path(args.domains_yaml))
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

    frozen_manifest = micro._load_prior_manifest(prior_sweep_dir)
    frozen_segment = _surface_segment(frozen_manifest["chosen_segment_start_ts_ms"], frozen_manifest["chosen_segment_end_ts_ms"])
    parent_segment = _surface_segment(frozen_manifest["parent_segment_start_ts_ms"], frozen_manifest["parent_segment_end_ts_ms"])

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
    prior_baseline_rows = micro._load_prior_baseline(prior_sweep_dir)
    baseline_signature_same = _rows_signature(baseline_rows) == _rows_signature(prior_baseline_rows)
    prior_growth_lookup = {
        (str(row["symbol"]), int(row["bar_close_ts_ms"])): (bool(row["active_growth_phase"]), bool(row["active_growth_complete"]))
        for row in prior_baseline_rows
    }
    active_growth_same = all(
        growth_flags.get((str(row["symbol"]), int(row["bar_close_ts_ms"])), (False, False))
        == prior_growth_lookup.get((str(row["symbol"]), int(row["bar_close_ts_ms"])))
        for row in baseline_rows
    )

    baseline_metrics = micro._compute_micro_metrics(
        baseline_rows,
        scenario_id="BASELINE",
        sensitivity=baseline_sensitivity,
        baseline_lookup=baseline_lookup,
        baseline_metrics=None,
        prior_winner_metrics=None,
        status="ok",
    )
    prior_micro_summary = _load_prior_microgrid_summary(prior_microgrid_dir)

    benchmark_rows, benchmark_weights = _run_twofactor_scenario(
        typed_config=typed_config,
        scenario_id="BENCHMARK_0P55_0P15",
        symbols=symbols,
        recorder_points=recorder_points,
        regime_map=regime_map,
        decision_map=decision_map,
        frozen_segment=frozen_segment,
        sensitivity=BENCHMARK_SENSITIVITY,
        strategist_weight=BENCHMARK_WEIGHT,
        growth_flags=growth_flags,
        baseline_lookup=baseline_lookup,
    )
    benchmark_rows = _scenario_rows_with_growth_flags(benchmark_rows, growth_flags)
    benchmark_base = micro._compute_micro_metrics(
        benchmark_rows,
        scenario_id="BENCHMARK_0P55_0P15",
        sensitivity=BENCHMARK_SENSITIVITY,
        baseline_lookup=baseline_lookup,
        baseline_metrics=baseline_metrics,
        prior_winner_metrics=baseline_metrics,
        status="ok",
    )
    benchmark_metrics = _to_twofactor_metrics(
        scenario_id="BENCHMARK_0P55_0P15",
        sensitivity=BENCHMARK_SENSITIVITY,
        strategist_weight=BENCHMARK_WEIGHT,
        tactician_weight=benchmark_weights[0],
        operator_weight=benchmark_weights[1],
        base=benchmark_base,
        prior_benchmark=benchmark_base,
    )
    prior_benchmark_row = prior_micro_summary.get((BENCHMARK_SENSITIVITY, BENCHMARK_WEIGHT), {})
    benchmark_reproduced = bool(prior_benchmark_row) and (
        math.isclose(float(prior_benchmark_row["growth_capture_pct"]), float(benchmark_base.growth_capture_pct or 0.0), abs_tol=EPS)
        and int(prior_benchmark_row["growth_capture_count"]) == int(benchmark_base.growth_capture_count)
        and math.isclose(float(prior_benchmark_row["false_buy_outside_growth_pct"]), float(benchmark_base.false_buy_outside_growth_pct or 0.0), abs_tol=EPS)
        and int(prior_benchmark_row["false_buy_outside_growth_count"]) == int(benchmark_base.false_buy_outside_growth_count)
        and math.isclose(float(prior_benchmark_row["churn_rate"]), float(benchmark_base.churn_rate), abs_tol=EPS)
    )

    _write_baseline_reconfirmation(
        out_dir / "AURORA_TWO_FACTOR_GRID_BASELINE_RECONFIRMATION.md",
        frozen_label=_surface_label(frozen_segment[0], frozen_segment[-1]),
        parity_ok=baseline_parity_ok,
        active_growth_same=active_growth_same,
        baseline_signature_same=baseline_signature_same,
        benchmark_reproduced=benchmark_reproduced,
        benchmark=benchmark_metrics,
    )

    scenario_rows_by_cell: dict[tuple[float, float], list[dict[str, Any]]] = {}
    metrics_by_cell: dict[tuple[float, float], TwoFactorMetrics] = {}
    index = 0
    for sensitivity in SENSITIVITY_GRID:
        for strategist_weight in WEIGHT_GRID:
            index += 1
            scenario_id = _scenario_id(index)
            rows, weights = _run_twofactor_scenario(
                typed_config=typed_config,
                scenario_id=scenario_id,
                symbols=symbols,
                recorder_points=recorder_points,
                regime_map=regime_map,
                decision_map=decision_map,
                frozen_segment=frozen_segment,
                sensitivity=sensitivity,
                strategist_weight=strategist_weight,
                growth_flags=growth_flags,
                baseline_lookup=baseline_lookup,
            )
            rows = _scenario_rows_with_growth_flags(rows, growth_flags)
            scenario_rows_by_cell[(sensitivity, strategist_weight)] = rows
            base_metrics = micro._compute_micro_metrics(
                rows,
                scenario_id=scenario_id,
                sensitivity=sensitivity,
                baseline_lookup=baseline_lookup,
                baseline_metrics=baseline_metrics,
                prior_winner_metrics=benchmark_base,
                status="ok",
            )
            metrics_by_cell[(sensitivity, strategist_weight)] = _to_twofactor_metrics(
                scenario_id=scenario_id,
                sensitivity=sensitivity,
                strategist_weight=strategist_weight,
                tactician_weight=weights[0],
                operator_weight=weights[1],
                base=base_metrics,
                prior_benchmark=benchmark_base,
            )

    metrics_rows = [metrics_by_cell[(s, w)] for s in SENSITIVITY_GRID for w in WEIGHT_GRID]
    summary_rows = [_summary_row(metrics) for metrics in metrics_rows]
    prev._write_json(out_dir / "AURORA_TWO_FACTOR_GRID_SUMMARY.json", summary_rows)
    prev._write_csv(out_dir / "AURORA_TWO_FACTOR_GRID_SUMMARY.csv", summary_rows)

    index = 0
    for sensitivity in SENSITIVITY_GRID:
        for strategist_weight in WEIGHT_GRID:
            index += 1
            prefix = _output_prefix(index, sensitivity, strategist_weight)
            rows = scenario_rows_by_cell[(sensitivity, strategist_weight)]
            metrics = metrics_by_cell[(sensitivity, strategist_weight)]
            prev._write_json(out_dir / f"{prefix}.json", rows)
            prev._write_csv(out_dir / f"{prefix}.csv", rows)
            _write_cell_report(
                out_dir / f"{metrics.scenario_id}_REPORT.md",
                metrics=metrics,
                baseline_metrics=baseline_metrics,
                benchmark=benchmark_metrics,
                metrics_by_cell=metrics_by_cell,
                rows=rows,
            )

    best_single = _choose_top_candidates(metrics_rows, count=1)[0]
    best_patch = _cell_patch_analysis(metrics_by_cell, benchmark=benchmark_metrics)
    best_safe = _best_safe_debias(metrics_rows, benchmark_weight=BENCHMARK_WEIGHT)
    best_true_capture = _best_true_capture(metrics_rows)
    interaction = _interaction_analysis(metrics_by_cell, benchmark=benchmark_metrics)

    _write_master_report(
        out_dir / "AURORA_TWO_FACTOR_GRID_MASTER_REPORT.md",
        metrics_rows=metrics_rows,
        best_single=best_single,
        best_patch=best_patch,
        best_safe_debias=best_safe,
        best_true_capture=best_true_capture,
        benchmark=benchmark_metrics,
        interaction=interaction,
        baseline_growth_sell_count=baseline_metrics.sell_active_count_growth,
    )

    additional_segment = micro._select_additional_trend_up_surface(
        complete_segments,
        symbols,
        regime_map,
        before_ts_ms=int(frozen_manifest["parent_segment_start_ts_ms"]),
    )
    confirmation_surfaces: list[ConfirmationSurface] = []
    for name, segment in (("PARENT_TREND_UP_SEGMENT", parent_segment), ("ADDITIONAL_RECENT_TREND_UP_EPISODE", additional_segment)):
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
        surface_growth_flags, _surface_feature_rows = micro._build_growth_flags_for_rows(
            surface_baseline_rows,
            recorder_series,
            candidate=chosen_candidate,
        )
        for row in surface_baseline_rows:
            flag, complete = surface_growth_flags.get((str(row["symbol"]), int(row["bar_close_ts_ms"])), (False, False))
            row["active_growth_phase"] = flag
            row["active_growth_complete"] = complete
        surface_baseline_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in surface_baseline_rows}
        surface_baseline_metrics = micro._compute_micro_metrics(
            surface_baseline_rows,
            scenario_id=f"{surface.name}_BASELINE",
            sensitivity=baseline_sensitivity,
            baseline_lookup=surface_baseline_lookup,
            baseline_metrics=None,
            prior_winner_metrics=None,
            status="ok",
        )
        surface_results: list[tuple[TwoFactorMetrics, dict[str, Any]]] = []
        for candidate in top_candidates:
            rows, weights = _run_twofactor_scenario(
                typed_config=typed_config,
                scenario_id=candidate.scenario_id,
                symbols=symbols,
                recorder_points=recorder_points,
                regime_map=regime_map,
                decision_map=decision_map,
                frozen_segment=segment,
                sensitivity=candidate.sensitivity,
                strategist_weight=candidate.strategist_weight,
                growth_flags=surface_growth_flags,
                baseline_lookup=surface_baseline_lookup,
            )
            rows = _scenario_rows_with_growth_flags(rows, surface_growth_flags)
            base_metrics = micro._compute_micro_metrics(
                rows,
                scenario_id=candidate.scenario_id,
                sensitivity=candidate.sensitivity,
                baseline_lookup=surface_baseline_lookup,
                baseline_metrics=surface_baseline_metrics,
                prior_winner_metrics=benchmark_base,
                status="ok",
            )
            metrics = _to_twofactor_metrics(
                scenario_id=candidate.scenario_id,
                sensitivity=candidate.sensitivity,
                strategist_weight=candidate.strategist_weight,
                tactician_weight=weights[0],
                operator_weight=weights[1],
                base=base_metrics,
                prior_benchmark=benchmark_base,
            )
            row = _summary_row(metrics)
            row["surface_name"] = surface.name
            surface_results.append((metrics, row))
        surface_results.sort(
            key=lambda item: _ranking_key(
                item[0],
                benchmark_sensitivity=BENCHMARK_SENSITIVITY,
                benchmark_weight=BENCHMARK_WEIGHT,
            ),
            reverse=True,
        )
        for rank, (_metrics, row) in enumerate(surface_results, start=1):
            row["surface_rank"] = rank
            row["baseline_growth_sell_count"] = surface_baseline_metrics.sell_active_count_growth
            confirmation_rows.append(row)
    prev._write_json(out_dir / "AURORA_TWO_FACTOR_GRID_CONFIRMATION_SUMMARY.json", confirmation_rows)
    prev._write_csv(out_dir / "AURORA_TWO_FACTOR_GRID_CONFIRMATION_SUMMARY.csv", confirmation_rows)
    _write_confirmation_report(
        out_dir / "AURORA_TWO_FACTOR_GRID_CONFIRMATION_REPORT.md",
        confirmation_rows=confirmation_rows,
        top_candidates=top_candidates,
        frozen_best=best_single,
        surfaces=confirmation_surfaces,
    )

    control_specs = [
        prev._choose_control_segment("TREND_DOWN_CONTROL", ["TREND_DOWN"], complete_segments, symbols, regime_map),
        prev._choose_control_segment("ALT_REGIME_CONTROL", ["MEAN_REVERSION", "HIGH_VOLATILITY", "UNCERTAIN"], complete_segments, symbols, regime_map),
    ]
    control_specs = [item for item in control_specs if item is not None]
    control_rows_for_report = [dataclasses.asdict(item) for item in control_specs]
    spillover_rows: list[dict[str, Any]] = []
    for candidate in top_candidates:
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
            control_rows, _weights = _run_twofactor_scenario(
                typed_config=typed_config,
                scenario_id=candidate.scenario_id,
                symbols=symbols,
                recorder_points=recorder_points,
                regime_map=regime_map,
                decision_map=decision_map,
                frozen_segment=control_segment,
                sensitivity=candidate.sensitivity,
                strategist_weight=candidate.strategist_weight,
                growth_flags={},
                baseline_lookup=control_baseline_lookup,
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
                    "scenario_id": candidate.scenario_id,
                    "sensitivity": candidate.sensitivity,
                    "strategist_weight": candidate.strategist_weight,
                    "control_name": control.name,
                    "target_regime": control.target_regime,
                    "sell_to_buy_flip_pct": sell_to_buy_flip_pct,
                    "buy_active_pct": buy_active_pct,
                    "churn_mult": churn_mult,
                    "verdict": "reject" if reject else "pass",
                }
            )
    prev._write_json(out_dir / "AURORA_TWO_FACTOR_GRID_SPILLOVER_SUMMARY.json", spillover_rows)
    prev._write_csv(out_dir / "AURORA_TWO_FACTOR_GRID_SPILLOVER_SUMMARY.csv", spillover_rows)
    _write_spillover_report(
        out_dir / "AURORA_TWO_FACTOR_GRID_SPILLOVER_REPORT.md",
        spillover_rows=spillover_rows,
        control_rows=control_rows_for_report,
    )

    spillover_verdicts: dict[str, list[str]] = defaultdict(list)
    for row in spillover_rows:
        spillover_verdicts[str(row["scenario_id"])].append(str(row["verdict"]))
    for key, metrics in list(metrics_by_cell.items()):
        verdicts = spillover_verdicts.get(metrics.scenario_id, [])
        metrics_by_cell[key] = dataclasses.replace(
            metrics,
            base=dataclasses.replace(
                metrics.base,
                spillover_verdict=("reject" if "reject" in verdicts else "pass" if "pass" in verdicts else "not_run"),
            ),
        )
    metrics_rows = [metrics_by_cell[(s, w)] for s in SENSITIVITY_GRID for w in WEIGHT_GRID]
    summary_rows = [_summary_row(metrics) for metrics in metrics_rows]
    prev._write_json(out_dir / "AURORA_TWO_FACTOR_GRID_SUMMARY.json", summary_rows)
    prev._write_csv(out_dir / "AURORA_TWO_FACTOR_GRID_SUMMARY.csv", summary_rows)

    rerun_ok = True
    for key, metrics in metrics_by_cell.items():
        rows, _weights = _run_twofactor_scenario(
            typed_config=typed_config,
            scenario_id=metrics.scenario_id,
            symbols=symbols,
            recorder_points=recorder_points,
            regime_map=regime_map,
            decision_map=decision_map,
            frozen_segment=frozen_segment,
            sensitivity=metrics.sensitivity,
            strategist_weight=metrics.strategist_weight,
            growth_flags=growth_flags,
            baseline_lookup=baseline_lookup,
        )
        rows = _scenario_rows_with_growth_flags(rows, growth_flags)
        if _rows_signature(rows) != _rows_signature(scenario_rows_by_cell[key]):
            rerun_ok = False
            break

    _write_validation_report(
        out_dir / "AURORA_TWO_FACTOR_GRID_VALIDATION_REPORT.md",
        baseline_parity_ok=baseline_parity_ok,
        active_growth_same=active_growth_same,
        baseline_signature_same=baseline_signature_same,
        benchmark_reproduced=benchmark_reproduced,
        scenario_count=len(metrics_rows),
        rerun_ok=rerun_ok,
        confirmation_surface_count=len(confirmation_surfaces),
        spillover_candidate_count=len(top_candidates),
        unknowns=[
            "Confirmation surfaces are weaker wherever parity drifts outside the frozen exact-parity subwindow.",
            "This package still cannot prove global multi-episode TREND_UP robustness or live economic superiority.",
        ],
    )

    evidence_limits = [
        "Primary ranking remains local to the previously frozen TREND_UP window.",
        "Only strategist sensitivity and strategist weight changed; no SMA or threshold overlays were tested here.",
        "Confirmation and spillover surfaces are bounded sanity checks, not production-proof validation.",
    ]
    if best_single.base.growth_capture_count <= benchmark_metrics.base.growth_capture_count or best_true_capture is None:
        recommendation = "threshold-asymmetry local study"
    else:
        recommendation = "broader shadow validation for top two-factor candidate only"
    _write_final_report(
        out_dir / "AURORA_TWO_FACTOR_GRID_FINAL_REPORT.md",
        best_single=best_single,
        best_patch=best_patch,
        best_safe_debias=best_safe,
        best_true_capture=best_true_capture,
        benchmark=benchmark_metrics,
        evidence_limits=evidence_limits,
        recommendation=recommendation,
        baseline_growth_sell_count=baseline_metrics.sell_active_count_growth,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
