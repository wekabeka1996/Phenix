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

from ..config_models import (
    AlphaSearchConfig,
    AlphaSearchSystemConfig,
    load_alpha_search_config,
    load_system_config,
)
from .contracts import ScenarioSpec
from .override_allowlist import validate_overrides, warn_partial_aurora_overrides

LOG = logging.getLogger(__name__)


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
        return copy.deepcopy(raw_configs.get("aurora", {}))
    elif strategy_type == "mean_reversion":
        return copy.deepcopy(raw_configs.get("mean_reversion", {}))
    elif strategy_type == "ensemble":
        # Ensemble uses alpha_search + alpha_search_system (no separate strategy file)
        return {}
    return {}


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
