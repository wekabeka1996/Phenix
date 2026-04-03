"""Execution-time entry gate bundle for Aurora-style trade proposals.

This module runs after the caller has already computed a candidate side, score,
shield multiplier, and optional EntryPlan. It returns a fail-closed allow/deny
decision plus a compact reject reason, but it does not emit events or mutate
caller state.

Important boundary notes proven from runtime wiring:
- Aurora's liquidity gate is evaluated earlier in aurora_decision.py; the
  LIQUIDITY enum value is not re-checked inside this class.
- Stage activation is keyed off gates_enabled membership. The parsed
  structural_gate.enabled flag is not consulted here.
"""

from typing import Any, Dict, Optional, Tuple
import logging

from apps.reference.config_models import ExecutionGateConfig, ExecutionGateName
from apps.reference.domains.decision_making.entry_plan import EntryPlanResult
from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons


class ExecutionGate:
    """Evaluate the implemented execution-gate stages for one entry attempt.

    The class is intentionally small and synchronous: it only inspects the
    supplied inputs and returns the first blocking reason. Callers own
    observability, blocked-event emission, and any upstream prerequisites such
    as liquidity readiness.
    """

    def __init__(self, config: ExecutionGateConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def check_entry(
        self,
        symbol: str,
        side: str,
        features: Dict[str, Any],
        final_score: float,
        shield_multiplier: float,
        entry_plan: Optional[EntryPlanResult],
        signal_threshold: float,
        oracle_level: str = "NORMAL",
        danger_zone_active: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """Evaluate the configured gate stages in their hard-coded order.

        Contract:
        - ``side`` is expected to be a validated trade intent direction.
        - ``features`` must already contain any directional evidence required by
          the Direction gate.
        - ``entry_plan`` may be None when upstream planning failed; this helper
          fails closed if a configured stage depends on it.

        Returns ``(allowed, reason)`` where ``reason`` is the first reject code
        produced by the executed stage sequence.
        """
        gates = self.config.gates_enabled

        # Stage 0: Hard Veto (fail-closed)
        if ExecutionGateName.HARD_VETO in gates:
            is_ok, reason = self._check_hard_veto(
                symbol=symbol,
                oracle_level=oracle_level,
                danger_zone_active=danger_zone_active,
                entry_plan=entry_plan,
            )
            if not is_ok:
                return False, reason

        # Stage 1: Direction. The caller must already have cached the pillar
        # trend evidence needed by this gate.
        if ExecutionGateName.DIRECTION in gates:
            is_ok, reason = self._check_direction(
                symbol=symbol,
                side=side,
                features=features,
                score=final_score,
            )
            if not is_ok:
                return False, reason

        # Stage 2: Threshold. Score is judged after upstream attenuation.
        if ExecutionGateName.THRESHOLD in gates:
            if abs(final_score) < abs(signal_threshold):
                return False, f"SCORE_TOO_WEAK:{final_score:.4f}<{signal_threshold}"

        # Stage 3: Shield invariant.
        if ExecutionGateName.SHIELD in gates:
            if not (0.0 <= shield_multiplier <= 1.0):
                return False, (
                    f"{NormalizedRejectReasons.SHIELD_INVARIANT_VIOLATED}:"
                    f"Mult={shield_multiplier}"
                )

            # Multiplier 0.0 is an explicit veto, not merely a weak score.
            if shield_multiplier == 0.0:
                return False, NormalizedRejectReasons.SHIELD_VETO_BLOCKED

        # HARD_VETO usually guarantees EntryPlan presence, but custom gate lists
        # may enable STRUCTURAL without HARD_VETO, so _check_structural() guards
        # the dependency again instead of assuming stage coupling.
        if ExecutionGateName.STRUCTURAL in gates:
            is_ok, reason = self._check_structural(entry_plan)
            if not is_ok:
                return False, reason

        return True, None

    def _check_hard_veto(
        self,
        symbol: str,
        oracle_level: str,
        danger_zone_active: bool,
        entry_plan: Optional[EntryPlanResult],
    ) -> Tuple[bool, Optional[str]]:
        """Reject on critical prerequisites that must never degrade open."""
        if danger_zone_active:
            return False, f"{NormalizedRejectReasons.HARD_VETO_BLOCKED}:DangerZone"

        if oracle_level in ("HIGH", "CRITICAL"):
            return False, f"{NormalizedRejectReasons.HARD_VETO_BLOCKED}:Oracle{oracle_level}"

        # Structural/sizing logic depends on a real EntryPlan result.
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
        """Verify the entry side against the available trend-direction inputs.

        Current behavior is intentionally conservative:
        - standard entries must align with Operator trend;
        - Strategist opposition blocks the otherwise aligned entry;
        - explicit counter-trend or "knife" handling is not implemented here,
          so such attempts are rejected rather than inferred from score alone.
        """
        intent_dir = 1 if side.upper() in ("BUY", "LONG") else -1

        op_trend = features.get("pillar_operator_trend")
        strat_trend = features.get("pillar_strategist_trend")

        if op_trend is None:
            return False, f"{NormalizedRejectReasons.DATA_NOT_READY}:MissingOpTrend"

        # Trend values are expected to be directional sentinels (-1, 0, 1), but
        # some fixtures pass 1.0/-1.0 floats, so parse through float first.
        try:
            op_trend_val = int(float(op_trend))
            strat_trend_val = int(
                float(strat_trend)) if strat_trend is not None else 0
        except (ValueError, TypeError):
            return False, f"{NormalizedRejectReasons.DATA_NOT_READY}:InvalidTrendValue"

        if op_trend_val != 0 and intent_dir == op_trend_val:
            if strat_trend_val != 0 and strat_trend_val != intent_dir:
                return False, (
                    f"{NormalizedRejectReasons.DIRECTIONAL_SANITY_BLOCKED}:"
                    "StrategistConflict"
                )
            return True, None

        if op_trend_val == 0:
            if strat_trend_val != 0 and intent_dir == strat_trend_val:
                return True, None
            return False, f"{NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION}:FlatTrend"

        # If we are here, the intent opposes Operator. The class does not carry
        # a separate knife-entry config, so counter-trend attempts fail closed.
        return False, (
            f"{NormalizedRejectReasons.DIRECTIONAL_SANITY_BLOCKED}:"
            f"CounterTrend({side} vs Op{op_trend_val})"
        )

    def _check_structural(
        self,
        entry_plan: Optional[EntryPlanResult],
    ) -> Tuple[bool, Optional[str]]:
        """Verify EntryPlan-derived risk/reward geometry.

        This stage fails closed on missing or non-numeric EntryPlan prices. It
        intentionally re-checks ``entry_plan is not None`` so custom
        configurations cannot crash the gate by enabling STRUCTURAL without
        HARD_VETO.
        """
        if entry_plan is None:
            return False, f"{NormalizedRejectReasons.STRUCTURAL_GATE_BLOCKED}:EntryPlanMissing"

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
                return False, (
                    f"{NormalizedRejectReasons.STRUCTURAL_GATE_BLOCKED}:"
                    f"LowRR({rr_ratio:.2f}<{self.config.structural_gate.min_risk_reward})"
                )

            max_rr = self.config.structural_gate.max_risk_reward
            if max_rr is not None and rr_ratio > max_rr:
                return False, (
                    f"{NormalizedRejectReasons.STRUCTURAL_GATE_BLOCKED}:"
                    f"HighRR({rr_ratio:.2f}>{max_rr})"
                )

            return True, None

        except (ValueError, TypeError):
            return False, f"{NormalizedRejectReasons.STRUCTURAL_GATE_BLOCKED}:InvalidPrices"
