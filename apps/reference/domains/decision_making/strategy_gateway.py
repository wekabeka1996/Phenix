"""StrategyGateway — Gate chain for EVT:STRATEGY_SIGNAL_PRODUCED.
Extracted from decision_making.py (Phase 14A, STEP 10). LOC budget: <=500.
"""
import decimal
import uuid
from typing import Any, TYPE_CHECKING

from apps.reference.config_contract import ConfigContractError
from apps.reference.utils.accessors import aget
from apps.reference.telemetry.metrics import inc_config_contract_violation
from apps.reference.contracts.reject_reasons import normalize_config_error
from vfoundation.core.protocol import Message

from .normalized_reject_reasons import NormalizedRejectReasons
from .decision_context import create_decision_context
from .entry_plan import resolve_strategy_entry_prices
from .tpsl_owner import resolve_gateway_tpsl_owner_ctx
from .gate_protocol import GateContext, GateOutcome
from .gate_chain import GateChain
from .gates import (
    risk_gate, risk_skew_gate, flip_gate, qos_gate,
    exposure_gate, ttl_gate, warmup_gate, safety_gate,
    arbitration_gate,
)

if TYPE_CHECKING:
    from .decision_making import DecisionMaking


class StrategyGateway:
    """Gate chain for strategy signals -> TRADE_INTENT_PROPOSED."""

    def __init__(self, dm: "DecisionMaking") -> None:
        self._dm = dm
        self.logger = dm.logger

    @property
    def _clock(self):
        return self._dm._clock

    @property
    def config(self):
        return self._dm.config

    def _rk(self, *, prefix: str, symbol: str, rid: str | None,
            side: str | None = None, ts_ms: Any = None) -> str:
        if rid:
            return f"{prefix}:{symbol}:{rid}"
        if ts_ms is None:
            ts_ms = self._clock.now_ms()
        return f"{prefix}:{symbol}:{side}:{ts_ms}" if side else f"{prefix}:{symbol}:{ts_ms}"

    def _rscfg(self, key: str) -> Any:
        v = getattr(self.config.domains.decision_making.risk_skew, key, None)
        if v is None:
            raise ValueError(
                f"domains.decision_making.risk_skew.{key} required (SSOT)")
        return v

    def _reject(self, *, symbol, strategy_id, side, rid,
                reason_code, reason, context, why_chain, details=None):
        self._dm._emit_trade_intent_rejected(
            symbol=symbol, strategy_id=str(strategy_id), side=str(side),
            rid=str(rid), reason_code=reason_code, reason=reason,
            context=context,
            why_chain=why_chain if isinstance(why_chain, list) else [],
            details=details)
        self._dm._record_blocked_intent(symbol)

    def _defer(self, *, symbol, reason, retry_key, next_ts, pld,
               why_chain, context, attempt=1, max_attempts=None):
        if max_attempts is None:
            try:
                strategy_id = pld.get("strategy_id", "aurora")
                strat_cfg = getattr(self.config.strategies, str(
                    strategy_id), getattr(self.config.strategies, "aurora", None))
                max_attempts = int(
                    getattr(strat_cfg.decision, "retry_max_count", 5))
            except Exception:
                max_attempts = 5

        now_ms = self._clock.now_ms()
        if attempt > 1 and next_ts > now_ms:
            base_delay = next_ts - now_ms
            try:
                strategy_id = pld.get("strategy_id", "aurora")
                strat_cfg = getattr(self.config.strategies, str(
                    strategy_id), getattr(self.config.strategies, "aurora", None))
                factor = float(getattr(strat_cfg.decision,
                               "retry_backoff_factor", 2.0))
            except Exception:
                factor = 2.0
            next_ts = now_ms + int(base_delay * (factor ** (attempt - 1)))

        self._dm._emit_intent_deferred_v1(
            symbol=symbol, reason=reason, retry_key=retry_key,
            next_allowed_ts=int(next_ts),
            original_event_name="EVT:STRATEGY_SIGNAL_PRODUCED",
            original_payload_min=dict(pld),
            attempt=attempt, max_attempts=max_attempts,
            why_chain=why_chain, context=context)
        self._dm._record_blocked_intent(symbol)

    def _block(self, symbol: str) -> None:
        self._dm._record_blocked_intent(symbol)

    def _emit_gate_chain_trace(self, symbol: str, strategy_id: str, rid: str, ts_ms: int, chain_result: Any) -> None:
        try:
            gates = []
            for entry in chain_result.trace:
                gate_dict = {
                    "gate_name": entry.gate_name,
                    "outcome": entry.outcome.value if hasattr(entry.outcome, "value") else str(entry.outcome),
                    "elapsed_ms": entry.elapsed_ms,
                }
                if entry.reason_code:
                    gate_dict["reason_code"] = entry.reason_code
                gates.append(gate_dict)

            payload = {
                "symbol": symbol,
                "strategy_id": str(strategy_id),
                "rid": str(rid),
                "ts_ms": int(ts_ms),
                "final_outcome": chain_result.final_outcome.value if hasattr(chain_result.final_outcome, "value") else str(chain_result.final_outcome),
                "total_elapsed_ms": chain_result.total_elapsed_ms,
                "gates": gates,
            }
            self._dm.fsm.emit(
                "EVT:GATE_CHAIN_TRACE",
                payload,
                why="gate_chain_evaluated",
                data_ref=[]
            )
        except Exception as e:
            self.logger.error(f"Error emitting GATE_CHAIN_TRACE: {e}")

    def _validate_md_amr_trace(self, trace: Any) -> tuple[bool, dict[str, Any]]:
        required = ["dir_score", "thr_buy", "thr_sell", "w_raw",
                    "w_norm", "qty_base", "qty_new", "conf_ratio"]
        if not isinstance(trace, dict):
            return False, {"error": "trace_not_dict", "required": required}

        missing = [key for key in required if key not in trace]
        if missing:
            return False, {"error": "missing_keys", "missing": missing}

        def _num(value: Any) -> float | None:
            try:
                dec = decimal.Decimal(str(value))
            except Exception:
                return None
            if not dec.is_finite():
                return None
            return float(dec)

        normalized: dict[str, Any] = {}
        weight_keys = ["d1", "h1", "m30", "m15"]
        for trace_key in ("w_raw", "w_norm"):
            weight_block = trace.get(trace_key)
            if not isinstance(weight_block, dict):
                return False, {"error": f"{trace_key}_not_dict"}
            missing_weights = [
                key for key in weight_keys if key not in weight_block]
            if missing_weights:
                return False, {"error": f"{trace_key}_missing", "missing": missing_weights}
            normalized[trace_key] = {}
            for weight_key in weight_keys:
                value = _num(weight_block.get(weight_key))
                if value is None:
                    return False, {"error": f"{trace_key}_{weight_key}_invalid"}
                normalized[trace_key][weight_key] = value

        for scalar_key in ("dir_score", "thr_buy", "thr_sell", "qty_base", "qty_new", "conf_ratio"):
            value = _num(trace.get(scalar_key))
            if value is None:
                return False, {"error": f"{scalar_key}_invalid"}
            normalized[scalar_key] = value

        if not (-1.0 <= normalized["dir_score"] <= 1.0):
            return False, {"error": "dir_score_out_of_range", "value": normalized["dir_score"]}
        if normalized["thr_buy"] <= 0.0 or normalized["thr_sell"] <= 0.0:
            return False, {"error": "threshold_non_positive"}
        if normalized["qty_base"] < 0.0 or normalized["qty_new"] < 0.0:
            return False, {"error": "qty_negative"}
        if not (0.0 <= normalized["conf_ratio"] <= 2.0):
            return False, {"error": "conf_ratio_out_of_range", "value": normalized["conf_ratio"]}

        if "objective" in trace:
            valid_objective, objective_info = self._validate_objective_trace(
                trace.get("objective"))
            if not valid_objective:
                return False, {"error": "objective_invalid", "details": objective_info}
            normalized["objective"] = objective_info["normalized"]

        for optional_key in ("atr_zscore", "bias", "dir_components"):
            if optional_key in trace:
                normalized[optional_key] = trace.get(optional_key)
        return True, {"normalized": normalized}

    def _validate_objective_trace(self, trace: Any) -> tuple[bool, dict[str, Any]]:
        required = ["trace_id", "multiplier",
                    "objective_score", "components", "raw_metrics"]
        if not isinstance(trace, dict):
            return False, {"error": "objective_not_dict", "required": required}
        missing = [key for key in required if key not in trace]
        if missing:
            return False, {"error": "objective_missing_keys", "missing": missing}

        def _num(value: Any) -> float | None:
            try:
                dec = decimal.Decimal(str(value))
            except Exception:
                return None
            if not dec.is_finite():
                return None
            return float(dec)

        trace_id = str(trace.get("trace_id") or "").strip()
        if not trace_id:
            return False, {"error": "objective_trace_id_invalid"}
        multiplier = _num(trace.get("multiplier"))
        objective_score = _num(trace.get("objective_score"))
        if multiplier is None or objective_score is None:
            return False, {"error": "objective_scalar_invalid"}
        components = trace.get("components")
        raw_metrics = trace.get("raw_metrics")
        if not isinstance(components, dict) or not isinstance(raw_metrics, dict):
            return False, {"error": "objective_maps_invalid"}

        normalized_components: dict[str, float] = {}
        for key, value in components.items():
            value_num = _num(value)
            if value_num is None:
                return False, {"error": "objective_component_invalid", "key": key}
            normalized_components[str(key)] = value_num
        normalized_raw_metrics: dict[str, float] = {}
        for key, value in raw_metrics.items():
            value_num = _num(value)
            if value_num is None:
                return False, {"error": "objective_raw_metric_invalid", "key": key}
            normalized_raw_metrics[str(key)] = value_num
        return True, {
            "normalized": {
                "trace_id": trace_id,
                "multiplier": multiplier,
                "objective_score": objective_score,
                "components": normalized_components,
                "raw_metrics": normalized_raw_metrics,
            }
        }

    def process_signal(self, event: Message) -> None:  # noqa: C901
        """Gate chain: EVT:STRATEGY_SIGNAL_PRODUCED -> TRADE_INTENT_PROPOSED."""
        try:
            pld = event.pld
            if not isinstance(pld, dict):
                self.logger.warning(
                    "STRATEGY_SIGNAL_PRODUCED: invalid payload")
                return
            strategy_id = pld.get("strategy_id")
            symbol = pld.get("symbol")
            side = pld.get("side")
            rid = pld.get("rid") or f"sig-{uuid.uuid4()}"
            why_chain = pld.get("why_chain") or []
            signal_tpsl_owner_ctx = pld.get("tpsl_owner_ctx")
            tf_sec = pld.get("tf_sec")
            if tf_sec is not None:
                try:
                    tf_sec = int(tf_sec)
                except (ValueError, TypeError):
                    tf_sec = None
            if not strategy_id or not symbol or not side:
                self.logger.warning(
                    "STRATEGY_SIGNAL_PRODUCED: missing strategy_id/symbol/side")
                return
            side = str(side).upper()
            strategy_id_s = str(strategy_id)
            intent_kind = str(pld.get("intent_kind") or "ENTRY").upper()
            is_reduce_path = strategy_id_s == "md_amr" and intent_kind in (
                "FULL_CLOSE", "PARTIAL_CLOSE")

            # === CANONICAL TIME NORMALIZATION (DM-TTL-NORMALIZATION-PACK-R1) ===
            raw_ts = pld.get("ts_ms")
            if raw_ts in (None, 0, "0", ""):
                if is_reduce_path:
                    # Risk-reducing actions bypass mandatory producer timestamps.
                    pld["ts_ms"] = self._clock.now_ms()
                else:
                    self._reject(symbol=symbol, strategy_id=strategy_id_s, side=side, rid=rid, reason_code="MISSING_TS_MS",
                                 reason="DECISION", context="strategy_signal_gateway:ts_ms_missing", why_chain=why_chain)
                    return
            else:
                try:
                    norm_ts = float(raw_ts)
                    if not (norm_ts > 0):
                        raise ValueError(
                            f"ts_ms must be positive, got {raw_ts}")
                    # Convert seconds to milliseconds
                    if norm_ts < 1_000_000_000_000:
                        norm_ts *= 1000.0
                    pld["ts_ms"] = int(norm_ts)
                except Exception as e:
                    self._reject(symbol=symbol, strategy_id=strategy_id_s, side=side, rid=rid, reason_code="INVALID_TS_MS",
                                 reason="DECISION", context=f"strategy_signal_gateway:ts_ms_invalid:{e}", why_chain=why_chain)
                    return

            md_amr_trace_norm: dict[str, Any] | None = None
            objective_trace_norm: dict[str, Any] | None = None
            scoring = pld.get("scoring") if isinstance(
                pld.get("scoring"), dict) else None
            if strategy_id_s == "md_amr":
                valid_trace, trace_info = self._validate_md_amr_trace(
                    pld.get("trace"))
                if not valid_trace:
                    self._reject(
                        symbol=symbol,
                        strategy_id=strategy_id_s,
                        side=side,
                        rid=rid,
                        reason_code="WAL_TRACE_INVALID",
                        reason="DECISION",
                        context="strategy_signal_gateway:md_amr_trace_invalid",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + ["wal_trace_invalid"],
                        details=trace_info,
                    )
                    return
                md_amr_trace_norm = trace_info.get("normalized")
                objective_trace_norm = md_amr_trace_norm.get(
                    "objective") if isinstance(md_amr_trace_norm, dict) else None
                if isinstance(scoring, dict) and scoring.get("objective") is not None:
                    valid_objective, objective_info = self._validate_objective_trace(
                        scoring.get("objective"))
                    if not valid_objective:
                        self._reject(
                            symbol=symbol,
                            strategy_id=strategy_id_s,
                            side=side,
                            rid=rid,
                            reason_code="WAL_TRACE_INVALID",
                            reason="DECISION",
                            context="strategy_signal_gateway:md_amr_objective_invalid",
                            why_chain=(why_chain if isinstance(
                                why_chain, list) else []) + ["objective_invalid"],
                            details=objective_info,
                        )
                        return
                    objective_trace_norm = objective_info.get("normalized")
                if intent_kind not in ("ENTRY", "FULL_CLOSE", "PARTIAL_CLOSE"):
                    self._reject(
                        symbol=symbol,
                        strategy_id=strategy_id_s,
                        side=side,
                        rid=rid,
                        reason_code="WAL_TRACE_INVALID",
                        reason="DECISION",
                        context=f"strategy_signal_gateway:md_amr_invalid_intent_kind:{intent_kind}",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + ["invalid_intent_kind"],
                        details={"intent_kind": intent_kind},
                    )
                    return
            elif strategy_id_s in {"aurora", "mean_reversion"}:
                if isinstance(scoring, dict) and scoring.get("objective") is not None:
                    valid_objective, objective_info = self._validate_objective_trace(
                        scoring.get("objective"))
                    if not valid_objective:
                        self._reject(
                            symbol=symbol,
                            strategy_id=strategy_id_s,
                            side=side,
                            rid=rid,
                            reason_code="WAL_TRACE_INVALID",
                            reason="DECISION",
                            context=f"strategy_signal_gateway:{strategy_id_s}_objective_invalid",
                            why_chain=(why_chain if isinstance(
                                why_chain, list) else []) + ["objective_invalid"],
                            details=objective_info,
                        )
                        return
                    objective_trace_norm = objective_info.get("normalized")
            self.logger.info(
                f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: Processing {side} signal rid={rid} strategy_id={strategy_id}")
            dm = self._dm

            # === READINESS CONTRACT (v7) ===
            readiness = pld.get("readiness")
            runtime_permissions = pld.get("runtime_permissions")
            if not isinstance(readiness, dict):
                self._reject(
                    symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                    reason_code="READINESS_MISSING", reason="READINESS",
                    context="strategy_signal_gateway:readiness_missing",
                    why_chain=why_chain, details={"required": "readiness.warmup_ok"})
                return
            allow_manage_existing_without_warmup = (
                is_reduce_path
                and isinstance(runtime_permissions, dict)
                and runtime_permissions.get("can_manage_existing_risk") is True
                and runtime_permissions.get("can_open_new_risk") is False
            )
            if readiness.get("warmup_ok") is not True and not allow_manage_existing_without_warmup:
                self._reject(
                    symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                    reason_code="READINESS_WARMUP_NOT_OK", reason="READINESS",
                    context="strategy_signal_gateway:readiness_warmup_not_ok",
                    why_chain=why_chain, details={"warmup_ok": readiness.get("warmup_ok")})
                return
            if isinstance(runtime_permissions, dict):
                if is_reduce_path and runtime_permissions.get("can_manage_existing_risk") is False:
                    self._reject(
                        symbol=symbol,
                        strategy_id=strategy_id,
                        side=side,
                        rid=rid,
                        reason_code="READINESS_MANAGE_EXISTING_RISK_NOT_ALLOWED",
                        reason="READINESS",
                        context="strategy_signal_gateway:manage_existing_risk_not_allowed",
                        why_chain=(why_chain if isinstance(why_chain, list) else [
                        ]) + ["manage_existing_risk_not_allowed"],
                        details={"runtime_permissions": runtime_permissions},
                    )
                    return
                if (not is_reduce_path) and runtime_permissions.get("can_open_new_risk") is False:
                    self._reject(
                        symbol=symbol,
                        strategy_id=strategy_id,
                        side=side,
                        rid=rid,
                        reason_code="READINESS_OPEN_NEW_RISK_NOT_ALLOWED",
                        reason="READINESS",
                        context="strategy_signal_gateway:open_new_risk_not_allowed",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + ["open_new_risk_not_allowed"],
                        details={"runtime_permissions": runtime_permissions},
                    )
                    return

            # Arbitration moved to GateChain (Package 4, Slice 4.3)
            if strategy_id_s == "md_amr" and intent_kind in ("FULL_CLOSE", "PARTIAL_CLOSE"):
                exit_reason = str(pld.get("exit_reason_code") or "MD_AMR_EXIT")
                strategy_trace_payload = None
                if md_amr_trace_norm or objective_trace_norm:
                    strategy_trace_payload = {}
                    if md_amr_trace_norm:
                        strategy_trace_payload["md_amr"] = md_amr_trace_norm
                    if objective_trace_norm:
                        strategy_trace_payload["objective"] = objective_trace_norm
                if intent_kind == "FULL_CLOSE":
                    emitted = dm._emit_reduce_only_close(
                        symbol=symbol,
                        reason=exit_reason,
                        rid=str(rid),
                        strategy_id=str(strategy_id_s),
                        strategy_trace=strategy_trace_payload,
                    )
                    if not emitted:
                        self._reject(
                            symbol=symbol,
                            strategy_id=strategy_id_s,
                            side=side,
                            rid=rid,
                            reason_code="NO_POSITION_FOR_CLOSE",
                            reason="DECISION",
                            context="strategy_signal_gateway:md_amr_full_close_no_position",
                            why_chain=(why_chain if isinstance(
                                why_chain, list) else []) + [exit_reason],
                        )
                    return

                qty_signed, _curr = dm._get_portfolio_position_qty_signed(
                    symbol)
                if qty_signed is None or abs(qty_signed) < decimal.Decimal("1e-9"):
                    self._reject(
                        symbol=symbol,
                        strategy_id=strategy_id_s,
                        side=side,
                        rid=rid,
                        reason_code="NO_POSITION_FOR_SCALEOUT",
                        reason="DECISION",
                        context="strategy_signal_gateway:md_amr_partial_close_no_position",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + [exit_reason],
                    )
                    return

                scaleout_fraction_raw = pld.get("scaleout_fraction")
                try:
                    scaleout_fraction = float(scaleout_fraction_raw)
                except Exception:
                    scaleout_fraction = 0.0
                if not (0.0 < scaleout_fraction <= 1.0):
                    self._reject(
                        symbol=symbol,
                        strategy_id=strategy_id_s,
                        side=side,
                        rid=rid,
                        reason_code="WAL_TRACE_INVALID",
                        reason="DECISION",
                        context="strategy_signal_gateway:md_amr_partial_close_invalid_fraction",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + ["invalid_scaleout_fraction"],
                        details={"scaleout_fraction": scaleout_fraction_raw},
                    )
                    return

                close_side = "SELL" if qty_signed > 0 else "BUY"
                close_qty = abs(qty_signed) * \
                    decimal.Decimal(str(scaleout_fraction))
                if close_qty <= decimal.Decimal("1e-9"):
                    self._reject(
                        symbol=symbol,
                        strategy_id=strategy_id_s,
                        side=side,
                        rid=rid,
                        reason_code="NO_POSITION_FOR_SCALEOUT",
                        reason="DECISION",
                        context="strategy_signal_gateway:md_amr_partial_close_zero_qty",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + [exit_reason],
                    )
                    return

                timestamp_ms = pld["ts_ms"]

                dm._propose_trade_intent(
                    symbol=symbol,
                    side=close_side,
                    qty=decimal.Decimal(str(close_qty)),
                    price=decimal.Decimal("0"),
                    why_chain=(why_chain if isinstance(why_chain, list)
                               else []) + [exit_reason, "md_amr_partial_close"],
                    rid=str(rid),
                    reduce_only=True,
                    strategy_id=str(strategy_id_s),
                    decision_ts_ms=timestamp_ms,
                    strategy_trace=strategy_trace_payload,
                )
                return

            # === GATE CHAIN (Package 4, Slice 4.3) ===
            # Canonical pre-intent gate pipeline.
            # Ordering: arbitration → risk_skew_pre → risk → risk_skew_post →
            #           flip → qos → exposure → ttl → warmup → safety
            gate_ctx = GateContext(
                symbol=symbol,
                strategy_id=strategy_id_s,
                side=side,
                rid=rid,
                pld=pld,
                config=self.config,
                clock=self._clock,
                dm=dm,
                symbol_states=dm.symbol_states,
                why_chain=why_chain if isinstance(why_chain, list) else [],
                ts_ms=pld["ts_ms"],
                tf_sec=tf_sec,
                is_reduce_path=False,
            )
            chain = GateChain([
                arbitration_gate.check,
                risk_skew_gate.check_pre_risk,
                risk_gate.check,
                risk_skew_gate.check_post_risk,
                flip_gate.check,
                qos_gate.check,
                exposure_gate.check,
                ttl_gate.check,
                warmup_gate.check,
                safety_gate.check,
            ])
            chain_result = chain.run(gate_ctx)

            self._emit_gate_chain_trace(
                symbol=symbol,
                strategy_id=strategy_id_s,
                rid=rid,
                ts_ms=pld["ts_ms"],
                chain_result=chain_result
            )

            if not chain_result.passed:
                self._dispatch_gate_result(
                    chain_result, gate_ctx, pld, why_chain,
                    strategy_id=strategy_id, side=side)
                return

            # === ALL GATES PASSED ===
            self.logger.info(
                f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: All gates passed, emitting TRADE_INTENT_PROPOSED")
            signal_ts_ms = pld["ts_ms"]
            timestamp_ms = signal_ts_ms

            # Extract accumulated data from gate context
            qty_dec = gate_ctx.accumulated["qty_dec"]
            entry_price_dec = gate_ctx.accumulated["entry_price_dec"]
            why_sizing = gate_ctx.accumulated.get("why_sizing", "")
            price_ctx = gate_ctx.accumulated.get("price_ctx", {})
            qos_enabled = gate_ctx.accumulated.get("_qos_enabled", False)
            latest_risk = gate_ctx.accumulated.get(
                "latest_risk", dm.symbol_states[symbol].get("risk") or {})


            if isinstance(why_chain, list):
                why_chain.append(str(why_sizing))

            # Entry prices (Strategy Primacy + EntryPlan fallback)
            stop_price, target_price, ep_trace = resolve_strategy_entry_prices(
                symbol=symbol, strategy_id=str(strategy_id),
                side=side, rid=rid, price_ctx=price_ctx, pld=pld,
                entry_price_dec=entry_price_dec, why_chain=why_chain,
                config=self.config, logger=self.logger, reject_fn=self._reject)
            if stop_price == "REJECT":
                return
            resolved_tpsl_owner_ctx = resolve_gateway_tpsl_owner_ctx(
                signal_tpsl_owner_ctx,
                ep_trace,
            )
            if resolved_tpsl_owner_ctx is not None:
                self.logger.info(
                    "[%s] TPSL_OWNER_RESOLVED intended=%s final=%s reason=%s",
                    symbol,
                    resolved_tpsl_owner_ctx.get("intended_owner"),
                    resolved_tpsl_owner_ctx.get("final_owner"),
                    resolved_tpsl_owner_ctx.get("owner_loss_reason"),
                )

            # TCA/Risk from latest_risk
            tca = latest_risk.get("tca_budget") or {}
            max_slip = int(tca.get("max_slippage_bps", 0)) or None
            max_lat = int(tca.get("max_latency_ms", 0)) or None
            risk_val = float(
                (latest_risk.get("risk_parameters") or {}).get("risk_score", 0.0))

            # Dispatch through facade (safety gates already ran in chain)
            dm._propose_trade_intent(
                symbol=symbol, side=side,
                qty=decimal.Decimal(str(qty_dec)), price=entry_price_dec,
                why_chain=why_chain if isinstance(why_chain, list) else [
                    str(why_chain)],
                rid=rid, reduce_only=False, strategy_id=str(strategy_id),
                decision_ts_ms=timestamp_ms,
                stop_price=stop_price, target_price=target_price,
                entry_plan_trace=ep_trace, tf_sec=tf_sec,
                max_slippage_bps=max_slip, max_latency_ms=max_lat,
                risk_score=risk_val,
                tpsl_owner_ctx=resolved_tpsl_owner_ctx,
                safety_gate_result=gate_ctx.accumulated.get("safety_gate_result"),
                strategy_trace=(
                    {
                        **({"md_amr": md_amr_trace_norm} if md_amr_trace_norm else {}),
                        **({"objective": objective_trace_norm} if objective_trace_norm else {}),
                    } or None
                ))
            if qos_enabled:
                dm._update_qos_state(symbol, strategy_id)

        except ConfigContractError as e:
            reason = normalize_config_error(e)
            nrr_code = NormalizedRejectReasons.CONFIG_CONTRACT_MISSING
            if "CFG_INVALID" in reason:
                nrr_code = NormalizedRejectReasons.CONFIG_CONTRACT_INVALID
            caught_sym = e.symbol or symbol
            inc_config_contract_violation(
                path=e.path or "unknown", symbol=caught_sym or "unknown")
            self.logger.critical(
                f"[{caught_sym or 'unknown'}] CONFIG BLOCK: {reason} - {e.why}")
            if caught_sym:
                self._block(caught_sym)
            self._dm._emit_trade_intent_rejected(
                symbol=caught_sym or "unknown",
                strategy_id=str(strategy_id), side=side,
                rid=str(rid), reason_code=nrr_code, reason=reason,
                context="strategy_signal_gateway:config_contract_violation",
                details={"path": e.path, "why": e.why,
                         "stage": "strategy_signal_gateway"},
                why_chain=why_chain or ["config_contract_violation"])
        except Exception as e:
            self.logger.error(
                f"STRATEGY_SIGNAL_GATEWAY error: {e}", exc_info=True)

    def _dispatch_gate_result(
        self, chain_result, gate_ctx, pld, why_chain, *,
        strategy_id, side,
    ) -> None:
        """Map a non-PASS GateChainResult to _reject / _defer / _block."""
        result = chain_result.terminal_result
        symbol = gate_ctx.symbol
        rid = gate_ctx.rid
        dm = self._dm

        # Merge gate-level why_extra into why_chain
        effective_why = (list(why_chain) if isinstance(why_chain, list) else []) + list(result.why_extra)

        if result.outcome == GateOutcome.BLOCK:
            self._block(symbol)
            return

        if result.outcome == GateOutcome.REJECT:
            # Safety gate denials need special trace emission
            if result.gate_name == "safety":
                sg = gate_ctx.accumulated.get("safety_gate_result")
                if sg and sg.outcome == "DENY":
                    dm._handle_safety_deny(
                        symbol, side, rid, why_chain, sg,
                        strategy_id=str(strategy_id))
                    return
                if sg and sg.outcome == "CONFIG_ERROR":
                    dm._emit_trade_intent_rejected(
                        symbol=symbol, strategy_id=str(strategy_id),
                        side=str(side), rid=str(rid),
                        reason_code=NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING,
                        reason="DECISION",
                        context=sg.config_error_context or "safety_gates config error",
                        why_chain=why_chain)
                    dm._record_blocked_intent(symbol)
                    return
            self._reject(
                symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                reason_code=result.reason_code,
                reason=result.reason or "DECISION",
                context=result.context,
                why_chain=effective_why,
                details=result.details,
            )
            return

        if result.outcome == GateOutcome.DEFER:
            now_ms = self._clock.now_ms()
            cu = result.context_update or {}

            # Compute next_ts from gate-specific context_update
            if "_defer_next_ts" in cu:
                next_ts = int(cu["_defer_next_ts"])
            elif "_defer_retry_sec" in cu:
                next_ts = now_ms + int(float(cu["_defer_retry_sec"]) * 1000)
            elif "_defer_cooldown_sec" in cu:
                next_ts = now_ms + int(float(cu["_defer_cooldown_sec"]) * 1000)
            elif "_defer_stale_ttl" in cu:
                next_ts = now_ms + int(float(cu["_defer_stale_ttl"]) * 1000)
            else:
                next_ts = now_ms + 500  # default 500ms

            attempt = cu.get("_defer_attempt", 1)
            max_attempts = cu.get("_defer_max_attempts", None)

            # Gate-specific retry key prefix
            prefix = str(strategy_id)
            if result.gate_name == "qos":
                prefix = f"{strategy_id}:qos"

            self._defer(
                symbol=symbol,
                reason=result.reason_code,
                retry_key=self._rk(
                    prefix=prefix, symbol=symbol,
                    rid=rid, side=side, ts_ms=pld.get("ts_ms")),
                next_ts=next_ts,
                pld=pld,
                why_chain=effective_why,
                context=result.context,
                attempt=attempt,
                max_attempts=max_attempts,
            )
