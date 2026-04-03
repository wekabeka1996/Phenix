"""Load Aurora strategy and domain config into handler runtime state.

The mixin translates the Aurora config tree into concrete handler attributes and
helper objects used later by AuroraHandler. It does not emit signals or resolve
per-symbol state on its own; its job is to materialize configuration contracts
into deterministic runtime fields.

Two config surfaces are supported:
- strict Pydantic AuroraConfig objects, which fail closed on missing fields;
- legacy/mock objects, which retain local defaults for older tests.
"""
from __future__ import annotations

import decimal
import logging
from typing import Any

from apps.reference.domains.decision_making.execution_gate import ExecutionGate
from apps.reference.domains.decision_making.exit_manager import ExitManager
from apps.reference.domains.decision_making.entry_plan import (
    EntryPlan,
    EntryPlanParams,
    ObiMissingPolicy,
)
from apps.reference.config_models import (
    ExitManagerConfig,
    OperationalMode,
    DashboardConfig,
)
from apps.reference.contracts.quadratic_rollout import (
    resolve_requested_quadratic_rollout,
)
from apps.reference.domains.decision_making.operational_mode import ModeManager
from apps.reference.domains.decision_making.dashboard import DashboardMetrics
from apps.reference.domains.decision_making.quadratic_scoring_kernel import (
    QuadraticScoringKernel,
)

logger = logging.getLogger("aurora_handler")


class AuroraConfigLoaderMixin:
    """Populate AuroraHandler state from strategy and domain configuration.

    Host contract:
    - ``self.config`` contains either a typed AuroraConfig or a test double.
    - ``self.logger`` is available for diagnostics.
    - ``self._build_shield_cascade()`` is supplied by AuroraScoringHelpersMixin.

    Side effects:
    - mutates handler attributes consumed by decision/execution paths;
    - constructs helper collaborators such as ExecutionGate, ExitManager,
      EntryPlan, ModeManager, and DashboardMetrics.
    """

    def _load_config(self) -> None:
        """Load Aurora config into handler attributes and helper objects.

        Strict Pydantic configs reject missing runtime-required fields. Legacy
        mocks keep compatibility defaults so isolated unit tests can still
        instantiate AuroraHandler without a full config tree.
        """
        aurora_cfg = getattr(self.config, "strategies", None)
        aurora = getattr(aurora_cfg, "aurora", None) if aurora_cfg else None

        # Warmup enforcement defaults to fail_fast unless the typed FE subtree is
        # present and explicitly overrides it.
        self._fe_warmup_enforcement_mode: str = "fail_fast"
        self._strict_pydantic_config: bool = False
        try:
            from apps.reference.config_models import AuroraConfig
            from apps.reference.domain_config import DomainConfigResolver

            if isinstance(self.config, AuroraConfig):
                self._strict_pydantic_config = True
                fe_cfg = DomainConfigResolver(
                    self.config).get_feature_engineering()
                warmup_cfg = getattr(fe_cfg, "warmup", None)
                if warmup_cfg is not None:
                    self._fe_warmup_enforcement_mode = str(
                        getattr(warmup_cfg, "enforcement_mode", "fail_fast"))
        except Exception:
            self._fe_warmup_enforcement_mode = "fail_fast"

        # timeframe_sec is a strict Aurora strategy contract. If the whole
        # strategy block is absent, keep a deterministic sentinel; the missing
        # decision block still fails closed below.
        if aurora is None:
            self.timeframe_sec = 0
            self.logger.debug(
                "AuroraHandler: aurora strategy not configured, timeframe_sec=0 (sentinel)")
        elif not hasattr(aurora, "timeframe_sec") or aurora.timeframe_sec is None:
            from apps.reference.config_contract import ConfigContractError
            raise ConfigContractError(
                path="strategies.aurora.timeframe_sec",
                why="timeframe_sec is mandatory in strategy config. Check config/aurora/strategies/aurora.yaml"
            )
        else:
            self.timeframe_sec = aurora.timeframe_sec

        decision = getattr(aurora, "decision", None) if aurora else None

        if decision:
            # Phase 6: Modes (Init first as used by shields)
            op_mode = getattr(decision, "operational_mode",
                              OperationalMode.PARANOID)
            self.mode_manager = ModeManager(op_mode)

            if self._strict_pydantic_config:
                # Typed config path: reject missing scoring inputs rather than
                # synthesizing runtime defaults.
                from apps.reference.config_contract import ConfigContractError

                thr_raw = getattr(decision, "signal_threshold", None)
                if thr_raw is None:
                    raise ConfigContractError(
                        path="strategies.aurora.decision.signal_threshold",
                        why="signal_threshold is required for AuroraHandler (no silent fallback).",
                    )
                self.signal_threshold = decimal.Decimal(str(thr_raw))

                # Side-bias parameters are required for kernel scoring (fail-closed).
                sb_window_raw = getattr(decision, "side_bias_window_sec", None)
                sb_target_raw = getattr(
                    decision, "side_bias_target_ratio", None)
                sb_penalty_raw = getattr(
                    decision, "side_bias_penalty_factor", None)
                sb_min_intents_raw = getattr(
                    decision, "side_bias_min_intents", None)
                if sb_window_raw is None:
                    raise ConfigContractError(
                        path="strategies.aurora.decision.side_bias_window_sec",
                        why="side_bias_window_sec is required (no silent fallback).",
                    )
                if sb_target_raw is None:
                    raise ConfigContractError(
                        path="strategies.aurora.decision.side_bias_target_ratio",
                        why="side_bias_target_ratio is required (no silent fallback).",
                    )
                if sb_penalty_raw is None:
                    raise ConfigContractError(
                        path="strategies.aurora.decision.side_bias_penalty_factor",
                        why="side_bias_penalty_factor is required (no silent fallback).",
                    )
                if sb_min_intents_raw is None:
                    raise ConfigContractError(
                        path="strategies.aurora.decision.side_bias_min_intents",
                        why="side_bias_min_intents is required (no silent fallback).",
                    )
                self.side_bias_window_sec = float(sb_window_raw)
                self.side_bias_target_ratio = float(sb_target_raw)
                self.side_bias_penalty_factor = float(sb_penalty_raw)
                self.side_bias_min_intents = int(sb_min_intents_raw)

                regime_thr = getattr(
                    decision, "regime_threshold_multipliers", None)
                if not isinstance(regime_thr, dict) or not regime_thr:
                    raise ConfigContractError(
                        path="strategies.aurora.decision.regime_threshold_multipliers",
                        why="regime_threshold_multipliers must be a non-empty mapping (include DEFAULT).",
                    )
                self.regime_thresholds = dict(regime_thr)
            else:
                # Legacy/mock config path: preserve historical defaults so older
                # tests can build a handler without a full AuroraConfig tree.
                self.signal_threshold = decimal.Decimal(
                    str(getattr(decision, "signal_threshold", "0.1")))
                self.side_bias_window_sec = float(
                    getattr(decision, "side_bias_window_sec", 420))
                self.side_bias_target_ratio = float(
                    getattr(decision, "side_bias_target_ratio", 0.72))
                self.side_bias_penalty_factor = float(
                    getattr(decision, "side_bias_penalty_factor", 0.25))
                self.side_bias_min_intents = int(
                    getattr(decision, "side_bias_min_intents", 18))
                self.regime_thresholds = getattr(
                    decision, "regime_threshold_multipliers", {"DEFAULT": 1.0})

            # Direction strength config
            ds_cfg = getattr(decision, "direction_strength_scoring", None)
            self.direction_strength_cfg = {
                "directional_features": list(getattr(ds_cfg, "directional_features", [])) if ds_cfg else [],
                "strength_features": list(getattr(ds_cfg, "strength_features", [])) if ds_cfg else [],
                "strength_alpha": float(getattr(ds_cfg, "strength_alpha", 0.5)) if ds_cfg else 0.5,
                "strength_cap": float(getattr(ds_cfg, "strength_cap", 1.5)) if ds_cfg else 1.5,
            }

            # SignalsConfig makes this mandatory in strict configs. Partial test
            # doubles still fall back to signed_v2 to avoid forcing full fixtures.
            signals = getattr(decision, "signals", None)
            self.delta_price_cap_pct = decimal.Decimal(str(getattr(
                signals, "delta_price_cap_pct", "0.005"))) if signals else decimal.Decimal("0.005")
            if signals is None:
                if self._strict_pydantic_config:
                    from apps.reference.config_contract import ConfigContractError
                    raise ConfigContractError(
                        path="strategies.aurora.decision.signals",
                        why="signals config is required (normalize_signals_mode). Check aurora.yaml."
                    )
                self.normalize_signals_mode = "signed_v2"
            else:
                self.normalize_signals_mode = str(
                    signals.normalize_signals_mode)

            # ═══════════════ Phase 9: Quadratic Kernel Routing ═══════════════
            requested_rollout = resolve_requested_quadratic_rollout(decision)
            self._aurora_requested_scoring_version = requested_rollout.requested_scoring_version
            self._aurora_effective_scoring_version = requested_rollout.effective_live_scoring_version
            self._quadratic_shadow_requested = requested_rollout.shadow_requested
            self._quadratic_rollback_armed = requested_rollout.rollback_armed
            self._quadratic_rollback_reason_chain = requested_rollout.rollback_reason_chain

            shadow_scoring_engine_cfg = getattr(
                decision, "scoring_engine", None)
            if self._quadratic_shadow_requested and shadow_scoring_engine_cfg is not None:
                self._quadratic_shadow_shield_fn = self._build_shield_cascade(
                    cfg=shadow_scoring_engine_cfg,
                    record_memory_shield=False,
                )
            else:
                self._quadratic_shadow_shield_fn = None

            if requested_rollout.effective_live_scoring_version == "quadratic":
                self.scoring_kernel_cls = QuadraticScoringKernel
                self._scoring_engine_cfg = shadow_scoring_engine_cfg
                self._shield_fn = self._build_shield_cascade()

                # SHIELD-FAIL-CLOSED: Quadratic mode MUST have a real shield cascade.
                # NullShield silently passes all signals through without attenuation —
                # this is only acceptable for legacy v1/v2 paths (now deleted).
                # Guard only in strict pydantic mode (production). Test mocks may use NullShield.
                from apps.reference.domains.decision_making.shields.null_shield import NullShield
                if self._strict_pydantic_config and isinstance(self._shield_fn, NullShield):
                    from apps.reference.config_contract import ConfigContractError
                    raise ConfigContractError(
                        path="strategies.aurora.decision.scoring_engine",
                        why=(
                            "Shield cascade resolved to NullShield while scoring_version='quadratic'. "
                            "Set scoring_engine.shield_enabled=true with at least one shield configured. "
                            "Fail-closed: Aurora cannot run Quadratic without active shield protection."
                        ),
                    )

                shield_name = repr(self._shield_fn) if hasattr(
                    self._shield_fn, '__repr__') else "ShieldCascade"
                self.logger.info(
                    f"Phase 9: QuadraticScoringKernel activated with {shield_name}")
            else:
                # Post-cleanup this branch is unreachable (effective_live is always quadratic).
                # Kept as defensive guard — will log and proceed.
                self.logger.warning(
                    "Quadratic rollout resolved to non-quadratic effective_live=%s "
                    "(unexpected post-Phase-9-cleanup). Proceeding with quadratic kernel.",
                    requested_rollout.effective_live_scoring_version,
                )
                self.scoring_kernel_cls = QuadraticScoringKernel
                self._scoring_engine_cfg = shadow_scoring_engine_cfg
                self._shield_fn = self._build_shield_cascade()
            # ═════════════════════════════════════════════════════════════════

            # Neutral threshold for hysteresis (global default)
            nt_raw = getattr(decision, "neutral_threshold", None)
            self.neutral_threshold = decimal.Decimal(
                str(nt_raw)) if nt_raw is not None else decimal.Decimal("0.05")

            # Phase 9: Sensitivity Tuning
            sm_raw = getattr(decision, "score_multiplier", 1.0)
            self.score_multiplier = float(sm_raw)

            geometry_cfg = getattr(decision, "decision_geometry", None)
            self.decision_admission_mode = str(
                getattr(geometry_cfg, "admission_mode", "quadratic")
            )
            self.decision_admission_power = (
                float(getattr(geometry_cfg, "admission_power"))
                if getattr(geometry_cfg, "admission_power", None) is not None
                else None
            )
            self.decision_sizing_mode = str(
                getattr(geometry_cfg, "sizing_mode", "quadratic")
            )
            self.decision_sizing_power = (
                float(getattr(geometry_cfg, "sizing_power"))
                if getattr(geometry_cfg, "sizing_power", None) is not None
                else None
            )
            self.decision_admission_shield_floor = float(
                getattr(geometry_cfg, "admission_shield_floor", 0.0) or 0.0
            )

            # REGIME-KILL-SWITCH-01: Optional config-driven regime blocklist.
            blocked = getattr(decision, "blocked_regimes", None)
            try:
                # Legacy mocks may expose arbitrary iterables here; normalize to
                # a stable string set or collapse to empty if the value is unusable.
                self.blocked_regimes = {str(x)
                                        for x in (blocked or []) if str(x)}
            except Exception:
                self.blocked_regimes = set()

            # Liquidity Gate (Score V2) - optional
            self._global_liquidity_gate_cfg = (
                getattr(decision, "liquidity_gate",
                        None) if self._strict_pydantic_config else None
            )

            # === Holding Period Config (Anti-Churn) ===
            hp_cfg = getattr(decision, "holding_period", None)
            if hp_cfg and getattr(hp_cfg, "enabled", False):
                self.holding_period_enabled = True
                self.default_min_duration_sec = float(
                    getattr(hp_cfg, "min_duration_sec", 30))
                self.default_emergency_threshold = float(
                    getattr(hp_cfg, "emergency_exit_threshold", 0.7))
                self.holding_apply_to_flips = bool(
                    getattr(hp_cfg, "apply_to_flips", True))
                self.logger.info(
                    f"Holding period enabled: min_duration={self.default_min_duration_sec}s, "
                    f"emergency_threshold={self.default_emergency_threshold}, apply_to_flips={self.holding_apply_to_flips}"
                )
            else:
                self.holding_period_enabled = False
                self.default_min_duration_sec = 30.0
                self.default_emergency_threshold = 0.7
                self.holding_apply_to_flips = True

            # === Re-entry Cooldown Config (Anti-Ping-Pong) ===
            rc_raw = getattr(decision, "reentry_cooldown_sec", None)
            self.default_reentry_cooldown_sec = float(
                rc_raw) if rc_raw is not None else 60.0
            self.logger.info(
                f"Re-entry cooldown: default={self.default_reentry_cooldown_sec}s")

            # === Anti-Churn: Time Multipliers + Regime Inertia ===
            ac_cfg = getattr(decision, "anti_churn", None)
            if ac_cfg and getattr(ac_cfg, "enabled", False):
                self.anti_churn_enabled = True
                self.time_multipliers = dict(
                    getattr(ac_cfg, "time_multipliers", {}) or {})

                ri_cfg = getattr(ac_cfg, "regime_inertia", None)
                self.regime_inertia_confirm_window_sec = float(
                    getattr(ri_cfg, "confirm_window_sec", 0.0)) if ri_cfg else 0.0
                self.regime_inertia_confirm_window_same_severity_sec = float(
                    getattr(ri_cfg, "confirm_window_same_severity_sec", 0.0)
                ) if ri_cfg else 0.0
                self.regime_inertia_immediate_risk_off = bool(
                    getattr(ri_cfg, "immediate_risk_off", True)) if ri_cfg else True
                self.regime_severity_map = dict(
                    getattr(ri_cfg, "severity_map", {}) or {})
            else:
                self.anti_churn_enabled = False
                self.time_multipliers = {}
                self.regime_inertia_confirm_window_sec = 0.0
                self.regime_inertia_confirm_window_same_severity_sec = 0.0
                self.regime_inertia_immediate_risk_off = True
                self.regime_severity_map = {}

            # === Vol-Adj Gates Config (Anti-Flat / Anti-FOMO) ===
            gates_cfg = getattr(decision, "gates", None)
            if gates_cfg and getattr(gates_cfg, "enabled", True):
                self.vol_gates_enabled = True
                self.anti_flat_sigma = float(
                    getattr(gates_cfg, "anti_flat_sigma", 0.5))
                self.anti_fomo_sigma = float(
                    getattr(gates_cfg, "anti_fomo_sigma", 4.0))
                self.motion_window_sec = int(
                    getattr(gates_cfg, "motion_window_sec", 900))
                self.logger.info(
                    f"Vol-Adj Gates enabled: anti_flat_sigma={self.anti_flat_sigma}, "
                    f"anti_fomo_sigma={self.anti_fomo_sigma}, motion_window={self.motion_window_sec}s"
                )
            else:
                self.vol_gates_enabled = False
                self.anti_flat_sigma = 0.5
                self.anti_fomo_sigma = 4.0
                self.motion_window_sec = 900

            # Phase 5: Execution Protocols
            execution_cfg = getattr(decision, "execution", None)
            self.execution_gate = ExecutionGate(
                execution_cfg) if execution_cfg is not None else None

            # BUG-3: Fail-closed if exit config is missing (Risk Critical)
            exit_cfg = getattr(decision, "exit", None)
            if exit_cfg is None:
                if self._strict_pydantic_config:
                    from apps.reference.config_contract import ConfigContractError
                    raise ConfigContractError(
                        path="strategies.aurora.decision.exit",
                        why="ExitManager config is mandatory (Fail-Closed). Check aurora.yaml."
                    )
                self.logger.warning(
                    "ExitManager config missing! Defaulting to disabled (Dangerous!)")
                exit_cfg = ExitManagerConfig(
                    time_exit_enabled=False,
                    signal_exit_enabled=False,
                )

            # Compatibility probe: older config objects may expose trailing_stop
            # under config.instruments. AuroraConfig.instruments is the precision
            # SSOT, so strict configs typically leave this unset here.
            _trailing_cfg = None
            try:
                instruments = getattr(self.config, "instruments", None)
                if instruments:
                    for _inst_cfg in instruments.values():
                        _trailing_cfg = getattr(
                            _inst_cfg, "trailing_stop", None)
                        if _trailing_cfg and getattr(_trailing_cfg, "enabled", False):
                            break
                        _trailing_cfg = None
            except Exception:
                _trailing_cfg = None

            self.exit_manager = ExitManager(
                exit_cfg or ExitManagerConfig(),
                trailing_enabled=bool(
                    getattr(_trailing_cfg, "enabled", False)) if _trailing_cfg else False,
                trailing_activation_pct=float(
                    getattr(_trailing_cfg, "activation_pct", 0.003)) if _trailing_cfg else 0.003,
                trailing_atr_mult=float(
                    getattr(_trailing_cfg, "trail_atr_mult", 0)) or None if _trailing_cfg else None,
                trailing_pct=float(
                    getattr(_trailing_cfg, "trail_pct", 0)) or None if _trailing_cfg else None,
            )

            # EntryPlan lives under the decision_making domain contract rather
            # than under strategies.aurora.decision.
            domains_cfg = getattr(self.config, "domains", None)
            dm_domain_cfg = getattr(
                domains_cfg, "decision_making", None) if domains_cfg else None
            ep_cfg = getattr(dm_domain_cfg, "entry_plan", None)

            if ep_cfg:
                self.entry_plan_params = EntryPlanParams(
                    atr_period=ep_cfg.atr_period,
                    entry_k_atr=float(ep_cfg.entry_k_atr),
                    sl_k_atr=float(ep_cfg.sl_k_atr),
                    tp_k_atr=float(ep_cfg.tp_k_atr),
                    obi_weight=float(ep_cfg.obi_weight),
                    obi_mod_clamp_min=float(ep_cfg.obi_mod_clamp_min),
                    obi_mod_clamp_max=float(ep_cfg.obi_mod_clamp_max),
                    require_atr=bool(ep_cfg.require_atr),
                    obi_missing_policy=ObiMissingPolicy.NEUTRAL,
                    structural_stop_enabled=bool(
                        ep_cfg.structural_stop_enabled),
                    base_atr_mult=float(ep_cfg.base_atr_mult),
                    confidence_scale=float(ep_cfg.confidence_scale),
                    min_stop_bps=int(ep_cfg.min_stop_bps),
                )
                self.entry_plan_calculator = EntryPlan(self.entry_plan_params)
            else:
                self.entry_plan_params = None
                self.entry_plan_calculator = None
                self.logger.warning(
                    "DecisionMakingDomainConfig.entry_plan missing: EntryPlan logic disabled (Structural Gate will block).")

            # Phase 6: Dashboard
            dash_cfg = getattr(decision, "dashboard",
                               None) or DashboardConfig(enabled=False)
            self.dashboard = DashboardMetrics(
                dash_cfg) if dash_cfg.enabled else None

        else:
            # P2: FAIL-CLOSED — decision config is mandatory
            from apps.reference.config_contract import ConfigContractError
            raise ConfigContractError(
                path="strategies.aurora.decision",
                why="Aurora decision config is mandatory. Check config/aurora/strategies/aurora.yaml"
            )
