from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class StrategyHTFRequirement:
    timeframe_sec: int
    required_bars: int
    scope: str
    source: str

    def to_payload(self) -> dict[str, object]:
        return {
            "timeframe_sec": int(self.timeframe_sec),
            "required_bars": int(self.required_bars),
            "scope": self.scope,
            "source": self.source,
        }


@dataclass(frozen=True)
class StrategyCompatibilityProfile:
    profile_id: str
    strategy_id: str
    active: bool
    active_symbols: tuple[str, ...]
    required_basis_tf_sec: int
    basis_required_bars: int
    required_htf: tuple[StrategyHTFRequirement, ...]
    needs_regime: bool
    needs_microstructure: bool
    needs_execution_context: bool
    local_hydration_contract: str | None
    restart_local_basis_counter: bool
    degraded_mode_allowance: str
    protect_only_capability: bool
    quadratic_readiness_blocks_by_default: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "strategy_id": self.strategy_id,
            "active": self.active,
            "active_symbols": list(self.active_symbols),
            "required_basis_tf_sec": int(self.required_basis_tf_sec),
            "basis_required_bars": int(self.basis_required_bars),
            "required_htf": [item.to_payload() for item in self.required_htf],
            "needs_regime": bool(self.needs_regime),
            "needs_microstructure": bool(self.needs_microstructure),
            "needs_execution_context": bool(self.needs_execution_context),
            "local_hydration_contract": self.local_hydration_contract,
            "restart_local_basis_counter": bool(self.restart_local_basis_counter),
            "degraded_mode_allowance": self.degraded_mode_allowance,
            "protect_only_capability": bool(self.protect_only_capability),
            "quadratic_readiness_blocks_by_default": bool(self.quadratic_readiness_blocks_by_default),
        }


def _extract_assignments(config: Any) -> dict[str, list[str]]:
    assignments_raw = getattr(
        getattr(config, "strategies_registry", None), "assignments", None)
    if not isinstance(assignments_raw, dict):
        return {}
    assignments: dict[str, list[str]] = {}
    for symbol, strategy_ids in assignments_raw.items():
        if not isinstance(strategy_ids, list):
            continue
        clean_ids = [str(strategy_id)
                     for strategy_id in strategy_ids if str(strategy_id)]
        if clean_ids:
            assignments[str(symbol).upper()] = clean_ids
    return assignments


def _active_symbols(assignments: Mapping[str, list[str]], strategy_id: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            symbol
            for symbol, strategy_ids in assignments.items()
            if strategy_id in strategy_ids
        )
    )


def regime_detector_required_bars(config: Any) -> int:
    """
    Canonical required bars for RegimeDetector warmup.

    Truth source: regime.yaml → models.sma_trend.sma_long_period
                              + models.volatility.atr_period / atr_sma_length

    Contract: Any strategy with needs_regime=True MUST fetch at least this many
    basis bars to ensure the global RegimeDetector can warm up its SMA and ATR buffers.

    Used by: strategy_compatibility_matrix, startup_warmup, main.py legacy path.
    Raises ValueError if regime model config is not reachable (fail-closed).
    """
    regime_cfg = config if hasattr(
        config, "basis_tf_sec") else getattr(config, "regime", config)
    models_cfg = getattr(regime_cfg, "models", None)
    sma_cfg = getattr(models_cfg, "sma_trend", None)
    vol_cfg = getattr(models_cfg, "volatility", None)

    if sma_cfg is None or vol_cfg is None:
        raise ValueError(
            "regime.models.sma_trend / regime.models.volatility not found in config — "
            "cannot compute regime_detector_required_bars. "
            "Verify regime.yaml is loaded and config_loader is not stripping models section."
        )

    sma_long = int(sma_cfg.sma_long_period)
    atr_period = int(vol_cfg.atr_period)
    atr_sma_length = int(vol_cfg.atr_sma_length)
    return max(sma_long, atr_period + atr_sma_length - 1)


# Internal alias — keeps existing internal call sites working during rollout
_structural_regime_basis_required_bars = regime_detector_required_bars


def _aurora_required_htf(config: Any) -> tuple[StrategyHTFRequirement, ...]:
    pillars_cfg = getattr(getattr(
        getattr(config, "domains", None), "feature_engineering", None), "pillars", None)
    if pillars_cfg is None or not bool(getattr(pillars_cfg, "enabled", False)):
        return ()
    backfill_cfg = getattr(pillars_cfg, "backfill", None)
    return (
        StrategyHTFRequirement(
            timeframe_sec=900,
            required_bars=int(getattr(backfill_cfg, "m15_candles", 50) or 50),
            scope="pillar_state",
            source="feature_engineering:pillars",
        ),
        StrategyHTFRequirement(
            timeframe_sec=14400,
            required_bars=int(getattr(backfill_cfg, "h4_candles", 100) or 100),
            scope="pillar_state",
            source="feature_engineering:pillars",
        ),
        StrategyHTFRequirement(
            timeframe_sec=86400,
            required_bars=int(getattr(backfill_cfg, "d1_candles", 200) or 200),
            scope="pillar_state",
            source="feature_engineering:pillars",
        ),
    )


def _active_aurora_profile_id(config: Any) -> str:
    # Phase 9 cleanup: Aurora is always quadratic. v2 kernel deleted.
    return "aurora_quadratic"


def _md_amr_basis_required_bars(md_cfg: Any) -> int:
    """Minimum md_amr history required before the core stops deferring."""
    channel_window_bars = int(getattr(md_cfg, "channel_window_bars", 12) or 12)
    atr_window = int(getattr(md_cfg, "atr_window", 14) or 14)
    atr_stats_window = int(getattr(md_cfg, "atr_stats_window", 64) or 64)
    atr_history_required_bars = atr_window + atr_stats_window - 1
    dir_components_required_bars = 96
    return max(
        channel_window_bars,
        atr_history_required_bars,
        dir_components_required_bars,
    )


def active_aurora_profile_id(config: Any) -> str:
    return _active_aurora_profile_id(config)


def get_active_strategy_profile(
    config: Any,
    strategy_id: str,
) -> StrategyCompatibilityProfile | None:
    profiles = build_active_strategy_compatibility_profiles(config)
    return profiles.get(str(strategy_id))


def build_full_strategy_compatibility_matrix(
    config: Any,
) -> dict[str, StrategyCompatibilityProfile]:
    assignments = _extract_assignments(config)
    aurora_cfg = getattr(getattr(config, "strategies", None), "aurora", None)
    mr_cfg = getattr(getattr(config, "strategies", None),
                     "mean_reversion", None)
    md_cfg = getattr(getattr(config, "strategies", None), "md_amr", None)
    active_aurora_profile_id = _active_aurora_profile_id(config)

    matrix = {
        "aurora_v2": StrategyCompatibilityProfile(
            profile_id="aurora_v2",
            strategy_id="aurora",
            active=active_aurora_profile_id == "aurora_v2",
            active_symbols=_active_symbols(assignments, "aurora"),
            required_basis_tf_sec=int(
                getattr(aurora_cfg, "timeframe_sec", 300) or 300),
            basis_required_bars=_structural_regime_basis_required_bars(config),
            required_htf=(),
            needs_regime=True,
            needs_microstructure=True,
            needs_execution_context=True,
            local_hydration_contract=None,
            restart_local_basis_counter=True,
            degraded_mode_allowance="PROTECT_ONLY",
            protect_only_capability=True,
            quadratic_readiness_blocks_by_default=False,
        ),
        "aurora_quadratic": StrategyCompatibilityProfile(
            profile_id="aurora_quadratic",
            strategy_id="aurora",
            active=active_aurora_profile_id == "aurora_quadratic",
            active_symbols=_active_symbols(assignments, "aurora"),
            required_basis_tf_sec=int(
                getattr(aurora_cfg, "timeframe_sec", 300) or 300),
            basis_required_bars=_structural_regime_basis_required_bars(config),
            required_htf=_aurora_required_htf(config),
            needs_regime=True,
            needs_microstructure=True,
            needs_execution_context=True,
            local_hydration_contract=None,
            restart_local_basis_counter=True,
            degraded_mode_allowance="PROTECT_ONLY",
            protect_only_capability=True,
            quadratic_readiness_blocks_by_default=True,
        ),
        "mean_reversion": StrategyCompatibilityProfile(
            profile_id="mean_reversion",
            strategy_id="mean_reversion",
            active=True,
            active_symbols=_active_symbols(assignments, "mean_reversion"),
            required_basis_tf_sec=int(
                getattr(mr_cfg, "timeframe_sec", 300) or 300),
            basis_required_bars=max(
                int(getattr(getattr(mr_cfg, "strategy", None), "min_bars", 25) or 25),
                _structural_regime_basis_required_bars(
                    config)  # Needs regime warmly loaded
            ),
            required_htf=(),
            needs_regime=True,
            needs_microstructure=False,
            needs_execution_context=True,
            local_hydration_contract=None,
            restart_local_basis_counter=False,
            degraded_mode_allowance="NON_TRADING_ONLY",
            protect_only_capability=False,
            quadratic_readiness_blocks_by_default=False,
        ),
        "md_amr": StrategyCompatibilityProfile(
            profile_id="md_amr",
            strategy_id="md_amr",
            active=True,
            active_symbols=_active_symbols(assignments, "md_amr"),
            required_basis_tf_sec=int(
                getattr(md_cfg, "timeframe_sec", 900) or 900),
            basis_required_bars=_md_amr_basis_required_bars(md_cfg),
            required_htf=(),
            needs_regime=True,
            needs_microstructure=False,
            needs_execution_context=True,
            local_hydration_contract="md_amr_rest_hydration",
            restart_local_basis_counter=True,
            degraded_mode_allowance="PROTECT_ONLY",
            protect_only_capability=True,
            quadratic_readiness_blocks_by_default=False,
        ),
    }
    return matrix


def build_active_strategy_compatibility_profiles(
    config: Any,
) -> dict[str, StrategyCompatibilityProfile]:
    matrix = build_full_strategy_compatibility_matrix(config)
    return {
        "aurora": matrix[_active_aurora_profile_id(config)],
        "mean_reversion": matrix["mean_reversion"],
        "md_amr": matrix["md_amr"],
    }
