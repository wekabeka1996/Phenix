"""IntentBuilder for the execution-critical trade-intent boundary.

This helper owns the post-gate path after safety checks returned ALLOW:
- warmup and one-open-order re-checks
- order-policy and TTL resolution
- trade_intent payload assembly
- WAL persistence and FSM emission
- side-channel observability (trace, lifecycle, order logger)

It deliberately consumes upstream sizing/price decisions instead of
recomputing them here.
"""

import decimal
import json
import logging
import uuid
from typing import Any, Callable, Optional, TYPE_CHECKING

from vfoundation.core.protocol import Message
from vfoundation.core.protocol import truncate_why
from vfoundation.dr import wal
from apps.reference.utils.accessors import aget
from apps.reference.telemetry.metrics import inc_decision_deferred
from apps.reference.telemetry.order_logger import order_logger
from apps.reference.telemetry.regime_confidence_audit import (
    emit_regime_decision_audit,
)
from .normalized_reject_reasons import NormalizedRejectReasons
from .tpsl_owner import clone_tpsl_owner_ctx

try:
    from apps.reference.telemetry.trade_lifecycle_logger import trade_lifecycle as _trade_lifecycle
except ImportError:
    _trade_lifecycle = None

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig
    from apps.reference.core.time.clock import Clock
    from .safety_gates import SafetyGateResult


class IntentBuilder:
    """Build, validate, and emit TRADE_INTENT_PROPOSED events.

    Receives a ``SafetyGateResult`` (ALLOW) and executes the remaining
    pre-flight checks, order-policy validation, payload construction,
    WAL persistence, and FSM emission.
    """

    def __init__(
        self,
        *,
        fsm: Any,
        clock: "Clock",
        config: "AuroraConfig",
        tca_prefs: Any,
        risk_budgets: Any,
        safe_decimal_fn: Callable,
        check_strategy_arbitration_fn: Callable,
        warmup_gate_fn: Callable,
        emit_rejected_fn: Callable,
        record_blocked_fn: Callable[[str], None],
        record_accepted_fn: Callable[[str], None],
        emit_deferred_fn: Callable,
        get_side_bias_params_fn: Callable,
        side_intent_window: dict,
        logger: logging.Logger,
    ) -> None:
        self._fsm = fsm
        self._clock = clock
        self.config = config
        self._tca_prefs = tca_prefs
        self._risk_budgets = risk_budgets
        self._safe_decimal = safe_decimal_fn
        self._check_strategy_arbitration = check_strategy_arbitration_fn
        self._warmup_gate = warmup_gate_fn
        self._emit_rejected = emit_rejected_fn
        self._record_blocked = record_blocked_fn
        self._record_accepted = record_accepted_fn
        self._emit_deferred = emit_deferred_fn
        self._get_side_bias_params = get_side_bias_params_fn
        self._side_intent_window = side_intent_window
        self.logger = logger
        self.seq_counter: int = 0

    # -- helpers ---------------------------------------------------------------

    def _get_strict(self, obj: Any, key: str, err_msg: str) -> Any:
        """Read a required field from a dict or object and fail on None."""
        if isinstance(obj, dict):
            val = obj[key] if key in obj else None
        else:
            val = aget(obj, key, None)
        if val is None:
            raise ValueError(err_msg)
        return val

    def _reject(self, *, symbol: str, strategy_id: str, side: str, rid: str,
                reason_code: str, context: str, why_chain: list) -> None:
        """Emit the canonical reject event for builder-local contract failures."""
        self._emit_rejected(
            symbol=symbol, strategy_id=str(strategy_id), side=str(side),
            rid=str(rid), reason_code=reason_code, reason="DECISION",
            context=context,
            why_chain=(why_chain if isinstance(why_chain, list) else []),
        )
        self._record_blocked(symbol)

    # -- main entry point ------------------------------------------------------

    def build_and_emit(
        self,
        *,
        symbol: str,
        side: str,
        qty: decimal.Decimal,
        price: decimal.Decimal,
        why_chain: list,
        rid: str,
        reduce_only: bool,
        strategy_id: str,
        decision_ts_ms: Optional[int],
        stop_price: Optional[str],
        target_price: Optional[str],
        entry_plan_trace: Optional[dict],
        tf_sec: Optional[int],
        max_slippage_bps: Optional[int],
        max_latency_ms: Optional[int],
        risk_score: Optional[float],
        tpsl_owner_ctx: Optional[dict] = None,
        strategy_trace: Optional[dict] = None,
        normalize_mode: str = "signed_v2",
        sg: "SafetyGateResult",
    ) -> None:
        """Build and emit a TRADE_INTENT_PROPOSED event.

        Execution order matters here: the builder performs the last contract
        checks, persists the proposal to WAL, emits it through the FSM, and
        only then commits arbitration/post-emit bookkeeping.
        """
        intent_side = sg.intent_side
        trace_ts_ms = sg.trace_ts_ms

        # ── Pre-flight: warmup re-check ────────────────────────
        if self._warmup_gate(
            symbol=symbol, rid=rid, reduce_only=reduce_only,
            context="decision_making:_propose_trade_intent",
        ):
            return

        # ── CAS guard (ENTRY only) ─────────────────────────────
        if not reduce_only:
            try:
                if hasattr(self._fsm, "order_index") and self._fsm.order_index:
                    if not self._fsm.order_index.try_reserve_entry(symbol, rid):
                        now_ms = self._clock.now_ms()
                        retry_key = f"order_in_flight:{symbol}:{rid}"
                        self.logger.info(
                            f"[{symbol}] TRADE_INTENT_DEFERRED: NRR-ORDER-IN-FLIGHT"
                        )
                        inc_decision_deferred("NRR-ORDER-IN-FLIGHT", symbol)
                        self._emit_deferred(
                            symbol=symbol, reason="NRR-ORDER-IN-FLIGHT",
                            retry_key=retry_key, next_allowed_ts=now_ms + 1000,
                            original_event_name="EVT:TRADE_INTENT_PROPOSED",
                            original_payload_min={
                                "symbol": symbol, "side": side,
                                "rid": rid, "strategy_id": strategy_id,
                            },
                            attempt=1, max_attempts=3,
                            why_chain=(why_chain or []) + ["order_in_flight"],
                            context="decision_making:one_open_order_guard",
                        )
                        self._record_blocked(symbol)
                        return
            except Exception as e:
                self.logger.error(
                    f"[{symbol}] OrderIndex access failed: {e}", exc_info=True)
                self._emit_deferred(
                    symbol=symbol,
                    reason="NRR-ORDER-INDEX-FAIL",
                    retry_key=f"order_index_fail:{symbol}:{rid}",
                    next_allowed_ts=self._clock.now_ms() + 1000,
                    original_event_name="EVT:TRADE_INTENT_PROPOSED",
                    original_payload_min={
                        "symbol": symbol,
                        "side": side,
                        "rid": rid,
                        "strategy_id": strategy_id,
                    },
                    attempt=1,
                    max_attempts=3,
                    why_chain=(why_chain or []) + ["order_index_failure"],
                    context="decision_making:order_index_failure",
                )
                self._record_blocked(symbol)
                return

        # ── Decimal conversion (after guards) ──────────────────
        try:
            qty = decimal.Decimal(str(qty))
            price = decimal.Decimal(str(price))
        except Exception as _e:
            self.logger.error(
                f"[{symbol}] Invalid qty/price: qty={qty!r} price={price!r}: {_e}")
            self._record_blocked(symbol)
            return

        # ── TCA prefs ──────────────────────────────────────────
        try:
            if max_slippage_bps is not None:
                max_slippage = str(max_slippage_bps)
            else:
                max_slippage = str(self._get_strict(
                    self._tca_prefs, 'max_slippage_bps', "Missing max_slippage_bps"))
            if max_latency_ms is not None:
                max_latency = max_latency_ms
            else:
                max_latency = self._get_strict(
                    self._tca_prefs, 'max_latency_ms', "Missing max_latency_ms")
            maker_pref = self._get_strict(
                self._tca_prefs, 'maker_preference', "Missing maker_preference")
        except ValueError as e:
            self.logger.error(f"TCA Config Block: {e}")
            return

        # ── Risk budgets ───────────────────────────────────────
        try:
            trade_cvar = str(self._get_strict(
                self._risk_budgets, 'trade_cvar95_max_bps', "Missing trade_cvar95_max_bps"))
            session_cvar = str(self._get_strict(
                self._risk_budgets, 'session_cvar95_max_bps', "Missing session_cvar95_max_bps"))
        except ValueError as e:
            self.logger.error(f"RiskBudget Config Block: {e}")
            return

        # ── Order policy resolution ────────────────────────────
        order_type, tif, valid_for_ms = self._resolve_order_policy(
            symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
            tf_sec=tf_sec, reduce_only=reduce_only, why_chain=why_chain,
        )
        if order_type is None:
            return  # rejection already emitted

        # ── SL/TP sanitization ─────────────────────────────────
        stop_price_payload: Optional[str] = None
        target_price_payload: Optional[str] = None
        if stop_price not in (None, "", "None"):
            sd = self._safe_decimal(stop_price, default=None)
            stop_price_payload = str(sd) if sd is not None else None
        if target_price not in (None, "", "None"):
            td = self._safe_decimal(target_price, default=None)
            target_price_payload = str(td) if td is not None else None
        tpsl_owner_payload = clone_tpsl_owner_ctx(tpsl_owner_ctx)

        # These schema-required fields are still produced in their current
        # compatibility form here. The builder does not have a proven local
        # Kelly calculator, so this path only preserves the existing runtime
        # values instead of introducing new sizing math.
        try:
            strat_cfg = getattr(self.config.strategies, str(
                strategy_id), getattr(self.config.strategies, "aurora", None))
            kelly_frac = str(
                getattr(getattr(strat_cfg.decision, "kelly", None), "fraction", "0.1"))
        except Exception:
            kelly_frac = "0.1"

        # ── Payload assembly ───────────────────────────────────
        trade_intent = {
            "rid": str(rid),
            "instrument": symbol,
            "side": side,
            "strategy": strategy_id,
            "order": {
                "qty": str(qty), "price": str(price), "price_ref": str(price),
                "reduce_only": reduce_only, "order_type": order_type, "tif": tif,
            },
            "p": "0.75", "payoff_ratio_r": "2.0",
            "tca_budget": {
                "max_slippage_bps": max_slippage,
                "max_latency_ms": max_latency,
                "maker_preference": str(maker_pref),
            },
            "risk_context": {"risk_score": risk_score if risk_score is not None else 0.0},
            "risk_budget": {"trade_cvar95_max_bps": trade_cvar, "session_cvar95_max_bps": session_cvar},
            "size": {"notional_cap_usd": str(qty * price), "kelly_fraction": kelly_frac},
            "valid_for_ms": valid_for_ms,
            "why": why_chain,
            "dto_version": "1.0.0",
            "schema_ref": "trade_intent_v1.json",
            "idempotent_key": str(uuid.uuid4()),
            "stop_price": stop_price_payload,
            "target_price": target_price_payload,
            "entry_plan": entry_plan_trace,
            "regime": sg.regime,
            "regime_confidence": sg.regime_confidence,
            "regime_provenance": None,
        }
        regime_provenance = getattr(sg, "regime_provenance", None)
        if isinstance(regime_provenance, dict) and regime_provenance:
            trade_intent["regime_provenance"] = regime_provenance
        if tpsl_owner_payload is not None:
            trade_intent["tpsl_owner_ctx"] = tpsl_owner_payload
        # Optional top-level trace is part of the active execution-boundary
        # schema and is only attached when an upstream strategy supplied one.
        if isinstance(strategy_trace, dict) and strategy_trace:
            trade_intent["trace"] = strategy_trace

        # ── Arbitration pre-check ──────────────────────────────
        commit = self._check_strategy_arbitration(
            symbol, strategy_id, ts_ms=decision_ts_ms, commit=False)
        if not commit["allowed"]:
            self.logger.info(
                f"[{symbol}] TRADE_INTENT_BLOCKED: Arbitration rejected: {commit['reason']}")
            self._record_blocked(symbol)
            return
        try:
            emit_regime_decision_audit(
                logger=self.logger,
                symbol=str(symbol),
                rid=str(rid),
                lifecycle_id=str(trade_intent["idempotent_key"]),
                strategy_id=str(strategy_id),
                sg=sg,
                outcome="ALLOW",
            )
        except Exception:
            self.logger.debug(
                "REGIME_AUDIT decision emit failed in IntentBuilder",
                exc_info=True,
            )

        # ── Forensic trace ─────────────────────────────────────
        trace_payload = {
            "symbol": symbol, "ts": trace_ts_ms, "intent_side": intent_side,
            "signal_score": sg.signal_score, "regime": sg.regime,
            "regime_confidence": sg.regime_confidence,
            "trend_dir": sg.trend_dir, "trend_run_length": sg.trend_run_length, "delta_price": sg.delta_price,
            "pm_norm_10s": sg.pm_norm_10s, "pm_norm_60s": sg.pm_norm_60s,
            "pm_norm_300s": sg.pm_norm_300s,
            "vol_pct_10s": sg.vol_pct_10s, "vol_pct_60s": sg.vol_pct_60s,
            "vol_pct_300s": sg.vol_pct_300s,
            "gate_outcome": "ALLOW", "deny_reason": None,
            "why": (str(sg.why_short)[:80] if sg.why_short else ""),
        }
        if isinstance(regime_provenance, dict) and regime_provenance:
            trace_payload["regime_provenance"] = regime_provenance
        if tpsl_owner_payload is not None:
            trace_payload["tpsl_owner_ctx"] = tpsl_owner_payload
            self.logger.info(
                "[%s] TPSL_OWNER_INTENT intended=%s final=%s reason=%s",
                symbol,
                tpsl_owner_payload.get("intended_owner"),
                tpsl_owner_payload.get("final_owner"),
                tpsl_owner_payload.get("owner_loss_reason"),
            )
        try:
            self._fsm.emit("EVT:DECISION_TRACE_EMITTED", payload=trace_payload,
                           why="decision_trace", data_ref=why_chain)
        except Exception:
            pass

        # ── Record accepted ────────────────────────────────────
        try:
            self._record_accepted(symbol)
        except Exception as e:
            self.logger.warning(
                f"Failed to record accepted intent metrics: {e}")

        # ── WAL + FSM emit ─────────────────────────────────────
        # Arbitration is committed only after both durability and boundary emit
        # succeeded, so a failed append/emit must leave the arbitration window
        # unpoisoned for the competing strategy.
        try:
            intent_evt = Message(
                op="EVT", verb="TRADE_INTENT_PROPOSED", src="decision_making",
                dst="execution_position", rid=str(rid), pld=trade_intent,
                why=truncate_why("trade_intent") or "trade_intent",
                data_ref=[str(x) for x in why_chain] if isinstance(
                    why_chain, list) else [],
                intent="PROPOSAL",
            )
            res = wal.append(intent_evt.model_dump())
            if res is None:
                self.logger.error(
                    f"[{symbol}] CRITICAL: WAL WRITE FAILED (LOCK TIMEOUT). RID={rid}")
                return
        except Exception as wal_e:
            self.logger.warning(
                f"Failed to write TRADE_INTENT_PROPOSED to WAL: {wal_e}")
            return

        try:
            self._fsm.emit("EVT:TRADE_INTENT_PROPOSED", payload=trade_intent,
                           why="trade_intent", data_ref=why_chain)
        except Exception as emit_e:
            self.logger.error(
                f"[{symbol}] CRITICAL: FSM EMIT FAILED for EVT:TRADE_INTENT_PROPOSED. "
                f"RID={rid}. reason={emit_e}")
            return

        # ── Arbitration final commit ───────────────────────────
        self._check_strategy_arbitration(
            symbol, strategy_id, ts_ms=decision_ts_ms, commit=True)

        # ── Lifecycle logger ───────────────────────────────────
        if _trade_lifecycle is not None:
            try:
                _trade_lifecycle.on_intent(
                    rid=str(rid), symbol=symbol, side=intent_side,
                    regime=str(sg.regime) if sg.regime else "",
                    confidence=float(
                        sg.regime_confidence) if sg.regime_confidence is not None else None,
                    regime_provenance=regime_provenance if isinstance(
                        regime_provenance, dict) else None,
                    signal_score=float(
                        sg.signal_score) if sg.signal_score is not None else None,
                    strategy_id=str(strategy_id), entry_type=order_type,
                )
            except Exception:
                pass

        # ── TAP LOG ────────────────────────────────────────────
        log_entry = {
            "symbol": symbol, "tf_sec": None,
            "bar_end_ts_ms": trace_ts_ms,
            "bar_id": f"{symbol}:intent:{trace_ts_ms}",
            "seq": self.seq_counter, "source": "dm_intent_emitted",
            "why": "intent_proposed",
        }
        print(json.dumps(log_entry), flush=True)
        self.seq_counter += 1

        # ── Side-bias bookkeeping ──────────────────────────────
        try:
            if not reduce_only:
                if symbol not in self._side_intent_window:
                    self._side_intent_window[symbol] = {
                        "buys": [], "sells": []}
                window_data = self._side_intent_window[symbol]
                now_sec = self._clock.now_sec()
                _, bias_window_sec, _, _ = self._get_side_bias_params(symbol)
                window_data["buys"] = [
                    ts for ts in window_data["buys"] if now_sec - ts < bias_window_sec]
                window_data["sells"] = [
                    ts for ts in window_data["sells"] if now_sec - ts < bias_window_sec]
                if intent_side == "LONG":
                    window_data["buys"].append(now_sec)
                elif intent_side == "SHORT":
                    window_data["sells"].append(now_sec)
        except Exception:
            pass

        # ── OrderLogger ────────────────────────────────────────
        # lifecycle_id mirrors idempotent_key at the top level so downstream
        # execution/order forensics can correlate the proposal without digging
        # through metadata.
        order_logger.write({
            "rid": rid, "event_type": "ORDER_INTENT",
            # PHASE 1: top-level lifecycle identity
            "lifecycle_id": trade_intent["idempotent_key"],
            "symbol": symbol, "side": side.upper(),
            "quantity": float(qty), "price": float(price),
            "source_fsm": "DecisionMaking",
            "regime": sg.regime, "regime_confidence": sg.regime_confidence,
            "regime_provenance": regime_provenance if isinstance(regime_provenance, dict) else None,
            "metadata": {
                "intent_proposed": True,
                "idempotent_key": trade_intent["idempotent_key"],
                "normalize_mode_effective": normalize_mode,
                "min_regime_confidence": getattr(sg, "min_regime_confidence", None),
                "threshold_applied": getattr(sg, "threshold_applied", None),
                "threshold_verdict": getattr(sg, "threshold_verdict", None),
                "threshold_reason": getattr(sg, "threshold_reason", None),
            },
        })

    # -- Order policy resolution -----------------------------------------------

    def _resolve_order_policy(
        self,
        *,
        symbol: str,
        strategy_id: str,
        side: str,
        rid: str,
        tf_sec: Optional[int],
        reduce_only: bool,
        why_chain: list,
    ) -> tuple[Optional[str], Optional[str], Optional[int]]:
        """Resolve order_type, tif, valid_for_ms.  Returns (None, ..., ...) on rejection."""
        order_type: Optional[str] = None
        tif: Optional[str] = None
        try:
            strat_cfg = getattr(self.config.strategies, str(strategy_id), None)
            exec_cfg = getattr(strat_cfg, "execution",
                               None) if strat_cfg else None
            if reduce_only and exec_cfg is not None:
                # Close orders use exit_order_type/exit_tif when configured,
                # falling back to entry fields for backward compatibility.
                order_type = getattr(exec_cfg, "exit_order_type",
                                     None) or getattr(exec_cfg, "entry_order_type", None)
                tif = getattr(exec_cfg, "exit_tif",
                              None) if getattr(exec_cfg, "exit_order_type", None) else getattr(exec_cfg, "entry_tif", None)
            else:
                order_type = getattr(exec_cfg, "entry_order_type",
                                     None) if exec_cfg else None
                tif = getattr(exec_cfg, "entry_tif",
                              None) if exec_cfg else None
        except Exception:
            pass

        if not order_type:
            self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                         reason_code=NormalizedRejectReasons.ORDER_TYPE_MISSING,
                         context="ORDER-POLICY-01: missing entry_order_type", why_chain=why_chain)
            return None, None, None

        order_type_u = str(order_type).upper()

        try:
            caps = self.config.domains.execution_position.order_capabilities
            supported_types = set(str(x).upper()
                                  for x in (caps.supported_order_types or []))
            supported_tifs = set(str(x).upper()
                                 for x in (caps.supported_tif or []))
        except Exception:
            supported_types, supported_tifs = set(), set()

        if supported_types and order_type_u not in supported_types:
            self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                         reason_code=NormalizedRejectReasons.UNSUPPORTED_ORDER_TYPE,
                         context=f"ORDER-POLICY-01: unsupported order_type={order_type_u}",
                         why_chain=why_chain)
            return None, None, None

        if order_type_u == "LIMIT":
            if tif is None:
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                             reason_code=NormalizedRejectReasons.TIF_REQUIRED_FOR_LIMIT,
                             context="ORDER-POLICY-01: LIMIT requires explicit tif",
                             why_chain=why_chain)
                return None, None, None
            tif_u = str(tif).upper()
            if supported_tifs and tif_u not in supported_tifs:
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                             reason_code=NormalizedRejectReasons.UNSUPPORTED_TIF,
                             context=f"ORDER-POLICY-01: unsupported tif={tif_u}",
                             why_chain=why_chain)
                return None, None, None
            tif = tif_u
        else:
            if tif is not None:
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                             reason_code=NormalizedRejectReasons.UNSUPPORTED_TIF,
                             context="ORDER-POLICY-01: MARKET must have tif=null",
                             why_chain=why_chain)
                return None, None, None
            tif = None

        # ── valid_for_ms (LIMIT only) ─────────────────────────
        # Close-path exemption: reduce_only LIMIT intents use exit_limit_ttl_ms
        # from config (if set), avoiding the entry-path tf_sec → ttl_by_tf_sec
        # pipeline.  Normal entry (reduce_only=False) unchanged.
        valid_for_ms: Optional[int] = None
        if order_type_u == "LIMIT" and reduce_only:
            # Reduce-only LIMIT close: schema still requires valid_for_ms as
            # integer.  Use exit_limit_ttl_ms from strategy execution config.
            try:
                strat_cfg = getattr(self.config.strategies,
                                    str(strategy_id), None)
                exec_cfg = getattr(strat_cfg, "execution",
                                   None) if strat_cfg else None
                exit_ttl = getattr(exec_cfg, "exit_limit_ttl_ms",
                                   None) if exec_cfg else None
                if exit_ttl is not None:
                    valid_for_ms = int(exit_ttl)
            except Exception:
                pass
            if valid_for_ms is None:
                # No exit_limit_ttl_ms configured; LIMIT close without TTL
                # would violate the schema.  Reject with clear diagnostics.
                self._reject(
                    symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                    reason_code=NormalizedRejectReasons.DATA_NOT_READY,
                    context="ORDER-POLICY-01: reduce_only LIMIT requires "
                            "execution.exit_limit_ttl_ms",
                    why_chain=why_chain)
                return None, None, None
        elif order_type_u == "LIMIT" and not reduce_only:
            if tf_sec is None:
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                             reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
                             context="EP-01.3-INT: LIMIT requires tf_sec",
                             why_chain=why_chain)
                return None, None, None
            try:
                pe_ttl_cfg = self.config.domains.execution_position.pending_entry_ttl
                if pe_ttl_cfg.enabled and tf_sec is not None:
                    ttl_by_tf = pe_ttl_cfg.ttl_by_tf_sec
                    if tf_sec in ttl_by_tf:
                        valid_for_ms = int(ttl_by_tf[tf_sec]) * 1000
                    elif pe_ttl_cfg.reject_unknown_tf:
                        self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                                     reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
                                     context=f"EP-01.3-INT: tf_sec={tf_sec} not in ttl_by_tf_sec",
                                     why_chain=why_chain)
                        return None, None, None
            except Exception as e:
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                             reason_code=NormalizedRejectReasons.DATA_NOT_READY,
                             context=f"EP-01.3-INT: valid_for_ms error: {e}",
                             why_chain=why_chain)
                return None, None, None

            if valid_for_ms is None:
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                             reason_code=NormalizedRejectReasons.DATA_NOT_READY,
                             context="EP-01.3-INT: LIMIT requires valid_for_ms",
                             why_chain=why_chain)
                return None, None, None

        return order_type_u, tif, valid_for_ms
