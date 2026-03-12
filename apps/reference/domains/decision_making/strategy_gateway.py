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
            raise ValueError(f"domains.decision_making.risk_skew.{key} required (SSOT)")
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
                strat_cfg = getattr(self.config.strategies, str(strategy_id), getattr(self.config.strategies, "aurora", None))
                max_attempts = int(getattr(strat_cfg.decision, "retry_max_count", 5))
            except Exception:
                max_attempts = 5
                
        now_ms = self._clock.now_ms()
        if attempt > 1 and next_ts > now_ms:
            base_delay = next_ts - now_ms
            try:
                strategy_id = pld.get("strategy_id", "aurora")
                strat_cfg = getattr(self.config.strategies, str(strategy_id), getattr(self.config.strategies, "aurora", None))
                factor = float(getattr(strat_cfg.decision, "retry_backoff_factor", 2.0))
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

    def _validate_md_amr_trace(self, trace: Any) -> tuple[bool, dict[str, Any]]:
        required = ["dir_score", "thr_buy", "thr_sell", "w_raw", "w_norm", "qty_base", "qty_new", "conf_ratio"]
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
            missing_weights = [key for key in weight_keys if key not in weight_block]
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
            valid_objective, objective_info = self._validate_objective_trace(trace.get("objective"))
            if not valid_objective:
                return False, {"error": "objective_invalid", "details": objective_info}
            normalized["objective"] = objective_info["normalized"]

        for optional_key in ("atr_zscore", "bias", "dir_components"):
            if optional_key in trace:
                normalized[optional_key] = trace.get(optional_key)
        return True, {"normalized": normalized}

    def _validate_objective_trace(self, trace: Any) -> tuple[bool, dict[str, Any]]:
        required = ["trace_id", "multiplier", "objective_score", "components", "raw_metrics"]
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
                self.logger.warning("STRATEGY_SIGNAL_PRODUCED: invalid payload")
                return
            strategy_id = pld.get("strategy_id")
            symbol = pld.get("symbol")
            side = pld.get("side")
            rid = pld.get("rid") or f"sig-{uuid.uuid4()}"
            why_chain = pld.get("why_chain") or []
            tf_sec = pld.get("tf_sec")
            if tf_sec is not None:
                try:
                    tf_sec = int(tf_sec)
                except (ValueError, TypeError):
                    tf_sec = None
            if not strategy_id or not symbol or not side:
                self.logger.warning("STRATEGY_SIGNAL_PRODUCED: missing strategy_id/symbol/side")
                return
            side = str(side).upper()
            if side not in ("BUY", "SELL"):
                self.logger.warning(f"[{symbol}] GATEWAY: invalid side={side!r}")
                return
            strategy_id_s = str(strategy_id)
            intent_kind = str(pld.get("intent_kind") or "ENTRY").upper()
            md_amr_trace_norm: dict[str, Any] | None = None
            objective_trace_norm: dict[str, Any] | None = None
            scoring = pld.get("scoring") if isinstance(pld.get("scoring"), dict) else None
            if strategy_id_s == "md_amr":
                valid_trace, trace_info = self._validate_md_amr_trace(pld.get("trace"))
                if not valid_trace:
                    self._reject(
                        symbol=symbol,
                        strategy_id=strategy_id_s,
                        side=side,
                        rid=rid,
                        reason_code="WAL_TRACE_INVALID",
                        reason="DECISION",
                        context="strategy_signal_gateway:md_amr_trace_invalid",
                        why_chain=(why_chain if isinstance(why_chain, list) else []) + ["wal_trace_invalid"],
                        details=trace_info,
                    )
                    return
                md_amr_trace_norm = trace_info.get("normalized")
                objective_trace_norm = md_amr_trace_norm.get("objective") if isinstance(md_amr_trace_norm, dict) else None
                if isinstance(scoring, dict) and scoring.get("objective") is not None:
                    valid_objective, objective_info = self._validate_objective_trace(scoring.get("objective"))
                    if not valid_objective:
                        self._reject(
                            symbol=symbol,
                            strategy_id=strategy_id_s,
                            side=side,
                            rid=rid,
                            reason_code="WAL_TRACE_INVALID",
                            reason="DECISION",
                            context="strategy_signal_gateway:md_amr_objective_invalid",
                            why_chain=(why_chain if isinstance(why_chain, list) else []) + ["objective_invalid"],
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
                        why_chain=(why_chain if isinstance(why_chain, list) else []) + ["invalid_intent_kind"],
                        details={"intent_kind": intent_kind},
                    )
                    return
            elif strategy_id_s in {"aurora", "mean_reversion"}:
                if isinstance(scoring, dict) and scoring.get("objective") is not None:
                    valid_objective, objective_info = self._validate_objective_trace(scoring.get("objective"))
                    if not valid_objective:
                        self._reject(
                            symbol=symbol,
                            strategy_id=strategy_id_s,
                            side=side,
                            rid=rid,
                            reason_code="WAL_TRACE_INVALID",
                            reason="DECISION",
                            context=f"strategy_signal_gateway:{strategy_id_s}_objective_invalid",
                            why_chain=(why_chain if isinstance(why_chain, list) else []) + ["objective_invalid"],
                            details=objective_info,
                        )
                        return
                    objective_trace_norm = objective_info.get("normalized")
            self.logger.info(f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: Processing {side} signal rid={rid} strategy_id={strategy_id}")
            dm = self._dm

            # === READINESS CONTRACT (v7) ===
            readiness = pld.get("readiness")
            runtime_permissions = pld.get("runtime_permissions")
            is_reduce_path = strategy_id_s == "md_amr" and intent_kind in ("FULL_CLOSE", "PARTIAL_CLOSE")
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
                        why_chain=(why_chain if isinstance(why_chain, list) else []) + ["manage_existing_risk_not_allowed"],
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
                        why_chain=(why_chain if isinstance(why_chain, list) else []) + ["open_new_risk_not_allowed"],
                        details={"runtime_permissions": runtime_permissions},
                    )
                    return

            # === GATE 0: STRATEGY ARBITRATION ===
            arb = dm._check_strategy_arbitration(
                symbol, str(strategy_id),
                ts_ms=int(pld["ts_ms"]) if pld.get("ts_ms") is not None else None,
                commit=True)
            if not arb["allowed"]:
                self._reject(
                    symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                    reason_code="ARBITRATION_BLOCKED", reason="ARBITRATION",
                    context="strategy_signal_gateway:arbitration",
                    why_chain=why_chain,
                    details={"arbitration_reason": arb.get("reason")})
                return

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
                            why_chain=(why_chain if isinstance(why_chain, list) else []) + [exit_reason],
                        )
                    return

                qty_signed, _curr = dm._get_portfolio_position_qty_signed(symbol)
                if qty_signed is None or abs(qty_signed) < decimal.Decimal("1e-9"):
                    self._reject(
                        symbol=symbol,
                        strategy_id=strategy_id_s,
                        side=side,
                        rid=rid,
                        reason_code="NO_POSITION_FOR_SCALEOUT",
                        reason="DECISION",
                        context="strategy_signal_gateway:md_amr_partial_close_no_position",
                        why_chain=(why_chain if isinstance(why_chain, list) else []) + [exit_reason],
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
                        why_chain=(why_chain if isinstance(why_chain, list) else []) + ["invalid_scaleout_fraction"],
                        details={"scaleout_fraction": scaleout_fraction_raw},
                    )
                    return

                close_side = "SELL" if qty_signed > 0 else "BUY"
                close_qty = abs(qty_signed) * decimal.Decimal(str(scaleout_fraction))
                if close_qty <= decimal.Decimal("1e-9"):
                    self._reject(
                        symbol=symbol,
                        strategy_id=strategy_id_s,
                        side=side,
                        rid=rid,
                        reason_code="NO_POSITION_FOR_SCALEOUT",
                        reason="DECISION",
                        context="strategy_signal_gateway:md_amr_partial_close_zero_qty",
                        why_chain=(why_chain if isinstance(why_chain, list) else []) + [exit_reason],
                    )
                    return

                ts_ms = pld.get("ts_ms")
                if ts_ms in (None, 0, "0", ""):
                    timestamp_ms = self._clock.now_ms()
                else:
                    timestamp_ms = int(ts_ms)
                    if 0 < timestamp_ms < 1_000_000_000_000:
                        timestamp_ms *= 1000

                dm._propose_trade_intent(
                    symbol=symbol,
                    side=close_side,
                    qty=decimal.Decimal(str(close_qty)),
                    price=decimal.Decimal("0"),
                    why_chain=(why_chain if isinstance(why_chain, list) else []) + [exit_reason, "md_amr_partial_close"],
                    rid=str(rid),
                    reduce_only=True,
                    strategy_id=str(strategy_id_s),
                    decision_ts_ms=timestamp_ms,
                    strategy_trace=strategy_trace_payload,
                )
                return

            # Risk-skew until_refresh guard
            guard = dm.symbol_states[symbol].get("risk_skew_guard") or {}
            if guard.get("until_refresh"):
                self.logger.error(f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: NO_TRADE_UNTIL_REFRESH (risk_skew_guard active)")
                retry_sec = self._rscfg("until_refresh_retry_sec")
                now_ms = self._clock.now_ms()
                self._defer(
                    symbol=symbol, reason="NRR-RISK-SKEW-UNTIL-REFRESH",
                    retry_key=self._rk(
                        prefix=str(strategy_id), symbol=symbol,
                        rid=rid, side=side, ts_ms=pld.get("ts_ms")),
                    next_ts=now_ms + int(retry_sec * 1000), pld=pld,
                    why_chain=(why_chain or []) + ["NO_TRADE_UNTIL_REFRESH", "risk_skew_guard"],
                    context="strategy_signal_gateway:risk_skew_until_refresh")
                return

            # === GATE 1: RISK GATE ===
            latest_risk = dm.symbol_states[symbol].get("risk")
            if not latest_risk:
                self._defer(
                    symbol=symbol, reason="NRR-DATA-NOT-READY",
                    retry_key=self._rk(
                        prefix=str(strategy_id), symbol=symbol,
                        rid=rid, side=side, ts_ms=pld.get("ts_ms")),
                    next_ts=self._clock.now_ms() + 500, pld=pld,
                    why_chain=(why_chain or []) + ["missing:risk", "fail_closed"],
                    context="strategy_signal_gateway:risk_not_ready")
                return
            risk_params = latest_risk.get("risk_parameters") or {}
            is_allowed = risk_params.get("is_trading_allowed", True)
            risk_score_raw = risk_params.get("risk_score")
            if risk_score_raw is None:
                self.logger.warning(f"[{symbol}] RISK_SCORE_MISSING: risk_score is None, deferring signal rid={rid}")
                self._defer(
                    symbol=symbol, reason="RISK_SCORE_MISSING",
                    retry_key=self._rk(
                        prefix=str(strategy_id), symbol=symbol,
                        rid=rid, side=side, ts_ms=pld.get("ts_ms")),
                    next_ts=self._clock.now_ms() + 500, pld=pld,
                    why_chain=(why_chain or []) + ["missing:risk_score", "fail_closed"],
                    context="strategy_signal_gateway:risk_score_missing")
                return
            try:
                risk_score = float(risk_score_raw)
            except Exception:
                self._defer(
                    symbol=symbol, reason="RISK_SCORE_INVALID",
                    retry_key=self._rk(
                        prefix=str(strategy_id), symbol=symbol,
                        rid=rid, side=side, ts_ms=pld.get("ts_ms")),
                    next_ts=self._clock.now_ms() + 500, pld=pld,
                    why_chain=(why_chain or []) + ["invalid:risk_score", "fail_closed"],
                    context="strategy_signal_gateway:risk_score_invalid")
                return
            if not is_allowed:
                self._reject(
                    symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                    reason_code="RISK_TRADING_NOT_ALLOWED", reason="RISK",
                    context="strategy_signal_gateway:risk_gate",
                    why_chain=why_chain, details={"is_trading_allowed": False})
                return
            # Risk score threshold (SSOT)
            used_override = False
            try:
                max_risk = float(self.config.domains.risk_management.trading_allowed_thresholds.max_risk_score)
                icfg = dm._get_aurora_instrument_cfg(symbol)
                mrs = icfg.max_risk_score if icfg is not None else None
                if mrs is not None and mrs.enabled:
                    max_risk = float(mrs.value)
                    used_override = True
            except Exception as e:
                self.logger.error(f"Config Contract Violation: {e}")
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid, reason_code="CONFIG_CONTRACT_ERROR", reason="DECISION", context=f"strategy_signal_gateway:risk_config_error:{e}", why_chain=why_chain)
                return
            if risk_score > max_risk:
                self.logger.warning(f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - risk_score {risk_score:.3f} > max {max_risk} used_override={used_override}")
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid, reason_code="RISK_SCORE_TOO_HIGH", reason="RISK", context=f"strategy_signal_gateway:risk_score_{risk_score:.3f}_gt_{max_risk}", why_chain=why_chain)
                return

            # === GATE 1.5: RISK SKEW + DEGRADED CONTEXT ===
            risk_ts = latest_risk.get("ts", 0)
            features_data = dm.symbol_states[symbol].get("features") or {}
            features_ts = features_data.get("ts", 0) if isinstance(features_data, dict) else 0
            if isinstance(features_data, dict):
                feats_pld = features_data.get("features") or {}
                if isinstance(feats_pld, dict):
                    ctx = create_decision_context(symbol, self._clock.now_ms(), feats_pld)
                    if dm._degraded_context_gate_should_defer(
                            symbol=symbol, rid=rid, ctx=ctx,
                            features_evt=features_data, strategy_id=str(strategy_id)):
                        return
            if risk_ts > 0 and features_ts > 0:
                if self._handle_risk_skew(
                        symbol=symbol, strategy_id=str(strategy_id),
                        side=side, rid=rid, pld=pld, why_chain=why_chain,
                        risk_ts=risk_ts, features_ts=features_ts):
                    return

            # === GATE 2: FLIP GATE ===
            flip_result = dm._handle_flip_orchestration(
                symbol=symbol, intent_side=side, original_pld=pld, source=str(strategy_id))
            if flip_result:
                if flip_result == "NRR-PORTFOLIO-UNKNOWN":
                    stale_ttl = self.config.domains.position_tracking.positions_stale_ttl_sec
                    if stale_ttl is None:
                        raise ValueError("positions_stale_ttl_sec required (SSOT)")
                    self._defer(
                        symbol=symbol, reason="NRR-PORTFOLIO-UNKNOWN",
                        retry_key=self._rk(
                            prefix=str(strategy_id), symbol=symbol,
                            rid=rid, side=side, ts_ms=pld.get("ts_ms")),
                        next_ts=self._clock.now_ms() + int(stale_ttl * 1000), pld=pld,
                        why_chain=(why_chain or []) + ["portfolio_unknown", "fail_closed"],
                        context="strategy_gateway_flip_check")
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid, reason_code="FLIP_GATE_UNKNOWN", reason="DECISION", context="strategy_signal_gateway:flip_unknown_state", why_chain=why_chain)
                return

            # === GATE 3: QOS GATE ===
            qos_enabled = dm._qos_enabled_for_strategy(str(strategy_id))
            if qos_enabled:
                qos_ok, qos_reason = dm._qos_allow(symbol, strategy_id=str(strategy_id))
                if not qos_ok:
                    mode = dm.qos_mode
                    if dm.qos_enforce and mode == "defer":
                        mode = "enforce"
                    if mode == "shadow":
                        self.logger.warning(f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: QoS shadow (reason: {qos_reason})")
                    elif mode == "defer":
                        next_ts = int(dm._calculate_next_allowed_time(symbol, strategy_id=str(strategy_id)))
                        self._defer(
                            symbol=symbol, reason=str(qos_reason or "qos_defer"),
                            retry_key=self._rk(
                                prefix=f"{strategy_id}:qos", symbol=symbol,
                                rid=rid, side=side, ts_ms=pld.get("ts_ms")),
                            next_ts=next_ts, pld=pld,
                            why_chain=(why_chain or []) + ["qos", "defer"],
                            context="strategy_gateway_qos")
                        return
                    else:
                        self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid, reason_code="QOS_RATE_LIMIT", reason="QOS", context=f"strategy_signal_gateway:qos_rejected:{qos_reason}", why_chain=why_chain)
                        return

            # === GATE 4: EXPOSURE / SIZING ===
            price_ctx = pld.get("price_ctx") if isinstance(pld.get("price_ctx"), dict) else {}
            entry_price = price_ctx.get("entry_price")
            if entry_price in (None, "", "0", 0):
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid, reason_code="MISSING_ENTRY_PRICE", reason="DECISION", context="strategy_signal_gateway:entry_price_missing", why_chain=why_chain)
                return
            try:
                entry_price_dec = decimal.Decimal(str(entry_price))
            except Exception:
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid, reason_code="INVALID_ENTRY_PRICE", reason="DECISION", context="strategy_signal_gateway:entry_price_invalid", why_chain=why_chain)
                return
            if not dm.latest_portfolio:
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid, reason_code="LATEST_PORTFOLIO_MISSING", reason="DECISION", context="strategy_signal_gateway:latest_portfolio_missing", why_chain=why_chain)
                return
            sizing_ctx = {
                "portfolio": dm.latest_portfolio,
                "features": dm.symbol_states[symbol].get("features") if symbol in dm.symbol_states else {},
            }
            regime_name = None
            scoring = pld.get("scoring") if isinstance(pld.get("scoring"), dict) else None
            if isinstance(scoring, dict):
                regime_name = scoring.get("regime")
            margin_pct_mult = None
            if str(strategy_id) == "aurora" and regime_name:
                try:
                    icfg = dm._get_aurora_instrument_cfg(symbol)
                    rs = aget(icfg, "regime_sizing", None) if icfg else None
                    if isinstance(rs, dict) and rs:
                        mult_raw = rs.get(str(regime_name)) or rs.get("DEFAULT")
                        if mult_raw is not None:
                            margin_pct_mult = decimal.Decimal(str(mult_raw))
                except Exception:
                    pass
            # Phase 0.6: STRESS attenuation — reduce margin_pct_mult when policy=attenuate
            try:
                _stress_state = getattr(dm, "_system_stress_states", {}).get(symbol, "NORMAL")
                if _stress_state == "STRESS":
                    _strat_cfg = getattr(dm.config.strategies, str(strategy_id), None)
                    _sg_cfg = getattr(_strat_cfg, "safety_gates", None) if _strat_cfg else None
                    _policy = str(getattr(_sg_cfg, "system_stress_policy", "off"))
                    if _policy == "attenuate":
                        _factor = decimal.Decimal(str(getattr(_sg_cfg, "stress_attenuation_factor", "0.5")))
                        margin_pct_mult = (margin_pct_mult if margin_pct_mult is not None else decimal.Decimal("1")) * _factor
            except Exception:
                pass  # fail-open: attenuation errors must not block trades
                
            # PKG-3: Inception fractional sizing
            try:
                sizing_cfg = pld.get("sizing") if isinstance(pld.get("sizing"), dict) else None
                if sizing_cfg and "margin_pct_mult" in sizing_cfg:
                    _inception_factor = decimal.Decimal(str(sizing_cfg["margin_pct_mult"]))
                    margin_pct_mult = (margin_pct_mult if margin_pct_mult is not None else decimal.Decimal("1")) * _inception_factor
            except Exception:
                pass
            try:
                qty_dec, why_sizing, sizing_rej, _ = dm._calculate_position_size(
                    symbol, entry_price_dec, side, sizing_ctx, margin_pct_mult=margin_pct_mult)
            except Exception as e:
                self._reject(
                    symbol=symbol, strategy_id=strategy_id, side=side,
                    rid=rid, reason_code="SIZING_ERROR", reason="DECISION",
                    context=f"strategy_signal_gateway:sizing_exception:{type(e).__name__}",
                    why_chain=(why_chain or []) + ["sizing_exception"],
                    details={"error": str(e)})
                return
            if qty_dec is None:
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid, reason_code="SIZING_QTY_NONE", reason="DECISION", context="strategy_signal_gateway:sizing_qty_none", why_chain=why_chain)
                return
            if not dm._precheck_exposure_cache(symbol, side, float(qty_dec * entry_price_dec)):
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid, reason_code="EXPOSURE_PRECHECK_FAILED", reason="RISK", context="strategy_signal_gateway:exposure_precheck", why_chain=why_chain)
                return

            # === GATE 5: TTL GATE ===
            signal_ts_ms = pld.get("ts_ms", 0)
            if signal_ts_ms in (None, 0, "0", ""):
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid, reason_code="MISSING_TS_MS", reason="DECISION", context="strategy_signal_gateway:ts_ms_missing", why_chain=why_chain)
                return
            current_ms = self._clock.now_ms()
            tf_sec_val = int(pld.get("tf_sec") or 0)
            if tf_sec_val > 0:
                bar_ttl = tf_sec_val * 1000 * 2
                sys_md = getattr(self.config.system, "market_data", None)
                if sys_md:
                    bar_ttl = float(getattr(sys_md, "bar_ttl_ms", bar_ttl) or bar_ttl)
                ttl_ms = bar_ttl
            else:
                ttl_ms = dm.features_ttl_sec * 1000
            if current_ms - int(signal_ts_ms) > ttl_ms:
                self._reject(symbol=symbol, strategy_id=strategy_id, side=side, rid=rid, reason_code="SIGNAL_STALE", reason="DECISION", context=f"strategy_signal_gateway:signal_is_stale_ttl_{ttl_ms}ms", why_chain=why_chain)
                return

            # === GATE 6: WARMUP ===
            if dm._warmup_gate_before_trade_intent(
                    symbol=symbol, rid=rid, reduce_only=False,
                    context="strategy_signal_gateway:pre_emit"):
                return

            # === ALL GATES PASSED ===
            self.logger.info(f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: All gates passed, emitting TRADE_INTENT_PROPOSED")
            timestamp_ms = int(signal_ts_ms)
            if 0 < timestamp_ms < 1_000_000_000_000:
                timestamp_ms *= 1000
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

            # TCA/Risk from latest_risk
            tca = latest_risk.get("tca_budget") or {}
            max_slip = int(tca.get("max_slippage_bps", 0)) or None
            max_lat = int(tca.get("max_latency_ms", 0)) or None
            risk_val = float((latest_risk.get("risk_parameters") or {}).get("risk_score", 0.0))

            # Dispatch through facade (safety gates + intent builder)
            dm._propose_trade_intent(
                symbol=symbol, side=side,
                qty=decimal.Decimal(str(qty_dec)), price=entry_price_dec,
                why_chain=why_chain if isinstance(why_chain, list) else [str(why_chain)],
                rid=rid, reduce_only=False, strategy_id=str(strategy_id),
                decision_ts_ms=timestamp_ms,
                stop_price=stop_price, target_price=target_price,
                entry_plan_trace=ep_trace, tf_sec=tf_sec,
                max_slippage_bps=max_slip, max_latency_ms=max_lat,
                risk_score=risk_val,
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
            inc_config_contract_violation(path=e.path or "unknown", symbol=caught_sym or "unknown")
            self.logger.critical(f"[{caught_sym or 'unknown'}] CONFIG BLOCK: {reason} - {e.why}")
            if caught_sym:
                self._block(caught_sym)
            self._dm._emit_trade_intent_rejected(
                symbol=caught_sym or "unknown",
                strategy_id=str(strategy_id), side=side,
                rid=str(rid), reason_code=nrr_code, reason=reason,
                context="strategy_signal_gateway:config_contract_violation",
                details={"path": e.path, "why": e.why, "stage": "strategy_signal_gateway"},
                why_chain=why_chain or ["config_contract_violation"])
        except Exception as e:
            self.logger.error(f"STRATEGY_SIGNAL_GATEWAY error: {e}", exc_info=True)

    def _handle_risk_skew(
        self, *, symbol: str, strategy_id: str, side: str,
        rid: str, pld: dict, why_chain: list,
        risk_ts: int, features_ts: int,
    ) -> bool:
        """Return True if signal should be blocked/deferred."""
        skew_sec = abs(features_ts - risk_ts) / 1000
        max_skew = self._rscfg("max_skew_sec")
        if skew_sec <= max_skew:
            return False
        max_defer = self._rscfg("max_defer_count")
        now_ms = self._clock.now_ms()
        window_sec = self._rscfg("defer_window_sec")
        state = self._dm.symbol_states[symbol].setdefault(
            "risk_skew_guard",
            {"defer_count": 0, "window_start_ms": now_ms, "until_refresh": False})
        try:
            ws = int(state.get("window_start_ms", now_ms))
        except Exception:
            ws = now_ms
            state["window_start_ms"] = now_ms
        if now_ms - ws > int(window_sec * 1000):
            state["defer_count"] = 0
            state["window_start_ms"] = now_ms
        try:
            state["defer_count"] = int(state.get("defer_count", 0)) + 1
        except Exception:
            state["defer_count"] = 1
        dc = int(state.get("defer_count", 1))
        if dc >= max_defer:
            state["until_refresh"] = True
            self.logger.error(f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: NO_TRADE_UNTIL_REFRESH skew={skew_sec:.1f}s > max={max_skew}s ({dc}/{max_defer})")
        else:
            cooldown = self._rscfg("defer_cooldown_sec")
            self.logger.warning(f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: DEFER NRR-RISK-STALE skew={skew_sec:.1f}s > max={max_skew}s ({dc}/{max_defer})")
            self._defer(
                symbol=symbol, reason="NRR-RISK-STALE",
                retry_key=self._rk(prefix=strategy_id, symbol=symbol, rid=rid, side=side, ts_ms=pld.get("ts_ms")),
                next_ts=now_ms + int(cooldown * 1000), pld=pld,
                attempt=dc, max_attempts=max_defer,
                why_chain=(why_chain or []) + ["risk_skew", f"skew_sec:{skew_sec:.3f}", f"defer_count:{dc}"],
                context="strategy_signal_gateway:risk_skew")
        self._block(symbol)
        return True
