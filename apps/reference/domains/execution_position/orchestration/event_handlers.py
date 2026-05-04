"""
Event handlers for execution_position domain.

Extracted from ExecPosFSM (Phase 14A decomposition).
Handles regime detection, portfolio state updates, order ACK/FILL events,
and tidy gate logic.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Dict

from apps.reference.core.time import get_clock
from apps.reference.contracts.runtime_regime_layers import (
    normalize_structural_regime_label,
    should_apply_global_execution_regime,
)
from ..state.truth_hardening import (
    build_position_signature,
    get_execution_truth_hardening,
)
from apps.reference.domains.execution_position.utils import classify_client_order_id
from apps.reference.utils.accessors import aget, dget

if TYPE_CHECKING:
    from vfoundation.core.fsm_emit_compat import Message

LOG = logging.getLogger(
    "apps.reference.domains.execution_position.event_handlers"
)

# FIX-LIFECYCLE-01: Trade lifecycle logger
try:
    from apps.reference.telemetry.trade_lifecycle_logger import trade_lifecycle as _trade_lifecycle
except ImportError:
    _trade_lifecycle = None

# ORDER LOGGER INT
try:
    from apps.reference.telemetry.order_logger import get_order_logger as _get_order_logger
except ImportError:
    _get_order_logger = None


class EPEventHandlers:
    """Handles FSM bus events for execution_position domain."""

    def __init__(self, fsm: Any) -> None:
        self._fsm = fsm

    def _resolve_position_close_reason(self, symbol: str) -> str:
        close_reason = "POSITION_CLOSED_DETECTED"
        try:
            cached_reason = self._fsm._last_close_reason_by_symbol.pop(
                symbol, None)
        except Exception:
            cached_reason = None

        normalized_cached_reason = str(cached_reason or "").strip().upper()
        if normalized_cached_reason:
            return normalized_cached_reason

        proof_getter = getattr(
            self._fsm, "get_recent_terminal_close_proof", None)
        if not callable(proof_getter):
            return close_reason

        try:
            proof = proof_getter(symbol)
        except Exception:
            proof = None

        normalized_proof_reason = str(
            (proof or {}).get("close_reason") or ""
        ).strip().upper()
        return normalized_proof_reason or close_reason

    def on_features_calculated(self, event: "Message") -> None:
        """Cache latest features snapshot for runtime adapters."""
        payload = event.pld or {}
        symbol = payload.get("symbol")
        if not symbol:
            return
        self._fsm._last_features_cache[str(symbol)] = dict(payload)

    def on_regime_detected(self, event: "Message") -> None:
        """
        EP-01: Handle EVT:REGIME_DETECTED to update ExposureGuard risk limits.
        EP-01.3-INT: Cancel pending entry orders on regime change.
        """
        from apps.reference.core.types.regime_types import map_regime_to_bucket

        pld = event.pld or {}
        regime_str = normalize_structural_regime_label(pld.get("regime"))
        symbol = pld.get("symbol")
        if not regime_str:
            LOG.warning(
                "EP-01: EVT:REGIME_DETECTED missing 'regime' field, skipping")
            return

        if symbol:
            self._fsm._last_regime_by_symbol[str(symbol)] = str(regime_str)

        if should_apply_global_execution_regime(pld):
            bucket = map_regime_to_bucket(regime_str)
            self._fsm.exposure_guard.on_regime_changed(bucket)

        if should_apply_global_execution_regime(pld):
            LOG.info(
                f"EP-01: Global execution regime adaptation triggered: label={regime_str} -> bucket={bucket.value}, "
                f"new_ratio={float(self._fsm.exposure_guard.max_directional_ratio):.2f}"
            )
        else:
            LOG.info(
                f"EP-01: Structural regime cached for {symbol or 'unknown'} without global exposure adaptation "
                f"(layer={pld.get('regime_layer', 'structural')}, scope={pld.get('regime_scope', 'per_symbol')})"
            )

        # EP-01.3-INT: Cancel pending entry orders on regime change
        try:
            pe_ttl_cfg = self._fsm.config.domains.execution_position.pending_entry_ttl
            if pe_ttl_cfg.enabled and pe_ttl_cfg.cancel_on_regime_change and symbol:
                adv = getattr(pe_ttl_cfg, "advanced_stale_cancel", None)
                if adv is not None and getattr(adv, "enabled", False):
                    self._fsm._evaluate_advanced_stale_cancel(
                        symbol, str(regime_str))
                else:
                    cancel_mode = getattr(
                        pe_ttl_cfg, 'regime_change_cancel_mode', 'immediate')
                    if cancel_mode == 'let_ttl_expire':
                        LOG.info(
                            f"EP-01.3: Regime changed for {symbol} -> {regime_str}, "
                            f"but regime_change_cancel_mode=let_ttl_expire, skipping cancel"
                        )
                    else:
                        self._fsm._entry_mgr.cancel_pending_entries_for_symbol(
                            symbol=symbol,
                            reason="CANCEL_STALE_REGIME",
                            context=f"regime_changed_to_{regime_str}"
                        )
        except AttributeError:
            pass

    def on_portfolio_state_updated(self, event: "Message") -> None:
        """
        Handle EVT:PORTFOLIO_STATE_UPDATED events to update exposure guard state.
        """
        from vfoundation.core.fsm_emit_compat import (
            Message,
            emit_compat,
            resolve_emit_compat_mode,
        )

        trace_stage = getattr(
            self._fsm, "_record_portfolio_event_trace_stage", None)

        self._fsm._latest_portfolio_state = event.pld or {}
        if callable(trace_stage):
            trace_stage(event, "latest_portfolio_state_set")

        # EXP-LEVERAGE-001: Update exposure guard with latest portfolio state
        self._fsm.exposure_guard.on_portfolio(
            self._fsm._latest_portfolio_state)

        # ORDER_INDEX: Best-effort TTL cleanup
        try:
            if hasattr(self._fsm.fsm, "order_index") and self._fsm.fsm.order_index:
                self._fsm.fsm.order_index.expire()
        except Exception:
            pass

        # EVT:EXPOSURE_SUMMARY_UPDATED after portfolio update
        try:
            exposure_summary = self._fsm.exposure_guard.get_exposure_summary()
            exposure_msg = Message(
                op="EVT",
                verb="EXPOSURE_SUMMARY_UPDATED",
                src="execution_position",
                dst="decision_making",
                rid="portfolio_update",
                pld={
                    "exposure_summary": exposure_summary,
                    "portfolio_state": self._fsm._latest_portfolio_state,
                    "timestamp_ms": get_clock().now_ms()
                },
                why="exposure_summary_updated_after_portfolio_change",
            )

            async def _do_emit_exposure():
                try:
                    emit = getattr(self._fsm.fsm, "emit", None)
                    mode = resolve_emit_compat_mode(
                        self._fsm.fsm,
                        emit=emit,
                        logger=LOG,
                    )
                    if mode == "message" and emit is not None:
                        result = emit(exposure_msg)
                        if hasattr(result, "__await__"):
                            await result
                    elif mode in {"op_verb_payload_why", "op_payload_why"}:
                        await emit_compat(self._fsm.fsm, exposure_msg, logger=LOG)
                    else:
                        LOG.error(
                            "Failed to emit exposure summary: unresolved emit contract"
                        )
                        return
                except Exception as ex:
                    LOG.error(f"Failed to emit exposure summary: {ex}")

            loop = self._fsm._get_async_loop()
            if loop:
                self._fsm._submit_async(_do_emit_exposure(), loop)
        except Exception as e:
            LOG.debug(f"Failed to prepare exposure summary update: {e}")

        # Detect position closures
        try:
            positions = self._fsm._latest_portfolio_state.get(
                "positions") or []
            current_amts: Dict[str, float] = {}
            for pos in positions:
                sym = pos.get("symbol")
                if not sym:
                    continue
                try:
                    current_amts[sym] = float(
                        pos.get("net_position") or pos.get("positionAmt") or 0.0)
                except Exception:
                    current_amts[sym] = 0.0

            epsilon = 1e-10
            all_syms = set(self._fsm._prev_position_amts.keys()
                           ) | set(current_amts.keys())
            hardening = get_execution_truth_hardening(self._fsm)
            if hardening is not None:
                portfolio_payload = self._fsm._latest_portfolio_state or {}
                for sym in all_syms:
                    hardening.observe_portfolio_state(
                        symbol=sym,
                        position_signature=build_position_signature(
                            portfolio_payload,
                            sym,
                        ),
                    )
            for sym in all_syms:
                prev_amt = float(self._fsm._prev_position_amts.get(sym, 0.0))
                now_amt = float(current_amts.get(sym, 0.0))
                if abs(prev_amt) >= epsilon and abs(now_amt) < epsilon:
                    closed_at = get_clock().now_sec()
                    self._fsm._last_position_closed_ts[sym] = closed_at
                    self._fsm._last_any_position_closed_ts = closed_at

                    _pos_close_regime = self._fsm._open_regime_by_symbol.pop(sym, {
                    })

                    # Try to extract PnL from the matched position data
                    pos_pnl = 0.0
                    for pos in positions:
                        if pos.get("symbol") == sym:
                            pos_pnl = float(pos.get("realizedPnl") or 0.0)
                            break
                    # Fall back to cached fill PnL when portfolio payload has no realizedPnl
                    if pos_pnl == 0.0:
                        try:
                            pos_pnl = float(
                                self._fsm._last_realized_pnl_by_symbol.get(sym, 0.0))
                        except Exception:
                            pass
                    close_reason = self._resolve_position_close_reason(sym)
                    try:
                        self._fsm._open_strategy_by_symbol.pop(sym, None)
                    except Exception:
                        pass
                    try:
                        self._fsm._clear_bracket_owner(sym)
                    except Exception:
                        pass

                    LOG.info(
                        f"[POSITION_CLOSED] {sym}: position closed (was {prev_amt}, now {now_amt})"
                        f" | open_regime={_pos_close_regime.get('regime')} | realized_pnl={pos_pnl}"
                    )

                    # FIX-LIFECYCLE-01: Flush lifecycle record
                    if _trade_lifecycle is not None:
                        try:
                            rid_for_sym = ""
                            try:
                                rid_for_sym = str(
                                    self._fsm._last_lifecycle_rid_by_symbol.get(sym) or "")
                            except Exception:
                                rid_for_sym = ""
                            if not rid_for_sym:
                                rid_for_sym = f"position_close:{sym}:{int(closed_at * 1000)}"
                            close_price = None
                            try:
                                close_price = self._fsm._last_lifecycle_fill_price_by_symbol.get(
                                    sym)
                            except Exception:
                                close_price = None
                            _trade_lifecycle.on_close(
                                rid=rid_for_sym,
                                close_price=float(
                                    close_price) if close_price is not None else None,
                                close_reason=close_reason,
                            )
                        except Exception:
                            pass
                        finally:
                            try:
                                self._fsm._last_lifecycle_rid_by_symbol.pop(
                                    sym, None)
                                self._fsm._last_lifecycle_fill_price_by_symbol.pop(
                                    sym, None)
                            except Exception:
                                pass

                    if _get_order_logger is not None:
                        try:
                            # PHASE 3: Get accumulated fees before write (used in two keys)
                            _pos_fees = self._fsm._accumulated_fees_by_symbol.get(
                                sym, 0.0)
                            _trade_id = self._fsm._last_trade_id_by_symbol.get(
                                sym, "")
                            _entry_side = self._fsm._last_entry_side_by_symbol.get(
                                sym, "N/A")
                            _close_ts_ms = int(closed_at * 1000)
                            _entry_regime_epoch_ref = _pos_close_regime.get(
                                "regime_epoch_ref")
                            _get_order_logger().write({
                                "rid": str(rid_for_sym) if 'rid_for_sym' in locals() and rid_for_sym else f"position_close:{sym}:{int(closed_at * 1000)}",
                                "event_type": "POSITION_CLOSED",
                                # PHASE 1
                                "lifecycle_id": self._fsm._last_lifecycle_ikey_by_symbol.get(sym, ""),
                                "symbol": sym,
                                # PHASE 2: real entry side from cache; falls back to "N/A" if cache empty
                                "side": _entry_side,
                                # PHASE 2: exchange tradeId from last fill cached per symbol
                                "trade_id": _trade_id,
                                # PHASE 3: accumulated fees and net PnL for neocortex reward_complete
                                "fees": _pos_fees,
                                "realized_pnl_net": pos_pnl - _pos_fees,
                                "source_fsm": "ExecPosFSM",
                                "why": close_reason,
                                "close_reason": close_reason,
                                "metadata": {
                                    "close_price": float(close_price) if 'close_price' in locals() and close_price is not None else None,
                                    "realized_pnl": pos_pnl
                                }
                            })
                            if hasattr(self._fsm, "bus") and self._fsm.bus is not None:
                                self._fsm.bus.emit(
                                    "EVT:POSITION_CLOSED",
                                    payload={
                                        "event_type": "POSITION_CLOSED",
                                        "symbol": sym,
                                        "trade_id": _trade_id,
                                        "close_reason": close_reason,
                                        "close_ts_ms": _close_ts_ms,
                                        "realized_pnl_net": pos_pnl - _pos_fees,
                                        "fees": _pos_fees,
                                        "entry_regime_epoch_ref": _entry_regime_epoch_ref,
                                        "side": _entry_side,
                                        "lifecycle_id": self._fsm._last_lifecycle_ikey_by_symbol.get(sym, ""),
                                        "realized_pnl": pos_pnl,
                                    },
                                    why="position_closed_detected",
                                    rid=str(rid_for_sym) if 'rid_for_sym' in locals(
                                    ) and rid_for_sym else f"position_close:{sym}:{_close_ts_ms}",
                                )
                        except Exception as e:
                            LOG.error(
                                f"Failed to write/emit POSITION_CLOSED close truth: {e}")

                        # PHASE 1: Clean up lifecycle ikey cache after POSITION_CLOSED write.
                        # CRITICAL: this block must stay AFTER the write above, NOT inside the
                        # _trade_lifecycle finally block at lines ~238-243 which runs before this write.
                        # PHASE 2: Also clean up trade_id and entry side caches.
                        # PHASE 3: Also clean up accumulated fees cache.
                        try:
                            self._fsm._last_lifecycle_ikey_by_symbol.pop(
                                sym, None)
                            self._fsm._last_trade_id_by_symbol.pop(sym, None)
                            self._fsm._last_entry_side_by_symbol.pop(sym, None)
                            self._fsm._accumulated_fees_by_symbol.pop(
                                sym, None)
                        except Exception:
                            pass

                    self._fsm._apply_authoritative_local_close_reset(
                        sym,
                        reason="position_closed_detected",
                        source="portfolio_update",
                        payload={
                            "close_reason": close_reason,
                            "prev_amt": prev_amt,
                            "now_amt": now_amt,
                        },
                    )

                    # Trigger orphan cleanup
                    if hasattr(self._fsm, "order_guardian") and self._fsm.order_guardian:
                        loop = self._fsm._get_async_loop()
                        if loop:
                            self._fsm._submit_async(
                                self._fsm.order_guardian.reconcile_symbol(
                                    sym, "portfolio_update"),
                                loop,
                            )

            self._fsm._prev_position_amts = current_amts
        except Exception as e:
            LOG.debug(f"Error checking position closures: {e}")

        # Clean up stale reservations
        if callable(trace_stage):
            trace_stage(event, "expire_stale_entered")
        try:
            expired = self._fsm.exposure_guard.expire_stale()
        except Exception as exc:
            if callable(trace_stage):
                trace_stage(event, "expire_stale_failed", error=exc)
            raise

        # Release post-fill holds
        released_postfill = list(
            self._fsm.exposure_guard.state.postfill_reservations.keys()
        )
        for key in released_postfill:
            self._fsm.exposure_guard.state.postfill_reservations.pop(key, None)

        if released_postfill:
            LOG.debug(
                f"RELEASED_POSTFILL_HOLDS: {len(released_postfill)} keys")

        if expired:
            if hasattr(self._fsm, "metrics_collector") and self._fsm.metrics_collector:
                for _ in expired:
                    if _ in self._fsm.exposure_guard.state.postfill_reservations:
                        self._fsm.metrics_collector.record_postfill_expired()

            expired_msg = Message(
                op="EVT",
                verb="PENDING_EXPOSURE_EXPIRED",
                src="execution_position",
                dst="monitoring",
                rid="exposure_cleanup",
                pld={"expired_keys": expired, "why": "ttl_expired"},
                why="exposure_cleanup",
            )
            loop = self._fsm._get_async_loop()
            if loop:
                self._fsm._submit_async(
                    emit_compat(
                        self._fsm.fsm,
                        expired_msg,
                        logger=aget(self._fsm, "logger", None),
                    ),
                    loop,
                )

    def on_order_ack(self, event: "Message") -> None:
        """Handle EVT:ORDER_ACK events from adapter."""
        payload = event.pld or {}
        order_id = payload.get("orderId")
        symbol = payload.get("symbol")
        rid = payload.get("rid") or event.rid

        if not order_id or not symbol:
            LOG.warning(
                f"[ACK] Missing orderId or symbol in ACK event: {payload}")
            return

        event_key = f"ack_{order_id}_{symbol}"
        if not self._fsm._mark_processed_event(event_key):
            LOG.debug(
                f"[ACK] Skipping duplicate ACK for {symbol} order {order_id}")
            return

        LOG.debug(
            f"[ACK] Processing ACK for {symbol} order {order_id} (rid={rid})")

        if hasattr(self._fsm, "exposure_guard"):
            LOG.debug(f"[ACK] Order {order_id} acknowledged for {symbol}")

        try:
            if hasattr(self._fsm, "watchdog") and self._fsm.watchdog is not None:
                self._fsm.watchdog.on_order_ack(order_id)
        except Exception as e:
            LOG.warning(f"[ACK] Failed to notify watchdog for {order_id}: {e}")

    def on_trade_executed(self, event: "Message") -> None:
        """Mirror canonical fill truth into lifecycle telemetry on the actual hot path."""
        payload = event.pld or {}
        symbol = payload.get("symbol")
        rid = payload.get("rid") or event.rid or payload.get("orderId")
        if not rid:
            return

        try:
            if symbol:
                self._fsm._last_lifecycle_rid_by_symbol[symbol] = str(rid)
                if payload.get("price") is not None:
                    self._fsm._last_lifecycle_fill_price_by_symbol[symbol] = float(
                        payload.get("price"))
        except Exception:
            pass

        if _trade_lifecycle is not None:
            try:
                _trade_lifecycle.on_fill(
                    rid=str(rid),
                    fill_price=float(payload.get("price", 0)
                                     ) if payload.get("price") else None,
                    fill_qty=float(payload.get("quantity", 0)) if payload.get(
                        "quantity") else None,
                    fees=float(payload.get("fees", payload.get("commission", 0))) if (
                        payload.get("fees") or payload.get("commission")
                    ) else None,
                )
            except Exception:
                pass

    def on_order_fill(self, event: "Message") -> None:
        """Handle adapter or canonical internal fill bookkeeping."""
        from vfoundation.core.fsm_emit_compat import Message, emit_compat

        payload = event.pld or {}
        skip_trade_lifecycle_log = bool(
            payload.get("_skip_trade_lifecycle_on_fill"))
        order_id = payload.get("orderId")
        symbol = payload.get("symbol")
        filled_qty = payload.get("quantity")
        rid = payload.get("rid") or event.rid
        client_order_id = payload.get(
            "clientOrderId") or payload.get("client_order_id")

        # PREFIX-CANON-01: Classify order role from canonical prefix registry
        _coid = str(payload.get("clientOrderId") or "")
        order_kind = classify_client_order_id(_coid)
        if order_kind == "UNKNOWN":
            order_kind = payload.get("close_reason", "UNKNOWN")

        if not order_id or not symbol or filled_qty is None:
            LOG.warning(
                f"[FILL] Missing orderId, symbol or quantity in FILL event: {payload}")
            return

        # DEF-E17: Do NOT pop pending_entry_meta while status is PARTIALLY_FILLED.
        # Popping on partial fill discards the pending metadata (idempotent_key, rid, etc.)
        # needed to process subsequent fill events for the same order.
        # Clear only on terminal statuses: FILLED, CANCELLED, REJECTED, EXPIRED.
        _early_fill_status = str(payload.get("status") or "").upper()
        if _early_fill_status != "PARTIALLY_FILLED":
            self._fsm._pending_entry_meta.pop(str(order_id), None)

        # FILL-PIPELINE-FIX-AUDIT: include trade_id in dedup key so multiple
        # partial fills (each with unique Binance trade_id "t") are not suppressed.
        # DEF-E18: If tradeId is missing, use cumulative_qty+update_time as fallback
        # so distinct partial fills are NOT collapsed into a single dedup key.
        _trade_id = str(payload.get("tradeId")
                        or payload.get("trade_id") or "")
        if _trade_id:
            event_key = f"fill_{order_id}_{_trade_id}_{symbol}"
        else:
            # DEF-E18 fallback: derive dedup key from cumulative qty + update time
            # so repeated delivery of the same partial fill is deduplicated, but
            # distinct partial fills (different cumQty) produce different keys.
            _cum_qty = str(payload.get("cumQty") or payload.get(
                "executedQty") or payload.get("quantity") or "")
            _update_time = str(payload.get("updateTime")
                               or payload.get("transactTime") or "")
            event_key = f"fill_{order_id}_{symbol}_{_cum_qty}_{_update_time}"
        if not self._fsm._mark_processed_event(event_key):
            LOG.debug(
                f"[FILL] Skipping duplicate FILL for {symbol} order {order_id}")
            return

        LOG.debug(
            f"[FILL] Processing FILL for {symbol} order {order_id}, qty={filled_qty} (rid={rid})")

        # FIX-LIFECYCLE-01: Cache rid/last fill price
        try:
            if symbol:
                self._fsm._last_lifecycle_rid_by_symbol[symbol] = str(
                    rid) if rid else str(order_id)
                if payload.get("price") is not None:
                    self._fsm._last_lifecycle_fill_price_by_symbol[symbol] = float(
                        payload.get("price"))
        except Exception:
            pass

        if _trade_lifecycle is not None and not skip_trade_lifecycle_log:
            try:
                _trade_lifecycle.on_fill(
                    rid=str(rid) if rid else str(order_id),
                    fill_price=float(payload.get("price", 0)
                                     ) if payload.get("price") else None,
                    fill_qty=float(filled_qty) if filled_qty else None,
                    fees=float(payload.get("commission", 0)) if payload.get(
                        "commission") else None,
                )
            except Exception:
                pass

        if _get_order_logger is not None:
            try:
                # Find order_index safely
                oi = getattr(self._fsm, "order_index", None)
                if not oi and hasattr(self._fsm, "fsm"):
                    oi = getattr(self._fsm.fsm, "order_index", None)

                res_id = None
                # PHASE 1: Early lifecycle_id lookup — must run before the ORDER_FILLED write
                # because TASK40 (which also populates the cache) runs after the write.
                _lifecycle_id_for_write = self._fsm._last_lifecycle_ikey_by_symbol.get(
                    symbol, "")
                if oi and not _lifecycle_id_for_write:
                    try:
                        _lc_ref = (
                            oi.get(exchangeOrderId=str(order_id)) or
                            (oi.get(clientOrderId=str(client_order_id)) if client_order_id else None) or
                            (oi.get(rid=str(rid)) if rid else None)
                        )
                        if _lc_ref and _lc_ref.idempotent_key:
                            _lifecycle_id_for_write = str(
                                _lc_ref.idempotent_key)
                            if symbol:
                                self._fsm._last_lifecycle_ikey_by_symbol[symbol] = _lifecycle_id_for_write
                    except Exception:
                        pass
                if oi:
                    # Reservation ID is intentionally unavailable on this path.
                    # An older get_intent_for_order() probe no longer exists on
                    # OrderIndex, so the logger keeps an explicit None placeholder
                    # until a later comment-only cleanup confirms the field is
                    # still expected in ORDER_FILLED writes.
                    res_id = None

                _get_order_logger().write({
                    "rid": str(payload.get("clientOrderId") or payload.get("orderId") or "unknown_fill"),
                    "event_type": "ORDER_FILLED",
                    "lifecycle_id": _lifecycle_id_for_write,  # PHASE 1
                    "symbol": symbol,
                    "side": payload.get("side", ""),
                    "quantity": float(filled_qty) if filled_qty else None,
                    "price": float(payload.get("price", 0)) if payload.get("price") else None,
                    "source_fsm": "ExecPosFSM",
                    "reservation_id": res_id,
                    "order_kind": order_kind,
                    "close_reason": payload.get("close_reason"),
                    "metadata": {
                        "fill_trade_id": str(payload.get("tradeId", "")),
                        "realized_pnl": float(payload.get("realizedPnl") or 0.0),
                        "commission": float(payload.get("commission", 0.0)),
                        "commissionAsset": str(payload.get("commissionAsset", "")),
                    }
                })
            except Exception as e:
                LOG.error(f"Failed to write ORDER_FILLED to order_logger: {e}")

        # Cache realized PnL and close_reason per symbol for POSITION_CLOSED logging
        if symbol and order_kind in ("SL", "TP", "TP1", "TP2", "BHSL", "BHTP", "CLOSE", "MARKET_FILLED"):
            try:
                self._fsm._last_realized_pnl_by_symbol[symbol] = float(
                    payload.get("realizedPnl") or 0.0)
                self._fsm._last_close_reason_by_symbol[symbol] = order_kind
            except Exception:
                pass

        # FILL-PIPELINE-FIX-AUDIT: Only remove from watchdog tracking on final FILLED.
        # PARTIALLY_FILLED means more fills are expected — keep the order tracked.
        _fill_status = str(payload.get("status") or "").upper()
        try:
            if hasattr(self._fsm, "watchdog") and self._fsm.watchdog is not None:
                if _fill_status != "PARTIALLY_FILLED":
                    self._fsm.watchdog.on_order_fill(order_id)
                else:
                    # Extend fill deadline for partially filled orders
                    if order_id in self._fsm.watchdog.acked_orders:
                        self._fsm.watchdog.acked_orders[order_id].deadline_ms = (
                            get_clock().now_ms() + self._fsm.watchdog.fill_ttl_ms)
                    LOG.info(
                        "PARTIAL_FILL_WATCHDOG_RETAINED: %s still tracked", order_id)
        except Exception as e:
            LOG.warning(
                f"[FILL] Failed to notify watchdog for {order_id}: {e}")

        # TASK40: Mark entry order terminal in OrderIndex
        # FILL-PIPELINE-FIX-AUDIT: only for final FILLED, not PARTIALLY_FILLED
        if _fill_status != "PARTIALLY_FILLED":
            try:
                if hasattr(self._fsm.fsm, "order_index") and self._fsm.fsm.order_index:
                    ref = None
                    ref = self._fsm.fsm.order_index.get(
                        exchangeOrderId=str(order_id))
                    if ref is None and client_order_id:
                        ref = self._fsm.fsm.order_index.get(
                            clientOrderId=str(client_order_id))
                    if ref is None and rid:
                        ref = self._fsm.fsm.order_index.get(rid=str(rid))
                    if ref is not None:
                        self._fsm.fsm.order_index.mark_terminal(ref)
                        # PHASE 1: Cache lifecycle_id for ORDER_FILLED and POSITION_CLOSED correlation
                        if ref.idempotent_key and symbol:
                            try:
                                self._fsm._last_lifecycle_ikey_by_symbol[symbol] = str(
                                    ref.idempotent_key)
                            except Exception:
                                pass
            except Exception:
                pass

        # PHASE 2: Cache exchange tradeId (all fills) and entry side (ENTRY fills only).
        # tradeId always wins with the most-recent fill's value.
        # Entry side is only updated for ENTRY fills — SL/TP fills must not overwrite it.
        if symbol:
            try:
                _trade_id_raw = str(payload.get("tradeId") or "")
                if _trade_id_raw:
                    self._fsm._last_trade_id_by_symbol[symbol] = _trade_id_raw
            except Exception:
                pass
            if order_kind == "ENTRY":
                try:
                    _oi_p2 = (
                        getattr(self._fsm, "order_index", None) or
                        getattr(getattr(self._fsm, "fsm", None),
                                "order_index", None)
                    )
                    if _oi_p2:
                        _p2_ref = (
                            _oi_p2.get(exchangeOrderId=str(order_id)) or
                            (_oi_p2.get(clientOrderId=str(client_order_id)) if client_order_id else None) or
                            (_oi_p2.get(rid=str(rid)) if rid else None)
                        )
                        if _p2_ref and getattr(_p2_ref, "side", None):
                            self._fsm._last_entry_side_by_symbol[symbol] = str(
                                _p2_ref.side)
                except Exception:
                    pass

        # PHASE 3: Accumulate commission fees across all fills for this symbol lifecycle.
        # Runs for ALL fills (ENTRY, SL, TP, CLOSE). Zero commission is accumulated as 0.0
        # to ensure the _accumulated_fees_by_symbol key is present even for fee-free fills.
        # This enables fees to be non-None in POSITION_CLOSED → reward_complete=True in neocortex.
        if symbol:
            try:
                _fee = float(payload.get("commission") or 0.0)
                _cur_fees = self._fsm._accumulated_fees_by_symbol.get(
                    symbol, 0.0)
                self._fsm._accumulated_fees_by_symbol[symbol] = _cur_fees + _fee
            except Exception:
                pass

        # PHASE A2 FIX: Inject cached intent data into ManageFlowFSM
        if rid in self._fsm._pending_intent_data:
            intent_data = self._fsm._pending_intent_data[rid]
            manage_flow = self._fsm.manage_flows.get(symbol)
            if manage_flow:
                LOG.info(
                    f"INJECTING_INTENT_DATA for {symbol} (rid={rid}): {intent_data}")
                sl_price = intent_data.get("stop_price")
                tp_price = intent_data.get("target_price")
                sl_is_real = sl_price is not None and str(
                    sl_price).strip().lower() != "none"
                tp_is_real = tp_price is not None and str(
                    tp_price).strip().lower() != "none"
                if sl_is_real:
                    manage_flow.set_intent_prices(
                        sl_price=sl_price, tp_price=tp_price if tp_is_real else None)
                    LOG.info(
                        f"INTENT_PRICES_INJECTED for {symbol}: SL={sl_price}, TP={tp_price if tp_is_real else 'None'}")
                else:
                    LOG.debug(
                        f"SKIP_INTENT_INJECTION for {symbol}: sl_price is None/invalid")
                self._fsm._pending_intent_data.pop(rid, None)
            else:
                LOG.warning(
                    f"Could not inject intent data: ManageFlow not found for {symbol}")

        # Create post-fill hold in exposure guard
        if hasattr(self._fsm, "exposure_guard"):
            postfill_key = f"postfill_{symbol}_{order_id}"
            fill_price = payload.get("price")
            hold_notional = None
            notional_source = ""
            try:
                hold_notional = abs(Decimal(str(filled_qty))) * \
                    abs(Decimal(str(fill_price)))
                notional_source = "fill_payload"
            except (InvalidOperation, TypeError, ValueError):
                pending_candidates = [
                    payload.get("idempotent_key"),
                    client_order_id,
                    rid,
                ]
                for candidate in pending_candidates:
                    if candidate in (None, ""):
                        continue
                    pending_item = self._fsm.exposure_guard.state.pending_exposure.get(
                        str(candidate))
                    if not isinstance(pending_item, dict):
                        continue
                    try:
                        hold_notional = abs(
                            Decimal(str(pending_item.get("notional"))))
                        notional_source = f"pending_exposure:{candidate}"
                        break
                    except (InvalidOperation, TypeError, ValueError):
                        continue
                if hold_notional is None:
                    hold_notional = Decimal("0")
                    notional_source = "compat_zero_missing_fill_notional"
                    LOG.warning(
                        "[FILL] No authoritative fill notional for postfill hold %s; "
                        "storing zero-notional canonical hold for compatibility",
                        postfill_key,
                    )

            hold = self._fsm.exposure_guard.record_postfill_hold(
                key=postfill_key,
                notional_usd=hold_notional,
                symbol=str(symbol),
                side=str(payload.get("side") or "SELL"),
                rid=str(rid) if rid not in (None, "") else None,
                qty=filled_qty,
                ts_ms=payload.get("ts_ms") or payload.get("ts"),
                notional_source=notional_source,
            )
            LOG.debug(
                "[FILL] Created postfill hold for %s exp_ts=%s source=%s",
                postfill_key,
                hold.get("exp_ts"),
                hold.get("notional_source"),
            )

        # LIMIT-ENTRY-DEFERRED-BRACKETS: keep pending truth until confirmed
        # protective placement succeeds.
        bracket_data = self._fsm._pending_brackets.get(order_id)
        if isinstance(bracket_data, dict):
            if _fill_status == "PARTIALLY_FILLED":
                LOG.info(
                    f"📌 [LIMIT-DEFERRED] Partial fill received for {symbol} entry {order_id}, "
                    f"keeping deferred TP/SL pending until terminal fill"
                )
            else:
                LOG.info(
                    f"📌 [LIMIT-DEFERRED] Fill received for {symbol} entry {order_id}, "
                    f"attempting deferred TP/SL placement"
                )
                loop = self._fsm._get_async_loop()
                if loop:
                    self._fsm._submit_async(
                        self._fsm._bracket_mgr.place_deferred_brackets(
                            order_id, dict(bracket_data)),
                        loop
                    )
                else:
                    LOG.warning(
                        "[LIMIT-DEFERRED] No async loop for %s entry %s; pending brackets kept",
                        symbol,
                        order_id,
                    )

        # Best-effort cleanup of orphaned brackets
        loop = self._fsm._get_async_loop()
        if loop:
            lifecycle_cfg = self._fsm.config.domains.execution_position.order_lifecycle

            async def delayed_cleanup():
                await get_clock().sleep_ms(lifecycle_cfg.fill_settlement_delay_ms)
                await self._fsm.order_guardian.cleanup_orphans()
            self._fsm._submit_async(delayed_cleanup(), loop)

        # EVT:EXPOSURE_SUMMARY_UPDATED after fill
        try:
            exposure_summary = self._fsm.exposure_guard.get_exposure_summary()
            exposure_msg = Message(
                op="EVT",
                verb="EXPOSURE_SUMMARY_UPDATED",
                src="execution_position",
                dst="decision_making",
                rid=rid or f"fill_{order_id}",
                pld={
                    "exposure_summary": exposure_summary,
                    "fill_order_id": order_id,
                    "fill_symbol": symbol,
                    "fill_quantity": filled_qty,
                    "timestamp_ms": get_clock().now_ms()
                },
                why="exposure_summary_updated_after_fill",
            )
            loop = self._fsm._get_async_loop()
            if loop:
                self._fsm._submit_async(
                    emit_compat(self._fsm.fsm, exposure_msg, logger=LOG), loop
                )
        except Exception as e:
            LOG.debug(
                f"Failed to emit exposure summary update after fill: {e}")

    # ---- GATE: SYMBOL_TIDY entry gating ----

    def on_symbol_tidy_event(self, payload: Dict[str, Any]) -> None:
        try:
            symbol = payload.get("symbol") if isinstance(
                payload, dict) else None
            if symbol:
                self._fsm._symbol_last_tidy_ts[symbol] = get_clock().now_sec()
                LOG.info(f"[GATE] tidy_event: symbol={symbol}")
        except Exception:
            pass

    def entry_tidy_gate_allow(self, symbol: str) -> bool:
        """Return True if new ENTRY is allowed under SYMBOL_TIDY gate."""
        try:
            allow_gate = bool(
                aget(self._fsm.config.execution,
                     "allow_trade_with_guardian_tidy_only", False)
            ) if self._fsm.config.execution else False
        except Exception:
            allow_gate = False

        if not allow_gate:
            return True

        ttl_ms = int(dget(self._fsm._guardian_cfg, "cleanup_ttl_ms", 6000))
        cooldown_ms = int(dget(self._fsm._guardian_cfg,
                          "symbol_cooldown_ms", 4000))

        now = get_clock().now_sec()
        last_tidy = self._fsm._symbol_last_tidy_ts[symbol] if symbol in self._fsm._symbol_last_tidy_ts else 0.0
        fresh = (now - last_tidy) * 1000.0 <= ttl_ms
        last_block = self._fsm._last_entry_block_ts[symbol] if symbol in self._fsm._last_entry_block_ts else 0.0
        cooldown_ok = (now - last_block) * 1000.0 >= cooldown_ms

        if fresh or (last_block > 0 and cooldown_ok):
            self._fsm._gate_metrics["gate_entry_allowed_tidy"] += 1
            LOG.info(
                f"[GATE] entry_allowed: tidy_recent={fresh} cooldown_ok={cooldown_ok} last_block={last_block} symbol={symbol}")
            return True

        self._fsm._last_entry_block_ts[symbol] = now
        self._fsm._gate_metrics["gate_entry_blocked_tidy"] += 1
        age_ms = int((now - last_tidy) * 1000.0)
        LOG.info(
            f"[GATE] entry_blocked: no_tidy_recent symbol={symbol} age_ms={age_ms} ttl_ms={ttl_ms} cooldown_ms={cooldown_ms}")
        return False
