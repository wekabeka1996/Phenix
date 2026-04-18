"""Scoring-support helpers mixed into AuroraHandler.

This mixin normalizes symbol-level config overrides, builds the shield
cascade, and applies helper gates/state transforms around the Aurora decision
path. It does not own event registration or the main decision orchestration;
those responsibilities stay in AuroraHandler and AuroraDecisionMixin.
"""
from __future__ import annotations

import decimal
import logging
from typing import Any, Dict, List, Optional

from apps.reference.domains.decision_making.aurora_policy import SideBiasState
from apps.reference.domains.decision_making.shields.null_shield import NullShield
from apps.reference.domains.decision_making.shields.base import ShieldCascade
from apps.reference.domains.decision_making.shields.context_shield import ContextShield
from apps.reference.domains.decision_making.shields.memory_shield import MemoryShield
from apps.reference.domains.decision_making.shields.danger_zone import DangerZoneShield

logger = logging.getLogger("aurora_handler")


class AuroraScoringHelpersMixin:
    """Scoring helper methods shared by AuroraHandler and AuroraDecisionMixin."""

    # ------------------------------------------------------------------
    # Vol-Adj Gates (Anti-Flat / Anti-FOMO)
    # ------------------------------------------------------------------

    def _get_motion_norm_sigma(self, symbol: str, features: Dict[str, Any]) -> Optional[float]:
        """Return absolute motion sigma for the configured price-motion window.

        The primary source is features["price_motion"]. If CMD input omitted that
        block, the helper falls back to the cached EVT:FEATURES_CALCULATED copy
        stored on symbol state.
        """
        pm = features.get("price_motion")

        # CMD:PROCESS_STRATEGY may omit price_motion; the cached event copy keeps
        # vol-adj gates on the same FE contract instead of silently disabling them.
        if not isinstance(pm, dict):
            state = self._symbol_states.get(symbol)
            if state and state.cached_price_motion:
                pm = state.cached_price_motion

        if not isinstance(pm, dict):
            return None

        # The exact pm_norm_<window>s bucket is part of the FE payload contract.
        window_key = f"pm_norm_{self.motion_window_sec}s"
        val = pm.get(window_key)

        if val is None:
            return None

        try:
            return abs(float(val))
        except (TypeError, ValueError):
            return None

    def _apply_vol_adj_gates(
        self,
        symbol: str,
        result: Any,
        state: Any,
        features: Dict[str, Any],
        *,
        effective_side: str | None = None,
    ) -> bool:
        """Apply anti-flat and anti-FOMO gates to actionable entry proposals.

        Returns True when this helper already emitted a blocked event. Missing
        motion data is treated as unavailable evidence and left to readiness or
        cached-price-motion handling rather than causing a local block.
        """
        if not self.vol_gates_enabled:
            return False

        # Gate the post-policy actionable side, not just the raw kernel side.
        side = effective_side if effective_side is not None else result.side
        if not side or state.position_side != "":
            return False  # Not an entry, skip gates

        motion_norm_sigma = self._get_motion_norm_sigma(symbol, features)

        if motion_norm_sigma is None:
            # Readiness handles missing data, don't block here
            self.logger.debug(
                f"[{symbol}] VOL_GATES: motion_norm_sigma=None, skipping")
            return False

        # Anti-Flat gate: block entry in dead market
        if motion_norm_sigma < self.anti_flat_sigma:
            self.logger.info(
                f"[{symbol}] GATE_ANTI_FLAT_SIGMA: Blocking entry "
                f"(motion={motion_norm_sigma:.3f} < threshold={self.anti_flat_sigma})"
            )
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="GATE_ANTI_FLAT_SIGMA",
                reason="VOL_GATE",
                context="aurora_handler:anti_flat",
                details={
                    "motion_norm_sigma": motion_norm_sigma,
                    "threshold": self.anti_flat_sigma,
                    "window_sec": self.motion_window_sec,
                },
                why_chain=["VOL_GATE", "ANTI_FLAT",
                           f"motion:{motion_norm_sigma:.3f}"],
            )
            return True

        # Anti-FOMO gate: block entry in extreme impulse
        if motion_norm_sigma > self.anti_fomo_sigma:
            self.logger.info(
                f"[{symbol}] GATE_ANTI_FOMO_SIGMA: Blocking entry "
                f"(motion={motion_norm_sigma:.3f} > threshold={self.anti_fomo_sigma})"
            )
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="GATE_ANTI_FOMO_SIGMA",
                reason="VOL_GATE",
                context="aurora_handler:anti_fomo",
                details={
                    "motion_norm_sigma": motion_norm_sigma,
                    "threshold": self.anti_fomo_sigma,
                    "window_sec": self.motion_window_sec,
                },
                why_chain=["VOL_GATE", "ANTI_FOMO",
                           f"motion:{motion_norm_sigma:.3f}"],
            )
            return True

        self.logger.debug(
            f"[{symbol}] VOL_GATES: passed (motion={motion_norm_sigma:.3f} in "
            f"[{self.anti_flat_sigma}, {self.anti_fomo_sigma}])"
        )
        return False

    # ------------------------------------------------------------------
    # Signal Weights / Thresholds / Config Helpers
    # ------------------------------------------------------------------

    def _get_signal_weights(self, symbol: str, instr_cfg: Any) -> Dict[str, float]:
        """Return per-symbol signal weights or the global decision fallback.

        ``None`` means "no symbol override". An explicit empty mapping remains
        a valid override and must not fall back to the global weights.
        """
        weights = getattr(instr_cfg, "weights", None)
        if weights is not None:
            return dict(weights)

        decision = getattr(self.config.strategies.aurora, "decision", None)
        return dict(getattr(decision, "signal_weights", {})) if decision else {}

    def _build_shield_cascade(self, *, cfg: Any | None = None, record_memory_shield: bool = True):
        """Build the runtime shield object from a scoring-engine config surface.

        ``cfg`` may be a strict ScoringEngineConfig or a legacy/mock object.
        A real cascade is built only when shield_enabled is literally ``True``;
        this prevents truthy mocks from silently enabling live protection paths.

        When record_memory_shield=True and MemoryShield is active, the created
        instance is also stored on self._memory_shield for later visit recording.
        """
        cfg = self._scoring_engine_cfg if cfg is None else cfg
        if not cfg:
            return NullShield()
        shield_enabled_raw = getattr(cfg, "shield_enabled", False)
        # Guard: only build real cascade if shield_enabled is explicitly True (bool).
        # This prevents MagicMock or other non-bool truthy values from triggering cascade build.
        if shield_enabled_raw is not True:
            return NullShield()

        shields = []

    # These getattr defaults intentionally mirror the typed config defaults
    # so partial mocks behave like the strict config path instead of drifting
    # to arbitrary MagicMock truthiness.

        # DangerZone first — hard safety gate should veto earliest
        dz_cfg = getattr(cfg, "danger_zone_shield", None)
        if dz_cfg and getattr(dz_cfg, "enabled", True):
            shields.append(DangerZoneShield(
                vol_threshold=getattr(dz_cfg, "vol_threshold", 0.95),
                spread_threshold=getattr(dz_cfg, "spread_threshold", 50.0),
                motion_threshold=getattr(dz_cfg, "motion_threshold", 3.0),
            ))

        # Context next — regime-aware attenuation
        ctx_cfg = getattr(cfg, "context_shield", None)
        if ctx_cfg and getattr(ctx_cfg, "enabled", True):
            shields.append(ContextShield(
                regime_multipliers=dict(
                    getattr(ctx_cfg, "regime_multipliers", {})),
                default_multiplier=getattr(ctx_cfg, "default_multiplier", 1.0),
                no_regime_multiplier=getattr(
                    ctx_cfg, "no_regime_multiplier", 0.5),
                ttl_ms=getattr(ctx_cfg, "ttl_ms", 14_400_000),
                stale_mult_normal=getattr(ctx_cfg, "stale_mult_normal", 0.7),
                stale_mult_danger=getattr(ctx_cfg, "stale_mult_danger", 0.35),
                danger_regimes=list(
                    getattr(ctx_cfg, "danger_regimes", ["HIGH_VOLATILITY"])),
            ))

        # Memory last — state-familiarity (Doctrine v2.6)
        mem_cfg = getattr(cfg, "memory_shield", None)
        if mem_cfg and getattr(mem_cfg, "enabled", True):
            if self.mode_manager:
                mem_cfg = self.mode_manager.apply_memory_shield_overrides(
                    mem_cfg)

            ms = MemoryShield(
                decay_rate=getattr(mem_cfg, "decay_rate", 0.95),
                max_states=getattr(mem_cfg, "max_states", 200),
                unknown_threshold=getattr(mem_cfg, "unknown_threshold", 10),
                exploring_threshold=getattr(
                    mem_cfg, "exploring_threshold", 50),
                unknown_multiplier=getattr(mem_cfg, "unknown_multiplier", 0.6),
                exploring_multiplier=getattr(
                    mem_cfg, "exploring_multiplier", 0.8),
                known_multiplier=getattr(mem_cfg, "known_multiplier", 1.0),
                storage_path=getattr(mem_cfg, "storage_path", None),
                flush_interval_sec=getattr(
                    mem_cfg, "flush_interval_sec", 60.0),
            )
            shields.append(ms)
            if record_memory_shield:
                self._memory_shield = ms  # BUG-2: Store reference for manual recording

        if not shields:
            return NullShield()

        return ShieldCascade(shields)

    def _get_regime_thresholds(self, *, symbol: str, instr_cfg: Any) -> Dict[str, float]:
        """Return symbol-specific regime thresholds with global fallback."""
        thr = getattr(instr_cfg, "regime_thresholds", None)
        if isinstance(thr, dict) and thr:
            return dict(thr)
        try:
            return dict(getattr(self, "regime_thresholds", {}) or {})
        except Exception:
            return {}

    def _check_liquidity_gate(
        self,
        *,
        symbol: str,
        instr_cfg: Any,
        features: Dict[str, Any],
        warmup_readiness: Any,
    ) -> tuple[bool, Dict[str, Any]]:
        """Evaluate the resolved Aurora liquidity gate and return ``(allowed, ctx)``.

        The per-symbol gate comes from instr_cfg. The global fallback is the
        already-resolved host attribute ``self._global_liquidity_gate_cfg``;
        this helper does not traverse the config tree itself.

        Fail-closed behavior (when enabled):
        - warmup_readiness['liquidity_kappa'] must be True
        - features['liquidity_kappa'] must exist and be parseable
        - liquidity_kappa >= kappa_min
        """
        gate_cfg = getattr(instr_cfg, "liquidity_gate",
                           None) if instr_cfg is not None else None
        if gate_cfg is None:
            gate_cfg = getattr(self, "_global_liquidity_gate_cfg", None)

        enabled_raw = getattr(gate_cfg, "enabled",
                              False) if gate_cfg is not None else False
        if not isinstance(enabled_raw, bool) or not enabled_raw:
            return True, {}

        kappa_min_raw = getattr(gate_cfg, "kappa_min", None)
        kappa_max_raw = getattr(gate_cfg, "kappa_max", None)
        # LiquidityGateConfig marks this field as parsed-but-not-implemented;
        # keep surfacing it in diagnostics so callers can see the resolved value.
        failsafe_qty_check = bool(
            getattr(gate_cfg, "failsafe_qty_check", True))

        # Readiness contract: require liquidity_kappa readiness when gate is enabled.
        ready_flag = None
        if isinstance(warmup_readiness, dict):
            ready_flag = warmup_readiness.get("liquidity_kappa")
        if ready_flag is not True:
            return False, {
                "reason_code": "LIQUIDITY_NOT_READY",
                "kappa": None,
                "kappa_min": kappa_min_raw,
                "kappa_max": kappa_max_raw,
                "ready": ready_flag,
                "failsafe_qty_check": failsafe_qty_check,
            }

        kappa_raw = features.get("liquidity_kappa")
        if kappa_raw is None:
            return False, {
                "reason_code": "LIQUIDITY_MISSING",
                "kappa": None,
                "kappa_min": kappa_min_raw,
                "kappa_max": kappa_max_raw,
                "ready": ready_flag,
                "failsafe_qty_check": failsafe_qty_check,
            }

        try:
            kappa = decimal.Decimal(str(kappa_raw))
        except Exception:
            kappa = None
        if kappa is None or (hasattr(kappa, "is_finite") and not kappa.is_finite()):
            return False, {
                "reason_code": "LIQUIDITY_INVALID",
                "kappa": str(kappa_raw),
                "kappa_min": kappa_min_raw,
                "kappa_max": kappa_max_raw,
                "ready": ready_flag,
                "failsafe_qty_check": failsafe_qty_check,
            }

        # Clamp (defensive only; FE already clamps using its own config).
        try:
            if kappa_max_raw is not None:
                kappa_max = decimal.Decimal(str(kappa_max_raw))
                if kappa > kappa_max:
                    kappa = kappa_max
        except Exception:
            pass

        try:
            kappa_min = decimal.Decimal(
                str(kappa_min_raw)) if kappa_min_raw is not None else decimal.Decimal("0")
        except Exception:
            # Strict typed configs should make this parseable. Legacy mocks fall
            # back to zero here so the handler stays observable instead of crashing.
            kappa_min = decimal.Decimal("0")

        if kappa < kappa_min:
            return False, {
                "reason_code": "LIQUIDITY_LOW",
                "kappa": str(kappa),
                "kappa_min": str(kappa_min),
                "kappa_max": str(kappa_max_raw) if kappa_max_raw is not None else None,
                "ready": ready_flag,
                "failsafe_qty_check": failsafe_qty_check,
            }

        return True, {}

    def _get_feature_neutrals(self, symbol: str, instr_cfg: Any) -> Dict[str, float]:
        """Return per-symbol neutral offsets or the global decision fallback.

        ``None`` means "no symbol override". An explicit empty mapping remains
        a valid override and must not fall back to the global neutrals.
        """
        neutrals = getattr(instr_cfg, "feature_neutrals", None)
        if neutrals is not None:
            return dict(neutrals)

        decision = getattr(self.config.strategies.aurora, "decision", None)
        return dict(getattr(decision, "feature_neutrals", {})) if decision else {}

    def _get_essential_features(self, symbol: str, instr_cfg: Any) -> List[str]:
        """Return per-symbol essential features or the global decision fallback.

        ``None`` means "no symbol override". An explicit empty list remains a
        valid override and must not fall back to the global requirement set.
        """
        essential = getattr(instr_cfg, "essential_features", None)
        if essential is not None:
            return list(essential)

        decision = getattr(self.config.strategies.aurora, "decision", None)
        return list(getattr(decision, "essential_features", [])) if decision else []

    def _get_side_bias_state(self, symbol: str) -> SideBiasState:
        """Build SideBiasState and prune expired side-bias history in place.

        This is not a pure getter: old timestamps are removed from the cached
        buy/sell history so repeated decisions share the same windowed state.
        """
        instr_cfg = self._get_instrument_config(symbol)
        penalty_factor = self.side_bias_penalty_factor
        window_sec = self.side_bias_window_sec
        target_ratio = self.side_bias_target_ratio
        min_intents = self.side_bias_min_intents

        # Per-symbol side_bias config currently overrides only the bias-shape
        # parameters; min_intents remains a global DecisionConfig contract.
        sb_cfg = getattr(instr_cfg, "side_bias",
                         None) if instr_cfg is not None else None
        if sb_cfg is not None:
            try:
                pen = getattr(sb_cfg, "penalty_factor", None)
                if pen is not None:
                    penalty_factor = float(pen)
                win = getattr(sb_cfg, "window_sec", None)
                if win is not None:
                    window_sec = float(win)
                targ = getattr(sb_cfg, "target_ratio", None)
                if targ is not None:
                    target_ratio = float(targ)
            except Exception:
                # Fail-safe: keep global values if override parsing fails
                pass

        state = self._symbol_states[symbol]
        now = float(self.wall_time_fn())

        # Prune in place so cached history stays bounded and all later calls see
        # the same rolling window rather than re-counting stale timestamps.
        state.buy_timestamps = [
            ts for ts in state.buy_timestamps if now - ts < window_sec]
        state.sell_timestamps = [
            ts for ts in state.sell_timestamps if now - ts < window_sec]

        return SideBiasState(
            buy_count=len(state.buy_timestamps),
            sell_count=len(state.sell_timestamps),
            window_sec=window_sec,
            target_ratio=target_ratio,
            penalty_factor=penalty_factor,
            min_intents=min_intents,
        )

    def _update_side_bias(self, symbol: str, side: str) -> None:
        """Append the current wall-clock timestamp for BUY or SELL emissions."""
        state = self._symbol_states[symbol]
        now = float(self.wall_time_fn())

        if side.lower() == "buy":
            state.buy_timestamps.append(now)
        elif side.lower() == "sell":
            state.sell_timestamps.append(now)
