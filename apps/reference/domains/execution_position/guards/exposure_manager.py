"""
Exposure management for execution_position domain.

Extracted from ExecPosFSM (Phase 14A decomposition).
Handles exposure fail-closed checks, shadow notional auditing,
cancel event processing, and exposure summary updates.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional

from apps.reference.core.time import get_clock
from apps.reference.telemetry.order_logger import order_logger

if TYPE_CHECKING:
    from vfoundation.core.fsm_emit_compat import Message

LOG = logging.getLogger(
    "apps.reference.domains.execution_position.exposure_manager"
)


class ExposureManager:
    """Manages exposure checks, shadow auditing, and cancel handling."""

    def __init__(self, fsm: Any) -> None:
        self._fsm = fsm

    def check_exposure_fail_closed(self, msg: "Message") -> Optional["Message"]:
        """
        EXP-FIX: Check exposure limits with fail-closed behavior.

        Returns error Message if request should be blocked, else None.
        """
        from vfoundation.core.fsm_emit_compat import Message
        from vfoundation.dr import wal

        pld = msg.pld or {}
        symbol = pld.get("symbol")
        qty = pld.get("qty")
        price_ref = pld.get("price_ref")

        if not symbol or not qty or not price_ref:
            LOG.warning(
                f"EXPOSURE_CHECK_SKIP: Missing required fields for {symbol}")
            return None

        side_raw = pld.get("side")
        side_str = getattr(side_raw, "value", side_raw)
        side = str(side_str).strip().upper() if side_str is not None else ""
        if not side:
            raise ValueError(
                "Order side is missing in payload. Cannot default to BUY."
            )
        if side not in {"BUY", "SELL", "LONG", "SHORT"}:
            raise ValueError(f"Order side is invalid: {side_raw!r}")

        try:
            notional_abs = Decimal(str(qty)) * Decimal(str(price_ref))
            notional_signed = - \
                notional_abs if side in {"SELL", "SHORT"} else notional_abs

            reduce_only = bool(pld.get("reduce_only", False))
            reserve_key = pld.get(
                "idempotent_key") or msg.rid or f"rid_{msg.rid}"

            # DEF-E06: Size-aware flip detection.
            # A "flip" (opposite-side order) should only free margin proportional to
            # how much of the existing position is being closed. A tiny opposite order
            # must NOT free the full current position's margin (the old side-only bug).
            is_flip = False
            # default: treat as full position flip if is_flip=True
            flip_fraction = Decimal("1")
            positions = self._fsm._latest_portfolio_state.get(
                "positions") or []
            for p in positions:
                if isinstance(p, dict) and str(p.get("symbol", "")).strip() == symbol:
                    curr_qty_str = str(p.get("net_position", "0"))
                    try:
                        curr_qty = Decimal(curr_qty_str)
                        if curr_qty != 0:
                            curr_side_is_buy = curr_qty > 0
                            intent_side_is_buy = (side in {"BUY", "LONG"})
                            if curr_side_is_buy != intent_side_is_buy:
                                is_flip = True
                                # DEF-E06: compute what fraction of the position this order closes.
                                # order_qty closes min(order_qty, abs(curr_qty)) contracts.
                                # flip_fraction = that amount / abs(curr_qty)
                                order_qty_dec = Decimal(str(qty))
                                curr_position_qty = abs(curr_qty)
                                closed_qty = min(
                                    order_qty_dec, curr_position_qty)
                                flip_fraction = closed_qty / \
                                    curr_position_qty  # in (0, 1]
                    except Exception:
                        pass
                    break

            exposure_check = self._fsm.exposure_guard.can_open(
                symbol, notional_signed, self._fsm._latest_portfolio_state,
                is_flip=is_flip, flip_fraction=flip_fraction,
            )

            if not exposure_check["allowed"]:
                reason = exposure_check["reason"]
                stale_sec = exposure_check["stale_sec"] if "stale_sec" in exposure_check else 0

                error_msg = Message(
                    op="ERR",
                    verb="OPEN",
                    src="execution_position",
                    dst=msg.src,
                    rid=msg.rid,
                    pld={
                        "reason": reason,
                        "stale_sec": stale_sec,
                        "symbol": symbol,
                        "side": side,
                        "idempotent_key": str(pld.get("idempotent_key") or ""),
                        "requested_notional": str(notional_signed),
                    },
                    why=f"exposure_fail_closed_{reason.lower()}",
                )

                try:
                    wal.append(error_msg.model_dump())
                except Exception as wal_e:
                    LOG.warning(f"Failed to write ERR:OPEN to WAL: {wal_e}")

                LOG.error(
                    f"EXPOSURE_FAIL_CLOSED_OPEN_BLOCKED: rid={msg.rid} symbol={symbol} "
                    f"side={side} reason={reason} stale_sec={stale_sec}"
                )

                if hasattr(self._fsm, "metrics_collector") and self._fsm.metrics_collector:
                    self._fsm.metrics_collector.record_exposure_fail_closed(
                        reason)

                return error_msg

            # Soft-limit clipping
            try:
                clipped_abs = exposure_check.get("clipped_notional_abs") if isinstance(
                    exposure_check, dict) else None
                if clipped_abs is not None:
                    clipped_abs_dec = Decimal(str(clipped_abs))
                    if clipped_abs_dec > Decimal("0") and clipped_abs_dec < abs(notional_signed):
                        price_dec = Decimal(str(price_ref))
                        if price_dec > Decimal("0"):
                            new_qty = clipped_abs_dec / price_dec
                            pld["qty"] = str(new_qty)
                            pld["exposure_clip"] = {
                                "requested_notional_abs": str(abs(notional_signed)),
                                "clipped_notional_abs": str(clipped_abs_dec),
                                "clip_reasons": exposure_check.get("clip_reasons", []),
                            }
                            notional_abs = clipped_abs_dec
                            notional_signed = - \
                                clipped_abs_dec if side in {
                                    "SELL", "SHORT"} else clipped_abs_dec
            except Exception:
                pass

            # EXP-FIX: Periodic shadow notional check
            shadow_cfg = self._fsm.config.domains.execution_position.shadow_check
            self._fsm._shadow_check_counter += 1

            if shadow_cfg.enabled and self._fsm._shadow_check_counter % shadow_cfg.check_every_n_requests == 0 and self._fsm.adapter:
                loop = self._fsm._get_async_loop()
                if loop:
                    self._fsm._submit_async(self.check_shadow_notional(), loop)

            # Reserve exposure
            self._fsm.exposure_guard.reserve(
                reserve_key,
                notional_abs,
                reduce_only=reduce_only,
                symbol=str(symbol),
                side=side,
            )

            return None

        except Exception as e:
            LOG.error(f"EXPOSURE_CHECK_ERROR: {e}", exc_info=True)

            reason = "EXPOSURE_CHECK_ERROR"
            error_msg = Message(
                op="ERR",
                verb="OPEN",
                src="execution_position",
                dst=msg.src,
                rid=msg.rid,
                pld={
                    "reason": reason,
                    "symbol": symbol,
                    "side": side,
                    "idempotent_key": str(pld.get("idempotent_key") or ""),
                },
                why="exposure_fail_closed_exception",
            )

            try:
                wal.append(error_msg.model_dump())
            except Exception as wal_e:
                LOG.warning(
                    f"Failed to write ERR:OPEN(EXPOSURE_CHECK_ERROR) to WAL: {wal_e}")

            return error_msg

    async def check_shadow_notional(self) -> None:
        """
        EXP-FIX: Periodic shadow notional check for safety auditing.
        """
        from vfoundation.core.fsm_emit_compat import Message, emit_compat

        try:
            if not hasattr(self._fsm, "adapter") or not self._fsm.adapter:
                return

            if not hasattr(self._fsm.adapter, "get_positions_notional_usd_shadow"):
                return

            shadow_notional = await self._fsm.adapter.get_positions_notional_usd_shadow()

            portfolio_notional = Decimal(
                str(self._fsm._latest_portfolio_state["open_positions_usd"]
                    if "open_positions_usd" in self._fsm._latest_portfolio_state else "0")
            )

            shadow_cfg = self._fsm.config.domains.execution_position.shadow_check
            # DEF-E19: Use Decimal for notional comparison — avoid float() precision loss
            shadow_notional_dec = Decimal(str(shadow_notional))
            max_notional = max(shadow_notional_dec,
                               portfolio_notional, Decimal("1"))
            diff_abs = abs(shadow_notional_dec - portfolio_notional)
            diff_pct = (diff_abs / max_notional) * 100

            use_absolute = (
                shadow_cfg.use_absolute_for_large_portfolios
                and max_notional >= shadow_cfg.large_portfolio_threshold_usd
            )

            if use_absolute:
                is_mismatch = diff_abs > shadow_cfg.absolute_threshold_usd
                threshold_desc = f"${shadow_cfg.absolute_threshold_usd:.0f}"
            else:
                is_mismatch = diff_pct > shadow_cfg.tolerance_pct
                threshold_desc = f">{shadow_cfg.tolerance_pct}%"

            if is_mismatch:
                LOG.warning(
                    f"EXPOSURE_MISMATCH: portfolio={portfolio_notional}, shadow={shadow_notional}, "
                    f"diff={diff_pct:.2f}%, threshold={threshold_desc}"
                )
                self._fsm.exposure_guard._increment_metric(
                    "exposure_mismatch_total", "shadow_check"
                )

                mismatch_msg = Message(
                    op="EVT",
                    verb="EXPOSURE_MISMATCH",
                    src="execution_position",
                    dst="monitoring",
                    rid="shadow_check",
                    pld={
                        "portfolio_notional": str(portfolio_notional),
                        "shadow_notional": shadow_notional,
                        "diff_pct": diff_pct,
                        "threshold": threshold_desc,
                    },
                    why="shadow_notional_mismatch",
                )
                await emit_compat(self._fsm.fsm, mismatch_msg, logger=LOG)
            else:
                LOG.debug(
                    f"SHADOW_CHECK_OK: portfolio={portfolio_notional}, shadow={shadow_notional}"
                )

        except Exception as e:
            LOG.error(f"SHADOW_CHECK_ERROR: {e}", exc_info=True)

    def handle_cancel_event(self, msg: "Message") -> None:
        """
        EXP-FIX: Handle order cancellation events for exposure summary update.
        """
        from vfoundation.core.fsm_emit_compat import Message
        from ..flows.manage.pending_brackets_wal import write_pending_brackets_cleared

        pld = msg.pld or {}
        symbol = pld.get("symbol")
        order_id = pld.get("order_id") or pld.get("orderId")
        client_order_id = pld.get("client_order_id")

        LOG.info(
            f"CANCEL_EVENT: Processing cancellation for {symbol} order {order_id}")

        # DEF-WATCHDOG-DEREG-AFTER-FILL: Ensure terminal states remove order from watchdog
        # This prevents stale fill_timeout events for cancelled/rejected/expired orders.
        if order_id and hasattr(self._fsm, "watchdog") and self._fsm.watchdog:
            _status = str(pld.get("status") or "").upper()
            if _status in {"CANCELED", "REJECTED", "EXPIRED", "FILLED"}:
                self._fsm.watchdog.on_order_cancel(str(order_id))

        # Cleanup pending brackets if entry was cancelled
        if order_id and order_id in self._fsm._pending_brackets:
            bracket_data = self._fsm._pending_brackets.pop(order_id, None)
            try:
                write_pending_brackets_cleared(
                    entry_order_id=order_id,
                    reason="cancelled",
                    symbol=bracket_data.get(
                        "symbol", "") if bracket_data else "",
                )
            except Exception as e:
                LOG.warning(f"Failed to clear pending brackets from WAL: {e}")
            self._fsm._persist_restore_artifact_snapshot(
                trigger="bracket_deferred_cleared:cancelled",
                allow_empty=True,
            )
            LOG.info(
                f"📌 [LIMIT-DEFERRED] Cleaned up pending brackets for cancelled entry {order_id}"
            )

        # TASK40: Mark order terminal in OrderIndex
        try:
            if hasattr(self._fsm.fsm, "order_index") and self._fsm.fsm.order_index:
                ref = None
                if order_id:
                    ref = self._fsm.fsm.order_index.get(
                        exchangeOrderId=str(order_id))
                if ref is None and client_order_id:
                    ref = self._fsm.fsm.order_index.get(
                        clientOrderId=str(client_order_id))
                if ref is not None:
                    self._fsm.fsm.order_index.mark_terminal(ref)
        except Exception:
            pass

        # Emit exposure summary update after cancellation
        try:
            exposure_summary = self._fsm.exposure_guard.get_exposure_summary()
            exposure_msg = Message(
                op="EVT",
                verb="EXPOSURE_SUMMARY_UPDATED",
                src="execution_position",
                dst="monitoring",
                rid=pld.get("rid") or msg.rid or f"cancel_{order_id}",
                pld={
                    "exposure_summary": exposure_summary,
                    "portfolio_state": getattr(
                        self._fsm, "_latest_portfolio_state", None),
                    "timestamp_ms": get_clock().now_ms(),
                    "cancel_order_id": order_id,
                    "cancel_symbol": symbol,
                    "cancel_client_order_id": client_order_id,
                    "update_reason": "order_cancelled",
                },
                why="order_cancelled_exposure_update",
            )
            loop = self._fsm._get_async_loop()
            if loop:
                self._fsm._submit_async(
                    self.emit_exposure_update_async(exposure_msg), loop)
            else:
                LOG.warning(
                    "No event loop available for cancel exposure update")
        except Exception as e:
            LOG.error(
                f"CANCEL_EVENT_ERROR: Failed to emit exposure update for {order_id}: {e}")

        # EP-01.3-SUPERSEDE-ACK: Check if this cancel allows queued supersede
        if symbol and symbol in self._fsm._supersede_canceling:
            has_more_pending = False
            if self._fsm.watchdog:
                for deadline in self._fsm.watchdog.pending_orders.values():
                    if deadline.symbol == symbol:
                        has_more_pending = True
                        break
                if not has_more_pending:
                    for deadline in self._fsm.watchdog.acked_orders.values():
                        if deadline.symbol == symbol:
                            has_more_pending = True
                            break

            if not has_more_pending:
                LOG.info(
                    f"EP-01.3: {symbol} cancel confirmed, processing queued supersede")
                self._fsm._entry_mgr.process_queued_supersede(symbol)

    async def emit_exposure_update_async(self, msg: "Message") -> None:
        """Asynchronously emit exposure update event."""
        from vfoundation.core.fsm_emit_compat import emit_compat
        from apps.reference.utils.accessors import aget
        try:
            await emit_compat(self._fsm.fsm, msg, logger=aget(self._fsm, "logger", None))
        except Exception as e:
            LOG.exception(f"Failed to emit exposure update event: {e}")
