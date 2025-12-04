"""
Inverse Symmetry Comparison Tool

Runs all 3 strategy modes on BNB March 2024 with BASE_CONFIG:
- base: Standard logic
- score_flip: Inverted signal (1 - phi)
- side_flip: Inverted side (short instead of long)
"""

import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, ".")

from apps.research.momentum_backtest.config import BASE_CONFIG
from apps.research.momentum_backtest.backtest_engine_v2 import BacktestEngineV2

def run_mode_comparison():
    """Run all 3 modes and compare results."""
    
    print("="*80)
    print("INVERSE SYMMETRY MODE COMPARISON")
    print("="*80)
    
    # Load BNB March 2024 features
    features_path = "apps/research/momentum_backtest/data/BNBUSDT-features-2024-03.csv"
    print(f"\nLoading features from {features_path}...")
    
    if not Path(features_path).exists():
        print(f"ERROR: Features file not found at {features_path}")
        return
    
    df = pd.read_csv(features_path)
    df['ts'] = pd.to_datetime(df['ts'])
    
    print(f"Loaded {len(df)} rows")
    print(f"Date range: {df['ts'].min()} to {df['ts'].max()}")
    
    # Run all 3 modes
    modes = ['base', 'score_flip', 'side_flip']
    results = []
    
    for mode in modes:
        print(f"\n{'='*80}")
        print(f"Running mode: {mode.upper()}")
        print(f"{'='*80}")
        
        # Create config for this mode
        config = BASE_CONFIG.copy()
        config['strategy_mode'] = mode
        
        # Run backtest
        engine = BacktestEngineV2(df, config)
        metrics = engine.run(debug=False)
        
        # Extract key metrics
        result = {
            'mode': mode,
            'trades': metrics.get('total_trades', 0),
            'pnl_usd': metrics.get('total_pnl_usd', 0.0),
            'max_dd_pct': metrics.get('max_drawdown_pct', 0.0),
            'win_rate': metrics.get('win_rate', 0.0),
            'calmar': metrics.get('calmar', 0.0),
            'sharpe': metrics.get('sharpe', 0.0),
        }
        results.append(result)
        
        print(f"\nResults for {mode}:")
        print(f"  Trades: {result['trades']}")
        print(f"  PnL: ${result['pnl_usd']:.2f}")
        print(f"  Max DD: {result['max_dd_pct']:.2f}%")
        print(f"  Win Rate: {result['win_rate']:.1%}")
        print(f"  Calmar: {result['calmar']:.3f}")
    
    # Print comparison table
    print(f"\n{'='*80}")
    print("COMPARISON TABLE")
    print(f"{'='*80}")
    print(f"{'MODE':<12} {'TRADES':>8} {'PNL_USD':>12} {'MAX_DD_%':>10} {'WIN_RATE':>10} {'CALMAR':>10}")
    print("-"*80)
    
    for r in results:
        print(f"{r['mode']:<12} {r['trades']:>8} {r['pnl_usd']:>12.2f} {r['max_dd_pct']:>10.2f} {r['win_rate']:>10.1%} {r['calmar']:>10.3f}")
    
    print(f"{'='*80}")
    
    # Analysis
    print("\nANALYSIS:")
    best_pnl = max(results, key=lambda x: x['pnl_usd'])
    print(f"✅ Best PnL: {best_pnl['mode']} (${best_pnl['pnl_usd']:.2f})")
    
    best_calmar = max(results, key=lambda x: x['calmar'])
    print(f"✅ Best Calmar: {best_calmar['mode']} ({best_calmar['calmar']:.3f})")
    
    # Save results
    df_results = pd.DataFrame(results)
    output_path = "apps/research/momentum_backtest/data/inverse_symmetry_results.csv"
    df_results.to_csv(output_path, index=False)
    print(f"\n✅ Results saved to {output_path}")
    
    return results

if __name__ == "__main__":
    run_mode_comparison()
