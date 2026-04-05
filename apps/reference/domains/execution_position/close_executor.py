"""Close/cancel execution helper for execution_position.

This module owns the imperative side of DEC:CLOSE, DEC:CANCEL_ORDER, and the
generic DEC:PLACE_ORDER path used by manage/auxiliary flows.
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from apps.reference.core.time import get_clock
from apps.reference.telemetry.order_logger import order_logger
from apps.reference.domains.execution_position.utils import generate_client_order_id

if TYPE_CHECKING:
    from vfoundation.core.fsm_emit_compat import Message

LOG = logging.getLogger(__name__)


class CloseExecutor:
    """Execute cancel, close, and generic auxiliary order verbs."""

    def __init__(self, fsm: Any) -> None:
        self._fsm = fsm

    async def execute_cancel_order(self, decision: "Message") -> None:
        """Cancel a specific order_id for the symbol in the decision payload."""
        pld = decision.pld or {}
        symbol = pld.get("symbol")
        oid = pld.get("order_id") or pld.get("orderId")
        if not symbol or not oid:
            LOG.error("DEC:CANCEL_ORDER missing symbol/order_id")
            return
        await self._fsm._cancel_order(symbol, oid)
        LOG.info(f"Cancelled order {oid} for {symbol}")

    async def execute_close(self, decision: "Message") -> None:
        """Execute CLOSE/CLOSE_POSITION with bracket cleanup and reconcile passes.

        A smaller requested qty takes the early partial-close branch and returns
        before the full-close teardown/reconcile path below.
        """
        pld = decision.pld or {}
        symbol = pld.get("symbol")
        if not symbol:
            LOG.error("DEC:CLOSE missing symbol; cannot execute")
            return

        requested_close_qty: Optional[Decimal] = None
        requested_close_qty_raw = pld.get("qty")
        if requested_close_qty_raw not in (None, "", "0", 0):
            try:
                requested_close_qty = abs(
                    Decimal(str(requested_close_qty_raw)))
            except Exception:
                LOG.warning(
                    "DEC:CLOSE invalid qty=%r for %s; falling back to full close",
                    requested_close_qty_raw,
                    symbol,
                )

        if requested_close_qty is not None:
            try:
                positions = await self._fsm.adapter.get_open_positions()
                positions_list = [
                    p.to_dict() if hasattr(p, "to_dict") else (
                        p.__dict__ if not isinstance(p, dict) else p
                    )
                    for p in positions
                ]
                pos = next(
                    (p for p in positions_list if p.get("symbol") == symbol), None)
            except Exception:
                pos = None

            amt = 0.0
            if pos is not None:
                try:
                    amt = float(pos["positionAmt"]
                                if "positionAmt" in pos else 0)
                except Exception:
                    amt = 0.0
            if abs(amt) < 1e-10:
                LOG.info(f"No open position to close for {symbol}")
                self._fsm._symbol_brackets.pop(symbol, None)
                self._fsm._persist_restore_artifact_snapshot(
                    trigger="close_executor:no_position_partial",
                    allow_empty=True,
                )
                return

            position_qty = abs(Decimal(str(amt)))
            if Decimal("0") < requested_close_qty < position_qty:
                close_side = "SELL" if amt > 0 else "BUY"
                close_id = generate_client_order_id(
                    "CLOSE",
                    symbol,
                    idempotent_key=str(
                        pld.get("idempotent_key") or decision.rid or "manual-close"),
                )
                await self._fsm.adapter.place_market_reduce_only(
                    symbol,
                    close_side,
                    str(requested_close_qty),
                    new_client_order_id=close_id,
                )
                LOG.info(
                    "Partial close executed for %s: side=%s qty=%s",
                    symbol,
                    close_side,
                    requested_close_qty,
                )
                lifecycle_cfg = self._fsm.config.domains.execution_position.order_lifecycle
                await get_clock().sleep_ms(lifecycle_cfg.fill_settlement_delay_ms)
                try:
                    await self._fsm.order_guardian.reconcile_symbol(symbol, decision.rid)
                except Exception as e:
                    LOG.warning(
                        f"Partial close reconcile failed for {symbol}: {e}")
                close_elapsed_ms = int(get_clock().now_sec(
                ) * 1000 - decision.ts) if decision.ts else 0
                self._fsm._emit_observability_event("DEC_CLOSE_COMPLETED", {
                    "symbol": symbol,
                    "elapsed_ms": close_elapsed_ms,
                    "orphans_cancelled": 0,
                    "partial_close": True,
                    "requested_qty": str(requested_close_qty),
                })
                return

        # Mark the symbol as closing before bracket teardown so concurrent manage
        # flows do not race in and recreate auxiliary orders mid-close.
        manage = self._fsm.manage_flows.get(symbol)
        if manage:
            manage._closing_position = True
            manage._closing_position_ts = get_clock().now_sec()
            LOG.info(
                f"🔒 [PHASE A2] Set closing flag for {symbol} to prevent bracket race")

        # First cancel the bracket IDs we already track locally.
        br = self._fsm._symbol_brackets[symbol] if symbol in self._fsm._symbol_brackets else {
        }
        tasks = []
        bracket_order_ids = []
        if br.get("sl_order_id"):
            tasks.append(self._fsm._cancel_order(symbol, br["sl_order_id"]))
            bracket_order_ids.append(("SL", br["sl_order_id"]))
        if br.get("tp_order_id"):
            tasks.append(self._fsm._cancel_order(symbol, br["tp_order_id"]))
            bracket_order_ids.append(("TP", br["tp_order_id"]))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for (bracket_type, oid), result in zip(bracket_order_ids, results):
                if isinstance(result, Exception):
                    if self._fsm._is_unknown_order_error(result):
                        LOG.info(
                            f"ℹ️ {bracket_type} bracket {oid} already absent (-2011) for {symbol}")
                        order_logger.write({
                            "rid": decision.rid or "manual-close",
                            "event_type": "ORDER_CANCELLED", "symbol": symbol,
                            "order_id": oid, "bracket_type": bracket_type,
                            "reason": "close_cancel_idempotent", "timestamp": get_clock().now_ms()
                        })
                    else:
                        LOG.warning(
                            f"❌ Failed to cancel {bracket_type} bracket {oid} for {symbol}: {result}")
                        order_logger.write({
                            "rid": decision.rid or "manual-close",
                            "event_type": "ORDER_CANCELLATION_FAILED", "symbol": symbol,
                            "order_id": oid, "bracket_type": bracket_type,
                            "reason": "close_cancel_exception", "error": str(result),
                            "timestamp": get_clock().now_ms()
                        })
                else:
                    if self._fsm._is_cancel_success_response(result):
                        LOG.info(
                            f"✅ Cancelled {bracket_type} bracket {oid} for {symbol}")
                        order_logger.write({
                            "rid": decision.rid or "manual-close",
                            "event_type": "ORDER_CANCELLED", "symbol": symbol,
                            "order_id": oid, "bracket_type": bracket_type,
                            "reason": "manual_close", "adapter_response": result,
                            "timestamp": get_clock().now_ms()
                        })
                    else:
                        cancel_status = self._fsm._cancel_status_str(result)
                        LOG.warning(
                            f"❌ Cancel rejected for {bracket_type} bracket {oid}: status={cancel_status}")

        # Re-read the exchange position after bracket cancellation so the close
        # order uses current on-exchange size rather than cached intent state.
        try:
            positions = await self._fsm.adapter.get_open_positions()
            positions_list = [
                p.to_dict() if hasattr(p, 'to_dict') else (
                    p.__dict__ if not isinstance(p, dict) else p)
                for p in positions
            ]
            pos = next(
                (p for p in positions_list if p.get("symbol") == symbol), None)
        except Exception:
            pos = None
        amt = 0.0
        if pos is not None:
            try:
                amt = float(pos["positionAmt"] if "positionAmt" in pos else 0)
            except Exception:
                amt = 0.0
        if abs(amt) < 1e-10:
            LOG.info(f"No open position to close for {symbol}")
            self._fsm._symbol_brackets.pop(symbol, None)
            self._fsm._persist_restore_artifact_snapshot(
                trigger="close_executor:no_position_full",
                allow_empty=True,
            )
            return
        close_side = "SELL" if amt > 0 else "BUY"
        close_qty = str(abs(Decimal(str(amt))))
        close_id = generate_client_order_id(
            "CLOSE", symbol,
            idempotent_key=str((decision.pld or {}).get(
                "idempotent_key") or decision.rid or "manual-close"),
        )
        await self._fsm.adapter.place_market_reduce_only(symbol, close_side, close_qty, new_client_order_id=close_id)
        LOG.info(
            f"Close executed for {symbol}: side={close_side} qty={close_qty}")
        self._fsm._symbol_brackets.pop(symbol, None)
        self._fsm._persist_restore_artifact_snapshot(
            trigger="close_executor:close_executed",
            allow_empty=True,
        )

        # Allow exchange-side settlement to catch up before orphan cleanup.
        lifecycle_cfg = self._fsm.config.domains.execution_position.order_lifecycle
        await get_clock().sleep_ms(lifecycle_cfg.position_close_cleanup_delay_ms)

        # Second-pass reconcile scans open orders for any remaining reduce-only
        # auxiliaries, not just the bracket IDs that were tracked in memory.
        LOG.info(f"🔄 [DEC:CLOSE RECONCILE] Starting sync cleanup for {symbol}")
        try:
            open_orders = await self._fsm.adapter.get_open_orders(symbol)
            open_orders_list = [
                o.to_dict() if hasattr(o, 'to_dict') else (
                    o.__dict__ if not isinstance(o, dict) else o)
                for o in open_orders
            ]
            cancel_tasks = []
            for o in open_orders_list:
                otype = (o.get("type") or "").upper()
                reduce_only = str(
                    o["reduceOnly"] if "reduceOnly" in o else "").lower() == "true"
                close_pos = str(
                    o["closePosition"] if "closePosition" in o else "").lower() == "true"
                if otype in ("STOP_MARKET", "TAKE_PROFIT_MARKET", "LIMIT") and (reduce_only or close_pos):
                    oid = o.get("orderId")
                    cancel_tasks.append(
                        (otype, oid, self._fsm._cancel_order(symbol, oid)))

            if cancel_tasks:
                results = await asyncio.gather(*[task[2] for task in cancel_tasks], return_exceptions=True)
                for (otype, oid, _), result in zip(cancel_tasks, results):
                    if isinstance(result, Exception):
                        if self._fsm._is_unknown_order_error(result):
                            LOG.info(
                                f"ℹ️ [DEC:CLOSE RECONCILE] {otype} {oid} already gone for {symbol} (-2011)")
                        else:
                            LOG.warning(
                                f"❌ [DEC:CLOSE RECONCILE] Failed to cancel {otype} {oid} for {symbol}: {result}")
                            self._fsm._orphan_metrics["errors"] += 1
                    else:
                        if self._fsm._is_cancel_success_response(result):
                            LOG.info(
                                f"✅ [DEC:CLOSE RECONCILE] Cancelled {otype} {oid} for {symbol}")
                            self._fsm._orphan_metrics["reconcile_cancelled"] += 1
                        else:
                            status = self._fsm._cancel_status_str(result)
                            LOG.warning(
                                f"❌ [DEC:CLOSE RECONCILE] Cancel response unexpected for {otype} {oid} (status={status})")
                            self._fsm._orphan_metrics["errors"] += 1

                self._fsm._emit_observability_event("RECONCILE_CANCELLED", {
                    "symbol": symbol,
                    "order_count": len(cancel_tasks),
                    "metric": self._fsm._orphan_metrics["reconcile_cancelled"]
                })
            else:
                LOG.info(
                    f"✅ [DEC:CLOSE RECONCILE] No orphaned brackets found for {symbol}")
        except Exception as e:
            LOG.warning(
                f"⚠️ [DEC:CLOSE RECONCILE] Error during cleanup for {symbol}: {e}")
            self._fsm._orphan_metrics["errors"] += 1

        await self._fsm.order_guardian.cleanup_orphans()
        await self._fsm.order_guardian.reconcile_symbol(symbol, decision.rid)

        # Clear closing flag
        manage = self._fsm.manage_flows.get(symbol)
        if manage:
            manage._closing_position = False
            LOG.info(
                f"🔓 [PHASE A2] Cleared closing flag for {symbol} - CLOSE complete")

        close_elapsed_ms = int(get_clock().now_sec() *
                               1000 - decision.ts) if decision.ts else 0
        self._fsm._emit_observability_event("DEC_CLOSE_COMPLETED", {
            "symbol": symbol, "elapsed_ms": close_elapsed_ms,
            "orphans_cancelled": self._fsm._orphan_metrics["reconcile_cancelled"]
        })

    async def execute_place_order(self, decision: "Message") -> None:
        """Submit a generic auxiliary order from an internal DEC:PLACE_ORDER."""

        pld = decision.pld or {}
        symbol = pld.get("symbol")
        side = pld.get("side")
        qty = pld.get("qty")
        order_type = pld["order_type"] if "order_type" in pld else "LIMIT"
        price = pld.get("price")
        stop_price = pld.get("stopPrice")
        client_id = pld.get("newClientOrderId")
        reduce_only = pld["reduceOnly"] if "reduceOnly" in pld else False

        LOG.info(
            f"Executing PLACE_ORDER: {symbol} {side} {order_type} {qty} @ {price}/{stop_price}")

        try:
            resp = None
            if order_type == "STOP_MARKET" and hasattr(self._fsm.adapter, "place_stop_market_close_position"):
                resp = await self._fsm.adapter.place_stop_market_close_position(
                    symbol, side, str(stop_price), new_client_order_id=client_id)
            elif order_type == "TAKE_PROFIT_MARKET" and hasattr(self._fsm.adapter, "place_take_profit_market_close_position"):
                resp = await self._fsm.adapter.place_take_profit_market_close_position(
                    symbol, side, str(stop_price), new_client_order_id=client_id)
            elif order_type == "LIMIT" and reduce_only and hasattr(self._fsm.adapter, "place_limit_reduce_only"):
                resp = await self._fsm.adapter.place_limit_reduce_only(
                    symbol, side, str(price), qty, new_client_order_id=client_id)
            else:
                if hasattr(self._fsm.adapter, "place_order"):
                    resp = await self._fsm.adapter.place_order(decision)
                else:
                    LOG.error(
                        f"Unsupported order type for PLACE_ORDER: {order_type}")
                    return

            LOG.info(f"✅ PLACE_ORDER success: {resp}")

            # Attach exchange IDs for internally issued bracket/aux orders so the
            # order index can reconcile later websocket/REST updates.
            try:
                if client_id and resp and hasattr(self._fsm.fsm, "order_index") and self._fsm.fsm.order_index:
                    ex_order_id = str(resp.get("orderId"))
                    rid_for_index = str(
                        getattr(decision, "rid", "") or "") or ex_order_id
                    idem_key = (
                        (decision.pld or {}).get("idempotent_key")
                        or getattr(decision, "idempotent_key", None)
                        or rid_for_index or client_id
                    )
                    self._fsm.fsm.order_index.upsert_from_open(
                        rid=rid_for_index, idempotent_key=str(idem_key),
                        clientOrderId=client_id, symbol=symbol,
                        side=str(side).upper() if side else "", order_type=str(order_type),
                    )
                    self._fsm.fsm.order_index.attach_exchange_id(
                        clientOrderId=client_id, exchangeOrderId=ex_order_id,
                    )
            except Exception:
                pass

            # Register brackets if applicable
            if client_id and resp:
                order_id = str(resp.get("orderId"))
                if "_sl" in client_id:
                    self._fsm._symbol_brackets.setdefault(
                        symbol, {})["sl_order_id"] = order_id
                elif "_tp" in client_id:
                    self._fsm._symbol_brackets.setdefault(
                        symbol, {})["tp_order_id"] = order_id

                manage_flow = self._fsm.manage_flows.get(symbol)
                if manage_flow:
                    brackets = self._fsm._symbol_brackets[symbol] if symbol in self._fsm._symbol_brackets else {
                    }
                    current_sl = brackets.get("sl_order_id")
                    current_tp = brackets.get("tp_order_id")
                    manage_flow.set_bracket_ids(current_sl, current_tp)
                self._fsm._persist_restore_artifact_snapshot(
                    trigger="close_executor:aux_bracket_registered",
                    allow_empty=True,
                )

        except Exception as e:
            LOG.error(f"❌ PLACE_ORDER failed: {e}")
