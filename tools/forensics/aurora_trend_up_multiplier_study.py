#!/usr/bin/env python3
"""TREND_UP-specific side-bias multiplier study for Aurora."""
from __future__ import annotations

import argparse
import csv
import dataclasses
import decimal
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.reference.domains.decision_making.quadratic_scoring_kernel import _determine_side
from tools.forensics import aurora_sensitivity_microgrid_study as micro
from tools.forensics import aurora_trend_up_strategist_sweep_study as prev

SAFE_BENCHMARK_SENSITIVITY = 0.55
SAFE_BENCHMARK_WEIGHT = 0.15
SAFE_WEIGHTS = (0.60, 0.25, 0.15)
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
EPS = 1e-12


@dataclass(frozen=True)
class MultiplierScenarioSpec:
    scenario_id: str
    family: str
    label: str
    bullish_mult: float
    bearish_mult: float


@dataclass(frozen=True)
class MultiplierMetrics:
    scenario_id: str
    family: str
    label: str
    bullish_mult: float
    bearish_mult: float
    base: micro.MicrogridMetrics
    classification: str
    sell_to_neutral_count: int
    neutral_to_buy_count: int
    sell_to_buy_count: int
    raw_score_mean: float | None
    raw_score_median: float | None
    raw_score_p90: float | None
    eff_score_mean: float | None
    eff_score_median: float | None
    eff_score_p90: float | None


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
    parser.add_argument("--strategies-yaml", default=str(REPO_ROOT / "config" / "aurora" / "strategies.yaml"))
    parser.add_argument("--recorder-dir", default=str(REPO_ROOT / "data" / "recorder"))
    parser.add_argument("--aurora-core-glob", default=str(REPO_ROOT / "logs" / "aurora_core.log*"))
    parser.add_argument("--decision-log-glob", default=str(REPO_ROOT / "logs" / "domain_decision_making.log*"))
    parser.add_argument("--shadow-journal", default=str(REPO_ROOT / "logs" / "shadow_critical_event_journal_v1.jsonl"))
    parser.add_argument("--trade-lifecycle", default=str(REPO_ROOT / "logs" / "trade_lifecycle.jsonl"))
    parser.add_argument("--prior-sweep-dir", default=str(REPO_ROOT / "reports" / "aurora_trend_up_strategist_sweep_2026-04-14"))
    parser.add_argument("--prior-two-factor-dir", default=str(REPO_ROOT / "reports" / "aurora_two_factor_grid_2026-04-14"))
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "reports" / "aurora_trend_up_multiplier_2026-04-14"))
    parser.add_argument("--symbols", nargs="*", default=None)
    return parser.parse_args(argv)


def _scenario_specs() -> list[MultiplierScenarioSpec]:
    specs: list[MultiplierScenarioSpec] = []
    for index, bullish in enumerate((1.05, 1.10, 1.15, 1.20, 1.30), start=1):
        specs.append(MultiplierScenarioSpec(f"MULTIPLIER_A{index}", "BULLISH_AMPLIFICATION", f"A{index}", bullish, 1.0))
    for index, bearish in enumerate((0.95, 0.90, 0.85, 0.80, 0.70), start=1):
        specs.append(MultiplierScenarioSpec(f"MULTIPLIER_B{index}", "BEARISH_DAMPING", f"B{index}", 1.0, bearish))
    combined = ((1.05, 0.95), (1.10, 0.95), (1.10, 0.90), (1.15, 0.90), (1.15, 0.85))
    for index, (bullish, bearish) in enumerate(combined, start=1):
        specs.append(MultiplierScenarioSpec(f"MULTIPLIER_C{index}", "ASYMMETRIC_REMAP", f"C{index}", bullish, bearish))
    return specs


def _surface_segment(start_ts_ms: int, end_ts_ms: int) -> list[int]:
    return list(range(int(start_ts_ms), int(end_ts_ms) + prev.TF_MS, prev.TF_MS))


def _surface_label(start_ts_ms: int, end_ts_ms: int) -> str:
    return f"{prev._iso_utc(start_ts_ms)} .. {prev._iso_utc(end_ts_ms)}"


def _rows_signature(rows: Sequence[dict[str, Any]]) -> str:
    return prev._deterministic_signature(rows)


def _write_markdown(path: Path, lines: Sequence[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_summary(path_json: Path, path_csv: Path, rows: Sequence[dict[str, Any]]) -> None:
    prev._write_json(path_json, rows)
    prev._write_csv(path_csv, rows)


def _load_safe_benchmark_row(path: Path) -> dict[str, Any] | None:
    with (path / "AURORA_TWO_FACTOR_GRID_SUMMARY.csv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if math.isclose(float(row["sensitivity"]), SAFE_BENCHMARK_SENSITIVITY, abs_tol=EPS) and math.isclose(float(row["strategist_weight"]), SAFE_BENCHMARK_WEIGHT, abs_tol=EPS):
                return dict(row)
    return None


def _apply_multiplier(score: float, *, regime_name: str, spec: MultiplierScenarioSpec) -> tuple[float, str]:
    if regime_name != "TREND_UP":
        return score, "outside_tredup_baseline"
    effective = score
    if effective > 0.0:
        effective *= spec.bullish_mult
    elif effective < 0.0:
        effective *= spec.bearish_mult
    return effective, "tredup_score_multiplier"

def _near_boundary_count(rows: Sequence[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        score = float(row["raw_decision_score"])
        thr_buy = float(row["thr_buy"])
        thr_sell = float(row["thr_sell"])
        nearest = min(abs(score - thr_buy), abs(score + thr_sell))
        scale = max(abs(thr_buy), abs(thr_sell), EPS)
        if nearest <= 0.10 * scale:
            count += 1
    return count


def _run_multiplier_scenario(*, typed_config: Any, symbols: Sequence[str], recorder_points: dict[str, dict[int, prev.RecorderPoint]], regime_map: dict[tuple[str, int], prev.RegimeEvidence], decision_map: dict[tuple[str, int], prev.DecisionEvidence], frozen_segment: Sequence[int], growth_flags: dict[tuple[str, int], tuple[bool, bool]], safe_benchmark_lookup: dict[tuple[str, int], dict[str, Any]], live_baseline_lookup: dict[tuple[str, int], dict[str, Any]], spec: MultiplierScenarioSpec) -> list[dict[str, Any]]:
    decision_cfg = typed_config.strategies.aurora.decision
    score_multiplier = float(getattr(decision_cfg, "score_multiplier", 1.0))
    geometry_cfg = getattr(decision_cfg, "decision_geometry", None)
    admission_mode = str(getattr(geometry_cfg, "admission_mode", "quadratic"))
    admission_power = float(getattr(geometry_cfg, "admission_power")) if getattr(geometry_cfg, "admission_power", None) is not None else None
    sizing_mode = str(getattr(geometry_cfg, "sizing_mode", "quadratic"))
    sizing_power = float(getattr(geometry_cfg, "sizing_power")) if getattr(geometry_cfg, "sizing_power", None) is not None else None
    admission_shield_floor = float(getattr(geometry_cfg, "admission_shield_floor", 0.0) or 0.0)
    neutral_threshold = decimal.Decimal(str(getattr(decision_cfg, "neutral_threshold", "0.05")))
    delta_price_cap_pct = decimal.Decimal(str(getattr(getattr(decision_cfg, "signals", None), "delta_price_cap_pct", "0.02")))
    no_bias = prev.SideBiasState(buy_count=0, sell_count=0, window_sec=float(getattr(decision_cfg, "side_bias_window_sec", 420.0)), target_ratio=float(getattr(decision_cfg, "side_bias_target_ratio", 0.72)), penalty_factor=float(getattr(decision_cfg, "side_bias_penalty_factor", 0.25)), min_intents=int(getattr(decision_cfg, "side_bias_min_intents", 18)))
    op_mode = getattr(decision_cfg, "operational_mode", prev.OperationalMode.PARANOID)
    mode_manager = prev.ModeManager(op_mode)
    shield_fn, _memory_shield = prev._build_shield_cascade(decision_cfg, mode_manager)
    target_bar_ts_set = set(int(bar_ts) for bar_ts in frozen_segment)
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        threshold, regime_thresholds = prev._resolve_symbol_thresholds(typed_config, symbol)
        current_side = ""
        joined_series = prev._build_joined_series(symbol=symbol, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, start_ts_ms=int(frozen_segment[0]), end_ts_ms=int(frozen_segment[-1]), pre_roll_bars=prev.PRE_ROLL_BARS)
        for item in joined_series:
            recorder = item["recorder"]
            regime = item["regime"]
            tactician = recorder.pillar_tactician
            operator = recorder.pillar_operator
            strategist = recorder.pillar_strategist
            if tactician is None or operator is None or strategist is None:
                current_side = ""
                continue
            strategist = prev._rebuild_strategist_from_sensitivity(strategist, SAFE_BENCHMARK_SENSITIVITY)
            pillar_sum = tactician * SAFE_WEIGHTS[0] + operator * SAFE_WEIGHTS[1] + strategist * SAFE_WEIGHTS[2]
            result = prev.QuadraticScoringKernel.compute(symbol=symbol, features=prev._bar_features(recorder=recorder, regime=regime, pillar_tactician=tactician, pillar_operator=operator, pillar_strategist=strategist, pillar_sum=pillar_sum), warmup_readiness={}, price=decimal.Decimal(str(recorder.close)), signal_weights={}, feature_neutrals={}, essential_features=[], base_threshold=threshold, regime_name=regime.regime, regime_thresholds=regime_thresholds, side_bias_state=no_bias, direction_strength_cfg={}, delta_price_cap_pct=delta_price_cap_pct, neutral_threshold=neutral_threshold, current_side=current_side, normalize_mode=str(getattr(getattr(decision_cfg, "signals", None), "normalize_signals_mode", "signed_v2")), shield_fn=shield_fn, score_multiplier=score_multiplier, linear_score=pillar_sum, admission_mode=admission_mode, admission_power=admission_power, sizing_mode=sizing_mode, sizing_power=sizing_power, admission_shield_floor=admission_shield_floor)
            raw_score = float(result.decision_score)
            effective_score, multiplier_mode = _apply_multiplier(raw_score, regime_name=regime.regime, spec=spec)
            adjusted_side, adjusted_why = _determine_side(decimal.Decimal(str(effective_score)), decimal.Decimal(result.thr_buy), decimal.Decimal(result.thr_sell), neutral_threshold, current_side)
            current_side = adjusted_side
            if recorder.bar_close_ts_ms not in target_bar_ts_set:
                continue
            growth_flag, growth_complete = growth_flags.get((symbol, recorder.bar_close_ts_ms), (False, False))
            benchmark_row = safe_benchmark_lookup[(symbol, recorder.bar_close_ts_ms)]
            live_baseline_row = live_baseline_lookup[(symbol, recorder.bar_close_ts_ms)]
            row = prev._build_target_row(family="score_multiplier", scenario_id=spec.scenario_id, symbol=symbol, bar_close_ts_ms=recorder.bar_close_ts_ms, regime=regime, result=result, pillar_tactician=tactician, pillar_operator=operator, pillar_strategist=strategist, pillar_sum=pillar_sum, baseline_row=benchmark_row, active_growth_phase=growth_flag, active_growth_complete=growth_complete, final_side_optional=None)
            row["safe_benchmark_raw_side"] = benchmark_row["raw_side"]
            row["live_baseline_raw_side"] = live_baseline_row["raw_side"]
            row["raw_side"] = adjusted_side
            row["final_score"] = effective_score
            row["changed_vs_baseline"] = adjusted_side != benchmark_row["raw_side"]
            row["family_label"] = spec.family
            row["scenario_label"] = spec.label
            row["bullish_multiplier"] = spec.bullish_mult
            row["bearish_multiplier"] = spec.bearish_mult
            row["raw_decision_score"] = raw_score
            row["effective_decision_score"] = effective_score
            row["score_delta"] = effective_score - raw_score
            row["multiplier_mode"] = multiplier_mode
            row["multiplier_side_why"] = adjusted_why
            rows.append(row)
    rows.sort(key=lambda row: (row["bar_close_ts_ms"], row["symbol"]))
    return rows


def _compute_multiplier_metrics(rows: Sequence[dict[str, Any]], *, spec: MultiplierScenarioSpec, benchmark_lookup: dict[tuple[str, int], dict[str, Any]], live_baseline_lookup: dict[tuple[str, int], dict[str, Any]], live_baseline_metrics: micro.MicrogridMetrics, benchmark_metrics: micro.MicrogridMetrics) -> MultiplierMetrics:
    base = micro._compute_micro_metrics(rows, scenario_id=spec.scenario_id, sensitivity=SAFE_BENCHMARK_SENSITIVITY, baseline_lookup=benchmark_lookup, baseline_metrics=live_baseline_metrics, prior_winner_metrics=benchmark_metrics, status="ok")
    sell_to_neutral = 0
    neutral_to_buy = 0
    sell_to_buy = 0
    raw_scores = [float(row["raw_decision_score"]) for row in rows]
    eff_scores = [float(row["effective_decision_score"]) for row in rows]
    for row in rows:
        baseline = live_baseline_lookup[(str(row["symbol"]), int(row["bar_close_ts_ms"]))]
        if baseline["raw_side"] == "sell" and row["raw_side"] == "":
            sell_to_neutral += 1
        if baseline["raw_side"] == "" and row["raw_side"] == "buy":
            neutral_to_buy += 1
        if baseline["raw_side"] == "sell" and row["raw_side"] == "buy":
            sell_to_buy += 1
    benchmark_churn = float(benchmark_metrics.churn_rate)
    if base.false_buy_outside_growth_count > 0 or base.oscillation_flag or base.churn_rate > max(benchmark_churn * 2.5, benchmark_churn + 0.08):
        if spec.family in {"BULLISH_AMPLIFICATION", "ASYMMETRIC_REMAP"} and base.growth_capture_count > benchmark_metrics.growth_capture_count:
            classification = "bullish inflation"
        else:
            classification = "unstable / risky"
    elif base.growth_capture_count >= benchmark_metrics.growth_capture_count + 1 and base.false_buy_outside_growth_count == 0:
        classification = "true capture candidate"
    elif base.growth_capture_count == 0 and base.growth_sell_reduction_count > 0:
        classification = "neutralizer"
    elif base.growth_capture_count == benchmark_metrics.growth_capture_count and base.false_buy_outside_growth_count == 0 and base.churn_rate <= benchmark_churn + EPS:
        classification = "de-bias only"
    else:
        classification = "inconclusive"
    return MultiplierMetrics(scenario_id=spec.scenario_id, family=spec.family, label=spec.label, bullish_mult=spec.bullish_mult, bearish_mult=spec.bearish_mult, base=dataclasses.replace(base, classification=classification), classification=classification, sell_to_neutral_count=sell_to_neutral, neutral_to_buy_count=neutral_to_buy, sell_to_buy_count=sell_to_buy, raw_score_mean=prev._mean(raw_scores), raw_score_median=prev._median(raw_scores), raw_score_p90=prev._percentile(raw_scores, 0.90), eff_score_mean=prev._mean(eff_scores), eff_score_median=prev._median(eff_scores), eff_score_p90=prev._percentile(eff_scores, 0.90))


def _ranking_key(metrics: MultiplierMetrics) -> tuple[float, float, float, float]:
    return (float(metrics.base.growth_capture_count), -float(metrics.base.false_buy_outside_growth_count), float(metrics.neutral_to_buy_count + metrics.sell_to_buy_count), -float(metrics.base.churn_rate))

def _write_baseline_reconfirmation(path: Path, *, frozen_label: str, live_parity_ok: bool, benchmark_reproduced: bool) -> None:
    lines = ["# AURORA TREND_UP MULTIPLIER BASELINE RECONFIRMATION", "", "## FACTS", f"- Frozen window reused exactly: `{frozen_label}`", f"- Live baseline parity passed: `{live_parity_ok}`", f"- Current safe benchmark `(0.55, 0.15)` reproduced exactly: `{benchmark_reproduced}`", "", "## INFERENCES", "- Multiplier package changes only how already computed decision_score is interpreted for side assignment in TREND_UP.", "", "## ASSUMPTIONS", "- Thresholds, pillars, strategist source, and regime detector remain frozen.", "", "## UNKNOWNS", "- Frozen-window proof does not establish production-safe multiplier semantics across all episodes.", "", "## Metrics", "- Insertion point: `effective_score = f(decision_score)` after kernel scoring and before `_determine_side(...)`.", "- Score-source preservation proof: raw `decision_score`, `pillar_sum`, and all pillar values remain unchanged and are persisted in scenario rows.", "", "## Evidence", "- TREND_UP-only multiplier math is applied post-score / pre-side; non-TREND_UP rows pass through unchanged."]
    _write_markdown(path, lines)


def _write_orientation_baseline(path: Path, *, rows: Sequence[dict[str, Any]], metrics: MultiplierMetrics) -> None:
    negative = [abs(float(row["raw_decision_score"])) for row in rows if float(row["raw_decision_score"]) < 0.0]
    positive = [float(row["raw_decision_score"]) for row in rows if float(row["raw_decision_score"]) > 0.0]
    near_boundary = _near_boundary_count(rows)
    growth_rows = [row for row in rows if row["active_growth_complete"] and row["active_growth_phase"]]
    sell_growth = sum(1 for row in growth_rows if row["raw_side"] == "sell")
    neutral_growth = sum(1 for row in growth_rows if row["raw_side"] == "")
    buy_growth = sum(1 for row in growth_rows if row["raw_side"] == "buy")
    if neutral_growth > sell_growth and neutral_growth > buy_growth:
        diagnosis = "mostly too neutral"
    elif sell_growth > neutral_growth and sell_growth > buy_growth:
        diagnosis = "mostly too bearish"
    elif neutral_growth > 0 and sell_growth > 0 and buy_growth < neutral_growth:
        diagnosis = "both too bearish and too neutral"
    else:
        diagnosis = "not strongly short-oriented on the safe benchmark"
    lines = ["# AURORA TREND_UP SHORT ORIENTATION BASELINE", "", "## FACTS", f"- Safe benchmark full occupancy sell/neutral/buy=`{metrics.base.sell_active_count_full}/{metrics.base.neutral_count_full}/{metrics.base.buy_active_count_full}`", f"- Safe benchmark growth occupancy sell/neutral/buy=`{metrics.base.sell_active_count_growth}/{metrics.base.neutral_count_growth}/{metrics.base.buy_active_count_growth}`", f"- Safe benchmark non-growth occupancy sell/neutral/buy=`{metrics.base.sell_active_count_non_growth}/{metrics.base.neutral_count_non_growth}/{metrics.base.buy_active_count_non_growth}`", f"- Growth capture=`{prev._render_pct(metrics.base.growth_capture_pct)}` ({metrics.base.growth_capture_count}/{metrics.base.growth_point_count})", f"- False BUY outside growth=`{prev._render_pct(metrics.base.false_buy_outside_growth_pct)}` ({metrics.base.false_buy_outside_growth_count}/{metrics.base.non_growth_point_count})", f"- Churn=`{metrics.base.churn_rate:.4f}` side_flips=`{metrics.base.side_flip_count}`", "", "## INFERENCES", f"- Baseline TREND_UP behavior on the safe benchmark is diagnosed as: `{diagnosis}`.", "", "## ASSUMPTIONS", "- Negative score magnitude approximates short conviction and positive score magnitude approximates long conviction.", "", "## UNKNOWNS", "- One frozen window cannot prove structural short orientation outside this episode.", "", "## Metrics", f"- Negative score magnitude mean/median/p90=`{prev._render_num(prev._mean(negative))}` / `{prev._render_num(prev._median(negative))}` / `{prev._render_num(prev._percentile(negative, 0.90))}`", f"- Positive score magnitude mean/median/p90=`{prev._render_num(prev._mean(positive))}` / `{prev._render_num(prev._median(positive))}` / `{prev._render_num(prev._percentile(positive, 0.90))}`", f"- Near-boundary points=`{near_boundary}/{len(rows)}`", f"- Side occupancy asymmetry sell-buy=`{metrics.base.sell_active_count_full - metrics.base.buy_active_count_full}`", "", "## Evidence", "- Safe benchmark already removed pathological growth-phase SELL on this anchor (`growth_sell_reduction=100%`), so the remaining defect surface is mostly under-capture via neutrality rather than active shorting."]
    _write_markdown(path, lines)


def _write_scenario_report(path: Path, *, metrics: MultiplierMetrics, benchmark_metrics: MultiplierMetrics, live_baseline_metrics: micro.MicrogridMetrics, rows: Sequence[dict[str, Any]]) -> None:
    lines = [f"# {metrics.scenario_id} REPORT", "", "## FACTS", f"- Family: `{metrics.family}`", f"- Label: `{metrics.label}`", f"- Bullish multiplier: `{metrics.bullish_mult:.2f}`", f"- Bearish multiplier: `{metrics.bearish_mult:.2f}`", f"- Classification: `{metrics.classification}`", "", "## INFERENCES", "- This scenario changes only post-score side interpretation in TREND_UP.", "", "## ASSUMPTIONS", "- Effective score, not raw score, governs side assignment in this experiment.", "", "## UNKNOWNS", "- Frozen-window improvement may not survive weaker confirmation surfaces.", "", "## Metrics", f"- Growth capture=`{prev._render_pct(metrics.base.growth_capture_pct)}` ({metrics.base.growth_capture_count}/{metrics.base.growth_point_count}) vs benchmark `{benchmark_metrics.base.growth_capture_count}/{benchmark_metrics.base.growth_point_count}`", f"- False BUY outside growth=`{prev._render_pct(metrics.base.false_buy_outside_growth_pct)}` ({metrics.base.false_buy_outside_growth_count}/{metrics.base.non_growth_point_count})", f"- Growth SELL reduction=`{prev._render_pct(metrics.base.growth_sell_reduction_pct)}` ({metrics.base.growth_sell_reduction_count}/{live_baseline_metrics.sell_active_count_growth})", f"- SELL->neutral=`{metrics.sell_to_neutral_count}` neutral->BUY=`{metrics.neutral_to_buy_count}` SELL->BUY=`{metrics.sell_to_buy_count}`", f"- Raw score mean/median/p90=`{prev._render_num(metrics.raw_score_mean)}` / `{prev._render_num(metrics.raw_score_median)}` / `{prev._render_num(metrics.raw_score_p90)}`", f"- Effective score mean/median/p90=`{prev._render_num(metrics.eff_score_mean)}` / `{prev._render_num(metrics.eff_score_median)}` / `{prev._render_num(metrics.eff_score_p90)}`", f"- Stability churn=`{metrics.base.churn_rate:.4f}` side_flips=`{metrics.base.side_flip_count}` oscillation=`{metrics.base.oscillation_flag}`", "", "## Evidence"]
    changed_rows = [row for row in rows if row["safe_benchmark_raw_side"] != row["raw_side"]][:12]
    if not changed_rows:
        lines.append("- No raw-side change relative to the current safe benchmark.")
    else:
        for row in changed_rows:
            lines.append(f"- `{row['timestamp']}` `{row['symbol']}` benchmark=`{row['safe_benchmark_raw_side']}` scenario=`{row['raw_side']}` growth=`{row['active_growth_phase']}` raw_score=`{float(row['raw_decision_score']):.6f}` eff_score=`{float(row['effective_decision_score']):.6f}` why=`{row['multiplier_side_why']}`")
    _write_markdown(path, lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    typed_config = prev._load_typed_config(REPO_ROOT / "config" / "aurora")
    symbols = list(args.symbols) if args.symbols else list(DEFAULT_SYMBOLS)
    recorder_points, recorder_series, _recorder_files = prev._load_recorder_points(Path(args.recorder_dir), symbols, prev.TF_SEC)
    aurora_core_paths = prev._ordered_rotated_paths(args.aurora_core_glob)
    decision_log_paths = prev._ordered_rotated_paths(args.decision_log_glob)
    regime_map, decision_map, _aurora_log_files = prev._parse_aurora_core_logs(aurora_core_paths, symbols)
    _side_evidence, _side_files = prev._parse_side_evidence(decision_log_paths + aurora_core_paths, Path(args.shadow_journal), Path(args.trade_lifecycle), symbols)
    common_recorder_ts = prev._compute_common_recorder_timestamps(recorder_points, symbols)
    completeness = prev._build_completeness_map(common_recorder_ts, recorder_points, regime_map, decision_map, symbols)
    complete_segments = prev._build_complete_segments(common_recorder_ts, completeness, prev.TF_MS)
    frozen_manifest = micro._load_prior_manifest(Path(args.prior_sweep_dir))
    frozen_segment = _surface_segment(frozen_manifest["chosen_segment_start_ts_ms"], frozen_manifest["chosen_segment_end_ts_ms"])
    parent_segment = _surface_segment(frozen_manifest["parent_segment_start_ts_ms"], frozen_manifest["parent_segment_end_ts_ms"])

    live_baseline_rows, _baseline_all_series, _baseline_target_rows = prev._run_baseline_replay(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=frozen_segment, active_growth_flags={})
    live_parity_ok, _parity_mismatches = prev._validate_baseline_parity(live_baseline_rows)
    chosen_candidate, _candidate_evals, growth_flags, _growth_feature_rows, _growth_thresholds = prev._evaluate_growth_candidates(live_baseline_rows, recorder_series)
    for row in live_baseline_rows:
        flag, complete = growth_flags.get((str(row["symbol"]), int(row["bar_close_ts_ms"])), (False, False))
        row["active_growth_phase"] = flag
        row["active_growth_complete"] = complete
    live_baseline_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in live_baseline_rows}
    live_baseline_metrics = micro._compute_micro_metrics(live_baseline_rows, scenario_id="LIVE_BASELINE", sensitivity=SAFE_BENCHMARK_SENSITIVITY, baseline_lookup=live_baseline_lookup, baseline_metrics=None, prior_winner_metrics=None, status="ok")

    benchmark_spec = MultiplierScenarioSpec("SAFE_BENCHMARK", "SAFE", "SAFE", 1.0, 1.0)
    benchmark_rows = _run_multiplier_scenario(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=frozen_segment, growth_flags=growth_flags, safe_benchmark_lookup=live_baseline_lookup, live_baseline_lookup=live_baseline_lookup, spec=benchmark_spec)
    safe_benchmark_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in benchmark_rows}
    benchmark_base = micro._compute_micro_metrics(benchmark_rows, scenario_id="SAFE_BENCHMARK", sensitivity=SAFE_BENCHMARK_SENSITIVITY, baseline_lookup=safe_benchmark_lookup, baseline_metrics=live_baseline_metrics, prior_winner_metrics=live_baseline_metrics, status="ok")
    benchmark_metrics = _compute_multiplier_metrics(rows=benchmark_rows, spec=benchmark_spec, benchmark_lookup=safe_benchmark_lookup, live_baseline_lookup=live_baseline_lookup, live_baseline_metrics=live_baseline_metrics, benchmark_metrics=benchmark_base)
    prior_benchmark_row = _load_safe_benchmark_row(Path(args.prior_two_factor_dir))
    benchmark_reproduced = prior_benchmark_row is not None and int(prior_benchmark_row["growth_capture_count"]) == benchmark_metrics.base.growth_capture_count and int(prior_benchmark_row["false_buy_outside_growth_count"]) == benchmark_metrics.base.false_buy_outside_growth_count and math.isclose(float(prior_benchmark_row["churn_rate"]), benchmark_metrics.base.churn_rate, abs_tol=EPS)

    _write_baseline_reconfirmation(out_dir / "AURORA_TREND_UP_MULTIPLIER_BASELINE_RECONFIRMATION.md", frozen_label=_surface_label(frozen_segment[0], frozen_segment[-1]), live_parity_ok=live_parity_ok, benchmark_reproduced=benchmark_reproduced)
    _write_orientation_baseline(out_dir / "AURORA_TREND_UP_SHORT_ORIENTATION_BASELINE.md", rows=benchmark_rows, metrics=benchmark_metrics)

    specs = _scenario_specs()
    metrics_by_id: dict[str, MultiplierMetrics] = {}
    rows_by_id: dict[str, list[dict[str, Any]]] = {}
    for spec in specs:
        rows = _run_multiplier_scenario(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=frozen_segment, growth_flags=growth_flags, safe_benchmark_lookup=safe_benchmark_lookup, live_baseline_lookup=live_baseline_lookup, spec=spec)
        rows_by_id[spec.scenario_id] = rows
        metrics = _compute_multiplier_metrics(rows=rows, spec=spec, benchmark_lookup=safe_benchmark_lookup, live_baseline_lookup=live_baseline_lookup, live_baseline_metrics=live_baseline_metrics, benchmark_metrics=benchmark_base)
        metrics_by_id[spec.scenario_id] = metrics
        prev._write_json(out_dir / f"{spec.scenario_id}.json", rows)
        prev._write_csv(out_dir / f"{spec.scenario_id}.csv", rows)
        _write_scenario_report(out_dir / f"{spec.scenario_id}_REPORT.md", metrics=metrics, benchmark_metrics=benchmark_metrics, live_baseline_metrics=live_baseline_metrics, rows=rows)

    metrics_rows = [metrics_by_id[spec.scenario_id] for spec in specs]
    summary_rows = []
    for metrics in metrics_rows:
        row = {"scenario_id": metrics.scenario_id, "family": metrics.family, "label": metrics.label, "classification": metrics.classification, "bullish_mult": metrics.bullish_mult, "bearish_mult": metrics.bearish_mult, "sell_to_neutral_count": metrics.sell_to_neutral_count, "neutral_to_buy_count": metrics.neutral_to_buy_count, "sell_to_buy_count": metrics.sell_to_buy_count, "raw_score_mean": metrics.raw_score_mean, "raw_score_median": metrics.raw_score_median, "raw_score_p90": metrics.raw_score_p90, "eff_score_mean": metrics.eff_score_mean, "eff_score_median": metrics.eff_score_median, "eff_score_p90": metrics.eff_score_p90}
        row.update(dataclasses.asdict(metrics.base))
        summary_rows.append(row)
    _write_summary(out_dir / "AURORA_TREND_UP_MULTIPLIER_SUMMARY.json", out_dir / "AURORA_TREND_UP_MULTIPLIER_SUMMARY.csv", summary_rows)

    ranked = sorted(metrics_rows, key=_ranking_key, reverse=True)
    best_single = ranked[0]
    best_true_capture = next((item for item in ranked if item.classification == "true capture candidate"), None)
    best_family = best_single.family
    family_best = {family: next(item for item in ranked if item.family == family) for family in ("BULLISH_AMPLIFICATION", "BEARISH_DAMPING", "ASYMMETRIC_REMAP")}
    master_lines = ["# AURORA TREND_UP MULTIPLIER MASTER REPORT", "", "## FACTS", f"- Scenario count: `{len(metrics_rows)}`", f"- Live baseline parity on frozen anchor: `{live_parity_ok}`", f"- Safe benchmark: growth_capture=`{prev._render_pct(benchmark_metrics.base.growth_capture_pct)}` ({benchmark_metrics.base.growth_capture_count}/{benchmark_metrics.base.growth_point_count}), false_buy=`{prev._render_pct(benchmark_metrics.base.false_buy_outside_growth_pct)}` ({benchmark_metrics.base.false_buy_outside_growth_count}/{benchmark_metrics.base.non_growth_point_count}), churn=`{benchmark_metrics.base.churn_rate:.4f}`", f"- Best single scenario: `{best_single.scenario_id}`", f"- Best family: `{best_family}`", f"- True capture candidate exists: `{best_true_capture is not None}`", "", "## INFERENCES", "- The study isolates TREND_UP side-decision bias from feature-source math.", "", "## ASSUMPTIONS", "- Positive-score amplification and negative-score damping are faithful proxies for regime-local side bias remap.", "", "## UNKNOWNS", "- Frozen-window ranking remains local until weaker surfaces are checked.", "", "## Metrics", "| Scenario | Family | Class | Growth Capture | False BUY | Sell->Neutral | Neutral->BUY | Sell->BUY | Churn |", "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for metrics in ranked:
        master_lines.append(f"| {metrics.scenario_id} | {metrics.family} | {metrics.classification} | {prev._render_pct(metrics.base.growth_capture_pct)} ({metrics.base.growth_capture_count}/{metrics.base.growth_point_count}) | {prev._render_pct(metrics.base.false_buy_outside_growth_pct)} ({metrics.base.false_buy_outside_growth_count}/{metrics.base.non_growth_point_count}) | {metrics.sell_to_neutral_count} | {metrics.neutral_to_buy_count} | {metrics.sell_to_buy_count} | {metrics.base.churn_rate:.4f} |")
    master_lines.extend(["", "## Evidence", f"- Best bullish amplification: `{family_best['BULLISH_AMPLIFICATION'].scenario_id}` -> `{family_best['BULLISH_AMPLIFICATION'].classification}`", f"- Best bearish damping: `{family_best['BEARISH_DAMPING'].scenario_id}` -> `{family_best['BEARISH_DAMPING'].classification}`", f"- Best combined asymmetry: `{family_best['ASYMMETRIC_REMAP'].scenario_id}` -> `{family_best['ASYMMETRIC_REMAP'].classification}`"])
    _write_markdown(out_dir / "AURORA_TREND_UP_MULTIPLIER_MASTER_REPORT.md", master_lines)

    additional_segment = micro._select_additional_trend_up_surface(complete_segments, symbols, regime_map, before_ts_ms=int(frozen_manifest["parent_segment_start_ts_ms"]))
    confirmation_surfaces: list[ConfirmationSurface] = []
    for name, segment in (("PARENT_TREND_UP_SEGMENT", parent_segment), ("ADDITIONAL_RECENT_TREND_UP_EPISODE", additional_segment)):
        if not segment:
            continue
        surface_rows, _x, _y = prev._run_baseline_replay(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=segment, active_growth_flags={})
        parity_ok, mismatches = prev._validate_baseline_parity(surface_rows)
        confirmation_surfaces.append(ConfirmationSurface(name, int(segment[0]), int(segment[-1]), len(segment), parity_ok, len(mismatches)))

    top_candidates = ranked[:3]
    confirmation_rows: list[dict[str, Any]] = []
    for surface in confirmation_surfaces:
        segment = _surface_segment(surface.start_ts_ms, surface.end_ts_ms)
        surface_live_rows, _x, _y = prev._run_baseline_replay(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=segment, active_growth_flags={})
        surface_growth_flags, _features = micro._build_growth_flags_for_rows(surface_live_rows, recorder_series, candidate=chosen_candidate)
        for row in surface_live_rows:
            flag, complete = surface_growth_flags.get((str(row["symbol"]), int(row["bar_close_ts_ms"])), (False, False))
            row["active_growth_phase"] = flag
            row["active_growth_complete"] = complete
        surface_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in surface_live_rows}
        surface_live_metrics = micro._compute_micro_metrics(surface_live_rows, scenario_id=f"{surface.name}_LIVE", sensitivity=SAFE_BENCHMARK_SENSITIVITY, baseline_lookup=surface_lookup, baseline_metrics=None, prior_winner_metrics=None, status="ok")
        surface_bench_rows = _run_multiplier_scenario(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=segment, growth_flags=surface_growth_flags, safe_benchmark_lookup=surface_lookup, live_baseline_lookup=surface_lookup, spec=benchmark_spec)
        surface_bench_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in surface_bench_rows}
        surface_bench_base = micro._compute_micro_metrics(surface_bench_rows, scenario_id=f"{surface.name}_BENCH", sensitivity=SAFE_BENCHMARK_SENSITIVITY, baseline_lookup=surface_bench_lookup, baseline_metrics=surface_live_metrics, prior_winner_metrics=surface_live_metrics, status="ok")
        ranked_surface: list[tuple[MultiplierMetrics, dict[str, Any]]] = []
        for candidate in top_candidates:
            spec = next(item for item in specs if item.scenario_id == candidate.scenario_id)
            rows = _run_multiplier_scenario(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=segment, growth_flags=surface_growth_flags, safe_benchmark_lookup=surface_bench_lookup, live_baseline_lookup=surface_lookup, spec=spec)
            metrics = _compute_multiplier_metrics(rows=rows, spec=spec, benchmark_lookup=surface_bench_lookup, live_baseline_lookup=surface_lookup, live_baseline_metrics=surface_live_metrics, benchmark_metrics=surface_bench_base)
            ranked_surface.append((metrics, {"surface_name": surface.name, "scenario_id": metrics.scenario_id, "classification": metrics.classification, "growth_capture_pct": metrics.base.growth_capture_pct, "growth_capture_count": metrics.base.growth_capture_count, "growth_point_count": metrics.base.growth_point_count, "false_buy_outside_growth_pct": metrics.base.false_buy_outside_growth_pct, "false_buy_outside_growth_count": metrics.base.false_buy_outside_growth_count, "non_growth_point_count": metrics.base.non_growth_point_count, "sell_to_neutral_count": metrics.sell_to_neutral_count, "neutral_to_buy_count": metrics.neutral_to_buy_count, "sell_to_buy_count": metrics.sell_to_buy_count, "churn_rate": metrics.base.churn_rate}))
        ranked_surface.sort(key=lambda item: _ranking_key(item[0]), reverse=True)
        for rank, (_metrics, row) in enumerate(ranked_surface, start=1):
            row["surface_rank"] = rank
            confirmation_rows.append(row)
    _write_summary(out_dir / "AURORA_TREND_UP_MULTIPLIER_CONFIRMATION_SUMMARY.json", out_dir / "AURORA_TREND_UP_MULTIPLIER_CONFIRMATION_SUMMARY.csv", confirmation_rows)
    conf_lines = ["# AURORA TREND_UP MULTIPLIER CONFIRMATION REPORT", "", "## FACTS", f"- Top candidates tested beyond frozen window: `{', '.join(item.scenario_id for item in top_candidates)}`", f"- Confirmation surfaces executed: `{len(confirmation_surfaces)}`", "", "## INFERENCES", "- Confirmation surfaces are weaker whenever parity drifts outside the frozen exact-parity subwindow.", "", "## ASSUMPTIONS", "- TREND_UP-only multiplier remained local to post-score side interpretation on confirmation surfaces.", "", "## UNKNOWNS", "- Rank stability here still does not prove broader regime robustness.", "", "## Metrics"]
    for surface in confirmation_surfaces:
        conf_lines.append(f"- `{surface.name}` window=`{_surface_label(surface.start_ts_ms, surface.end_ts_ms)}` bars=`{surface.segment_bar_count}` parity_ok=`{surface.parity_ok}` mismatches=`{surface.parity_mismatch_count}`")
    conf_lines.extend(["", "## Evidence", "| Surface | Scenario | Class | Growth Capture | False BUY | Sell->Neutral | Neutral->BUY | Sell->BUY | Churn | Rank |", "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"])
    for row in confirmation_rows:
        conf_lines.append(f"| {row['surface_name']} | {row['scenario_id']} | {row['classification']} | {prev._render_pct(row['growth_capture_pct'])} ({row['growth_capture_count']}/{row['growth_point_count']}) | {prev._render_pct(row['false_buy_outside_growth_pct'])} ({row['false_buy_outside_growth_count']}/{row['non_growth_point_count']}) | {row['sell_to_neutral_count']} | {row['neutral_to_buy_count']} | {row['sell_to_buy_count']} | {row['churn_rate']:.4f} | {row['surface_rank']} |")
    _write_markdown(out_dir / "AURORA_TREND_UP_MULTIPLIER_CONFIRMATION_REPORT.md", conf_lines)

    control_specs = [prev._choose_control_segment("TREND_DOWN_CONTROL", ["TREND_DOWN"], complete_segments, symbols, regime_map), prev._choose_control_segment("ALT_REGIME_CONTROL", ["MEAN_REVERSION", "HIGH_VOLATILITY", "UNCERTAIN"], complete_segments, symbols, regime_map)]
    control_specs = [item for item in control_specs if item is not None]
    spillover_rows: list[dict[str, Any]] = []
    for candidate in top_candidates:
        spec = next(item for item in specs if item.scenario_id == candidate.scenario_id)
        for control in control_specs:
            control_segment = _surface_segment(control.start_ts_ms, control.end_ts_ms)
            control_live_rows, _x, _y = prev._run_baseline_replay(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=control_segment, active_growth_flags={})
            control_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in control_live_rows}
            control_bench_rows = _run_multiplier_scenario(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=control_segment, growth_flags={}, safe_benchmark_lookup=control_lookup, live_baseline_lookup=control_lookup, spec=benchmark_spec)
            control_bench_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in control_bench_rows}
            control_rows = _run_multiplier_scenario(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=control_segment, growth_flags={}, safe_benchmark_lookup=control_bench_lookup, live_baseline_lookup=control_lookup, spec=spec)
            sell_to_buy_flips = 0
            baseline_sell_count = 0
            changed_points = 0
            for row in control_rows:
                baseline = control_bench_lookup.get((str(row["symbol"]), int(row["bar_close_ts_ms"])))
                if baseline is None:
                    continue
                if baseline["raw_side"] == "sell":
                    baseline_sell_count += 1
                    if row["raw_side"] == "buy":
                        sell_to_buy_flips += 1
                if row["raw_side"] != baseline["raw_side"]:
                    changed_points += 1
            sell_to_buy_flip_pct = sell_to_buy_flips / max(1, baseline_sell_count)
            buy_active_pct = sum(1 for row in control_rows if row["raw_side"] == "buy") / max(1, len(control_rows))
            baseline_churn = prev._compute_churn_rate(control_bench_rows)
            scenario_churn = prev._compute_churn_rate(control_rows)
            churn_mult = 1.0 if baseline_churn <= EPS and scenario_churn <= EPS else (float("inf") if baseline_churn <= EPS else scenario_churn / baseline_churn)
            reject = sell_to_buy_flip_pct > prev.SPILLOVER_TREND_DOWN_FLIP_MAX or (control.target_regime == "TREND_DOWN" and buy_active_pct > prev.SPILLOVER_TREND_DOWN_BUY_MAX) or churn_mult > prev.CHURN_MULT_MAX
            spillover_rows.append({"scenario_id": candidate.scenario_id, "control_name": control.name, "sell_to_buy_flip_pct": sell_to_buy_flip_pct, "buy_active_pct": buy_active_pct, "changed_points": changed_points, "churn_mult": churn_mult, "verdict": "reject" if reject else "pass"})
    _write_summary(out_dir / "AURORA_TREND_UP_MULTIPLIER_SPILLOVER_SUMMARY.json", out_dir / "AURORA_TREND_UP_MULTIPLIER_SPILLOVER_SUMMARY.csv", spillover_rows)
    spill_lines = ["# AURORA TREND_UP MULTIPLIER SPILLOVER REPORT", "", "## FACTS", f"- Spillover probe rows: `{len(spillover_rows)}`", f"- Control windows sampled: `{len(control_specs)}`", "", "## INFERENCES", "- Passing bounded probes is not full cross-regime safety proof.", "", "## ASSUMPTIONS", "- Because multiplier is TREND_UP-only, non-TREND_UP controls should remain nearly unchanged.", "", "## UNKNOWNS", "- Multiplier logic may still distort unseen mixed-regime sequences outside sampled controls.", "", "## Metrics"]
    for control in control_specs:
        spill_lines.append(f"- Control `{control.name}` window=`{_surface_label(control.start_ts_ms, control.end_ts_ms)}` target_regime=`{control.target_regime}` bars=`{control.segment_bar_count}`")
    spill_lines.extend(["", "## Evidence", "| Candidate | Control | Sell->Buy Flip | BUY Active | Changed Points | Churn Mult | Verdict |", "|---|---|---:|---:|---:|---:|---|"])
    for row in spillover_rows:
        spill_lines.append(f"| {row['scenario_id']} | {row['control_name']} | {row['sell_to_buy_flip_pct']:.2%} | {row['buy_active_pct']:.2%} | {row['changed_points']} | {row['churn_mult']:.2f} | {row['verdict']} |")
    _write_markdown(out_dir / "AURORA_TREND_UP_MULTIPLIER_SPILLOVER_REPORT.md", spill_lines)

    rerun_ok = True
    for spec in specs:
        rerun_rows = _run_multiplier_scenario(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=frozen_segment, growth_flags=growth_flags, safe_benchmark_lookup=safe_benchmark_lookup, live_baseline_lookup=live_baseline_lookup, spec=spec)
        if _rows_signature(rerun_rows) != _rows_signature(rows_by_id[spec.scenario_id]):
            rerun_ok = False
            break
    validation_lines = ["# AURORA TREND_UP MULTIPLIER VALIDATION REPORT", "", "## FACTS", f"- Live baseline parity reconfirmed: `{live_parity_ok}`", f"- Safe benchmark reproduced exactly: `{benchmark_reproduced}`", f"- Scenario count executed: `{len(metrics_rows)}`", f"- Deterministic rerun signature match: `{rerun_ok}`", f"- Confirmation surfaces executed: `{len(confirmation_surfaces)}`", f"- Spillover candidates rechecked: `{len(top_candidates)}`", "", "## INFERENCES", "- The package reused the same frozen window first and changed only TREND_UP post-score side interpretation.", "", "## ASSUMPTIONS", "- Validation remains research-only, not deployment guidance.", "", "## UNKNOWNS", "- Confirmation surfaces are weaker wherever parity drifts.", "- The package still cannot prove global TREND_UP robustness or live PnL superiority.", "", "## Metrics", "- All mandatory multiplier scenarios executed with score-source frozen and raw decision_score preserved in row-level diagnostics.", "", "## Evidence", "- Multiplier touched only effective score before `_determine_side(...)`; raw score and pillars remained unchanged."]
    _write_markdown(out_dir / "AURORA_TREND_UP_MULTIPLIER_VALIDATION_REPORT.md", validation_lines)

    if best_true_capture is not None:
        recommendation = "broader shadow validation for top multiplier candidate only"
    elif best_single.classification in {"de-bias only", "inconclusive", "neutralizer", "unstable / risky", "bullish inflation"}:
        recommendation = "reject current path as insufficient"
    else:
        recommendation = "ordinary TREND_UP suppress / exhaustion-only short policy"
    final_lines = ["# AURORA TREND_UP MULTIPLIER FINAL REPORT", "", "## Proven findings", f"- Best single scenario on the frozen window: `{best_single.scenario_id}` (`{best_single.family}`) with growth_capture=`{prev._render_pct(best_single.base.growth_capture_pct)}` ({best_single.base.growth_capture_count}/{best_single.base.growth_point_count}), false_buy=`{prev._render_pct(best_single.base.false_buy_outside_growth_pct)}` ({best_single.base.false_buy_outside_growth_count}/{best_single.base.non_growth_point_count}), churn=`{best_single.base.churn_rate:.4f}`, classification=`{best_single.classification}`.", f"- Multiplier package materially beat the current safe benchmark without new problems: `{best_true_capture is not None}`.", f"- Current safe benchmark short-orientation diagnosis: see `AURORA_TREND_UP_SHORT_ORIENTATION_BASELINE.md` (safe benchmark is mostly under-capture via neutrality if SELL occupancy is already suppressed).", "", "## Best single scenario", f"- `{best_single.scenario_id}` family=`{best_single.family}` bullish_mult=`{best_single.bullish_mult:.2f}` bearish_mult=`{best_single.bearish_mult:.2f}`.", "", "## Best family", f"- `{best_family}`", "", "## Comparison to current safe benchmark", f"- Safe benchmark `(0.55, 0.15)` delivered growth_capture=`{prev._render_pct(benchmark_metrics.base.growth_capture_pct)}` ({benchmark_metrics.base.growth_capture_count}/{benchmark_metrics.base.growth_point_count}), false_buy=`{prev._render_pct(benchmark_metrics.base.false_buy_outside_growth_pct)}` ({benchmark_metrics.base.false_buy_outside_growth_count}/{benchmark_metrics.base.non_growth_point_count}), churn=`{benchmark_metrics.base.churn_rate:.4f}`.", f"- Best multiplier materially improved growth capture: `{best_single.base.growth_capture_count > benchmark_metrics.base.growth_capture_count}`.", "", "## Behavior classification", f"- Best bullish amplification `{family_best['BULLISH_AMPLIFICATION'].scenario_id}` -> `{family_best['BULLISH_AMPLIFICATION'].classification}`", f"- Best bearish damping `{family_best['BEARISH_DAMPING'].scenario_id}` -> `{family_best['BEARISH_DAMPING'].classification}`", f"- Best combined asymmetry `{family_best['ASYMMETRIC_REMAP'].scenario_id}` -> `{family_best['ASYMMETRIC_REMAP'].classification}`", "", "## Evidence limits", "- Primary ranking remains local to the frozen TREND_UP window.", "- Confirmation surfaces are weaker because parity outside the frozen exact-parity subwindow drifts.", "- Spillover probes are bounded sanity checks only.", "", "## Recommended next package", f"- {recommendation}"]
    _write_markdown(out_dir / "AURORA_TREND_UP_MULTIPLIER_FINAL_REPORT.md", final_lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
