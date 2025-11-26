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

        norm_positions = self._normalize_positions(positions or [])
        norm_orders = self._normalize_orders(open_orders or [])

        # If bracket_service is provided, try its evaluation first (for INFO/WARN/ALERT plans)
        recs: List[WatchdogRecommendation] = []
        if hasattr(self.bracket_service, "evaluate_all"):
            try:
                plans = self.bracket_service.evaluate_all(
                    positions=norm_positions,
                    orders=norm_orders,
                    cfg=rules_cfg,
                    guardian_meta=bracket_metas,
                )
                for plan in plans:
                    logger.debug(
                        "Bracket plan evaluated by watchdog",
                        extra={
                            "symbol": getattr(plan, "symbol", None),
                            "side": getattr(plan, "side", None),
                            "severity": getattr(plan, "severity", None),
                            "why": getattr(plan, "why", None),
                            "actions": [getattr(a, "action_type", None) for a in getattr(plan, "actions", [])],
                        },
                    )
                    if getattr(plan, "severity", None) in ("WARN", "ALERT"):
                        recs.extend(self._plan_to_recommendations(plan))
                if recs:
                    return recs
            except Exception as e:
                logger.error("Watchdog BracketService evaluation failed",
                             exc_info=True, extra={"error": str(e)})

        # Index stops by symbol (using OrderView attributes)
        stop_orders_by_symbol: Dict[str, List[OrderView]] = {}
        for order in norm_orders:
            is_stop = order.stop_price is not None or order.order_type.startswith(
                "STOP")
            if is_stop:
                stop_orders_by_symbol.setdefault(
                    order.symbol, []).append(order)

        position_symbols = {p.symbol for p in norm_positions}

        # Orphan stops (no corresponding position)
        for order in norm_orders:
            is_stop = order.stop_price is not None or order.order_type.startswith(
                "STOP")
            if is_stop and order.symbol not in position_symbols:
                recs.append(
                    WatchdogRecommendation(
                        symbol=order.symbol,
                        side=order.side,
                        kind="WARN",
                        action=WatchdogAction.FORCE_SNAPSHOT,
                        target_id=order.order_id,
                        reason="orphan_stop_order",
                        orders_to_cancel=[
                            order.order_id] if order.order_id else [],
                        details={"action_type": order.order_type},
                    )
                )

        # Evaluate each position
        for pos in norm_positions:
            symbol = pos.symbol
            side = pos.side
            pos_stop_orders = stop_orders_by_symbol.get(symbol, [])

            # Match stops by opposite side
            opposite_side = "SELL" if side == "LONG" else "BUY"
            valid_stops = [
                o for o in pos_stop_orders
                if o.order_type in {"STOP_MARKET", "STOP", "STOP_LOSS", "STOP_LOSS_MARKET"}
                and o.side == opposite_side
            ]
            invalid_stops = [
                o for o in pos_stop_orders
                if o.order_type not in {"STOP_MARKET", "STOP", "STOP_LOSS", "STOP_LOSS_MARKET"}
                and o.side == opposite_side
            ]

            if not valid_stops:
                recs.append(
                    WatchdogRecommendation(
                        symbol=symbol,
                        side=side,
                        kind="ALERT",
                        action=WatchdogAction.ALERT,
                        target_id=None,
                        reason="missing_sl",
                        orders_to_cancel=[],
                        details={},
                    )
                )
            elif len(valid_stops) > 1:
                # Keep first, cancel extras
                extra_ids = [o.order_id for o in valid_stops[1:] if o.order_id]
                recs.append(
                    WatchdogRecommendation(
                        symbol=symbol,
                        side=side,
                        kind="WARN",
                        action=WatchdogAction.SUPPRESS_BRACKETS,
                        target_id=None,
                        reason="too_many_sl",
                        orders_to_cancel=extra_ids,
                        details={},
                    )
                )

            # Invalid stop types with stop_price present
            for o in invalid_stops:
                oid = o.order_id
                recs.append(
                    WatchdogRecommendation(
                        symbol=symbol,
                        side=side,
                        kind="WARN",
                        action=WatchdogAction.SUPPRESS_BRACKETS,
                        target_id=oid,
                        reason="invalid_stop_type",
                        orders_to_cancel=[oid] if oid else [],
                        details={"action_type": o.order_type},
                    )
                )

        return recs

    def _normalize_positions(self, raw_positions: List[Dict[str, Any]]) -> List[PositionView]:
        views: List[PositionView] = []
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
            entry = raw.get("entryPrice") or raw.get("avg_price") or raw.get(
                "avg_entry_price") or raw.get("entry_price") or 0
            try:
                entry_price = Decimal(str(entry)) if entry else Decimal("0")
                # PositionView requires entry_price > 0 when qty > 0
                if entry_price <= 0:
                    # Fallback to avoid validation error
                    entry_price = Decimal("1")
                views.append(
                    PositionView(
                        symbol=symbol,
                        side=side,
                        qty=abs(qty),
                        avg_entry_price=entry_price,
                    )
                )
            except Exception:
                continue
        return views

    def _normalize_orders(self, raw_orders: List[Dict[str, Any]]) -> List[OrderView]:
        views: List[OrderView] = []
        for raw in raw_orders:
            try:
                order_id = raw.get("orderId") or raw.get(
                    "order_id") or raw.get("clientOrderId")
                if not order_id:
                    continue
                symbol = str(raw.get("symbol", "")).upper()
                if not symbol:
                    continue
                side = str(raw.get("side", "")).upper() or "BUY"
                order_type = raw.get("type") or raw.get(
                    "order_type") or "LIMIT"
                qty = Decimal(str(raw.get("quantity") or raw.get(
                    "origQty") or raw.get("qty") or 0))
                price = raw.get("price")
                stop_price = raw.get("stopPrice") or raw.get("stop_price")
                reduce_only = bool(raw.get("reduce_only")
                                   or raw.get("reduceOnly", False))
                close_position = bool(
                    raw.get("close_position") or raw.get("closePosition", False))
                status = str(raw.get("status") or "NEW")
                created_ts = float(raw.get("created_ts")
                                   or raw.get("time") or 0)
                update_ts = float(raw.get("update_ts") or raw.get(
                    "updateTime") or created_ts)

                views.append(
                    OrderView(
                        order_id=str(order_id),
                        client_order_id=str(raw.get("clientOrderId") or raw.get(
                            "client_order_id") or order_id),
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        qty=qty,
                        price=Decimal(str(price)) if price not in (
                            None, "") else None,
                        stop_price=Decimal(str(stop_price)) if stop_price not in (
                            None, "") else None,
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
                    orders_to_cancel=[
                        action.order_id] if action.order_id else [],
                    details={"action_type": action.action_type,
                             "why": action.why},
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
