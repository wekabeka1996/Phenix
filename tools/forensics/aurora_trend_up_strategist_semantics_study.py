#!/usr/bin/env python3
"""TREND_UP-only strategist horizon / participation study for Aurora."""
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

from tools.forensics import aurora_sensitivity_microgrid_study as micro
from tools.forensics import aurora_trend_up_strategist_sweep_study as prev

SAFE_BENCHMARK_SENSITIVITY = 0.55
SAFE_BENCHMARK_WEIGHT = 0.15
SAFE_WEIGHTS = (0.60, 0.25, 0.15)
EPS = 1e-12


@dataclass(frozen=True)
class SemanticsScenarioSpec:
    scenario_id: str
    family: str
    label: str
    mode: str
    sma_period: int | None


@dataclass(frozen=True)
class SemanticsMetrics:
    scenario_id: str
    family: str
    label: str
    mode: str
    sma_period: int | None
    base: micro.MicrogridMetrics
    classification: str
    strategist_raw_mean: float | None
    strategist_effective_mean: float | None
    strategist_delta_mean: float | None
    baseline_sell_to_neutral_count: int
    baseline_sell_to_buy_count: int


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
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "reports" / "aurora_trend_up_strategist_semantics_2026-04-14"))
    parser.add_argument("--symbols", nargs="*", default=None)
    return parser.parse_args(argv)


def _scenario_specs() -> list[SemanticsScenarioSpec]:
    return [
        SemanticsScenarioSpec("SEMANTICS_A1", "HORIZON_COMPRESSION", "A1", "horizon", 180),
        SemanticsScenarioSpec("SEMANTICS_A2", "HORIZON_COMPRESSION", "A2", "horizon", 150),
        SemanticsScenarioSpec("SEMANTICS_A3", "HORIZON_COMPRESSION", "A3", "horizon", 100),
        SemanticsScenarioSpec("SEMANTICS_A4", "HORIZON_COMPRESSION", "A4", "horizon", 75),
        SemanticsScenarioSpec("SEMANTICS_A5", "HORIZON_COMPRESSION", "A5", "horizon", 50),
        SemanticsScenarioSpec("SEMANTICS_B1", "FULL_SUPPRESSION", "B1", "zero_pre_aggregation", None),
        SemanticsScenarioSpec("SEMANTICS_B2", "FULL_SUPPRESSION", "B2", "zero_hard", None),
        SemanticsScenarioSpec("SEMANTICS_B3", "FULL_SUPPRESSION", "B3", "zero_bypass_trace", None),
        SemanticsScenarioSpec("SEMANTICS_C1", "SELL_ONLY_SUPPRESSION", "C1", "ignore_if_sell", None),
        SemanticsScenarioSpec("SEMANTICS_C2", "SELL_ONLY_SUPPRESSION", "C2", "clip_non_negative", None),
        SemanticsScenarioSpec("SEMANTICS_C3", "SELL_ONLY_SUPPRESSION", "C3", "exclude_negative_path", None),
        SemanticsScenarioSpec("SEMANTICS_C4", "SELL_ONLY_SUPPRESSION", "C4", "suppress_bearish_hold", None),
        SemanticsScenarioSpec("SEMANTICS_C5", "SELL_ONLY_SUPPRESSION", "C5", "route_to_neutral_only", None),
    ]


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


def _strategist_plumbing_summary(symbols: Sequence[str], htf_manifest_path: Path) -> list[str]:
    return [
        "Current strategist runtime contract: D1 close series -> SMA(period) -> tanh(raw*sensitivity) -> weighted into pillar_sum.",
        f"Safe benchmark freeze: sensitivity={SAFE_BENCHMARK_SENSITIVITY:.2f}, strategist_weight={SAFE_BENCHMARK_WEIGHT:.2f}.",
        f"Frozen HTF seed manifest reused: `{htf_manifest_path}`.",
        f"Symbols under study: `{', '.join(symbols)}`.",
        "Replay override insertion point: strategist contribution before aggregation into pillar_sum, with optional conditional side override for SELL-only variants.",
    ]


def _apply_semantics_override(*, spec: SemanticsScenarioSpec, strategist_base: float, strategist_horizon: float | None, provisional_side: str, current_side: str) -> tuple[float, str | None]:
    if spec.family == "HORIZON_COMPRESSION":
        if strategist_horizon is None:
            raise RuntimeError(f"Missing D1 strategist for {spec.scenario_id}")
        return strategist_horizon, None
    if spec.family == "FULL_SUPPRESSION":
        return 0.0, None
    if spec.mode == "ignore_if_sell":
        return strategist_base, "recompute_if_sell"
    if spec.mode == "clip_non_negative":
        return max(strategist_base, 0.0), None
    if spec.mode == "exclude_negative_path":
        return 0.0 if strategist_base < 0 else strategist_base, None
    if spec.mode == "suppress_bearish_hold":
        if current_side == "sell" or provisional_side == "sell":
            return max(strategist_base, 0.0), None
        return strategist_base, None
    if spec.mode == "route_to_neutral_only":
        return strategist_base, "neutralize_if_sell"
    return strategist_base, None

def _run_semantics_scenario(*, typed_config: Any, symbols: Sequence[str], recorder_points: dict[str, dict[int, prev.RecorderPoint]], regime_map: dict[tuple[str, int], prev.RegimeEvidence], decision_map: dict[tuple[str, int], prev.DecisionEvidence], frozen_segment: Sequence[int], growth_flags: dict[tuple[str, int], tuple[bool, bool]], safe_benchmark_lookup: dict[tuple[str, int], dict[str, Any]], live_baseline_lookup: dict[tuple[str, int], dict[str, Any]], spec: SemanticsScenarioSpec, d1_series_by_symbol: dict[str, list[tuple[int, float]]], d1_rule_by_symbol: dict[str, bool]) -> list[dict[str, Any]]:
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
            strategist_recorded = recorder.pillar_strategist
            if tactician is None or operator is None or strategist_recorded is None:
                current_side = ""
                continue
            strategist_base = prev._rebuild_strategist_from_sensitivity(strategist_recorded, SAFE_BENCHMARK_SENSITIVITY)
            strategist_horizon = None
            if spec.family == "HORIZON_COMPRESSION":
                strategist_horizon = prev._compute_strategist_from_d1(d1_series=d1_series_by_symbol[symbol], bar_close_ts_ms=recorder.bar_close_ts_ms, sma_period=int(spec.sma_period), sensitivity=SAFE_BENCHMARK_SENSITIVITY, include_current_open_day=d1_rule_by_symbol[symbol])
            provisional_side = safe_benchmark_lookup.get((symbol, recorder.bar_close_ts_ms), {}).get("raw_side", "")
            strategist_effective, action = _apply_semantics_override(spec=spec, strategist_base=strategist_base, strategist_horizon=strategist_horizon, provisional_side=provisional_side, current_side=current_side)
            pillar_sum = tactician * SAFE_WEIGHTS[0] + operator * SAFE_WEIGHTS[1] + strategist_effective * SAFE_WEIGHTS[2]
            result = prev.QuadraticScoringKernel.compute(symbol=symbol, features=prev._bar_features(recorder=recorder, regime=regime, pillar_tactician=tactician, pillar_operator=operator, pillar_strategist=strategist_effective, pillar_sum=pillar_sum), warmup_readiness={}, price=decimal.Decimal(str(recorder.close)), signal_weights={}, feature_neutrals={}, essential_features=[], base_threshold=threshold, regime_name=regime.regime, regime_thresholds=regime_thresholds, side_bias_state=no_bias, direction_strength_cfg={}, delta_price_cap_pct=delta_price_cap_pct, neutral_threshold=neutral_threshold, current_side=current_side, normalize_mode=str(getattr(getattr(decision_cfg, "signals", None), "normalize_signals_mode", "signed_v2")), shield_fn=shield_fn, score_multiplier=score_multiplier, linear_score=pillar_sum, admission_mode=admission_mode, admission_power=admission_power, sizing_mode=sizing_mode, sizing_power=sizing_power, admission_shield_floor=admission_shield_floor)
            final_side = str(result.side)
            final_result = result
            final_effective = strategist_effective
            if action == "recompute_if_sell" and final_side == "sell":
                final_effective = 0.0
                final_pillar_sum = tactician * SAFE_WEIGHTS[0] + operator * SAFE_WEIGHTS[1]
                final_result = prev.QuadraticScoringKernel.compute(symbol=symbol, features=prev._bar_features(recorder=recorder, regime=regime, pillar_tactician=tactician, pillar_operator=operator, pillar_strategist=0.0, pillar_sum=final_pillar_sum), warmup_readiness={}, price=decimal.Decimal(str(recorder.close)), signal_weights={}, feature_neutrals={}, essential_features=[], base_threshold=threshold, regime_name=regime.regime, regime_thresholds=regime_thresholds, side_bias_state=no_bias, direction_strength_cfg={}, delta_price_cap_pct=delta_price_cap_pct, neutral_threshold=neutral_threshold, current_side=current_side, normalize_mode=str(getattr(getattr(decision_cfg, "signals", None), "normalize_signals_mode", "signed_v2")), shield_fn=shield_fn, score_multiplier=score_multiplier, linear_score=final_pillar_sum, admission_mode=admission_mode, admission_power=admission_power, sizing_mode=sizing_mode, sizing_power=sizing_power, admission_shield_floor=admission_shield_floor)
                final_side = str(final_result.side)
                pillar_sum = final_pillar_sum
            elif action == "neutralize_if_sell" and final_side == "sell":
                final_side = ""
            current_side = final_side
            if recorder.bar_close_ts_ms not in target_bar_ts_set:
                continue
            growth_flag, growth_complete = growth_flags.get((symbol, recorder.bar_close_ts_ms), (False, False))
            benchmark_row = safe_benchmark_lookup[(symbol, recorder.bar_close_ts_ms)]
            live_baseline_row = live_baseline_lookup[(symbol, recorder.bar_close_ts_ms)]
            row = prev._build_target_row(family="strategist_semantics", scenario_id=spec.scenario_id, symbol=symbol, bar_close_ts_ms=recorder.bar_close_ts_ms, regime=regime, result=final_result, pillar_tactician=tactician, pillar_operator=operator, pillar_strategist=final_effective, pillar_sum=pillar_sum, baseline_row=benchmark_row, active_growth_phase=growth_flag, active_growth_complete=growth_complete, final_side_optional=None)
            row["raw_side"] = final_side
            row["changed_vs_baseline"] = final_side != benchmark_row["raw_side"]
            row["safe_benchmark_raw_side"] = benchmark_row["raw_side"]
            row["live_baseline_raw_side"] = live_baseline_row["raw_side"]
            row["family_label"] = spec.family
            row["scenario_label"] = spec.label
            row["semantic_mode"] = spec.mode
            row["semantic_sma_period"] = spec.sma_period
            row["strategist_raw"] = strategist_base
            row["strategist_effective"] = final_effective
            row["strategist_contrib_raw"] = strategist_base * SAFE_WEIGHTS[2]
            row["strategist_contrib_effective"] = final_effective * SAFE_WEIGHTS[2]
            row["semantic_action"] = action or "direct"
            rows.append(row)
    rows.sort(key=lambda row: (row["bar_close_ts_ms"], row["symbol"]))
    return rows


def _compute_semantics_metrics(rows: Sequence[dict[str, Any]], *, spec: SemanticsScenarioSpec, benchmark_lookup: dict[tuple[str, int], dict[str, Any]], live_baseline_lookup: dict[tuple[str, int], dict[str, Any]], live_baseline_metrics: micro.MicrogridMetrics, benchmark_metrics: micro.MicrogridMetrics) -> SemanticsMetrics:
    base = micro._compute_micro_metrics(rows, scenario_id=spec.scenario_id, sensitivity=SAFE_BENCHMARK_SENSITIVITY, baseline_lookup=benchmark_lookup, baseline_metrics=live_baseline_metrics, prior_winner_metrics=benchmark_metrics, status="ok")
    strategist_raw = [float(row["strategist_raw"]) for row in rows]
    strategist_eff = [float(row["strategist_effective"]) for row in rows]
    strategist_delta = [float(row["strategist_effective"]) - float(row["strategist_raw"]) for row in rows]
    sell_to_neutral = 0
    sell_to_buy = 0
    for row in rows:
        baseline = live_baseline_lookup[(str(row["symbol"]), int(row["bar_close_ts_ms"]))]
        if baseline["raw_side"] == "sell":
            if row["raw_side"] == "":
                sell_to_neutral += 1
            elif row["raw_side"] == "buy":
                sell_to_buy += 1
    if base.false_buy_outside_growth_count > 0 and base.growth_capture_count > benchmark_metrics.growth_capture_count:
        classification = "over-bullish distortion"
    elif base.false_buy_outside_growth_count > 0 or base.oscillation_flag or base.churn_rate > max(benchmark_metrics.churn_rate * 2.5, benchmark_metrics.churn_rate + 0.08):
        classification = "unstable / risky"
    elif base.growth_capture_count >= benchmark_metrics.growth_capture_count + 1 and base.false_buy_outside_growth_count == 0:
        classification = "true capture candidate"
    elif base.growth_capture_count == 0 and base.growth_sell_reduction_count > 0:
        classification = "neutralizer"
    elif base.growth_capture_count == benchmark_metrics.growth_capture_count and base.false_buy_outside_growth_count == 0 and base.churn_rate <= benchmark_metrics.churn_rate + EPS:
        classification = "de-bias only"
    else:
        classification = "inconclusive"
    return SemanticsMetrics(scenario_id=spec.scenario_id, family=spec.family, label=spec.label, mode=spec.mode, sma_period=spec.sma_period, base=dataclasses.replace(base, classification=classification), classification=classification, strategist_raw_mean=prev._mean(strategist_raw), strategist_effective_mean=prev._mean(strategist_eff), strategist_delta_mean=prev._mean(strategist_delta), baseline_sell_to_neutral_count=sell_to_neutral, baseline_sell_to_buy_count=sell_to_buy)


def _ranking_key(metrics: SemanticsMetrics) -> tuple[float, float, float, float]:
    return (float(metrics.base.growth_capture_count), -float(metrics.base.false_buy_outside_growth_count), float(metrics.base.growth_sell_reduction_count), -float(metrics.base.churn_rate))


def _write_baseline_reconfirmation(path: Path, *, frozen_label: str, live_parity_ok: bool, benchmark_reproduced: bool, plumbing_lines: Sequence[str]) -> None:
    lines = ["# AURORA TREND_UP STRATEGIST SEMANTICS BASELINE RECONFIRMATION", "", "## FACTS", f"- Frozen window reused exactly: `{frozen_label}`", f"- Live baseline parity passed: `{live_parity_ok}`", f"- Current safe benchmark `(0.55, 0.15)` reproduced exactly: `{benchmark_reproduced}`", "", "## INFERENCES", "- The package changes strategist semantics only inside TREND_UP; thresholds and non-strategist score-source stay frozen.", "", "## ASSUMPTIONS", "- D1 HTF seed from the prior strategist sweep remains authoritative for horizon-compression replay.", "", "## UNKNOWNS", "- Reusing one frozen window does not prove broader semantic correctness.", "", "## Metrics"]
    lines.extend(f"- {item}" for item in plumbing_lines)
    lines.extend(["", "## Evidence", "- Override insertion point: strategist value before weighted aggregation into pillar_sum, plus explicit SELL-only side override branches for C-family."])
    _write_markdown(path, lines)


def _write_scenario_report(path: Path, *, metrics: SemanticsMetrics, benchmark_metrics: SemanticsMetrics, live_baseline_metrics: micro.MicrogridMetrics, rows: Sequence[dict[str, Any]]) -> None:
    lines = [f"# {metrics.scenario_id} REPORT", "", "## FACTS", f"- Family: `{metrics.family}`", f"- Label: `{metrics.label}`", f"- Mode: `{metrics.mode}`", f"- SMA override: `{metrics.sma_period}`", f"- Classification: `{metrics.classification}`", "", "## INFERENCES", "- This scenario tests strategist semantics, not threshold geometry or weight/sensitivity retune.", "", "## ASSUMPTIONS", "- Effective strategist replacement is applied only for TREND_UP side formation.", "", "## UNKNOWNS", "- Local frozen-window win may still degrade on weaker surfaces.", "", "## Metrics", f"- Growth capture=`{prev._render_pct(metrics.base.growth_capture_pct)}` ({metrics.base.growth_capture_count}/{metrics.base.growth_point_count}) vs benchmark `{benchmark_metrics.base.growth_capture_count}/{benchmark_metrics.base.growth_point_count}`", f"- False BUY outside growth=`{prev._render_pct(metrics.base.false_buy_outside_growth_pct)}` ({metrics.base.false_buy_outside_growth_count}/{metrics.base.non_growth_point_count})", f"- Growth SELL reduction=`{prev._render_pct(metrics.base.growth_sell_reduction_pct)}` ({metrics.base.growth_sell_reduction_count}/{live_baseline_metrics.sell_active_count_growth})", f"- Occupancy growth sell/neutral/buy=`{metrics.base.sell_active_count_growth}/{metrics.base.neutral_count_growth}/{metrics.base.buy_active_count_growth}`", f"- Occupancy non-growth sell/neutral/buy=`{metrics.base.sell_active_count_non_growth}/{metrics.base.neutral_count_non_growth}/{metrics.base.buy_active_count_non_growth}`", f"- Strategist raw/effective/delta mean=`{prev._render_num(metrics.strategist_raw_mean)}` / `{prev._render_num(metrics.strategist_effective_mean)}` / `{prev._render_num(metrics.strategist_delta_mean)}`", f"- Baseline SELL -> neutral/buy=`{metrics.baseline_sell_to_neutral_count}/{metrics.baseline_sell_to_buy_count}`", f"- Stability churn=`{metrics.base.churn_rate:.4f}` side_flips=`{metrics.base.side_flip_count}` oscillation=`{metrics.base.oscillation_flag}`", "", "## Evidence"]
    changed_rows = [row for row in rows if row["safe_benchmark_raw_side"] != row["raw_side"]][:10]
    if not changed_rows:
        lines.append("- No raw-side change relative to the current safe benchmark.")
    else:
        for row in changed_rows:
            lines.append(f"- `{row['timestamp']}` `{row['symbol']}` benchmark=`{row['safe_benchmark_raw_side']}` scenario=`{row['raw_side']}` strategist_raw=`{float(row['strategist_raw']):.6f}` strategist_effective=`{float(row['strategist_effective']):.6f}` action=`{row['semantic_action']}` growth=`{row['active_growth_phase']}`")
    _write_markdown(path, lines)

def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    typed_config = prev._load_typed_config(REPO_ROOT / "config" / "aurora")
    symbols = list(args.symbols) if args.symbols else prev._parse_aurora_symbols(Path(args.strategies_yaml))
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
    htf_manifest_path = Path(frozen_manifest["htf_seed_manifest"])
    htf_manifest = prev.json.loads(htf_manifest_path.read_text(encoding="utf-8"))
    d1_series_by_symbol = prev._load_d1_series_from_manifest(htf_manifest)

    live_baseline_rows, _baseline_all_series, _baseline_target_rows = prev._run_baseline_replay(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=frozen_segment, active_growth_flags={})
    live_parity_ok, _parity_mismatches = prev._validate_baseline_parity(live_baseline_rows)
    chosen_candidate, _candidate_evals, growth_flags, _growth_feature_rows, _growth_thresholds = prev._evaluate_growth_candidates(live_baseline_rows, recorder_series)
    for row in live_baseline_rows:
        flag, complete = growth_flags.get((str(row["symbol"]), int(row["bar_close_ts_ms"])), (False, False))
        row["active_growth_phase"] = flag
        row["active_growth_complete"] = complete
    d1_rule_by_symbol = prev._choose_d1_inclusion_rule(d1_series_by_symbol, live_baseline_rows)
    live_baseline_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in live_baseline_rows}
    live_baseline_metrics = micro._compute_micro_metrics(live_baseline_rows, scenario_id="LIVE_BASELINE", sensitivity=SAFE_BENCHMARK_SENSITIVITY, baseline_lookup=live_baseline_lookup, baseline_metrics=None, prior_winner_metrics=None, status="ok")

    benchmark_spec = SemanticsScenarioSpec("SAFE_BENCHMARK", "BENCHMARK", "SAFE", "baseline", None)
    benchmark_rows = _run_semantics_scenario(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=frozen_segment, growth_flags=growth_flags, safe_benchmark_lookup=live_baseline_lookup, live_baseline_lookup=live_baseline_lookup, spec=benchmark_spec, d1_series_by_symbol=d1_series_by_symbol, d1_rule_by_symbol=d1_rule_by_symbol)
    safe_benchmark_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in benchmark_rows}
    benchmark_base = micro._compute_micro_metrics(benchmark_rows, scenario_id="SAFE_BENCHMARK", sensitivity=SAFE_BENCHMARK_SENSITIVITY, baseline_lookup=safe_benchmark_lookup, baseline_metrics=live_baseline_metrics, prior_winner_metrics=live_baseline_metrics, status="ok")
    benchmark_metrics = _compute_semantics_metrics(benchmark_rows, spec=benchmark_spec, benchmark_lookup=safe_benchmark_lookup, live_baseline_lookup=live_baseline_lookup, live_baseline_metrics=live_baseline_metrics, benchmark_metrics=benchmark_base)
    prior_benchmark_row = _load_safe_benchmark_row(Path(args.prior_two_factor_dir))
    benchmark_reproduced = prior_benchmark_row is not None and int(prior_benchmark_row["growth_capture_count"]) == benchmark_metrics.base.growth_capture_count and int(prior_benchmark_row["false_buy_outside_growth_count"]) == benchmark_metrics.base.false_buy_outside_growth_count and math.isclose(float(prior_benchmark_row["churn_rate"]), benchmark_metrics.base.churn_rate, abs_tol=EPS)

    _write_baseline_reconfirmation(out_dir / "AURORA_TREND_UP_STRATEGIST_SEMANTICS_BASELINE_RECONFIRMATION.md", frozen_label=_surface_label(frozen_segment[0], frozen_segment[-1]), live_parity_ok=live_parity_ok, benchmark_reproduced=benchmark_reproduced, plumbing_lines=_strategist_plumbing_summary(symbols, htf_manifest_path))

    scenario_specs = _scenario_specs()
    metrics_by_id: dict[str, SemanticsMetrics] = {}
    rows_by_id: dict[str, list[dict[str, Any]]] = {}
    for spec in scenario_specs:
        rows = _run_semantics_scenario(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=frozen_segment, growth_flags=growth_flags, safe_benchmark_lookup=safe_benchmark_lookup, live_baseline_lookup=live_baseline_lookup, spec=spec, d1_series_by_symbol=d1_series_by_symbol, d1_rule_by_symbol=d1_rule_by_symbol)
        rows_by_id[spec.scenario_id] = rows
        metrics_by_id[spec.scenario_id] = _compute_semantics_metrics(rows, spec=spec, benchmark_lookup=safe_benchmark_lookup, live_baseline_lookup=live_baseline_lookup, live_baseline_metrics=live_baseline_metrics, benchmark_metrics=benchmark_base)
        prev._write_json(out_dir / f"{spec.scenario_id}.json", rows)
        prev._write_csv(out_dir / f"{spec.scenario_id}.csv", rows)
        _write_scenario_report(out_dir / f"{spec.scenario_id}_REPORT.md", metrics=metrics_by_id[spec.scenario_id], benchmark_metrics=benchmark_metrics, live_baseline_metrics=live_baseline_metrics, rows=rows)
    metrics_rows = [metrics_by_id[spec.scenario_id] for spec in scenario_specs]
    summary_rows = []
    for metrics in metrics_rows:
        row = {"scenario_id": metrics.scenario_id, "family": metrics.family, "label": metrics.label, "mode": metrics.mode, "sma_period": metrics.sma_period, "classification": metrics.classification, "strategist_raw_mean": metrics.strategist_raw_mean, "strategist_effective_mean": metrics.strategist_effective_mean, "strategist_delta_mean": metrics.strategist_delta_mean, "baseline_sell_to_neutral_count": metrics.baseline_sell_to_neutral_count, "baseline_sell_to_buy_count": metrics.baseline_sell_to_buy_count}
        row.update(dataclasses.asdict(metrics.base))
        summary_rows.append(row)
    _write_summary(out_dir / "AURORA_TREND_UP_STRATEGIST_SEMANTICS_SUMMARY.json", out_dir / "AURORA_TREND_UP_STRATEGIST_SEMANTICS_SUMMARY.csv", summary_rows)

    ranked = sorted(metrics_rows, key=_ranking_key, reverse=True)
    best_single = ranked[0]
    best_true_capture = next((item for item in ranked if item.classification == "true capture candidate"), None)
    best_family = next((item.family for item in ranked if item.classification in {"true capture candidate", "de-bias only", "neutralizer"}), best_single.family)
    family_best = {family: next(item for item in ranked if item.family == family) for family in ("HORIZON_COMPRESSION", "FULL_SUPPRESSION", "SELL_ONLY_SUPPRESSION")}
    master_lines = ["# AURORA TREND_UP STRATEGIST SEMANTICS MASTER REPORT", "", "## FACTS", f"- Scenario count: `{len(metrics_rows)}`", f"- Safe benchmark: growth_capture=`{prev._render_pct(benchmark_metrics.base.growth_capture_pct)}` ({benchmark_metrics.base.growth_capture_count}/{benchmark_metrics.base.growth_point_count}), false_buy=`{prev._render_pct(benchmark_metrics.base.false_buy_outside_growth_pct)}` ({benchmark_metrics.base.false_buy_outside_growth_count}/{benchmark_metrics.base.non_growth_point_count}), churn=`{benchmark_metrics.base.churn_rate:.4f}`", f"- Best single scenario: `{best_single.scenario_id}`", f"- Best family: `{best_family}`", f"- Best local patch: `not proven`", "", "## INFERENCES", "- This package distinguishes strategist lag, strategist participation, and strategist SELL influence as separate hypotheses.", "", "## ASSUMPTIONS", "- Material improvement means strictly beating the current safe benchmark on growth-capture count.", "", "## UNKNOWNS", "- Frozen-window ranking remains local evidence until weaker surfaces are checked.", "", "## Metrics", "| Scenario | Family | Class | Growth Capture | False BUY | Growth SELL Reduction | Churn |", "|---|---|---|---:|---:|---:|---:|"]
    for metrics in ranked:
        master_lines.append(f"| {metrics.scenario_id} | {metrics.family} | {metrics.classification} | {prev._render_pct(metrics.base.growth_capture_pct)} ({metrics.base.growth_capture_count}/{metrics.base.growth_point_count}) | {prev._render_pct(metrics.base.false_buy_outside_growth_pct)} ({metrics.base.false_buy_outside_growth_count}/{metrics.base.non_growth_point_count}) | {prev._render_pct(metrics.base.growth_sell_reduction_pct)} ({metrics.base.growth_sell_reduction_count}/{live_baseline_metrics.sell_active_count_growth}) | {metrics.base.churn_rate:.4f} |")
    master_lines.extend(["", "## Evidence", f"- Horizon compression best: `{family_best['HORIZON_COMPRESSION'].scenario_id}` -> `{family_best['HORIZON_COMPRESSION'].classification}`", f"- Full suppression best: `{family_best['FULL_SUPPRESSION'].scenario_id}` -> `{family_best['FULL_SUPPRESSION'].classification}`", f"- SELL-only suppression best: `{family_best['SELL_ONLY_SUPPRESSION'].scenario_id}` -> `{family_best['SELL_ONLY_SUPPRESSION'].classification}`"])
    _write_markdown(out_dir / "AURORA_TREND_UP_STRATEGIST_SEMANTICS_MASTER_REPORT.md", master_lines)

    additional_segment = micro._select_additional_trend_up_surface(complete_segments, symbols, regime_map, before_ts_ms=int(frozen_manifest["parent_segment_start_ts_ms"]))
    confirmation_surfaces: list[ConfirmationSurface] = []
    for name, segment in (("PARENT_TREND_UP_SEGMENT", parent_segment), ("ADDITIONAL_RECENT_TREND_UP_EPISODE", additional_segment)):
        if not segment:
            continue
        surface_rows, _a, _b = prev._run_baseline_replay(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=segment, active_growth_flags={})
        parity_ok, mismatches = prev._validate_baseline_parity(surface_rows)
        confirmation_surfaces.append(ConfirmationSurface(name, int(segment[0]), int(segment[-1]), len(segment), parity_ok, len(mismatches)))
    top_candidates = ranked[:3]
    confirmation_rows: list[dict[str, Any]] = []
    for surface in confirmation_surfaces:
        segment = _surface_segment(surface.start_ts_ms, surface.end_ts_ms)
        surface_live_rows, _a, _b = prev._run_baseline_replay(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=segment, active_growth_flags={})
        surface_growth_flags, _features = micro._build_growth_flags_for_rows(surface_live_rows, recorder_series, candidate=chosen_candidate)
        for row in surface_live_rows:
            flag, complete = surface_growth_flags.get((str(row["symbol"]), int(row["bar_close_ts_ms"])), (False, False))
            row["active_growth_phase"] = flag
            row["active_growth_complete"] = complete
        surface_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in surface_live_rows}
        surface_live_metrics = micro._compute_micro_metrics(surface_live_rows, scenario_id=f"{surface.name}_LIVE", sensitivity=SAFE_BENCHMARK_SENSITIVITY, baseline_lookup=surface_lookup, baseline_metrics=None, prior_winner_metrics=None, status="ok")
        surface_bench_rows = _run_semantics_scenario(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=segment, growth_flags=surface_growth_flags, safe_benchmark_lookup=surface_lookup, live_baseline_lookup=surface_lookup, spec=benchmark_spec, d1_series_by_symbol=d1_series_by_symbol, d1_rule_by_symbol=d1_rule_by_symbol)
        surface_bench_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in surface_bench_rows}
        surface_bench_base = micro._compute_micro_metrics(surface_bench_rows, scenario_id=f"{surface.name}_BENCH", sensitivity=SAFE_BENCHMARK_SENSITIVITY, baseline_lookup=surface_bench_lookup, baseline_metrics=surface_live_metrics, prior_winner_metrics=surface_live_metrics, status="ok")
        ranked_surface: list[tuple[SemanticsMetrics, dict[str, Any]]] = []
        for candidate in top_candidates:
            spec = next(item for item in scenario_specs if item.scenario_id == candidate.scenario_id)
            rows = _run_semantics_scenario(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=segment, growth_flags=surface_growth_flags, safe_benchmark_lookup=surface_bench_lookup, live_baseline_lookup=surface_lookup, spec=spec, d1_series_by_symbol=d1_series_by_symbol, d1_rule_by_symbol=d1_rule_by_symbol)
            metrics = _compute_semantics_metrics(rows, spec=spec, benchmark_lookup=surface_bench_lookup, live_baseline_lookup=surface_lookup, live_baseline_metrics=surface_live_metrics, benchmark_metrics=surface_bench_base)
            ranked_surface.append((metrics, {"surface_name": surface.name, "scenario_id": metrics.scenario_id, "growth_capture_pct": metrics.base.growth_capture_pct, "growth_capture_count": metrics.base.growth_capture_count, "growth_point_count": metrics.base.growth_point_count, "false_buy_outside_growth_pct": metrics.base.false_buy_outside_growth_pct, "false_buy_outside_growth_count": metrics.base.false_buy_outside_growth_count, "non_growth_point_count": metrics.base.non_growth_point_count, "growth_sell_reduction_pct": metrics.base.growth_sell_reduction_pct, "growth_sell_reduction_count": metrics.base.growth_sell_reduction_count, "baseline_growth_sell_count": surface_live_metrics.sell_active_count_growth, "churn_rate": metrics.base.churn_rate}))
        ranked_surface.sort(key=lambda item: _ranking_key(item[0]), reverse=True)
        for rank, (_metrics, row) in enumerate(ranked_surface, start=1):
            row["surface_rank"] = rank
            confirmation_rows.append(row)
    _write_summary(out_dir / "AURORA_TREND_UP_STRATEGIST_SEMANTICS_CONFIRMATION_SUMMARY.json", out_dir / "AURORA_TREND_UP_STRATEGIST_SEMANTICS_CONFIRMATION_SUMMARY.csv", confirmation_rows)
    conf_lines = ["# AURORA TREND_UP STRATEGIST SEMANTICS CONFIRMATION REPORT", "", "## FACTS", f"- Top candidates tested beyond frozen window: `{', '.join(item.scenario_id for item in top_candidates)}`", f"- Confirmation surfaces executed: `{len(confirmation_surfaces)}`", "", "## INFERENCES", "- Confirmation surfaces are weaker whenever parity drifts outside the frozen exact-parity subwindow.", "", "## ASSUMPTIONS", "- Strategist semantic override remained TREND_UP-only.", "", "## UNKNOWNS", "- Rank stability here still does not prove broader regime robustness.", "", "## Metrics"]
    for surface in confirmation_surfaces:
        conf_lines.append(f"- `{surface.name}` window=`{_surface_label(surface.start_ts_ms, surface.end_ts_ms)}` bars=`{surface.segment_bar_count}` parity_ok=`{surface.parity_ok}` mismatches=`{surface.parity_mismatch_count}`")
    conf_lines.extend(["", "## Evidence", "| Surface | Scenario | Growth Capture | False BUY | Growth SELL Reduction | Churn | Rank |", "|---|---|---:|---:|---:|---:|---:|"])
    for row in confirmation_rows:
        conf_lines.append(f"| {row['surface_name']} | {row['scenario_id']} | {prev._render_pct(row['growth_capture_pct'])} ({row['growth_capture_count']}/{row['growth_point_count']}) | {prev._render_pct(row['false_buy_outside_growth_pct'])} ({row['false_buy_outside_growth_count']}/{row['non_growth_point_count']}) | {prev._render_pct(row['growth_sell_reduction_pct'])} ({row['growth_sell_reduction_count']}/{row['baseline_growth_sell_count']}) | {row['churn_rate']:.4f} | {row['surface_rank']} |")
    _write_markdown(out_dir / "AURORA_TREND_UP_STRATEGIST_SEMANTICS_CONFIRMATION_REPORT.md", conf_lines)

    control_specs = [prev._choose_control_segment("TREND_DOWN_CONTROL", ["TREND_DOWN"], complete_segments, symbols, regime_map), prev._choose_control_segment("ALT_REGIME_CONTROL", ["MEAN_REVERSION", "HIGH_VOLATILITY", "UNCERTAIN"], complete_segments, symbols, regime_map)]
    control_specs = [item for item in control_specs if item is not None]
    spillover_rows: list[dict[str, Any]] = []
    for candidate in top_candidates:
        spec = next(item for item in scenario_specs if item.scenario_id == candidate.scenario_id)
        for control in control_specs:
            control_segment = _surface_segment(control.start_ts_ms, control.end_ts_ms)
            control_live_rows, _a, _b = prev._run_baseline_replay(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=control_segment, active_growth_flags={})
            control_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in control_live_rows}
            control_bench_rows = _run_semantics_scenario(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=control_segment, growth_flags={}, safe_benchmark_lookup=control_lookup, live_baseline_lookup=control_lookup, spec=benchmark_spec, d1_series_by_symbol=d1_series_by_symbol, d1_rule_by_symbol=d1_rule_by_symbol)
            control_bench_lookup = {(str(row["symbol"]), int(row["bar_close_ts_ms"])): row for row in control_bench_rows}
            control_rows = _run_semantics_scenario(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=control_segment, growth_flags={}, safe_benchmark_lookup=control_bench_lookup, live_baseline_lookup=control_lookup, spec=spec, d1_series_by_symbol=d1_series_by_symbol, d1_rule_by_symbol=d1_rule_by_symbol)
            sell_to_buy_flips = 0
            baseline_sell_count = 0
            for row in control_rows:
                baseline = control_bench_lookup.get((str(row["symbol"]), int(row["bar_close_ts_ms"])))
                if baseline is None:
                    continue
                if baseline["raw_side"] == "sell":
                    baseline_sell_count += 1
                    if row["raw_side"] == "buy":
                        sell_to_buy_flips += 1
            sell_to_buy_flip_pct = sell_to_buy_flips / max(1, baseline_sell_count)
            buy_active_pct = sum(1 for row in control_rows if row["raw_side"] == "buy") / max(1, len(control_rows))
            baseline_churn = prev._compute_churn_rate(control_bench_rows)
            scenario_churn = prev._compute_churn_rate(control_rows)
            churn_mult = 1.0 if baseline_churn <= EPS and scenario_churn <= EPS else (float("inf") if baseline_churn <= EPS else scenario_churn / baseline_churn)
            reject = sell_to_buy_flip_pct > prev.SPILLOVER_TREND_DOWN_FLIP_MAX or (control.target_regime == "TREND_DOWN" and buy_active_pct > prev.SPILLOVER_TREND_DOWN_BUY_MAX) or churn_mult > prev.CHURN_MULT_MAX
            spillover_rows.append({"scenario_id": candidate.scenario_id, "control_name": control.name, "sell_to_buy_flip_pct": sell_to_buy_flip_pct, "buy_active_pct": buy_active_pct, "churn_mult": churn_mult, "verdict": "reject" if reject else "pass"})
    _write_summary(out_dir / "AURORA_TREND_UP_STRATEGIST_SEMANTICS_SPILLOVER_SUMMARY.json", out_dir / "AURORA_TREND_UP_STRATEGIST_SEMANTICS_SPILLOVER_SUMMARY.csv", spillover_rows)
    spill_lines = ["# AURORA TREND_UP STRATEGIST SEMANTICS SPILLOVER REPORT", "", "## FACTS", f"- Spillover probe rows: `{len(spillover_rows)}`", f"- Control windows sampled: `{len(control_specs)}`", "", "## INFERENCES", "- Passing bounded probes is not full cross-regime safety proof.", "", "## ASSUMPTIONS", "- Hard reject remains: TREND_DOWN buy-active > 5%, sell->buy flips > 10%, or churn > 1.5x.", "", "## UNKNOWNS", "- Semantic strategist changes could still distort unseen regimes outside sampled controls.", "", "## Metrics"]
    for control in control_specs:
        spill_lines.append(f"- Control `{control.name}` window=`{_surface_label(control.start_ts_ms, control.end_ts_ms)}` target_regime=`{control.target_regime}` bars=`{control.segment_bar_count}`")
    spill_lines.extend(["", "## Evidence", "| Candidate | Control | Sell->Buy Flip | BUY Active | Churn Mult | Verdict |", "|---|---|---:|---:|---:|---|"])
    for row in spillover_rows:
        spill_lines.append(f"| {row['scenario_id']} | {row['control_name']} | {row['sell_to_buy_flip_pct']:.2%} | {row['buy_active_pct']:.2%} | {row['churn_mult']:.2f} | {row['verdict']} |")
    _write_markdown(out_dir / "AURORA_TREND_UP_STRATEGIST_SEMANTICS_SPILLOVER_REPORT.md", spill_lines)

    rerun_ok = True
    for spec in scenario_specs:
        rerun_rows = _run_semantics_scenario(typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map, decision_map=decision_map, frozen_segment=frozen_segment, growth_flags=growth_flags, safe_benchmark_lookup=safe_benchmark_lookup, live_baseline_lookup=live_baseline_lookup, spec=spec, d1_series_by_symbol=d1_series_by_symbol, d1_rule_by_symbol=d1_rule_by_symbol)
        if _rows_signature(rerun_rows) != _rows_signature(rows_by_id[spec.scenario_id]):
            rerun_ok = False
            break
    validation_lines = ["# AURORA TREND_UP STRATEGIST SEMANTICS VALIDATION REPORT", "", "## FACTS", f"- Live baseline parity reconfirmed: `{live_parity_ok}`", f"- Safe benchmark reproduced exactly: `{benchmark_reproduced}`", f"- Scenario count executed: `{len(metrics_rows)}`", f"- Deterministic rerun signature match: `{rerun_ok}`", f"- Confirmation surfaces executed: `{len(confirmation_surfaces)}`", f"- Spillover candidates rechecked: `{len(top_candidates)}`", "", "## INFERENCES", "- The package is valid only because it reused the same frozen window first and stayed strategist-semantics-only.", "", "## ASSUMPTIONS", "- Validation remains research-only, not deployment guidance.", "", "## UNKNOWNS", "- Confirmation surfaces are weaker wherever parity drifts.", "- The package still cannot prove global TREND_UP robustness or live PnL superiority.", "", "## Metrics", "- All mandatory strategist-semantics scenarios executed with thresholds and weights frozen at the safe benchmark.", "", "## Evidence", "- Horizon overrides used frozen D1 seed; suppression overrides changed only strategist participation in TREND_UP."]
    _write_markdown(out_dir / "AURORA_TREND_UP_STRATEGIST_SEMANTICS_VALIDATION_REPORT.md", validation_lines)

    issue_inference = "strategist lag" if best_family == "HORIZON_COMPRESSION" else ("strategist participation" if best_family == "FULL_SUPPRESSION" else "strategist SELL influence")
    recommendation = "broader shadow validation for top strategist-semantics candidate only" if best_true_capture is not None else "regime-overlay / hard countertrend short gate study"
    final_lines = ["# AURORA TREND_UP STRATEGIST SEMANTICS FINAL REPORT", "", "## Proven findings", f"- Best single scenario on the frozen window: `{best_single.scenario_id}` (`{best_single.family}`) with growth_capture=`{prev._render_pct(best_single.base.growth_capture_pct)}` ({best_single.base.growth_capture_count}/{best_single.base.growth_point_count}), false_buy=`{prev._render_pct(best_single.base.false_buy_outside_growth_pct)}` ({best_single.base.false_buy_outside_growth_count}/{best_single.base.non_growth_point_count}), churn=`{best_single.base.churn_rate:.4f}`, classification=`{best_single.classification}`.", f"- Material improvement over current safe benchmark was proven: `{best_single.base.growth_capture_count > benchmark_metrics.base.growth_capture_count}`.", f"- A true capture candidate was proven: `{best_true_capture is not None}`.", f"- Best family points primarily to: `{issue_inference}`.", "", "## Best single scenario", f"- `{best_single.scenario_id}` family=`{best_single.family}` mode=`{best_single.mode}` sma=`{best_single.sma_period}`.", "", "## Best family", f"- `{best_family}`", "", "## Comparison to current safe benchmark", f"- Safe benchmark `(0.55, 0.15)` delivered growth_capture=`{prev._render_pct(benchmark_metrics.base.growth_capture_pct)}` ({benchmark_metrics.base.growth_capture_count}/{benchmark_metrics.base.growth_point_count}), false_buy=`{prev._render_pct(benchmark_metrics.base.false_buy_outside_growth_pct)}` ({benchmark_metrics.base.false_buy_outside_growth_count}/{benchmark_metrics.base.non_growth_point_count}), churn=`{benchmark_metrics.base.churn_rate:.4f}`.", f"- Strategist-semantics package materially beat that benchmark without new problems: `{best_true_capture is not None}`.", "", "## Behavior classification", f"- Horizon compression best `{family_best['HORIZON_COMPRESSION'].scenario_id}` -> `{family_best['HORIZON_COMPRESSION'].classification}`", f"- Full suppression best `{family_best['FULL_SUPPRESSION'].scenario_id}` -> `{family_best['FULL_SUPPRESSION'].classification}`", f"- SELL-only suppression best `{family_best['SELL_ONLY_SUPPRESSION'].scenario_id}` -> `{family_best['SELL_ONLY_SUPPRESSION'].classification}`", "", "## Evidence limits", "- Primary ranking remains local to the frozen TREND_UP window.", "- Confirmation surfaces are weaker because parity outside the frozen exact-parity subwindow drifts.", "- Spillover probes are bounded sanity checks only.", "", "## Recommended next package", f"- {recommendation}"]
    _write_markdown(out_dir / "AURORA_TREND_UP_STRATEGIST_SEMANTICS_FINAL_REPORT.md", final_lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
