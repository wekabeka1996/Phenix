"""
CLI entry point for R&D pipeline
Usage: python -m apps.research.momentum_backtest.cli optuna --n-trials 50
"""

import argparse
import sys
import pandas as pd
from pathlib import Path

from apps.research.momentum_backtest.optuna_runner import run_optuna_study
from apps.research.momentum_backtest.config import get_processed_file_path, FEATURES_DATASET_TEMPLATE


def load_features(filepath: str = None) -> pd.DataFrame:
    """Load features dataset"""
    if filepath is None:
        filepath = get_processed_file_path(FEATURES_DATASET_TEMPLATE)
    
    print(f"Loading features from: {filepath}")
    df = pd.read_csv(filepath)
    df['ts'] = pd.to_datetime(df['ts'])
    
    print(f"Loaded: {len(df):,} rows")
    print(f"Date range: {df['ts'].min()} to {df['ts'].max()}")
    print(f"Columns: {df.columns.tolist()}")
    
    return df


def cmd_optuna(args):
    """Run Optuna optimization"""
    print("\n" + "="*60)
    print("R&D PIPELINE - OPTUNA OPTIMIZATION")
    print("="*60 + "\n")
    
    # Load data
    df_features = load_features(args.features_path)
    
    # Run optimization
    study = run_optuna_study(
        df_features,
        n_trials=args.n_trials,
        storage_url=args.storage
    )
    
    print("\n✅ Optimization complete!")
    
    # Save best params to file if requested
    if args.output:
        import json
        output_path = Path(args.output)
        
        best_params = study.best_trial.params
        best_metrics = {
            "score": study.best_trial.value,
            "total_trades": study.best_trial.user_attrs.get("total_trades"),
            "calmar": study.best_trial.user_attrs.get("calmar"),
            "max_dd_pct": study.best_trial.user_attrs.get("max_dd_pct"),
            "pnl_usd": study.best_trial.user_attrs.get("pnl_usd"),
            "win_rate": study.best_trial.user_attrs.get("win_rate"),
        }
        
        result = {
            "best_params": best_params,
            "best_metrics": best_metrics,
        }
        
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\n📝 Best parameters saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="R&D Pipeline CLI for Momentum/Scalping Strategy"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Optuna command
    optuna_parser = subparsers.add_parser('optuna', help='Run Optuna optimization')
    optuna_parser.add_argument(
        '--n-trials',
        type=int,
        default=50,
        help='Number of optimization trials (default: 50)'
    )
    optuna_parser.add_argument(
        '--features-path',
        type=str,
        default=None,
        help='Path to features CSV (default: auto-detect)'
    )
    optuna_parser.add_argument(
        '--storage',
        type=str,
        default=None,
        help='Optuna storage URL (e.g., sqlite:///optuna.db)'
    )
    optuna_parser.add_argument(
        '--output',
        type=str,
        default='best_params.json',
        help='Output file for best parameters (default: best_params.json)'
    )
    
    args = parser.parse_args()
    
    if args.command == 'optuna':
        cmd_optuna(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
