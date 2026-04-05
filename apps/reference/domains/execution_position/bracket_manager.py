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

            sl_resp, tp_resp = await asyncio.gather(
                place_sl_async(), place_tp_async(), return_exceptions=False)
        except Exception as e:
            LOG.error(f"Error placing brackets in parallel: {e}")
            # Fall back to the older sequential behavior to salvage bracket
            # placement when one side of the parallel path fails unexpectedly.
            sl_resp = await self._fsm.adapter.place_stop_market_close_position(
                symbol, sl_side, str(sl), new_client_order_id=sl_id)
            try:
                tp_resp = await self._fsm.adapter.place_take_profit_market_close_position(
                    symbol, tp_side, str(tp), new_client_order_id=tp_id)
            except BinanceAPIError as e:
                if e.code == -2021:
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
            self._fsm._symbol_brackets.setdefault(
                symbol, {})["sl_order_id"] = sl_order_id

        if tp_resp:
            LOG.info(f"✅ TP placed: {tp_resp}")
            self._fsm._orphan_metrics["tp_sl_placed_success"] += 1
            tp_order_id = str(tp_resp["orderId"])
            self._fsm.correlation_store.put_sl_tp_ack(
                tp_order_id, entry_resp["clientOrderId"],
                corr_value, oco_group_value, decision.rid or "")
            self._fsm._symbol_brackets.setdefault(
                symbol, {})["tp_order_id"] = tp_order_id

        # --- CANONICAL OrderIndex registration for bracket children ---
        # Binance algo orders: the placement response contains `clientAlgoId` which
        # becomes the child order's `clientOrderId` in WS ORDER_TRADE_UPDATE fills.
        # We register clientAlgoId (if present) as the primary clientOrderId lookup
        # key so WS fills can be correlated.  The system-generated sl_id/tp_id
        # ("SL-xxx"/"TP-xxx") is kept as a secondary registration for legacy paths.
        sl_algo_client_id = str(sl_resp.get("clientAlgoId", "")).strip() if sl_resp else ""
        tp_algo_client_id = str(tp_resp.get("clientAlgoId", "")).strip() if tp_resp else ""

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
            self._fsm.order_guardian.register_brackets(
                symbol=symbol, entry_order_id=str(entry_resp["orderId"]),
                sl_order_id=sl_order_id, tp_order_id=tp_order_id,
                sl_client_id=sl_id if sl_resp else None,
                tp_client_id=tp_id if tp_resp else None,
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
    ) -> None:
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
            return

        if not await self._fsm.order_guardian.should_place_brackets(symbol, entry_order_id):
            LOG.warning(
                f"🚫 [LIMIT-DEFERRED] OrderGuardian blocked brackets for {symbol}")
            return

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
            self._fsm._symbol_brackets.setdefault(
                symbol, {})["sl_order_id"] = sl_order_id
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
            self._fsm._symbol_brackets.setdefault(
                symbol, {})["tp_order_id"] = tp_order_id
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
                    self._fsm._symbol_brackets.setdefault(
                        symbol, {})["tp_order_id"] = tp_order_id
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
        sl_algo_client_id = str(sl_resp.get("clientAlgoId", "")).strip() if sl_resp else ""
        tp_algo_client_id = str(tp_resp.get("clientAlgoId", "")).strip() if tp_resp else ""

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

        # Register with OrderGuardian
        if sl_resp:
            self._fsm.order_guardian.register_bracket(
                symbol=symbol, parent_order_id=entry_order_id,
                order_id=str(sl_resp["orderId"]), client_order_id=sl_id,
                kind="SL", corr_id=corr_id, rid=rid)
        if tp_resp:
            self._fsm.order_guardian.register_bracket(
                symbol=symbol, parent_order_id=entry_order_id,
                order_id=str(tp_resp["orderId"]), client_order_id=tp_id,
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

        LOG.info(
            f"✅ [LIMIT-DEFERRED] Brackets placed for {symbol}: "
            f"SL={'OK' if sl_resp else 'FAILED'}, TP={'OK' if tp_resp else 'FAILED'}")

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
