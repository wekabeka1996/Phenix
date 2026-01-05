#!/usr/bin/env python3
"""
Shadow Run with Synthetic Crash Scenarios.

This script:
1. Takes real feature logs
2. Injects synthetic "crash" events to test system behavior
3. Compares how different configs react to these scenarios

This is crucial because the current feature logs lack crash events.
"""

import json
import copy
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Any
import statistics


def load_features(log_path: Path) -> List[Dict[str, Any]]:
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


def create_crash_scenario(base_features: Dict[str, Any], crash_intensity: float = 0.5) -> Dict[str, Any]:
    """
    Create a synthetic crash scenario from base features.
    
    crash_intensity: 0.0 = no crash, 1.0 = extreme crash
    """
    crash = copy.deepcopy(base_features)
    
    price = float(crash.get("price", 1000))
    
    # Simulate price drop: -0.5% to -2% depending on intensity
    crash_pct = 0.005 + (crash_intensity * 0.015)  # 0.5% to 2%
    new_price = price * (1 - crash_pct)
    crash["price"] = str(new_price)
    
    # delta_price should be strongly negative (absolute value)
    # This is the key signal that price is dropping
    crash["delta_price"] = str(-price * crash_pct)
    
    # During crashes, OBI often remains positive (buy walls from "dip buyers")
    # This is the TRAP described in SHORT_TREND_ANALYSIS_AND_PROPOSALS.md
    if crash_intensity > 0.3:
        crash["obi"] = str(0.5 + crash_intensity * 0.3)  # Positive OBI (trap!)
    
    # TFI usually turns negative in crashes
    crash["tfi"] = str(-0.3 - crash_intensity * 0.5)
    
    # Volume spikes during crashes
    crash["volume_spike"] = str(0.8 + crash_intensity * 0.2)
    
    # EMA bias turns bearish
    crash["ema_bias"] = str(0.3 - crash_intensity * 0.2)  # Below 0.5 = bearish
    
    return crash


def calc_score(features: dict, weights: dict, adaptive_dp: bool = False) -> Decimal:
    """
    Calculate signal score.
    
    adaptive_dp: If True, use asset-specific volatility normalization for delta_price
    """
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
            if adaptive_dp:
                # Adaptive cap: 0.5% for BTC, 1% for ETH, 2% for alts
                # This makes the system more sensitive to BTC moves
                if price > 50000:  # BTC-like
                    dp_cap_pct = Decimal("0.005")  # 0.5%
                elif price > 1000:  # ETH-like
                    dp_cap_pct = Decimal("0.01")  # 1%
                else:
                    dp_cap_pct = Decimal("0.02")  # 2%
            else:
                dp_cap_pct = Decimal("0.02")  # Standard 2% cap
            
            dp_pct = value / price
            if dp_pct > dp_cap_pct:
                dp_pct = dp_cap_pct
            elif dp_pct < -dp_cap_pct:
                dp_pct = -dp_cap_pct
            value = dp_pct / dp_cap_pct  # [-1, 1]
        
        score += value * Decimal(str(weight))
    
    return score


def analyze_crash_response(symbol: str, logs_dir: str = "logs/features"):
    """Test how different configs respond to synthetic crashes."""
    
    log_path = Path(logs_dir) / f"{symbol}.log"
    if not log_path.exists():
        print(f"Log not found: {log_path}")
        return
    
    features_list = load_features(log_path)
    if not features_list:
        return
    
    print(f"\n{'='*80}")
    print(f"  CRASH SCENARIO ANALYSIS: {symbol}")
    print(f"{'='*80}")
    
    # Take a sample baseline feature
    baseline = features_list[len(features_list) // 2]
    base_price = float(baseline.get("price", 1000))
    
    print(f"\n  Baseline price: ${base_price:.2f}")
    print(f"  Baseline OBI: {baseline.get('obi', 0)}")
    print(f"  Baseline delta_price: {baseline.get('delta_price', 0)}")
    
    # Define configs
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
    
    proposed_weights = current_weights.copy()
    proposed_weights["obi"] = 0.03
    proposed_weights["delta_price"] = 0.15
    
    aggressive_weights = current_weights.copy()
    aggressive_weights["obi"] = 0.02
    aggressive_weights["delta_price"] = 0.25
    
    threshold = Decimal("0.10")
    
    print(f"\n  Configs to compare:")
    print(f"    - CURRENT:    OBI={current_weights['obi']}, delta_price={current_weights['delta_price']}")
    print(f"    - PROPOSED:   OBI={proposed_weights['obi']}, delta_price={proposed_weights['delta_price']}")
    print(f"    - AGGRESSIVE: OBI={aggressive_weights['obi']}, delta_price={aggressive_weights['delta_price']}")
    
    print(f"\n  {'Crash':^10} | {'Price':^10} | {'ΔP%':^8} | {'OBI':^6} | {'CURRENT':^10} | {'PROPOSED':^10} | {'AGGRESSIVE':^10}")
    print(f"  {'-'*88}")
    
    # Test different crash intensities
    for intensity in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
        crash_feat = create_crash_scenario(baseline, intensity)
        
        price = float(crash_feat.get("price", 0))
        dp = float(crash_feat.get("delta_price", 0))
        dp_pct = (dp / base_price) * 100 if base_price > 0 else 0
        obi = float(crash_feat.get("obi", 0))
        
        score_curr = calc_score(crash_feat, current_weights)
        score_prop = calc_score(crash_feat, proposed_weights)
        score_aggr = calc_score(crash_feat, aggressive_weights)
        
        def signal_str(score: Decimal) -> str:
            if score >= threshold:
                return f"{float(score):+.3f} LONG"
            elif score <= -threshold:
                return f"{float(score):+.3f} SHORT"
            else:
                return f"{float(score):+.3f} FLAT"
        
        intensity_label = f"{intensity*100:.0f}%"
        
        print(f"  {intensity_label:^10} | ${price:>8.2f} | {dp_pct:>+7.2f}% | {obi:>+5.2f} | {signal_str(score_curr):^10} | {signal_str(score_prop):^10} | {signal_str(score_aggr):^10}")
    
    # Test with adaptive normalization
    print(f"\n  === WITH ADAPTIVE DELTA_PRICE NORMALIZATION ===")
    print(f"  {'Crash':^10} | {'CURRENT':^12} | {'PROPOSED':^12} | {'AGGRESSIVE':^12}")
    print(f"  {'-'*60}")
    
    for intensity in [0.0, 0.4, 0.8, 1.0]:
        crash_feat = create_crash_scenario(baseline, intensity)
        
        score_curr = calc_score(crash_feat, current_weights, adaptive_dp=True)
        score_prop = calc_score(crash_feat, proposed_weights, adaptive_dp=True)
        score_aggr = calc_score(crash_feat, aggressive_weights, adaptive_dp=True)
        
        def signal_str(score: Decimal) -> str:
            if score >= threshold:
                return f"{float(score):+.3f} LONG"
            elif score <= -threshold:
                return f"{float(score):+.3f} SHORT"
            else:
                return f"{float(score):+.3f} FLAT"
        
        intensity_label = f"{intensity*100:.0f}%"
        
        print(f"  {intensity_label:^10} | {signal_str(score_curr):^12} | {signal_str(score_prop):^12} | {signal_str(score_aggr):^12}")


def recommend_flash_crash_guard(symbol: str, logs_dir: str = "logs/features"):
    """
    Analyze what Flash Crash Guard threshold would be optimal.
    
    Based on the proposal in SHORT_TREND_ANALYSIS_AND_PROPOSALS.md
    """
    log_path = Path(logs_dir) / f"{symbol}.log"
    if not log_path.exists():
        return
    
    features_list = load_features(log_path)
    if not features_list:
        return
    
    print(f"\n{'='*80}")
    print(f"  FLASH CRASH GUARD ANALYSIS: {symbol}")
    print(f"{'='*80}")
    
    # Calculate delta_price distribution
    dp_pcts = []
    for feat in features_list:
        price = float(feat.get("price", 1))
        dp = float(feat.get("delta_price", 0))
        if price > 0:
            dp_pcts.append((dp / price) * 100)  # In percent
    
    if not dp_pcts:
        return
    
    print(f"\n  Delta Price (% of price) Distribution:")
    print(f"    Mean:   {statistics.mean(dp_pcts):+.4f}%")
    print(f"    StdDev: {statistics.stdev(dp_pcts):.4f}%")
    print(f"    Min:    {min(dp_pcts):+.4f}%")
    print(f"    Max:    {max(dp_pcts):+.4f}%")
    
    # Percentiles
    sorted_dp = sorted(dp_pcts)
    n = len(sorted_dp)
    p1 = sorted_dp[int(n * 0.01)]
    p5 = sorted_dp[int(n * 0.05)]
    p95 = sorted_dp[int(n * 0.95)]
    p99 = sorted_dp[int(n * 0.99)]
    
    print(f"\n  Percentiles:")
    print(f"    P1:  {p1:+.4f}%")
    print(f"    P5:  {p5:+.4f}%")
    print(f"    P95: {p95:+.4f}%")
    print(f"    P99: {p99:+.4f}%")
    
    # Recommendation
    print(f"\n  📋 RECOMMENDED FLASH CRASH GUARD THRESHOLDS:")
    print(f"    Conservative (block at P1):  {p1:.4f}% = {p1/100:.6f} as ratio")
    print(f"    Moderate (2x StdDev):        {-2*statistics.stdev(dp_pcts):.4f}%")
    print(f"    Aggressive (block at P5):    {p5:.4f}%")
    
    print(f"\n  💡 For SHORT_TREND_ANALYSIS_AND_PROPOSALS.md Flash Crash Guard:")
    print(f"     Current proposal: -0.35% ({-0.0035:.6f})")
    print(f"     Based on data, consider: {min(p1, -0.35):.4f}%")


def main():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]
    
    print("\n" + "="*80)
    print("  SHADOW RUN: CRASH SCENARIO TESTING")
    print("  Testing how different configs react to simulated market crashes")
    print("="*80)
    
    for symbol in symbols:
        try:
            analyze_crash_response(symbol)
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")
    
    print("\n\n" + "="*80)
    print("  FLASH CRASH GUARD THRESHOLD RECOMMENDATIONS")
    print("="*80)
    
    for symbol in symbols:
        try:
            recommend_flash_crash_guard(symbol)
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")


if __name__ == "__main__":
    main()
