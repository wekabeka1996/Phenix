
import decimal

# Simulation of the new logic
NEUTRAL_OFFSETS = {
    "ema_bias": decimal.Decimal("0.5"),
    "volume_spike": decimal.Decimal("0.0"),
    "macro_sync": decimal.Decimal("0.5"),
    "liquidity_kappa": decimal.Decimal("0.0"),
    "obi": decimal.Decimal("0.0"),
    "tfi": decimal.Decimal("0.0"),
    "volatility_state": decimal.Decimal("0.0"),
    "depth_imbalance": decimal.Decimal("0.5"),
    "delta_price": decimal.Decimal("0.0"),
}

WEIGHTS_BTC = {
    "ema_bias": 0.15,
    "volume_spike": 0.15,
    "macro_sync": 0.15,
    "liquidity_kappa": 0.15,
    "obi": 0.10,
    "tfi": 0.10,
    "volatility_state": 0.10,
    "depth_imbalance": 0.05,
    "delta_price": 0.05
}

def calculate_score(features, weights):
    signal_score = decimal.Decimal("0")
    logs = []
    
    for f, w in weights.items():
        weight = decimal.Decimal(str(w))
        val = decimal.Decimal(str(features.get(f, 0.0)))
        
        # GATE
        if f == "liquidity_kappa":
            if val < decimal.Decimal("0.5"):
                logs.append(f"BLOCKED: Low Liquidity {val}")
                return -999, logs
            continue
            
        offset = NEUTRAL_OFFSETS.get(f, decimal.Decimal("0.0"))
        normalized_val = val - offset
        contribution = normalized_val * weight
        
        signal_score += contribution
        logs.append(f"{f}: {val} -> {normalized_val} * {weight} = {contribution}")
        
    return signal_score, logs

def test_incident_case():
    print("\n--- TEST: Incident Scenario (Peak Entry) ---")
    # Real data from SOLUSDT incident
    features = {
        "liquidity_kappa": 0.9943,
        "ema_bias": 0.4997,
        "macro_sync": 0.6385,
        "volume_spike": 0.3478,
        "volatility_state": 0.1811,
        "depth_imbalance": 0.6522,
        "delta_price": 0.01,
        "obi": -0.3080,
        "tfi": -0.2646,
        "volume_zscore": 0.90
    }
    
    score, logs = calculate_score(features, WEIGHTS_BTC)
    print("\n".join(logs))
    print(f"\nFINAL SCORE: {score:.4f}")
    if score < 0.1:
        print("RESULT: BLOCKED (Correct)")
    else:
        print("RESULT: ALLOWED (Failure)")

def test_neutral_case():
    print("\n--- TEST: Neutral Market ---")
    features = {
        "liquidity_kappa": 1.0,
        "ema_bias": 0.5,
        "macro_sync": 0.5,
        "volume_spike": 0.0,
        "volatility_state": 0.0,
        "depth_imbalance": 0.5,
        "delta_price": 0.0,
        "obi": 0.0,
        "tfi": 0.0
    }
    score, logs = calculate_score(features, WEIGHTS_BTC)
    print(f"FINAL SCORE: {score:.4f} (Expected ~0.0)")

def test_strong_signal():
    print("\n--- TEST: Strong Buy Signal ---")
    features = {
        "liquidity_kappa": 1.0, # Pass gate
        "ema_bias": 0.8,        # Bullish trend (+0.3)
        "macro_sync": 0.8,      # Sync Bullish (+0.3)
        "volume_spike": 0.5,    # Active (+0.5)
        "volatility_state": 0.2,# Low vol? (+0.2)
        "depth_imbalance": 0.2, # Ask depleted, Bid dominant (For depth_imb: 0.5 neutral. 0.2 means bids?) 
                                # Wait, depth_imbalance often 0.5 neutral. 
                                # If 0 is bid heavy, then 0.2 - 0.5 = -0.3.
                                # But wait, is low depth_imbalance bullish?
                                # Usually yes, phi < 0.5 is bullish (bid support).
                                # But let's check weights? 
                                # If weight is positive, and we want positive score for buy...
                                # Then we want (val - offset) > 0.
                                # So val > offset.
                                # If depth_imbalance > 0.5 is bearish (ask heavy), then logic is inverted?
                                # Let's ignore depth for a moment and assume general bullishness.
        "obi": 0.8,             # Buy pressure
        "tfi": 0.5,             # Buy flow
        "delta_price": 0.01     # Up
    }
    
    # Correction: depth_imbalance logic
    # If high depth_imbalance (0.9) means Ask Heavy (Bearish), then 0.9 - 0.5 = 0.4. 
    # 0.4 * weight -> Positive score?
    # Wait, if positive score = BUY, then bearish feature should decrease score.
    # So 0.9 (Bearish) -> Positive contribution? THAT IS WRONG.
    # We might have another bug or I misunderstand depth_imbalance.
    # Code says: "phi > 0.5 indicates ask dominance (bearish)".
    # If weight is positive (0.05), then 0.9 will ADD to score.
    # THIS MEANS DEPTH IMBALANCE MIGHT BE INVERTED IN CONFIG OR CODE!
    # But let's focus on Net-Zero verification first.
    
    score, logs = calculate_score(features, WEIGHTS_BTC)
    print(f"FINAL SCORE: {score:.4f} (Expected > 0.1)")

if __name__ == "__main__":
    test_incident_case()
    test_neutral_case()
    test_strong_signal()
