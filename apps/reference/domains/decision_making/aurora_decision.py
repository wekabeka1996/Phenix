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

from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    combine_restore_permissions_live_first,
    lookup_restore_status,
    merge_restore_readiness_live_first,
    restore_execution_blocking_tokens,
    restore_status_to_readiness_status,
)
from apps.reference.bootstrap.startup_warmup import (
    apply_startup_warmup_permission_overlay,
    startup_warmup_gate_tokens,
)
from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    extract_canonical_bar_identity,
    extract_canonical_replay_identity,
)
from apps.reference.contracts.runtime_gap_policy import (
    attach_gap_status_payload,
    build_basis_bar_status_from_gap,
    build_trading_status_from_gap,
    extract_gap_status,
    gap_blocking_tokens,
    gap_blocks_open_new_risk,
)
from apps.reference.contracts.runtime_readiness import (
    RuntimeReadinessScope,
    cold_status,
    make_permissions,
    make_snapshot,
    partial_status,
    ready_status,
)
from apps.reference.contracts.quadratic_rollout import (
    apply_live_quadratic_permission_gate,
    build_quadratic_rollout_snapshot,
    evaluate_quadratic_shadow,
    not_requested_shadow_evaluation,
    resolve_requested_quadratic_rollout,
)
from apps.reference.domains.decision_making.quadratic_scoring_kernel import (
    ScoringResult,
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

    def _build_quadratic_decision_trace(
        self,
        *,
        symbol: str,
        cmd: Dict[str, Any],
        state: "SymbolState",
        features: Dict[str, Any],
        result: ScoringResult,
        effective_neutral: decimal.Decimal,
    ) -> Dict[str, Any]:
        psi = result.psi_vector or {}
        shield_reasons = []
        if isinstance(psi.get("shield_reasons"), list):
            shield_reasons = list(psi.get("shield_reasons") or [])
        return {
            "symbol": symbol,
            "tf_sec": int(cmd.get("tf_sec") or self.timeframe_sec or 0),
            "bar_close_ts": features.get("bar_close_ts") or cmd.get("bar_close_ts"),
            "regime": state.regime,
            "regime_adjustment_source": "regime_thresholds",
            "pillar_sum": psi.get("s_linear", features.get("pillar_sum")),
            "pillar_tactician": features.get("pillar_tactician"),
            "pillar_operator": features.get("pillar_operator"),
            "pillar_strategist": features.get("pillar_strategist"),
            "pillar_contribs": dict(features.get("pillar_contribs", {}) or {}),
            "raw_sum": psi.get("s_linear"),
            "score_multiplier": psi.get("multiplier", getattr(self, "score_multiplier", 1.0)),
            "s_scaled_raw": psi.get("s_scaled_raw"),
            "s_clamped": psi.get("s_clamped"),
            "raw_exposure": psi.get("raw_exposure"),
            "shield_multiplier": psi.get("shield_multiplier", float(result.shield_multiplier or 1.0)),
            "shield_reasons": shield_reasons,
            "final_score": psi.get("final_score", float(getattr(result, "score", 0.0))),
            "final_exposure": psi.get("final_exposure", float(getattr(result, "score", 0.0))),
            "thr_buy": psi.get("thr_buy", float(getattr(result, "thr_buy", 0.0))),
            "thr_sell": psi.get("thr_sell", float(getattr(result, "thr_sell", 0.0))),
            "neutral_threshold": float(effective_neutral),
            "threshold_factor": psi.get(
                "threshold_factor",
                float(getattr(result, "threshold_factor", 1.0)),
            ),
            "side": getattr(result, "side", ""),
            "deferred": bool(getattr(result, "deferred", False)),
            "defer_reason": getattr(result, "defer_reason", None),
            "side_why": psi.get("side_why"),
        }

    def _compact_quadratic_decision_trace(
        self,
        trace: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        if not isinstance(trace, dict):
            return {}
        keys = (
            "regime",
            "raw_sum",
            "raw_exposure",
            "shield_multiplier",
            "final_score",
            "thr_buy",
            "thr_sell",
            "threshold_factor",
            "side",
            "deferred",
            "defer_reason",
            "side_why",
        )
        return {
            key: trace.get(key)
            for key in keys
            if key in trace
        }

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

        # System-level warmup state is now exclusively controlled by the StrategyGateway 
        # (see readiness_gates.py). Handlers only track it for diagnostics, not fail-closed gates.
        state = self._symbol_states[symbol]
        state.warmup_full_ready = bool(warmup.get("full_ready", False))

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

        # FIX:N-2 — Cold-start bars_required gate: block signals until handler has
        # accumulated enough real-time bars to produce meaningful features/regime.
        # Uses basis_required_bars from StrategyCompatibilityProfile as threshold.
        _bars_seen = getattr(
            self, "_bars_seen_since_restart", {}).get(symbol, 0)
        _basis_required = getattr(self, "_basis_required_bars_override", None)
        _readiness_contract_error: str | None = None
        if _basis_required is None:
            try:
                from apps.reference.contracts.strategy_compatibility_matrix import (
                    get_active_strategy_profile,
                )
                _profile = get_active_strategy_profile(
                    self.config, self.strategy_id)
                if _profile is None:
                    _readiness_contract_error = "READINESS_CONTRACT_UNRESOLVED:PROFILE_NOT_FOUND"
                    _basis_required = 0
                else:
                    _basis_required = int(_profile.basis_required_bars)
            except Exception as _exc:
                _readiness_contract_error = f"READINESS_CONTRACT_UNRESOLVED:{type(_exc).__name__}"
                _basis_required = 0
        if _readiness_contract_error:
            self.logger.error(
                "[%s] READINESS_CONTRACT_UNRESOLVED — cannot resolve basis_required_bars: %s — blocking signal",
                symbol, _readiness_contract_error,
            )
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="READINESS_CONTRACT_UNRESOLVED",
                reason="READINESS",
                context="aurora_handler:basis_required_resolution",
                details={"error": _readiness_contract_error},
                why_chain=["READINESS", "READINESS_CONTRACT_UNRESOLVED"],
            )
            return
        if _basis_required and _bars_seen < _basis_required:
            self.logger.info(
                "[%s] BARS_REQUIRED gate: %d/%d bars — blocking signal (quadratic path NOT reached)",
                symbol, _bars_seen, _basis_required,
            )
            write_trade_intent_rejected(
                symbol=symbol,
                tf_sec=int(cmd.get("tf_sec") or 0),
                bar_close_ts=cmd.get("bar_close_ts"),
                reason_code="BARS_REQUIRED_COLD_START",
                stage="STRATEGY",
                why=f"Cold-start: {_bars_seen}/{_basis_required} bars seen",
                src="aurora_handler",
                ts_ms=cmd.get("bar_close_ts"),
                rid=cmd.get("rid"),
            )
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="BARS_REQUIRED_COLD_START",
                reason="READINESS",
                context="aurora_handler:bars_required_gate",
                details={
                    "bars_seen": _bars_seen,
                    "basis_required_bars": _basis_required,
                },
                why_chain=[
                    "READINESS",
                    "BARS_REQUIRED",
                    f"bars_seen:{_bars_seen}",
                    f"basis_required:{_basis_required}",
                ],
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
                reason_code=str(liq_ctx.get("reason_code")
                                or "LIQUIDITY_GATE_FAIL"),
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
            decision_cfg = getattr(
                self.config.strategies.aurora, "decision", None)
            veto_cfg = getattr(decision_cfg, "anchor_shock_veto",
                               None) if decision_cfg else None
            if veto_cfg and getattr(veto_cfg, "enabled", False):
                veto_anchor_symbol = getattr(
                    veto_cfg, "anchor_symbol", "BTCUSDT")
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
                    self.logger.debug(
                        f"[{symbol}] Using per-symbol threshold (direct): {effective_threshold}")
                elif hasattr(st_cfg, "enabled") and st_cfg.enabled:
                    if hasattr(st_cfg, "value") and st_cfg.value is not None:
                        effective_threshold = decimal.Decimal(
                            str(st_cfg.value))
                        self.logger.debug(
                            f"[{symbol}] Using per-symbol threshold (enabled): {effective_threshold}")

            nt_cfg = getattr(instr_cfg, "neutral_threshold", None)
            if nt_cfg is not None:
                if isinstance(nt_cfg, (int, float)):
                    effective_neutral = decimal.Decimal(str(nt_cfg))
                    self.logger.debug(
                        f"[{symbol}] Using per-symbol neutral_threshold: {effective_neutral}")
                elif hasattr(nt_cfg, "value") and nt_cfg.value is not None:
                    effective_neutral = decimal.Decimal(str(nt_cfg.value))

        # Get current side for hysteresis
        current_side = state.last_signal_side

        # Call scoring kernel
        effective_regime_thresholds = self._get_regime_thresholds(
            symbol=symbol, instr_cfg=instr_cfg)

        extra_kwargs = {
            "regime_smoother": getattr(self, "_regime_smoother", None),
        }
        if self.scoring_kernel_cls is QuadraticScoringKernel:
            extra_kwargs["shield_fn"] = self._shield_fn
            extra_kwargs["pillar_contribs"] = features.get(
                "pillar_contribs", {})
            extra_kwargs["score_multiplier"] = getattr(
                self, "score_multiplier", 1.0)

        bar_identity = extract_canonical_bar_identity(
            cmd,
            default_symbol=symbol,
            default_timeframe_sec=int(
                cmd.get("tf_sec") or self.timeframe_sec or 0),
            default_source_mode=RuntimeBarSourceMode.LIVE,
        )
        if "regime" not in features:
            features["regime"] = state.regime
        if "regime_ts_ms" not in features:
            features["regime_ts_ms"] = state.regime_ts_ms
        if "bar_close_ts" not in features:
            bar_close_ts_raw = (
                int(bar_identity.bar_end_ts_ms)
                if bar_identity is not None
                else cmd.get("bar_close_ts")
            )
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
            normalize_mode=self.normalize_signals_mode,
            neutral_threshold=effective_neutral,
            current_side=current_side,
        )
        decision_cfg = getattr(
            getattr(getattr(self.config, "strategies", None), "aurora", None),
            "decision",
            None,
        )
        requested_rollout = resolve_requested_quadratic_rollout(decision_cfg)
        quadratic_shadow_evaluation = evaluate_quadratic_shadow(
            requested_rollout=requested_rollout,
            compute_kwargs=_compute_kwargs,
            shield_fn=getattr(self, "_quadratic_shadow_shield_fn", None),
            pillar_contribs=features.get("pillar_contribs", {}),
            score_multiplier=getattr(self, "score_multiplier", 1.0),
            regime_smoother=getattr(self, "_regime_smoother", None),
        )
        try:
            result = self.scoring_kernel_cls.compute(
                **_compute_kwargs,
                **extra_kwargs,
            )
        except Exception as _kernel_exc:
            # QUADRATIC-FAIL-CLOSED: No silent fallback to v2.
            # Policy: kernel crash → emit observable event + fail-closed (no signal this bar).
            # Explicit rollback requires: scoring_version: "v2" in aurora.yaml
            _kernel_name = getattr(self.scoring_kernel_cls, "__name__",
                                   "UnknownKernel") if self.scoring_kernel_cls else "None"
            self.logger.exception(
                "[%s] KERNEL_CRASH: %s — fail-closed, no v2 fallback (kernel=%s)",
                symbol, _kernel_exc, _kernel_name,
            )
            try:
                self.emit_fn("EVT:QUADRATIC_KERNEL_CRASH", {
                    "schema_version": 1,
                    "symbol": symbol,
                    "strategy_id": self.strategy_id,
                    "kernel": _kernel_name,
                    "error": str(_kernel_exc),
                    "ts_ms": int(self.wall_time_fn() * 1000),
                })
            except Exception:
                pass  # Best-effort telemetry, never mask the original crash
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="QUADRATIC_KERNEL_CRASH",
                reason="KERNEL_CRASH",
                context="aurora_handler:kernel_crash_failsafe",
                details={"kernel": _kernel_name,
                         "error": str(_kernel_exc)[:200]},
                why_chain=["KERNEL_CRASH", str(_kernel_exc)[:80]],
            )
            return

        # Handle result
        state.last_signal_side = result.side
        decision_trace = self._build_quadratic_decision_trace(
            symbol=symbol,
            cmd=cmd,
            state=state,
            features=features,
            result=result,
            effective_neutral=effective_neutral,
        )

        # QUADRATIC-VISIBILITY: Emit structured trace at INFO level and as FSM event
        # so the operator can see it in logs and downstream sinks.
        compact_trace = self._compact_quadratic_decision_trace(decision_trace)
        self.logger.info(
            "[%s] QUADRATIC_DECISION_TRACE score=%.6f side=%s deferred=%s regime=%s",
            symbol,
            float(result.score),
            result.side,
            result.deferred,
            state.regime,
        )
        try:
            self.emit_fn("EVT:QUADRATIC_DECISION_TRACE", {
                "schema_version": 1,
                "strategy_id": self.strategy_id,
                "symbol": symbol,
                "tf_sec": int(cmd.get("tf_sec") or self.timeframe_sec or 0),
                "score": float(result.score),
                "side": str(result.side),
                "deferred": bool(result.deferred),
                "defer_reason": str(result.defer_reason) if result.defer_reason else None,
                "regime": str(state.regime),
                "shield_multiplier": float(result.shield_multiplier or 1.0),
                "thr_buy": str(result.thr_buy) if result.thr_buy is not None else None,
                "thr_sell": str(result.thr_sell) if result.thr_sell is not None else None,
                "quadratic_path_reached": True,
                "compact_trace": compact_trace,
                "ts_ms": int(self.wall_time_fn() * 1000),
            })
        except Exception:
            pass  # Best-effort telemetry

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
            self.logger.debug(
                f"[{symbol}] Kernel deferred: {result.defer_reason}")
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
                details={
                    "defer_reason": defer_reason,
                    "decision_trace": self._compact_quadratic_decision_trace(
                        decision_trace
                    ),
                },
                why_chain=["KERNEL_DEFERRED", defer_reason],
            )
            return

        current_position_side = state.position_side
        effective_side = result.side

        # PKG-3: Regime-Shift Inception Check
        inception_cfg = getattr(self.config, "regime_shift_inception", None)
        micro_fraction = 1.0

        allowed_regimes = None
        try:
            allowed_regimes = getattr(instr_cfg, "allowed_regimes", None)
        except Exception:
            allowed_regimes = None

        state_regime_for_gate = str(state.regime)
        if inception_cfg and getattr(inception_cfg, "enabled", False) and allowed_regimes:
            raw_regime = str(
                state.regime_raw_event) if state.regime_raw_event else ""
            if raw_regime and raw_regime != str(state.regime):
                raw_factor = effective_regime_thresholds.get(raw_regime, 1.0)
                raw_threshold = effective_threshold * \
                    decimal.Decimal(str(raw_factor))

                from apps.reference.domains.decision_making.inception_filter import check_inception_eligibility
                inc_res = check_inception_eligibility(
                    raw_regime=raw_regime,
                    stable_regime=str(state.regime),
                    allowed_regimes=list(allowed_regimes),
                    signal_score=result.score,
                    signal_threshold_for_raw=raw_threshold,
                    stress_state=state.system_stress_state,
                    config=inception_cfg
                )

                # Telemetry
                action_taken = getattr(
                    inception_cfg, "action", "none") if inc_res.eligible else "none"
                self.emit_fn("EVT:REGIME_SHIFT_SUSPECTED", {
                    "symbol": symbol,
                    "ts_ms": int(self.wall_time_fn() * 1000),
                    "raw_regime": raw_regime,
                    "stable_regime": str(state.regime),
                    "confirm_count": 0,
                    "confirm_required": 1,
                    "eligible": inc_res.eligible,
                    "action_taken": action_taken,
                    "why": inc_res.why[:80]
                })

                if inc_res.eligible and action_taken == "micro_size":
                    micro_fraction = inc_res.micro_fraction
                    _compute_kwargs["regime_name"] = raw_regime
                    try:
                        new_result = self.scoring_kernel_cls.compute(
                            **_compute_kwargs, **extra_kwargs)
                        if new_result.side:
                            result = new_result
                            effective_side = result.side
                            result.why_chain.append(
                                f"INCEPTION_RESCUE:{raw_regime}")
                            result.why_chain.append(inc_res.why)
                            state_regime_for_gate = raw_regime
                    except Exception as e:
                        self.logger.error(
                            f"[{symbol}] Inception fallback failed: {e}")

        # === STRICT REGIME ALLOWLIST GATE ===
        if not RegimeAllowlistContract.is_regime_allowed(current_regime=state_regime_for_gate, allowed_regimes=allowed_regimes):
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="REGIME_NOT_ALLOWLISTED",
                reason="REGIME",
                context="aurora_handler:strict_regime_allowlist",
                details={
                    "regime": state_regime_for_gate,
                    "allowed_regimes": list(allowed_regimes or []),
                    "score": float(result.score),
                    "thr_buy": float(result.thr_buy),
                    "thr_sell": float(result.thr_sell),
                    "explain": RegimeAllowlistContract.explain_blocking(
                        symbol=symbol,
                        current_regime=state_regime_for_gate,
                        allowed_regimes=list(
                            allowed_regimes) if allowed_regimes else None,
                    ),
                },
                why_chain=["REGIME_ALLOWLIST",
                           f"REGIME={state_regime_for_gate}", "STRICT"],
            )
            return

        # === PHASE 5: EXIT MANAGER ===
        shield_breakdown = getattr(result, "shield_breakdown", {}) or {}
        shield_reasons = shield_breakdown.get(
            "reasons", []) if isinstance(shield_breakdown, dict) else []
        danger_zone_active = any("DANGER_ZONE" in str(r)
                                 for r in shield_reasons)
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
                    state.mfe_price = max(
                        state.mfe_price, decimal.Decimal(str(bar_high)))
                else:
                    state.mfe_price = max(state.mfe_price, price_dec)
            else:
                bar_low = features.get("low")
                if bar_low is not None:
                    state.mfe_price = min(
                        state.mfe_price, decimal.Decimal(str(bar_low)))
                else:
                    state.mfe_price = min(state.mfe_price, price_dec)

            atr_raw = features.get("atr")
            atr_dec = decimal.Decimal(
                str(atr_raw)) if atr_raw is not None else None

            should_exit, exit_reason, new_sl = self.exit_manager.check_exit(
                symbol=symbol,
                current_position_side=current_position_side,
                entry_price=decimal.Decimal(
                    str(features.get("entry_price", "0"))),
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
                    self.logger.info(
                        f"[{symbol}] EXIT MANAGER: Forcing exit ({exit_reason})")
                    effective_side = target_side

            elif new_sl is not None:
                stop_loss_override = new_sl
                self.logger.info(
                    f"[{symbol}] EXIT MANAGER: Tightening stops ({exit_reason}) to {new_sl}")

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
                self.logger.info(
                    f"[{symbol}] Position closed (neutral). Starting re-entry cooldown.")
            self.logger.debug(
                f"[{symbol}] Neutral signal (score={float(result.score):.4f})")
            return

        # === RE-ENTRY COOLDOWN ===
        if state.position_side == "" and effective_side:
            if state.last_exit_timestamp:
                reentry_cooldown = self._get_reentry_cooldown_sec(symbol)
                time_since_exit = float(
                    self.monotonic_fn()) - state.last_exit_timestamp
                if time_since_exit < reentry_cooldown:
                    self.logger.info(
                        f"[{symbol}] REENTRY_COOLDOWN: Blocking entry {time_since_exit:.1f}s < {reentry_cooldown}s"
                    )
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code="REENTRY_COOLDOWN",
                        reason="COOLDOWN",
                        context="aurora_handler:reentry_cooldown",
                        details={"time_since_exit": time_since_exit,
                                 "cooldown": reentry_cooldown},
                        why_chain=[
                            "REENTRY_COOLDOWN", f"wait:{reentry_cooldown - time_since_exit:.1f}s"],
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
            shield_mult = float(
                getattr(result, "shield_multiplier", 1.0) or 1.0)

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
                confidence = min(1.0, abs(score_for_conf) /
                                 factor) if factor > 0 else 0.5

                entry_plan_res = entry_plan_calc.compute(
                    side=result.side,
                    ref_price=price_dec,
                    atr=features.get("atr"),
                    obi=features.get("obi"),
                    pillar_confidence=confidence,
                    tick_size=getattr(instr_cfg, "tick_size",
                                      None) if instr_cfg else None,
                )
            except Exception as e:
                self.logger.warning(
                    f"[{symbol}] EntryPlan computation failed: {e}")
                self._emit_strategy_blocked(
                    symbol=symbol,
                    reason_code="ENTRY_PLAN_COMPUTE_FAILED",
                    reason="HARD_VETO:EntryPlanComputeFailed",
                    context="aurora_handler:entry_plan",
                    details={"error": str(e)},
                    why_chain=["ENTRY_PLAN", "COMPUTE_FAILED", "FAIL_CLOSED"],
                )
                return

            active_threshold = float(
                result.thr_buy if result.side.lower() == "buy" else result.thr_sell)

            # Objective Engine Integration (post-EntryPlan / pre-ExecutionGate seam)
            domain_cfg = getattr(getattr(self.config, "domains", None),
                                 "objective_engine", None)
            strategy_cfg = getattr(getattr(self.config.strategies, "aurora", None),
                                   "objective", None)
            objective_domain_enabled = getattr(
                domain_cfg, "enabled", False) is True
            objective_strategy_enabled = getattr(
                strategy_cfg, "enabled", False) is True
            if domain_cfg and strategy_cfg and objective_domain_enabled and objective_strategy_enabled:
                try:
                    from apps.reference.domains.objective_engine.adapters import (
                        build_behavior_input,
                        build_execution_input,
                        build_exposure_input,
                        build_market_input,
                        build_objective_input,
                        build_signal_input,
                        build_structure_input,
                        compute_projected_order_notional,
                        compute_readiness_completeness,
                    )
                    from apps.reference.domains.objective_engine.engine import evaluate_objective

                    cost_cfg = domain_cfg.components.get("cost")
                    behavior_cfg = domain_cfg.components.get("behavior")

                    # FIX:N-7 — Soft-block on missing preconditions instead of
                    # raising ValueError. These are normal during startup warmup.
                    _objective_precondition_fail = None
                    if cost_cfg is None or not cost_cfg.enabled:
                        _objective_precondition_fail = "OBJECTIVE_COMPONENT_MISSING:cost"
                    elif behavior_cfg is None or not behavior_cfg.enabled:
                        _objective_precondition_fail = "OBJECTIVE_COMPONENT_MISSING:behavior"
                    elif not isinstance(self._latest_portfolio, dict):
                        _objective_precondition_fail = "OBJECTIVE_PORTFOLIO_MISSING"
                    elif not isinstance(self._latest_exposure_summary, dict):
                        _objective_precondition_fail = "OBJECTIVE_EXPOSURE_SUMMARY_MISSING"
                    elif not state.regime:
                        _objective_precondition_fail = "OBJECTIVE_REGIME_MISSING"
                    elif not state.regime_ts_ms:
                        _objective_precondition_fail = "OBJECTIVE_REGIME_TS_MISSING"
                    elif entry_plan_res is None:
                        _objective_precondition_fail = "OBJECTIVE_ENTRY_PLAN_MISSING"
                    if _objective_precondition_fail is not None:
                        self.logger.debug(
                            "[%s] Objective precondition not met: %s",
                            symbol, _objective_precondition_fail,
                        )
                        self._emit_strategy_blocked(
                            symbol=symbol,
                            reason_code="OBJECTIVE_PRECONDITION_NOT_MET",
                            reason="DECISION",
                            context="aurora_handler:objective_engine",
                            details={
                                "precondition": _objective_precondition_fail},
                            why_chain=["OBJECTIVE_ENGINE",
                                       "PRECONDITION_NOT_MET",
                                       _objective_precondition_fail],
                        )
                        return

                    objective_market = build_market_input(features=features)
                    readiness_completeness = compute_readiness_completeness(
                        warmup_readiness)
                    signal_input = build_signal_input(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        signal_score=float(result.score),
                        signal_direction=1 if result.side == "buy" else -1,
                        regime=str(state.regime),
                        regime_age_sec=float(
                            (int(self.wall_time_fn() * 1000) - int(state.regime_ts_ms)) / 1000.0),
                        regime_confidence=float(state.regime_confidence),
                        readiness_completeness=readiness_completeness,
                    )
                    structure_input = build_structure_input(
                        signal_score=float(result.score),
                        active_threshold=active_threshold,
                        entry_plan=entry_plan_res,
                    )
                    projected_notional_usd = compute_projected_order_notional(
                        symbol=symbol,
                        side=result.side.upper(),
                        entry_price=decimal.Decimal(
                            str(entry_plan_res.entry_price)),
                        position_queries=self._position_queries,
                        portfolio=self._latest_portfolio,
                        features_payload=cmd.get("features") if isinstance(
                            cmd.get("features"), dict) else {},
                        margin_pct_mult=decimal.Decimal(str(micro_fraction)),
                    )
                    exposure_input = build_exposure_input(
                        config=self.config,
                        portfolio=self._latest_portfolio,
                        exposure_summary=self._latest_exposure_summary,
                        projected_order_notional_usd=projected_notional_usd,
                    )
                    behavior_input = build_behavior_input(
                        now_ms=int(self.wall_time_fn() * 1000),
                        window_sec=float(
                            behavior_cfg.parameters["window_sec"]),
                        cancel_replace_ts_ms=state.objective_cancel_replace_ts_ms,
                        blocked_intent_ts_ms=state.objective_blocked_ts_ms,
                        reentry_ts_ms=state.objective_reentry_ts_ms,
                    )
                    execution_input = build_execution_input(
                        expected_fee_bps=float(
                            cost_cfg.parameters["base_fee_bps"]),
                        expected_slippage_bps=objective_market.spread_bps *
                        float(
                            cost_cfg.parameters["slippage_from_spread_ratio"]),
                    )
                    obj_input = build_objective_input(
                        signal=signal_input,
                        market=objective_market,
                        structure=structure_input,
                        exposure=exposure_input,
                        behavior=behavior_input,
                        execution=execution_input,
                    )
                    obj_score = evaluate_objective(
                        obj_input, domain_cfg, strategy_cfg)

                    if obj_score.is_blocked:
                        self._emit_strategy_blocked(
                            symbol=symbol,
                            reason_code="OBJECTIVE_GATE_BLOCKED",
                            reason="DECISION",
                            context="aurora_handler:objective_engine",
                            details={
                                "objective_score": obj_score.objective_score,
                                "objective_multiplier": obj_score.multiplier,
                                "objective_components": obj_score.components,
                                "objective_raw_metrics": obj_score.raw_metrics,
                                "block_reason": obj_score.block_reason,
                            },
                            why_chain=["OBJECTIVE_ENGINE", str(
                                obj_score.block_reason or "GATE_BLOCKED")],
                        )
                        return

                    result.score = decimal.Decimal(
                        str(obj_score.objective_score))
                    if not result.psi_vector:
                        result.psi_vector = {}
                    result.psi_vector["objective"] = obj_score.trace.model_dump(
                    )
                except Exception as e:
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code="OBJECTIVE_ENGINE_FAIL_CLOSED",
                        reason="DECISION",
                        context="aurora_handler:objective_engine",
                        details={"error": str(e)},
                        why_chain=["OBJECTIVE_ENGINE", "FAIL_CLOSED", str(e)],
                    )
                    return

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
                        "decision_trace": self._compact_quadratic_decision_trace(
                            decision_trace
                        ),
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
                micro_fraction=micro_fraction,
                quadratic_shadow_evaluation=quadratic_shadow_evaluation,
            )
        else:
            self._emit_signal(
                symbol,
                result,
                features,
                cmd,
                effective_side=effective_side,
                micro_fraction=micro_fraction,
                quadratic_shadow_evaluation=quadratic_shadow_evaluation,
            )

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
        micro_fraction: float = 1.0,
        quadratic_shadow_evaluation: Any | None = None,
    ) -> None:
        """Emit EVT:STRATEGY_SIGNAL_PRODUCED with readiness contract."""
        state = self._symbol_states[symbol]
        side = effective_side if effective_side is not None else result.side
        now_ms = int(self.wall_time_fn() * 1000)
        bar_identity = extract_canonical_bar_identity(
            source_event,
            default_symbol=symbol,
            default_timeframe_sec=int(source_event.get(
                "tf_sec") or self.timeframe_sec or 0),
            default_source_mode=RuntimeBarSourceMode.LIVE,
        )
        replay_identity = extract_canonical_replay_identity(
            source_event,
            default_symbol=symbol,
            default_timeframe_sec=int(source_event.get(
                "tf_sec") or self.timeframe_sec or 0),
            default_source_mode=RuntimeBarSourceMode.LIVE,
        )
        gap_status = extract_gap_status(
            source_event,
            default_source="market_data:payload_bridge",
            default_source_mode=RuntimeBarSourceMode.LIVE,
        )

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
            vel_cfg = getattr(instr_cfg, "volatility_entry_logic",
                              None) if instr_cfg else None

            if vel_cfg and getattr(vel_cfg, "enabled", False):
                volatility = self._get_volatility_strict(symbol, features)
                if volatility is None:
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code="ATR_MISSING_FAIL_CLOSED",
                        reason="DATA_NOT_READY",
                        context="aurora_handler:volatility_entry",
                        details={"required_feature": "atr"},
                        why_chain=["VOLATILITY_ENTRY",
                                   "ATR_MISSING", "FAIL_CLOSED"],
                    )
                    return

                regime = state.regime or "DEFAULT"
                multipliers = getattr(vel_cfg, "regime_multipliers", {})
                mult_raw = multipliers.get(regime, multipliers.get("DEFAULT"))
                if mult_raw is None:
                    self.logger.error(
                        f"[{symbol}] regime_multipliers missing DEFAULT key (fail-closed)")
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
        restore_snapshot = self.get_runtime_analytics_restore_snapshot(symbol)
        decision_cfg = getattr(
            getattr(getattr(self.config, "strategies", None), "aurora", None),
            "decision",
            None,
        )
        requested_rollout = resolve_requested_quadratic_rollout(decision_cfg)
        base_runtime_permissions = make_permissions(
            can_manage_existing_risk=True,
            can_open_new_risk=not gap_blocks_open_new_risk(gap_status),
        )
        runtime_permissions = combine_restore_permissions_live_first(
            base_runtime_permissions,
            restore_snapshot,
        )
        gap_reason_chain = list(gap_blocking_tokens(gap_status)) + list(
            restore_execution_blocking_tokens(restore_snapshot)
        )
        gap_reason_chain = list(dict.fromkeys(gap_reason_chain))
        quadratic_htf_status = (
            ready_status(
                why=["pillar_sum_present"],
                updated_at=now_ms,
                source="feature_engineering:payload_bridge",
                evidence_ref=f"pillar:{symbol}:{self.timeframe_sec}:{now_ms}",
            )
            if features.get("pillar_sum") is not None
            else cold_status(
                why=["pillar_sum_missing"],
                updated_at=now_ms,
                source="feature_engineering:payload_bridge",
                evidence_ref=f"pillar:{symbol}:{self.timeframe_sec}:{now_ms}",
            )
        )
        runtime_scopes = {
            RuntimeReadinessScope.BASIS_BAR_READY.value: build_basis_bar_status_from_gap(
                gap_status,
                updated_at=now_ms,
                source="market_data:payload_bridge",
                evidence_ref=(bar_identity.to_ref()
                              if bar_identity is not None else None),
            ),
            RuntimeReadinessScope.MICROSTRUCTURE_READY.value: (
                ready_status(
                    why=["fe_warmup_full_ready"],
                    updated_at=now_ms,
                    source="feature_engineering:payload_bridge",
                    evidence_ref=f"warmup:{symbol}:{now_ms}",
                )
                if state.warmup_full_ready
                else cold_status(
                    why=["fe_warmup_not_ready"],
                    updated_at=now_ms,
                    source="feature_engineering:payload_bridge",
                    evidence_ref=f"warmup:{symbol}:{now_ms}",
                )
            ),
            RuntimeReadinessScope.QUADRATIC_HTF_READY.value: quadratic_htf_status,
            RuntimeReadinessScope.STRATEGY_READY_PER_SYMBOL.value: ready_status(
                why=["signal_emitted"],
                updated_at=now_ms,
                source="decision_making:aurora",
                evidence_ref=f"signal:{symbol}:{now_ms}",
            ),
        }
        runtime_scopes[RuntimeReadinessScope.REGIME_READY.value] = (
            ready_status(
                why=["regime_heartbeat_present"],
                updated_at=state.regime_ts_ms or now_ms,
                source="regime_detector:payload_bridge",
                evidence_ref=f"regime:{symbol}:{state.regime_ts_ms or now_ms}",
            )
            if state.regime and state.regime_ts_ms
            else partial_status(
                why=["regime_heartbeat_missing"],
                updated_at=now_ms,
                source="regime_detector:payload_bridge",
                evidence_ref=f"regime:{symbol}:{now_ms}",
            )
        )
        if restore_snapshot is not None:
            runtime_scopes[RuntimeReadinessScope.EXECUTION_CONTEXT_READY.value] = restore_status_to_readiness_status(
                lookup_restore_status(
                    restore_snapshot,
                    RuntimeAnalyticsRestoreScope.EXECUTION_STATE,
                ),
                updated_at=now_ms,
                source="execution_position:startup_restore",
                evidence_ref=f"execution:{symbol}:{now_ms}",
            )
            runtime_scopes[RuntimeReadinessScope.MICROSTRUCTURE_READY.value] = merge_restore_readiness_live_first(
                lookup_restore_status(
                    restore_snapshot,
                    RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_CACHE,
                ),
                live_status=runtime_scopes[RuntimeReadinessScope.MICROSTRUCTURE_READY.value],
                updated_at=now_ms,
                source="feature_engineering:startup_restore",
                evidence_ref=f"fe_cache:{symbol}:{now_ms}",
                live_evidence_present=True,
            )
            runtime_scopes[RuntimeReadinessScope.QUADRATIC_HTF_READY.value] = merge_restore_readiness_live_first(
                lookup_restore_status(
                    restore_snapshot,
                    RuntimeAnalyticsRestoreScope.PILLAR_STATE,
                ),
                live_status=runtime_scopes[RuntimeReadinessScope.QUADRATIC_HTF_READY.value],
                updated_at=now_ms,
                source="feature_engineering:startup_restore",
                evidence_ref=f"pillars:{symbol}:{now_ms}",
                live_evidence_present=True,
            )
            runtime_scopes[RuntimeReadinessScope.REGIME_READY.value] = merge_restore_readiness_live_first(
                lookup_restore_status(
                    restore_snapshot,
                    RuntimeAnalyticsRestoreScope.REGIME_DETECTOR_STATE,
                ),
                live_status=runtime_scopes[RuntimeReadinessScope.REGIME_READY.value],
                updated_at=now_ms,
                source="regime_detector:startup_restore",
                evidence_ref=f"regime:{symbol}:{now_ms}",
                live_evidence_present=True,
            )
            runtime_scopes[RuntimeReadinessScope.STRATEGY_READY_PER_SYMBOL.value] = merge_restore_readiness_live_first(
                lookup_restore_status(
                    restore_snapshot,
                    RuntimeAnalyticsRestoreScope.DECISION_CACHE,
                ),
                live_status=runtime_scopes[RuntimeReadinessScope.STRATEGY_READY_PER_SYMBOL.value],
                updated_at=now_ms,
                source="decision_making:startup_restore",
                evidence_ref=f"decision_cache:{symbol}:{now_ms}",
                restored_why=["signal_emitted"],
                live_evidence_present=True,
            )
        quadratic_rollout = build_quadratic_rollout_snapshot(
            requested_rollout=requested_rollout,
            quadratic_readiness=runtime_scopes[RuntimeReadinessScope.QUADRATIC_HTF_READY.value],
            runtime_permissions=runtime_permissions,
            shadow_evaluation=(
                quadratic_shadow_evaluation
                if quadratic_shadow_evaluation is not None
                else not_requested_shadow_evaluation()
            ),
        )
        runtime_permissions = apply_live_quadratic_permission_gate(
            runtime_permissions,
            quadratic_rollout,
        )
        runtime_permissions = apply_startup_warmup_permission_overlay(
            runtime_permissions,
        )
        blocking_reason_chain = list(gap_reason_chain) + list(
            quadratic_rollout.quadratic_blocking_reason_chain
        )
        blocking_reason_chain.extend(startup_warmup_gate_tokens())
        blocking_reason_chain = list(dict.fromkeys(blocking_reason_chain))
        if runtime_permissions.can_manage_existing_risk and (not runtime_permissions.can_open_new_risk):
            blocking_reason_chain.append("protect_only")
            blocking_reason_chain = list(dict.fromkeys(blocking_reason_chain))
        runtime_scopes[RuntimeReadinessScope.TRADING_READY.value] = build_trading_status_from_gap(
            gap_status,
            updated_at=now_ms,
            source="decision_making:aurora",
            evidence_ref=f"signal:{symbol}:{now_ms}",
            allow_open_new_risk=runtime_permissions.can_open_new_risk,
            open_ready_why=["open_new_risk_allowed"],
            blocked_why=blocking_reason_chain,
        )
        runtime_snapshot = make_snapshot(
            strategy_id=self.strategy_id,
            symbol=symbol,
            updated_at=now_ms,
            scopes=runtime_scopes,
            source="decision_making:aurora",
            permissions=runtime_permissions,
            blocking_reason_chain=blocking_reason_chain,
        )
        payload = {
            "strategy_id": self.strategy_id,
            "symbol": symbol,
            "side": side.upper(),
            "ts_ms": now_ms,
            "rid": f"aurora_{symbol}_{now_ms}",
            "bar_close_ts": (
                int(bar_identity.bar_end_ts_ms)
                if bar_identity is not None
                else int(source_event.get("bar_close_ts") or 0)
            ),
            "why_chain": result.why_chain,
            "readiness": {"warmup_ok": state.warmup_full_ready},
            "runtime_permissions": runtime_permissions.to_payload(),
            "runtime_readiness": runtime_snapshot.to_payload(),
            "rollout_mode": quadratic_rollout.mode.value,
            "rollback_armed_status": quadratic_rollout.rollback_armed_status.value,
            "quadratic_rollout": quadratic_rollout.to_payload(),
            "price_ctx": {
                "entry_price": str(entry_price),
            },
            "scoring": {
                "score": float(result.score),
                "thr_buy": float(result.thr_buy),
                "thr_sell": float(result.thr_sell),
                "regime": result.regime,
                "psi_vector": result.psi_vector,
                "objective": (result.psi_vector or {}).get("objective"),
            },
            "sizing": {
                "margin_pct_mult": float(micro_fraction),
            },
            "volatility": features.get("volatility"),
            "liquidity": features.get("liquidity"),
            "tf_sec": self.timeframe_sec,
            "source_mode": (
                bar_identity.source_mode.value
                if bar_identity is not None
                else str(source_event.get("source_mode") or RuntimeBarSourceMode.LIVE.value)
            ),
            "regime_ctx": {
                "confidence": state.regime_confidence,
                "regime_ts_ms": state.regime_ts_ms,
                "regime_age_sec": round((now_ms - state.regime_ts_ms) / 1000, 1) if state.regime_ts_ms else 0,
                "regime": state.regime,
            },
        }
        if bar_identity is not None:
            payload["bar_identity"] = bar_identity.to_payload()
            payload["close_boundary_ts_ms"] = int(
                bar_identity.close_boundary_ts_ms)
        if replay_identity is not None:
            payload["replay_identity"] = replay_identity.to_payload()
            payload["replay_generation"] = int(
                replay_identity.replay_generation)
        if gap_status is not None:
            attach_gap_status_payload(
                payload, gap=gap_status, attach_nested_bar=False)
        if restore_snapshot is not None:
            payload["analytics_restore"] = restore_snapshot.to_payload()

        # BUG-5: Instrument Quantization (Phase 9)
        instruments_cfg = getattr(self.config, "instruments", None)
        precision = instruments_cfg.get(symbol) if isinstance(
            instruments_cfg, dict) else None

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
                max_notional_cap = getattr(
                    leverage_cfg, "max_notional_value", None) or decimal.Decimal("1000000")

                q_pos = quantize_exposure(
                    exposure=float(result.score),
                    price=entry_price,
                    max_notional=max_notional_cap,
                    leverage=target_leverage,
                    spec=spec,
                )

                if q_pos.reject_reason:
                    self.logger.warning(
                        f"[{symbol}] QUANTIZER_REJECT: {q_pos.reject_reason}")
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code="QUANTIZER_REJECT",
                        reason=q_pos.reject_reason,
                        context="aurora_handler:quantizer",
                        details={"exposure": result.score,
                                 "price": str(entry_price)},
                        why_chain=result.why_chain +
                        [f"QUANTIZER:{q_pos.reject_reason}"],
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
                ms.record_visit(symbol, features, bar_close_ts=int(
                    now_ms/1000), state_hash=state_hash)

        # === INJECT REGIME-BASED TP/SL INTO PAYLOAD ===
        if tpsl_result is not None:
            payload["price_ctx"]["stop_price"] = str(tpsl_result["stop_price"])
            payload["price_ctx"]["target_price"] = str(
                tpsl_result["target_price"])

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
