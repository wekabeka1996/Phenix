"""
Aurora Validation Runner - February 2024
========================================
Test optimal configs on unseen data to verify no overfitting
"""
import sys
import json
import yaml
from pathlib import Path
import pandas as pd

sys.path.insert(0, ".")

from apps.research.aurora_optuna.backtest_engine_aurora import BacktestEngineAurora
from apps.research.aurora_optuna.features_aurora import build_aurora_features
from apps.research.aurora_optuna.config import get_data_path, FEATURES_DATASET_TEMPLATE_3M, FEATURES_DATASET_TEMPLATE_5M

# Load optimal config
with open("config/aurora_optimal_production_v1.yaml", "r") as f:
    optimal_config = yaml.safe_load(f)

SYMBOLS_CONFIG = {
    'SOLUSDT': {
        'timeframe': '3m',
        'bar_seconds': 180,
        'params': optimal_config['aurora_optimal']['SOLUSDT'],
        'expected_pnl': 201.60,
        'source': 'Phase 2'
    },
    'ETHUSDT': {
        'timeframe': '5m',
        'bar_seconds': 300,
        'params': optimal_config['aurora_optimal']['ETHUSDT'],
        'expected_pnl': 105.87,
        'source': 'DEEP'
    },
    'DOGEUSDT': {
        'timeframe': '3m',
        'bar_seconds': 180,
        'params': optimal_config['aurora_optimal']['DOGEUSDT'],
        'expected_pnl': 85.89,
        'source': 'DEEP'
    },
    'XRPUSDT': {
        'timeframe': '3m',
        'bar_seconds': 180,
        'params': optimal_config['aurora_optimal']['XRPUSDT'],
        'expected_pnl': 28.96,
        'source': 'Phase 2'
    },
}

def convert_yaml_to_params(yaml_params):
    """Convert YAML config format to backtest params format."""
    features = yaml_params['features']
    weights = yaml_params['weights']
    decision = yaml_params['decision']
    exit_params = yaml_params['exit']
    
    params = {
        # EMA
        'ema_period_short': features['ema']['period_short'],
        'ema_period_long': features['ema']['period_long'],
        
        # Volume
        'volume_window_sec': features['volume']['window_sec'],
        'volume_sma_length': features['volume']['sma_length'],
        'volume_cap_max': features['volume']['cap_max'],
        
        # Liquidity
        'liquidity_depth_half': features['liquidity']['depth_half'],
        'liquidity_kappa_min': features['liquidity']['kappa_min'],
        
        # OBI/TFI
        'obi_window_sec': features['obi']['window_sec'],
        'tfi_window_sec': features['tfi']['window_sec'],
        
        # Volatility
        'volatility_window_sec': features['volatility']['window_sec'],
        'volatility_sma_length': features['volatility']['sma_length'],
        'volatility_cap_max': features['volatility']['cap_max'],
        
        # Depth Imbalance
        'depth_imbalance_smoothing': features['depth_imbalance']['use_smoothing'],
        
        # Delta Price
        'delta_price_spike_filter_ms': features['delta_price']['spike_filter_ms'],
        
        # Macro Sync
        'macro_sync_window': features['macro_sync']['window'],
        
        # Weights
        'weight_ema': weights['ema'],
        'weight_volume': weights['volume'],
        'weight_macro': weights['macro'],
        'weight_liquidity': weights['liquidity'],
        'weight_obi': weights['obi'],
        'weight_tfi': weights['tfi'],
        'weight_volatility': weights['volatility'],
        'weight_depth_imbalance': weights['depth_imbalance'],
        'weight_delta_price': weights['delta_price'],
        
        # Decision
        'signal_threshold': decision['signal_threshold'],
        'max_risk_score': decision['max_risk_score'],
        'allowed_regimes': decision['allowed_regimes'],
        
        # Exit
        'sl_pct': exit_params['sl_pct'],
        'max_hold_sec': exit_params['max_hold_sec'],
    }
    
    return params

def load_data(symbol, year, month, timeframe):
    """Load pre-built feature data."""
    template = FEATURES_DATASET_TEMPLATE_3M if timeframe == '3m' else FEATURES_DATASET_TEMPLATE_5M
    feat_path = get_data_path(template, symbol, year, month)
    
    if not feat_path.exists():
        print(f"⚠️  Feature file not found: {feat_path}")
        print(f"   Run: python apps/research/aurora_optuna/build_features.py --symbol {symbol} --year {year} --month {month} --timeframe {timeframe}")
        return None, None
    
    print(f"Loading {symbol} from {feat_path}...")
    df = pd.read_csv(feat_path)
    df['ts'] = pd.to_datetime(df['ts'])
    
    # Load BTC data for macro sync
    btc_df = None
    if symbol != "BTCUSDT":
        btc_path = get_data_path(template, "BTCUSDT", year, month)
        if btc_path.exists():
            btc_df = pd.read_csv(btc_path)
            btc_df['ts'] = pd.to_datetime(btc_df['ts'])
            
            col_name = 'close_180s' if timeframe == '3m' else 'close_300s'
            if col_name in btc_df.columns:
                btc_df['btc_close_1s'] = btc_df[col_name]
    
    return df, btc_df

def validate_symbol(symbol, year='2024', month='02'):
    """Run validation backtest for a symbol."""
    config = SYMBOLS_CONFIG[symbol]
    timeframe = config['timeframe']
    bar_seconds = config['bar_seconds']
    
    print(f"\n{'='*80}")
    print(f"📊 VALIDATION: {symbol} ({timeframe}) — {month}/{year}")
    print(f"{'='*80}")
    print(f"Training: January 2024 → {config['source']}")
    print(f"Expected PnL: ${config['expected_pnl']:.2f}")
    print(f"{'='*80}\n")
    
    # Load data
    df, btc_df = load_data(symbol, year, month, timeframe)
    if df is None:
        return None
    
    # Convert YAML params to backtest format
    params = convert_yaml_to_params(config['params'])
    
    # Build features & run backtest
    df_features = build_aurora_features(df, btc_df, params, bar_seconds=bar_seconds)
    engine = BacktestEngineAurora(df_features, params)
    metrics = engine.run()
    
    # Calculate validation ratio
    validation_ratio = (metrics['total_pnl'] / config['expected_pnl']) * 100 if config['expected_pnl'] != 0 else 0
    
    print(f"\n{'='*80}")
    print(f"✅ RESULTS: {symbol}")
    print(f"{'='*80}")
    print(f"  Training (Jan):    ${config['expected_pnl']:.2f}")
    print(f"  Validation (Feb):  ${metrics['total_pnl']:.2f}")
    print(f"  Ratio:             {validation_ratio:.1f}%")
    print(f"  Trades:            {metrics['trades']}")
    print(f"  Win Rate:          {metrics['win_rate']:.1%}")
    print(f"  Max DD:            ${metrics['max_dd']:.2f}")
    print(f"  Calmar:            {metrics['calmar']:.2f}")
    print(f"{'='*80}\n")
    
    return {
        'symbol': symbol,
        'training_pnl': config['expected_pnl'],
        'validation_pnl': metrics['total_pnl'],
        'ratio_pct': validation_ratio,
        'metrics': metrics,
        'params': params
    }

import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", default="02", help="Month to validate (default: 02)")
    args = parser.parse_args()
    
    month_name = "February" if args.month == "02" else "January" if args.month == "01" else args.month
    
    print(f"\n🎯 AURORA VALIDATION — {month_name} 2024")
    print("="*80)
    if args.month == "02":
        print("Testing optimal configs on unseen data")
        print("Expected: 70-130% of training performance")
    else:
        print(f"Verifying performance on {month_name} data")
    print("="*80)
    
    results = {}
    for symbol in ['SOLUSDT', 'ETHUSDT', 'DOGEUSDT', 'XRPUSDT']:
        result = validate_symbol(symbol, month=args.month)
        if result:
            results[symbol] = result
    
    # Summary
    if results:
        print("\n" + "="*80)
        print("📈 PORTFOLIO SUMMARY")
        print("="*80)
        
        total_training = sum(r['training_pnl'] for r in results.values())
        total_validation = sum(r['validation_pnl'] for r in results.values())
        portfolio_ratio = (total_validation / total_training) * 100
        
        print(f"\n{'Symbol':<12} {'Expected':<12} {'Actual':<12} {'Ratio':<10} {'Status'}")
        print("-" * 80)
        
        for symbol, r in results.items():
            ratio = r['ratio_pct']
            if args.month == "01":
                # For Jan, we expect ~100% match
                status = "✅ MATCH" if 95 <= ratio <= 105 else "⚠️ DIFF"
            else:
                # For Feb, we expect 70-130%
                status = "✅ PASS" if 70 <= ratio <= 130 else "⚠️ WARN" if 50 <= ratio < 70 else "❌ FAIL"
                
            print(f"{symbol:<12} ${r['training_pnl']:<11.2f} ${r['validation_pnl']:<11.2f} {ratio:<9.1f}% {status}")
        
        print("-" * 80)
        print(f"{'TOTAL':<12} ${total_training:<11.2f} ${total_validation:<11.2f} {portfolio_ratio:<9.1f}%")
        
        # Interpretation
        print("\n" + "="*80)
        print("🔍 INTERPRETATION")
        print("="*80)
        
        if args.month == "01":
            if 95 <= portfolio_ratio <= 105:
                print("✅ SANITY CHECK PASSED. Logic matches training results.")
            else:
                print("⚠️ SANITY CHECK FAILED. Discrepancy between training and validation logic.")
        else:
            if 70 <= portfolio_ratio <= 130:
                print("✅ VALIDATION PASSED! Parameters are robust.")
            elif 50 <= portfolio_ratio < 70:
                print("⚠️  PARTIAL SUCCESS. Some overfitting detected.")
            else:
                print("❌ VALIDATION FAILED. Significant overfitting.")
        
        # Save results
        with open(f"validation_{args.month}_2024_results.json", "w") as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Results saved: validation_{args.month}_2024_results.json")
        print("="*80 + "\n")

if __name__ == "__main__":
    main()
