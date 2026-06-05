#!/usr/bin/env python3
from __future__ import annotations
from tools.system_stress_calibration.core import (
    ORACLE_MODES,
    STRESS_LABEL_POLICIES,
    CandidateSpec,
    OracleSpec,
    WalkForwardWindow,
    build_dataset_bundle,
    build_walkforward_windows,
    candidate_rank_tuple,
    collect_active_weight_keys,
    compute_oracle_score_cache,
    evaluate_candidate_walkforward,
    generate_candidate_specs,
    load_exclusion_policy,
    parse_date,
    quantize_weights,
    split_by_day,
    validate_dataset_manifest,
)
from apps.reference.config_loader import get_config

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


DEFAULT_RESEARCH_ORACLE_PRIMARY = "future_vol"
DEFAULT_RESEARCH_STRESS_LABEL_POLICY = "primary_quantile"
DEFAULT_RESEARCH_HORIZON_BARS = 4
DEFAULT_RESEARCH_PRIMARY_QUANTILE = 0.9
DEFAULT_RESEARCH_RANKING_STACK = [
    "validate_aggregate_balanced_accuracy",
    "validate_aggregate_f1",
    "validate_worst_balanced_accuracy",
    "-validate_aggregate_overblocking_proxy",
    "-validate_aggregate_state_switches_per_1000",
    "-validate_aggregate_alert_gap",
]
DISPLAY_METRICS = [
    "f1",
    "precision",
    "recall",
    "balanced_accuracy",
    "alert_rate",
    "label_rate",
    "coverage",
    "state_switches_per_1000",
    "avg_dwell_bars",
    "overblocking_proxy",
    "stress_rate",
    "extreme_rate",
]


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Contract-first system stress calibration with research and acceptance modes."
    )
    ap.add_argument(
        "--mode", choices=["research", "acceptance"], default="research")
    ap.add_argument("--out-dir", default="reports/system_stress_calibration",
                    help="Artifact output directory")
    ap.add_argument("--recorder-dir", default="data/recorder",
                    help="Recorder root dir")
    ap.add_argument("--symbols", nargs="*",
                    default=["BTCUSDT"], help="Symbols to include")
    ap.add_argument("--tf-sec", type=int, default=900,
                    help="Recorder timeframe seconds")
    ap.add_argument("--start", type=parse_date, default=None,
                    help="Start date inclusive (YYYY-MM-DD)")
    ap.add_argument("--end", type=parse_date, default=None,
                    help="End date exclusive (YYYY-MM-DD)")
    ap.add_argument("--dataset-manifest",
                    help="Frozen dataset manifest JSON. Research mode writes it if missing; acceptance mode requires it.")
    ap.add_argument("--excluded-sessions",
                    help="Optional exclusion policy JSON with exclude_dates / exclude_files.")
    ap.add_argument("--strict-dataset", action="store_true",
                    help="Fail if actual dataset diverges from the manifest.")
    ap.add_argument("--skip-bad-csvs", action="store_true",
                    help="Research-only opt-in: skip malformed recorder CSVs with explicit warnings.")
    ap.add_argument("--train-frac", type=float, default=0.7,
                    help="Legacy single-split train fraction for research mode when walk-forward is not configured.")
    ap.add_argument("--oracle-primary", choices=ORACLE_MODES,
                    default=None, help="Primary oracle mode.")
    ap.add_argument("--label-mode", dest="oracle_primary", choices=ORACLE_MODES,
                    help="Backward-compatible alias for --oracle-primary.")
    ap.add_argument("--oracle-secondary", choices=ORACLE_MODES,
                    default=None, help="Optional secondary oracle mode.")
    ap.add_argument("--forecast-horizon-bars", type=int, default=None,
                    help="Forecast horizon in bars for the oracle.")
    ap.add_argument("--horizon-bars", dest="forecast_horizon_bars", type=int,
                    help="Backward-compatible alias for --forecast-horizon-bars.")
    ap.add_argument("--stress-label-policy", choices=STRESS_LABEL_POLICIES,
                    default=None, help="How primary and secondary oracle labels are combined.")
    ap.add_argument("--primary-label-quantile", type=float, default=None,
                    help="Train-derived positive label quantile for the primary oracle.")
    ap.add_argument("--label-quantile", dest="primary_label_quantile", type=float,
                    help="Backward-compatible alias for --primary-label-quantile.")
    ap.add_argument("--secondary-label-quantile", type=float, default=None,
                    help="Optional train-derived positive label quantile for the secondary oracle.")
    ap.add_argument("--wf-train-windows", type=int, default=None,
                    help="Walk-forward train window count in unique days.")
    ap.add_argument("--wf-validate-windows", type=int, default=None,
                    help="Walk-forward validate window count in unique days.")
    ap.add_argument("--wf-test-windows", type=int, default=None,
                    help="Walk-forward test window count in unique days.")
    ap.add_argument("--wf-step-windows", type=int, default=None,
                    help="Walk-forward step size in unique days.")
    ap.add_argument("--aggregation-methods", nargs="+", choices=["weighted_vote", "k_of_n", "max"], default=[
                    "weighted_vote"], help="Aggregation methods to evaluate.")
    ap.add_argument("--search-steps", nargs="+", type=float,
                    default=None, help="Search schedule steps, e.g. 0.5 0.1 0.05.")
    ap.add_argument("--grid-step", type=float, default=None,
                    help="Backward-compatible single-step alias for --search-steps.")
    ap.add_argument("--final-rounding-step", type=float, default=None,
                    help="Optional final quantization step validated separately after search.")
    ap.add_argument("--baseline-window", type=int, default=None,
                    help="Optional override for system_stress.baseline_window during calibration.")
    ap.add_argument("--burn-in-bars", type=int, default=None,
                    help="Optional override for system_stress.burn_in_bars during calibration.")
    ap.add_argument("--top-k", type=int, default=5,
                    help="How many top candidates to retain per search stage.")
    ap.add_argument("--ranking-stack", nargs="+", default=None,
                    help="Explicit candidate ranking stack, e.g. validate_aggregate_balanced_accuracy -validate_aggregate_overblocking_proxy.")
    ap.add_argument("--accept-min-test-balanced-accuracy-lift",
                    type=float, default=None)
    ap.add_argument("--accept-min-test-f1-lift", type=float, default=None)
    ap.add_argument("--accept-max-test-state-switches-per-1000",
                    type=float, default=None)
    ap.add_argument("--accept-max-test-overblocking-proxy",
                    type=float, default=None)
    ap.add_argument("--accept-max-test-alert-rate", type=float, default=None)
    ap.add_argument("--accept-min-test-coverage", type=float, default=None)
    ap.add_argument(
        "--accept-min-worst-test-balanced-accuracy-lift", type=float, default=None)
    return ap.parse_args(argv)


def _fmt_metrics(metrics: dict[str, float]) -> dict[str, float]:
    return {key: round(float(metrics[key]), 4) for key in DISPLAY_METRICS if key in metrics}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2,
                    sort_keys=True), encoding="utf-8")


def _yaml_lines(value: Any, indent: int = 0) -> list[str]:
    prefix = "  " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, nested in value.items():
            if isinstance(nested, dict):
                lines.append(f"{prefix}{key}:")
                lines.extend(_yaml_lines(nested, indent + 1))
            else:
                lines.append(f"{prefix}{key}: {json.dumps(nested)}")
        return lines
    return [f"{prefix}{json.dumps(value)}"]


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(_yaml_lines(payload)) + "\n", encoding="utf-8")


def _candidate_from_live_config(config: Any) -> CandidateSpec:
    method = str(config.system_stress.aggregation.method)
    weights = dict(config.system_stress.aggregation.weights or {}) or None
    k = getattr(config.system_stress.aggregation, "k", None)
    return CandidateSpec(
        aggregation_method=method,  # type: ignore[arg-type]
        weights=weights,
        k=int(k) if k is not None else None,
    )


def _resolve_search_steps(args: argparse.Namespace) -> list[float]:
    if args.search_steps:
        return [float(step) for step in args.search_steps]
    if args.grid_step is not None:
        return [float(args.grid_step)]
    return [0.1]


def _resolve_oracle(args: argparse.Namespace) -> OracleSpec:
    if args.mode == "research":
        primary = args.oracle_primary or DEFAULT_RESEARCH_ORACLE_PRIMARY
        policy = args.stress_label_policy or DEFAULT_RESEARCH_STRESS_LABEL_POLICY
        horizon = int(
            args.forecast_horizon_bars or DEFAULT_RESEARCH_HORIZON_BARS)
        primary_quantile = float(
            args.primary_label_quantile or DEFAULT_RESEARCH_PRIMARY_QUANTILE)
        return OracleSpec(
            primary=primary,
            secondary=args.oracle_secondary,
            forecast_horizon_bars=horizon,
            stress_label_policy=policy,
            primary_quantile=primary_quantile,
            secondary_quantile=args.secondary_label_quantile,
        )

    missing = []
    if args.oracle_primary is None:
        missing.append("--oracle-primary")
    if args.stress_label_policy is None:
        missing.append("--stress-label-policy")
    if args.forecast_horizon_bars is None:
        missing.append("--forecast-horizon-bars")
    if args.primary_label_quantile is None:
        missing.append("--primary-label-quantile")
    if missing:
        raise ValueError(
            "Acceptance mode requires explicit oracle contract: " + ", ".join(missing))
    return OracleSpec(
        primary=args.oracle_primary,
        secondary=args.oracle_secondary,
        forecast_horizon_bars=int(args.forecast_horizon_bars),
        stress_label_policy=args.stress_label_policy,
        primary_quantile=float(args.primary_label_quantile),
        secondary_quantile=args.secondary_label_quantile,
    )


def _resolve_ranking_stack(args: argparse.Namespace) -> list[str]:
    return list(args.ranking_stack or DEFAULT_RESEARCH_RANKING_STACK)


def _resolve_windows(frame, args: argparse.Namespace) -> list[WalkForwardWindow]:
    wf_args = [
        args.wf_train_windows,
        args.wf_validate_windows,
        args.wf_test_windows,
        args.wf_step_windows,
    ]
    any_wf = any(value is not None for value in wf_args)
    all_wf = all(value is not None for value in wf_args)

    if args.mode == "acceptance":
        if not all_wf:
            raise ValueError(
                "Acceptance mode requires explicit walk-forward config: --wf-train-windows, --wf-validate-windows, --wf-test-windows, --wf-step-windows"
            )
        return build_walkforward_windows(
            frame,
            train_windows=int(args.wf_train_windows),
            validate_windows=int(args.wf_validate_windows),
            test_windows=int(args.wf_test_windows),
            step_windows=int(args.wf_step_windows),
        )

    if any_wf and not all_wf:
        raise ValueError(
            "Research mode walk-forward config must provide all four knobs together."
        )
    if all_wf:
        return build_walkforward_windows(
            frame,
            train_windows=int(args.wf_train_windows),
            validate_windows=int(args.wf_validate_windows),
            test_windows=int(args.wf_test_windows),
            step_windows=int(args.wf_step_windows),
        )

    split = split_by_day(frame, train_frac=float(args.train_frac))
    if split.test.empty:
        raise ValueError(
            "Research mode single split requires at least two unique days.")
    return [
        WalkForwardWindow(
            window_id=1,
            train_days=list(split.train_days),
            validate_days=list(split.test_days),
            test_days=list(split.test_days),
        )
    ]


def _acceptance_gates(args: argparse.Namespace) -> dict[str, float]:
    gates = {
        "accept_min_test_balanced_accuracy_lift": args.accept_min_test_balanced_accuracy_lift,
        "accept_min_test_f1_lift": args.accept_min_test_f1_lift,
        "accept_max_test_state_switches_per_1000": args.accept_max_test_state_switches_per_1000,
        "accept_max_test_overblocking_proxy": args.accept_max_test_overblocking_proxy,
        "accept_max_test_alert_rate": args.accept_max_test_alert_rate,
        "accept_min_test_coverage": args.accept_min_test_coverage,
        "accept_min_worst_test_balanced_accuracy_lift": args.accept_min_worst_test_balanced_accuracy_lift,
    }
    if args.mode == "acceptance":
        missing = [key for key, value in gates.items() if value is None]
        if missing:
            raise ValueError("Acceptance mode requires explicit acceptance gates: " +
                             ", ".join(f"--{item.replace('_', '-')}" for item in missing))
    return {key: float(value) for key, value in gates.items() if value is not None}


def _prepare_dataset(args: argparse.Namespace, out_dir: Path) -> tuple[Any, list[str]]:
    if args.mode == "acceptance":
        if not args.strict_dataset:
            raise ValueError("Acceptance mode requires --strict-dataset.")
        if not args.dataset_manifest:
            raise ValueError("Acceptance mode requires --dataset-manifest.")
        if args.skip_bad_csvs:
            raise ValueError(
                "Acceptance mode forbids --skip-bad-csvs; use an explicit exclusion policy or a frozen manifest.")

    exclusion_policy = load_exclusion_policy(
        Path(args.excluded_sessions)) if args.excluded_sessions else None
    bundle = build_dataset_bundle(
        Path(args.recorder_dir),
        start=args.start,
        end=args.end,
        symbols=args.symbols,
        tf_sec=int(args.tf_sec),
        exclusion_policy=exclusion_policy,
        skip_bad_csvs=bool(args.skip_bad_csvs),
    )
    if bundle.frame.empty:
        raise ValueError(
            "No recorder rows loaded for the requested dataset contract.")

    manifest_diffs: list[str] = []
    manifest_path = Path(
        args.dataset_manifest) if args.dataset_manifest else None
    if manifest_path and manifest_path.exists():
        expected_manifest = json.loads(
            manifest_path.read_text(encoding="utf-8"))
        manifest_diffs = validate_dataset_manifest(
            bundle.manifest, expected_manifest, strict=bool(args.strict_dataset))
    elif manifest_path and args.mode == "research":
        _write_json(manifest_path, bundle.manifest)
    elif manifest_path and args.mode == "acceptance":
        raise ValueError(
            f"Acceptance mode manifest does not exist: {manifest_path}")

    _write_json(out_dir / "dataset_manifest.json", bundle.manifest)
    return bundle, manifest_diffs


def _flatten_window_rows(stage_label: str, candidate_spec: CandidateSpec, evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window in evaluation["window_rows"]:
        for split_name in ("validate", "test"):
            record = {
                "stage": stage_label,
                "candidate_id": candidate_spec.candidate_id(),
                "aggregation_method": candidate_spec.aggregation_method,
                "k": candidate_spec.k,
                "window_id": window["window_id"],
                "split": split_name,
                "train_days": ",".join(window["train_days"]),
                "validate_days": ",".join(window["validate_days"]),
                "test_days": ",".join(window["test_days"]),
                "primary_threshold": window["thresholds"].get("primary_threshold"),
                "secondary_threshold": window["thresholds"].get("secondary_threshold"),
            }
            record.update({key: window[split_name][key]
                          for key in window[split_name] if key in DISPLAY_METRICS})
            rows.append(record)
    return rows


def _condense_evaluation(candidate_spec: CandidateSpec, evaluation: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate": candidate_spec.as_dict(),
        "validate_aggregate": evaluation["validate"]["aggregate"],
        "validate_worst": evaluation["validate"]["worst"],
        "test_aggregate": evaluation["test"]["aggregate"],
        "test_worst": evaluation["test"]["worst"],
        "ranking_tuple": evaluation["ranking_tuple"],
    }


def _compare_candidate_to_baseline(candidate_eval: dict[str, Any], baseline_eval: dict[str, Any]) -> dict[str, float]:
    candidate_test = candidate_eval["test"]["aggregate"]
    baseline_test = baseline_eval["test"]["aggregate"]
    candidate_worst = candidate_eval["test"]["worst"]
    baseline_worst = baseline_eval["test"]["worst"]
    return {
        "test_balanced_accuracy_lift": float(candidate_test["balanced_accuracy"] - baseline_test["balanced_accuracy"]),
        "test_f1_lift": float(candidate_test["f1"] - baseline_test["f1"]),
        "worst_test_balanced_accuracy_lift": float(candidate_worst["balanced_accuracy"] - baseline_worst["balanced_accuracy"]),
        "candidate_test_state_switches_per_1000": float(candidate_test["state_switches_per_1000"]),
        "candidate_test_overblocking_proxy": float(candidate_test["overblocking_proxy"]),
        "candidate_test_alert_rate": float(candidate_test["alert_rate"]),
        "candidate_test_coverage": float(candidate_test["coverage"]),
    }


def _evaluate_acceptance(candidate_eval: dict[str, Any], baseline_eval: dict[str, Any], gates: dict[str, float]) -> dict[str, Any]:
    comparison = _compare_candidate_to_baseline(candidate_eval, baseline_eval)
    reasons: list[str] = []
    if comparison["test_balanced_accuracy_lift"] < gates.get("accept_min_test_balanced_accuracy_lift", float("-inf")):
        reasons.append(
            f"test_balanced_accuracy_lift {comparison['test_balanced_accuracy_lift']:.4f} < required {gates['accept_min_test_balanced_accuracy_lift']:.4f}"
        )
    if comparison["test_f1_lift"] < gates.get("accept_min_test_f1_lift", float("-inf")):
        reasons.append(
            f"test_f1_lift {comparison['test_f1_lift']:.4f} < required {gates['accept_min_test_f1_lift']:.4f}"
        )
    if comparison["worst_test_balanced_accuracy_lift"] < gates.get("accept_min_worst_test_balanced_accuracy_lift", float("-inf")):
        reasons.append(
            f"worst_test_balanced_accuracy_lift {comparison['worst_test_balanced_accuracy_lift']:.4f} < required {gates['accept_min_worst_test_balanced_accuracy_lift']:.4f}"
        )
    if comparison["candidate_test_state_switches_per_1000"] > gates.get("accept_max_test_state_switches_per_1000", float("inf")):
        reasons.append(
            f"test_state_switches_per_1000 {comparison['candidate_test_state_switches_per_1000']:.4f} > allowed {gates['accept_max_test_state_switches_per_1000']:.4f}"
        )
    if comparison["candidate_test_overblocking_proxy"] > gates.get("accept_max_test_overblocking_proxy", float("inf")):
        reasons.append(
            f"test_overblocking_proxy {comparison['candidate_test_overblocking_proxy']:.4f} > allowed {gates['accept_max_test_overblocking_proxy']:.4f}"
        )
    if comparison["candidate_test_alert_rate"] > gates.get("accept_max_test_alert_rate", float("inf")):
        reasons.append(
            f"test_alert_rate {comparison['candidate_test_alert_rate']:.4f} > allowed {gates['accept_max_test_alert_rate']:.4f}"
        )
    if comparison["candidate_test_coverage"] < gates.get("accept_min_test_coverage", float("-inf")):
        reasons.append(
            f"test_coverage {comparison['candidate_test_coverage']:.4f} < required {gates['accept_min_test_coverage']:.4f}"
        )
    return {
        "passed": not reasons,
        "reasons": reasons,
        "comparison": comparison,
    }


def _render_report(
    *,
    out_dir: Path,
    mode: str,
    dataset_manifest: dict[str, Any],
    manifest_diffs: list[str],
    windows: list[WalkForwardWindow],
    oracle: OracleSpec,
    ranking_stack: list[str],
    search_steps: list[float],
    aggregation_methods: list[str],
    baseline_spec: CandidateSpec,
    baseline_eval: dict[str, Any],
    winner_spec: CandidateSpec,
    winner_eval: dict[str, Any],
    deploy_spec: CandidateSpec,
    deploy_eval: dict[str, Any],
    acceptance: dict[str, Any] | None,
    stage_summaries: list[dict[str, Any]],
    yaml_patch_path: Path,
) -> Path:
    lines = [
        "# System Stress Calibration Report",
        "",
        "## Executive Summary",
        "",
        f"- mode: {mode}",
        f"- dataset_fingerprint: {dataset_manifest['fingerprint']}",
        f"- walkforward_windows: {len(windows)}",
        f"- search_steps: {search_steps}",
        f"- aggregation_methods: {aggregation_methods}",
        f"- baseline_candidate: {baseline_spec.candidate_id()}",
        f"- selected_candidate: {winner_spec.candidate_id()}",
        f"- deploy_candidate: {deploy_spec.candidate_id()}",
        "",
        "## Dataset Contract",
        "",
        f"- symbols: {dataset_manifest['symbols']}",
        f"- tf_sec: {dataset_manifest['tf_sec']}",
        f"- included_files: {len(dataset_manifest['included_files'])}",
        f"- excluded_files: {len(dataset_manifest['excluded_files'])}",
        f"- row_count: {dataset_manifest['row_count']}",
        f"- day_count: {dataset_manifest['day_count']}",
        f"- manifest_diffs: {manifest_diffs if manifest_diffs else 'none'}",
        "",
        "## Oracle Contract",
        "",
        f"- primary: {oracle.primary}",
        f"- secondary: {oracle.secondary}",
        f"- forecast_horizon_bars: {oracle.forecast_horizon_bars}",
        f"- stress_label_policy: {oracle.stress_label_policy}",
        f"- primary_quantile: {oracle.primary_quantile}",
        f"- secondary_quantile: {oracle.secondary_quantile if oracle.secondary_quantile is not None else oracle.primary_quantile}",
        "",
        "## Walk-Forward Scheme",
        "",
    ]
    for window in windows:
        lines.append(
            f"- window {window.window_id}: train={window.train_days} validate={window.validate_days} test={window.test_days}"
        )
    lines.extend(
        [
            "",
            "## Ranking Stack",
            "",
            f"- {ranking_stack}",
            "",
            "## Baseline vs Candidate",
            "",
            f"- baseline validate aggregate: {_fmt_metrics(baseline_eval['validate']['aggregate'])}",
            f"- baseline test aggregate: {_fmt_metrics(baseline_eval['test']['aggregate'])}",
            f"- candidate validate aggregate: {_fmt_metrics(winner_eval['validate']['aggregate'])}",
            f"- candidate test aggregate: {_fmt_metrics(winner_eval['test']['aggregate'])}",
            f"- deploy validate aggregate: {_fmt_metrics(deploy_eval['validate']['aggregate'])}",
            f"- deploy test aggregate: {_fmt_metrics(deploy_eval['test']['aggregate'])}",
            "",
            "## Stage Summaries",
            "",
        ]
    )
    for stage in stage_summaries:
        lines.append(f"### {stage['stage_label']}")
        lines.append("")
        for item in stage["top_candidates"]:
            lines.append(
                f"- {item['candidate']['candidate_id']}: validate={_fmt_metrics(item['validate_aggregate'])} test={_fmt_metrics(item['test_aggregate'])}"
            )
        lines.append("")
    lines.extend(
        [
            "## YAML Patch",
            "",
            f"- {yaml_patch_path.as_posix()}",
            "",
            "## Testnet Rollout Recommendation",
            "",
        ]
    )
    if acceptance is None or not acceptance.get("passed", False):
        lines.extend(
            [
                "- verdict: do not promote to blocking policy on testnet yet",
                "- recommendation: keep system_stress enabled only for research or shadow-style analysis, or at most testnet attenuate after separate manual review",
            ]
        )
    else:
        lines.extend(
            [
                "- verdict: candidate cleared acceptance gates for testnet rollout",
                "- recommendation: hybrid_live_data_testnet_exec with phased rollout off -> attenuate -> block",
            ]
        )
    if acceptance is not None:
        lines.extend(
            [
                "",
                "## Acceptance Gates",
                "",
                f"- passed: {acceptance['passed']}",
                f"- reasons: {acceptance['reasons'] if acceptance['reasons'] else 'none'}",
                f"- comparison: {acceptance['comparison']}",
            ]
        )
    report_path = out_dir / "report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def _execute(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    oracle = _resolve_oracle(args)
    ranking_stack = _resolve_ranking_stack(args)
    search_steps = _resolve_search_steps(args)
    acceptance_gates = _acceptance_gates(args)
    bundle, manifest_diffs = _prepare_dataset(args, out_dir)
    windows = _resolve_windows(bundle.frame, args)

    base_cfg = get_config()
    base_cfg_dict = base_cfg.model_dump()
    weight_keys = collect_active_weight_keys(base_cfg)
    baseline_spec = _candidate_from_live_config(base_cfg)
    score_cache = compute_oracle_score_cache(bundle.frame, oracle=oracle)

    baseline_eval = evaluate_candidate_walkforward(
        bundle.frame,
        windows=windows,
        score_cache=score_cache,
        oracle=oracle,
        base_cfg_dict=base_cfg_dict,
        candidate=baseline_spec,
        tf_sec=int(args.tf_sec),
        baseline_window=args.baseline_window,
        burn_in_bars=args.burn_in_bars,
        ranking_stack=ranking_stack,
    )

    stage_summaries: list[dict[str, Any]] = []
    metrics_rows: list[dict[str, Any]] = _flatten_window_rows(
        "baseline", baseline_spec, baseline_eval)
    winner_spec = baseline_spec
    winner_eval = baseline_eval

    for step in search_steps:
        stage_label = f"step_{step:g}"
        evaluations: list[tuple[CandidateSpec, dict[str, Any]]] = []
        for candidate_spec in generate_candidate_specs(
            weight_keys,
            aggregation_methods=args.aggregation_methods,
            step=float(step),
        ):
            evaluation = evaluate_candidate_walkforward(
                bundle.frame,
                windows=windows,
                score_cache=score_cache,
                oracle=oracle,
                base_cfg_dict=base_cfg_dict,
                candidate=candidate_spec,
                tf_sec=int(args.tf_sec),
                baseline_window=args.baseline_window,
                burn_in_bars=args.burn_in_bars,
                ranking_stack=ranking_stack,
            )
            evaluations.append((candidate_spec, evaluation))
            metrics_rows.extend(_flatten_window_rows(
                stage_label, candidate_spec, evaluation))

        evaluations.sort(
            key=lambda item: candidate_rank_tuple(
                item[1]["ranking_metrics"], ranking_stack),
            reverse=True,
        )
        winner_spec, winner_eval = evaluations[0]
        stage_summaries.append(
            {
                "stage_label": stage_label,
                "step": float(step),
                "candidate_count": len(evaluations),
                "top_candidates": [
                    _condense_evaluation(candidate_spec, evaluation)
                    for candidate_spec, evaluation in evaluations[: int(args.top_k)]
                ],
            }
        )

    deploy_spec = winner_spec
    deploy_eval = winner_eval
    rounded_eval = None
    if args.final_rounding_step is not None and winner_spec.aggregation_method == "weighted_vote" and winner_spec.weights is not None:
        rounded_spec = CandidateSpec(
            aggregation_method="weighted_vote",
            weights=quantize_weights(
                winner_spec.weights, step=float(args.final_rounding_step)),
        )
        rounded_eval = evaluate_candidate_walkforward(
            bundle.frame,
            windows=windows,
            score_cache=score_cache,
            oracle=oracle,
            base_cfg_dict=base_cfg_dict,
            candidate=rounded_spec,
            tf_sec=int(args.tf_sec),
            baseline_window=args.baseline_window,
            burn_in_bars=args.burn_in_bars,
            ranking_stack=ranking_stack,
        )
        metrics_rows.extend(_flatten_window_rows(
            f"rounded_{args.final_rounding_step:g}", rounded_spec, rounded_eval))
        deploy_spec = rounded_spec
        deploy_eval = rounded_eval

    acceptance = None
    if args.mode == "acceptance":
        acceptance = _evaluate_acceptance(
            deploy_eval, baseline_eval, acceptance_gates)

    if metrics_rows:
        import pandas as pd

        pd.DataFrame(metrics_rows).to_csv(
            out_dir / "walkforward_metrics.csv", index=False)

    yaml_patch_path = out_dir / "yaml_patch_snippet.yaml"
    _write_yaml(yaml_patch_path, deploy_spec.to_yaml_fragment())

    candidate_summary = {
        "mode": args.mode,
        "dataset_manifest_path": str((out_dir / "dataset_manifest.json").as_posix()),
        "report_path": str((out_dir / "report.md").as_posix()),
        "yaml_patch_path": str(yaml_patch_path.as_posix()),
        "search_steps": search_steps,
        "ranking_stack": ranking_stack,
        "oracle": oracle.as_dict(),
        "baseline_candidate": baseline_spec.as_dict(),
        "selected_candidate": winner_spec.as_dict(),
        "deploy_candidate": deploy_spec.as_dict(),
        "acceptance": acceptance,
    }
    _write_json(out_dir / "candidate_summary.json", candidate_summary)

    candidate_metrics = {
        "baseline": {
            "candidate": baseline_spec.as_dict(),
            "validate": baseline_eval["validate"],
            "test": baseline_eval["test"],
        },
        "selected_candidate": {
            "candidate": winner_spec.as_dict(),
            "validate": winner_eval["validate"],
            "test": winner_eval["test"],
        },
        "deploy_candidate": {
            "candidate": deploy_spec.as_dict(),
            "validate": deploy_eval["validate"],
            "test": deploy_eval["test"],
        },
        "rounded_candidate": {
            "candidate": deploy_spec.as_dict(),
            "validate": deploy_eval["validate"],
            "test": deploy_eval["test"],
        } if rounded_eval is not None else None,
        "stage_summaries": stage_summaries,
        "manifest_diffs": manifest_diffs,
    }
    _write_json(out_dir / "candidate_metrics.json", candidate_metrics)

    report_path = _render_report(
        out_dir=out_dir,
        mode=args.mode,
        dataset_manifest=bundle.manifest,
        manifest_diffs=manifest_diffs,
        windows=windows,
        oracle=oracle,
        ranking_stack=ranking_stack,
        search_steps=search_steps,
        aggregation_methods=list(args.aggregation_methods),
        baseline_spec=baseline_spec,
        baseline_eval=baseline_eval,
        winner_spec=winner_spec,
        winner_eval=winner_eval,
        deploy_spec=deploy_spec,
        deploy_eval=deploy_eval,
        acceptance=acceptance,
        stage_summaries=stage_summaries,
        yaml_patch_path=yaml_patch_path,
    )

    print("\n" + "=" * 80)
    print("System stress contract-first calibration")
    print(f"mode={args.mode} out_dir={out_dir.as_posix()}")
    print(f"dataset_fingerprint={bundle.manifest['fingerprint']}")
    print(
        f"windows={len(windows)} search_steps={search_steps} aggregation_methods={list(args.aggregation_methods)}")
    print(
        f"baseline test aggregate: {_fmt_metrics(baseline_eval['test']['aggregate'])}")
    print(
        f"selected test aggregate: {_fmt_metrics(winner_eval['test']['aggregate'])}")
    if rounded_eval is not None:
        print(
            f"rounded deploy test aggregate: {_fmt_metrics(deploy_eval['test']['aggregate'])}")
    if acceptance is not None:
        print(f"acceptance_passed={acceptance['passed']}")
        if acceptance["reasons"]:
            for reason in acceptance["reasons"]:
                print(f"  acceptance_blocker: {reason}")
    print(
        f"artifacts: report={report_path.as_posix()} yaml={yaml_patch_path.as_posix()}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return _execute(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
