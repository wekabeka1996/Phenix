"""
Bracket order management for execution_position domain.

Extracted from ExecPosFSM (Phase 14A decomposition).
Handles TP/SL bracket placement (parallel and deferred),
pre-flight position checks, and bracket registration.
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
    """Manages TP/SL bracket placement and pre-flight checks."""

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
    ) -> None:
        """Place SL and TP brackets in parallel with -2021 retry logic."""
        from apps.reference.adapters.binance_adapter import BinanceAPIError

        sl_side = opposite_side(side)
        sl_id = generate_client_order_id(
            "SL", symbol, idempotent_key=str(idem_key) if idem_key else None)
        tp_side = opposite_side(side)
        tp_id = generate_client_order_id(
            "TP", symbol, idempotent_key=str(idem_key) if idem_key else None)

        # Read bracket placement config from SSOT
        bracket_cfg = self._fsm.config.domains.execution_position.bracket_placement
        tp_widen_first = Decimal("1") + Decimal(str(bracket_cfg.tp_widen_first_bps)) / Decimal("10000")
        tp_widen_second = Decimal("1") + Decimal(str(bracket_cfg.tp_widen_second_bps)) / Decimal("10000")
        retry_backoff_ms = bracket_cfg.retry_backoff_ms

        sl_resp = None
        tp_resp = None

        try:
            async def place_sl_async():
                return await self._fsm.adapter.place_stop_market_close_position(
                    symbol, sl_side, str(sl), new_client_order_id=sl_id)

            async def place_tp_async():
                try:
                    return await self._fsm.adapter.place_take_profit_market_close_position(
                        symbol, tp_side, str(tp), new_client_order_id=tp_id)
                except BinanceAPIError as e:
                    if e.code == -2021:
                        LOG.warning(f"⚠️ [PHASE A3] TP -2021 error, attempting backoff for {symbol}")
                        self._fsm._orphan_metrics["tp_sl_retry_backoff"] += 1

                        tp_adj = tp * tp_widen_first
                        tp_adj = quantize_stop_price(
                            tp_adj, tick_size, side="BUY" if side == "BUY" else "SELL")
                        if self._fsm.metrics_collector:
                            self._fsm.metrics_collector.record_retry("tp_adjust")

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
                                    LOG.warning(f"⚠️ [PHASE A3] TP -2021 fallback to LIMIT for {symbol}")
                                    if self._fsm.metrics_collector:
                                        self._fsm.metrics_collector.record_retry("tp_fallback")
                                    return await self._fsm.adapter.place_limit_reduce_only(
                                        symbol, tp_side, str(tp_adj2), qty, new_client_order_id=tp_id)
                            else:
                                raise
                        if self._fsm.metrics_collector:
                            self._fsm.metrics_collector.record_retry("tp_fallback")
                        return await self._fsm.adapter.place_limit_reduce_only(
                            symbol, tp_side, str(tp_adj), qty, new_client_order_id=tp_id)
                    else:
                        raise

            sl_resp, tp_resp = await asyncio.gather(
                place_sl_async(), place_tp_async(), return_exceptions=False)
        except Exception as e:
            LOG.error(f"Error placing brackets in parallel: {e}")
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
            corr_id=corr_id, oco_group_id=oco_group_id)

    def _register_bracket_results(
        self, *, symbol, sl_resp, tp_resp, sl_id, tp_id,
        entry_resp, decision, corr_id, oco_group_id
    ):
        """Register bracket results with correlation store and order guardian."""
        sl_order_id = None
        tp_order_id = None

        if sl_resp:
            LOG.info(f"✅ SL placed: {sl_resp}")
            self._fsm._orphan_metrics["tp_sl_placed_success"] += 1
            sl_order_id = str(sl_resp["orderId"])
            self._fsm.correlation_store.put_sl_tp_ack(
                sl_order_id, entry_resp["clientOrderId"],
                decision.corr_id or "", decision.oco_group_id or "", decision.rid or "")
            self._fsm._symbol_brackets.setdefault(symbol, {})["sl_order_id"] = sl_order_id

        if tp_resp:
            LOG.info(f"✅ TP placed: {tp_resp}")
            self._fsm._orphan_metrics["tp_sl_placed_success"] += 1
            tp_order_id = str(tp_resp["orderId"])
            self._fsm.correlation_store.put_sl_tp_ack(
                tp_order_id, entry_resp["clientOrderId"],
                decision.corr_id or "", decision.oco_group_id or "", decision.rid or "")
            self._fsm._symbol_brackets.setdefault(symbol, {})["tp_order_id"] = tp_order_id

        if sl_order_id or tp_order_id:
            self._fsm.order_guardian.register_brackets(
                symbol=symbol, entry_order_id=str(entry_resp["orderId"]),
                sl_order_id=sl_order_id, tp_order_id=tp_order_id,
                sl_client_id=sl_id if sl_resp else None,
                tp_client_id=tp_id if tp_resp else None,
                corr_id=decision.corr_id, rid=decision.rid)

            try:
                import asyncio
                asyncio.ensure_future(self._fsm.order_guardian.cleanup_other_brackets_for_symbol(
                    symbol, keep_parent_order_id=str(entry_resp["orderId"])))
            except Exception as _e:
                LOG.debug(f"OrderGuardian cleanup_other_brackets_for_symbol skipped: {_e}")

        manage_flow = self._fsm.manage_flows.get(symbol)
        if manage_flow:
            brackets = self._fsm._symbol_brackets[symbol] if symbol in self._fsm._symbol_brackets else {}
            manage_flow.set_bracket_ids(
                sl_order_id=brackets.get("sl_order_id"),
                tp_order_id=brackets.get("tp_order_id"))

    async def place_deferred_brackets(
        self, entry_order_id: str, bracket_data: Dict[str, Any]
    ) -> None:
        """LIMIT-ENTRY-DEFERRED-BRACKETS: Place TP/SL brackets after LIMIT entry fill."""
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

        LOG.info(f"📌 [LIMIT-DEFERRED] Placing brackets for {symbol}: SL={sl}, TP={tp}")

        if not await self.preflight_position_check(symbol):
            LOG.warning(f"🚫 [LIMIT-DEFERRED] Position check failed for {symbol}, skipping brackets")
            return

        if not await self._fsm.order_guardian.should_place_brackets(symbol, entry_order_id):
            LOG.warning(f"🚫 [LIMIT-DEFERRED] OrderGuardian blocked brackets for {symbol}")
            return

        sl_side = opposite_side(side)
        sl_id = generate_client_order_id("SL", symbol, idempotent_key=str(idem_key) if idem_key else None)
        tp_side = opposite_side(side)
        tp_id = generate_client_order_id("TP", symbol, idempotent_key=str(idem_key) if idem_key else None)

        bracket_cfg = self._fsm.config.domains.execution_position.bracket_placement
        tp_widen_first = Decimal("1") + Decimal(str(bracket_cfg.tp_widen_first_bps)) / Decimal("10000")

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
            self._fsm._symbol_brackets.setdefault(symbol, {})["sl_order_id"] = sl_order_id
        except Exception as e:
            LOG.error(f"❌ [LIMIT-DEFERRED] Failed to place SL for {symbol}: {e}")

        try:
            tp_resp = await self._fsm.adapter.place_take_profit_market_close_position(
                symbol, tp_side, str(tp), new_client_order_id=tp_id)
            LOG.info(f"✅ [LIMIT-DEFERRED] TP placed: {tp_resp}")
            self._fsm._orphan_metrics["tp_sl_placed_success"] += 1
            tp_order_id = str(tp_resp["orderId"])
            self._fsm.correlation_store.put_sl_tp_ack(
                tp_order_id, entry_client_order_id or "", corr_id or "",
                oco_group_id or "", rid or "")
            self._fsm._symbol_brackets.setdefault(symbol, {})["tp_order_id"] = tp_order_id
        except BinanceAPIError as e:
            if e.code == -2021:
                LOG.warning(f"⚠️ [LIMIT-DEFERRED] TP -2021 for {symbol}, widening")
                tp_adj = tp * tp_widen_first
                tp_adj = quantize_stop_price(tp_adj, tick_size, side="BUY" if side == "BUY" else "SELL")
                try:
                    tp_resp = await self._fsm.adapter.place_take_profit_market_close_position(
                        symbol, tp_side, str(tp_adj), new_client_order_id=tp_id)
                    LOG.info(f"✅ [LIMIT-DEFERRED] TP placed (widened): {tp_resp}")
                    tp_order_id = str(tp_resp["orderId"])
                    self._fsm.correlation_store.put_sl_tp_ack(
                        tp_order_id, entry_client_order_id or "", corr_id or "",
                        oco_group_id or "", rid or "")
                    self._fsm._symbol_brackets.setdefault(symbol, {})["tp_order_id"] = tp_order_id
                except Exception as e2:
                    LOG.error(f"❌ [LIMIT-DEFERRED] TP retry failed for {symbol}: {e2}")
            else:
                LOG.error(f"❌ [LIMIT-DEFERRED] Failed to place TP for {symbol}: {e}")
        except Exception as e:
            LOG.error(f"❌ [LIMIT-DEFERRED] Failed to place TP for {symbol}: {e}")

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

        LOG.info(
            f"✅ [LIMIT-DEFERRED] Brackets placed for {symbol}: "
            f"SL={'OK' if sl_resp else 'FAILED'}, TP={'OK' if tp_resp else 'FAILED'}")

    async def preflight_position_check(self, symbol: str) -> bool:
        """PHASE A3: Pre-flight check before placing TP/SL orders."""
        exec_cfg = getattr(self._fsm.config, "trading", None)
        exec_cfg = getattr(exec_cfg, "execution", None) if exec_cfg is not None else None
        backoff_ms = getattr(exec_cfg, "preflight_backoff_ms", None) if exec_cfg is not None else None
        if not backoff_ms:
            raise ValueError(
                "trading.execution.preflight_backoff_ms is required for TP/SL preflight; no fallback/default is allowed.")
        backoff_ms = [int(x) for x in backoff_ms]
        if any(x <= 0 for x in backoff_ms):
            raise ValueError(f"trading.execution.preflight_backoff_ms must be positive ints, got: {backoff_ms}")
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
                pos = next((p for p in positions_list if p.get("symbol") == symbol), None)
                if pos is None:
                    position_amt = 0.0
                else:
                    position_amt = float(pos.get("position_amount") or pos.get("positionAmt") or 0)
                elapsed_ms = int((get_clock().now_sec() - start) * 1000)
                LOG.info(f"[BRK] preflight positionRisk posAmt={position_amt} try={tries} elapsed={elapsed_ms}ms")
                if abs(position_amt) >= 1e-10:
                    LOG.info("[BRK] preflight DECISION=allow (pos!=0)")
                    return True
                if tries > len(backoff_ms):
                    LOG.warning(f"🚫 [PHASE A3] PRE-FLIGHT SKIPPED: Position is 0 for {symbol} after {tries} tries")
                    self._fsm._orphan_metrics["tp_sl_skipped_no_position"] += 1
                    return False
                await get_clock().sleep_ms(backoff_ms[tries - 1])
            except Exception as e:
                LOG.warning(f"⚠️ [PHASE A3] PRE-FLIGHT ERROR for {symbol} (try {tries}): {e}")
                if tries > len(backoff_ms):
                    return False
                await get_clock().sleep_ms(backoff_ms[tries - 1])
