"""
Scenario Config Resolver
========================

Materializes effective config for each scenario BEFORE runtime.

Two modes:
- override: load base_refs YAML files, apply dot-path overrides, validate
- full_config: load full config files from scenario_config_dir, validate

Persists effective_config.yaml in scenario log directory for auditability.
"""

import copy
import logging
from pathlib import Path
from typing import Any, Dict, Tuple, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from apps.reference.config_models import (
    ExitManagerConfig,
    AuroraInstrumentConfig,
    CANONICAL_WEIGHT_KEYS,
)

from ..config_models import (
    AlphaSearchConfig,
    AlphaSearchSystemConfig,
    load_alpha_search_config,
    load_system_config,
)
from .contracts import ScenarioSpec
from .override_allowlist import validate_overrides, warn_partial_aurora_overrides

LOG = logging.getLogger(__name__)


SUPPORTED_AURORA_DECISION_FIELDS = {
    "signal_threshold",
    "signal_weights",
    "feature_neutrals",
    "regime_threshold_multipliers",
    "blocked_regimes",
    "direction_strength_scoring",
    "gates",
    "exit",
}


class AuroraScenarioDecisionConfig(BaseModel):
    """Strict subset of Aurora decision config consumed by alpha_search runtime."""

    model_config = ConfigDict(extra="forbid")

    signal_threshold: Optional[float] = None
    signal_weights: Optional[Dict[str, float]] = None
    feature_neutrals: Optional[Dict[str, float]] = None
    regime_threshold_multipliers: Optional[Dict[str, float]] = None
    blocked_regimes: Optional[list[str]] = None
    direction_strength_scoring: Optional[Dict[str, Any]] = None
    gates: Optional[Dict[str, Any]] = None
    exit: Optional[ExitManagerConfig] = None

    @field_validator("signal_weights")
    @classmethod
    def validate_signal_weight_keys(
        cls,
        value: Optional[Dict[str, float]],
    ) -> Optional[Dict[str, float]]:
        if value is None:
            return value
        invalid_keys = sorted(set(value.keys()) - CANONICAL_WEIGHT_KEYS)
        if invalid_keys:
            raise ValueError(
                "Invalid decision.signal_weights keys: "
                f"{invalid_keys}. Valid keys: {sorted(CANONICAL_WEIGHT_KEYS)}"
            )
        return value


class AuroraScenarioStrategyConfig(BaseModel):
    """Strict Aurora strategy subset needed by alpha_search scenario runtime."""

    model_config = ConfigDict(extra="forbid")

    decision: AuroraScenarioDecisionConfig = Field(
        default_factory=AuroraScenarioDecisionConfig
    )
    assets: Dict[str, AuroraInstrumentConfig] = Field(default_factory=dict)


class ConfigResolutionError(RuntimeError):
    """Raised when scenario config resolution fails (fail-closed)."""

    def __init__(self, scenario_id: str, reason: str):
        self.scenario_id = scenario_id
        self.reason = reason
        super().__init__(f"[{scenario_id}] Config resolution failed: {reason}")


def resolve_scenario_config(
    scenario: ScenarioSpec,
    project_root: Path,
) -> Tuple[AlphaSearchConfig, AlphaSearchSystemConfig, Dict[str, Any]]:
    """
    Materialize effective configuration for a single scenario.

    Returns:
        (alpha_search_config, system_config, strategy_config)

    strategy_config contains the raw aurora.yaml or mean_reversion.yaml
    dict for parameter injection into the scoring adapter.
    """
    if scenario.config_mode == "override":
        return _resolve_override_mode(scenario, project_root)
    elif scenario.config_mode == "full_config":
        return _resolve_full_config_mode(scenario, project_root)
    else:
        raise ConfigResolutionError(
            scenario.scenario_id,
            f"Unknown config_mode: {scenario.config_mode}",
        )


def _resolve_override_mode(
    scenario: ScenarioSpec,
    project_root: Path,
) -> Tuple[AlphaSearchConfig, AlphaSearchSystemConfig, Dict[str, Any]]:
    """
    Resolve config in override mode:
    1. Load base_refs YAML files
    2. Validate overrides against allowlist
    3. Apply dot-path overrides
    4. Validate final result via Pydantic
    """
    sid = scenario.scenario_id
    base_refs = scenario.base_refs or {}
    overrides = scenario.overrides or {}

    # --- Load base configs ---
    raw_configs: Dict[str, Dict[str, Any]] = {}
    for ref_name, ref_path in base_refs.items():
        full_path = project_root / ref_path
        if not full_path.exists():
            raise ConfigResolutionError(
                sid, f"Base ref '{ref_name}' not found: {full_path}"
            )
        with open(full_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        # Unwrap top-level key if it matches the ref name.
        # E.g., aurora.yaml has {"aurora": {...}} ΓÇö unwrap to get the inner dict.
        # Similarly alpha_search.yaml has {"alpha_search": {...}}.
        if ref_name in raw and isinstance(raw[ref_name], dict) and len(raw) == 1:
            raw = raw[ref_name]
        raw_configs[ref_name] = raw

    # --- Validate overrides against allowlist ---
    if overrides:
        rejected = validate_overrides(scenario.strategy_type, overrides)
        if rejected:
            raise ConfigResolutionError(
                sid,
                f"Disallowed override paths for {scenario.strategy_type}: {rejected}",
            )

        # Soft warnings for aurora consistency
        if scenario.strategy_type == "aurora":
            warnings = warn_partial_aurora_overrides(overrides)
            for w in warnings:
                LOG.warning(f"[{sid}] {w}")

    # --- Apply overrides to raw configs ---
    for dot_path, value in overrides.items():
        _apply_dot_path_override(raw_configs, dot_path, value, sid)

    # --- Propagate aurora decision overrides to assets and judge to prevent shadowing ---
    if scenario.strategy_type == "aurora":
        for dot_path, value in overrides.items():
            if dot_path.startswith("aurora.decision."):
                _propagate_aurora_decision_override_to_assets(
                    raw_configs, dot_path, value, sid, overrides
                )
                _propagate_aurora_decision_override_to_judge(
                    raw_configs, dot_path, value, sid, overrides
                )

    # --- Build typed configs ---
    alpha_search_config = _build_alpha_search_config(raw_configs, sid)
    system_config = _build_system_config(raw_configs, sid)
    strategy_config = _extract_strategy_config(
        raw_configs, scenario.strategy_type)

    LOG.info(
        f"[{sid}] Config resolved (override mode): "
        f"overrides={len(overrides)}, strategy={scenario.strategy_type}"
    )

    return alpha_search_config, system_config, strategy_config


def _resolve_full_config_mode(
    scenario: ScenarioSpec,
    project_root: Path,
) -> Tuple[AlphaSearchConfig, AlphaSearchSystemConfig, Dict[str, Any]]:
    """
    Resolve config in full_config mode:
    1. Load full config files from scenario_config_dir
    2. Validate via Pydantic
    """
    sid = scenario.scenario_id
    config_dir = project_root / scenario.scenario_config_dir

    if not config_dir.exists():
        raise ConfigResolutionError(
            sid, f"Scenario config dir not found: {config_dir}"
        )

    raw_configs: Dict[str, Dict[str, Any]] = {}

    # Load all YAML files from scenario dir
    for yaml_file in config_dir.glob("*.yaml"):
        stem = yaml_file.stem  # e.g. "aurora", "alpha_search", "alpha_search_system"
        with open(yaml_file, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        raw_configs[stem] = raw

    alpha_search_config = _build_alpha_search_config(raw_configs, sid)
    system_config = _build_system_config(raw_configs, sid)
    strategy_config = _extract_strategy_config(
        raw_configs, scenario.strategy_type)

    LOG.info(
        f"[{sid}] Config resolved (full_config mode): "
        f"files={list(raw_configs.keys())}, strategy={scenario.strategy_type}"
    )

    return alpha_search_config, system_config, strategy_config


# =============================================================================
# Override application
# =============================================================================

def _apply_dot_path_override(
    raw_configs: Dict[str, Dict[str, Any]],
    dot_path: str,
    value: Any,
    scenario_id: str,
) -> None:
    """
    Apply a single dot-path override.

    Dot path format: "config_name.key1.key2.key3"
    First segment determines which raw_config dict to target.
    """
    parts = dot_path.split(".")
    if len(parts) < 2:
        raise ConfigResolutionError(
            scenario_id,
            f"Override path too short (need at least config.key): {dot_path}",
        )

    # First segment is the config name
    config_name = parts[0]
    key_parts = parts[1:]

    if config_name not in raw_configs:
        # Create empty dict for new config references (e.g., overrides that
        # target configs not in base_refs but referenced in allowlist)
        raw_configs[config_name] = {}

    target = raw_configs[config_name]

    # Navigate to parent of final key
    for part in key_parts[:-1]:
        if part not in target:
            target[part] = {}
        elif not isinstance(target[part], dict):
            raise ConfigResolutionError(
                scenario_id,
                f"Cannot override through non-dict node at '{dot_path}' "
                f"(segment '{part}' is {type(target[part]).__name__})",
            )
        target = target[part]

    # Set the final value
    target[key_parts[-1]] = value


def _propagate_aurora_decision_override_to_assets(
    raw_configs: Dict[str, Dict[str, Any]],
    dot_path: str,
    value: Any,
    scenario_id: str,
    explicit_overrides: Dict[str, Any]
) -> None:
    """Propagate global aurora.decision.* overrides to all assets to prevent shadowing."""
    aurora_config = raw_configs.get("aurora", {})
    assets = aurora_config.get("assets", {})
    if not assets:
        return
        
    parts = dot_path.split(".")
    
    def apply_if_not_explicit(asset_path: str):
        if asset_path not in explicit_overrides:
            _apply_dot_path_override(raw_configs, asset_path, value, scenario_id)

    # Format: aurora.decision.signal_weights.obi
    if len(parts) == 4 and parts[2] == "signal_weights":
        key = parts[3]
        for symbol in assets.keys():
            apply_if_not_explicit(f"aurora.assets.{symbol}.weights.{key}")
            
    # Format: aurora.decision.feature_neutrals.obi
    elif len(parts) == 4 and parts[2] == "feature_neutrals":
        key = parts[3]
        for symbol in assets.keys():
            apply_if_not_explicit(f"aurora.assets.{symbol}.feature_neutrals.{key}")
            
    # Format: aurora.decision.regime_threshold_multipliers.HIGH_VOLATILITY
    elif len(parts) == 4 and parts[2] == "regime_threshold_multipliers":
        key = parts[3]
        for symbol in assets.keys():
            apply_if_not_explicit(f"aurora.assets.{symbol}.regime_thresholds.{key}")
            
    # Format: aurora.decision.signal_threshold
    elif len(parts) == 3 and parts[2] == "signal_threshold":
        for symbol in assets.keys():
            if isinstance(assets[symbol], dict) and "signal_threshold" in assets[symbol]:
                apply_if_not_explicit(f"aurora.assets.{symbol}.signal_threshold.value")


def _propagate_aurora_decision_override_to_judge(
    raw_configs: Dict[str, Dict[str, Any]],
    dot_path: str,
    value: Any,
    scenario_id: str,
    explicit_overrides: Dict[str, Any]
) -> None:
    """Propagate global aurora.decision.* overrides to judge experts to keep them synchronized."""
    parts = dot_path.split(".")
    
    def apply_if_not_explicit(path: str):
        if path not in explicit_overrides:
            _apply_dot_path_override(raw_configs, path, value, scenario_id)

    # Format: aurora.decision.signal_weights.obi
    if len(parts) == 4 and parts[2] == "signal_weights":
        key = parts[3]
        apply_if_not_explicit(f"alpha_search.judge.experts.signal_weights.signal_weights.{key}")
        apply_if_not_explicit(f"alpha_search.judge.experts.feature_neutrals.signal_weights.{key}")

    # Format: aurora.decision.feature_neutrals.obi
    elif len(parts) == 4 and parts[2] == "feature_neutrals":
        key = parts[3]
        apply_if_not_explicit(f"alpha_search.judge.experts.signal_weights.feature_neutrals.{key}")
        apply_if_not_explicit(f"alpha_search.judge.experts.feature_neutrals.feature_neutrals.{key}")

    # Format: aurora.decision.signal_threshold
    elif len(parts) == 3 and parts[2] == "signal_threshold":
        apply_if_not_explicit("alpha_search.judge.experts.signal_weights.signal_threshold")
        apply_if_not_explicit("alpha_search.judge.experts.feature_neutrals.signal_threshold")
        apply_if_not_explicit("alpha_search.providers.judge_sw.threshold")
        apply_if_not_explicit("alpha_search.providers.judge_fn.threshold")


# =============================================================================
# Config building helpers
# =============================================================================

def _build_alpha_search_config(
    raw_configs: Dict[str, Dict[str, Any]],
    scenario_id: str,
) -> AlphaSearchConfig:
    """Build AlphaSearchConfig from raw configs. Always enabled for shadow."""
    raw = raw_configs.get("alpha_search", {})

    # Unwrap nested key if present
    if "alpha_search" in raw:
        raw = raw["alpha_search"]

    # Force enabled + shadow for standalone
    raw = copy.deepcopy(raw)
    raw["enabled"] = True
    raw["shadow_mode"] = True

    try:
        return AlphaSearchConfig.model_validate(raw)
    except Exception as e:
        raise ConfigResolutionError(
            scenario_id, f"AlphaSearchConfig validation failed: {e}"
        ) from e


def _build_system_config(
    raw_configs: Dict[str, Dict[str, Any]],
    scenario_id: str,
) -> AlphaSearchSystemConfig:
    """Build AlphaSearchSystemConfig from raw configs."""
    raw = raw_configs.get("alpha_search_system", {})

    # Unwrap nested key if present
    if "alpha_search_system" in raw:
        raw = raw["alpha_search_system"]

    raw = copy.deepcopy(raw)

    try:
        return AlphaSearchSystemConfig.model_validate(raw)
    except Exception as e:
        raise ConfigResolutionError(
            scenario_id, f"AlphaSearchSystemConfig validation failed: {e}"
        ) from e


def _extract_strategy_config(
    raw_configs: Dict[str, Dict[str, Any]],
    strategy_type: str,
) -> Dict[str, Any]:
    """Extract strategy-specific raw config dict for adapter injection."""
    if strategy_type == "aurora":
        return _validate_aurora_strategy_subset(raw_configs.get("aurora", {}))
    elif strategy_type == "mean_reversion":
        return copy.deepcopy(raw_configs.get("mean_reversion", {}))
    elif strategy_type == "md_amr":
        return copy.deepcopy(raw_configs.get("md_amr", {}))
    elif strategy_type == "ensemble":
        # Ensemble uses alpha_search + alpha_search_system (no separate strategy file)
        return {}
    return {}


def _validate_aurora_strategy_subset(raw_strategy: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the Aurora surfaces consumed by alpha_search scenarios."""
    if not raw_strategy:
        return {}

    decision = copy.deepcopy(raw_strategy.get("decision", {}))
    if "signal_threshold" not in decision and "threshold" in decision:
        decision["signal_threshold"] = decision.pop("threshold")

    decision_subset = {
        key: value
        for key, value in decision.items()
        if key in SUPPORTED_AURORA_DECISION_FIELDS
    }

    try:
        subset = AuroraScenarioStrategyConfig.model_validate(
            {
                "decision": decision_subset,
                "assets": raw_strategy.get("assets", {}),
            }
        )
    except ValidationError as exc:
        raise ConfigResolutionError(
            "aurora",
            f"Aurora strategy subset validation failed: {exc}",
        ) from exc

    validated = copy.deepcopy(raw_strategy)
    validated["decision"] = subset.decision.model_dump(exclude_none=True)
    validated["assets"] = {
        symbol: asset.model_dump(exclude_none=True)
        for symbol, asset in subset.assets.items()
    }
    return validated


# =============================================================================
# Config persistence
# =============================================================================

def persist_effective_config(
    scenario_id: str,
    alpha_search_config: AlphaSearchConfig,
    system_config: AlphaSearchSystemConfig,
    strategy_config: Dict[str, Any],
    output_dir: Path,
) -> Path:
    """
    Persist materialized config to effective_config.yaml for auditability.

    Returns path to the written file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "config_effective.yaml"

    effective = {
        "scenario_id": scenario_id,
        "alpha_search": alpha_search_config.model_dump(),
        "alpha_search_system": system_config.model_dump(),
        "strategy": strategy_config,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(effective, f, default_flow_style=False, allow_unicode=True)

    LOG.debug(f"[{scenario_id}] Effective config persisted: {output_path}")
    return output_path
