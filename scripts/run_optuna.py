#!/usr/bin/env python3
"""
Optuna Hyperparameter Optimization for Aurora Strategy
=======================================================

Entry point for Aurora optimization: legacy flat Optuna OR hierarchical 3-stage pipeline.

Usage (legacy flat — unchanged):
    python scripts/run_optuna.py --trials 50
    python scripts/run_optuna.py --trials 10 --study-name "aurora_test"

Usage (hierarchical — NEW):
    python scripts/run_optuna.py --stage full --start 2024-01-01 --end 2025-12-31
    python scripts/run_optuna.py --stage 0 --start 2024-01-01 --end 2025-10-01 --trials 30
    python scripts/run_optuna.py --stage 1 --start 2024-01-01 --end 2025-10-01 --stage0-best-path runs/optuna/best_regime_patch.yaml
    python scripts/run_optuna.py --stage 2 --start 2024-01-01 --end 2025-10-01 --candidate-path runs/optuna/candidate.yaml
"""

import os
import tempfile
# HACK-PERF: Force WAL_DIR to temp to avoid reading GBs of production logs on startup
if "WAL_DIR" not in os.environ:
    # Use a fresh WAL dir per optimization run to avoid lock/contention spillover
    # from prior runs and to keep append/read costs bounded.
    wal_sim_dir = tempfile.mkdtemp(prefix="phenix_optuna_wal_")
    os.environ["WAL_DIR"] = wal_sim_dir
    print(f"🚀 [run_optuna] Forced WAL_DIR={wal_sim_dir} (Performance Optimization)")

if "TRADE_INTENT_REJECT_WAL_MODE" not in os.environ:
    os.environ["TRADE_INTENT_REJECT_WAL_MODE"] = "memory"
    print("🚀 [run_optuna] TRADE_INTENT_REJECT_WAL_MODE=memory")

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

LOG = logging.getLogger("OptunaMain")

ARTIFACTS_DIR = project_root / "runs" / "optuna"


def _save_yaml(path: Path, data: dict) -> None:
    """Write dict to YAML file."""
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
    LOG.info(f"💾 Saved: {path}")


def _load_yaml(path: Path) -> dict:
    """Load YAML file."""
    import yaml
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Legacy flat Optuna (unchanged behavior)
# ---------------------------------------------------------------------------

def run_legacy(args: argparse.Namespace) -> None:
    """Run legacy flat Optuna optimization (pre-hierarchical)."""
    from backtest_engine.optuna_runner import OptunaRunner

    config_dir = args.config_dir
    optuna_config_path = args.optuna_config or (config_dir / "optuna_config.yaml")

    LOG.info("=" * 60)
    LOG.info("🔬 OPTUNA OPTIMIZATION — AURORA STRATEGY (LEGACY FLAT)")
    LOG.info("=" * 60)
    LOG.info(f"Config dir: {config_dir}")
    LOG.info(f"Optuna config: {optuna_config_path}")
    LOG.info(f"Trials: {args.trials}")

    runner = OptunaRunner(
        optuna_config_path=optuna_config_path,
        config_dir=config_dir,
    )

    if args.trials != 50:
        runner.study_cfg.n_trials = args.trials

    if args.study_name:
        runner.study_cfg.name = args.study_name

    study = runner.run()

    print("\n" + "=" * 60)
    print("🏆 OPTIMIZATION COMPLETE")
    print("=" * 60)
    print(f"Best trial: #{study.best_trial.number}")
    print(f"Best Calmar: {study.best_value:.4f}")
    print(f"Best params:")
    for k, v in study.best_params.items():
        print(f"  {k}: {v}")
    print("=" * 60)

    best_params_path = ARTIFACTS_DIR / f"{runner.study_cfg.name}_best.yaml"
    _save_yaml(best_params_path, {
        "best_trial": study.best_trial.number,
        "best_value": study.best_value,
        "best_params": study.best_params,
    })


# ---------------------------------------------------------------------------
# Hierarchical optimization (Stage 0 / 1 / 2 / full)
# ---------------------------------------------------------------------------

def run_hierarchical(args: argparse.Namespace) -> None:
    """Route to the appropriate hierarchical stage."""
    from optimization.optimizer import AuroraOptimizer, DateRange, compute_train_holdout_split, _build_overlay

    config_dir = args.config_dir.parent  # --config-dir points to aurora/, we need config/
    stage = args.stage

    LOG.info("=" * 60)
    LOG.info(f"🔬 HIERARCHICAL OPTIMIZATION — STAGE: {stage.upper()}")
    LOG.info("=" * 60)

    # Date ranges
    train_range = None
    holdout_range = None

    if stage == "full":
        if not args.start or not args.end:
            LOG.error("--start and --end required for --stage full")
            sys.exit(1)
        holdout_months = args.holdout_months or 3
        train_range, holdout_range = compute_train_holdout_split(
            args.start, args.end, holdout_months,
        )
        LOG.info(f"Train: {train_range.start} → {train_range.end}")
        LOG.info(f"Holdout: {holdout_range.start} → {holdout_range.end}")
    elif args.start and args.end:
        train_range = DateRange(args.start, args.end)
        if args.holdout_start and args.holdout_end:
            holdout_range = DateRange(args.holdout_start, args.holdout_end)

    optimizer = AuroraOptimizer(
        config_dir=config_dir,
        train_range=train_range,
        holdout_range=holdout_range,
    )

    if args.storage:
        optimizer.optimizer_cfg.setdefault("optuna", {})["storage"] = args.storage

    # Override trial counts
    if args.trials:
        if stage in ("0", "full"):
            optimizer.optimizer_cfg.setdefault("stage0", {})["n_trials"] = args.trials
        if stage in ("1", "full"):
            optimizer.optimizer_cfg.setdefault("stage1", {})["n_trials"] = args.trials

    if args.seed is not None:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)

    # --- Stage routing ---

    if stage == "0":
        result = optimizer.run_stage0()
        _print_stage0_result(result)
        # Save artifact
        _save_yaml(ARTIFACTS_DIR / "best_regime_patch.yaml", {
            "best_stability_score": result.best_stability_score,
            "best_basis_tf_sec": result.best_basis_tf_sec,
            "best_params": result.best_params,
            "grid_scores": {str(k): v for k, v in result.all_grid_scores.items()},
        })

    elif stage == "1":
        # Load frozen regime config
        regime_config = _load_regime_config(args)
        result = optimizer.run_stage1(regime_config)
        _print_stage1_result(result)
        _save_yaml(ARTIFACTS_DIR / "best_strategy_patch.yaml", {
            "best_alpha_score": result.best_alpha_score,
            "best_sharpe": result.best_sharpe,
            "best_params": result.best_params,
        })

    elif stage == "2":
        # Load candidate (regime + strategy merged)
        candidate = _load_candidate_config(args)
        s1_sharpe = candidate.pop("_stage1_sharpe", 0.0)
        result = optimizer.run_stage2(candidate, stage1_sharpe=s1_sharpe)
        _print_stage2_result(result)
        _save_yaml(ARTIFACTS_DIR / "stage2_report.yaml", {
            "passed": result.passed,
            "median_sharpe": result.median_sharpe,
            "sharpe_degradation": result.sharpe_degradation,
            "bootstrap_pnl_positive_pct": result.bootstrap_pnl_positive_pct,
            "failed_folds": result.failed_folds,
            "reasons": result.reasons,
            "fold_details": [
                {
                    "fold_id": f.fold_id,
                    "test_sharpe": f.test_sharpe,
                    "test_mdd_pct": f.test_mdd_pct,
                    "test_trades": f.test_trades,
                    "hard_violation": f.hard_violation,
                    "bootstrap_pnl_positive_pct": f.bootstrap_pnl_positive_pct,
                    "stress_sharpe_median": f.stress_sharpe_median,
                    "stress_runs": f.stress_runs,
                }
                for f in result.fold_results
            ],
        })

    elif stage == "full":
        result = optimizer.run_full_pipeline(full_start=args.start, full_end=args.end)
        _print_pipeline_result(result)
        if result.stage0:
            _save_yaml(ARTIFACTS_DIR / "best_regime_patch.yaml", {
                "best_stability_score": result.stage0.best_stability_score,
                "best_basis_tf_sec": result.stage0.best_basis_tf_sec,
                "best_params": result.stage0.best_params,
                "grid_scores": {str(k): v for k, v in result.stage0.all_grid_scores.items()},
            })
        if result.stage1:
            _save_yaml(ARTIFACTS_DIR / "best_strategy_patch.yaml", {
                "best_alpha_score": result.stage1.best_alpha_score,
                "best_sharpe": result.stage1.best_sharpe,
                "best_params": result.stage1.best_params,
            })
        if result.stage2:
            _save_yaml(ARTIFACTS_DIR / "stage2_report.yaml", {
                "passed": result.stage2.passed,
                "median_sharpe": result.stage2.median_sharpe,
                "sharpe_degradation": result.stage2.sharpe_degradation,
                "bootstrap_pnl_positive_pct": result.stage2.bootstrap_pnl_positive_pct,
                "failed_folds": result.stage2.failed_folds,
                "reasons": result.stage2.reasons,
                "fold_results": [
                    {
                        "fold_id": f.fold_id,
                        "test_sharpe": f.test_sharpe,
                        "test_mdd_pct": f.test_mdd_pct,
                        "test_trades": f.test_trades,
                        "hard_violation": f.hard_violation,
                        "bootstrap_pnl_positive_pct": f.bootstrap_pnl_positive_pct,
                        "stress_sharpe_median": f.stress_sharpe_median,
                        "stress_runs": f.stress_runs,
                    }
                    for f in result.stage2.fold_results
                ],
            })
        # Save production patch if passed
        if result.production_ready:
            _save_yaml(ARTIFACTS_DIR / "production_patch.yaml", result.final_config)
        # Save full report
        _save_yaml(ARTIFACTS_DIR / "pipeline_report.yaml", {
            "production_ready": result.production_ready,
            "stage0": {
                "best_stability_score": result.stage0.best_stability_score if result.stage0 else None,
                "best_basis_tf_sec": result.stage0.best_basis_tf_sec if result.stage0 else None,
            },
            "stage1": {
                "best_alpha_score": result.stage1.best_alpha_score if result.stage1 else None,
                "best_sharpe": result.stage1.best_sharpe if result.stage1 else None,
            },
            "stage2": {
                "passed": result.stage2.passed if result.stage2 else None,
                "median_sharpe": result.stage2.median_sharpe if result.stage2 else None,
            },
            "holdout": {
                "passed": result.holdout.passed if result.holdout else None,
                "sharpe": result.holdout.sharpe if result.holdout else None,
                "reason": result.holdout.reason if result.holdout else None,
            },
        })
    else:
        LOG.error(f"Unknown stage: {stage}")
        sys.exit(1)


def _load_regime_config(args: argparse.Namespace) -> dict:
    """Load frozen regime config for Stage 1."""
    if args.stage0_best_path:
        data = _load_yaml(Path(args.stage0_best_path))
        from optimization.optimizer import _build_overlay
        overlay = _build_overlay(data.get("best_params", {}))
        overlay["basis_tf_sec"] = data.get("best_basis_tf_sec", 300)
        return overlay
    # Fallback: check default location
    default_path = ARTIFACTS_DIR / "best_regime_patch.yaml"
    if default_path.exists():
        LOG.info(f"Loading regime config from default: {default_path}")
        return _load_regime_config(argparse.Namespace(stage0_best_path=str(default_path)))
    LOG.error("Stage 1 requires regime config: --stage0-best-path or runs/optuna/best_regime_patch.yaml")
    sys.exit(1)


def _load_candidate_config(args: argparse.Namespace) -> dict:
    """Load candidate config (merged regime + strategy) for Stage 2."""
    if args.candidate_path:
        return _load_yaml(Path(args.candidate_path))
    # Auto-merge from stage0 + stage1 artifacts
    regime_path = ARTIFACTS_DIR / "best_regime_patch.yaml"
    strategy_path = ARTIFACTS_DIR / "best_strategy_patch.yaml"
    if regime_path.exists() and strategy_path.exists():
        LOG.info("Auto-merging candidate from best_regime_patch.yaml + best_strategy_patch.yaml")
        from optimization.optimizer import _build_overlay, _merge_config
        regime_data = _load_yaml(regime_path)
        strategy_data = _load_yaml(strategy_path)
        regime_overlay = _build_overlay(regime_data.get("best_params", {}))
        regime_overlay["basis_tf_sec"] = regime_data.get("best_basis_tf_sec", 300)
        strategy_overlay = _build_overlay(strategy_data.get("best_params", {}))
        candidate = _merge_config(regime_overlay, strategy_overlay)
        candidate["_stage1_sharpe"] = strategy_data.get("best_sharpe", 0.0)
        return candidate
    LOG.error("Stage 2 requires --candidate-path or both best_regime_patch.yaml + best_strategy_patch.yaml")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _print_stage0_result(r) -> None:
    print("\n" + "=" * 60)
    print("🔬 STAGE 0: REGIME CALIBRATION — RESULTS")
    print("=" * 60)
    print(f"Best stability_score: {r.best_stability_score:.4f}")
    print(f"Best basis_tf_sec:    {r.best_basis_tf_sec}")
    print(f"Grid scores:")
    for tf, score in sorted(r.all_grid_scores.items()):
        print(f"  tf={tf}s → {score:.4f}")
    print(f"Best params:")
    for k, v in r.best_params.items():
        print(f"  {k}: {v}")
    print("=" * 60)


def _print_stage1_result(r) -> None:
    print("\n" + "=" * 60)
    print("📈 STAGE 1: ALPHA SEARCH — RESULTS")
    print("=" * 60)
    print(f"Best alpha_score: {r.best_alpha_score:.4f}")
    print(f"Best Sharpe:      {r.best_sharpe:.4f}")
    print(f"Best params:")
    for k, v in r.best_params.items():
        print(f"  {k}: {v}")
    print("=" * 60)


def _print_stage2_result(r) -> None:
    print("\n" + "=" * 60)
    verdict = "✅ PASSED" if r.passed else "❌ FAILED"
    print(f"🛡️ STAGE 2: ROBUSTNESS — {verdict}")
    print("=" * 60)
    print(f"Median Sharpe:     {r.median_sharpe:.4f}")
    print(f"Degradation:       {r.sharpe_degradation:.4f}")
    print(f"Bootstrap PnL+:    {r.bootstrap_pnl_positive_pct:.1%}")
    print(f"Failed folds:      {r.failed_folds}/{len(r.fold_results)}")
    if r.reasons:
        print(f"Reasons: {' | '.join(r.reasons)}")
    for f in r.fold_results:
        status = "❌ HARD" if f.hard_violation else "✅"
        print(f"  Fold {f.fold_id}: {status} sharpe={f.test_sharpe:.3f} mdd={f.test_mdd_pct:.1f}% "
              f"trades={f.test_trades} bs_pnl+={f.bootstrap_pnl_positive_pct:.0%} "
              f"stress_sharpe={f.stress_sharpe_median:.3f}")
    print("=" * 60)


def _print_pipeline_result(r) -> None:
    print("\n" + "=" * 60)
    verdict = "✅ PRODUCTION READY" if r.production_ready else "❌ NOT READY"
    print(f"🏁 FULL PIPELINE — {verdict}")
    print("=" * 60)
    if r.stage0:
        print(f"Stage 0: stability={r.stage0.best_stability_score:.4f}, tf={r.stage0.best_basis_tf_sec}")
    if r.stage1:
        print(f"Stage 1: alpha={r.stage1.best_alpha_score:.4f}, sharpe={r.stage1.best_sharpe:.4f}")
    if r.stage2:
        s2v = "✅" if r.stage2.passed else "❌"
        print(f"Stage 2: {s2v} median_sharpe={r.stage2.median_sharpe:.4f}, "
              f"folds_failed={r.stage2.failed_folds}")
    if r.holdout:
        hv = "✅" if r.holdout.passed else "❌"
        print(f"Holdout: {hv} sharpe={r.holdout.sharpe:.4f}, reason={r.holdout.reason}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aurora optimization: legacy flat OR hierarchical 3-stage pipeline"
    )
    parser.add_argument(
        "--stage",
        type=str,
        choices=["0", "1", "2", "full"],
        default=None,
        help="Hierarchical stage: 0=Regime, 1=Alpha, 2=Robustness, full=S0→S1→S2→Holdout"
    )
    parser.add_argument("--trials", "-n", type=int, default=50, help="Number of optimization trials")
    parser.add_argument(
        "--config-dir", type=Path, default=project_root / "config" / "aurora",
        help="Path to Aurora config directory",
    )
    parser.add_argument("--optuna-config", type=Path, default=None, help="Path to optuna_config.yaml")
    parser.add_argument("--study-name", type=str, default=None, help="Override study name")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    # Hierarchical-specific arguments
    parser.add_argument("--start", type=str, default=None, help="Train start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="Train end date (YYYY-MM-DD)")
    parser.add_argument("--holdout-start", type=str, default=None, help="Holdout start (YYYY-MM-DD)")
    parser.add_argument("--holdout-end", type=str, default=None, help="Holdout end (YYYY-MM-DD)")
    parser.add_argument("--holdout-months", type=int, default=None, help="Holdout reserve months (for --stage full)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument(
        "--stage0-best-path", type=str, default=None,
        help="Path to Stage 0 result YAML (for --stage 1)",
    )
    parser.add_argument(
        "--candidate-path", type=str, default=None,
        help="Path to merged candidate YAML (for --stage 2)",
    )
    parser.add_argument("--storage", type=str, default=None, help="Optuna storage URI")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    if not args.verbose:
        logging.getLogger("OptunaMain").setLevel(logging.INFO)
        logging.getLogger("optimization").setLevel(logging.INFO)
        logging.getLogger("optuna").setLevel(logging.INFO)
        logging.getLogger("apps.reference").setLevel(logging.ERROR)
        logging.getLogger("backtest_engine").setLevel(logging.WARNING)
        logging.getLogger("vfoundation").setLevel(logging.WARNING)
        logging.getLogger("event_chain").setLevel(logging.WARNING)

    if args.stage:
        run_hierarchical(args)
    else:
        run_legacy(args)


if __name__ == "__main__":
    main()
