"""Decision-processing mixin for AuroraHandler.

This module orchestrates the per-symbol decision path around the scoring
kernel. It applies readiness and policy gates, records diagnostic traces, and
builds the EVT:STRATEGY_SIGNAL_PRODUCED payload with runtime readiness data.

Aurora semantics on this path are intentionally strict:
- ordinary live denials should surface as STRATEGY_DECISION_BLOCKED;
- EVT:INTENT_DEFERRED is reserved for kernel-side anomaly or fail-closed
    outcomes after the quadratic path has already been reached.
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
)
from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    extract_canonical_bar_identity,
    extract_canonical_replay_identity,
)
from apps.reference.contracts.runtime_gap_policy import (
    attach_gap_status_payload,
    extract_gap_status,
    gap_blocks_open_new_risk,
)
from apps.reference.contracts.runtime_regime_layers import (
    build_regime_provenance_fields,
)
from apps.reference.contracts.runtime_readiness import (
    RuntimePermissions,
    RuntimeReadinessScope,
    cold_status,
    make_permissions,
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
from apps.reference.domains.decision_making.runtime_readiness_builder import (
    RestoreScopeSpec,
    RuntimeReadinessBuildRequest,
    build_runtime_readiness,
)
from apps.reference.domains.decision_making.decision_truth_artifacts import (
    canonicalize_intent_deferred_reason,
    write_intent_deferred,
)
from apps.reference.domains.decision_making.entry_plan import EntryPlanResult
from apps.reference.domains.decision_making.tpsl_owner import (
    TPSL_OWNER_ENTRY_PLAN,
    TPSL_OWNER_REGIME_TPSL,
    build_tpsl_owner_ctx,
)
from apps.reference.domains.regime_allowlist.contract import RegimeAllowlistContract
from apps.reference.domains.decision_making.instrument_quantizer import (
    quantize_exposure,
    InstrumentSpec as QuantizerSpec,
)
from apps.reference.domains.decision_making.trade_intent_reject_wal import (
    write_trade_intent_rejected,
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
        """Build a serializable trace for operator-facing quadratic diagnostics.

        The trace prefers kernel explainability fields from ``psi_vector`` and
        backfills a small set of values from the handler inputs when the kernel
        did not populate them explicitly.
        """
        psi = result.psi_vector or {}
        shield_multiplier = float(
            getattr(result, "shield_multiplier", 1.0) or 1.0
        )
        admission_shield_multiplier = float(
            getattr(result, "admission_shield_multiplier", shield_multiplier)
            or shield_multiplier
        )
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
            "raw_score": psi.get("s_linear"),
            "score_multiplier": psi.get("multiplier", getattr(self, "score_multiplier", 1.0)),
            "admission_mode": psi.get("admission_mode", getattr(self, "decision_admission_mode", "quadratic")),
            "sizing_mode": psi.get("sizing_mode", getattr(self, "decision_sizing_mode", "quadratic")),
            "s_scaled_raw": psi.get("s_scaled_raw"),
            "s_clamped": psi.get("s_clamped"),
            "raw_exposure": psi.get("raw_exposure"),
            "shield_multiplier": psi.get("shield_multiplier", shield_multiplier),
            "admission_shield_multiplier": psi.get("admission_shield_multiplier", admission_shield_multiplier),
            "shield_reasons": shield_reasons,
            "decision_score": psi.get("decision_score", float(getattr(result, "decision_score", getattr(result, "score", 0.0)))),
            "sizing_score": psi.get("sizing_score", float(getattr(result, "sizing_score", getattr(result, "score", 0.0)))),
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
            "admission_result": "side" if getattr(result, "side", "") else "neutral",
            "deferred": bool(getattr(result, "deferred", False)),
            "defer_reason": getattr(result, "defer_reason", None),
            "side_why": psi.get("side_why"),
        }

    def _compact_quadratic_decision_trace(
        self,
        trace: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        """Keep only the stable trace fields reused by blocked/deferred payloads."""
        if not isinstance(trace, dict):
            return {}
        keys = (
            "regime",
            "raw_sum",
            "raw_score",
            "admission_mode",
            "sizing_mode",
            "raw_exposure",
            "shield_multiplier",
            "admission_shield_multiplier",
            "decision_score",
            "sizing_score",
            "final_score",
            "thr_buy",
            "thr_sell",
            "threshold_factor",
            "admission_result",
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
        Process one CMD:PROCESS_STRATEGY payload for a single symbol.

        The method is intentionally side-effectful: it updates symbol state,
        may enrich the incoming ``features`` mapping with missing regime/bar
        identity fields, and emits one of the strategy blocked, deferred, trace,
        or signal events depending on where the decision path stops.
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

        # Warmup ownership lives upstream. The handler only mirrors the flag so
        # emitted diagnostics can explain which readiness evidence was present.
        state = self._symbol_states[symbol]
        state.warmup_full_ready = bool(warmup.get("full_ready", False))

        # Reject stale regime state before touching the kernel; downstream
        # scoring assumes the cached regime heartbeat is still current.
        liveness_block = self._check_regime_liveness(symbol, state)
        if liveness_block is not None:
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code=liveness_block["reason_code"],
                reason="LIVENESS",
                context="aurora_handler:regime_liveness_guard",
                rid=cmd.get("rid"),
                why=liveness_block["why"],
                details=liveness_block.get("details", {}),
                why_chain=["LIVENESS", liveness_block["reason_code"]],
                tf_sec=int(cmd.get("tf_sec") or 0),
                bar_close_ts=cmd.get("bar_close_ts"),
            )
            return

        # The compatibility profile defines how many live bars are required
        # before this handler may trust regime/features enough to trade.
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
            # These gates stop the bar before any actionable signal exists, so
            # they also write a reject WAL record for forensic continuity.
            write_trade_intent_rejected(
                symbol=symbol,
                strategy_id=self.strategy_id,
                tf_sec=int(cmd.get("tf_sec") or self.timeframe_sec or 0),
                bar_close_ts=cmd.get("bar_close_ts"),
                reason_code="READINESS_CONTRACT_UNRESOLVED",
                stage="STRATEGY",
                why="aurora_handler:readiness_contract_unresolved",
                src="aurora_handler",
                ts_ms=cmd.get("bar_close_ts"),
                rid=cmd.get("rid"),
                context="aurora_handler:basis_required_resolution",
                why_chain=["READINESS", "READINESS_CONTRACT_UNRESOLVED"],
                details={"error": _readiness_contract_error},
            )
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
            cold_start_why = f"Cold-start: {_bars_seen}/{_basis_required} bars seen"
            cold_start_details = {
                "bars_seen": _bars_seen,
                "basis_required_bars": _basis_required,
            }
            cold_start_why_chain = [
                "READINESS",
                "BARS_REQUIRED",
                f"bars_seen:{_bars_seen}",
                f"basis_required:{_basis_required}",
            ]
            write_trade_intent_rejected(
                symbol=symbol,
                strategy_id=self.strategy_id,
                tf_sec=int(cmd.get("tf_sec") or self.timeframe_sec or 0),
                bar_close_ts=cmd.get("bar_close_ts"),
                reason_code="BARS_REQUIRED_COLD_START",
                stage="STRATEGY",
                why=cold_start_why,
                src="aurora_handler",
                ts_ms=cmd.get("bar_close_ts"),
                rid=cmd.get("rid"),
                context="aurora_handler:bars_required_gate",
                why_chain=cold_start_why_chain,
                details=cold_start_details,
            )
            self.logger.info(
                "[%s] BARS_REQUIRED gate: %d/%d bars — blocking signal (quadratic path NOT reached)",
                symbol, _bars_seen, _basis_required,
            )
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="BARS_REQUIRED_COLD_START",
                reason="READINESS",
                context="aurora_handler:bars_required_gate",
                rid=cmd.get("rid"),
                why=cold_start_why,
                details=cold_start_details,
                why_chain=cold_start_why_chain,
                tf_sec=int(cmd.get("tf_sec") or 0),
                bar_close_ts=cmd.get("bar_close_ts"),
            )
            return

        # Price is a hard precondition for kernel scoring and every downstream
        # payload branch in this method.
        price = features.get("price")
        if price is None:
            self.logger.warning(f"[{symbol}] Missing price in features")
            return
        price_dec = decimal.Decimal(str(price))

        # These helpers normalize symbol-level overrides so the kernel can work
        # against a stable input contract.
        signal_weights = self._get_signal_weights(symbol, instr_cfg)
        feature_neutrals = self._get_feature_neutrals(symbol, instr_cfg)
        essential_features = self._get_essential_features(symbol, instr_cfg)

        # Liquidity gating happens before the kernel so a normal live denial is
        # reported as STRATEGY_DECISION_BLOCKED instead of a deferred kernel
        # outcome.
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

        # Resolve macro-veto inputs once up front. Parse failures stay
        # observable via logging but do not crash the decision path.
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

        # Instrument overrides adjust admission thresholds without mutating the
        # handler defaults shared by other symbols.
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
        bar_close_ts_raw = (
            int(bar_identity.bar_end_ts_ms)
            if bar_identity is not None
            else cmd.get("bar_close_ts")
        )
        # Some downstream contracts expect these fields inside ``features`` even
        # when upstream omitted them. Only fill missing keys so upstream values
        # remain the source of truth when present.
        if "regime" not in features:
            features["regime"] = state.regime
        if "regime_ts_ms" not in features:
            features["regime_ts_ms"] = state.regime_ts_ms
        if "bar_close_ts" not in features:
            if bar_close_ts_raw is not None:
                features["bar_close_ts"] = int(bar_close_ts_raw)
        regime_provenance = build_regime_provenance_fields(
            {
                "regime": state.regime,
                "regime_event_ts_ms": state.regime_event_ts_ms or state.regime_ts_ms,
            },
            bar_close_ts_ms=(
                int(bar_close_ts_raw)
                if bar_close_ts_raw is not None
                else features.get("bar_close_ts")
            ),
            missing_heartbeat=state.last_regime_heartbeat_ms is None,
        )
        for key, value in regime_provenance.items():
            if key not in features:
                features[key] = value

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
            admission_mode=getattr(
                self, "decision_admission_mode", "quadratic"),
            admission_power=getattr(self, "decision_admission_power", None),
            sizing_mode=getattr(self, "decision_sizing_mode", "quadratic"),
            sizing_power=getattr(self, "decision_sizing_power", None),
            admission_shield_floor=getattr(
                self, "decision_admission_shield_floor", 0.0),
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
            # Kernel crashes stay fail-closed. The rollout contract no longer
            # provides a legacy v2 fallback path, so this branch must emit
            # diagnostics and stop the bar from producing a signal.
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

        # Emit a compact trace both to logs and as an event so blocked/deferred
        # investigations can correlate the same scoring snapshot.
        compact_trace = self._compact_quadratic_decision_trace(decision_trace)
        shield_multiplier = float(
            getattr(result, "shield_multiplier", 1.0) or 1.0
        )
        admission_shield_multiplier = float(
            getattr(result, "admission_shield_multiplier", shield_multiplier)
            or shield_multiplier
        )
        self.logger.info(
            "[%s] QUADRATIC_DECISION_TRACE score=%.6f decision_score=%.6f sizing_score=%.6f side=%s deferred=%s regime=%s",
            symbol,
            float(result.score),
            float(getattr(result, "decision_score", result.score)),
            float(getattr(result, "sizing_score", result.score)),
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
                "raw_score": float(getattr(result, "raw_score", 0.0)),
                "decision_score": float(getattr(result, "decision_score", result.score)),
                "sizing_score": float(getattr(result, "sizing_score", result.score)),
                "side": str(result.side),
                "deferred": bool(result.deferred),
                "defer_reason": str(result.defer_reason) if result.defer_reason else None,
                "regime": str(state.regime),
                "shield_multiplier": shield_multiplier,
                "admission_shield_multiplier": admission_shield_multiplier,
                "thr_buy": str(result.thr_buy) if result.thr_buy is not None else None,
                "thr_sell": str(result.thr_sell) if result.thr_sell is not None else None,
                "admission_mode": str(getattr(self, "decision_admission_mode", "quadratic")),
                "sizing_mode": str(getattr(self, "decision_sizing_mode", "quadratic")),
                "quadratic_path_reached": True,
                "compact_trace": compact_trace,
                "ts_ms": int(self.wall_time_fn() * 1000),
            })
        except Exception:
            pass  # Best-effort telemetry

        # Kernel visibility log
        _psi = result.psi_vector or {}
        self.logger.info(
            "[%s] KERNEL_DIAG: engine=%s admission=%s sizing=%s s_linear=%.4f decision_score=%.6f sizing_score=%.6f "
            "shield_mult=%.3f admission_shield_mult=%.3f deferred=%s defer_reason=%s side=%s thr_buy=%s thr_sell=%s",
            symbol,
            _psi.get("scoring_engine", "?"),
            _psi.get("admission_mode", "quadratic"),
            _psi.get("sizing_mode", "quadratic"),
            float(_psi.get("s_linear", 0.0)),
            float(getattr(result, "decision_score", result.score)),
            float(getattr(result, "sizing_score", result.score)),
            shield_multiplier,
            admission_shield_multiplier,
            result.deferred,
            result.defer_reason or "-",
            result.side,
            result.thr_buy,
            result.thr_sell,
        )

        # Aurora-specific semantics: once the quadratic path has been reached,
        # deferred is reserved for anomaly/fail-closed kernel outcomes.
        # Normal live policy denials should already have surfaced as
        # STRATEGY_DECISION_BLOCKED via explicit gates.
        if result.deferred:
            self.logger.debug(
                f"[{symbol}] Kernel deferred: {result.defer_reason}")
            defer_reason_raw = str(result.defer_reason or "NRR-DATA-NOT-READY")
            canonical_reason, reason_code, raw_reason = canonicalize_intent_deferred_reason(
                defer_reason_raw
            )
            created_ts = int(self.wall_time_fn() * 1000)
            original_event_payload = {
                "symbol": symbol,
                "tf_sec": int(cmd.get("tf_sec") or self.timeframe_sec or 0),
                "bar_close_ts": cmd.get("bar_close_ts"),
                "bar": dict(cmd.get("bar") or {}),
                "features": dict(cmd.get("features") or {}),
                "warmup": dict(cmd.get("warmup") or {}),
                "rid": cmd.get("rid"),
                "strategy_id": self.strategy_id,
            }
            if isinstance(cmd.get("regime"), dict):
                original_event_payload["regime"] = dict(
                    cmd.get("regime") or {})
            elif cmd.get("regime") is not None:
                original_event_payload["regime"] = cmd.get("regime")
            if raw_reason:
                original_event_payload["raw_defer_reason"] = raw_reason
            retry_payload = write_intent_deferred(
                symbol=symbol,
                reason=canonical_reason,
                reason_code=reason_code,
                retry_key=f"aurora-kernel:{symbol}:{cmd.get('bar_close_ts') or created_ts}",
                next_allowed_ts=created_ts + 1000,
                attempt=1,
                max_attempts=3,
                original_event={
                    "event_name": "CMD:PROCESS_STRATEGY",
                    "payload_min": original_event_payload,
                },
                src="aurora_handler",
                ts_ms=created_ts,
                rid=cmd.get("rid"),
                why_chain=["KERNEL_DEFERRED", canonical_reason],
                context="aurora_handler:kernel_deferred",
                retry_policy={
                    "attempt": 1,
                    "max_attempts": 3,
                    "backoff_ms": 1000,
                    "ttl_ms": 5000,
                },
                raw_reason=raw_reason,
            )
            retry_payload["details"] = {
                "decision_trace": self._compact_quadratic_decision_trace(
                    decision_trace
                )
            }
            self.emit_fn("EVT:INTENT_DEFERRED", retry_payload)
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

        # Exit management can override the actionable side or tighten the stop
        # loss, but it does not rewrite the raw kernel result.
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

        # Holding-period policy may force a hold on soft exits/flips while
        # leaving the original scoring result intact for diagnostics.
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

        # Re-entry cooldown applies only after a real exit was recorded in state.
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

        # Volatility-adjusted gates own their own blocked-event emission.
        if self._apply_vol_adj_gates(symbol, result, state, features, effective_side=effective_side):
            return

        # The anchor veto is intentionally asymmetric: it only blocks long risk
        # when the configured macro residual breaches the downside threshold.
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

        # Downstream planners and gates must consume the post-policy side that
        # will actually be emitted, while result.side remains the raw kernel output.
        canonical_side = str(effective_side).lower()

        # Entry planning and execution gating only run when the handler was
        # wired with an execution gate; otherwise the raw strategy signal is
        # emitted after the decision-phase checks above.
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
                    side=canonical_side,
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
                result.thr_buy if canonical_side == "buy" else result.thr_sell)

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
                from apps.reference.domains.decision_making.objective_gate_evaluator import (
                    ObjectiveBehaviorAdapter,
                    ObjectiveGateRequest,
                    ObjectiveGateStatus,
                    ObjectiveSignalAdapter,
                    ObjectiveSizingAdapter,
                    ObjectiveStructureAdapter,
                    evaluate_objective_gate,
                )

                if state.regime_confidence is None:
                    self.logger.debug(
                        "[%s] Objective precondition not met: %s",
                        symbol, "OBJECTIVE_REGIME_CONFIDENCE_MISSING",
                    )
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code="OBJECTIVE_PRECONDITION_NOT_MET",
                        reason="DECISION",
                        context="aurora_handler:objective_engine",
                        details={
                            "precondition": "OBJECTIVE_REGIME_CONFIDENCE_MISSING"},
                        why_chain=["OBJECTIVE_ENGINE",
                                   "PRECONDITION_NOT_MET",
                                   "OBJECTIVE_REGIME_CONFIDENCE_MISSING"],
                    )
                    return

                _now_ms = int(self.wall_time_fn() * 1000)
                obj_gate_result = evaluate_objective_gate(ObjectiveGateRequest(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    config=self.config,
                    domain_cfg=domain_cfg,
                    strategy_cfg=strategy_cfg,
                    market_features=features,
                    signal=ObjectiveSignalAdapter(
                        signal_score=float(result.score),
                        signal_direction=1 if canonical_side == "buy" else -1,
                        regime_name=str(state.regime),
                        regime_ts_ms=int(
                            state.regime_ts_ms) if state.regime_ts_ms else 0,
                        regime_confidence=float(state.regime_confidence),
                        readiness_source=warmup_readiness,
                        active_threshold=active_threshold,
                    ),
                    structure=ObjectiveStructureAdapter(
                        mode="entry_plan",
                        entry_plan=entry_plan_res,
                    ),
                    sizing=ObjectiveSizingAdapter(
                        side=canonical_side.upper(),
                        entry_price=decimal.Decimal(
                            str(entry_plan_res.entry_price)),
                        features_payload=cmd.get("features") if isinstance(
                            cmd.get("features"), dict) else {},
                        margin_pct_mult=decimal.Decimal(str(micro_fraction)),
                    ),
                    behavior=ObjectiveBehaviorAdapter(
                        now_ms=_now_ms,
                        cancel_replace_ts_ms=state.objective_cancel_replace_ts_ms,
                        blocked_intent_ts_ms=state.objective_blocked_ts_ms,
                        reentry_ts_ms=state.objective_reentry_ts_ms,
                    ),
                    portfolio=self._latest_portfolio,
                    exposure_summary=self._latest_exposure_summary,
                    position_queries=self._position_queries,
                ))

                if obj_gate_result.status == ObjectiveGateStatus.PRECONDITION_FAILED:
                    self.logger.debug(
                        "[%s] Objective precondition not met: %s",
                        symbol, obj_gate_result.precondition_code,
                    )
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code="OBJECTIVE_PRECONDITION_NOT_MET",
                        reason="DECISION",
                        context="aurora_handler:objective_engine",
                        details={
                            "precondition": obj_gate_result.precondition_code},
                        why_chain=["OBJECTIVE_ENGINE",
                                   "PRECONDITION_NOT_MET",
                                   str(obj_gate_result.precondition_code)],
                    )
                    return

                if obj_gate_result.status == ObjectiveGateStatus.GATE_BLOCKED:
                    obj_score = obj_gate_result.objective_score
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

                if obj_gate_result.status == ObjectiveGateStatus.EVALUATION_ERROR:
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code="OBJECTIVE_ENGINE_FAIL_CLOSED",
                        reason="DECISION",
                        context="aurora_handler:objective_engine",
                        details={"error": str(obj_gate_result.error)},
                        why_chain=["OBJECTIVE_ENGINE",
                                   "FAIL_CLOSED", str(obj_gate_result.error)],
                    )
                    return

                if obj_gate_result.status == ObjectiveGateStatus.PASSED:
                    obj_score = obj_gate_result.objective_score
                    result.score = decimal.Decimal(
                        str(obj_score.objective_score))
                    if not result.psi_vector:
                        result.psi_vector = {}
                    result.psi_vector["objective"] = obj_gate_result.trace_payload

            gate_ok, gate_reason = self.execution_gate.check_entry(
                symbol=symbol,
                side=canonical_side,
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
                effective_side=canonical_side,
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
                effective_side=canonical_side,
                micro_fraction=micro_fraction,
                quadratic_shadow_evaluation=quadratic_shadow_evaluation,
            )

        # Update side bias history
        self._update_side_bias(symbol, canonical_side)

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
        """Emit EVT:STRATEGY_SIGNAL_PRODUCED with runtime readiness metadata.

        This helper assumes the upstream decision path has already selected an
        actionable side and validated the basic signal inputs. It may still fail
        closed locally when payload-specific prerequisites such as ATR-based
        entry pricing or instrument quantization are unavailable.
        """
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

        # Entry price starts from the bar price and is refined either by the
        # entry-plan result or by the legacy volatility/regime TPSL helpers.
        anchor_price = decimal.Decimal(str(features.get("price", "0")))
        entry_price = anchor_price

        tpsl_result = None
        tpsl_owner_ctx = None

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
            tpsl_owner_ctx = build_tpsl_owner_ctx(
                intended_owner=TPSL_OWNER_ENTRY_PLAN,
                final_owner=TPSL_OWNER_ENTRY_PLAN,
                owner_loss_reason=None,
            )
        else:
            # When no explicit entry plan was produced, build the payload prices
            # from the older regime-aware TPSL path used by existing consumers.
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
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code="VOLATILITY_ENTRY_MULTIPLIER_MISSING",
                        reason="CONFIG",
                        context="aurora_handler:volatility_entry",
                        details={
                            "regime": regime,
                            "configured_regimes": sorted(str(key) for key in multipliers.keys()),
                        },
                        why_chain=[
                            "VOLATILITY_ENTRY",
                            "REGIME_MULTIPLIER_MISSING",
                            "FAIL_CLOSED",
                        ],
                    )
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
            tpsl_owner_ctx = build_tpsl_owner_ctx(
                intended_owner=TPSL_OWNER_REGIME_TPSL,
                final_owner=(
                    TPSL_OWNER_REGIME_TPSL if tpsl_result is not None else None
                ),
                owner_loss_reason=self._get_tpsl_owner_loss_reason(),
            )

        # Exit manager is allowed to tighten the emitted stop without changing
        # the rest of the TP/SL payload construction.
        if stop_loss_override is not None and tpsl_result:
            tpsl_result["stop_price"] = stop_loss_override
            tpsl_result["tpsl_ctx"]["mode"] = "EXIT_MANAGER_OVERRIDE"

        # Runtime readiness is snapshotted at emit time so downstream consumers
        # can see the exact permissions and evidence that accompanied the signal.
        restore_snapshot = self.get_runtime_analytics_restore_snapshot(symbol)
        decision_cfg = getattr(
            getattr(getattr(self.config, "strategies", None), "aurora", None),
            "decision",
            None,
        )
        requested_rollout = resolve_requested_quadratic_rollout(decision_cfg)

        # ── Quadratic HTF scope (Aurora-local) ───────────────────────
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
        # Pre-merge PILLAR_STATE restore into quadratic scope so the rollout
        # snapshot sees the merged value.
        if restore_snapshot is not None:
            quadratic_htf_status = merge_restore_readiness_live_first(
                lookup_restore_status(
                    restore_snapshot,
                    RuntimeAnalyticsRestoreScope.PILLAR_STATE,
                ),
                live_status=quadratic_htf_status,
                updated_at=now_ms,
                source="feature_engineering:startup_restore",
                evidence_ref=f"pillars:{symbol}:{now_ms}",
                live_evidence_present=True,
            )

        # Build quadratic rollout using pre-merged scope.
        # Permissions must include restore-merge so nested rollout semantics
        # are consistent with top-level runtime_permissions.
        _base_perms_for_rollout = make_permissions(
            can_manage_existing_risk=True,
            can_open_new_risk=not gap_blocks_open_new_risk(gap_status),
        )
        _rollout_perms = combine_restore_permissions_live_first(
            _base_perms_for_rollout,
            restore_snapshot,
        )
        quadratic_rollout = build_quadratic_rollout_snapshot(
            requested_rollout=requested_rollout,
            quadratic_readiness=quadratic_htf_status,
            runtime_permissions=_rollout_perms,
            shadow_evaluation=(
                quadratic_shadow_evaluation
                if quadratic_shadow_evaluation is not None
                else not_requested_shadow_evaluation()
            ),
        )

        # ── Permission overlay: quadratic gate ───────────────────────
        def _quadratic_overlay(
            perms: RuntimePermissions,
        ) -> tuple[RuntimePermissions, tuple[str, ...]]:
            gated = apply_live_quadratic_permission_gate(
                perms, quadratic_rollout)
            return gated, tuple(quadratic_rollout.quadratic_blocking_reason_chain)

        # ── Restore specs (everything except PILLAR_STATE) ───────────
        restore_specs: tuple[RestoreScopeSpec, ...] = ()
        if restore_snapshot is not None:
            restore_specs = (
                RestoreScopeSpec(
                    restore_scope=RuntimeAnalyticsRestoreScope.EXECUTION_STATE,
                    target_scope=RuntimeReadinessScope.EXECUTION_CONTEXT_READY.value,
                    mode="restore_only",
                    source="execution_position:startup_restore",
                    evidence_ref=f"execution:{symbol}:{now_ms}",
                ),
                RestoreScopeSpec(
                    restore_scope=RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_CACHE,
                    target_scope=RuntimeReadinessScope.MICROSTRUCTURE_READY.value,
                    mode="merge_live_first",
                    source="feature_engineering:startup_restore",
                    evidence_ref=f"fe_cache:{symbol}:{now_ms}",
                    live_evidence_present=True,
                ),
                RestoreScopeSpec(
                    restore_scope=RuntimeAnalyticsRestoreScope.REGIME_DETECTOR_STATE,
                    target_scope=RuntimeReadinessScope.REGIME_READY.value,
                    mode="merge_live_first",
                    source="regime_detector:startup_restore",
                    evidence_ref=f"regime:{symbol}:{now_ms}",
                    live_evidence_present=True,
                ),
                RestoreScopeSpec(
                    restore_scope=RuntimeAnalyticsRestoreScope.DECISION_CACHE,
                    target_scope=RuntimeReadinessScope.STRATEGY_READY_PER_SYMBOL.value,
                    mode="merge_live_first",
                    source="decision_making:startup_restore",
                    evidence_ref=f"decision_cache:{symbol}:{now_ms}",
                    restored_why=("signal_emitted",),
                    live_evidence_present=True,
                ),
            )

        # ── Delegate to shared builder ───────────────────────────────
        builder_result = build_runtime_readiness(
            RuntimeReadinessBuildRequest(
                strategy_id=self.strategy_id,
                symbol=symbol,
                updated_at=now_ms,
                source_prefix="decision_making:aurora",
                gap_status=gap_status,
                restore_snapshot=restore_snapshot,
                bar_identity=bar_identity,
                base_can_open_new_risk=True,
                warmup_ready=state.warmup_full_ready,
                regime_present=bool(state.regime and state.regime_ts_ms),
                regime_ts_ms=state.regime_ts_ms,
                regime_ready_why="regime_heartbeat_present",
                regime_missing_why="regime_heartbeat_missing",
                regime_live_source="regime_detector:payload_bridge",
                regime_ready_evidence_ref=f"regime:{symbol}:{state.regime_ts_ms or now_ms}",
                regime_missing_evidence_ref=f"regime:{symbol}:{now_ms}",
                signal_evidence_ref=f"signal:{symbol}:{now_ms}",
                strategy_ready_why=("signal_emitted",),
                restore_specs=restore_specs,
                extra_scopes={
                    RuntimeReadinessScope.QUADRATIC_HTF_READY.value: quadratic_htf_status,
                },
                permission_overlay=_quadratic_overlay,
            ),
        )
        runtime_permissions = builder_result.permissions
        runtime_snapshot = builder_result.snapshot
        blocking_reason_chain = list(builder_result.blocking_reason_chain)
        shield_multiplier_total = float(
            getattr(result, "shield_multiplier", 1.0) or 1.0
        )
        admission_shield_multiplier = float(
            getattr(result, "admission_shield_multiplier",
                    shield_multiplier_total)
            or shield_multiplier_total
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
                "raw_score": float(getattr(result, "raw_score", 0.0)),
                "decision_score": float(getattr(result, "decision_score", result.score)),
                "sizing_score": float(getattr(result, "sizing_score", result.score)),
                "thr_buy": float(result.thr_buy),
                "thr_sell": float(result.thr_sell),
                "regime": result.regime,
                "psi_vector": result.psi_vector,
                "objective": (result.psi_vector or {}).get("objective"),
                "admission_mode": str(getattr(self, "decision_admission_mode", "quadratic")),
                "sizing_mode": str(getattr(self, "decision_sizing_mode", "quadratic")),
                "shield_multiplier_total": shield_multiplier_total,
                "admission_shield_multiplier": admission_shield_multiplier,
                "admission_result": "side" if side else "neutral",
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
                "regime_event_ts_ms": regime_provenance.get("regime_event_ts_ms"),
                "regime_source": regime_provenance.get("regime_source"),
                "regime_same_bar": regime_provenance.get("regime_same_bar"),
                "regime_provenance_reason": regime_provenance.get("regime_provenance_reason"),
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
        if tpsl_owner_ctx is not None:
            payload["tpsl_owner_ctx"] = tpsl_owner_ctx

        # Quantization is applied only when instrument precision metadata is
        # available; a reject here blocks emission because the payload would not
        # correspond to an executable order size.
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
                    exposure=float(
                        getattr(result, "sizing_score", result.score)),
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

        # Memory-shield recording is best-effort and only runs when the scoring
        # result exposed a stable state hash to deduplicate visits.
        ms = getattr(self, "_memory_shield", None)
        if ms:
            sh_details = getattr(result, "details", {}) or {}
            state_hash = sh_details.get("memory_state_hash")
            if state_hash:
                ms.record_visit(symbol, features, bar_close_ts=int(
                    now_ms/1000), state_hash=state_hash)

        # Attach TP/SL context only after all local fail-closed checks passed so
        # the emitted payload stays internally consistent.
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

        if tpsl_owner_ctx is not None:
            self.logger.info(
                "[%s] TPSL_OWNER_SIGNAL intended=%s final=%s reason=%s",
                symbol,
                tpsl_owner_ctx.get("intended_owner"),
                tpsl_owner_ctx.get("final_owner"),
                tpsl_owner_ctx.get("owner_loss_reason"),
            )

        self.logger.info(
            f"[{symbol}] SIGNAL: {side.upper()} score={float(result.score):.4f} "
            f"(thr_buy={float(result.thr_buy):.4f}, thr_sell={float(result.thr_sell):.4f})"
        )

        self.emit_fn("EVT:STRATEGY_SIGNAL_PRODUCED", payload)

        # Update state
        state.last_signal_ts_ms = now_ms
        state.last_signal_side = side
