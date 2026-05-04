"""
Pending entry management for execution_position domain.

Extracted from ExecPosFSM (Phase 14A decomposition).
Handles pending entry cancellation, panic killswitch, supersede logic,
and order timeout handling.
"""
from __future__ import annotations

from decimal import Decimal
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Set, Tuple, Optional

from apps.reference.core.time import get_clock
from apps.reference.telemetry.order_logger import order_logger

if TYPE_CHECKING:
    from vfoundation.core.fsm_emit_compat import Message

LOG = logging.getLogger("apps.reference.domains.execution_position.entry_manager")

# FIX-LIFECYCLE-01: Trade lifecycle source-of-truth logger
try:
    from apps.reference.telemetry.trade_lifecycle_logger import trade_lifecycle as _trade_lifecycle
except ImportError:
    _trade_lifecycle = None


class EntryManager:
    """Manages pending entry orders: cancellation, supersede, panic, timeouts."""

    def __init__(self, fsm: Any) -> None:
        self._fsm = fsm

    def cancel_pending_entries_for_symbol(
        self,
        symbol: str,
        reason: str,
        context: str = "",
        filter_order_ids: set[str] | None = None,
    ) -> None:
        """
        EP-01.3-INT: Cancel pending entry orders for a symbol.

        Iterates through watchdog tracked orders (pending_orders + acked_orders)
        and cancels those matching the symbol.
        """
        watchdog = self._fsm.watchdog
        if not watchdog:
            return

        orders_to_cancel = []

        # Check pending_orders (not yet ACKed)
        for order_id, deadline in list(watchdog.pending_orders.items()):
            if deadline.symbol == symbol and (filter_order_ids is None or str(order_id) in filter_order_ids):
                orders_to_cancel.append((order_id, deadline))

        # Check acked_orders (ACKed but not yet filled)
        for order_id, deadline in list(watchdog.acked_orders.items()):
            if deadline.symbol == symbol and (filter_order_ids is None or str(order_id) in filter_order_ids):
                orders_to_cancel.append((order_id, deadline))

        if not orders_to_cancel:
            LOG.debug(f"EP-01.3: No pending entries to cancel for {symbol} ({reason})")
            return

        LOG.info(
            f"EP-01.3: Cancelling {len(orders_to_cancel)} pending entries for {symbol} "
            f"(reason={reason}, context={context})"
        )

        for order_id, deadline in orders_to_cancel:
            # Schedule async cancel
            loop = self._fsm._get_async_loop()
            if loop and self._fsm.adapter and not self._fsm.shadow_mode:
                async def _do_cancel(oid: str, sym: str, dl: Any):
                    try:
                        await self._fsm._cancel_order(sym, oid)
                        LOG.info(f"✅ EP-01.3: Cancelled pending entry {oid} ({reason})")
                        # Remove from watchdog tracking
                        watchdog.on_order_cancel(oid)
                        self._fsm.remove_pending_entry_metadata(oid)
                        # Log cancellation
                        order_logger.write({
                            "rid": dl.rid,
                            "event_type": "ORDER_CANCELLED",
                            "symbol": sym,
                            "order_id": oid,
                            "reason": reason,
                            "context": context,
                            "timestamp": get_clock().now_ms()
                        })
                        # FIX-LIFECYCLE-01: Record cancel in trade lifecycle
                        if _trade_lifecycle is not None:
                            try:
                                _trade_lifecycle.on_cancel(rid=dl.rid, cancel_reason=reason)
                            except Exception:
                                pass
                    except Exception as e:
                        if self._fsm._is_unknown_order_error(e):
                            LOG.info(f"✅ EP-01.3: Pending entry {oid} already absent (-2011)")
                            watchdog.on_order_cancel(oid)
                            self._fsm.remove_pending_entry_metadata(oid)
                        else:
                            LOG.warning(f"EP-01.3: Failed to cancel pending entry {oid}: {e}")

                self._fsm._submit_async(_do_cancel(order_id, symbol, deadline), loop)
            else:
                # Just remove from tracking (shadow mode or no adapter)
                watchdog.on_order_cancel(order_id)
                self._fsm.remove_pending_entry_metadata(order_id)

    def cancel_all_pending_entries(self, reason: str = "CANCEL_PANIC_KILL") -> None:
        """
        PANIC-INT: Cancel ALL pending entry orders across all symbols.
        """
        watchdog = self._fsm.watchdog
        if not watchdog:
            return

        # Collect all symbols with pending entries
        symbols_with_pending = set()
        for deadline in watchdog.pending_orders.values():
            symbols_with_pending.add(deadline.symbol)
        for deadline in watchdog.acked_orders.values():
            symbols_with_pending.add(deadline.symbol)

        if not symbols_with_pending:
            LOG.debug(f"PANIC-INT: No pending entries to cancel ({reason})")
            return

        LOG.warning(
            f"PANIC-INT: Cancelling ALL pending entries for {len(symbols_with_pending)} symbols ({reason})"
        )

        for symbol in symbols_with_pending:
            self.cancel_pending_entries_for_symbol(
                symbol=symbol,
                reason=reason,
                context="panic_killswitch_activated"
            )

    def on_panic_killswitch_activated(self) -> None:
        """
        PANIC-INT: Handle panic killswitch activation.
        """
        LOG.error("PANIC-INT: panic_killswitch ACTIVATED - cancelling all pending entries")

        # Check config flag
        try:
            pe_ttl_cfg = self._fsm.config.domains.execution_position.pending_entry_ttl
            if not pe_ttl_cfg.enabled or not pe_ttl_cfg.cancel_on_panic:
                LOG.info("PANIC-INT: cancel_on_panic disabled, skipping")
                return
        except AttributeError:
            LOG.warning("PANIC-INT: pending_entry_ttl config not loaded, cancelling anyway")

        self.cancel_all_pending_entries("CANCEL_PANIC_KILL")

    def process_queued_supersede(self, symbol: str) -> None:
        """
        EP-01.3-SUPERSEDE-ACK: Process queued DEC:OPEN after cancel is confirmed.
        """
        # Remove from canceling set
        self._fsm.clear_supersede_canceling(symbol)

        # Get queued decision
        queued_data = self._fsm.dequeue_supersede(symbol)
        if not queued_data:
            LOG.debug(f"EP-01.3: No queued supersede for {symbol}")
            return

        decision = queued_data.get("decision")
        queued_at = queued_data.get("queued_at", 0)
        age_sec = get_clock().now_sec() - queued_at

        if not decision:
            LOG.warning(f"EP-01.3: Queued supersede for {symbol} has no decision")
            return

        LOG.info(
            f"EP-01.3: Executing queued supersede DEC:OPEN for {symbol} (waited {age_sec:.2f}s)"
        )

        # Re-submit the decision for processing
        loop = self._fsm._get_async_loop()
        if loop:
            self._fsm._submit_async(self._fsm._execute_decision(decision), loop)
        else:
            LOG.error(f"EP-01.3: No event loop for queued supersede {symbol}")

    async def handle_order_timeout(self, deadline: Any) -> None:
        """Handle a timed-out order with NRR-019 logging and idempotent cancellation."""
        from vfoundation.core.fsm_emit_compat import Message, emit_compat
        from apps.reference.utils.accessors import aget
        from ...terminal_order_contracts import emit_canonical_terminal_order_event

        LOG.warning(
            f"Order timeout: {deadline.order_id} ({deadline.symbol}) - {deadline.timeout_type.value}, "
            f"nrr_code=NRR-019, corr_id={deadline.corr_id}, rid={deadline.rid}"
        )

        # Log to OrderLoggerV1
        order_logger.write({
            "rid": deadline.rid or f"timeout_{deadline.order_id}",
            "event_type": "ORDER_TIMEOUT",
            "symbol": deadline.symbol,
            "client_order_id": deadline.client_order_id,
            "order_id": deadline.order_id,
            "nrr_code": "NRR-019",
            "why": f"Order timeout: {deadline.timeout_type.value}",
            "source_fsm": "ExecPosFSM",
            "metadata": {
                "timeout_type": deadline.timeout_type.value,
                "corr_id": deadline.corr_id
            }
        })

        # Attempt idempotent cancellation if adapter is available
        if self._fsm.adapter and not self._fsm.shadow_mode:
            try:
                self._fsm.watchdog.cancel_attempt_count += 1
                cancel_result = await self._fsm._cancel_order(deadline.symbol, deadline.order_id)

                if self._fsm._is_cancel_success_response(cancel_result):
                    self._fsm.watchdog.cancel_success_count += 1
                    LOG.info(
                        f"✅ Cancelled timed-out order {deadline.order_id}: {cancel_result}")
                    order_logger.write({
                        "rid": deadline.rid,
                        "event_type": "ORDER_CANCELLED",
                        "symbol": deadline.symbol,
                        "order_id": deadline.order_id,
                        "reason": "timeout_cancellation",
                        "timeout_type": deadline.timeout_type.value,
                        "adapter_response": cancel_result,
                        "timestamp": get_clock().now_ms()
                    })
                    self._fsm.watchdog.on_order_cancel(deadline.order_id)
                    await emit_canonical_terminal_order_event(
                        fsm=self._fsm.fsm,
                        event_name="EVT:ORDER_STATE_CHANGED",
                        payload={
                            "symbol": deadline.symbol,
                            "orderId": deadline.order_id,
                            "client_order_id": deadline.client_order_id,
                            "status": "CANCELED",
                            "reason": "timeout_cancellation",
                            "timeout_type": deadline.timeout_type.value,
                            "corr_id": deadline.corr_id,
                        },
                        rid=deadline.rid,
                        src="execution_position",
                        dst="monitoring",
                        why="timeout_cancellation",
                        logger=aget(self._fsm, "logger", None),
                        write_wal=True,
                        fallback_ts_ms=get_clock().now_ms(),
                    )
                else:
                    status = str(
                        cancel_result["status"]
                        if isinstance(cancel_result, dict) and "status" in cancel_result
                        else ""
                    ).upper()
                    LOG.error(
                        f"❌ Cancel rejected for timed-out order {deadline.order_id}: "
                        f"status={status}, result={cancel_result}"
                    )
                    order_logger.write({
                        "rid": deadline.rid,
                        "event_type": "ORDER_CANCELLATION_FAILED",
                        "symbol": deadline.symbol,
                        "order_id": deadline.order_id,
                        "reason": f"timeout_cancel_rejected_status_{status}",
                        "timeout_type": deadline.timeout_type.value,
                        "adapter_response": cancel_result,
                        "timestamp": get_clock().now_ms()
                    })

            except Exception as e:
                if self._fsm._is_unknown_order_error(e):
                    self._fsm.watchdog.cancel_success_count += 1
                    LOG.info(
                        f"✅ Timed-out order {deadline.order_id} already absent (-2011)")
                    order_logger.write({
                        "rid": deadline.rid,
                        "event_type": "ORDER_CANCELLED",
                        "symbol": deadline.symbol,
                        "order_id": deadline.order_id,
                        "reason": "timeout_cancel_idempotent",
                        "timeout_type": deadline.timeout_type.value,
                        "timestamp": get_clock().now_ms()
                    })
                    self._fsm.watchdog.on_order_cancel(deadline.order_id)
                    await emit_canonical_terminal_order_event(
                        fsm=self._fsm.fsm,
                        event_name="EVT:ORDER_STATE_CHANGED",
                        payload={
                            "symbol": deadline.symbol,
                            "orderId": deadline.order_id,
                            "client_order_id": deadline.client_order_id,
                            "status": "CANCELED",
                            "reason": "timeout_cancel_idempotent",
                            "timeout_type": deadline.timeout_type.value,
                            "corr_id": deadline.corr_id,
                        },
                        rid=deadline.rid,
                        src="execution_position",
                        dst="monitoring",
                        why="timeout_cancel_idempotent",
                        logger=aget(self._fsm, "logger", None),
                        write_wal=True,
                        fallback_ts_ms=get_clock().now_ms(),
                    )
                else:
                    LOG.warning(
                        f"Failed to cancel timed-out order {deadline.order_id}: {e}")
                    order_logger.write({
                        "rid": deadline.rid,
                        "event_type": "ORDER_CANCELLATION_FAILED",
                        "symbol": deadline.symbol,
                        "order_id": deadline.order_id,
                        "reason": "timeout_cancel_exception",
                        "timeout_type": deadline.timeout_type.value,
                        "error": str(e),
                        "timestamp": get_clock().now_ms()
                    })

        # Record timeout metric
        if self._fsm.metrics_collector:
            self._fsm.metrics_collector.record_order_timeout()

        # Alert on circuit breaker conditions (multiple timeouts)
        if self._fsm.alert_manager:
            timeout_key = f"timeout_{deadline.symbol}"
            if not hasattr(self._fsm, '_timeout_counts'):
                self._fsm._timeout_counts = {}
            cur = self._fsm._timeout_counts[timeout_key] if timeout_key in self._fsm._timeout_counts else 0
            self._fsm._timeout_counts[timeout_key] = cur + 1

            if self._fsm._timeout_counts[timeout_key] >= 3:
                try:
                    self._fsm.alert_manager.check_circuit_breaker(True, 300)
                    LOG.warning(
                        f"Circuit breaker alert triggered for {deadline.symbol} due to repeated timeouts")
                except Exception as e:
                    LOG.error(f"Error triggering circuit breaker alert: {e}")

        # Emit event for monitoring
        timeout_msg = Message(
            op="EVT",
            verb="ORDER_TIMEOUT",
            intent="OBSERVATION",
            src="execution_position",
            dst="monitoring",
            rid=deadline.rid or f"timeout_{deadline.order_id}",
            pld={
                "order_id": deadline.order_id,
                "client_order_id": deadline.client_order_id,
                "symbol": deadline.symbol,
                "timeout_type": deadline.timeout_type.value,
                "corr_id": deadline.corr_id,
                "nrr_code": "NRR-019"
            },
            why="order_timeout_expired",
        )

        try:
            await emit_compat(self._fsm.fsm, timeout_msg, logger=aget(self._fsm, "logger", None))
        except Exception as e:
            LOG.error(f"Failed to emit timeout event: {e}")

    def evaluate_supersede_reprice_guard(
        self,
        symbol: str,
        decision: Message,
        pending_order_ids: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Evaluate whether a same-side LIMIT supersede materially improves price."""
        try:
            pe_ttl_cfg = self._fsm.config.domains.execution_position.pending_entry_ttl
            guard_cfg = pe_ttl_cfg.supersede_reprice_guard
        except AttributeError:
            return None

        if guard_cfg is None:
            return None
        try:
            if not bool(guard_cfg.enabled):
                return None
        except AttributeError:
            return None

        pld = decision.pld or {}
        if str(pld.get("order_type", "")).upper() != "LIMIT":
            return None

        new_side = str(pld.get("side", "")).upper()
        new_price_raw = pld.get("price")
        if not new_side or new_price_raw in (None, ""):
            return None

        try:
            new_price = Decimal(str(new_price_raw))
        except Exception:
            return None
        if new_price <= 0:
            return None

        features_snap = self._fsm._last_features_cache.get(symbol) or {}
        feats = features_snap.get("features", {}) if isinstance(
            features_snap, dict) else {}
        atr_14 = None
        atr_raw = feats.get("atr_14")
        if atr_raw not in (None, ""):
            try:
                atr_14 = Decimal(str(atr_raw))
            except Exception:
                atr_14 = None
        if atr_14 is not None and atr_14 <= 0:
            atr_14 = None

        analyses: List[Dict[str, Any]] = []
        for order_id in pending_order_ids:
            meta = self._fsm.get_pending_entry_metadata(order_id)
            if meta is None or str(meta.side).upper() != new_side:
                return None
            old_price = Decimal(str(meta.limit_price))
            bps_threshold_px = (
                old_price
                * Decimal(str(getattr(guard_cfg, "min_price_improvement_bps", 0.0)))
                / Decimal("10000")
            )
            atr_threshold_px = Decimal("0")
            atr_mult = Decimal(
                str(getattr(guard_cfg, "min_price_improvement_atr_mult", 0.0)))
            if atr_14 is not None and atr_mult > 0:
                atr_threshold_px = atr_14 * atr_mult
            threshold_px = max(bps_threshold_px, atr_threshold_px)
            improvement_px = new_price - old_price if new_side == "BUY" else old_price - new_price
            analyses.append(
                {
                    "order_id": order_id,
                    "old_price": str(old_price),
                    "new_price": str(new_price),
                    "improvement_px": float(improvement_px),
                    "threshold_px": float(threshold_px),
                    "allow_cancel": improvement_px >= threshold_px,
                }
            )

        if not analyses:
            return None
        decision_summary = {
            "symbol": symbol,
            "side": new_side,
            "analyses": analyses,
            "enforce": bool(getattr(guard_cfg, "enforce", False)),
            "allow_cancel": all(bool(item.get("allow_cancel")) for item in analyses),
        }
        if hasattr(self, "_emit_observability_event"):
            try:
                self._fsm._emit_observability_event(
                    "SUPERSEDE_REPRICE_GUARD", decision_summary)
            except Exception:
                pass
        return decision_summary


    def evaluate_advanced_stale_cancel(self, symbol: str, new_regime: str) -> None:
        """Cancel pending entries only when regime, age, and drift gates all pass."""
        try:
            pe_cfg = self._fsm.config.domains.execution_position.pending_entry_ttl
            adv = pe_cfg.advanced_stale_cancel
        except AttributeError:
            return
        if adv is None or not adv.enabled:
            return

        candidates: List[Tuple[str, Any]] = []
        if self._fsm.watchdog:
            for oid, dl in list(self._fsm.watchdog.pending_orders.items()):
                if dl.symbol == symbol:
                    candidates.append((oid, dl))
            for oid, dl in list(self._fsm.watchdog.acked_orders.items()):
                if dl.symbol == symbol:
                    candidates.append((oid, dl))
        if not candidates:
            return

        now_ms = get_clock().now_ms()
        features_snap = self._fsm._last_features_cache.get(symbol)
        approved_order_ids: Set[str] = set()

        for order_id, _deadline in candidates:
            meta = self._fsm.get_pending_entry_metadata(order_id)
            if meta is None:
                continue

            if meta.cancelable_regimes is not None:
                if new_regime not in meta.cancelable_regimes:
                    continue
            else:
                side_may = set(
                    getattr(adv, "may_cancel_regimes", {}).get(meta.side, []))
                never = set(
                    getattr(adv, "never_cancel_regimes", ["UNCERTAIN"]))
                if new_regime not in (side_may - never):
                    continue

            age_ms = now_ms - meta.placed_at_ms
            min_age_ms = adv.min_age_before_cancel_sec * 1000
            if age_ms < min_age_ms:
                continue

            if features_snap is None:
                continue
            feats = features_snap.get("features", {})
            price_raw = feats.get("price")
            atr_raw = feats.get("atr_14")
            if price_raw is None or atr_raw is None:
                continue
            try:
                current_price = Decimal(str(price_raw))
                atr_14 = Decimal(str(atr_raw))
                limit_price = Decimal(str(meta.limit_price))
            except Exception:
                continue
            if atr_14 <= 0:
                continue

            threshold = atr_14 * Decimal(str(adv.drift_away.atr_mult))
            drift = current_price - limit_price if meta.side == "BUY" else limit_price - current_price
            if drift < threshold:
                continue
            approved_order_ids.add(order_id)

        if approved_order_ids:
            self.cancel_pending_entries_for_symbol(
                symbol=symbol,
                reason="CANCEL_STALE_REGIME_ADVANCED",
                context=f"regime={new_regime} approved={sorted(approved_order_ids)}",
                filter_order_ids=approved_order_ids,
            )

