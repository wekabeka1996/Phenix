"""
AggOco Watchdog (V2) — thin detect-only layer over BracketService.

Responsibilities:
- Build BracketState for all symbols/sides using BracketService.
- Evaluate to BracketPlans.
- Surface severities (INFO/WARN/ALERT) via metrics/logs.

Non-responsibilities:
- No TP/SL math (delegated to tp_sl_math via BracketService).
- No auto-heal, no adapter calls, no OrderGuardian mutations.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .types import WatchdogAction, WatchdogRecommendation
from .bracket_service import (
    BracketService,
    BracketRulesConfig,
    PositionView,
    OrderView,
    BracketPlan,
)
from .converters import normalize_positions, normalize_orders

logger = logging.getLogger(__name__)


class AggOcoWatchdogService:
    """
    Detect-only watchdog backed by BracketService.
    """

    def __init__(self, bracket_service: Optional[BracketService] = None, cfg: Optional[Dict[str, Any]] = None):
        self.bracket_service = bracket_service or BracketService(
            aggregator=None, guardian=None, watchdog=None)  # guardian None in V2
        self.cfg = cfg or {}

    def analyze(
        self,
        open_orders: List[Dict[str, Any]],
        positions: List[Dict[str, Any]],
        bracket_metas: Optional[Any] = None
    ) -> List[WatchdogRecommendation]:
        """
        Evaluate all symbols/sides via BracketService and return recommendations (detect-only).
        """
        try:
            rules_cfg = self._get_rules_cfg()
        except Exception:
            return []

        # If disabled, skip
        if not rules_cfg.enabled:
            return []

        norm_positions = normalize_positions(positions or [])
        norm_orders = normalize_orders(open_orders or [])

        # Use BracketService for evaluation
        recs: List[WatchdogRecommendation] = []

        # Ensure we have a service instance
        if not self.bracket_service:
             self.bracket_service = BracketService(aggregator=None, guardian=None)

        try:
            plans = self.bracket_service.evaluate_all(
                positions=norm_positions,
                orders=norm_orders,
                cfg=rules_cfg,
                guardian_meta=bracket_metas,
            )

            for plan in plans:
                # Log evaluation details for debugging
                if plan.severity != "INFO":
                    logger.debug(
                        "Bracket plan evaluated by watchdog",
                        extra={
                            "symbol": plan.symbol,
                            "side": plan.side,
                            "severity": plan.severity,
                            "why": plan.why,
                            "actions": [a.action_type for a in plan.actions],
                        },
                    )

                # Convert actionable plans to recommendations
                if plan.severity in ("WARN", "ALERT") or plan.has_actions:
                    recs.extend(self._plan_to_recommendations(plan))

        except Exception as e:
            logger.error("Watchdog BracketService evaluation failed",
                         exc_info=True, extra={"error": str(e)})

        return recs

    def _plan_to_recommendations(self, plan: BracketPlan) -> List[WatchdogRecommendation]:
        recs: List[WatchdogRecommendation] = []

        # If there are specific actions, map them
        for action in plan.actions:
            # Map severity to action type
            # ALERT -> SUPPRESS (stop trading/fix immediately)
            # WARN -> FORCE_SNAPSHOT (refresh state/minor fix)
            recommended_action = WatchdogAction.SUPPRESS_BRACKETS if plan.severity == "ALERT" else WatchdogAction.FORCE_SNAPSHOT

            recs.append(
                WatchdogRecommendation(
                    symbol=plan.symbol,
                    side=plan.side,
                    kind=plan.severity,
                    action=recommended_action,
                    target_id=action.order_id,
                    reason=plan.why, # Use plan-level why for context
                    orders_to_cancel=[
                        action.order_id] if action.order_id else [],
                    details={
                        "action_type": action.action_type,
                        "why": action.why, # Specific action why
                        "price": str(action.price) if action.price else None,
                        "qty": str(action.qty) if action.qty else None
                    },
                )
            )

        # If no actions but severity is high (e.g. ambiguous state), emit a general recommendation
        if not plan.actions and plan.severity in ("WARN", "ALERT"):
            recommended_action = WatchdogAction.SUPPRESS_BRACKETS if plan.severity == "ALERT" else WatchdogAction.NONE
            recs.append(
                WatchdogRecommendation(
                    symbol=plan.symbol,
                    side=plan.side,
                    kind=plan.severity,
                    action=recommended_action,
                    target_id=None,
                    reason=plan.why,
                    orders_to_cancel=[],
                    details={},
                )
            )
        return recs

    def _get_rules_cfg(self) -> BracketRulesConfig:
        cfg_root = self.cfg.get("aggregated_oco", {}) if isinstance(
            self.cfg, dict) else {}
        return BracketRulesConfig(
            enabled=cfg_root.get("enabled", True),
            allow_unprotected_position=cfg_root.get(
                "allow_unprotected_position", False),
            recalc_on_partial_close=cfg_root.get(
                "recalc_on_partial_close", True),
            recalc_on_scale_in=cfg_root.get("recalc_on_scale_in", True),
            ttl_protect_new_bracket_ms=cfg_root.get(
                "ttl_protect_new_bracket_ms", 5000),
            max_tp_legs=cfg_root.get("max_tp_legs", 1),
            max_sl_legs=cfg_root.get("max_sl_legs", 1),
            sl_pct=cfg_root.get("sl_pct", 0.02),
            tp_rr=cfg_root.get("tp_rr", 2.0),
        )
