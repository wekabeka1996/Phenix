#!/usr/bin/env python3
"""
Tool: score_compare.py
Description: Compares Legacy V1 Scoring vs V2 Net-Zero Scoring on historical feature logs.
Usage: python3 apps/reference/tools/score_compare.py --file logs/features.log --weights-file config/aurora.yaml
"""

import sys
import json
import argparse
import decimal
from decimal import Decimal
import logging

# Ensure path
import os
sys.path.append(os.getcwd())

from apps.reference.domains.decision_making.signal_score_v2 import SignalScoreV2, ScoreResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("score_compare")

def mock_v1_score(features: dict, weights: dict, neutrals_v1_hardcoded: dict) -> Decimal:
    """Legacy V1 Logic Simulation."""
    score = Decimal("0")
    # V1 logic (simplified): sum(w * (val - offset))
    # It didn't normalize by sum(w)! It relied on weights summing to ~1 or threshold tuning.
    # Also it handled liquidity as a weighted feature.
    
    for f, w in weights.items():
        val = Decimal(str(features.get(f, 0)))
        offset = Decimal(str(neutrals_v1_hardcoded.get(f, 0)))
        
        # V1 logic usually clamped delta_price differently but let's assume normalized inputs 
        # or use raw logic if we had V1 code here.
        # We will assume features are pre-normalized for comparison parity,
        # EXCEPT we subtract offset.
        
        score += Decimal(str(w)) * (val - offset)
    return score

def main():
    parser = argparse.ArgumentParser(description="Compare Score V1 vs V2")
    parser.add_argument("--mock", action="store_true", help="Run with mock data")
    args = parser.parse_args()

    if args.mock:
        run_mock_comparison()
        return

    logger.info("Please provide log file mode (not fully implemented without log format spec). Running mock.")
    run_mock_comparison()

def run_mock_comparison():
    logger.info("--- Running Mock Comparison ---")
    
    # 1. Setup Configuration
    # Example: ETHUSDT weights (from Step 62)
    weights_v1 = {
        "ema_bias": 0.058,
        "volume_spike": 0.241,
        "macro_sync": 0.131,
        "liquidity_kappa": 0.341, # Included in V1
        "obi": 0.155,
        "tfi": 0.093,
        "volatility_state": 0.036,
        "depth_imbalance": 0.256,
        "delta_price": 0.253
        # Sum > 1.0 (1.56)
    }
    
    weights_v2 = weights_v1.copy()
    del weights_v2["liquidity_kappa"] # Removed in V2
    
    neutrals_v2 = {
        "ema_bias": 0.5,
        "volume_spike": 0.0,
        "macro_sync": 0.5,
        "obi": 0.0,
        "tfi": 0.0,
        "volatility_state": 0.0,
        "depth_imbalance": 0.5,
        "delta_price": 0.0
    }
    
    # Hardcoded V1 offsets (from legacy code block)
    neutrals_v1 = {
        "ema_bias": 0.5,
        "macro_sync": 0.5,
        "depth_imbalance": 0.5,
        # Others 0
    }

    # 2. Mock Feature Event (Baseline "Neutral-ish" Market)
    features_neutral = {
        "ema_bias": 0.55, # slightly bullish
        "volume_spike": 0.1, # quiet
        "macro_sync": 0.6, # slightly aligned
        "liquidity_kappa": 0.8, # good liquidity
        "obi": 0.1, # slight buy pressure
        "tfi": 0.1, 
        "volatility_state": 0.1,
        "depth_imbalance": 0.6, # buy heavy
        "delta_price": 0.01
    }
    
    compare("Baseline", features_neutral, weights_v1, weights_v2, neutrals_v1, neutrals_v2)

    # 3. Mock Feature Event (High Score V1, Gate Fail)
    features_gate_fail = features_neutral.copy()
    features_gate_fail["liquidity_kappa"] = 0.1 # FAIL GATE
    
    compare("Liq Fail", features_gate_fail, weights_v1, weights_v2, neutrals_v1, neutrals_v2, gate_kappa=0.2)

    # 4. Mock Feature Event (Peak Entry Scenario)
    # Price spiked (obi high), but neutral offset logic should dampen?
    # V1: sum(w*val). active features add up directly.
    # V2: sum(w*(val-neutral)) / sum(|w|).
    
    features_peak = {
        "ema_bias": 0.9, # VERY bullish
        "volume_spike": 0.8, # High volume
        "macro_sync": 0.5, # Neutral
        "liquidity_kappa": 0.5,
        "obi": 0.9, # Buy pressure
        "tfi": 0.9,
        "volatility_state": 0.8,
        "depth_imbalance": 0.9,
        "delta_price": 0.8
    }
    compare("Peak/Hot", features_peak, weights_v1, weights_v2, neutrals_v1, neutrals_v2)


def compare(name, f, w1, w2, n1, n2, gate_kappa=None):
    print(f"\n[{name}]")
    
    # V1 Calc
    s1 = mock_v1_score(f, w1, n1)
    print(f"  V1 Score (Legacy): {s1:.4f} (Weights Sum: {sum(w1.values()):.2f})")
    
    # V2 Calc
    # Check Gate
    kappa = f.get("liquidity_kappa", 0)
    if gate_kappa and kappa < gate_kappa:
        print(f"  V2 Score: BLOCKED (Kappa {kappa} < {gate_kappa})")
        return

    readiness = {k: True for k in f}
    res = SignalScoreV2.calculate_score(f, w2, n2, readiness, set(), "MOCK")
    print(f"  V2 Score (NetZero): {res.score:.4f} (Raw: {res.score_raw:.4f}, WAbs: {res.wabs:.4f})")
    
    diff = float(res.score) - float(s1)
    print(f"  Diff (V2 - V1): {diff:.4f}")

if __name__ == "__main__":
    main()
