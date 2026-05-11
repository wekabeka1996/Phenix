#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from optimization.research.proxy_runner import ResearchHarnessConfig, ResearchHarnessRunner, build_strategy_proxy_spec
from optimization.research.provenance import ResearchTrialRequest
from scripts.diagnostics.run_single_backtest import _load_overlay_yaml


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run a strict-config-compatible research proxy backtest")
    parser.add_argument("--config-dir", default="config/aurora", help="Config directory to load")
    parser.add_argument("--strategy-id", default="aurora", help="Strategy id to assign to tradable symbols")
    parser.add_argument("--label", default="research_proxy", help="Human-readable proxy label")
    parser.add_argument("--trading-symbols", nargs="+", required=True, help="Tradable symbols for the proxy run")
    parser.add_argument("--context-symbols", nargs="*", default=None, help="Tracked-only context symbols")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--balance", type=float, default=1000.0, help="Initial balance USDT")
    parser.add_argument("--overlay-yaml", default=None, help="Optional YAML file with config overlay")
    parser.add_argument("--trial-id", default=None, help="Optional stable trial identifier for provenance manifests")
    parser.add_argument("--arm-id", default=None, help="Optional experiment arm id for provenance manifests")
    parser.add_argument(
        "--trial-params-json",
        default=None,
        help="Optional JSON object with requested trial parameters for provenance preflight",
    )
    parser.add_argument(
        "--expected-paths-json",
        default=None,
        help="Optional JSON array of expected changed YAML dot-paths for provenance preflight",
    )
    parser.add_argument("--parent-anchor", default=None, help="Optional parent anchor label, e.g. v1")
    parser.add_argument(
        "--anchor-overlay-yaml",
        default=None,
        help="Optional anchor overlay YAML used for effective-delta comparison during preflight",
    )
    parser.add_argument(
        "--fail-on-scoring-fallback",
        action="store_true",
        help="Treat any quadratic fallback as a hard-invalid run verdict",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    overlay = {}
    if args.overlay_yaml:
        overlay = _load_overlay_yaml(args.overlay_yaml)

    anchor_overlay = None
    if args.anchor_overlay_yaml:
        anchor_overlay = _load_overlay_yaml(args.anchor_overlay_yaml)

    overlay.setdefault("trading", {}).setdefault("backtest", {})["initial_balance"] = float(args.balance)

    proxy = build_strategy_proxy_spec(
        label=args.label,
        strategy_id=args.strategy_id,
        tradable_symbols=list(args.trading_symbols),
        context_symbols=list(args.context_symbols or []),
    )
    runner = ResearchHarnessRunner(
        config=ResearchHarnessConfig(
            config_dir=Path(args.config_dir),
            proxy=proxy,
            fail_on_scoring_fallback=bool(args.fail_on_scoring_fallback),
        )
    )

    trial_request = None
    if args.trial_id or args.arm_id or args.trial_params_json or args.expected_paths_json:
        if not args.trial_id or not args.arm_id:
            print("ERROR: --trial-id and --arm-id are required when trial provenance args are used")
            return 1
        try:
            trial_params = json.loads(args.trial_params_json) if args.trial_params_json else {}
            expected_paths = json.loads(args.expected_paths_json) if args.expected_paths_json else []
        except json.JSONDecodeError as exc:
            print(f"ERROR: Failed to parse trial provenance JSON: {exc}")
            return 1
        if not isinstance(trial_params, dict):
            print("ERROR: --trial-params-json must decode to a JSON object")
            return 1
        if not isinstance(expected_paths, list):
            print("ERROR: --expected-paths-json must decode to a JSON array")
            return 1
        trial_request = ResearchTrialRequest(
            trial_id=str(args.trial_id),
            arm_id=str(args.arm_id),
            trial_params_json=trial_params,
            expected_changed_paths=[str(item) for item in expected_paths],
            parent_anchor=(str(args.parent_anchor) if args.parent_anchor else None),
            anchor_overrides=anchor_overlay,
        )

    metrics, stage_result = runner.run_stage1(
        overlay,
        start_date=args.start,
        end_date=args.end,
        trial_request=trial_request,
    )
    report = stage_result.raw_report if isinstance(stage_result.raw_report, dict) else {}
    run_id = report.get("run_id") if isinstance(report, dict) else None

    print("=" * 60)
    print(f"  RESEARCH PROXY BACKTEST | label={args.label}")
    print(f"  tradable_symbols : {proxy.tradable_symbols}")
    print(f"  context_symbols  : {proxy.context_symbols}")
    print(f"  tracked_symbols  : {proxy.tracked_symbols}")
    print(f"  period           : {args.start} -> {args.end}")
    print(f"  fail_on_fallback : {bool(args.fail_on_scoring_fallback)}")
    print("=" * 60)

    if not stage_result.success:
        print(f"ERROR: {stage_result.error}")
        if run_id:
            print(f"run_id: {run_id}")
        return 1

    telemetry = stage_result.scoring_telemetry or {}
    proxy_universe = stage_result.proxy_universe or {}
    search_provenance = stage_result.search_provenance or {}
    print(f"run_id                : {run_id}")
    print(f"roi_pct               : {getattr(metrics, 'roi_pct', None)}")
    print(f"max_drawdown_pct      : {getattr(metrics, 'max_drawdown_pct', None)}")
    print(f"total_trades          : {getattr(metrics, 'total_trades', None)}")
    print(f"sharpe_ratio          : {getattr(metrics, 'sharpe_ratio', None)}")
    print(f"quadratic_selected    : {telemetry.get('quadratic_engine_selected_count')}")
    print(f"quadratic_fallbacks   : {telemetry.get('quadratic_fallback_count')}")
    print(f"fallback_also_failed  : {telemetry.get('fallback_also_failed_count')}")
    print(f"engines_observed      : {telemetry.get('engine_names_observed')}")
    print(f"proxy_assignments     : {proxy_universe.get('strategy_assignments')}")
    print(f"proxy_tracked_symbols : {proxy_universe.get('tracked_symbols')}")
    if search_provenance:
        print(f"trial_id              : {search_provenance.get('trial_id')}")
        print(f"arm_id                : {search_provenance.get('arm_id')}")
        print(f"overlay_hash          : {search_provenance.get('overlay_hash')}")
        print(f"effective_config_hash : {search_provenance.get('effective_config_hash')}")
        print(f"strategy_slice_hash   : {search_provenance.get('effective_strategy_slice_hash')}")
        print(f"preflight_passed      : {search_provenance.get('preflight_passed')}")
        print(f"rejection_reason      : {search_provenance.get('rejection_reason')}")
        print(f"trial_manifest        : {stage_result.preflight_manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())