"""Bracket placement helper for execution_position.

This module owns TP/SL submission after an entry is accepted. It covers the
immediate market-entry path, the deferred limit-entry path, bounded preflight
position checks, and registration with correlation/order-guardian state.
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional

from apps.reference.core.time import get_clock
from apps.reference.domains.execution_position.utils import (
    generate_client_order_id,
    opposite_side,
    quantize_stop_price,
)

if TYPE_CHECKING:
    from vfoundation.core.fsm_emit_compat import Message

LOG = logging.getLogger(__name__)


class BracketManager:
    """Place and register TP/SL brackets around filled entries."""

    def __init__(self, fsm: Any) -> None:
        self._fsm = fsm

    async def _record_bracket_failure(
        self,
        *,
        symbol: str,
        source_path: str,
        failure_class: str,
        reason: str,
        why_code: str,
        rid: Any = None,
        side: Any = None,
        qty: Any = None,
        entry_order_id: Any = None,
        entry_client_order_id: Any = None,
        strategy_id: Any = None,
        details: Any = None,
        live_position_proven: bool = False,
        remediation_action_override: Optional[str] = None,
    ) -> None:
        handler = getattr(
            self._fsm, "_handle_bracket_protection_missing", None)
        if callable(handler):
            await handler(
                symbol=symbol,
                source_path=source_path,
                failure_class=failure_class,
                reason=reason,
                why_code=why_code,
                rid=rid,
                side=side,
                qty=qty,
                entry_order_id=entry_order_id,
                entry_client_order_id=entry_client_order_id,
                strategy_id=strategy_id,
                details=details,
                live_position_proven=live_position_proven,
                remediation_action_override=remediation_action_override,
            )
            return

        emit = getattr(self._fsm, "_emit_execution_bus_event", None)
        if callable(emit):
            emit(
                "EVT:BRACKET_PLACEMENT_FAILED",
                {
                    "ts_ms": get_clock().now_ms(),
                    "symbol": symbol,
                    "source_path": source_path,
                    "failure_class": failure_class,
                    "reason": reason,
                    "why_code": why_code,
                    "remediation_action": remediation_action_override or (
                        "force_reduce_only_close"
                        if live_position_proven
                        else "position_not_proven_no_close"
                    ),
                    "rid": rid,
                    "side": side,
                    "qty": str(qty) if qty is not None else None,
                    "entry_order_id": str(entry_order_id) if entry_order_id is not None else None,
                    "entry_client_order_id": str(entry_client_order_id) if entry_client_order_id is not None else None,
                    "strategy_id": str(strategy_id) if strategy_id is not None else None,
                    "details": details,
                    "why": "execution:bracket_placement_failed",
                },
            )

    async def _has_live_synced_brackets(self, symbol: str) -> bool:
        """Return True when the current lifecycle already has live synced SL/TP."""
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return False

        try:
            has_active_lifecycle = bool(
                self._fsm._has_active_lifecycle_for_symbol(symbol_key)
            )
        except Exception:
            has_active_lifecycle = False

        if not has_active_lifecycle:
            return False

        bracket_state = dict(
            getattr(self._fsm, "_symbol_brackets", {}).get(symbol_key) or {}
        )
        sl_order_id = str(bracket_state.get("sl_order_id") or "").strip()
        tp_order_id = str(bracket_state.get("tp_order_id") or "").strip()
        if not sl_order_id or not tp_order_id:
            return False

        guardian = getattr(self._fsm, "order_guardian", None)
        get_open_brackets = getattr(guardian, "get_our_open_brackets", None)
        if get_open_brackets is None:
            return False

        try:
            open_brackets = await get_open_brackets(symbol_key)
        except Exception as exc:
            LOG.debug(
                "[LIMIT-DEFERRED] live bracket overlap check failed for %s: %s",
                symbol_key,
                exc,
            )
            return False

        open_order_ids = {
            str(order.get("orderId") or "").strip()
            for order in open_brackets
            if isinstance(order, dict) and str(order.get("orderId") or "").strip()
        }
        if sl_order_id not in open_order_ids or tp_order_id not in open_order_ids:
            return False

        LOG.info(
            "📌 [LIMIT-DEFERRED] Existing live brackets already protect %s, suppressing duplicate placement (SL=%s TP=%s)",
            symbol_key,
            sl_order_id,
            tp_order_id,
        )
        return True

    async def place_brackets_parallel(
        self,
        *,
        symbol: str,
        side: str,
        sl: Any,
        tp: Any,
        qty: str,
        tick_size: float,
        idem_key: Any,
        corr_id: Any,
        oco_group_id: Any,
        entry_resp: Dict[str, Any],
        decision: "Message",
        owner_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Place SL/TP together for market entries.

        The TP side owns the Binance -2021 widen/retry fallback. If the
        parallel branch fails as a whole, the manager retries sequentially so a
        transient failure in one coroutine does not drop both protective orders.
        """
        from apps.reference.adapters.binance_adapter import BinanceAPIError

        sl_side = opposite_side(side)
        sl_id = generate_client_order_id(
            "SL", symbol, idempotent_key=str(idem_key) if idem_key else None)
        tp_side = opposite_side(side)
        tp_id = generate_client_order_id(
            "TP", symbol, idempotent_key=str(idem_key) if idem_key else None)

        # Read bracket placement config from SSOT
        bracket_cfg = self._fsm.config.domains.execution_position.bracket_placement
        tp_widen_first = Decimal(
            "1") + Decimal(str(bracket_cfg.tp_widen_first_bps)) / Decimal("10000")
        tp_widen_second = Decimal(
            "1") + Decimal(str(bracket_cfg.tp_widen_second_bps)) / Decimal("10000")
        retry_backoff_ms = bracket_cfg.retry_backoff_ms

        sl_resp = None
        tp_resp = None

        try:
            # Run both protective orders concurrently, but keep the TP-specific
            # widen/fallback policy local to the TP coroutine.
            async def place_sl_async():
                return await self._fsm.adapter.place_stop_market_close_position(
                    symbol, sl_side, str(sl), new_client_order_id=sl_id)

            async def place_tp_async():
                try:
                    return await self._fsm.adapter.place_take_profit_market_close_position(
                        symbol, tp_side, str(tp), new_client_order_id=tp_id)
                except BinanceAPIError as e:
                    if e.code == -2021:
                        LOG.warning(
                            f"⚠️ [PHASE A3] TP -2021 error, attempting backoff for {symbol}")
                        self._fsm._orphan_metrics["tp_sl_retry_backoff"] += 1

                        tp_adj = tp * tp_widen_first
                        tp_adj = quantize_stop_price(
                            tp_adj, tick_size, side="BUY" if side == "BUY" else "SELL")
                        if self._fsm.metrics_collector:
                            self._fsm.metrics_collector.record_retry(
                                "tp_adjust")

                        await get_clock().sleep_ms(retry_backoff_ms[0])

                        try:
                            return await self._fsm.adapter.place_take_profit_market_close_position(
                                symbol, tp_side, str(tp_adj), new_client_order_id=tp_id)
                        except BinanceAPIError as e2:
                            if e2.code == -2021 and len(retry_backoff_ms) > 1:
                                await get_clock().sleep_ms(retry_backoff_ms[1])
                                tp_adj2 = tp * tp_widen_second
                                tp_adj2 = quantize_stop_price(
                                    tp_adj2, tick_size, side="BUY" if side == "BUY" else "SELL")
                                try:
                                    return await self._fsm.adapter.place_take_profit_market_close_position(
                                        symbol, tp_side, str(tp_adj2), new_client_order_id=tp_id)
                                except BinanceAPIError:
                                    LOG.warning(
                                        f"⚠️ [PHASE A3] TP -2021 fallback to LIMIT for {symbol}")
                                    if self._fsm.metrics_collector:
                                        self._fsm.metrics_collector.record_retry(
                                            "tp_fallback")
                                    return await self._fsm.adapter.place_limit_reduce_only(
                                        symbol, tp_side, str(tp_adj2), qty, new_client_order_id=tp_id)
                            else:
                                raise
                        if self._fsm.metrics_collector:
                            self._fsm.metrics_collector.record_retry(
                                "tp_fallback")
                        return await self._fsm.adapter.place_limit_reduce_only(
                            symbol, tp_side, str(tp_adj), qty, new_client_order_id=tp_id)
                    else:
                        raise

            # DEF-E01: Use return_exceptions=True so each side is classified
            # independently. With return_exceptions=False, if SL succeeds but TP
            # fails the exception propagates immediately — the fallback below then
            # retries BOTH sides, creating a duplicate SL on exchange.
            _gather_results = await asyncio.gather(
                place_sl_async(), place_tp_async(), return_exceptions=True)
            sl_result, tp_result = _gather_results[0], _gather_results[1]

            sl_ok = not isinstance(sl_result, BaseException)
            tp_ok = not isinstance(tp_result, BaseException)

            if sl_ok and tp_ok:
                # Happy path: both sides placed
                sl_resp = sl_result
                tp_resp = tp_result
            elif sl_ok and not tp_ok:
                # DEF-E01: SL placed, TP failed — only retry TP, not SL
                LOG.warning(
                    "DEF-E01: bracket partial: SL placed, TP failed (%s). Retrying TP only.",
                    tp_result,
                )
                sl_resp = sl_result
                try:
                    tp_resp = await place_tp_async()
                except Exception as tp_retry_err:
                    LOG.error(
                        "DEF-E01: TP retry failed after partial success: %s", tp_retry_err)
                    raise tp_retry_err from tp_result
            elif not sl_ok and tp_ok:
                # DEF-E01: TP placed, SL failed — only retry SL (protective order missing!)
                LOG.warning(
                    "DEF-E01: bracket partial: TP placed, SL failed (%s). Retrying SL only.",
                    sl_result,
                )
                tp_resp = tp_result
                try:
                    sl_resp = await place_sl_async()
                except Exception as sl_retry_err:
                    LOG.error(
                        "DEF-E01: SL retry failed after partial success: %s", sl_retry_err)
                    raise sl_retry_err from sl_result
            else:
                # Both failed — raise SL error (primary protective order)
                raise sl_result  # type: ignore[misc]
        except Exception as e:
            LOG.error(f"Error placing brackets in parallel: {e}")
            # Fallback: only reached when both sides or a non-gather exception fails
            # — NOT used for single-side partial failures (handled above by DEF-E01).
            try:
                sl_resp = await self._fsm.adapter.place_stop_market_close_position(
                    symbol, sl_side, str(sl), new_client_order_id=sl_id)
                try:
                    tp_resp = await self._fsm.adapter.place_take_profit_market_close_position(
                        symbol, tp_side, str(tp), new_client_order_id=tp_id)
                except BinanceAPIError as retry_error:
                    if retry_error.code == -2021:
                        tp_adj = tp * tp_widen_first
                        tp_adj = quantize_stop_price(
                            tp_adj, tick_size, side="BUY" if side == "BUY" else "SELL")
                        try:
                            tp_resp = await self._fsm.adapter.place_take_profit_market_close_position(
                                symbol, tp_side, str(tp_adj), new_client_order_id=tp_id)
                        except BinanceAPIError:
                            tp_resp = await self._fsm.adapter.place_limit_reduce_only(
                                symbol, tp_side, str(tp_adj), qty, new_client_order_id=tp_id)
                    else:
                        raise
            except Exception as final_error:
                await self._record_bracket_failure(
                    symbol=symbol,
                    source_path="BracketManager.place_brackets_parallel",
                    failure_class="adapter_rejection",
                    reason=str(final_error),
                    why_code="BRACKET_PRIMARY_ADAPTER_REJECTION",
                    rid=getattr(decision, "rid", None),
                    side=side,
                    qty=qty,
                    entry_order_id=entry_resp.get("orderId"),
                    entry_client_order_id=entry_resp.get("clientOrderId"),
                    strategy_id=(owner_context or {}).get("strategy_id"),
                    details={"initial_error": str(e)},
                    live_position_proven=True,
                )
                raise

        if not (sl_resp and tp_resp):
            await self._record_bracket_failure(
                symbol=symbol,
                source_path="BracketManager.place_brackets_parallel",
                failure_class="adapter_rejection",
                reason="primary_bracket_response_missing",
                why_code="BRACKET_PRIMARY_RESPONSE_MISSING",
                rid=getattr(decision, "rid", None),
                side=side,
                qty=qty,
                entry_order_id=entry_resp.get("orderId"),
                entry_client_order_id=entry_resp.get("clientOrderId"),
                strategy_id=(owner_context or {}).get("strategy_id"),
                details={
                    "sl_response_present": sl_resp is not None,
                    "tp_response_present": tp_resp is not None,
                },
                live_position_proven=True,
            )
            raise RuntimeError(
                "primary bracket placement did not return both SL and TP responses")

        # Register results
        self._register_bracket_results(
            symbol=symbol, sl_resp=sl_resp, tp_resp=tp_resp,
            sl_id=sl_id, tp_id=tp_id,
            entry_resp=entry_resp, decision=decision,
            corr_id=corr_id, oco_group_id=oco_group_id,
            owner_context=owner_context, placement_path="primary")

    def _register_bracket_results(
        self, *, symbol, sl_resp, tp_resp, sl_id, tp_id,
        entry_resp, decision, corr_id, oco_group_id,
        owner_context: Optional[Dict[str, Any]] = None,
        placement_path: str = "primary",
    ):
        """Mirror accepted bracket IDs into FSM, correlation, and guardian state."""
        corr_value = corr_id or decision.corr_id or ""
        oco_group_value = oco_group_id or decision.oco_group_id or ""
        sl_order_id = None
        tp_order_id = None

        if sl_resp:
            LOG.info(f"✅ SL placed: {sl_resp}")
            self._fsm._orphan_metrics["tp_sl_placed_success"] += 1
            sl_order_id = str(sl_resp["orderId"])
            self._fsm.correlation_store.put_sl_tp_ack(
                sl_order_id, entry_resp["clientOrderId"],
                corr_value, oco_group_value, decision.rid or "")
            self._fsm._set_symbol_bracket_order(
                symbol,
                order_role="SL",
                order_id=sl_order_id,
            )

        if tp_resp:
            LOG.info(f"✅ TP placed: {tp_resp}")
            self._fsm._orphan_metrics["tp_sl_placed_success"] += 1
            tp_order_id = str(tp_resp["orderId"])
            self._fsm.correlation_store.put_sl_tp_ack(
                tp_order_id, entry_resp["clientOrderId"],
                corr_value, oco_group_value, decision.rid or "")
            self._fsm._set_symbol_bracket_order(
                symbol,
                order_role="TP",
                order_id=tp_order_id,
            )

        # --- CANONICAL OrderIndex registration for bracket children ---
        # Binance algo orders: the placement response contains `clientAlgoId` which
        # becomes the child order's `clientOrderId` in WS ORDER_TRADE_UPDATE fills.
        # We register clientAlgoId (if present) as the primary clientOrderId lookup
        # key so WS fills can be correlated.  The system-generated sl_id/tp_id
        # ("SL-xxx"/"TP-xxx") is kept as a secondary registration for legacy paths.
        sl_algo_client_id = str(sl_resp.get(
            "clientAlgoId", "")).strip() if sl_resp else ""
        tp_algo_client_id = str(tp_resp.get(
            "clientAlgoId", "")).strip() if tp_resp else ""

        order_index = getattr(self._fsm, "order_index", None) or getattr(
            getattr(self._fsm, "fsm", None), "order_index", None
        )
        if order_index is not None:
            bracket_side = opposite_side(
                str(entry_resp.get("side", "")).upper()
                or str(getattr(decision, "side", "") or "").upper()
                or ""
            )
            parent_rid = decision.rid or str(entry_resp.get("orderId", ""))
            idem_str = str(
                getattr(decision, "idempotent_key", "")
                or entry_resp.get("clientOrderId", "")
                or ""
            )
            if sl_order_id and sl_id:
                # Use clientAlgoId as the primary clientOrderId (matches WS fills)
                sl_client_for_index = sl_algo_client_id or sl_id
                try:
                    order_index.register_bracket_child(
                        rid=parent_rid,
                        idempotent_key=idem_str,
                        clientOrderId=sl_client_for_index,
                        exchangeOrderId=sl_order_id,
                        symbol=symbol,
                        side=bracket_side,
                        order_type="STOP_MARKET",
                        order_kind="SL",
                    )
                except Exception as exc:
                    LOG.error(
                        "OrderIndex bracket child registration failed for SL %s/%s: %s",
                        sl_client_for_index, sl_order_id, exc,
                    )
                # If clientAlgoId differs from sl_id, also register sl_id as secondary
                # so legacy code paths that reference "SL-xxx" still resolve.
                if sl_algo_client_id and sl_algo_client_id != sl_id:
                    try:
                        order_index.register_bracket_child(
                            rid=parent_rid,
                            idempotent_key=idem_str,
                            clientOrderId=sl_id,
                            exchangeOrderId=sl_order_id,
                            symbol=symbol,
                            side=bracket_side,
                            order_type="STOP_MARKET",
                            order_kind="SL",
                        )
                    except Exception:
                        pass  # Best-effort secondary registration
            if tp_order_id and tp_id:
                tp_client_for_index = tp_algo_client_id or tp_id
                try:
                    order_index.register_bracket_child(
                        rid=parent_rid,
                        idempotent_key=idem_str,
                        clientOrderId=tp_client_for_index,
                        exchangeOrderId=tp_order_id,
                        symbol=symbol,
                        side=bracket_side,
                        order_type="TAKE_PROFIT_MARKET",
                        order_kind="TP",
                    )
                except Exception as exc:
                    LOG.error(
                        "OrderIndex bracket child registration failed for TP %s/%s: %s",
                        tp_client_for_index, tp_order_id, exc,
                    )
                if tp_algo_client_id and tp_algo_client_id != tp_id:
                    try:
                        order_index.register_bracket_child(
                            rid=parent_rid,
                            idempotent_key=idem_str,
                            clientOrderId=tp_id,
                            exchangeOrderId=tp_order_id,
                            symbol=symbol,
                            side=bracket_side,
                            order_type="TAKE_PROFIT_MARKET",
                            order_kind="TP",
                        )
                    except Exception:
                        pass  # Best-effort secondary registration

        if sl_order_id or tp_order_id:
            # Persist the exchange child client identity into guardian when Binance
            # returns clientAlgoId; restart/runtime reconstruction consumes this field.
            sl_client_for_guardian = (
                (sl_algo_client_id or sl_id) if sl_resp else None
            )
            tp_client_for_guardian = (
                (tp_algo_client_id or tp_id) if tp_resp else None
            )
            self._fsm.order_guardian.register_brackets(
                symbol=symbol, entry_order_id=str(entry_resp["orderId"]),
                sl_order_id=sl_order_id, tp_order_id=tp_order_id,
                sl_client_id=sl_client_for_guardian,
                tp_client_id=tp_client_for_guardian,
                corr_id=corr_value, rid=decision.rid)

            try:
                # Best-effort cleanup avoids leaving older bracket sets alive
                # after a newer entry has already been acknowledged.
                import asyncio
                asyncio.ensure_future(self._fsm.order_guardian.cleanup_other_brackets_for_symbol(
                    symbol, keep_parent_order_id=str(entry_resp["orderId"])))
            except Exception as _e:
                LOG.debug(
                    f"OrderGuardian cleanup_other_brackets_for_symbol skipped: {_e}")

        manage_flow = self._fsm.manage_flows.get(symbol)
        if manage_flow:
            brackets = self._fsm._symbol_brackets[symbol] if symbol in self._fsm._symbol_brackets else {
            }
            manage_flow.set_bracket_ids(
                sl_order_id=brackets.get("sl_order_id"),
                tp_order_id=brackets.get("tp_order_id"),
                sl_algo_client_id=sl_algo_client_id or None,
                tp_algo_client_id=tp_algo_client_id or None,
            )

        if sl_order_id or tp_order_id:
            owner_context = dict(owner_context or {})
            lifecycle_active = self._fsm._has_active_lifecycle_for_symbol(
                symbol)
            owner_snapshot = self._fsm._remember_bracket_owner(
                symbol=symbol,
                strategy_id=owner_context.get("strategy_id"),
                strategy_source=owner_context.get("strategy_source"),
                owner_status=str(owner_context.get(
                    "owner_status") or "missing"),
                detail=owner_context.get(
                    "detail") or owner_context.get("owner_detail"),
                assigned_strategies=owner_context.get("assigned_strategies"),
                placement_path=placement_path,
                rid=decision.rid,
                corr_id=corr_value,
                entry_order_id=str(entry_resp.get("orderId") or ""),
                entry_client_order_id=entry_resp.get("clientOrderId"),
                lifecycle_active=lifecycle_active,
            )
            self._fsm._append_bracket_ownership_record(
                event_type="EXECUTION_BRACKET_PRIMARY_PLACED",
                symbol=symbol,
                placement_path=placement_path,
                strategy_id=owner_snapshot.get("strategy_id"),
                strategy_source=owner_snapshot.get("strategy_source"),
                owner_status=str(owner_snapshot.get(
                    "owner_status") or "missing"),
                detail=owner_snapshot.get("detail"),
                assigned_strategies=owner_snapshot.get("assigned_strategies"),
                rid=decision.rid,
                corr_id=corr_value,
                entry_order_id=str(entry_resp.get("orderId") or ""),
                entry_client_order_id=entry_resp.get("clientOrderId"),
                sl_order_id=sl_order_id,
                tp_order_id=tp_order_id,
                lifecycle_active=lifecycle_active,
            )

    async def place_deferred_brackets(
        self, entry_order_id: str, bracket_data: Dict[str, Any]
    ) -> bool:
        """Place TP/SL after a deferred LIMIT entry fill is confirmed."""
        from apps.reference.adapters.binance_adapter import BinanceAPIError

        symbol = bracket_data["symbol"]
        side = bracket_data["side"]
        sl = bracket_data["sl"]
        tp = bracket_data["tp"]
        rid = bracket_data.get("rid")
        idem_key = bracket_data.get("idem_key")
        tick_size = bracket_data.get("tick_size", Decimal("0.1"))
        corr_id = bracket_data.get("corr_id")
        oco_group_id = bracket_data.get("oco_group_id")
        entry_client_order_id = bracket_data.get("entry_client_order_id")

        LOG.info(
            f"📌 [LIMIT-DEFERRED] Placing brackets for {symbol}: SL={sl}, TP={tp}")

        # The deferred path reuses the same two guards as the immediate path:
        # position must be visible first, and OrderGuardian must accept the
        # entry->brackets transition for this parent order.
        if not await self.preflight_position_check(symbol):
            LOG.warning(
                f"🚫 [LIMIT-DEFERRED] Position check failed for {symbol}, skipping brackets")
            await self._record_bracket_failure(
                symbol=symbol,
                source_path="BracketManager.place_deferred_brackets",
                failure_class="transient_position_preflight_false",
                reason="deferred_position_preflight_false",
                why_code="BRACKET_DEFERRED_PREFLIGHT_FALSE",
                rid=rid,
                side=side,
                qty=bracket_data.get("qty"),
                entry_order_id=entry_order_id,
                entry_client_order_id=entry_client_order_id,
                strategy_id=bracket_data.get("strategy_id"),
                live_position_proven=False,
            )
            return False

        if not await self._fsm.order_guardian.should_place_brackets(symbol, entry_order_id):
            LOG.warning(
                f"🚫 [LIMIT-DEFERRED] OrderGuardian blocked brackets for {symbol}")
            await self._record_bracket_failure(
                symbol=symbol,
                source_path="BracketManager.place_deferred_brackets",
                failure_class="duplicate_or_guardian_veto",
                reason="order_guardian_blocked_deferred_brackets",
                why_code="BRACKET_DEFERRED_GUARDIAN_BLOCKED",
                rid=rid,
                side=side,
                qty=bracket_data.get("qty"),
                entry_order_id=entry_order_id,
                entry_client_order_id=entry_client_order_id,
                strategy_id=bracket_data.get("strategy_id"),
                live_position_proven=False,
            )
            return False

        if await self._has_live_synced_brackets(symbol):
            await self._record_bracket_failure(
                symbol=symbol,
                source_path="BracketManager.place_deferred_brackets",
                failure_class="duplicate_already_existing_brackets",
                reason="existing_exchange_brackets_already_protect_position",
                why_code="BRACKET_DEFERRED_EXISTING_EXCHANGE_BRACKETS",
                rid=rid,
                side=side,
                qty=bracket_data.get("qty"),
                entry_order_id=entry_order_id,
                entry_client_order_id=entry_client_order_id,
                strategy_id=bracket_data.get("strategy_id"),
                live_position_proven=False,
                remediation_action_override="existing_exchange_brackets_synced",
            )
            self._fsm._clear_pending_brackets(
                entry_order_id,
                reason="filled",
                symbol=symbol,
                persist_snapshot=True,
            )
            return True

        sl_side = opposite_side(side)
        sl_id = generate_client_order_id(
            "SL", symbol, idempotent_key=str(idem_key) if idem_key else None)
        tp_side = opposite_side(side)
        tp_id = generate_client_order_id(
            "TP", symbol, idempotent_key=str(idem_key) if idem_key else None)

        bracket_cfg = self._fsm.config.domains.execution_position.bracket_placement
        tp_widen_first = Decimal(
            "1") + Decimal(str(bracket_cfg.tp_widen_first_bps)) / Decimal("10000")

        sl_resp = None
        tp_resp = None
        try:
            sl_resp = await self._fsm.adapter.place_stop_market_close_position(
                symbol, sl_side, str(sl), new_client_order_id=sl_id)
            LOG.info(f"✅ [LIMIT-DEFERRED] SL placed: {sl_resp}")
            self._fsm._orphan_metrics["tp_sl_placed_success"] += 1
            sl_order_id = str(sl_resp["orderId"])
            self._fsm.correlation_store.put_sl_tp_ack(
                sl_order_id, entry_client_order_id or "", corr_id or "",
                oco_group_id or "", rid or "")
            self._fsm._set_symbol_bracket_order(
                symbol,
                order_role="SL",
                order_id=sl_order_id,
            )
        except Exception as e:
            LOG.error(
                f"❌ [LIMIT-DEFERRED] Failed to place SL for {symbol}: {e}")

        try:
            tp_resp = await self._fsm.adapter.place_take_profit_market_close_position(
                symbol, tp_side, str(tp), new_client_order_id=tp_id)
            LOG.info(f"✅ [LIMIT-DEFERRED] TP placed: {tp_resp}")
            self._fsm._orphan_metrics["tp_sl_placed_success"] += 1
            tp_order_id = str(tp_resp["orderId"])
            self._fsm.correlation_store.put_sl_tp_ack(
                tp_order_id, entry_client_order_id or "", corr_id or "",
                oco_group_id or "", rid or "")
            self._fsm._set_symbol_bracket_order(
                symbol,
                order_role="TP",
                order_id=tp_order_id,
            )
        except BinanceAPIError as e:
            if e.code == -2021:
                LOG.warning(
                    f"⚠️ [LIMIT-DEFERRED] TP -2021 for {symbol}, widening")
                tp_adj = tp * tp_widen_first
                tp_adj = quantize_stop_price(
                    tp_adj, tick_size, side="BUY" if side == "BUY" else "SELL")
                try:
                    tp_resp = await self._fsm.adapter.place_take_profit_market_close_position(
                        symbol, tp_side, str(tp_adj), new_client_order_id=tp_id)
                    LOG.info(
                        f"✅ [LIMIT-DEFERRED] TP placed (widened): {tp_resp}")
                    tp_order_id = str(tp_resp["orderId"])
                    self._fsm.correlation_store.put_sl_tp_ack(
                        tp_order_id, entry_client_order_id or "", corr_id or "",
                        oco_group_id or "", rid or "")
                    self._fsm._set_symbol_bracket_order(
                        symbol,
                        order_role="TP",
                        order_id=tp_order_id,
                    )
                except Exception as e2:
                    LOG.error(
                        f"❌ [LIMIT-DEFERRED] TP retry failed for {symbol}: {e2}")
            else:
                LOG.error(
                    f"❌ [LIMIT-DEFERRED] Failed to place TP for {symbol}: {e}")
        except Exception as e:
            LOG.error(
                f"❌ [LIMIT-DEFERRED] Failed to place TP for {symbol}: {e}")

        # --- CANONICAL OrderIndex registration for deferred bracket children ---
        # Extract clientAlgoId for WS fill correlation (same pattern as primary path).
        sl_algo_client_id = str(sl_resp.get(
            "clientAlgoId", "")).strip() if sl_resp else ""
        tp_algo_client_id = str(tp_resp.get(
            "clientAlgoId", "")).strip() if tp_resp else ""

        order_index = getattr(self._fsm, "order_index", None) or getattr(
            getattr(self._fsm, "fsm", None), "order_index", None
        )
        if order_index is not None:
            bracket_side = opposite_side(side)
            parent_rid = rid or entry_order_id
            idem_str = str(idem_key or entry_client_order_id or "")
            if sl_resp:
                sl_client_for_index = sl_algo_client_id or sl_id
                try:
                    order_index.register_bracket_child(
                        rid=parent_rid,
                        idempotent_key=idem_str,
                        clientOrderId=sl_client_for_index,
                        exchangeOrderId=str(sl_resp["orderId"]),
                        symbol=symbol,
                        side=bracket_side,
                        order_type="STOP_MARKET",
                        order_kind="SL",
                    )
                except Exception as exc:
                    LOG.error(
                        "OrderIndex deferred bracket child registration failed for SL %s: %s",
                        sl_client_for_index, exc,
                    )
                if sl_algo_client_id and sl_algo_client_id != sl_id:
                    try:
                        order_index.register_bracket_child(
                            rid=parent_rid,
                            idempotent_key=idem_str,
                            clientOrderId=sl_id,
                            exchangeOrderId=str(sl_resp["orderId"]),
                            symbol=symbol,
                            side=bracket_side,
                            order_type="STOP_MARKET",
                            order_kind="SL",
                        )
                    except Exception:
                        pass
            if tp_resp:
                tp_client_for_index = tp_algo_client_id or tp_id
                try:
                    order_index.register_bracket_child(
                        rid=parent_rid,
                        idempotent_key=idem_str,
                        clientOrderId=tp_client_for_index,
                        exchangeOrderId=str(tp_resp["orderId"]),
                        symbol=symbol,
                        side=bracket_side,
                        order_type="TAKE_PROFIT_MARKET",
                        order_kind="TP",
                    )
                except Exception as exc:
                    LOG.error(
                        "OrderIndex deferred bracket child registration failed for TP %s: %s",
                        tp_client_for_index, exc,
                    )
                if tp_algo_client_id and tp_algo_client_id != tp_id:
                    try:
                        order_index.register_bracket_child(
                            rid=parent_rid,
                            idempotent_key=idem_str,
                            clientOrderId=tp_id,
                            exchangeOrderId=str(tp_resp["orderId"]),
                            symbol=symbol,
                            side=bracket_side,
                            order_type="TAKE_PROFIT_MARKET",
                            order_kind="TP",
                        )
                    except Exception:
                        pass

        # Persist the exchange child client identity into guardian when Binance
        # returns clientAlgoId; restart/runtime reconstruction consumes this field.
        if sl_resp:
            sl_client_for_guardian = sl_algo_client_id or sl_id
            self._fsm.order_guardian.register_bracket(
                symbol=symbol, parent_order_id=entry_order_id,
                order_id=str(sl_resp["orderId"]), client_order_id=sl_client_for_guardian,
                kind="SL", corr_id=corr_id, rid=rid)
        if tp_resp:
            tp_client_for_guardian = tp_algo_client_id or tp_id
            self._fsm.order_guardian.register_bracket(
                symbol=symbol, parent_order_id=entry_order_id,
                order_id=str(tp_resp["orderId"]), client_order_id=tp_client_for_guardian,
                kind="TP", corr_id=corr_id, rid=rid)

        # Sync bracket IDs (including algo client IDs) to ManageFlowFSM
        manage_flow = self._fsm.manage_flows.get(symbol)
        if manage_flow:
            brackets = self._fsm._symbol_brackets.get(symbol, {})
            manage_flow.set_bracket_ids(
                sl_order_id=brackets.get("sl_order_id"),
                tp_order_id=brackets.get("tp_order_id"),
                sl_algo_client_id=sl_algo_client_id or None,
                tp_algo_client_id=tp_algo_client_id or None,
            )

        if sl_resp or tp_resp:
            lifecycle_active = self._fsm._has_active_lifecycle_for_symbol(
                symbol)
            owner_snapshot = self._fsm._remember_bracket_owner(
                symbol=symbol,
                strategy_id=bracket_data.get("strategy_id"),
                strategy_source=bracket_data.get("strategy_source"),
                owner_status=str(bracket_data.get(
                    "owner_status") or "missing"),
                detail=bracket_data.get("owner_detail"),
                assigned_strategies=bracket_data.get("assigned_strategies"),
                placement_path="deferred",
                rid=rid,
                corr_id=corr_id,
                entry_order_id=entry_order_id,
                entry_client_order_id=entry_client_order_id,
                lifecycle_active=lifecycle_active,
            )
            self._fsm._append_bracket_ownership_record(
                event_type="EXECUTION_BRACKET_DEFERRED_PLACED",
                symbol=symbol,
                placement_path="deferred",
                strategy_id=owner_snapshot.get("strategy_id"),
                strategy_source=owner_snapshot.get("strategy_source"),
                owner_status=str(owner_snapshot.get(
                    "owner_status") or "missing"),
                detail=owner_snapshot.get("detail"),
                assigned_strategies=owner_snapshot.get("assigned_strategies"),
                rid=rid,
                corr_id=corr_id,
                entry_order_id=entry_order_id,
                entry_client_order_id=entry_client_order_id,
                sl_order_id=str(sl_resp["orderId"]) if sl_resp else None,
                tp_order_id=str(tp_resp["orderId"]) if tp_resp else None,
                lifecycle_active=lifecycle_active,
            )

        placement_success = bool(sl_resp and tp_resp)
        if placement_success:
            self._fsm._clear_pending_brackets(
                entry_order_id,
                reason="filled",
                symbol=symbol,
                persist_snapshot=True,
            )
        else:
            # A1-REMEDIATION: preflight_position_check already confirmed the position is live.
            # Any bracket placement failure after that point must use live_position_proven=True
            # so the protection-missing handler can trigger a force-close.  We distinguish
            # three partial-failure sub-cases to produce precise observability payloads.
            sl_present = sl_resp is not None
            tp_present = tp_resp is not None
            common_details = {
                "sl_response_present": sl_present,
                "tp_response_present": tp_present,
                "missing_sl": not sl_present,
                "missing_tp": not tp_present,
                "preflight_position_confirmed": True,
                "deferred_brackets": True,
            }

            if not sl_present and not tp_present:
                # Both legs failed — position is fully unprotected.
                why_code = "BRACKET_DEFERRED_BOTH_FAILED"
                reason = "deferred_both_sl_and_tp_placement_failed_after_preflight"
                failure_class = "adapter_rejection"
            elif not sl_present:
                # SL failed, TP placed — downside unprotected. Critical: requires remediation.
                why_code = "BRACKET_DEFERRED_SL_MISSING"
                reason = "deferred_sl_placement_failed_tp_placed_after_preflight"
                failure_class = "adapter_rejection_partial_sl_missing"
            else:
                # SL placed, TP failed — upside exit missing. Policy: full SL+TP pair required;
                # no silent partial-protection accepted.  Trigger remediation.
                why_code = "BRACKET_DEFERRED_TP_MISSING"
                reason = "deferred_tp_placement_failed_sl_placed_after_preflight"
                failure_class = "adapter_rejection_partial_tp_missing"

            await self._record_bracket_failure(
                symbol=symbol,
                source_path="BracketManager.place_deferred_brackets",
                failure_class=failure_class,
                reason=reason,
                why_code=why_code,
                rid=rid,
                side=side,
                qty=bracket_data.get("qty"),
                entry_order_id=entry_order_id,
                entry_client_order_id=entry_client_order_id,
                strategy_id=bracket_data.get("strategy_id"),
                details=common_details,
                live_position_proven=True,
            )

        LOG.info(
            f"✅ [LIMIT-DEFERRED] Brackets placed for {symbol}: "
            f"SL={'OK' if sl_resp else 'FAILED'}, TP={'OK' if tp_resp else 'FAILED'}")
        return placement_success

    async def preflight_position_check(self, symbol: str) -> bool:
        """Confirm that the exchange exposes a non-zero position before TP/SL placement.

        The retry cadence comes from trading.execution.preflight_backoff_ms and
        is intentionally strict: missing or invalid config raises immediately,
        while exchange/read-path instability degrades to a bounded False result.
        """
        exec_cfg = getattr(self._fsm.config, "trading", None)
        exec_cfg = getattr(exec_cfg, "execution",
                           None) if exec_cfg is not None else None
        backoff_ms = getattr(exec_cfg, "preflight_backoff_ms",
                             None) if exec_cfg is not None else None
        if not backoff_ms:
            raise ValueError(
                "trading.execution.preflight_backoff_ms is required for TP/SL preflight; no fallback/default is allowed.")
        backoff_ms = [int(x) for x in backoff_ms]
        if any(x <= 0 for x in backoff_ms):
            raise ValueError(
                f"trading.execution.preflight_backoff_ms must be positive ints, got: {backoff_ms}")
        tries = 0
        start = get_clock().now_sec()

        while True:
            tries += 1
            try:
                positions = await self._fsm.adapter.get_open_positions(symbol)
                positions_list = [
                    p.to_dict() if hasattr(p, 'to_dict') else (
                        p.__dict__ if not isinstance(p, dict) else p)
                    for p in positions
                ]
                pos = next(
                    (p for p in positions_list if p.get("symbol") == symbol), None)
                if pos is None:
                    position_amt = 0.0
                else:
                    position_amt = float(
                        pos.get("position_amount") or pos.get("positionAmt") or 0)
                elapsed_ms = int((get_clock().now_sec() - start) * 1000)
                LOG.info(
                    f"[BRK] preflight positionRisk posAmt={position_amt} try={tries} elapsed={elapsed_ms}ms")
                if abs(position_amt) >= 1e-10:
                    LOG.info("[BRK] preflight DECISION=allow (pos!=0)")
                    return True
                if tries > len(backoff_ms):
                    LOG.warning(
                        f"🚫 [PHASE A3] PRE-FLIGHT SKIPPED: Position is 0 for {symbol} after {tries} tries")
                    self._fsm._orphan_metrics["tp_sl_skipped_no_position"] += 1
                    return False
                await get_clock().sleep_ms(backoff_ms[tries - 1])
            except Exception as e:
                LOG.warning(
                    f"⚠️ [PHASE A3] PRE-FLIGHT ERROR for {symbol} (try {tries}): {e}")
                if tries > len(backoff_ms):
                    return False
                await get_clock().sleep_ms(backoff_ms[tries - 1])
