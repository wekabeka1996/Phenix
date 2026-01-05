
"""
Signal Score V2 Core Module.

Implements the Net-Zero Scoring formula and validation logic as per TASK: GLOBAL-SCORE-V2-PEAKFIX-001.

Formula:
    score_raw = Σ w_i * (x_i - neutral_i)
    wabs = Σ |w_i|
    score = score_raw / wabs

Features:
    - Fail-closed validation (essential features check)
    - Configuration contract validation (neutrals map integrity)
    - Scale invariant normalization
"""

import decimal
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)

class SignalScoreV2:
    def __init__(self, feature_neutrals: Dict[str, float], essential_features: List[str]):
        self.neutrals = {k: Decimal(str(v)) for k, v in feature_neutrals.items()}
        self.essential_features = set(essential_features)
    
    def validate_config(self, weights: Dict[str, float]) -> None:
        """
        Validate that all weighted features have a defined neutral point.
        Raises ValueError if configuration is invalid (Startup Abort).
        """
        missing = []
        for feature in weights.keys():
            if feature not in self.neutrals:
                missing.append(feature)
        
        if missing:
            raise ValueError(
                f"Configuration Error: Missing neutral baselines for weighted features: {missing}. "
                f"All features in signal_weights must have a defined neutral point in feature_neutrals."
            )

    def calculate(
        self, 
        features: Dict[str, Any], 
        weights: Dict[str, float]
    ) -> Tuple[Decimal, Dict[str, Any], Optional[str]]:
        """
        Calculate Signal Score V2.
        
        Args:
            features: Dictionary of feature values (str, float, or Decimal)
            weights: Dictionary of feature weights
            
        Returns:
            (score, debug_metadata, reject_reason)
            
            score: Decimal score in approximately [-1, 1] range (or 0 if rejected)
            debug_metadata: Dict with calculation details (raw_score, wabs, contributors)
            reject_reason: None if successful, or NRR string if blocked (e.g. NRR-FEATURES-NOT-READY)
        """
        score_raw = Decimal("0")
        wabs = Decimal("0")
        contributors = {}
        
        # 1. Essential Features Check (Fail-Closed)
        # Check if all essential features are present in the input details
        # Note: 'features' input might effectively be missing keys or have None values
        missing_essential = []
        for eff in self.essential_features:
            if eff not in features or features[eff] is None:
                missing_essential.append(eff)
                
        if missing_essential:
            return Decimal("0"), {}, f"NRR-FEATURES-NOT-READY: Missing {missing_essential}"

        # 2. Score Calculation
        for feature, weight_float in weights.items():
            # Skip if weight is 0
            if weight_float == 0:
                continue
                
            # If a weighted feature is missing but not essential, strictly speaking V2 says:
            # "if feature not-ready or missing -> skip from score_raw and wabs"
            # BUT if it is essential, we would have caught it above.
            if feature not in features or features[feature] is None:
                continue
                
            try:
                val = Decimal(str(features[feature]))
                weight = Decimal(str(weight_float))
                neutral = self.neutrals.get(feature, Decimal("0")) # Should exist due to validate_config
                
                term = (val - neutral) * weight
                score_raw += term
                wabs += abs(weight)
                
                contributors[feature] = {
                    "val": float(val),
                    "neutral": float(neutral),
                    "diff": float(val - neutral),
                    "weight": float(weight),
                    "contribution": float(term)
                }
                
            except Exception as e:
                # Malformed value -> Treat as missing -> fail closed if essential
                if feature in self.essential_features:
                    return Decimal("0"), {}, f"NRR-FEATURES-INVALID: {feature} error {e}"
                continue

        # 3. Normalization
        if wabs == 0:
            return Decimal("0"), {"reason": "zero_weights"}, None
            
        final_score = score_raw / wabs
        
        metadata = {
            "score_raw": float(score_raw),
            "wabs": float(wabs),
            "score_v2": float(final_score),
            "contributors": contributors
        }
        
        return final_score, metadata, None

