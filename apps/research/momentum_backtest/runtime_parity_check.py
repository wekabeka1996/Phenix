"""
Runtime Parity Check: Production vs R&D Signal Validation

Compares production bot runtime log with R&D pipeline to ensure
signal logic alignment before parameter optimization.

Usage:
    python -m apps.research.momentum_backtest.runtime_parity_check \
        --runtime-log path/to/runtime_log.csv \
        --features path/to/features.csv \
        --params-json path/to/params.json
"""

import pandas as pd
import numpy as np
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any


def compare_runtime_vs_research(
    runtime_log_path: str,
    features_path: str,
    params: dict,
    max_rows: int = 50_000,
) -> dict:
    """
    Compare production runtime signal vs R&D pipeline.
    
    Args:
        runtime_log_path: Path to prod runtime log (CSV/JSONL)
            Required columns: ts, score_prod, signal_prod
            Optional: tfi_phi, tob_phi, etc. for detailed debugging
        features_path: Path to R&D features CSV
        params: Strategy parameters dict with:
            w_tfi, w_tob, w_bs, w_bl, w_macro, threshold
        max_rows: Maximum rows to process (for speed)
        
    Returns:
        Dict with:
            - match_rate_signal: Fraction of matching signals
            - n_rows: Total rows compared
            - n_disagree: Count of disagreements
            - examples_prod1_rnd0: List of cases where prod=1, rnd=0
            - examples_prod0_rnd1: List of cases where prod=0, rnd=1
            - score_correlation: Pearson correlation of scores
            - score_mae: Mean absolute error of scores
    """
    
    print("="*60)
    print("RUNTIME PARITY CHECK")
    print("="*60)
    
    # Load runtime log
    print(f"\n1. Loading runtime log: {runtime_log_path}")
    runtime_log_path = Path(runtime_log_path)
    
    if not runtime_log_path.exists():
        raise FileNotFoundError(f"Runtime log not found: {runtime_log_path}")
    
    # Support CSV and JSONL
    if runtime_log_path.suffix == '.csv':
        runtime_df = pd.read_csv(runtime_log_path, nrows=max_rows)
    elif runtime_log_path.suffix in ['.jsonl', '.json']:
        runtime_df = pd.read_json(runtime_log_path, lines=True, nrows=max_rows)
    else:
        raise ValueError(f"Unsupported file format: {runtime_log_path.suffix}")
    
    # Validate required columns
    required_cols = ['ts', 'signal_prod']
    missing_cols = [col for col in required_cols if col not in runtime_df.columns]
    if missing_cols:
        raise ValueError(f"Runtime log missing required columns: {missing_cols}")
    
    # Parse timestamp
    runtime_df['ts'] = pd.to_datetime(runtime_df['ts'])
    
    print(f"   Loaded {len(runtime_df)} rows")
    print(f"   Time range: {runtime_df['ts'].min()} to {runtime_df['ts'].max()}")
    print(f"   Columns: {runtime_df.columns.tolist()}")
    
    # Load R&D features
    print(f"\n2. Loading R&D features: {features_path}")
    features_df = pd.read_csv(features_path)
    features_df['ts'] = pd.to_datetime(features_df['ts'])
    
    print(f"   Loaded {len(features_df)} rows")
    print(f"   Time range: {features_df['ts'].min()} to {features_df['ts'].max()}")
    
    # Find common time range
    common_start = max(runtime_df['ts'].min(), features_df['ts'].min())
    common_end = min(runtime_df['ts'].max(), features_df['ts'].max())
    
    print(f"\n3. Finding common time range...")
    print(f"   Common range: {common_start} to {common_end}")
    
    # Filter both to common range
    runtime_df = runtime_df[(runtime_df['ts'] >= common_start) & (runtime_df['ts'] <= common_end)].copy()
    features_df = features_df[(features_df['ts'] >= common_start) & (features_df['ts'] <= common_end)].copy()
    
    print(f"   Runtime rows in range: {len(runtime_df)}")
    print(f"   Features rows in range: {len(features_df)}")
    
    # Compute R&D score
    print(f"\n4. Computing R&D score...")
    
    # Verify phi-features exist
    phi_features = ['tfi_phi', 'tob_phi', 'ema_bias_short_phi', 'ema_bias_long_phi', 'macro_phi']
    missing_phi = [f for f in phi_features if f not in features_df.columns]
    if missing_phi:
        raise ValueError(f"Features missing phi columns: {missing_phi}")
    
    # Extract weights
    w_tfi = params.get('w_tfi', 0.0)
    w_tob = params.get('w_tob', 0.0)
    w_bs = params.get('w_bs', 0.0)
    w_bl = params.get('w_bl', 0.0)
    w_macro = params.get('w_macro', 0.0)
    threshold = params.get('threshold', 0.1)
    
    print(f"   Params: w_tfi={w_tfi:.3f}, w_tob={w_tob:.3f}, w_bs={w_bs:.3f}, w_bl={w_bl:.3f}, w_macro={w_macro:.3f}")
    print(f"   Threshold: {threshold:.3f}")
    
    # Additive score (PROD PARITY)
    features_df['score_rnd'] = (
        w_tfi * features_df['tfi_phi'] +
        w_tob * features_df['tob_phi'] +
        w_bs * features_df['ema_bias_short_phi'] +
        w_bl * features_df['ema_bias_long_phi'] +
        w_macro * features_df['macro_phi']
    )
    
    # Signal (long-only for v1)
    features_df['signal_rnd'] = (features_df['score_rnd'] > threshold).astype(int)
    
    print(f"   R&D score computed: mean={features_df['score_rnd'].mean():.3f}, std={features_df['score_rnd'].std():.3f}")
    print(f"   R&D signals: {features_df['signal_rnd'].sum()} / {len(features_df)} ({features_df['signal_rnd'].mean():.1%})")
    
    # Join on timestamp
    print(f"\n5. Joining runtime and R&D by timestamp...")
    
    # Merge on ts (should be 1:1 if same data source)
    merged = pd.merge(
        runtime_df[['ts', 'signal_prod', 'score_prod'] if 'score_prod' in runtime_df.columns else ['ts', 'signal_prod']],
        features_df[['ts', 'score_rnd', 'signal_rnd']],
        on='ts',
        how='inner'
    )
    
    print(f"   Merged rows: {len(merged)}")
    
    if len(merged) == 0:
        print("\n⚠️  WARNING: No matching timestamps between runtime and R&D!")
        print("   Check that both datasets cover the same time period.")
        return {
            "match_rate_signal": 0.0,
            "n_rows": 0,
            "n_disagree": 0,
            "examples_prod1_rnd0": [],
            "examples_prod0_rnd1": [],
            "score_correlation": 0.0,
            "score_mae": 0.0,
        }
    
    # Calculate metrics
    print(f"\n6. Calculating parity metrics...")
    
    n_rows = len(merged)
    signal_match = (merged['signal_prod'] == merged['signal_rnd'])
    n_agree = signal_match.sum()
    n_disagree = (~signal_match).sum()
    match_rate = n_agree / n_rows if n_rows > 0 else 0.0
    
    print(f"   Total rows: {n_rows}")
    print(f"   Agreements: {n_agree}")
    print(f"   Disagreements: {n_disagree}")
    print(f"   Match rate: {match_rate:.1%}")
    
    # Score metrics (if score_prod available)
    score_corr = 0.0
    score_mae = 0.0
    if 'score_prod' in merged.columns:
        score_corr = merged['score_prod'].corr(merged['score_rnd'])
        score_mae = (merged['score_prod'] - merged['score_rnd']).abs().mean()
        print(f"   Score correlation: {score_corr:.3f}")
        print(f"   Score MAE: {score_mae:.4f}")
    
    # Examples of disagreements
    prod1_rnd0 = merged[(merged['signal_prod'] == 1) & (merged['signal_rnd'] == 0)]
    prod0_rnd1 = merged[(merged['signal_prod'] == 0) & (merged['signal_rnd'] == 1)]
    
    print(f"\n7. Disagreement breakdown...")
    print(f"   Prod=1, R&D=0: {len(prod1_rnd0)} cases")
    print(f"   Prod=0, R&D=1: {len(prod0_rnd1)} cases")
    
    # Collect examples
    examples_prod1_rnd0 = prod1_rnd0.head(10).to_dict('records') if len(prod1_rnd0) > 0 else []
    examples_prod0_rnd1 = prod0_rnd1.head(10).to_dict('records') if len(prod0_rnd1) > 0 else []
    
    # Print examples
    if len(prod1_rnd0) > 0:
        print(f"\n   Examples where Prod=1 but R&D=0 (first 5):")
        for i, row in enumerate(prod1_rnd0.head(5).itertuples(), 1):
            score_prod_val = f"{row.score_prod:.4f}" if 'score_prod' in merged.columns else "N/A"
            print(f"      {i}. ts={row.ts}, score_prod={score_prod_val}, score_rnd={row.score_rnd:.4f}")
    
    if len(prod0_rnd1) > 0:
        print(f"\n   Examples where Prod=0 but R&D=1 (first 5):")
        for i, row in enumerate(prod0_rnd1.head(5).itertuples(), 1):
            score_prod_val = f"{row.score_prod:.4f}" if 'score_prod' in merged.columns else "N/A"
            print(f"      {i}. ts={row.ts}, score_prod={score_prod_val}, score_rnd={row.score_rnd:.4f}")
    
    return {
        "match_rate_signal": float(match_rate),
        "n_rows": int(n_rows),
        "n_agree": int(n_agree),
        "n_disagree": int(n_disagree),
        "examples_prod1_rnd0": examples_prod1_rnd0,
        "examples_prod0_rnd1": examples_prod0_rnd1,
        "score_correlation": float(score_corr),
        "score_mae": float(score_mae),
    }


def main():
    """CLI entrypoint for runtime parity check"""
    parser = argparse.ArgumentParser(
        description="Compare production runtime log vs R&D signal pipeline"
    )
    
    parser.add_argument(
        '--runtime-log',
        type=str,
        required=True,
        help='Path to runtime log (CSV or JSONL) with ts, signal_prod columns'
    )
    
    parser.add_argument(
        '--features',
        type=str,
        required=True,
        help='Path to R&D features CSV'
    )
    
    parser.add_argument(
        '--params-json',
        type=str,
        required=True,
        help='Path to params JSON file with w_tfi, w_tob, w_bs, w_bl, w_macro, threshold'
    )
    
    parser.add_argument(
        '--max-rows',
        type=int,
        default=50000,
        help='Maximum rows to process (default: 50000)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='parity_report.json',
        help='Output file for parity report (default: parity_report.json)'
    )
    
    args = parser.parse_args()
    
    # Load params
    with open(args.params_json, 'r') as f:
        params = json.load(f)
    
    # Run comparison
    result = compare_runtime_vs_research(
        runtime_log_path=args.runtime_log,
        features_path=args.features,
        params=params,
        max_rows=args.max_rows
    )
    
    # Save report
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n{'='*60}")
    print("PARITY CHECK COMPLETE")
    print(f"{'='*60}")
    print(f"Match rate: {result['match_rate_signal']:.1%}")
    print(f"Report saved to: {args.output}")
    
    # Assessment
    if result['match_rate_signal'] >= 0.95:
        print("\n✅ PARITY ACHIEVED (≥95%)")
        print("   R&D pipeline matches production signal logic.")
        print("   Ready for Optuna v2 optimization.")
    elif result['match_rate_signal'] >= 0.90:
        print("\n⚠️  PARITY MARGINAL (90-95%)")
        print("   Close but review disagreement examples before Optuna.")
    else:
        print("\n❌ PARITY FAILED (<90%)")
        print("   Investigate discrepancies before optimization!")
        print("   Review examples and adjust features/score formula.")


if __name__ == "__main__":
    main()
