"""
AuroraScoringKernel — Pure Scoring Logic for Aurora Strategy.

This module extracts the deterministic scoring math from `_make_decision_for_symbol`,
enabling:
1. Shadow mode comparison
2. Handler-based signal emission
3. Unit testing without DM dependencies

Contract:
- Input: Features, config, regime, side_bias_params
- Output: ScoringResult (score, side, thresholds, why_chain)
- No side effects (no logging state, no emission)
"""
from __future__ import annotations

import decimal
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from apps.reference.domains.decision_making.decision_context import (
    create_decision_context,
    DecisionContext,
)
from apps.reference.domains.decision_making.scoring_direction_strength_v1 import (
    compute_direction_strength_score,
    DirectionStrengthScore,
)


@dataclass
class ScoringResult:
    """Result of Aurora scoring kernel computation."""
    
    # Core outputs
    score: decimal.Decimal
    side: str  # "buy", "sell", or ""
    thr_buy: decimal.Decimal
    thr_sell: decimal.Decimal
    
    # Explainability
    why_chain: List[str] = field(default_factory=list)
    psi_vector: Dict[str, Any] = field(default_factory=dict)
    
    # Regime context
    regime: Optional[str] = None
    threshold_factor: decimal.Decimal = decimal.Decimal("1.0")
    
    # Side bias context
    buy_bias_mult: decimal.Decimal = decimal.Decimal("1.0")
    sell_bias_mult: decimal.Decimal = decimal.Decimal("1.0")
    
    # Deferred state
    deferred: bool = False
    defer_reason: Optional[str] = None
    
    # Phase 9: Shield context
    shield_multiplier: decimal.Decimal = decimal.Decimal("1.0")
    shield_breakdown: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SideBiasState:
    """Side bias window state for penalty calculation."""
    
    buy_count: int = 0
    sell_count: int = 0
    window_sec: float = 420.0
    target_ratio: float = 0.72
    penalty_factor: float = 0.25
    min_intents: int = 18


class AuroraScoringKernel:
    """
    Pure scoring kernel for Aurora strategy.
    
    Responsible ONLY for:
    1. Signal score calculation (via compute_direction_strength_score)
    2. Threshold calculation (base × regime_factor × side_bias)
    3. Side determination (buy/sell/neutral)
    
    NOT responsible for:
    - Gate checks (QoS, risk, exposure)
    - State tracking (side bias history)
    - Event emission
    """
    
    @staticmethod
    def compute(
        *,
        symbol: str,
        features: Dict[str, Any],
        warmup_readiness: Dict[str, bool],
        price: decimal.Decimal,
        signal_weights: Dict[str, float],
        feature_neutrals: Dict[str, float],
        essential_features: List[str],
        base_threshold: decimal.Decimal,
        regime_name: Optional[str],
        regime_thresholds: Dict[str, float],
        side_bias_state: Optional[SideBiasState],
        direction_strength_cfg: Dict[str, Any],
        delta_price_cap_pct: decimal.Decimal,
        scoring_version: str = "v2",
        # Hysteresis support
        neutral_threshold: Optional[decimal.Decimal] = None,
        current_side: str = "",
    ) -> ScoringResult:
        """
        Compute Aurora signal score and side.
        
        Args:
            symbol: Trading pair
            features: Raw feature dict from FE
            warmup_readiness: Feature readiness map
            price: Current price for normalization
            signal_weights: Feature weights
            feature_neutrals: Neutral points for features
            essential_features: Required features for scoring
            base_threshold: Signal threshold before adjustments
            regime_name: Current regime (or None)
            regime_thresholds: Regime → threshold multiplier map
            side_bias_state: Current side bias state (or None)
            direction_strength_cfg: DirectionStrengthScoring config
            delta_price_cap_pct: Cap for delta_price normalization
            scoring_version: "v1" or "v2"
            
        Returns:
            ScoringResult with score, side, thresholds, and explainability data
        """
        result = ScoringResult(
            score=decimal.Decimal("0"),
            side="",
            thr_buy=base_threshold,
            thr_sell=base_threshold,
            why_chain=[],
            regime=regime_name,
        )

        def _to_decimal_or_none(v: Any) -> Optional[decimal.Decimal]:
            if v is None:
                return None
            if isinstance(v, decimal.Decimal):
                return v if v.is_finite() else None
            try:
                d = decimal.Decimal(str(v))
            except Exception:
                return None
            return d if d.is_finite() else None
        
        # 1. Normalize delta_price
        dp_raw = _to_decimal_or_none(features.get("delta_price")) or decimal.Decimal("0")
        if price > 0 and delta_price_cap_pct > 0:
            dp_pct = dp_raw / price
            if dp_pct > delta_price_cap_pct:
                dp_pct = delta_price_cap_pct
            elif dp_pct < -delta_price_cap_pct:
                dp_pct = -delta_price_cap_pct
            dp_norm = dp_pct / delta_price_cap_pct
        else:
            dp_norm = decimal.Decimal("0")
        
        # 2. Build v2 feature map
        v2_features = dict(features)
        v2_features["delta_price"] = dp_norm
        
        # 3. Check essential features in readiness
        essential_set = set(essential_features)
        missing_ready_keys = essential_set - set(warmup_readiness.keys())
        if missing_ready_keys:
            result.deferred = True
            result.defer_reason = f"MISSING_READY_KEYS:{','.join(sorted(missing_ready_keys))}"
            return result
        
        # 4. Compute direction strength score
        ds_score = compute_direction_strength_score(
            features=v2_features,
            weights=signal_weights,
            neutrals=feature_neutrals,
            readiness=warmup_readiness,
            essential_features=essential_set,
            normalize_mode="net_zero",
            directional_features=list(direction_strength_cfg["directional_features"]),
            strength_features=list(direction_strength_cfg["strength_features"]),
            strength_alpha=float(direction_strength_cfg["strength_alpha"]),
            strength_cap=float(direction_strength_cfg["strength_cap"]),
            symbol=symbol,
        )
        
        if ds_score.deferred:
            result.deferred = True
            result.defer_reason = ds_score.deny_reason
            return result
        
        signal_score = ds_score.final_score
        result.score = signal_score
        
        # 5. Update psi_vector for explainability
        result.psi_vector = {
            "dir_score": float(ds_score.dir_score),
            "strength_score": float(ds_score.strength_score),
            "final_score": float(ds_score.final_score),
            "delta_price_norm": float(dp_norm),
        }
        
        # 6. Calculate threshold factor from regime
        if regime_name and regime_name in regime_thresholds:
            factor = _to_decimal_or_none(regime_thresholds[regime_name])
        elif "DEFAULT" in regime_thresholds:
            factor = _to_decimal_or_none(regime_thresholds["DEFAULT"])
        else:
            # Fail-closed: no factor means we can't proceed
            result.deferred = True
            result.defer_reason = f"MISSING_REGIME_THRESHOLD:{regime_name}"
            return result

        if factor is None or factor <= 0:
            result.deferred = True
            result.defer_reason = f"INVALID_REGIME_THRESHOLD_VALUE:{regime_name}"
            return result
        
        result.threshold_factor = factor
        signal_threshold = base_threshold * factor
        
        # 7. Calculate side bias penalties
        buy_bias_mult = decimal.Decimal("1.0")
        sell_bias_mult = decimal.Decimal("1.0")
        
        if side_bias_state and (side_bias_state.buy_count + side_bias_state.sell_count) >= side_bias_state.min_intents:
            total_count = side_bias_state.buy_count + side_bias_state.sell_count
            sell_share = decimal.Decimal(str(side_bias_state.sell_count)) / decimal.Decimal(str(total_count))
            target = decimal.Decimal(str(side_bias_state.target_ratio))
            penalty_factor = decimal.Decimal(str(side_bias_state.penalty_factor))
            
            if sell_share > target:
                # Too many SELLs → penalize SELL threshold
                excess = sell_share - target
                max_excess = decimal.Decimal("1.0") - target
                scaling = excess / max_excess if max_excess > 0 else decimal.Decimal("1.0")
                penalty = penalty_factor * scaling
                sell_bias_mult += penalty
                result.why_chain.append(f"sell_bias_penalty:{float(penalty):.2%}")
            elif sell_share < (decimal.Decimal("1.0") - target):
                # Too many BUYs → penalize BUY threshold
                buy_share = decimal.Decimal("1.0") - sell_share
                excess = buy_share - target
                max_excess = decimal.Decimal("1.0") - target
                scaling = excess / max_excess if max_excess > 0 else decimal.Decimal("1.0")
                penalty = penalty_factor * scaling
                buy_bias_mult += penalty
                result.why_chain.append(f"buy_bias_penalty:{float(penalty):.2%}")
        
        result.buy_bias_mult = buy_bias_mult
        result.sell_bias_mult = sell_bias_mult
        
        # 8. Final thresholds
        thr_buy = signal_threshold * buy_bias_mult
        thr_sell = signal_threshold * sell_bias_mult
        result.thr_buy = thr_buy
        result.thr_sell = thr_sell
        
        # 9. Determine side (with Hysteresis)
        # If neutral_threshold is provided, use 3-zone logic:
        #   - ENTER: cross signal_threshold
        #   - HOLD: stay if score > neutral_threshold (for current direction)
        #   - EXIT: drop below neutral_threshold
        
        thr_neutral = neutral_threshold if neutral_threshold is not None else thr_buy
        
        if current_side == "buy":
            # Currently LONG: check if we should hold or exit
            if signal_score <= -thr_sell:
                # FLIP to SELL (strong opposite signal)
                result.side = "sell"
                result.why_chain.append(f"flip:buy->sell:score={float(signal_score):.4f}<=-thr_sell={float(thr_sell):.4f}")
            elif signal_score >= thr_neutral:
                # HOLD: score still above neutral threshold
                result.side = "buy"
                result.why_chain.append(f"hold:buy:score={float(signal_score):.4f}>=thr_neutral={float(thr_neutral):.4f}")
            else:
                # EXIT: score dropped below neutral threshold
                result.side = ""
                result.why_chain.append(f"exit:buy->neutral:score={float(signal_score):.4f}<thr_neutral={float(thr_neutral):.4f}")
        
        elif current_side == "sell":
            # Currently SHORT: check if we should hold or exit
            if signal_score >= thr_buy:
                # FLIP to BUY (strong opposite signal)
                result.side = "buy"
                result.why_chain.append(f"flip:sell->buy:score={float(signal_score):.4f}>=thr_buy={float(thr_buy):.4f}")
            elif signal_score <= -thr_neutral:
                # HOLD: score still below -neutral threshold
                result.side = "sell"
                result.why_chain.append(f"hold:sell:score={float(signal_score):.4f}<=-thr_neutral={float(-thr_neutral):.4f}")
            else:
                # EXIT: score rose above -neutral threshold
                result.side = ""
                result.why_chain.append(f"exit:sell->neutral:score={float(signal_score):.4f}>-thr_neutral={float(-thr_neutral):.4f}")
        
        else:
            # Currently NEUTRAL: use standard entry logic
            if signal_score >= thr_buy:
                result.side = "buy"
                result.why_chain.append(f"enter:buy:score={float(signal_score):.4f}>=thr_buy={float(thr_buy):.4f}")
            elif signal_score <= -thr_sell:
                result.side = "sell"
                result.why_chain.append(f"enter:sell:score={float(signal_score):.4f}<=-thr_sell={float(thr_sell):.4f}")
            else:
                result.side = ""
                result.why_chain.append(f"neutral:score={float(signal_score):.4f}")
        
        return result
