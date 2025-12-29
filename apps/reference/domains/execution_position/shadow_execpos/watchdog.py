"""
AggOco Watchdog (V2) — detect-only layer using Aggregator OCO core.

Phase 11: Removed BracketService dependency, uses cleanup module directly.

Responsibilities:
- Detect orphan brackets (position flat + lingering SL/TP)
- Detect bracket gaps (position exists but missing SL/TP)
- Surface severities (INFO/WARN/ALERT) via metrics/logs.

Non-responsibilities:
- No TP/SL math (delegated to core_math).
- No auto-heal, no adapter calls, no OrderGuardian mutations.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .types import WatchdogAction, WatchdogRecommendation

# Phase 11: Import from contract layer (no bracket_service dependency)
from ..aggregator_oco.view_types import PositionView, OrderView
from ..aggregator_oco.contracts import BracketPlan, BracketConfig, AggregatorInput, PositionSnapshot, OrderSnapshot
from ..aggregator_oco.cleanup import plan_orphan_cleanup
from ..aggregator_oco.engine import compute_bracket_plan_from_views

from .converters import normalize_positions, normalize_orders

logger = logging.getLogger(__name__)


# ============================================================================
# Watchdog Configuration (matches legacy BracketRulesConfig interface)
# ============================================================================

class WatchdogConfig:
    """Configuration for watchdog analysis."""

    def __init__(
        self,
        enabled: bool = True,
        allow_unprotected_position: bool = False,
        sl_pct: float = 0.02,
        tp_rr: float = 2.0,
        max_tp_legs: int = 1,
        max_sl_legs: int = 1,
    ):
        self.enabled = enabled
        self.allow_unprotected_position = allow_unprotected_position
        self.sl_pct = sl_pct
        self.tp_rr = tp_rr
        self.max_tp_legs = max_tp_legs
        self.max_sl_legs = max_sl_legs


class AggOcoWatchdogService:
    """
    Detect-only watchdog using Aggregator OCO core modules.

    Phase 11: No BracketService dependency.
    """

    def __init__(self, cfg: Optional[Dict[str, Any]] = None, bracket_service: Any = None):
        self.cfg = cfg or {}
        # Legacy compatibility: accept bracket_service but ignore it
        self.bracket_service = None  # DEPRECATED - not used

    def analyze(
        self,
        open_orders: List[Dict[str, Any]],
        positions: List[Dict[str, Any]],
        bracket_metas: Optional[Any] = None
    ) -> List[WatchdogRecommendation]:
        """
        Evaluate all symbols/sides and return recommendations (detect-only).
        """
        try:
            watchdog_cfg = self._get_watchdog_cfg()
        except Exception:
            return []

        # If disabled, skip
        if not watchdog_cfg.enabled:
            return []

        norm_positions = normalize_positions(positions or [])
        norm_orders = normalize_orders(open_orders or [])

        recs: List[WatchdogRecommendation] = []

        try:
            # Group orders by symbol
            orders_by_symbol: Dict[str, List[OrderView]] = {}
            for order in norm_orders:
                orders_by_symbol.setdefault(order.symbol, []).append(order)

            # Group positions by symbol
            positions_by_symbol: Dict[str, PositionView] = {}
            for pos in norm_positions:
                positions_by_symbol[pos.symbol] = pos

            # Get all symbols from both positions and orders
            all_symbols = set(orders_by_symbol.keys()) | set(
                positions_by_symbol.keys())

            for symbol in all_symbols:
                pos = positions_by_symbol.get(symbol)
                symbol_orders = orders_by_symbol.get(symbol, [])

                # Check for orphan brackets (no position but has brackets)
                if pos is None or pos.qty == 0:
                    orphan_plan = plan_orphan_cleanup(symbol, symbol_orders)
                    if orphan_plan.actions:
                        recs.extend(self._plan_to_recommendations(orphan_plan))
                    continue

                # Position exists - check for missing brackets
                bracket_cfg = BracketConfig(
                    sl_pct=Decimal(str(watchdog_cfg.sl_pct)),
                    tp_rr=Decimal(str(watchdog_cfg.tp_rr)),
                )

                try:
                    plan = compute_bracket_plan_from_views(
                        pos_view=pos,
                        order_views=symbol_orders,
                        cfg=bracket_cfg,
                        symbol=symbol,
                        side=pos.side,
                    )

                    # Only report non-INFO severity or plans with actions
                    if plan.severity in ("WARN", "ALERT") or plan.actions:
                        recs.extend(self._plan_to_recommendations(plan))

                except Exception as e:
                    logger.debug(
                        f"Watchdog evaluation failed for {symbol}",
                        extra={"error": str(e)},
                    )

        except Exception as e:
            logger.error(
                "Watchdog evaluation failed",
                exc_info=True,
                extra={"error": str(e)},
            )

        return recs

    def _plan_to_recommendations(self, plan: BracketPlan) -> List[WatchdogRecommendation]:
        recs: List[WatchdogRecommendation] = []

        # If there are specific actions, map them
        for action in plan.actions:
            # Map severity to action type
            # ALERT -> SUPPRESS (stop trading/fix immediately)
            # WARN -> FORCE_SNAPSHOT (refresh state/minor fix)
            recommended_action = (
                WatchdogAction.SUPPRESS_BRACKETS
                if plan.severity == "ALERT"
                else WatchdogAction.FORCE_SNAPSHOT
            )

            order_id = action.order_ref or action.client_order_id

            recs.append(
                WatchdogRecommendation(
                    symbol=plan.symbol,
                    side=plan.side,
                    kind=plan.severity,
                    action=recommended_action,
                    target_id=order_id,
                    reason=plan.why,
                    orders_to_cancel=[
                        order_id] if order_id and action.action == "CANCEL" else [],
                    details={
                        "action_type": action.action,
                        "why": action.why,
                        "leg_type": action.leg_type,
                    },
                )
            )

        # If no actions but severity is high (e.g. ambiguous state), emit a general recommendation
        if not plan.actions and plan.severity in ("WARN", "ALERT"):
            recommended_action = (
                WatchdogAction.SUPPRESS_BRACKETS
                if plan.severity == "ALERT"
                else WatchdogAction.NONE
            )
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

    def _get_watchdog_cfg(self) -> WatchdogConfig:
        cfg_root = self.cfg.get("aggregated_oco", {}) if isinstance(
            self.cfg, dict) else {}
        return WatchdogConfig(
            enabled=cfg_root.get("enabled", True),
            allow_unprotected_position=cfg_root.get(
                "allow_unprotected_position", False),
            sl_pct=cfg_root.get("sl_pct", 0.02),
            tp_rr=cfg_root.get("tp_rr", 2.0),
            max_tp_legs=cfg_root.get("max_tp_legs", 1),
            max_sl_legs=cfg_root.get("max_sl_legs", 1),
        )
