"""
Aurora Decision Processing Mixin.

Extracted from aurora_handler.py (Phase 14A Decomposition).

Provides:
  - _process_decision: Core scoring kernel invocation + gates
  - _emit_signal: EVT:STRATEGY_SIGNAL_PRODUCED payload builder
"""
from __future__ import annotations

import decimal
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from apps.reference.domains.decision_making.aurora_scoring_kernel import (
    AuroraScoringKernel,
    ScoringResult,
)
from apps.reference.domains.decision_making.quadratic_scoring_kernel import (
    QuadraticScoringKernel,
)
from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
from apps.reference.domains.decision_making.entry_plan import EntryPlanResult
from apps.reference.domains.decision_making.trade_intent_reject_wal import write_trade_intent_rejected
from apps.reference.domains.regime_allowlist.contract import RegimeAllowlistContract
from apps.reference.domains.decision_making.instrument_quantizer import (
    quantize_exposure,
    InstrumentSpec as QuantizerSpec,
)

if TYPE_CHECKING:
    from apps.reference.domains.decision_making.aurora_handler import SymbolState

logger = logging.getLogger("aurora_handler")


class AuroraDecisionMixin:
    """
    Mixin: core decision processing and signal emission for AuroraHandler.

    Self-attributes used (provided by AuroraHandler):
      - self.logger, self.config, self.emit_fn
      - self._symbol_states, self.strategy_id, self.timeframe_sec
      - self.scoring_kernel_cls, self._shield_fn
      - self.direction_strength_cfg, self.delta_price_cap_pct
      - self.signal_threshold, self.neutral_threshold, self.score_multiplier
      - self.blocked_regimes, self.vol_gates_enabled
      - self.execution_gate, self.exit_manager, self.entry_plan_calculator
      - self.holding_period_enabled, self.mode_manager, self.dashboard
      - self.monotonic_fn, self.wall_time_fn
      - Various helper methods from other mixins
    """

    def _process_decision(self, symbol: str, cmd: Dict[str, Any]) -> None:
        """
        Internal: Process decision logic after CMD:PROCESS_STRATEGY validation.

        This contains the core scoring kernel and signal emission logic.
        """
        # Check if symbol is enabled for Aurora
        if not self._is_symbol_enabled(symbol):
            return

        # Get instrument config
        instr_cfg = self._get_instrument_config(symbol)
        if not instr_cfg:
            return

        # Extract features and readiness from CMD payload
        features = cmd.get("features", {})
        warmup = cmd.get("warmup", {})
        warmup_readiness = warmup.get("ready", {})

        # Update warmup state
        state = self._symbol_states[symbol]
        state.warmup_full_ready = bool(warmup.get("full_ready", False))

        # Check warmup readiness (fail-closed)
        if not state.warmup_full_ready:
            mode = str(getattr(self, "_fe_warmup_enforcement_mode", "fail_fast"))
            if mode == "fail_fast":
                self.logger.debug(f"[{symbol}] Warmup not ready, skipping (mode=fail_fast)")
                write_trade_intent_rejected(
                    symbol=symbol,
                    tf_sec=int(cmd.get("tf_sec") or 0),
                    bar_close_ts=cmd.get("bar_close_ts"),
                    reason_code=NormalizedRejectReasons.FEATURES_NOT_READY,
                    stage="STRATEGY",
                    why="Warmup not full_ready (fail-closed; enforcement_mode=fail_fast)",
                    src="aurora_handler",
                    ts_ms=cmd.get("bar_close_ts"),
                    rid=cmd.get("rid"),
                )
                self._emit_strategy_blocked(
                    symbol=symbol,
                    reason_code="READINESS_FE_WARMUP_NOT_READY",
                    reason="READINESS",
                    context="aurora_handler:_process_decision",
                    details={"warmup_full_ready": False, "enforcement_mode": mode},
                    why_chain=["READINESS", "warmup_full_ready:false", f"enforcement_mode:{mode}"],
                )
                return

            # warn_only / disabled: allow decision processing to proceed in degraded mode
            self.logger.debug(
                f"[{symbol}] Warmup not ready, continuing (enforcement_mode={mode})"
            )

        # DM-CRITICAL-PATCHES-02: Regime liveness guard
        liveness_block = self._check_regime_liveness(symbol, state)
        if liveness_block is not None:
            write_trade_intent_rejected(
                symbol=symbol,
                tf_sec=int(cmd.get("tf_sec") or 0),
                bar_close_ts=cmd.get("bar_close_ts"),
                reason_code=liveness_block["reason_code"],
                stage="STRATEGY",
                why=liveness_block["why"],
                src="aurora_handler",
                ts_ms=cmd.get("bar_close_ts"),
                rid=cmd.get("rid"),
            )
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code=liveness_block["reason_code"],
                reason="LIVENESS",
                context="aurora_handler:regime_liveness_guard",
                details=liveness_block.get("details", {}),
                why_chain=["LIVENESS", liveness_block["reason_code"]],
            )
            return

        # Get price
        price = features.get("price")
        if price is None:
            self.logger.warning(f"[{symbol}] Missing price in features")
            return
        price_dec = decimal.Decimal(str(price))

        # Get config for this symbol
        signal_weights = self._get_signal_weights(symbol, instr_cfg)
        feature_neutrals = self._get_feature_neutrals(symbol, instr_cfg)
        essential_features = self._get_essential_features(symbol, instr_cfg)

        # === LIQUIDITY GATE (Score V2) ===
        liq_ok, liq_ctx = self._check_liquidity_gate(
            symbol=symbol,
            instr_cfg=instr_cfg,
            features=features,
            warmup_readiness=warmup_readiness,
        )
        if not liq_ok:
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code=str(liq_ctx.get("reason_code") or "LIQUIDITY_GATE_FAIL"),
                reason="LIQUIDITY",
                context="aurora_handler:liquidity_gate",
                details=liq_ctx,
                why_chain=[
                    "LIQUIDITY_GATE",
                    f"kappa={liq_ctx.get('kappa')}",
                    f"min={liq_ctx.get('kappa_min')}",
                ],
            )
            return

        # Build side bias state
        side_bias = self._get_side_bias_state(symbol)

        # === [SAFETY PATCH: ANCHOR SHOCK VETO (pre-check)] ===
        veto_cfg = None
        veto_anchor_symbol = "BTCUSDT"
        veto_threshold: float | None = None
        veto_macro_resid: float | None = None
        veto_applicable = False
        try:
            decision_cfg = getattr(self.config.strategies.aurora, "decision", None)
            veto_cfg = getattr(decision_cfg, "anchor_shock_veto", None) if decision_cfg else None
            if veto_cfg and getattr(veto_cfg, "enabled", False):
                veto_anchor_symbol = getattr(veto_cfg, "anchor_symbol", "BTCUSDT")
                veto_threshold = float(getattr(veto_cfg, "threshold", -2.0))
                veto_applicable = symbol != veto_anchor_symbol
                if veto_applicable:
                    macro_val = features.get("macro_resid")
                    if macro_val is not None:
                        veto_macro_resid = float(macro_val)
        except Exception as e:
            self.logger.warning(f"[{symbol}] Veto check warning: {e}")
            veto_cfg = None
            veto_threshold = None
            veto_macro_resid = None
            veto_applicable = False

        # === [PATCH: PER-SYMBOL THRESHOLD SUPPORT] ===
        effective_threshold = self.signal_threshold
        effective_neutral = self.neutral_threshold

        if instr_cfg:
            st_cfg = getattr(instr_cfg, "signal_threshold", None)

            if st_cfg is not None:
                if isinstance(st_cfg, (int, float)):
                    effective_threshold = decimal.Decimal(str(st_cfg))
                    self.logger.debug(f"[{symbol}] Using per-symbol threshold (direct): {effective_threshold}")
                elif hasattr(st_cfg, "enabled") and st_cfg.enabled:
                    if hasattr(st_cfg, "value") and st_cfg.value is not None:
                        effective_threshold = decimal.Decimal(str(st_cfg.value))
                        self.logger.debug(f"[{symbol}] Using per-symbol threshold (enabled): {effective_threshold}")

            nt_cfg = getattr(instr_cfg, "neutral_threshold", None)
            if nt_cfg is not None:
                if isinstance(nt_cfg, (int, float)):
                    effective_neutral = decimal.Decimal(str(nt_cfg))
                    self.logger.debug(f"[{symbol}] Using per-symbol neutral_threshold: {effective_neutral}")
                elif hasattr(nt_cfg, "value") and nt_cfg.value is not None:
                    effective_neutral = decimal.Decimal(str(nt_cfg.value))

        # Get current side for hysteresis
        current_side = state.last_signal_side

        # Call scoring kernel
        effective_regime_thresholds = self._get_regime_thresholds(symbol=symbol, instr_cfg=instr_cfg)

        extra_kwargs = {}
        if self.scoring_kernel_cls is QuadraticScoringKernel:
            extra_kwargs["shield_fn"] = self._shield_fn
            extra_kwargs["pillar_contribs"] = features.get("pillar_contribs", {})
            extra_kwargs["score_multiplier"] = getattr(self, "score_multiplier", 1.0)

        if "regime" not in features:
            features["regime"] = state.regime
        if "regime_ts_ms" not in features:
            features["regime_ts_ms"] = state.regime_ts_ms
        if "bar_close_ts" not in features:
            bar_close_ts_raw = cmd.get("bar_close_ts")
            if bar_close_ts_raw is not None:
                features["bar_close_ts"] = int(bar_close_ts_raw)

        _compute_kwargs = dict(
            symbol=symbol,
            features=features,
            warmup_readiness=warmup_readiness,
            price=price_dec,
            signal_weights=signal_weights,
            feature_neutrals=feature_neutrals,
            essential_features=essential_features,
            base_threshold=effective_threshold,
            regime_name=state.regime,
            regime_thresholds=effective_regime_thresholds,
            side_bias_state=side_bias,
            direction_strength_cfg=self.direction_strength_cfg,
            delta_price_cap_pct=self.delta_price_cap_pct,
            neutral_threshold=effective_neutral,
            current_side=current_side,
        )
        try:
            result = self.scoring_kernel_cls.compute(
                **_compute_kwargs,
                **extra_kwargs,
            )
        except Exception as _kernel_exc:
            if self.scoring_kernel_cls is QuadraticScoringKernel:
                self.logger.error(
                    "[%s] QUADRATIC_FALLBACK: %s — falling back to AuroraScoringKernel (local only)",
                    symbol, _kernel_exc,
                )
                try:
                    result = AuroraScoringKernel.compute(**_compute_kwargs)
                except Exception as _fallback_exc:
                    self.logger.error("[%s] FALLBACK ALSO FAILED: %s", symbol, _fallback_exc)
                    raise _fallback_exc from _kernel_exc
            else:
                raise

        # Handle result
        state.last_signal_side = result.side

        # Kernel visibility log
        _psi = result.psi_vector or {}
        self.logger.info(
            "[%s] KERNEL_DIAG: engine=%s s_linear=%.4f score=%.6f "
            "shield_mult=%.3f deferred=%s defer_reason=%s side=%s thr_buy=%s thr_sell=%s",
            symbol,
            _psi.get("scoring_engine", "?"),
            float(_psi.get("s_linear", 0.0)),
            float(result.score),
            float(result.shield_multiplier or 1.0),
            result.deferred,
            result.defer_reason or "-",
            result.side,
            result.thr_buy,
            result.thr_sell,
        )

        if result.deferred:
            self.logger.debug(f"[{symbol}] Kernel deferred: {result.defer_reason}")
            defer_reason = str(result.defer_reason or "UNKNOWN")
            reason_code = "AURORA_KERNEL_DEFERRED"
            reason = "READINESS"
            if (warmup_readiness.get("spread_bps") is False) or ("spread" in defer_reason.lower()):
                reason = "SPREAD"
                reason_code = "SPREAD_NOT_READY"
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code=reason_code,
                reason=reason,
                context="aurora_handler:kernel_deferred",
                details={"defer_reason": defer_reason},
                why_chain=["KERNEL_DEFERRED", defer_reason],
            )
            return

        current_position_side = state.position_side
        effective_side = result.side

        # === STRICT REGIME ALLOWLIST GATE ===
        allowed_regimes = None
        try:
            allowed_regimes = getattr(instr_cfg, "allowed_regimes", None)
        except Exception:
            allowed_regimes = None
        if not RegimeAllowlistContract.is_regime_allowed(current_regime=str(state.regime), allowed_regimes=allowed_regimes):
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="REGIME_NOT_ALLOWLISTED",
                reason="REGIME",
                context="aurora_handler:strict_regime_allowlist",
                details={
                    "regime": state.regime,
                    "allowed_regimes": list(allowed_regimes or []),
                    "score": float(result.score),
                    "thr_buy": float(result.thr_buy),
                    "thr_sell": float(result.thr_sell),
                    "explain": RegimeAllowlistContract.explain_blocking(
                        symbol=symbol,
                        current_regime=str(state.regime),
                        allowed_regimes=list(allowed_regimes) if allowed_regimes else None,
                    ),
                },
                why_chain=["REGIME_ALLOWLIST", f"REGIME={state.regime}", "STRICT"],
            )
            return

        # === PHASE 5: EXIT MANAGER ===
        shield_breakdown = getattr(result, "shield_breakdown", {}) or {}
        shield_reasons = shield_breakdown.get("reasons", []) if isinstance(shield_breakdown, dict) else []
        danger_zone_active = any("DANGER_ZONE" in str(r) for r in shield_reasons)
        should_exit = False
        stop_loss_override = None

        if current_position_side != "":
            entry_ts = state.entry_timestamp or float(self.monotonic_fn())
            hold_time_sec = float(self.monotonic_fn()) - entry_ts

            # S2-TRAILING: Update MFE
            if state.mfe_price is None:
                state.mfe_price = price_dec
            elif current_position_side.upper() == "LONG":
                bar_high = features.get("high")
                if bar_high is not None:
                    state.mfe_price = max(state.mfe_price, decimal.Decimal(str(bar_high)))
                else:
                    state.mfe_price = max(state.mfe_price, price_dec)
            else:
                bar_low = features.get("low")
                if bar_low is not None:
                    state.mfe_price = min(state.mfe_price, decimal.Decimal(str(bar_low)))
                else:
                    state.mfe_price = min(state.mfe_price, price_dec)

            atr_raw = features.get("atr")
            atr_dec = decimal.Decimal(str(atr_raw)) if atr_raw is not None else None

            should_exit, exit_reason, new_sl = self.exit_manager.check_exit(
                symbol=symbol,
                current_position_side=current_position_side,
                entry_price=decimal.Decimal(str(features.get("entry_price", "0"))),
                current_price=price_dec,
                hold_time_sec=hold_time_sec,
                final_score=float(result.score),
                danger_zone_active=danger_zone_active,
                current_stop_loss=None,
                mfe_price=state.mfe_price,
                atr=atr_dec,
            )

            if should_exit:
                target_side = "SELL" if current_position_side.lower() in ("buy", "long") else "BUY"
                if effective_side != target_side:
                    self.logger.info(f"[{symbol}] EXIT MANAGER: Forcing exit ({exit_reason})")
                    effective_side = target_side

            elif new_sl is not None:
                stop_loss_override = new_sl
                self.logger.info(f"[{symbol}] EXIT MANAGER: Tightening stops ({exit_reason}) to {new_sl}")

        # === HOLDING PERIOD CHECK ===
        is_exit_signal = (not effective_side) and (current_position_side != "")
        is_flip_signal = (
            current_position_side != ""
            and effective_side
            and effective_side.lower() != current_position_side
        )

        if (is_exit_signal or is_flip_signal) and not should_exit:
            if self._should_suppress_soft_exit(symbol, result, is_flip=is_flip_signal):
                self.logger.info(
                    f"[{symbol}] HOLDING_PERIOD: Forcing HOLD (side={current_position_side}) "
                    f"suppressing {'flip' if is_flip_signal else 'exit'}"
                )
                effective_side = current_position_side

        # === REGIME KILL-SWITCH ===
        if getattr(self, "blocked_regimes", None) and state.regime in self.blocked_regimes:
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="REGIME_KILL_SWITCH",
                reason="REGIME_BLOCKED",
                context="aurora_handler:regime_kill_switch",
                details={
                    "regime": state.regime,
                    "score": float(result.score),
                    "thr_buy": float(result.thr_buy),
                    "thr_sell": float(result.thr_sell),
                },
                why_chain=["REGIME_KILL_SWITCH", f"REGIME={state.regime}"],
            )
            return

        if not effective_side:
            if state.position_side:
                state.last_exit_timestamp = float(self.monotonic_fn())
                state.position_side = ""
                self._clear_entry(symbol)
                self.logger.info(f"[{symbol}] Position closed (neutral). Starting re-entry cooldown.")
            self.logger.debug(f"[{symbol}] Neutral signal (score={float(result.score):.4f})")
            return

        # === RE-ENTRY COOLDOWN ===
        if state.position_side == "" and effective_side:
            if state.last_exit_timestamp:
                reentry_cooldown = self._get_reentry_cooldown_sec(symbol)
                time_since_exit = float(self.monotonic_fn()) - state.last_exit_timestamp
                if time_since_exit < reentry_cooldown:
                    self.logger.info(
                        f"[{symbol}] REENTRY_COOLDOWN: Blocking entry {time_since_exit:.1f}s < {reentry_cooldown}s"
                    )
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code="REENTRY_COOLDOWN",
                        reason="COOLDOWN",
                        context="aurora_handler:reentry_cooldown",
                        details={"time_since_exit": time_since_exit, "cooldown": reentry_cooldown},
                        why_chain=["REENTRY_COOLDOWN", f"wait:{reentry_cooldown - time_since_exit:.1f}s"],
                    )
                    return

        # === VOL-ADJ GATES ===
        if self._apply_vol_adj_gates(symbol, result, state, features, effective_side=effective_side):
            return

        # === ANCHOR SHOCK VETO ===
        if (
            veto_cfg
            and getattr(veto_cfg, "enabled", False)
            and veto_applicable
            and veto_threshold is not None
            and veto_macro_resid is not None
            and (effective_side or "").lower() == "buy"
            and veto_macro_resid < veto_threshold
        ):
            self.logger.warning(
                f"[{symbol}] ANCHOR SHOCK VETO: Blocking BUY signal "
                f"(macro_resid={veto_macro_resid:.2f} < {veto_threshold})"
            )
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="ANCHOR_SHOCK_VETO",
                reason="MACRO_VETO",
                context="aurora_handler:anchor_shock_veto",
                details={
                    "macro_resid": veto_macro_resid,
                    "threshold": veto_threshold,
                    "side": effective_side,
                    "anchor_symbol": veto_anchor_symbol,
                },
                why_chain=["MACRO_VETO", "ANCHOR_SHOCK_VETO"],
            )
            return

        # === PHASE 5: EXECUTION GATES & ENTRY PLAN ===
        if self.execution_gate is not None:
            shield_mult = float(getattr(result, "shield_multiplier", 1.0) or 1.0)

            entry_plan_res = None
            entry_plan_calc = getattr(self, "entry_plan_calculator", None)
            if entry_plan_calc is None or not hasattr(entry_plan_calc, "compute"):
                self.logger.warning(
                    f"[{symbol}] EntryPlan not configured in domains.decision_making.entry_plan. Blocking entry (fail-closed)."
                )
                self._emit_strategy_blocked(
                    symbol=symbol,
                    reason_code="ENTRY_PLAN_MISSING",
                    reason="HARD_VETO:EntryPlanMissing",
                    context="aurora_handler:entry_plan",
                    details={
                        "config_path": "domains.decision_making.entry_plan",
                        "entry_plan_calculator_is_none": entry_plan_calc is None,
                    },
                    why_chain=["ENTRY_PLAN", "MISSING", "FAIL_CLOSED"],
                )
                return
            try:
                factor = float(getattr(result, "threshold_factor", 1.0) or 1.0)
                score_for_conf = float(getattr(result, "score", 0.0) or 0.0)
                confidence = min(1.0, abs(score_for_conf) / factor) if factor > 0 else 0.5

                entry_plan_res = entry_plan_calc.compute(
                    side=result.side,
                    ref_price=price_dec,
                    atr=features.get("atr"),
                    obi=features.get("obi"),
                    pillar_confidence=confidence,
                    tick_size=getattr(instr_cfg, "tick_size", None) if instr_cfg else None,
                )
            except Exception as e:
                self.logger.warning(f"[{symbol}] EntryPlan computation failed: {e}")
                self._emit_strategy_blocked(
                    symbol=symbol,
                    reason_code="ENTRY_PLAN_COMPUTE_FAILED",
                    reason="HARD_VETO:EntryPlanComputeFailed",
                    context="aurora_handler:entry_plan",
                    details={"error": str(e)},
                    why_chain=["ENTRY_PLAN", "COMPUTE_FAILED", "FAIL_CLOSED"],
                )
                return

            active_threshold = float(result.thr_buy if result.side.lower() == "buy" else result.thr_sell)

            gate_ok, gate_reason = self.execution_gate.check_entry(
                symbol=symbol,
                side=result.side,
                features=features,
                final_score=float(result.score),
                shield_multiplier=shield_mult,
                entry_plan=entry_plan_res,
                signal_threshold=active_threshold,
                oracle_level="NORMAL",
                danger_zone_active=danger_zone_active,
            )

            if not gate_ok:
                self._emit_strategy_blocked(
                    symbol=symbol,
                    reason_code="EXECUTION_GATE_BLOCKED",
                    reason=str(gate_reason),
                    context="aurora_handler:execution_gate",
                    details={
                        "gate_reason": gate_reason,
                        "score": float(result.score),
                        "shield_mult": shield_mult,
                        "threshold": active_threshold,
                    },
                    why_chain=["EXECUTION_GATE", str(gate_reason)],
                )
                return

            self._emit_signal(
                symbol,
                result,
                features,
                cmd,
                effective_side=effective_side,
                entry_plan=entry_plan_res,
                stop_loss_override=stop_loss_override,
            )
        else:
            self._emit_signal(symbol, result, features, cmd, effective_side=effective_side)

        # Update side bias history
        self._update_side_bias(symbol, effective_side)

    def _emit_signal(
        self,
        symbol: str,
        result: ScoringResult,
        features: Dict[str, Any],
        source_event: Dict[str, Any],
        *,
        effective_side: str | None = None,
        entry_plan: Optional[EntryPlanResult] = None,
        stop_loss_override: Optional[decimal.Decimal] = None,
    ) -> None:
        """Emit EVT:STRATEGY_SIGNAL_PRODUCED with readiness contract."""
        state = self._symbol_states[symbol]
        side = effective_side if effective_side is not None else result.side
        now_ms = int(self.wall_time_fn() * 1000)

        # Get anchor price and default entry price
        anchor_price = decimal.Decimal(str(features.get("price", "0")))
        entry_price = anchor_price

        # === ENTRY PLAN (Phase 4/5) ===
        tpsl_result = None

        if entry_plan:
            entry_price = decimal.Decimal(entry_plan.entry_price)
            stop_price = decimal.Decimal(entry_plan.stop_loss_price)
            target_price = decimal.Decimal(entry_plan.take_profit_price)

            tpsl_result = {
                "stop_price": stop_price,
                "target_price": target_price,
                "tpsl_ctx": {
                    "mode": "ENTRY_PLAN",
                    "risk_bps": 0,
                    "reward_bps": 0,
                }
            }
        else:
            # Fallback to Legacy Regime TPSL
            instr_cfg = self._get_instrument_config(symbol)
            vel_cfg = getattr(instr_cfg, "volatility_entry_logic", None) if instr_cfg else None

            if vel_cfg and getattr(vel_cfg, "enabled", False):
                volatility = self._get_volatility_strict(symbol, features)
                if volatility is None:
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code="ATR_MISSING_FAIL_CLOSED",
                        reason="DATA_NOT_READY",
                        context="aurora_handler:volatility_entry",
                        details={"required_feature": "atr"},
                        why_chain=["VOLATILITY_ENTRY", "ATR_MISSING", "FAIL_CLOSED"],
                    )
                    return

                regime = state.regime or "DEFAULT"
                multipliers = getattr(vel_cfg, "regime_multipliers", {})
                mult_raw = multipliers.get(regime, multipliers.get("DEFAULT"))
                if mult_raw is None:
                    self.logger.error(f"[{symbol}] regime_multipliers missing DEFAULT key (fail-closed)")
                    return
                mult = decimal.Decimal(str(mult_raw))

                offset = volatility * mult

                if side.lower() == "buy":
                    entry_price = anchor_price - offset
                elif side.lower() == "sell":
                    entry_price = anchor_price + offset

                self.logger.debug(
                    f"[{symbol}] Limit Offset: {offset:.6f} for Regime: {regime} "
                    f"(atr={volatility:.6f}, mult={mult}, entry={entry_price:.6f})"
                )

            tpsl_result = self._compute_regime_tpsl(
                symbol=symbol,
                entry_price=entry_price,
                side=side,
                regime=state.regime,
                instr_cfg=instr_cfg,
                features=features,
            )

        # === STOP LOSS OVERRIDE (Exit Manager) ===
        if stop_loss_override is not None and tpsl_result:
            tpsl_result["stop_price"] = stop_loss_override
            tpsl_result["tpsl_ctx"]["mode"] = "EXIT_MANAGER_OVERRIDE"

        # Build payload per v7 contract
        payload = {
            "strategy_id": self.strategy_id,
            "symbol": symbol,
            "side": side.upper(),
            "ts_ms": now_ms,
            "rid": f"aurora_{symbol}_{now_ms}",
            "why_chain": result.why_chain,
            "readiness": {"warmup_ok": state.warmup_full_ready},
            "price_ctx": {
                "entry_price": str(entry_price),
            },
            "scoring": {
                "score": float(result.score),
                "thr_buy": float(result.thr_buy),
                "thr_sell": float(result.thr_sell),
                "regime": result.regime,
                "psi_vector": result.psi_vector,
            },
            "volatility": features.get("volatility"),
            "liquidity": features.get("liquidity"),
            "tf_sec": self.timeframe_sec,
            "regime_ctx": {
                "confidence": state.regime_confidence,
                "regime_ts_ms": state.regime_ts_ms,
                "regime_age_sec": round((now_ms - state.regime_ts_ms) / 1000, 1) if state.regime_ts_ms else 0,
                "regime": state.regime,
            },
        }

        # BUG-5: Instrument Quantization (Phase 9)
        instruments_cfg = getattr(self.config, "instruments", None)
        precision = instruments_cfg.get(symbol) if isinstance(instruments_cfg, dict) else None

        if precision:
            try:
                spec = QuantizerSpec(
                    step_size=precision.step_size,
                    min_qty=precision.min_qty,
                    min_notional=precision.min_notional,
                    tick_size=precision.tick_size,
                )

                instr_cfg = self._get_instrument_config(symbol)
                leverage_cfg = getattr(instr_cfg, "leverage", None)
                target_leverage = getattr(leverage_cfg, "target", 20)
                max_notional_cap = getattr(leverage_cfg, "max_notional_value", None) or decimal.Decimal("1000000")

                q_pos = quantize_exposure(
                    exposure=float(result.score),
                    price=entry_price,
                    max_notional=max_notional_cap,
                    leverage=target_leverage,
                    spec=spec,
                )

                if q_pos.reject_reason:
                    self.logger.warning(f"[{symbol}] QUANTIZER_REJECT: {q_pos.reject_reason}")
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code="QUANTIZER_REJECT",
                        reason=q_pos.reject_reason,
                        context="aurora_handler:quantizer",
                        details={"exposure": result.score, "price": str(entry_price)},
                        why_chain=result.why_chain + [f"QUANTIZER:{q_pos.reject_reason}"],
                    )
                    return

                payload["quantization"] = {
                    "qty": str(q_pos.qty),
                    "notional": str(q_pos.notional),
                    "margin_required": str(q_pos.margin_required),
                }

            except Exception as e:
                self.logger.error(f"[{symbol}] QUANTIZER_ERROR: {e}")
                self._emit_strategy_blocked(
                    symbol=symbol,
                    reason_code="QUANTIZER_ERROR",
                    reason=str(e),
                    context="aurora_handler:quantizer_crash",
                    details={"error": str(e)},
                    why_chain=result.why_chain + ["QUANTIZER_CRASH"],
                )
                return

        # BUG-2: IDEMPOTENT MEMORY RECORDING
        ms = getattr(self, "_memory_shield", None)
        if ms:
            sh_details = getattr(result, "details", {}) or {}
            state_hash = sh_details.get("memory_state_hash")
            if state_hash:
                ms.record_visit(symbol, features, bar_close_ts=int(now_ms/1000), state_hash=state_hash)

        # === INJECT REGIME-BASED TP/SL INTO PAYLOAD ===
        if tpsl_result is not None:
            payload["price_ctx"]["stop_price"] = str(tpsl_result["stop_price"])
            payload["price_ctx"]["target_price"] = str(tpsl_result["target_price"])

            payload["tpsl_ctx"] = tpsl_result["tpsl_ctx"]

            tpsl_ctx = tpsl_result["tpsl_ctx"]
            tpsl_why = (
                f"tpsl:regime={tpsl_ctx.get('regime_used')} "
                f"mode={tpsl_ctx.get('mode')} "
                f"sl_pct_post={tpsl_ctx.get('sl_pct_post', tpsl_ctx.get('sl_pct_eff', 0)):.4f} "
                f"tp_rr_pre={tpsl_ctx.get('rr_pre', tpsl_ctx.get('tp_rr_eff', tpsl_ctx.get('rr', 0))):.2f} "
                f"rr_post={tpsl_ctx.get('rr_post', tpsl_ctx.get('rr_eff', 0)):.2f}"
            )
            payload["why_chain"] = result.why_chain + [tpsl_why]

            self.logger.info(
                f"[{symbol}] REGIME_TPSL: regime={tpsl_ctx.get('regime_used')} "
                f"stop={tpsl_result['stop_price']:.6f} target={tpsl_result['target_price']:.6f}"
            )

        self.logger.info(
            f"[{symbol}] SIGNAL: {side.upper()} score={float(result.score):.4f} "
            f"(thr_buy={float(result.thr_buy):.4f}, thr_sell={float(result.thr_sell):.4f})"
        )

        self.emit_fn("EVT:STRATEGY_SIGNAL_PRODUCED", payload)

        # Update state
        state.last_signal_ts_ms = now_ms
        state.last_signal_side = side
