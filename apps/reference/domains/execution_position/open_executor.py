"""
Open order execution for execution_position domain.

Extracted from ExecPosFSM._execute_decision (Phase 14A decomposition).
Handles the DEC:OPEN verb: supersede checks, qty normalization,
SL/TP resolution, order policy validation, entry placement,
and bracket orchestration.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional

from apps.reference.core.time import get_clock
from apps.reference.telemetry.order_logger import order_logger
from apps.reference.domains.execution_position.utils import (
    generate_client_order_id,
    quantize_stop_price,
)
from apps.reference.domains.execution_position.qty_normalizer import normalize_qty
from apps.reference.domains.execution_position.pending_brackets_wal import write_pending_brackets_stored

if TYPE_CHECKING:
    from vfoundation.core.fsm_emit_compat import Message

LOG = logging.getLogger(__name__)

# FIX-LIFECYCLE-01: Trade lifecycle source-of-truth logger
try:
    from apps.reference.telemetry.trade_lifecycle_logger import trade_lifecycle as _trade_lifecycle
except ImportError:
    _trade_lifecycle = None

try:
    from apps.reference.domains.execution_position.fsm_manage import validate_not_immediate
except ImportError:
    def validate_not_immediate(pos_side, tp, sl, mark):
        pass


class OpenExecutor:
    """Executes DEC:OPEN verb — full entry lifecycle."""

    def __init__(self, fsm: Any) -> None:
        self._fsm = fsm

    async def execute_open(self, decision: "Message") -> None:
        """Execute the OPEN entry flow."""
        from vfoundation.core.fsm_emit_compat import Message, emit_compat
        from vfoundation.dr import wal

        symbol = decision.pld["symbol"]
        side = decision.pld["side"].upper()
        raw_qty = decision.pld["qty"]

        # EP-01.3-SUPERSEDE-ACK: Check if already waiting for cancel
        if symbol in self._fsm._supersede_canceling:
            LOG.info(f"EP-01.3: {symbol} already canceling pending entry, queueing new DEC:OPEN (supersede)")
            self._fsm._supersede_queue[symbol] = {
                "decision": decision, "queued_at": get_clock().now_sec()}
            return

        # EP-01.3-SUPERSEDE-ACK: Check if pending entries exist
        has_pending, pending_order_ids = self._check_pending_entries(symbol)
        if has_pending:
            if self._handle_supersede(symbol, side, decision, pending_order_ids):
                return  # Queued for later

        # Get mark price and instrument spec
        mark = await self._fsm.adapter.get_mark_price(symbol)
        instrument_spec = None
        if hasattr(self._fsm.config, "instruments") and self._fsm.config.instruments:
            instrument_spec = self._fsm.config.instruments.get(symbol)

        if not instrument_spec:
            err = f"instruments.{symbol} is missing (required SSOT for tick_size/step_size/min_qty/min_notional)"
            LOG.error(f"❌ [{symbol}] INSTRUMENT_CONFIG_MISSING: {err}")
            order_logger.write({"rid": decision.rid, "event_type": "ORDER_REJECTED",
                "symbol": symbol, "side": side, "quantity": str(raw_qty),
                "nrr_code": "NRR-INSTRUMENT-CONFIG-MISSING", "why": err})
            await emit_compat(self._fsm.fsm, Message(
                op="EVT", verb="ORDER_REJECTED", src="execution_position",
                dst="decision_making", rid=decision.rid,
                pld={"symbol": symbol, "side": side, "raw_qty": str(raw_qty),
                     "reason": "NRR-INSTRUMENT-CONFIG-MISSING", "details": err},
                why="NRR-INSTRUMENT-CONFIG-MISSING"), logger=LOG)
            return

        tick_size = float(instrument_spec.tick_size)
        step_size = instrument_spec.step_size
        min_qty = instrument_spec.min_qty
        min_notional = instrument_spec.min_notional

        # Normalize qty
        norm_result = normalize_qty(raw_qty=raw_qty, price=mark,
            step_size=step_size, min_qty=min_qty, min_notional=min_notional)
        if not norm_result.ok:
            LOG.warning(f"❌ [{symbol}] QTY_NORMALIZE_REJECTED: {norm_result.why}")
            order_logger.write({"rid": decision.rid, "event_type": "QTY_NORMALIZE_REJECTED",
                "symbol": symbol, "side": side, "quantity": str(raw_qty),
                "nrr_code": norm_result.why, "adapter_response": norm_result.to_dict()})
            await emit_compat(self._fsm.fsm, Message(
                op="EVT", verb="ORDER_REJECTED", src="execution_position",
                dst="decision_making", rid=decision.rid,
                pld={"symbol": symbol, "side": side, "raw_qty": str(raw_qty),
                     "reason": norm_result.why, "norm_result": norm_result.to_dict()},
                why=norm_result.why), logger=LOG)
            return
        qty = str(norm_result.qty)
        LOG.info(f"✅ [{symbol}] QTY_NORMALIZED: raw={raw_qty} → normalized={qty}")

        # Resolve SL/TP
        sl, tp, sl_source, tp_source = self._resolve_sl_tp(decision, symbol, side, mark)
        if sl is None or tp is None:
            return  # Already logged/rejected in _resolve_sl_tp

        # Quantize and validate
        tp = quantize_stop_price(float(tp), tick_size, side="BUY" if side == "BUY" else "SELL")
        sl = quantize_stop_price(float(sl), tick_size, side="SELL" if side == "BUY" else "BUY")
        validate_not_immediate("LONG" if side == "BUY" else "SHORT", tp, sl, mark)

        # GATE: Check SYMBOL_TIDY
        if decision.verb == "OPEN":
            sym_for_gate = decision.pld.get("symbol")
            if sym_for_gate and not self._fsm._evt_handlers.entry_tidy_gate_allow(sym_for_gate):
                return

        # Validate order policy
        order_type, tif, price = self._validate_order_policy(decision, symbol, side, qty)
        if order_type is None:
            return  # Already rejected

        # Generate entry ID and place order
        idem_key = (decision.pld or {}).get("idempotent_key") or getattr(decision, "idempotent_key", None) or decision.rid
        entry_id = generate_client_order_id("ENTRY", symbol, idempotent_key=str(idem_key) if idem_key else None)
        entry_resp = None

        if order_type == "LIMIT" and price:
            entry_resp = await self._place_limit_entry(decision, symbol, side, price, qty, tif, entry_id, wal)
            if entry_resp is None:
                return  # Rejected (GTX etc)
        else:
            entry_resp = await self._fsm.adapter.place_market_entry(symbol, side, qty, entry_id)
            LOG.info(f"✅ MARKET entry placed: {entry_resp}")

        # Post-entry: ORDER_INDEX, guardian, watchdog, logging
        self._post_entry_registration(decision, symbol, side, qty, raw_qty, entry_id, entry_resp,
                                       idem_key, norm_result, order_type, mark)

        # LIMIT deferred brackets path
        if order_type == "LIMIT":
            self._store_pending_brackets(entry_resp, symbol, side, sl, tp, qty, decision,
                                          idem_key, tick_size, entry_id)
            return None

        # MARKET: Pre-flight + immediate bracket placement
        if not await self._fsm._bracket_mgr.preflight_position_check(symbol):
            LOG.warning(f"🚫 [PHASE A3] Skipping TP/SL placement - position check failed for {symbol}")
            return None

        entry_order_id = str(entry_resp["orderId"])
        if not await self._fsm.order_guardian.should_place_brackets(symbol, entry_order_id):
            LOG.warning(f"🚫 OrderGuardian blocked bracket placement for {symbol}")
            return None

        await self._fsm._bracket_mgr.place_brackets_parallel(
            symbol=symbol, side=side, sl=sl, tp=tp, qty=qty,
            tick_size=tick_size, idem_key=idem_key,
            corr_id=decision.corr_id, oco_group_id=decision.oco_group_id,
            entry_resp=entry_resp, decision=decision)

    def _check_pending_entries(self, symbol: str):
        """Check if pending entries exist for this symbol."""
        has_pending = False
        pending_order_ids = []
        wdog = self._fsm.watchdog
        if wdog:
            for order_id, deadline in list(wdog.pending_orders.items()):
                if deadline.symbol == symbol:
                    has_pending = True
                    pending_order_ids.append(order_id)
            for order_id, deadline in list(wdog.acked_orders.items()):
                if deadline.symbol == symbol:
                    has_pending = True
                    pending_order_ids.append(order_id)
        return has_pending, pending_order_ids

    def _handle_supersede(self, symbol, side, decision, pending_order_ids):
        """EP-01.3-SUPERSEDE-ACK: Cancel pending and queue new decision. Returns True if queued."""
        try:
            pe_ttl_cfg = self._fsm.config.domains.execution_position.pending_entry_ttl
            if pe_ttl_cfg.enabled and pe_ttl_cfg.cancel_on_supersede:
                guard_result = self._fsm._evaluate_supersede_reprice_guard(symbol, decision, pending_order_ids)
                if guard_result is not None and not bool(guard_result.get("allow_cancel")):
                    analyses = guard_result.get("analyses") or []
                    LOG.info(
                        "EP-01.3: %s supersede reprice guard blocked cancel/repost (analyses=%s)",
                        symbol,
                        analyses,
                    )
                    if bool(guard_result.get("enforce")):
                        return True
                LOG.info(f"EP-01.3: {symbol} has {len(pending_order_ids)} pending entries, queueing new DEC:OPEN")
                self._fsm._supersede_canceling.add(symbol)
                self._fsm._supersede_queue[symbol] = {
                    "decision": decision, "cancel_order_ids": pending_order_ids,
                    "queued_at": get_clock().now_sec()}
                self._fsm._entry_mgr.cancel_pending_entries_for_symbol(
                    symbol=symbol, reason="CANCEL_SUPERSEDED", context=f"new_open_side={side}")
                loop = self._fsm._get_async_loop()
                if loop:
                    async def _supersede_timeout():
                        timeout_sec = float(pe_ttl_cfg.supersede_cancel_timeout_sec)
                        await get_clock().sleep_sec(timeout_sec)
                        if symbol in self._fsm._supersede_canceling:
                            LOG.warning(f"EP-01.3: {symbol} supersede cancel timeout, proceeding with queued open")
                            self._fsm._entry_mgr.process_queued_supersede(symbol)
                    self._fsm._submit_async(_supersede_timeout(), loop)
                return True
        except AttributeError:
            pass
        return False

    def _resolve_sl_tp(self, decision, symbol, side, mark):
        """Resolve SL/TP from strategy-provided prices or config fallback."""
        from vfoundation.core.fsm_emit_compat import Message, emit_compat

        explicit_sl_raw = decision.pld.get("stop_price") if decision.pld else None
        explicit_tp_raw = decision.pld.get("target_price") if decision.pld else None

        explicit_sl: Optional[Decimal] = None
        explicit_tp: Optional[Decimal] = None

        if explicit_sl_raw not in (None, "", "None", "null"):
            try:
                explicit_sl = Decimal(str(explicit_sl_raw))
            except Exception as e:
                LOG.warning(f"[{symbol}] Invalid explicit stop_price '{explicit_sl_raw}': {e}")

        if explicit_tp_raw not in (None, "", "None", "null"):
            try:
                explicit_tp = Decimal(str(explicit_tp_raw))
            except Exception as e:
                LOG.warning(f"[{symbol}] Invalid explicit target_price '{explicit_tp_raw}': {e}")

        sl_pct = tp_low_ratio = tp_high_ratio = None
        config_loaded = False

        if explicit_sl is None or explicit_tp is None:
            try:
                aurora = getattr(self._fsm.config.strategies, "aurora", None)
                if aurora is None:
                    raise ValueError("strategies.aurora not configured")
                instr_cfg = aurora.assets.get(symbol)
                if instr_cfg is None:
                    raise ValueError(f"strategies.aurora.assets.{symbol} not configured")
                exit_cfg = getattr(instr_cfg, "exit", None)
                if exit_cfg is None or exit_cfg.sl_pct is None:
                    raise ValueError(f"strategies.aurora.assets.{symbol}.exit.sl_pct is required")
                sl_pct = exit_cfg.sl_pct
                tp_cfg = getattr(instr_cfg, "take_profit", None)
                if tp_cfg is None or tp_cfg.tp_low_ratio is None:
                    raise ValueError(f"strategies.aurora.assets.{symbol}.take_profit.tp_low_ratio is required")
                tp_low_ratio = tp_cfg.tp_low_ratio
                tp_high_ratio = getattr(tp_cfg, "tp_high_ratio", None)
                config_loaded = True
            except (ValueError, AttributeError) as cfg_err:
                if explicit_sl is None or explicit_tp is None:
                    LOG.error(f"❌ [{symbol}] FAIL-CLOSED: Strategy did not provide SL/TP and config fallback missing: {cfg_err}")
                    # Rejection handled - return None
                    return None, None, None, None

        mark_dec = Decimal(str(mark))

        if explicit_sl is not None:
            sl, sl_source = explicit_sl, "STRATEGY"
        elif config_loaded and sl_pct is not None:
            sl_pct_dec = Decimal(str(sl_pct))
            sl = mark_dec * (Decimal("1") - sl_pct_dec) if side == "BUY" else mark_dec * (Decimal("1") + sl_pct_dec)
            sl_source = "CONFIG_FALLBACK"
        else:
            LOG.error(f"❌ [{symbol}] FAIL-CLOSED: No SL source available")
            return None, None, None, None

        if explicit_tp is not None:
            tp, tp_source = explicit_tp, "STRATEGY"
        elif config_loaded and sl_pct is not None and tp_low_ratio is not None:
            sl_pct_dec = Decimal(str(sl_pct))
            tp_low_ratio_dec = Decimal(str(tp_low_ratio))
            tp = mark_dec * (Decimal("1") + sl_pct_dec * tp_low_ratio_dec) if side == "BUY" else mark_dec * (Decimal("1") - sl_pct_dec * tp_low_ratio_dec)
            tp_source = "CONFIG_FALLBACK"
        else:
            LOG.error(f"❌ [{symbol}] FAIL-CLOSED: No TP source available")
            return None, None, None, None

        LOG.info(f"[{symbol}] TP/SL_RESOLVED: mark={mark}, SL={sl} (source={sl_source}), TP={tp} (source={tp_source})")
        return sl, tp, sl_source, tp_source

    def _validate_order_policy(self, decision, symbol, side, qty):
        """Validate order_type/tif/price policy. Returns (order_type, tif, price) or (None, None, None)."""
        from vfoundation.core.fsm_emit_compat import Message, emit_compat

        order_type = decision.pld.get("order_type")
        tif = decision.pld.get("tif")
        price = decision.pld.get("price")

        def _reject(nrr_code, details):
            order_logger.write({"rid": decision.rid, "event_type": "ORDER_REJECTED",
                "symbol": symbol, "side": side, "quantity": float(qty),
                "nrr_code": nrr_code, "why": details[:80], "source_fsm": "ExecPosFSM"})
            loop = self._fsm._get_async_loop()
            if loop:
                async def _do_reject():
                    await emit_compat(self._fsm.fsm, Message(
                        op="EVT", verb="ORDER_REJECTED", src="execution_position",
                        dst="decision_making", rid=decision.rid,
                        pld={"symbol": symbol, "side": side, "reason": nrr_code, "details": details},
                        why=nrr_code), logger=LOG)
                self._fsm._submit_async(_do_reject(), loop)

        if not order_type:
            _reject("NRR-047", "ORDER-POLICY-01: missing order_type (fail-closed)")
            return None, None, None

        order_type = str(order_type).upper()
        if order_type == "MARKET":
            if tif is not None:
                _reject("NRR-049", "ORDER-POLICY-01: MARKET must have tif=null")
                return None, None, None
        elif order_type == "LIMIT":
            if not price:
                _reject("NRR-050", "ORDER-POLICY-01: LIMIT requires price")
                return None, None, None
            if tif is None:
                _reject("NRR-052", "ORDER-POLICY-01: LIMIT requires tif (no default)")
                return None, None, None
            tif = str(tif).upper()
            if decision.pld.get("valid_for_ms") is None:
                _reject("NRR-025", "EP-01.3-INT: LIMIT requires valid_for_ms")
                return None, None, None
        else:
            _reject("NRR-048", f"ORDER-POLICY-01: unsupported order_type={order_type}")
            return None, None, None

        return order_type, tif, price

    async def _place_limit_entry(self, decision, symbol, side, price, qty, tif, entry_id, wal):
        """Place LIMIT entry, handle GTX rejection. Returns resp or None."""
        from vfoundation.core.fsm_emit_compat import Message, emit_compat

        LOG.info(f"Placing LIMIT entry: {symbol} {side} {qty} @ {price}, tif={tif}")
        try:
            entry_resp = await self._fsm.adapter.place_limit_entry(
                symbol, side, price, qty, time_in_force=tif, new_client_order_id=entry_id)
            LOG.info(f"✅ LIMIT entry placed: {entry_resp}")
            return entry_resp
        except Exception as e:
            from .reasons import MAKER_ONLY_REJECT, is_maker_only_reject_error
            err_code = getattr(e, 'code', None)
            if err_code and is_maker_only_reject_error(err_code):
                LOG.warning(f"MAKER_ONLY_REJECT: GTX order rejected (code={err_code}), symbol={symbol}")
                order_logger.write({"rid": decision.rid, "event_type": "ORDER_REJECTED",
                    "symbol": symbol, "side": side, "quantity": float(qty),
                    "nrr_code": "NRR-018", "why": MAKER_ONLY_REJECT, "source_fsm": "ExecPosFSM"})
                reject_msg = Message(op="EVT", verb="ORDER_REJECTED", src="execution_position",
                    dst="decision_making", rid=decision.rid,
                    pld={"symbol": symbol, "side": side, "reason": MAKER_ONLY_REJECT, "error_code": err_code},
                    why=MAKER_ONLY_REJECT)
                try:
                    wal.append(reject_msg.model_dump())
                except Exception:
                    pass
                await emit_compat(self._fsm.fsm, reject_msg, logger=LOG)
                return None
            else:
                LOG.error(f"LIMIT entry failed: {e}")
                raise

    def _post_entry_registration(self, decision, symbol, side, qty, raw_qty, entry_id, entry_resp,
                                  idem_key, norm_result, order_type, mark):
        """Register entry with ORDER_INDEX, guardian, watchdog, and logging."""
        from vfoundation.dr import wal
        from vfoundation.core.fsm_emit_compat import Message

        # ORDER_INDEX
        try:
            if hasattr(self._fsm.fsm, "order_index") and self._fsm.fsm.order_index:
                entry_order_id = str(entry_resp.get("orderId"))
                self._fsm.fsm.order_index.upsert_from_open(
                    rid=decision.rid or entry_order_id,
                    idempotent_key=str(idem_key), clientOrderId=entry_id,
                    symbol=symbol, side=str(side).upper(), order_type=order_type or "MARKET")
                self._fsm.fsm.order_index.attach_exchange_id(
                    clientOrderId=entry_id, exchangeOrderId=entry_order_id)
        except Exception:
            pass

        # Guardian
        self._fsm.order_guardian.register_entry(
            symbol=symbol, order_id=str(entry_resp["orderId"]),
            client_order_id=entry_id, side=side, qty=qty,
            corr_id=decision.corr_id, rid=decision.rid)
        try:
            metadata = decision.pld.get("metadata") if isinstance(decision.pld.get("metadata"), dict) else {}
            strategy_id = metadata.get("strategy_id") or decision.pld.get("strategy") or "aurora"
            self._fsm._open_strategy_by_symbol[symbol] = str(strategy_id)
        except Exception:
            pass

        # Polling tracking
        if hasattr(self._fsm.adapter, 'track_order'):
            self._fsm.adapter.track_order(entry_resp)

        # Watchdog
        self._fsm.watchdog.ensure_started()
        valid_for_ms = None
        if decision.pld and "valid_for_ms" in decision.pld:
            try:
                valid_for_ms = int(decision.pld["valid_for_ms"]) if decision.pld["valid_for_ms"] is not None else None
            except (ValueError, TypeError):
                valid_for_ms = None
        self._fsm.watchdog.track_order_placed(
            order_id=str(entry_resp["orderId"]), client_order_id=entry_id,
            symbol=symbol, corr_id=decision.corr_id, rid=decision.rid,
            fill_ttl_override_ms=valid_for_ms)

        # Order logger
        _open_regime = (decision.pld or {}).get("regime")
        _open_regime_confidence = (decision.pld or {}).get("regime_confidence")
        order_logger.write({
            "rid": decision.rid, "event_type": "ORDER_PLACED", "symbol": symbol,
            "side": side, "quantity": float(qty), "qty_raw": float(raw_qty) if raw_qty else None,
            "client_order_id": entry_id, "order_id": str(entry_resp["orderId"]),
            "source_fsm": "ExecPosFSM", "reservation_id": decision.corr_id,
            "adapter_response": entry_resp, "regime": _open_regime,
            "regime_confidence": _open_regime_confidence,
            "metadata": {"order_type": "MARKET_ENTRY", "corr_id": decision.corr_id}})

        self._fsm._open_regime_by_symbol[symbol] = {
            "regime": _open_regime, "regime_confidence": _open_regime_confidence}

        if _trade_lifecycle is not None:
            try:
                price = decision.pld.get("price")
                _trade_lifecycle.on_order_placed(
                    rid=decision.rid, order_id=str(entry_resp["orderId"]),
                    price=float(price) if price else None)
            except Exception:
                pass

        # WAL persistence
        try:
            order_placed_msg = Message(
                op="EVT", verb="ORDER_PLACED", src="execution_position", dst="observability",
                rid=decision.rid,
                pld={"symbol": symbol, "side": side, "qty": str(qty), "order_type": order_type,
                     "client_order_id": entry_id, "exchange_order_id": str(entry_resp.get("orderId")),
                     "order_id": str(entry_resp.get("orderId")), "rid": decision.rid,
                     "ts_ms": get_clock().now_ms(), "corr_id": decision.corr_id},
                why="order_placed")
            wal.append(order_placed_msg.model_dump())
            if hasattr(self._fsm, "bus"):
                self._fsm.bus.emit(
                    "EVT:ORDER_PLACED",
                    dict(order_placed_msg.pld or {}),
                    order_placed_msg.why,
                    [],
                )
        except Exception as wal_e:
            LOG.warning(f"Failed to write EVT:ORDER_PLACED to WAL: {wal_e}")

        # Correlation store
        entry_order_id = str(entry_resp["orderId"])
        decision.link_ack_id = entry_order_id
        self._fsm.correlation_store.put_entry_ack(entry_order_id, {
            'corr_id': decision.corr_id, 'oco_group_id': decision.oco_group_id,
            'rid': decision.rid, 'parent_client_order_id': None})
        self._fsm.log_adapter.log_trade_execution(
            rid=decision.rid, symbol=symbol, side=side,
            order_id=entry_order_id, status="ACK", corr_id=decision.corr_id)

        # Watchdog ACK
        self._fsm.watchdog.ensure_started()
        self._fsm.watchdog.on_order_ack(entry_order_id)

        if str(order_type).upper() == "LIMIT":
            try:
                from apps.reference.domains.execution_position.fsm import PendingEntryMeta

                metadata = decision.pld.get("metadata") if isinstance(decision.pld.get("metadata"), dict) else {}
                tf_sec = metadata.get("tf_sec") or decision.pld.get("tf_sec") or 0
                try:
                    tf_sec_int = int(tf_sec)
                except Exception:
                    tf_sec_int = 0

                strategy_id = metadata.get("strategy_id") or decision.pld.get("strategy") or "aurora"
                strategy_cfg = getattr(self._fsm.config.strategies, str(strategy_id), None)
                assets = getattr(strategy_cfg, "assets", None) if strategy_cfg is not None else None
                asset_cfg = assets.get(symbol) if isinstance(assets, dict) else None
                allowed_regimes = getattr(asset_cfg, "allowed_regimes", None) if asset_cfg is not None else None

                cancelable_regimes = None
                pe_cfg = self._fsm.config.domains.execution_position.pending_entry_ttl
                adv = getattr(pe_cfg, "advanced_stale_cancel", None)
                if adv is not None and getattr(adv, "enabled", False) and isinstance(allowed_regimes, list):
                    may_cancel = set(getattr(adv, "may_cancel_regimes", {}).get(str(side).upper(), []))
                    never_cancel = set(getattr(adv, "never_cancel_regimes", ["UNCERTAIN"]))
                    cancelable_regimes = sorted((set(str(x) for x in allowed_regimes) & may_cancel) - never_cancel)

                self._fsm._pending_entry_meta[entry_order_id] = PendingEntryMeta(
                    symbol=symbol,
                    side=str(side).upper(),
                    limit_price=str(decision.pld.get("price")),
                    placed_at_ms=get_clock().now_ms(),
                    tf_sec=tf_sec_int,
                    cancelable_regimes=cancelable_regimes,
                )
            except Exception as meta_err:
                LOG.debug("Failed to record PendingEntryMeta for %s: %s", entry_order_id, meta_err)

    def _store_pending_brackets(self, entry_resp, symbol, side, sl, tp, qty, decision,
                                 idem_key, tick_size, entry_id):
        """Store pending bracket data for LIMIT deferred placement."""
        entry_order_id = str(entry_resp["orderId"])
        self._fsm._pending_brackets[entry_order_id] = {
            "symbol": symbol, "side": side, "sl": sl, "tp": tp, "qty": qty,
            "rid": decision.rid, "idem_key": idem_key, "tick_size": tick_size,
            "corr_id": decision.corr_id, "oco_group_id": decision.oco_group_id,
            "entry_client_order_id": entry_id, "created_at": get_clock().now_sec()}
        try:
            write_pending_brackets_stored(
                entry_order_id=entry_order_id, symbol=symbol, side=side,
                sl=sl, tp=tp, qty=qty, rid=decision.rid, idem_key=idem_key,
                tick_size=tick_size, corr_id=decision.corr_id,
                oco_group_id=decision.oco_group_id, entry_client_order_id=entry_id)
        except Exception as e:
            LOG.warning(f"Failed to persist pending brackets to WAL: {e}")
        LOG.info(f"📌 [LIMIT-DEFERRED] Stored pending brackets for {symbol} entry {entry_order_id}, SL={sl}, TP={tp}")
