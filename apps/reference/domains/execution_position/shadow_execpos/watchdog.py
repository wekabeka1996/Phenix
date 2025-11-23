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
    BracketPlan,
    PositionView as BracketPositionView,
    OrderView as BracketOrderView,
)

# Legacy constants retained for test compatibility (no longer used internally)
NO_SL_FOR_OPEN_POSITION = "NO_SL_FOR_OPEN_POSITION"
ORPHAN_SL_FOR_ZERO_POSITION = "ORPHAN_SL_FOR_ZERO_POSITION"
MULTIPLE_META_SETS = "MULTIPLE_META_SETS"
TOO_MANY_SL_FOR_OPEN_POSITION = "TOO_MANY_SL_FOR_OPEN_POSITION"

logger = logging.getLogger(__name__)


class AggOcoWatchdogService:
    """
    Detect-only watchdog backed by BracketService.
    """

    def __init__(self, bracket_service: Optional[BracketService] = None, cfg: Optional[Dict[str, Any]] = None):
        self.bracket_service = bracket_service or BracketService(aggregator=None, guardian=None, watchdog=None)  # guardian None in V2
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

        norm_positions = self._normalize_positions(positions or [])
        norm_orders = self._normalize_orders(open_orders or [])

        try:
            plans = self.bracket_service.evaluate_all(
                positions=norm_positions,
                orders=norm_orders,
                cfg=rules_cfg,
                guardian_meta=bracket_metas,
            )
        except Exception as e:
            logger.error("Watchdog BracketService evaluation failed", exc_info=True, extra={"error": str(e)})
            return []

        recs: List[WatchdogRecommendation] = []
        for plan in plans:
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
            if plan.severity in ("WARN", "ALERT"):
                recs.extend(self._plan_to_recommendations(plan))

        return recs

    def _normalize_positions(self, raw_positions: List[Dict[str, Any]]) -> List[BracketPositionView]:
        views: List[BracketPositionView] = []
        for raw in raw_positions:
            if raw is None:
                continue
            symbol = str(raw.get("symbol", "")).upper()
            if not symbol:
                continue
            qty = None
            for key in ["positionAmt", "position_amt", "qty", "quantity", "position_size"]:
                if key in raw:
                    try:
                        qty = Decimal(str(raw[key]))
                        break
                    except Exception:
                        qty = None
            if qty is None:
                continue
            if abs(qty) < Decimal("0.0001"):
                continue
            side = "LONG" if qty > 0 else "SHORT"
            entry = raw.get("entryPrice") or raw.get("avg_price") or raw.get("avg_entry_price") or raw.get("entry_price") or 0
            try:
                views.append(
                    BracketPositionView(
                        symbol=symbol,
                        side=side,
                        qty=abs(qty),
                        avg_entry_price=Decimal(str(entry)),
                    )
                )
            except Exception:
                continue
        return views

    def _normalize_orders(self, raw_orders: List[Dict[str, Any]]) -> List[BracketOrderView]:
        views: List[BracketOrderView] = []
        for raw in raw_orders:
            try:
                order_id = raw.get("orderId") or raw.get("order_id") or raw.get("clientOrderId")
                if not order_id:
                    continue
                symbol = str(raw.get("symbol", "")).upper()
                if not symbol:
                    continue
                side = str(raw.get("side", "")).upper() or "BUY"
                order_type = raw.get("type") or raw.get("order_type") or "LIMIT"
                qty = Decimal(str(raw.get("quantity") or raw.get("origQty") or raw.get("qty") or 0))
                price = raw.get("price")
                stop_price = raw.get("stopPrice") or raw.get("stop_price")
                reduce_only = bool(raw.get("reduce_only") or raw.get("reduceOnly", False))
                close_position = bool(raw.get("close_position") or raw.get("closePosition", False))
                status = str(raw.get("status") or "NEW")
                created_ts = float(raw.get("created_ts") or raw.get("time") or 0)
                update_ts = float(raw.get("update_ts") or raw.get("updateTime") or created_ts)

                views.append(
                    BracketOrderView(
                        order_id=str(order_id),
                        client_order_id=str(raw.get("clientOrderId") or raw.get("client_order_id") or order_id),
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        qty=qty,
                        price=Decimal(str(price)) if price not in (None, "") else None,
                        stop_price=Decimal(str(stop_price)) if stop_price not in (None, "") else None,
                        reduce_only=reduce_only,
                        close_position=close_position,
                        status=status,
                        created_ts=created_ts,
                        update_ts=update_ts,
                    )
                )
            except Exception:
                continue
        return views

    def _plan_to_recommendations(self, plan: BracketPlan) -> List[WatchdogRecommendation]:
        recs: List[WatchdogRecommendation] = []
        for action in plan.actions:
            recommended_action = WatchdogAction.SUPPRESS_BRACKETS if plan.severity == "ALERT" else WatchdogAction.FORCE_SNAPSHOT
            recs.append(
                WatchdogRecommendation(
                    symbol=plan.symbol,
                    side=plan.side,
                    kind=plan.severity,
                    action=recommended_action,
                    target_id=action.order_id,
                    reason=plan.why,
                    orders_to_cancel=[action.order_id] if action.order_id else [],
                    details={"action_type": action.action_type, "why": action.why},
                )
            )
        if not plan.actions:
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
        cfg_root = self.cfg.get("aggregated_oco", {}) if isinstance(self.cfg, dict) else {}
        return BracketRulesConfig(
            enabled=cfg_root.get("enabled", True),
            allow_unprotected_position=cfg_root.get("allow_unprotected_position", False),
            recalc_on_partial_close=cfg_root.get("recalc_on_partial_close", True),
            recalc_on_scale_in=cfg_root.get("recalc_on_scale_in", True),
            ttl_protect_new_bracket_ms=cfg_root.get("ttl_protect_new_bracket_ms", 5000),
            max_tp_legs=cfg_root.get("max_tp_legs", 1),
            max_sl_legs=cfg_root.get("max_sl_legs", 1),
            sl_pct=cfg_root.get("sl_pct", 0.02),
            tp_rr=cfg_root.get("tp_rr", 2.0),
        )
