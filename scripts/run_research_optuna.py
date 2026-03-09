"""
scripts/run_research_optuna.py — CLI entry point for Optuna Research Domain.

Runs selective weight optimization via SelectiveOptimizer.
All results are persisted in SQLite (resumable — run with same --study-name
to continue a previous study with more trials).

Examples:
    # Tune BTC weights only, all symbols as backtest universe
    python scripts/run_research_optuna.py \\
        --symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT 1000PEPEUSDT \\
        --search-space btc_weights \\
        --start 2024-01-01 --end 2025-10-01 \\
        --n-trials 100 --objective calmar \\
        --study-name "btc_weights_march_2026" \\
        --output runs/research/btc_weights_march_2026.yaml

    # Tune BTC weights AND global signal weights together
    python scripts/run_research_optuna.py \\
        --symbols BTCUSDT \\
        --search-space btc_weights global_signal_weights \\
        --start 2024-06-01 --end 2024-12-31 \\
        --n-trials 50 --objective sharpe \\
        --study-name "btc_global_joint"

    # List all available search space groups
    python scripts/run_research_optuna.py --list-groups
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as script
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from optimization.research.selective_optimizer import (
    SelectiveOptimizer,
    ResearchGates,
    ResearchObjectiveMode,
    ResearchStudyConfig,
)
from optimization.research.weight_registry import describe_group, list_groups


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Optuna Research Domain — selective Aurora weight optimizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--list-groups",
        action="store_true",
        help="List all available search space groups and exit",
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        metavar="SYMBOL",
        default=["BTCUSDT"],
        help="Symbols to include in backtest universe (default: BTCUSDT)",
    )
    parser.add_argument(
        "--search-space",
        nargs="+",
        metavar="GROUP",
        dest="search_space",
        default=["btc_weights"],
        help="Search space groups to tune (default: btc_weights). Use --list-groups to see all.",
    )
    parser.add_argument(
        "--start",
        metavar="YYYY-MM-DD",
        required=False,
        default="2024-01-01",
        help="Backtest start date (default: 2024-01-01)",
    )
    parser.add_argument(
        "--end",
        metavar="YYYY-MM-DD",
        required=False,
        default="2025-10-01",
        help="Backtest end date (default: 2025-10-01)",
    )
    parser.add_argument(
        "--n-trials",
        type=int,
        default=100,
        metavar="N",
        help="Number of Optuna trials (default: 100)",
    )
    parser.add_argument(
        "--objective",
        choices=[m.value for m in ResearchObjectiveMode],
        default=ResearchObjectiveMode.CALMAR.value,
        help="Optimization objective (default: calmar)",
    )
    parser.add_argument(
        "--study-name",
        default="research_study",
        metavar="NAME",
        help="Optuna study name (used for SQLite persistence). Same name resumes. (default: research_study)",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help="Path to export best config YAML overlay (default: runs/research/<study-name>.yaml)",
    )
    parser.add_argument(
        "--config-dir",
        metavar="DIR",
        default="config/aurora",
        help="Path to aurora config directory (default: config/aurora)",
    )
    parser.add_argument(
        "--db",
        metavar="SQLITE_URL",
        default=None,
        help="SQLite URL for Optuna storage (default: sqlite:///runs/optuna/research.db)",
    )
    parser.add_argument(
        "--min-trades",
        type=int,
        default=5,
        metavar="N",
        help="Gate: minimum trades to accept a trial (default: 5)",
    )
    parser.add_argument(
        "--max-dd",
        type=float,
        default=40.0,
        metavar="PCT",
        help="Gate: maximum allowed drawdown %% (default: 40.0)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Optuna TPE sampler seed (default: 42)",
    )
    parser.add_argument(
        "--n-jobs",
        type=int,
        default=1,
        help="Parallel trials (default: 1). Set >1 for parallel optimization.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("run_research_optuna")

    # --list-groups
    if args.list_groups:
        groups = list_groups()
        print("Available search space groups:")
        for g in groups:
            meta = describe_group(g)
            desc = meta.get("description", "(no description)")
            print(f"  {g:<30} {desc}")
        sys.exit(0)

    # Resolve paths
    config_dir = Path(args.config_dir).resolve()
    if not config_dir.exists():
        log.error(f"config-dir not found: {config_dir}")
        sys.exit(1)

    output_path = Path(
        args.output or f"runs/research/{args.study_name}.yaml"
    )
    db = args.db or "sqlite:///runs/optuna/research.db"

    study_config = ResearchStudyConfig(
        name=args.study_name,
        n_trials=args.n_trials,
        n_jobs=args.n_jobs,
        storage=db,
        seed=args.seed,
    )
    gates = ResearchGates(
        min_trades=args.min_trades,
        max_dd_pct=args.max_dd,
    )

    log.info(
        f"Starting Research Optimizer:\n"
        f"  symbols      = {args.symbols}\n"
        f"  search-space = {args.search_space}\n"
        f"  date_range   = {args.start} .. {args.end}\n"
        f"  objective    = {args.objective}\n"
        f"  n_trials     = {args.n_trials}\n"
        f"  study_name   = {args.study_name}\n"
        f"  config_dir   = {config_dir}\n"
        f"  db           = {db}"
    )

    optimizer = SelectiveOptimizer(
        config_dir=config_dir,
        symbols=args.symbols,
        search_space_names=args.search_space,
        date_range=(args.start, args.end),
        study_config=study_config,
        gates=gates,
        objective=ResearchObjectiveMode(args.objective),
    )

    study = optimizer.run()

    # Print results
    print("\n" + "=" * 60)
    print(f"Study: {args.study_name}")
    print(f"Completed trials: {len(study.trials)}")
    print(f"Best value ({args.objective}): {study.best_value:.4f}")
    print("Best params:")
    for k, v in study.best_params.items():
        print(f"  {k:<55} = {v}")
    print("=" * 60)

    # Export best config YAML
    optimizer.export_best_config(study, output_path)
    print(f"\nBest config saved: {output_path}")


if __name__ == "__main__":
    main()
