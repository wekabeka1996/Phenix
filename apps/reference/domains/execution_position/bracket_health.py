import asyncio
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from apps.reference.core.time import get_clock
from apps.reference.domains.execution_position.bracket_math import compute_bracket_targets
from apps.reference.domains.execution_position.fsm_manage import ManageState
from apps.reference.domains.execution_position.utils import (
    coerce_exchange_bool,
    generate_client_order_id,
    opposite_side,
    quantize_stop_price,
)

if TYPE_CHECKING:
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

LOG = logging.getLogger(__name__)


class BracketHealth:
    def __init__(self, fsm: "ExecPosFSM") -> None:
        self._fsm = fsm
        self._bracket_health_started = False

    def schedule_bracket_health_check(self) -> None:
        """Schedule the bracket health loop once the shared async runtime is ready."""
        if self._bracket_health_started:
            return

        try:
            cfg = self._fsm.config.domains.execution_position.bracket_health_check
        except (AttributeError, TypeError):
            cfg = None

        if cfg is None:
            return
        try:
            if not bool(cfg.enabled):
                return
        except AttributeError:
            return

        loop = self._fsm._get_async_loop()
        if not loop:
            LOG.debug("[BRACKET-HEALTH] deferred: no event loop active")
            return

        self._fsm._submit_async(self._bracket_health_loop(), loop)
        self._bracket_health_started = True
        LOG.info(
            "[BRACKET-HEALTH] scheduled (interval=%ss, grace=%sms)",
            int(cfg.interval_sec),
            int(cfg.grace_period_ms),
        )

    async def _bracket_health_loop(self) -> None:
        """Periodic safety net for missing SL/TP brackets."""
        try:
            cfg = self._fsm.config.domains.execution_position.bracket_health_check
        except (AttributeError, TypeError):
            return

        if cfg is None:
            return
        try:
            if not bool(cfg.enabled):
                return
        except AttributeError:
            return

        while True:
            try:
                await get_clock().sleep_sec(float(cfg.interval_sec))
                await self._run_bracket_health_check(cfg)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                LOG.warning(f"[BRACKET-HEALTH] loop error: {e}")

    async def _run_bracket_health_check(self, cfg: Any) -> None:
        """Check live positions and re-arm missing SL/TP brackets when safe."""
        if not self._fsm.adapter:
            return

        try:
            positions = await self._fsm.adapter.get_open_positions()
        except Exception as e:
            LOG.warning(f"[BRACKET-HEALTH] failed to get positions: {e}")
            return

        if not positions:
            return

        current_time_ms = get_clock().now_ms()
        placements_this_cycle = 0

        for pos in positions:
            if placements_this_cycle >= int(cfg.max_placements_per_cycle):
                break

            if hasattr(pos, "to_dict"):
                pos_dict = pos.to_dict()
            elif isinstance(pos, dict):
                pos_dict = pos
            else:
                pos_dict = pos.__dict__ if hasattr(pos, "__dict__") else {}

            symbol = str(pos_dict.get("symbol") or "")
            if not symbol:
                continue

            try:
                position_amt = float(
                    pos_dict.get("net_position")
                    or pos_dict.get("positionAmt")
                    or pos_dict.get("position_amount")
                    or 0.0
                )
            except Exception:
                position_amt = 0.0
            if abs(position_amt) < 1e-10:
                continue

            entry_price_raw = pos_dict.get(
                "entryPrice") or pos_dict.get("entry_price")
            try:
                entry_price = float(entry_price_raw or 0.0)
            except Exception:
                entry_price = 0.0
            if entry_price <= 0.0:
                continue

            update_time_ms = int(
                pos_dict.get("updateTime") or pos_dict.get(
                    "update_time_ms") or 0
            )
            if update_time_ms > 0 and (current_time_ms - update_time_ms) < int(cfg.grace_period_ms):
                continue

            has_sl, has_tp = await self._check_brackets_on_exchange(symbol)
            if has_sl and has_tp:
                continue

            side = "BUY" if position_amt > 0 else "SELL"
            owner_context = self._resolve_health_check_bracket_context(
                symbol=symbol,
                entry_price=entry_price,
                side=side,
            )
            sl_price = owner_context.get("sl_price")
            tp_price = owner_context.get("tp_price")
            if sl_price is None or tp_price is None:
                self._fsm._bracket_ownership.append_bracket_ownership_record(
                    event_type="EXECUTION_BRACKET_RECOVERY_SKIPPED",
                    symbol=symbol,
                    placement_path="recovery",
                    strategy_id=owner_context.get("strategy_id"),
                    strategy_source=owner_context.get("strategy_source"),
                    owner_status=str(owner_context.get(
                        "owner_status") or "missing"),
                    detail=owner_context.get("detail"),
                    assigned_strategies=owner_context.get(
                        "assigned_strategies"),
                    lifecycle_active=self._fsm._has_active_lifecycle_for_symbol(
                        symbol),
                )
                continue

            placed = await self._place_health_check_brackets(
                symbol=symbol,
                side=side,
                sl_price=sl_price,
                tp_price=tp_price,
                need_sl=not has_sl,
                need_tp=not has_tp,
                owner_context=owner_context,
            )
            if placed:
                placements_this_cycle += 1

    async def _check_brackets_on_exchange(self, symbol: str) -> Tuple[bool, bool]:
        """Inspect exchange open orders and detect existing SL/TP brackets."""
        try:
            if hasattr(self._fsm.adapter, "_request"):
                raw_orders = await self._fsm.adapter._request(
                    "GET", "/fapi/v1/openOrders", {"symbol": symbol}
                )
            else:
                raw_orders = await self._fsm.adapter.get_open_orders(symbol)
        except Exception as e:
            LOG.warning(
                f"[BRACKET-HEALTH] failed to inspect open orders for {symbol}: {e}")
            return True, True

        has_sl = False
        has_tp = False
        for order in raw_orders or []:
            if hasattr(order, "to_dict"):
                order_dict = order.to_dict()
            elif isinstance(order, dict):
                order_dict = order
            else:
                order_dict = order.__dict__ if hasattr(
                    order, "__dict__") else {}

            order_type = str(order_dict.get("type") or "").upper()
            reduce_only_raw = order_dict.get("reduceOnly", False)
            close_position_raw = order_dict.get("closePosition", False)
            reduce_only = coerce_exchange_bool(reduce_only_raw)
            close_position = coerce_exchange_bool(close_position_raw)

            if order_type == "STOP_MARKET" and (reduce_only or close_position):
                has_sl = True
            if order_type == "TAKE_PROFIT_MARKET" and (reduce_only or close_position):
                has_tp = True

        return has_sl, has_tp

    def _resolve_health_check_bracket_context(
        self,
        *,
        symbol: str,
        entry_price: float,
        side: str,
    ) -> Dict[str, Any]:
        context = dict(
            self._fsm._bracket_ownership.resolve_strategy_owner_for_recovery(symbol=symbol))
        context.setdefault("assigned_strategies",
                           self._fsm._bracket_ownership._strategy_assignments_for_symbol(symbol))
        context["sl_price"] = None
        context["tp_price"] = None
        strategy_id = str(context.get("strategy_id") or "").strip()
        if context.get("owner_status") != "resolved" or not strategy_id:
            return context

        regime = str(self._fsm._last_regime_by_symbol.get(symbol) or "DEFAULT")
        sl_price, tp_price, detail = self._compute_strategy_health_check_brackets(
            symbol=symbol,
            entry_price=entry_price,
            side=side,
            strategy_id=strategy_id,
            regime=regime,
        )
        if sl_price is None or tp_price is None:
            current_detail = str(context.get("detail") or "").strip()
            if detail:
                context["detail"] = f"{current_detail};{detail}" if current_detail else detail
            return context

        context["sl_price"] = sl_price
        context["tp_price"] = tp_price
        return context

    def _compute_strategy_health_check_brackets(
        self,
        *,
        symbol: str,
        entry_price: float,
        side: str,
        strategy_id: str,
        regime: str,
    ) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """Compute recovery brackets from the explicit strategy owner for the symbol."""
        try:
            sl_pct_eff: Optional[float] = None
            tp_rr_eff: Optional[float] = None

            if strategy_id == "md_amr" and getattr(self._fsm.config.strategies, "md_amr", None) is not None:
                strategy_cfg = self._fsm.config.strategies.md_amr
                asset_cfg = strategy_cfg.assets.get(symbol) if isinstance(
                    strategy_cfg.assets, dict) else None
                exit_cfg = getattr(asset_cfg, "exit",
                                   None) if asset_cfg is not None else None
                if exit_cfg is not None and getattr(exit_cfg, "sl_pct", None) is not None and getattr(exit_cfg, "tp_rr", None) is not None:
                    sl_pct_eff = float(exit_cfg.sl_pct)
                    tp_rr_eff = float(exit_cfg.tp_rr)
                    regime_tpsl = getattr(exit_cfg, "regime_tpsl", None)
                    try:
                        regime_tpsl_enabled = bool(
                            regime_tpsl.enabled) if regime_tpsl is not None else False
                    except AttributeError:
                        regime_tpsl_enabled = False
                    if regime_tpsl_enabled:
                        sl_mult = float((getattr(regime_tpsl, "sl_mult", {}) or {}).get(
                            regime, (getattr(regime_tpsl, "sl_mult", {}) or {}).get("DEFAULT", 1.0)))
                        tp_mult = float((getattr(regime_tpsl, "tp_mult", {}) or {}).get(
                            regime, (getattr(regime_tpsl, "tp_mult", {}) or {}).get("DEFAULT", 1.0)))
                        sl_pct_eff = sl_pct_eff * sl_mult
                        tp_rr_eff = tp_rr_eff * tp_mult
                        if getattr(regime_tpsl, "min_sl_pct", None) is not None:
                            sl_pct_eff = max(
                                float(regime_tpsl.min_sl_pct), sl_pct_eff)
                        if getattr(regime_tpsl, "max_sl_pct", None) is not None:
                            sl_pct_eff = min(
                                float(regime_tpsl.max_sl_pct), sl_pct_eff)
                        if getattr(regime_tpsl, "min_tp_rr", None) is not None:
                            tp_rr_eff = max(
                                float(regime_tpsl.min_tp_rr), tp_rr_eff)
                        if getattr(regime_tpsl, "max_tp_rr", None) is not None:
                            tp_rr_eff = min(
                                float(regime_tpsl.max_tp_rr), tp_rr_eff)
            elif strategy_id == "aurora" and getattr(self._fsm.config.strategies, "aurora", None) is not None:
                strategy_cfg = getattr(self._fsm.config.strategies, "aurora", None)
                asset_cfg = strategy_cfg.assets.get(
                    symbol) if strategy_cfg is not None else None
                exit_cfg = getattr(asset_cfg, "exit",
                                   None) if asset_cfg is not None else None
                tp_cfg = getattr(asset_cfg, "take_profit",
                                 None) if asset_cfg is not None else None
                if exit_cfg is not None and getattr(exit_cfg, "sl_pct", None) is not None and tp_cfg is not None and getattr(tp_cfg, "tp_low_ratio", None) is not None:
                    sl_pct_eff = float(exit_cfg.sl_pct)
                    tp_rr_eff = float(tp_cfg.tp_low_ratio)
                    regime_tpsl = getattr(exit_cfg, "regime_tpsl", None)
                    try:
                        regime_tpsl_enabled = bool(
                            regime_tpsl.enabled) if regime_tpsl is not None else False
                    except AttributeError:
                        regime_tpsl_enabled = False
                    regime_tpsl_mode = str(
                        getattr(regime_tpsl, "mode", "")) if regime_tpsl is not None else ""
                    if regime_tpsl_enabled and regime_tpsl_mode == "pct_mult":
                        sl_mult = float((getattr(regime_tpsl, "sl_mult", {}) or {}).get(
                            regime, (getattr(regime_tpsl, "sl_mult", {}) or {}).get("DEFAULT", 1.0)))
                        tp_mult = float((getattr(regime_tpsl, "tp_mult", {}) or {}).get(
                            regime, (getattr(regime_tpsl, "tp_mult", {}) or {}).get("DEFAULT", 1.0)))
                        sl_pct_eff = sl_pct_eff * sl_mult
                        tp_rr_eff = tp_rr_eff * tp_mult
                        if getattr(regime_tpsl, "min_sl_pct", None) is not None:
                            sl_pct_eff = max(
                                float(regime_tpsl.min_sl_pct), sl_pct_eff)
                        if getattr(regime_tpsl, "max_sl_pct", None) is not None:
                            sl_pct_eff = min(
                                float(regime_tpsl.max_sl_pct), sl_pct_eff)
                        if getattr(regime_tpsl, "min_tp_rr", None) is not None:
                            tp_rr_eff = max(
                                float(regime_tpsl.min_tp_rr), tp_rr_eff)
                        if getattr(regime_tpsl, "max_tp_rr", None) is not None:
                            tp_rr_eff = min(
                                float(regime_tpsl.max_tp_rr), tp_rr_eff)
            elif strategy_id == "mean_reversion":
                return None, None, "unsupported_recovery_strategy:mean_reversion"
            else:
                return None, None, f"unsupported_recovery_strategy:{strategy_id}"

            if sl_pct_eff is None or tp_rr_eff is None:
                return None, None, f"recovery_exit_profile_missing:{strategy_id}"

            instrument_spec = self._fsm.config.instruments.get(symbol)
            tick_size = Decimal(str(instrument_spec.tick_size)
                                ) if instrument_spec is not None else Decimal("0.01")

            recovery_targets = compute_bracket_targets(
                reference_price=entry_price,
                position_side=side,
                sl_pct=sl_pct_eff,
                tp_low_ratio=tp_rr_eff,
            )

            return (
                float(quantize_stop_price(float(recovery_targets.sl_price), float(tick_size),
                      side="SELL" if side == "BUY" else "BUY")),
                float(quantize_stop_price(float(recovery_targets.tp1_price), float(tick_size),
                      side="BUY" if side == "BUY" else "SELL")),
                None,
            )
        except Exception as e:
            LOG.warning(
                f"[BRACKET-HEALTH] failed to compute recovery brackets for {symbol}: {e}")
            return None, None, f"recovery_compute_error:{strategy_id}"

    def _compute_health_check_brackets(
        self,
        *,
        symbol: str,
        entry_price: float,
        side: str,
    ) -> Tuple[Optional[float], Optional[float]]:
        context = self._resolve_health_check_bracket_context(
            symbol=symbol,
            entry_price=entry_price,
            side=side,
        )
        return context.get("sl_price"), context.get("tp_price")

    async def _place_health_check_brackets(
        self,
        *,
        symbol: str,
        side: str,
        sl_price: float,
        tp_price: float,
        need_sl: bool,
        need_tp: bool,
        owner_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Place only the missing recovery brackets and register them with current owners."""
        if not self._fsm.adapter or not self._fsm.order_guardian:
            return False

        if not await self._fsm._preflight_position_check(symbol):
            return False

        bracket_side = opposite_side(side)
        parent_order_id = f"health_check:{symbol}"
        placed = False
        owner_context = dict(owner_context or {})

        if need_sl:
            try:
                sl_client_id = generate_client_order_id("BHSL", symbol)
                sl_resp = await self._fsm.adapter.place_stop_market_close_position(
                    symbol,
                    bracket_side,
                    str(sl_price),
                    new_client_order_id=sl_client_id,
                )
                sl_order_id = str(
                    sl_resp.get("orderId", "")
                    if isinstance(sl_resp, dict)
                    else getattr(sl_resp, "order_id", "")
                )
                if sl_order_id:
                    self._fsm._set_symbol_bracket_order(
                        symbol,
                        order_role="SL",
                        order_id=sl_order_id,
                    )
                    self._fsm.order_guardian.register_bracket(
                        symbol=symbol,
                        parent_order_id=parent_order_id,
                        order_id=sl_order_id,
                        client_order_id=sl_client_id,
                        kind="SL",
                        corr_id="bracket_health",
                        rid="bracket_health",
                    )
                    placed = True
            except Exception as e:
                LOG.warning(
                    f"[BRACKET-HEALTH] SL recovery failed for {symbol}: {e}")

        if need_tp:
            try:
                tp_client_id = generate_client_order_id("BHTP", symbol)
                tp_resp = await self._fsm.adapter.place_take_profit_market_close_position(
                    symbol,
                    bracket_side,
                    str(tp_price),
                    new_client_order_id=tp_client_id,
                )
                tp_order_id = str(
                    tp_resp.get("orderId", "")
                    if isinstance(tp_resp, dict)
                    else getattr(tp_resp, "order_id", "")
                )
                if tp_order_id:
                    self._fsm._set_symbol_bracket_order(
                        symbol,
                        order_role="TP",
                        order_id=tp_order_id,
                    )
                    self._fsm.order_guardian.register_bracket(
                        symbol=symbol,
                        parent_order_id=parent_order_id,
                        order_id=tp_order_id,
                        client_order_id=tp_client_id,
                        kind="TP",
                        corr_id="bracket_health",
                        rid="bracket_health",
                    )
                    placed = True
            except Exception as e:
                LOG.warning(
                    f"[BRACKET-HEALTH] TP recovery failed for {symbol}: {e}")

        if placed:
            lifecycle_active = self._fsm._has_active_lifecycle_for_symbol(symbol)
            owner_snapshot = self._fsm._bracket_ownership.remember_bracket_owner(
                symbol=symbol,
                strategy_id=owner_context.get("strategy_id"),
                strategy_source=owner_context.get("strategy_source"),
                owner_status=str(owner_context.get(
                    "owner_status") or "resolved"),
                detail=owner_context.get("detail"),
                assigned_strategies=owner_context.get("assigned_strategies"),
                placement_path="recovery",
                lifecycle_active=lifecycle_active,
            )
            manage_flow = self._fsm.manage_flows.get(symbol)
            # GUARD: Only sync bracket IDs into ManageFlowFSM when a real lifecycle
            # is active (state != FLAT). Injecting bracket IDs into a FLAT FSM corrupts
            # has_active_lifecycle() truth, causing a self-reinforcing OPEN_GUARD_FAIL loop.
            # The bracket IDs remain in _symbol_brackets for external observability.
            if manage_flow is not None and manage_flow.state != ManageState.FLAT:
                brackets = self._fsm._symbol_brackets.get(symbol, {})
                manage_flow.set_bracket_ids(
                    brackets.get("sl_order_id"),
                    brackets.get("tp_order_id"),
                )
            self._fsm._emit_observability_event(
                "BRACKET_HEALTH_REARMED",
                {
                    "symbol": symbol,
                    "need_sl": bool(need_sl),
                    "need_tp": bool(need_tp),
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                },
            )
            self._fsm._bracket_ownership.append_bracket_ownership_record(
                event_type="EXECUTION_BRACKET_RECOVERY_PLACED",
                symbol=symbol,
                placement_path="recovery",
                strategy_id=owner_snapshot.get("strategy_id"),
                strategy_source=owner_snapshot.get("strategy_source"),
                owner_status=str(owner_snapshot.get(
                    "owner_status") or "resolved"),
                detail=owner_snapshot.get("detail"),
                assigned_strategies=owner_snapshot.get("assigned_strategies"),
                lifecycle_active=lifecycle_active,
                sl_order_id=(self._fsm._symbol_brackets.get(
                    symbol, {}) or {}).get("sl_order_id"),
                tp_order_id=(self._fsm._symbol_brackets.get(
                    symbol, {}) or {}).get("tp_order_id"),
            )

        return placed

    # Phase 14.2: _initialize_adapter
    #  extracted to AdapterInitMixin (adapter_init.py)

