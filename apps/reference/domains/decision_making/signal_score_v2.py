"""
Signal Score V2 - Global Scoring & Gating Kernel
================================================

Implements the "Net-Zero Scoring" standard (Incidence Fix 2026-01-04).
Formula: score = Σ w_i * (x_i - neutral_i) / Σ |w_i|

Key Principles:
1. Fail-Closed: Missing or not-ready essential features -> DEFER/BLOCK.
2. Net-Zero: All features normalized to [-1, 1] (or similar) around 0.
3. Liquidity Gating: liquidity_kappa is NOT a weighted feature, but a hard gate.
4. Config Contract: All weighted features MUST have a defined neutral offset.

Scope: Project-wide (Aurora, MeanReversion if applicable).
"""

import logging
import decimal
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass

logger = logging.getLogger("signal_score_v2")

@dataclass
class ScoreResult:
    """Result of score evaluation."""
    score: decimal.Decimal
    score_raw: decimal.Decimal
    wabs: decimal.Decimal
    is_ready: bool
    deferred: bool
    reasons: List[str]
    missing_features: List[str]
    not_ready_features: List[str]
    contribs: Dict[str, float]  # Contribution of each feature to score_raw

class SignalScoreV2:
    """
    V2 Scoring Engine.
    
    Usage:
        engine = SignalScoreV2()
        # Init time
        engine.validate_config(weights, neutrals)
        # Runtime
        result = engine.calculate_score(...)
        if result.deferred:
            return ...
    """

    @staticmethod
    def validate_config(
        weights: Dict[str, float],
        neutrals: Dict[str, float],
        strategy_id: str = "unknown"
    ) -> None:
        """
        Validate that every weighted feature has a defined neutral offset.
        Raises ValueError if contract violated.
        """
        missing_neutrals = []
        for feat, w in weights.items():
            # Skip 0-weight features? No, explicit config is better.
            # But if w=0, maybe strictness is relaxed? 
            # User says: "feature_neutrals має бути визначений для кожної weighted feature"
            if getattr(w, "real", w) == 0:
                continue
            
            if feat not in neutrals:
                missing_neutrals.append(feat)
        
        if missing_neutrals:
            raise ValueError(
                f"[{strategy_id}] SignalScoreV2 Configuration Error: "
                f"Missing neutral offsets for weighted features: {missing_neutrals}. "
                "Every feature in 'signal_weights' must have a corresponding entry in 'feature_neutrals'."
            )

    @staticmethod
    def calculate_score(
        features: Dict[str, Any],
        weights: Dict[str, float],
        neutrals: Dict[str, float],
        readiness: Dict[str, bool],
        essential_features: Set[str],
        symbol: str = "unknown"
    ) -> ScoreResult:
        """
        Calculate V2 Score.

        Args:
            features: Dictionary of feature values (str/float/Decimal)
            weights: Dictionary of weights
            neutrals: Dictionary of neutral offsets
            readiness: Dictionary of feature readiness status (from warmup['ready'])
            essential_features: Set of features that MUST be ready/present
            symbol: For logging

        Returns:
            ScoreResult
        """
        score_raw = decimal.Decimal("0")
        wabs = decimal.Decimal("0")
        
        contribs: Dict[str, float] = {}
        missing: List[str] = []
        not_ready: List[str] = []
        reasons: List[str] = []
        
        # 1. Iterate over defined weights
        for feat, w_raw in weights.items():
            w = decimal.Decimal(str(w_raw))
            if w == 0:
                continue

            # Check existence
            if feat not in features:
                if feat in essential_features:
                    missing.append(feat)
                continue # Skip if missing but not essential (though this affects wabs if we skip w?)
                # Wait, formula says: "score_raw = Σ w_i * ...", "wabs = Σ |w_i|"
                # "ВАЖЛИВО: якщо фіча not-ready або відсутня → вона не входить ні в score_raw, ні в wabs."
            
            val_raw = features[feat]
            
            # Check readiness
            # If readiness dict provided, use it. If key missing, assume NOT ready (fail-closed)
            is_ready = readiness.get(feat, False)
            if not is_ready:
                if feat in essential_features:
                    not_ready.append(feat)
                continue # Skip from calculation
            
            # Check neutral config availability
            # (Should be caught at init, but runtime fail-safe)
            if feat not in neutrals:
                # Treat as missing config -> BLOCK/DEFER if essential? 
                # Or just error? User said "startup abort", so here we assume it exists or we default to 0 with error log?
                # But we can't default. 
                logger.error(f"[{symbol}] Missing neutral for active weighted feature {feat}")
                missing.append(f"{feat}(cfg)")
                continue

            neutral = decimal.Decimal(str(neutrals[feat]))
            
            # Calculate component
            try:
                val = decimal.Decimal(str(val_raw))
                component = w * (val - neutral)
                score_raw += component
                wabs += abs(w)
                contribs[feat] = float(component)
            except Exception as e:
                logger.warning(f"[{symbol}] Error calc feature {feat}: {e}")
                missing.append(f"{feat}(err)")

        # 2. Check essential blockers
        deferred = False
        if missing:
            reasons.append(f"NRR-FEATURES-MISSING:{','.join(missing)}")
            deferred = True
        if not_ready:
            reasons.append(f"NRR-FEATURES-NOT-READY:{','.join(not_ready)}")
            deferred = True
            
        # 3. Finalize Score
        if deferred:
            return ScoreResult(
                score=decimal.Decimal("0"),
                score_raw=decimal.Decimal("0"),
                wabs=decimal.Decimal("0"),
                is_ready=False,
                deferred=True,
                reasons=reasons,
                missing_features=missing,
                not_ready_features=not_ready,
                contribs={}
            )

        if wabs == 0:
            # No active features -> Neutral (0) or Error? 
            # If essentials were required, we would have deferred.
            # If no essentials and wabs=0, it means no weights active. Result 0.
            return ScoreResult(
                score=decimal.Decimal("0"),
                score_raw=decimal.Decimal("0"),
                wabs=decimal.Decimal("0"),
                is_ready=True, # Technically ready to say "0"
                deferred=False,
                reasons=[],
                missing_features=[],
                not_ready_features=[],
                contribs={}
            )

        score_norm = score_raw / wabs
        
        return ScoreResult(
            score=score_norm,
            score_raw=score_raw,
            wabs=wabs,
            is_ready=True,
            deferred=False,
            reasons=[],
            missing_features=[],
            not_ready_features=[],
            contribs=contribs
        )
