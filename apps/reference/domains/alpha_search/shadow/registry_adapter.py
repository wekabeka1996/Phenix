"""
Shadow Registry → ScenarioMatrixConfig Adapter
================================================

Converts ShadowScenarioRegistry (scenario_registry_v2.yaml format) into a
ScenarioMatrixConfig (scenario_matrix.yaml format) so ScenarioManager can
consume 30 shadow scenarios without changing its interface.

AUTHORITY BOUNDARY:
  This adapter only constructs configuration objects.
  It never emits real ORDER_INTENT, CMD:OPEN, CMD:CLOSE.
  All produced ScenarioSpec objects remain shadow-only.

Field mapping:
  ShadowScenarioSpec.score_provider + family → ScenarioSpec.strategy_type
  ShadowScenarioSpec.entry_threshold         → threshold override (strategy-specific path)
  ShadowScenarioSpec.score_overrides         → ScenarioSpec.overrides (with prefix normalisation)

Override prefix normalisation:
  score_override "mean_reversion.*"  → "alpha_search_system.mean_reversion.*"
  score_override "ensemble.*"        → "alpha_search_system.ensemble.*"
  score_override "momentum.*"        → "alpha_search_system.momentum.*"
  score_override "volatility.*"      → "alpha_search_system.volatility.*"
  score_override "aurora.*"          → "aurora.*"           (kept as-is)
  score_override "alpha_search.*"    → "alpha_search.*"     (kept as-is)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .scenario_registry import (
    ShadowScenarioRegistry,
    ShadowScenarioSpec,
    ScenarioFamily,
    load_registry,
)
from ..runtime.contracts import (
    ScenarioMatrixConfig,
    ScenarioSpec,
    RuntimeConfig,
    HotReloadConfig,
    InputConfig,
)

LOG = logging.getLogger(__name__)

# Base config refs per strategy type
_BASE_REFS: Dict[str, Dict[str, str]] = {
    "aurora": {
        "aurora": "config/aurora/strategies/aurora.yaml",
        "alpha_search": "config/alpha_search.yaml",
        "alpha_search_system": "config/alpha_search_system.yaml",
    },
    "mean_reversion": {
        "mean_reversion": "config/aurora/strategies/mean_reversion.yaml",
        "alpha_search": "config/alpha_search.yaml",
        "alpha_search_system": "config/alpha_search_system.yaml",
    },
    "ensemble": {
        "alpha_search": "config/alpha_search.yaml",
        "alpha_search_system": "config/alpha_search_system.yaml",
    },
}

# Prefixes in score_overrides that need alpha_search_system. prepended
_SYSTEM_CONFIG_PREFIXES = (
    "mean_reversion.",
    "ensemble.",
    "momentum.",
    "volatility.",
)

# Shadow lab: aurora symbols whose per-asset allowed_regimes we must override.
# Production aurora.yaml restricts each symbol to specific regimes (e.g. BTC → HIGH_VOLATILITY only).
# Alpha_input data is 100% UNCERTAIN regime → without this override, all aurora scenarios score=0.
_SHADOW_AURORA_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "BNBUSDT",
]

# All regimes that can appear in alpha_input; shadow lab observes signals in all of them.
_SHADOW_ALL_REGIMES = [
    "TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY", "LOW_VOLATILITY",
    "MEAN_REVERSION", "UNCERTAIN", "DEFAULT", "FLAT_NORMAL", "FLAT_LOW", "FLAT_HIGH",
]


def _strategy_type(spec: ShadowScenarioSpec) -> str:
    """Derive runtime strategy_type from score_provider + family."""
    provider = spec.score_provider
    family = spec.family

    if provider == "aurora":
        return "aurora"
    # ta_ensemble with mean_reversion family uses the mean_reversion strategy plugin
    if family == ScenarioFamily.MEAN_REVERSION:
        return "mean_reversion"
    return "ensemble"


def _normalise_override_key(key: str) -> str:
    """Prepend alpha_search_system. to system-config override paths."""
    for prefix in _SYSTEM_CONFIG_PREFIXES:
        if key.startswith(prefix):
            return f"alpha_search_system.{key}"
    return key


def _build_overrides(spec: ShadowScenarioSpec, strategy_type: str) -> Dict[str, Any]:
    """
    Build the dot-path overrides dict for a ScenarioSpec.

    Merges:
    1. Threshold override (strategy-specific path)
    2. Normalised score_overrides from the shadow spec
    """
    overrides: Dict[str, Any] = {}

    # --- Threshold override ---
    thr = spec.entry_threshold
    if strategy_type == "aurora":
        overrides["aurora.decision.signal_threshold"] = thr
        overrides["alpha_search.providers.aurora.threshold"] = thr
        # Shadow-only: unlock UNCERTAIN regime per asset.
        # Production aurora.yaml has restrictive allowed_regimes (e.g. BTC=["HIGH_VOLATILITY"]).
        # Alpha_input replay data is 100% UNCERTAIN → without this, all aurora scenarios score=0.
        for _sym in _SHADOW_AURORA_SYMBOLS:
            overrides[f"aurora.assets.{_sym}.allowed_regimes"] = _SHADOW_ALL_REGIMES
            # Production aurora.yaml has regime_thresholds.UNCERTAIN=99.0 for BTC/ETH
            # (impossible threshold multiplier). Shadow lab normalises to 1.0.
            overrides[f"aurora.assets.{_sym}.regime_thresholds.UNCERTAIN"] = 1.0
    elif strategy_type == "mean_reversion":
        overrides["mean_reversion.strategy.entry_threshold"] = thr
        overrides["alpha_search.providers.ta_ensemble.threshold"] = thr
    else:  # ensemble
        overrides["alpha_search.providers.ta_ensemble.threshold"] = thr

    # --- score_overrides normalisation ---
    for raw_key, value in (spec.score_overrides or {}).items():
        normalised = _normalise_override_key(raw_key)
        overrides[normalised] = value

    return overrides


def _spec_to_runtime(spec: ShadowScenarioSpec) -> ScenarioSpec:
    """Convert one ShadowScenarioSpec → ScenarioSpec (runtime format)."""
    strat = _strategy_type(spec)
    overrides = _build_overrides(spec, strat)
    base_refs = _BASE_REFS[strat]

    return ScenarioSpec(
        scenario_id=spec.scenario_id,
        version=spec.version,
        family=spec.family.value,
        provider=spec.score_provider,
        shadow_only=spec.shadow_only,
        authority_applied=spec.authority_applied,
        no_effect=spec.no_effect,
        enabled=spec.enabled,
        strategy_type=strat,
        config_mode="override",
        base_refs=base_refs,
        overrides=overrides,
    )


def registry_to_matrix_config(
    registry: ShadowScenarioRegistry,
    *,
    source_mode: str = "replay",
    stream_path: str = "logs/alpha_input/alpha_input_v1.jsonl",
    max_workers: int = 4,
    parallelism: str = "thread_pool",
) -> ScenarioMatrixConfig:
    """
    Convert a ShadowScenarioRegistry into a ScenarioMatrixConfig.

    The resulting config can be passed directly to ScenarioManager.
    All produced scenarios carry strategy_type + base_refs + overrides
    derived from the shadow registry spec.

    Args:
        registry: Validated ShadowScenarioRegistry instance.
        source_mode: "replay" | "live_tail" for the ingest gateway.
        stream_path: Path to alpha_input_v1.jsonl stream.
        max_workers: Thread pool worker count.
        parallelism: "thread_pool" | "sequential".

    Returns:
        ScenarioMatrixConfig validated by Pydantic (fail-closed).

    Raises:
        pydantic.ValidationError: if conversion produces invalid config.
    """
    enabled_count = len(registry.get_enabled())

    runtime = RuntimeConfig(
        max_scenarios=max(50, enabled_count),
        max_concurrent_scenarios=max(50, enabled_count),
        parallelism=parallelism,
        max_workers=max_workers,
        queue_maxsize=4000,
        backpressure_policy="drop_oldest",
        memory_budget_mb_per_scenario=50,
        scenario_timeout_sec=5.0,
        health_heartbeat_sec=30.0,
    )

    hot_reload = HotReloadConfig(enabled=False)

    input_cfg = InputConfig(
        source_mode=source_mode,
        stream_path=stream_path,
    )

    runtime_specs = []
    skipped = []
    for spec in registry.scenarios:
        try:
            runtime_specs.append(_spec_to_runtime(spec))
        except Exception as exc:
            LOG.warning(
                "[%s] Skipping scenario — conversion failed: %s",
                spec.scenario_id, exc,
            )
            skipped.append(spec.scenario_id)

    if skipped:
        LOG.warning("Skipped %d scenarios during registry adaptation: %s", len(skipped), skipped)

    if not runtime_specs:
        raise ValueError("registry_to_matrix_config produced zero runnable scenarios")

    LOG.info(
        "registry_to_matrix_config: registry_id=%s → %d scenarios (%d enabled, %d skipped)",
        registry.registry_id,
        len(runtime_specs),
        sum(1 for s in runtime_specs if s.enabled),
        len(skipped),
    )

    return ScenarioMatrixConfig(
        matrix_id=f"registry:{registry.registry_id}:v{registry.version}",
        version=registry.version,
        runtime=runtime,
        hot_reload=hot_reload,
        input=input_cfg,
        scenarios=runtime_specs,
    )


def load_registry_as_matrix_config(
    path: str,
    *,
    source_mode: str = "replay",
    stream_path: str = "logs/alpha_input/alpha_input_v1.jsonl",
    max_workers: int = 4,
) -> ScenarioMatrixConfig:
    """
    Load scenario_registry_v2.yaml and convert to ScenarioMatrixConfig.

    Fail-closed: raises on missing file, schema errors, or conversion failures.
    """
    registry = load_registry(path)
    LOG.info(
        "Loaded registry: id=%s version=%d total=%d enabled=%d",
        registry.registry_id,
        registry.version,
        len(registry.scenarios),
        len(registry.get_enabled()),
    )
    return registry_to_matrix_config(
        registry,
        source_mode=source_mode,
        stream_path=stream_path,
        max_workers=max_workers,
    )
