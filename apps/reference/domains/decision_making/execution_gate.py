"""
Phase 5: Execution Gate (4-stage filter).

Standardized gate logic for all entries.
Enforces strict fail-closed validation and specific business rules.
"""
from typing import Dict, Any, Optional, Tuple, Literal
import logging
from decimal import Decimal

from apps.reference.config_models import ExecutionGateConfig, ExecutionGateName
from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
from apps.reference.domains.decision_making.entry_plan import EntryPlanResult


class ExecutionGate:
    """
    Enforces a strict 4-stage filter pipeline for trade entry.
    All enabled stages must pass for an entry to be allowed.
    """
    def __init__(self, config: ExecutionGateConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def check_entry(
        self,
        symbol: str,
        side: str,  # "BUY" or "SELL"
        features: Dict[str, Any],
        final_score: float,  # Post-shield score
        shield_multiplier: float,
        entry_plan: Optional[EntryPlanResult],
        signal_threshold: float,
        oracle_level: str = "NORMAL",
        danger_zone_active: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluate all enabled execution gates.
        
        Args:
            symbol: Trading pair symbol
            side: Intent side ("BUY"/"SELL")
            features: Feature map (must contain pillar features for Direction gate)
            final_score: Computed score after shield application
            shield_multiplier: Aggregate shield multiplier applied
            entry_plan: Computed EntryPlan (required for Structural gate)
            signal_threshold: Minimum absolute score required
            oracle_level: External oracle state ("NORMAL", "HIGH", "CRITICAL")
            danger_zone_active: Whether danger zone is triggered
            
        Returns:
            (is_allowed, reject_reason)
        """
        gates = self.config.gates_enabled
        
        # Stage 0: Hard Veto (Fail-closed)
        if ExecutionGateName.HARD_VETO in gates:
            is_ok, reason = self._check_hard_veto(
                symbol, oracle_level, danger_zone_active, entry_plan
            )
            if not is_ok:
                return False, reason

        # Stage 1: Direction (Standard vs Knife)
        # Note: Direction check relies on pillar features existing
        if ExecutionGateName.DIRECTION in gates:
            is_ok, reason = self._check_direction(
                symbol, side, features, final_score
            )
            if not is_ok:
                return False, reason

        # Stage 2: Threshold (Final Score)
        if ExecutionGateName.THRESHOLD in gates:
            if abs(final_score) < abs(signal_threshold):
                # Score too weak after shields/attenuation
                return False, f"SCORE_TOO_WEAK:{final_score:.4f}<{signal_threshold}"

        # Stage 3: Shield Invariant
        if ExecutionGateName.SHIELD in gates:
            # 1. Invariant: 0.0 <= multiplier <= 1.0 (Fail-closed on bad math/config)
            if not (0.0 <= shield_multiplier <= 1.0):
                return False, f"{NormalizedRejectReasons.SHIELD_INVARIANT_VIOLATED}:Mult={shield_multiplier}"
            
            # 2. Veto: Multiplier 0.0 means explicit block
            if shield_multiplier == 0.0:
                return False, NormalizedRejectReasons.SHIELD_VETO_BLOCKED

        # Stage 4: Structural (EntryPlan Risk/Reward)
        if ExecutionGateName.STRUCTURAL in gates:
            # EntryPlan is guaranteed != None by Stage 0 if enabled
            is_ok, reason = self._check_structural(entry_plan)
            if not is_ok:
                return False, reason

        # All gates passed
        return True, None

    def _check_hard_veto(
        self,
        symbol: str,
        oracle_level: str,
        danger_zone_active: bool,
        entry_plan: Optional[EntryPlanResult],
    ) -> Tuple[bool, Optional[str]]:
        """Fail-closed checks for critical conditions."""
        # 1. Danger Zone Active -> REJECT
        if danger_zone_active:
            return False, f"{NormalizedRejectReasons.HARD_VETO_BLOCKED}:DangerZone"
            
        # 2. Oracle Level Critical -> REJECT
        if oracle_level in ("HIGH", "CRITICAL"):
            return False, f"{NormalizedRejectReasons.HARD_VETO_BLOCKED}:Oracle{oracle_level}"
            
        # 3. Entry Plan Missing (Fail-closed)
        # Structural/Sizing logic requires EntryPlan. If it failed to compute, we cannot trade.
        if entry_plan is None:
            return False, f"{NormalizedRejectReasons.HARD_VETO_BLOCKED}:EntryPlanMissing"
            
        return True, None

    def _check_direction(
        self,
        symbol: str,
        side: str,
        features: Dict[str, Any],
        score: float,
    ) -> Tuple[bool, Optional[str]]:
        """Verify direction matches Operator trend or Knife criteria."""
        # Normalize side to 1 (BUY) or -1 (SELL)
        intent_dir = 1 if side.upper() in ("BUY", "LONG") else -1
        
        # Get Pillar Trends (Operator H4, Strategist D1)
        # Expected keys: "pillar_operator_trend", "pillar_strategist_trend"
        # Values: 1 (UP), -1 (DOWN), 0 (NEUTRAL/UNKNOWN) - Fail-closed if missing
        
        op_trend = features.get("pillar_operator_trend")
        strat_trend = features.get("pillar_strategist_trend")
        
        if op_trend is None:
            # Fail-closed: Cannot determine primary trend
            return False, f"{NormalizedRejectReasons.DATA_NOT_READY}:MissingOpTrend"
            
        # Fix: Handle float values (e.g. 1.0 from linear pillar) safely
        try:
            op_trend_val = int(float(op_trend))
            strat_trend_val = int(float(strat_trend)) if strat_trend is not None else 0
        except (ValueError, TypeError):
             return False, f"{NormalizedRejectReasons.DATA_NOT_READY}:InvalidTrendValue"
        
        # 1. Standard Entry: Must match Operator
        if op_trend_val != 0 and (intent_dir == op_trend_val):
            # Operator agrees. Check Strategist for Major Conflict?
            # User rule: "if Strategist opposes > threshold -> WAIT"
            # Here assuming simple conflict if signs opposite.
            if strat_trend_val != 0 and strat_trend_val != intent_dir:
                # Major Conflict (D1 opposes H4)
                # For now, simplistic: REJECT standard entry on conflict (WAIT) via gate
                return False, f"{NormalizedRejectReasons.DIRECTIONAL_SANITY_BLOCKED}:StrategistConflict"
            return True, None
            
        # 2. Knife Entry (Counter-Trend)
        # Defined as: Intent opposes Operator (or Operator neutral?)
        # User rule: "Knife allowed only if Knife-trigger + abs(score) <= knife_max"
        # Since we don't have knife_trigger feature explicit here, we assume standard mode restricts counter-trend.
        # IF intents are generated by a Knife strategy, they might set a flag.
        # But for generic Aurora, we primarily follow trend.
        
        # If Operator is flat (0), allow if Strategist agrees?
        if op_trend_val == 0:
            if strat_trend_val != 0 and intent_dir == strat_trend_val:
                return True, None # Follow D1 if H4 flat
            # If both flat, allow? Maybe depends on regime. 
            # Strictest interpretation: No trend = No trade.
            return False, f"{NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION}:FlatTrend"

        # If we are here, Intent != Operator.
        # This is a Counter-Trend / Knife attempt.
        # Unless we implement explicit Knife logic configs, we BLOCK.
        # TODO: Implement Knife override logic if needed.
        return False, f"{NormalizedRejectReasons.DIRECTIONAL_SANITY_BLOCKED}:CounterTrend({side} vs Op{op_trend_val})"

    def _check_structural(self, entry_plan: EntryPlanResult) -> Tuple[bool, Optional[str]]:
        """Verify Risk/Reward ratio from EntryPlan."""
        # Calculate Risk and Reward distances
        try:
            entry_price = float(entry_plan.entry_price)
            stop_price = float(entry_plan.stop_loss_price)
            tp_price = float(entry_plan.take_profit_price)
            
            risk_dist = abs(entry_price - stop_price)
            reward_dist = abs(entry_price - tp_price)
            
            if risk_dist <= 0:
                 return False, f"{NormalizedRejectReasons.STRUCTURAL_GATE_BLOCKED}:ZeroRiskDist"
                 
            rr_ratio = reward_dist / risk_dist
            
            if rr_ratio < self.config.structural_gate.min_risk_reward:
                return False, f"{NormalizedRejectReasons.STRUCTURAL_GATE_BLOCKED}:LowRR({rr_ratio:.2f}<{self.config.structural_gate.min_risk_reward})"
                
            if self.config.structural_gate.max_risk_reward:
                if rr_ratio > self.config.structural_gate.max_risk_reward:
                    # Cap R/R (e.g. don't aim for moon) - return False or just warn?
                    # Config says "filter unrealistic TPs", so Block.
                    return False, f"{NormalizedRejectReasons.STRUCTURAL_GATE_BLOCKED}:HighRR({rr_ratio:.2f}>{self.config.structural_gate.max_risk_reward})"
                    
            return True, None
            
        except (ValueError, TypeError):
             return False, f"{NormalizedRejectReasons.STRUCTURAL_GATE_BLOCKED}:InvalidPrices"
