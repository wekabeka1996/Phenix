#!/usr/bin/env python3
"""
Deep Analysis of Feature Logs and Signal Scoring.

This script analyzes:
1. Distribution of signal scores with different weights
2. How many signals cross threshold with each config
3. Impact of delta_price on signal direction
"""

import json
from decimal import Decimal
from pathlib import Path
from collections import defaultdict
import statistics


def load_features(log_path: Path):
    """Load feature log."""
    features = []
    with open(log_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    features.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return features


def calc_score(features: dict, weights: dict) -> Decimal:
    """Calculate signal score."""
    score = Decimal("0")
    price = Decimal(str(features.get("price", "1")))
    
    for feat_name, weight in weights.items():
        raw = features.get(feat_name, "0")
        try:
            value = Decimal(str(raw))
        except Exception:
            value = Decimal("0")
        
        # Special handling for delta_price
        if feat_name == "delta_price" and price > 0:
            dp_cap_pct = Decimal("0.02")
            dp_pct = value / price
            if dp_pct > dp_cap_pct:
                dp_pct = dp_cap_pct
            elif dp_pct < -dp_cap_pct:
                dp_pct = -dp_cap_pct
            value = dp_pct / dp_cap_pct  # [-1, 1]
        
        score += value * Decimal(str(weight))
    
    return score


def analyze_symbol(symbol: str, logs_dir: str = "logs/features"):
    """Analyze signal distribution for a symbol."""
    log_path = Path(logs_dir) / f"{symbol}.log"
    if not log_path.exists():
        print(f"Log not found: {log_path}")
        return
    
    features_list = load_features(log_path)
    print(f"\n{'='*70}")
    print(f"  ANALYSIS: {symbol} ({len(features_list)} samples)")
    print(f"{'='*70}")
    
    # Current config weights
    current_weights = {
        "obi": 0.10,
        "tfi": 0.10,
        "delta_price": 0.05,
        "ema_bias": 0.15,
        "volume_spike": 0.10,
        "volatility_state": 0.10,
        "depth_imbalance": 0.10,
        "macro_sync": 0.10,
        "large_trade_imbalance": 0.10,
        "liquidity_kappa": 0.05,
    }
    
    # Proposed config weights (from SHORT_TREND_ANALYSIS_AND_PROPOSALS.md)
    proposed_weights = current_weights.copy()
    proposed_weights["obi"] = 0.03
    proposed_weights["delta_price"] = 0.15
    
    # Calculate scores
    current_scores = []
    proposed_scores = []
    
    for feat in features_list:
        current_scores.append(float(calc_score(feat, current_weights)))
        proposed_scores.append(float(calc_score(feat, proposed_weights)))
    
    # Statistics
    print(f"\n📊 Signal Score Distribution:")
    print(f"\n   CURRENT CONFIG (OBI=0.10, delta_price=0.05):")
    print(f"      Mean:   {statistics.mean(current_scores):+.4f}")
    print(f"      StdDev: {statistics.stdev(current_scores):.4f}")
    print(f"      Min:    {min(current_scores):+.4f}")
    print(f"      Max:    {max(current_scores):+.4f}")
    
    print(f"\n   PROPOSED CONFIG (OBI=0.03, delta_price=0.15):")
    print(f"      Mean:   {statistics.mean(proposed_scores):+.4f}")
    print(f"      StdDev: {statistics.stdev(proposed_scores):.4f}")
    print(f"      Min:    {min(proposed_scores):+.4f}")
    print(f"      Max:    {max(proposed_scores):+.4f}")
    
    # Threshold analysis
    print(f"\n📈 Threshold Crossing Analysis:")
    thresholds = [0.05, 0.08, 0.10, 0.15, 0.20]
    
    for th in thresholds:
        curr_long = sum(1 for s in current_scores if s >= th)
        curr_short = sum(1 for s in current_scores if s <= -th)
        prop_long = sum(1 for s in proposed_scores if s >= th)
        prop_short = sum(1 for s in proposed_scores if s <= -th)
        
        print(f"\n   Threshold = {th}:")
        print(f"      CURRENT:  Long: {curr_long:5d}, Short: {curr_short:5d}, Total: {curr_long + curr_short:5d}")
        print(f"      PROPOSED: Long: {prop_long:5d}, Short: {prop_short:5d}, Total: {prop_long + prop_short:5d}")
    
    # Delta price impact analysis
    print(f"\n🔍 Delta Price Analysis:")
    
    # Find cases where delta_price is strongly negative
    crash_cases = []
    for i, feat in enumerate(features_list):
        price = float(feat.get("price", 1))
        dp = float(feat.get("delta_price", 0))
        if price > 0:
            dp_pct = dp / price
            if dp_pct < -0.0035:  # Flash crash threshold
                crash_cases.append({
                    "index": i,
                    "price": price,
                    "dp": dp,
                    "dp_pct": dp_pct,
                    "obi": float(feat.get("obi", 0)),
                    "current_score": current_scores[i],
                    "proposed_score": proposed_scores[i],
                })
    
    print(f"\n   Cases with delta_price < -0.35% (crash-like): {len(crash_cases)}")
    
    if crash_cases:
        # Analyze if current config triggers Long in these cases
        curr_long_during_crash = sum(1 for c in crash_cases if c["current_score"] >= 0.10)
        prop_long_during_crash = sum(1 for c in crash_cases if c["proposed_score"] >= 0.10)
        
        print(f"   CURRENT config would trigger LONG during crash: {curr_long_during_crash}")
        print(f"   PROPOSED config would trigger LONG during crash: {prop_long_during_crash}")
        
        if crash_cases:
            print(f"\n   Sample crash cases (first 5):")
            for c in crash_cases[:5]:
                print(f"      idx={c['index']:6d}, price={c['price']:.2f}, dp={c['dp']:.2f} ({c['dp_pct']*100:.3f}%), "
                      f"OBI={c['obi']:.2f}, curr_score={c['current_score']:+.3f}, prop_score={c['proposed_score']:+.3f}")
    
    # Feature contribution analysis
    print(f"\n📊 Feature Contribution (sample of last 100 bars, threshold=0.10):")
    
    # Take last 100 features
    sample_features = features_list[-100:] if len(features_list) >= 100 else features_list
    
    # Calculate contribution of each feature
    contributions_current = defaultdict(list)
    contributions_proposed = defaultdict(list)
    
    for feat in sample_features:
        price = Decimal(str(feat.get("price", "1")))
        
        for feat_name in current_weights.keys():
            raw = feat.get(feat_name, "0")
            try:
                value = Decimal(str(raw))
            except Exception:
                value = Decimal("0")
            
            if feat_name == "delta_price" and price > 0:
                dp_cap_pct = Decimal("0.02")
                dp_pct = value / price
                if dp_pct > dp_cap_pct:
                    dp_pct = dp_cap_pct
                elif dp_pct < -dp_cap_pct:
                    dp_pct = -dp_cap_pct
                value = dp_pct / dp_cap_pct
            
            contrib_curr = float(value * Decimal(str(current_weights[feat_name])))
            contrib_prop = float(value * Decimal(str(proposed_weights[feat_name])))
            
            contributions_current[feat_name].append(contrib_curr)
            contributions_proposed[feat_name].append(contrib_prop)
    
    print(f"\n   Feature         | Current Avg | Proposed Avg | Δ Impact")
    print(f"   {'-'*60}")
    
    for feat_name in sorted(current_weights.keys()):
        curr_avg = statistics.mean(contributions_current[feat_name])
        prop_avg = statistics.mean(contributions_proposed[feat_name])
        delta = prop_avg - curr_avg
        print(f"   {feat_name:20s} | {curr_avg:+.5f}    | {prop_avg:+.5f}    | {delta:+.5f}")


def main():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]
    
    print("\n" + "="*70)
    print("  DEEP FEATURE LOG ANALYSIS")
    print("="*70)
    
    for symbol in symbols:
        try:
            analyze_symbol(symbol)
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")


if __name__ == "__main__":
    main()
