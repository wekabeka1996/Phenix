"""
Event handlers for execution_position domain.

Extracted from ExecPosFSM (Phase 14A decomposition).
Handles regime detection, portfolio state updates, order ACK/FILL events,
and tidy gate logic.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict

from apps.reference.core.time import get_clock
from apps.reference.utils.accessors import aget, dget

if TYPE_CHECKING:
    from vfoundation.core.fsm_emit_compat import Message

LOG = logging.getLogger(__name__)

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

    def on_regime_detected(self, event: "Message") -> None:
        """
        EP-01: Handle EVT:REGIME_DETECTED to update ExposureGuard risk limits.
        EP-01.3-INT: Cancel pending entry orders on regime change.
        """
        from apps.reference.core.types.regime_types import map_regime_to_bucket

        pld = event.pld or {}
        regime_str = pld.get("regime")
        symbol = pld.get("symbol")
        if not regime_str:
            LOG.warning("EP-01: EVT:REGIME_DETECTED missing 'regime' field, skipping")
            return

        bucket = map_regime_to_bucket(regime_str)
        self._fsm.exposure_guard.on_regime_changed(bucket)

        LOG.info(
            f"EP-01: Regime adaptation triggered: label={regime_str} → bucket={bucket.value}, "
            f"new_ratio={float(self._fsm.exposure_guard.max_directional_ratio):.2f}"
        )

        # EP-01.3-INT: Cancel pending entry orders on regime change
        try:
            pe_ttl_cfg = self._fsm.config.domains.execution_position.pending_entry_ttl
            if pe_ttl_cfg.enabled and pe_ttl_cfg.cancel_on_regime_change and symbol:
                cancel_mode = getattr(pe_ttl_cfg, 'regime_change_cancel_mode', 'immediate')
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
        from vfoundation.core.fsm_emit_compat import Message, emit_compat

        self._fsm._latest_portfolio_state = event.pld or {}

        # EXP-LEVERAGE-001: Update exposure guard with latest portfolio state
        self._fsm.exposure_guard.on_portfolio(self._fsm._latest_portfolio_state)

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
                    self._fsm.fsm.emit(
                        "EVT:EXPOSURE_SUMMARY_UPDATED",
                        {
                            "exposure_summary": exposure_summary,
                            "portfolio_state": self._fsm._latest_portfolio_state,
                            "timestamp_ms": get_clock().now_ms()
                        },
                        "exposure_summary_updated_after_portfolio_change"
                    )
                except TypeError:
                    await emit_compat(self._fsm.fsm, exposure_msg, logger=LOG)
                except Exception as ex:
                    LOG.error(f"Failed to emit exposure summary: {ex}")

            loop = self._fsm._get_async_loop()
            if loop:
                self._fsm._submit_async(_do_emit_exposure(), loop)
        except Exception as e:
            LOG.debug(f"Failed to prepare exposure summary update: {e}")

        # Detect position closures
        try:
            positions = self._fsm._latest_portfolio_state.get("positions") or []
            current_amts: Dict[str, float] = {}
            for pos in positions:
                sym = pos.get("symbol")
                if not sym:
                    continue
                try:
                    current_amts[sym] = float(pos.get("positionAmt") or 0.0)
                except Exception:
                    current_amts[sym] = 0.0

            epsilon = 1e-10
            all_syms = set(self._fsm._prev_position_amts.keys()) | set(current_amts.keys())
            for sym in all_syms:
                prev_amt = float(self._fsm._prev_position_amts.get(sym, 0.0))
                now_amt = float(current_amts.get(sym, 0.0))
                if abs(prev_amt) >= epsilon and abs(now_amt) < epsilon:
                    closed_at = get_clock().now_sec()
                    self._fsm._last_position_closed_ts[sym] = closed_at
                    self._fsm._last_any_position_closed_ts = closed_at

                    _pos_close_regime = self._fsm._open_regime_by_symbol.pop(sym, {})
                    
                    # Try to extract PnL from the matched position data
                    pos_pnl = 0.0
                    for pos in positions:
                        if pos.get("symbol") == sym:
                            pos_pnl = float(pos.get("realizedPnl") or 0.0)
                            break
                    # Fall back to cached fill PnL when portfolio payload has no realizedPnl
                    if pos_pnl == 0.0:
                        try:
                            pos_pnl = float(self._fsm._last_realized_pnl_by_symbol.get(sym, 0.0))
                        except Exception:
                            pass
                    close_reason = "POSITION_CLOSED_DETECTED"
                    try:
                        close_reason = self._fsm._last_close_reason_by_symbol.pop(sym, "POSITION_CLOSED_DETECTED")
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
                                rid_for_sym = str(self._fsm._last_lifecycle_rid_by_symbol.get(sym) or "")
                            except Exception:
                                rid_for_sym = ""
                            if not rid_for_sym:
                                rid_for_sym = f"position_close:{sym}:{int(closed_at * 1000)}"
                            close_price = None
                            try:
                                close_price = self._fsm._last_lifecycle_fill_price_by_symbol.get(sym)
                            except Exception:
                                close_price = None
                            _trade_lifecycle.on_close(
                                rid=rid_for_sym,
                                close_price=float(close_price) if close_price is not None else None,
                                close_reason="POSITION_CLOSED_DETECTED",
                            )
                        except Exception:
                            pass
                        finally:
                            try:
                                self._fsm._last_lifecycle_rid_by_symbol.pop(sym, None)
                                self._fsm._last_lifecycle_fill_price_by_symbol.pop(sym, None)
                            except Exception:
                                pass

                    if _get_order_logger is not None:
                        try:
                            _get_order_logger().write({
                                "rid": str(rid_for_sym) if 'rid_for_sym' in locals() and rid_for_sym else f"position_close:{sym}:{int(closed_at * 1000)}",
                                "event_type": "POSITION_CLOSED",
                                "symbol": sym,
                                "side": "N/A",  # Not immediately available in this context without tracking
                                "source_fsm": "ExecPosFSM",
                                "why": close_reason,
                                "close_reason": close_reason,
                                "metadata": {
                                    "close_price": float(close_price) if 'close_price' in locals() and close_price is not None else None,
                                    "realized_pnl": pos_pnl
                                }
                            })
                        except Exception as e:
                            LOG.error(f"Failed to write POSITION_CLOSED to order_logger: {e}")

                    # Trigger orphan cleanup
                    if hasattr(self._fsm, "order_guardian") and self._fsm.order_guardian:
                        loop = self._fsm._get_async_loop()
                        if loop:
                            self._fsm._submit_async(
                                self._fsm.order_guardian.reconcile_symbol(sym, "portfolio_update"),
                                loop,
                            )

            self._fsm._prev_position_amts = current_amts
        except Exception as e:
            LOG.debug(f"Error checking position closures: {e}")

        # Clean up stale reservations
        expired = self._fsm.exposure_guard.expire_stale()

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
            LOG.warning(f"[ACK] Missing orderId or symbol in ACK event: {payload}")
            return

        event_key = f"ack_{order_id}_{symbol}"
        if not self._fsm._mark_processed_event(event_key):
            LOG.debug(f"[ACK] Skipping duplicate ACK for {symbol} order {order_id}")
            return

        LOG.debug(f"[ACK] Processing ACK for {symbol} order {order_id} (rid={rid})")

        if hasattr(self._fsm, "exposure_guard"):
            LOG.debug(f"[ACK] Order {order_id} acknowledged for {symbol}")

        try:
            if hasattr(self._fsm, "watchdog") and self._fsm.watchdog is not None:
                self._fsm.watchdog.on_order_ack(order_id)
        except Exception as e:
            LOG.warning(f"[ACK] Failed to notify watchdog for {order_id}: {e}")

    def on_order_fill(self, event: "Message") -> None:
        """Handle EVT:ORDER_FILL events from adapter."""
        from vfoundation.core.fsm_emit_compat import Message, emit_compat
        from apps.reference.domains.execution_position.pending_brackets_wal import write_pending_brackets_cleared

        payload = event.pld or {}
        order_id = payload.get("orderId")
        symbol = payload.get("symbol")
        filled_qty = payload.get("quantity")
        rid = payload.get("rid") or event.rid
        client_order_id = payload.get("clientOrderId") or payload.get("client_order_id")

        # Infer order_kind from clientOrderId prefix
        _coid = str(payload.get("clientOrderId") or "").upper()
        if _coid.startswith("ENTRY-"):
            order_kind = "ENTRY"
        elif _coid.startswith("SL-"):
            order_kind = "SL"
        elif _coid.startswith("TP-"):
            order_kind = "TP"
        elif _coid.startswith("CLOSE-"):
            order_kind = "CLOSE"
        else:
            order_kind = payload.get("close_reason", "UNKNOWN")

        if not order_id or not symbol or filled_qty is None:
            LOG.warning(f"[FILL] Missing orderId, symbol or quantity in FILL event: {payload}")
            return

        event_key = f"fill_{order_id}_{symbol}"
        if not self._fsm._mark_processed_event(event_key):
            LOG.debug(f"[FILL] Skipping duplicate FILL for {symbol} order {order_id}")
            return

        LOG.debug(f"[FILL] Processing FILL for {symbol} order {order_id}, qty={filled_qty} (rid={rid})")

        # FIX-LIFECYCLE-01: Cache rid/last fill price
        try:
            if symbol:
                self._fsm._last_lifecycle_rid_by_symbol[symbol] = str(rid) if rid else str(order_id)
                if payload.get("price") is not None:
                    self._fsm._last_lifecycle_fill_price_by_symbol[symbol] = float(payload.get("price"))
        except Exception:
            pass

        if _trade_lifecycle is not None:
            try:
                _trade_lifecycle.on_fill(
                    rid=str(rid) if rid else str(order_id),
                    fill_price=float(payload.get("price", 0)) if payload.get("price") else None,
                    fill_qty=float(filled_qty) if filled_qty else None,
                    fees=float(payload.get("commission", 0)) if payload.get("commission") else None,
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
                if oi:
                    intent = oi.get_intent_for_order(str(payload.get("clientOrderId") or payload.get("orderId")))
                    if intent:
                        res_id = getattr(intent, "reservation_id", None)

                _get_order_logger().write({
                    "rid": str(payload.get("clientOrderId") or payload.get("orderId") or "unknown_fill"),
                    "event_type": "ORDER_FILLED",
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
        if symbol and order_kind in ("SL", "TP", "CLOSE", "MARKET_FILLED"):
            try:
                self._fsm._last_realized_pnl_by_symbol[symbol] = float(payload.get("realizedPnl") or 0.0)
                self._fsm._last_close_reason_by_symbol[symbol] = order_kind
            except Exception:
                pass

        try:
            if hasattr(self._fsm, "watchdog") and self._fsm.watchdog is not None:
                self._fsm.watchdog.on_order_fill(order_id)
        except Exception as e:
            LOG.warning(f"[FILL] Failed to notify watchdog for {order_id}: {e}")

        # TASK40: Mark entry order terminal in OrderIndex
        try:
            if hasattr(self._fsm.fsm, "order_index") and self._fsm.fsm.order_index:
                ref = None
                ref = self._fsm.fsm.order_index.get(exchangeOrderId=str(order_id))
                if ref is None and client_order_id:
                    ref = self._fsm.fsm.order_index.get(clientOrderId=str(client_order_id))
                if ref is None and rid:
                    ref = self._fsm.fsm.order_index.get(rid=str(rid))
                if ref is not None:
                    self._fsm.fsm.order_index.mark_terminal(ref)
        except Exception:
            pass

        # PHASE A2 FIX: Inject cached intent data into ManageFlowFSM
        if rid in self._fsm._pending_intent_data:
            intent_data = self._fsm._pending_intent_data[rid]
            manage_flow = self._fsm.manage_flows.get(symbol)
            if manage_flow:
                LOG.info(f"INJECTING_INTENT_DATA for {symbol} (rid={rid}): {intent_data}")
                sl_price = intent_data.get("stop_price")
                tp_price = intent_data.get("target_price")
                sl_is_real = sl_price is not None and str(sl_price).strip().lower() != "none"
                tp_is_real = tp_price is not None and str(tp_price).strip().lower() != "none"
                if sl_is_real:
                    manage_flow.set_intent_prices(sl_price=sl_price, tp_price=tp_price if tp_is_real else None)
                    LOG.info(f"INTENT_PRICES_INJECTED for {symbol}: SL={sl_price}, TP={tp_price if tp_is_real else 'None'}")
                else:
                    LOG.debug(f"SKIP_INTENT_INJECTION for {symbol}: sl_price is None/invalid")
                self._fsm._pending_intent_data.pop(rid, None)
            else:
                LOG.warning(f"Could not inject intent data: ManageFlow not found for {symbol}")

        # Create post-fill hold in exposure guard
        if hasattr(self._fsm, "exposure_guard"):
            postfill_key = f"postfill_{symbol}_{order_id}"
            self._fsm.exposure_guard.state.postfill_reservations[postfill_key] = {
                "symbol": symbol,
                "qty": filled_qty,
                "ts_ms": int(__import__('time').time() * 1000),
                "rid": rid,
            }
            LOG.debug(f"[FILL] Created postfill hold for {postfill_key}")

        # LIMIT-ENTRY-DEFERRED-BRACKETS: Place brackets on fill
        if order_id in self._fsm._pending_brackets:
            bracket_data = self._fsm._pending_brackets.pop(order_id)
            try:
                write_pending_brackets_cleared(
                    entry_order_id=order_id,
                    reason="filled",
                    symbol=bracket_data.get("symbol", ""),
                )
            except Exception as e:
                LOG.warning(f"Failed to clear pending brackets from WAL: {e}")
            LOG.info(
                f"📌 [LIMIT-DEFERRED] Fill received for {symbol} entry {order_id}, "
                f"placing deferred TP/SL brackets"
            )
            loop = self._fsm._get_async_loop()
            if loop:
                self._fsm._submit_async(
                    self._fsm._bracket_mgr.place_deferred_brackets(order_id, bracket_data),
                    loop
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
            LOG.debug(f"Failed to emit exposure summary update after fill: {e}")

    # ---- GATE: SYMBOL_TIDY entry gating ----

    def on_symbol_tidy_event(self, payload: Dict[str, Any]) -> None:
        try:
            symbol = payload.get("symbol") if isinstance(payload, dict) else None
            if symbol:
                self._fsm._symbol_last_tidy_ts[symbol] = get_clock().now_sec()
                LOG.info(f"[GATE] tidy_event: symbol={symbol}")
        except Exception:
            pass

    def entry_tidy_gate_allow(self, symbol: str) -> bool:
        """Return True if new ENTRY is allowed under SYMBOL_TIDY gate."""
        try:
            allow_gate = bool(
                aget(self._fsm.config.execution, "allow_trade_with_guardian_tidy_only", False)
            ) if self._fsm.config.execution else False
        except Exception:
            allow_gate = False

        if not allow_gate:
            return True

        ttl_ms = int(dget(self._fsm._guardian_cfg, "cleanup_ttl_ms", 6000))
        cooldown_ms = int(dget(self._fsm._guardian_cfg, "symbol_cooldown_ms", 4000))

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
