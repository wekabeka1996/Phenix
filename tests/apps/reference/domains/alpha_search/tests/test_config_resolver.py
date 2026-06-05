"""
T1: Config Resolver Tests
=========================

Tests for apps/reference/domains/alpha_search/runtime/config_resolver.py
28 tests covering override mode, full_config mode, dot-path overrides, and persistence.
"""

import copy
import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from pydantic import ValidationError

from apps.reference.domains.alpha_search.runtime.config_resolver import (
    resolve_scenario_config,
    _apply_dot_path_override,
    _build_alpha_search_config,
    _build_system_config,
    _extract_strategy_config,
    persist_effective_config,
    ConfigResolutionError,
)
from apps.reference.domains.alpha_search.runtime.contracts import ScenarioSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)


def _minimal_alpha_search_yaml():
    """Minimal alpha_search config that passes Pydantic validation."""
    return {
        "alpha_search": {
            "enabled": True,
            "shadow_mode": True,
            "triggers": {
                "feature_event": "EVT:FEATURES_CALCULATED",
                "decision_event": "CMD:PROCESS_STRATEGY",
                "emit_event": "EVT:ALPHA_SCORE_CALCULATED",
            },
            "cache": {"max_per_symbol": 10, "require_same_bar_close_ts": False},
            "providers": {
                "aurora": {
                    "enabled": True,
                    "symbols": ["BTCUSDT"],
                    "threshold": 0.155,
                    "fail_closed": True,
                    "adapter": {
                        "scoring_version": "v2",
                        "essential_features": ["obi", "delta_price", "macro_resid"],
                    },
                },
            },
            "virtual_trader": {
                "enabled": False,
                "per_provider": True,
                "max_positions_per_symbol": 1,
                "notional_size": 1000,
                "exit": {"max_bars": 12, "max_hold_sec": 3600},
            },
            "legacy": {},
        }
    }


def _minimal_aurora_yaml():
    """Minimal aurora strategy config with top-level key."""
    return {
        "aurora": {
            "decision": {
                "signal_threshold": 0.155,
                "signal_weights": {"obi": 0.20, "delta_price": 0.15},
                "feature_neutrals": {"obi": 0.50},
                "gates": {"anti_flat_sigma": 0.45, "anti_fomo_sigma": 6.0},
            }
        }
    }


# ---------------------------------------------------------------------------
# Override Mode
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOverrideMode:

    def test_happy_path(self, tmp_path):
        """Override mode loads base refs, applies overrides, returns valid configs."""
        root = tmp_path / "project"
        _write_yaml(root / "config" / "alpha_search.yaml",
                    _minimal_alpha_search_yaml())
        _write_yaml(root / "config" / "aurora.yaml", _minimal_aurora_yaml())

        spec = ScenarioSpec(
            scenario_id="S_TEST",
            strategy_type="aurora",
            config_mode="override",
            base_refs={
                "alpha_search": "config/alpha_search.yaml",
                "aurora": "config/aurora.yaml",
            },
            overrides={},
        )

        alpha_cfg, sys_cfg, strat_cfg = resolve_scenario_config(spec, root)

        assert alpha_cfg.enabled is True
        assert alpha_cfg.shadow_mode is True
        assert strat_cfg.get("decision", {}).get("signal_threshold") == 0.155

    def test_missing_base_ref_raises(self, tmp_path):
        """Missing base ref file raises ConfigResolutionError."""
        root = tmp_path / "project"
        root.mkdir()

        spec = ScenarioSpec(
            scenario_id="S_MISSING",
            strategy_type="aurora",
            config_mode="override",
            base_refs={"aurora": "config/nonexistent.yaml"},
            overrides={},
        )

        with pytest.raises(ConfigResolutionError, match="not found"):
            resolve_scenario_config(spec, root)

    def test_disallowed_override_rejected(self, tmp_path):
        """Overrides not in allowlist raise ConfigResolutionError."""
        root = tmp_path / "project"
        _write_yaml(root / "config" / "alpha_search.yaml",
                    _minimal_alpha_search_yaml())
        _write_yaml(root / "config" / "aurora.yaml", _minimal_aurora_yaml())

        spec = ScenarioSpec(
            scenario_id="S_BAD",
            strategy_type="aurora",
            config_mode="override",
            base_refs={
                "alpha_search": "config/alpha_search.yaml",
                "aurora": "config/aurora.yaml",
            },
            overrides={"aurora.internal.secret": True},
        )

        with pytest.raises(ConfigResolutionError, match="Disallowed"):
            resolve_scenario_config(spec, root)

    def test_yaml_unwrap_top_key(self, tmp_path):
        """YAML with top-level key matching ref name is unwrapped."""
        root = tmp_path / "project"
        wrapped = {"aurora": {"decision": {"signal_threshold": 0.12}}}
        _write_yaml(root / "config" / "aurora.yaml", wrapped)
        _write_yaml(root / "config" / "alpha_search.yaml",
                    _minimal_alpha_search_yaml())

        spec = ScenarioSpec(
            scenario_id="S_UNWRAP",
            strategy_type="aurora",
            config_mode="override",
            base_refs={
                "aurora": "config/aurora.yaml",
                "alpha_search": "config/alpha_search.yaml",
            },
            overrides={},
        )

        _, _, strat_cfg = resolve_scenario_config(spec, root)
        # Unwrapped: strat_cfg should be {"decision": {...}} not {"aurora": {"decision": {...}}}
        assert "decision" in strat_cfg
        assert "aurora" not in strat_cfg

    def test_no_unwrap_flat_yaml(self, tmp_path):
        """Flat YAML (no matching top-level key) is NOT unwrapped."""
        root = tmp_path / "project"
        flat = {"decision": {"signal_threshold": 0.12}}
        _write_yaml(root / "config" / "aurora.yaml", flat)
        _write_yaml(root / "config" / "alpha_search.yaml",
                    _minimal_alpha_search_yaml())

        spec = ScenarioSpec(
            scenario_id="S_FLAT",
            strategy_type="aurora",
            config_mode="override",
            base_refs={
                "aurora": "config/aurora.yaml",
                "alpha_search": "config/alpha_search.yaml",
            },
            overrides={},
        )

        _, _, strat_cfg = resolve_scenario_config(spec, root)
        assert "decision" in strat_cfg

    def test_aurora_threshold_override(self, tmp_path):
        """Aurora signal_threshold override applied correctly."""
        root = tmp_path / "project"
        _write_yaml(root / "config" / "aurora.yaml", _minimal_aurora_yaml())
        _write_yaml(root / "config" / "alpha_search.yaml",
                    _minimal_alpha_search_yaml())

        spec = ScenarioSpec(
            scenario_id="S_THR",
            strategy_type="aurora",
            config_mode="override",
            base_refs={
                "aurora": "config/aurora.yaml",
                "alpha_search": "config/alpha_search.yaml",
            },
            overrides={"aurora.decision.signal_threshold": 0.12},
        )

        _, _, strat_cfg = resolve_scenario_config(spec, root)
        assert strat_cfg["decision"]["signal_threshold"] == 0.12

    def test_aurora_decision_exit_subset_validated(self, tmp_path):
        """Aurora decision.exit survives strict subset validation when fields are canonical."""
        root = tmp_path / "project"
        aurora_yaml = _minimal_aurora_yaml()
        aurora_yaml["aurora"]["decision"]["exit"] = {
            "time_exit_enabled": True,
            "max_hold_time_sec": 7200,
            "signal_exit_enabled": True,
            "signal_reversal_threshold": -0.2,
            "danger_zone_action": "TIGHTEN_STOPS",
            "danger_zone_tighten_factor": 0.5,
        }
        _write_yaml(root / "config" / "aurora.yaml", aurora_yaml)
        _write_yaml(root / "config" / "alpha_search.yaml", _minimal_alpha_search_yaml())

        spec = ScenarioSpec(
            scenario_id="S_EXIT",
            strategy_type="aurora",
            config_mode="override",
            base_refs={
                "aurora": "config/aurora.yaml",
                "alpha_search": "config/alpha_search.yaml",
            },
            overrides={},
        )

        _, _, strat_cfg = resolve_scenario_config(spec, root)

        assert strat_cfg["decision"]["exit"] == {
            "time_exit_enabled": True,
            "max_hold_time_sec": 7200,
            "signal_exit_enabled": True,
            "signal_reversal_threshold": -0.2,
            "danger_zone_action": "TIGHTEN_STOPS",
            "danger_zone_tighten_factor": 0.5,
        }

    def test_invalid_aurora_asset_weight_key_fails_closed(self, tmp_path):
        """Invalid per-asset weight key is rejected during aurora subset validation."""
        root = tmp_path / "project"
        _write_yaml(root / "config" / "alpha_search.yaml", _minimal_alpha_search_yaml())
        _write_yaml(
            root / "config" / "aurora.yaml",
            {
                "aurora": {
                    "decision": {"signal_threshold": 0.155},
                    "assets": {
                        "BTCUSDT": {
                            "enabled": True,
                            "weights": {"not_a_real_weight": 0.5},
                        }
                    },
                }
            },
        )

        spec = ScenarioSpec(
            scenario_id="S_BAD_ASSET_WEIGHTS",
            strategy_type="aurora",
            config_mode="override",
            base_refs={
                "aurora": "config/aurora.yaml",
                "alpha_search": "config/alpha_search.yaml",
            },
            overrides={},
        )

        with pytest.raises(ConfigResolutionError, match="subset validation failed"):
            resolve_scenario_config(spec, root)

    def test_partial_aurora_warns(self, tmp_path, caplog):
        """Threshold without neutrals logs warning."""
        root = tmp_path / "project"
        _write_yaml(root / "config" / "aurora.yaml", _minimal_aurora_yaml())
        _write_yaml(root / "config" / "alpha_search.yaml",
                    _minimal_alpha_search_yaml())

        spec = ScenarioSpec(
            scenario_id="S_WARN",
            strategy_type="aurora",
            config_mode="override",
            base_refs={
                "aurora": "config/aurora.yaml",
                "alpha_search": "config/alpha_search.yaml",
            },
            overrides={"aurora.decision.signal_threshold": 0.12},
        )

        import logging
        with caplog.at_level(logging.WARNING):
            resolve_scenario_config(spec, root)

        assert any("feature_neutrals" in msg for msg in caplog.messages)

    def test_deepcopy_no_mutation(self, tmp_path):
        """Overrides don't mutate original config dicts."""
        root = tmp_path / "project"
        aurora_data = _minimal_aurora_yaml()
        orig_threshold = aurora_data["aurora"]["decision"]["signal_threshold"]
        _write_yaml(root / "config" / "aurora.yaml", aurora_data)
        _write_yaml(root / "config" / "alpha_search.yaml",
                    _minimal_alpha_search_yaml())

        spec = ScenarioSpec(
            scenario_id="S_COPY",
            strategy_type="aurora",
            config_mode="override",
            base_refs={
                "aurora": "config/aurora.yaml",
                "alpha_search": "config/alpha_search.yaml",
            },
            overrides={"aurora.decision.signal_threshold": 0.99},
        )

        resolve_scenario_config(spec, root)
        # Original data should be unchanged
        assert aurora_data["aurora"]["decision"]["signal_threshold"] == orig_threshold

    def test_null_alpha_search_yaml_fails_closed(self, tmp_path):
        """Null alpha_search YAML should fail config resolution instead of silently defaulting."""
        root = tmp_path / "project"
        (root / "config").mkdir(parents=True)
        (root / "config" / "alpha_search.yaml").write_text("null\n", encoding="utf-8")
        _write_yaml(root / "config" / "aurora.yaml", _minimal_aurora_yaml())

        spec = ScenarioSpec(
            scenario_id="S_NULL",
            strategy_type="aurora",
            config_mode="override",
            base_refs={
                "alpha_search": "config/alpha_search.yaml",
                "aurora": "config/aurora.yaml",
            },
            overrides={},
        )

        with pytest.raises(ConfigResolutionError):
            resolve_scenario_config(spec, root)


# ---------------------------------------------------------------------------
# Full Config Mode
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFullConfigMode:

    def test_happy_path(self, tmp_path):
        """Full config mode loads all YAMLs from directory."""
        root = tmp_path / "project"
        cfg_dir = root / "scenarios" / "S_FULL"
        cfg_dir.mkdir(parents=True)

        _write_yaml(cfg_dir / "alpha_search.yaml",
                    _minimal_alpha_search_yaml()["alpha_search"])
        _write_yaml(cfg_dir / "alpha_search_system.yaml", {})

        spec = ScenarioSpec(
            scenario_id="S_FULL",
            strategy_type="aurora",
            config_mode="full_config",
            scenario_config_dir="scenarios/S_FULL",
        )

        alpha_cfg, sys_cfg, strat_cfg = resolve_scenario_config(spec, root)
        assert alpha_cfg.enabled is True

    def test_missing_dir_raises(self, tmp_path):
        """Missing scenario config dir raises ConfigResolutionError."""
        root = tmp_path / "project"
        root.mkdir()

        spec = ScenarioSpec(
            scenario_id="S_NODIR",
            strategy_type="aurora",
            config_mode="full_config",
            scenario_config_dir="scenarios/nonexistent",
        )

        with pytest.raises(ConfigResolutionError, match="not found"):
            resolve_scenario_config(spec, root)

    def test_empty_dir_uses_defaults(self, tmp_path):
        """Empty config dir falls back to default configs."""
        root = tmp_path / "project"
        cfg_dir = root / "scenarios" / "S_EMPTY"
        cfg_dir.mkdir(parents=True)

        spec = ScenarioSpec(
            scenario_id="S_EMPTY",
            strategy_type="aurora",
            config_mode="full_config",
            scenario_config_dir="scenarios/S_EMPTY",
        )

        # Empty dir -> no providers -> ConfigResolutionError
        with pytest.raises(ConfigResolutionError):
            resolve_scenario_config(spec, root)


# ---------------------------------------------------------------------------
# Dot-Path Overrides
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDotPathOverride:

    def test_simple_set(self):
        """Simple dot-path override sets value."""
        raw = {"alpha_search": {"providers": {"aurora": {"threshold": 0.1}}}}
        _apply_dot_path_override(
            raw, "alpha_search.providers.aurora.threshold", 0.2, "TEST")
        assert raw["alpha_search"]["providers"]["aurora"]["threshold"] == 0.2

    def test_creates_intermediate_dicts(self):
        """Missing intermediate dcts are created."""
        raw = {"config": {}}
        _apply_dot_path_override(raw, "config.a.b.c", 42, "TEST")
        assert raw["config"]["a"]["b"]["c"] == 42

    def test_path_too_short_raises(self):
        """Single-segment path raises error."""
        raw = {"x": 1}
        with pytest.raises(ConfigResolutionError, match="too short"):
            _apply_dot_path_override(raw, "x", 2, "TEST")

    def test_through_non_dict_raises(self):
        """Navigating through a non-dict value raises."""
        raw = {"config": {"key": "string_not_dict"}}
        with pytest.raises(ConfigResolutionError, match="non-dict"):
            _apply_dot_path_override(raw, "config.key.sub", 1, "TEST")

    def test_creates_new_config_section(self):
        """New top-level config name is auto-created."""
        raw = {}
        _apply_dot_path_override(raw, "new_section.key1", "val", "TEST")
        assert raw["new_section"]["key1"] == "val"


# ---------------------------------------------------------------------------
# Config Building Helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildHelpers:

    def test_build_alpha_search_config_forces_enabled_shadow(self):
        """Alpha search config always has enabled=True, shadow_mode=True."""
        raw_cfgs = {"alpha_search": _minimal_alpha_search_yaml()[
            "alpha_search"]}
        raw_cfgs["alpha_search"]["enabled"] = False
        raw_cfgs["alpha_search"]["shadow_mode"] = False

        cfg = _build_alpha_search_config(raw_cfgs, "TEST")
        assert cfg.enabled is True
        assert cfg.shadow_mode is True

    def test_build_alpha_search_config_unwraps_nested_key(self):
        """Double-nested alpha_search key is unwrapped."""
        raw_cfgs = {"alpha_search": {"alpha_search": _minimal_alpha_search_yaml()[
            "alpha_search"]}}
        cfg = _build_alpha_search_config(raw_cfgs, "TEST")
        assert cfg.enabled is True

    def test_build_system_config_defaults(self):
        """Empty dict produces valid system config with defaults."""
        raw_cfgs = {}
        cfg = _build_system_config(raw_cfgs, "TEST")
        assert cfg is not None

    def test_build_system_config_unwraps_nested(self):
        """Nested alpha_search_system key unwrapped."""
        raw_cfgs = {"alpha_search_system": {"alpha_search_system": {}}}
        cfg = _build_system_config(raw_cfgs, "TEST")
        assert cfg is not None

    def test_extract_strategy_config_aurora(self):
        """Aurora strategy extracts and deep-copies aurora dict."""
        raw = {"aurora": {"decision": {"threshold": 0.1}}}
        result = _extract_strategy_config(raw, "aurora")
        assert result["decision"]["signal_threshold"] == 0.1
        # Verify it's a deep copy
        result["decision"]["signal_threshold"] = 0.99
        assert raw["aurora"]["decision"]["threshold"] == 0.1

    def test_extract_strategy_config_mr(self):
        """Mean reversion strategy extracts correct dict."""
        raw = {"mean_reversion": {"strategy": {"bb_window": 20}}}
        result = _extract_strategy_config(raw, "mean_reversion")
        assert result["strategy"]["bb_window"] == 20

    def test_extract_strategy_config_ensemble_empty(self):
        """Ensemble strategy returns empty dict."""
        raw = {}
        result = _extract_strategy_config(raw, "ensemble")
        assert result == {}


# ---------------------------------------------------------------------------
# Config Persistence
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPersistConfig:

    def test_writes_yaml(self, tmp_path):
        """Effective config written as YAML file."""
        from apps.reference.domains.alpha_search.config_models import (
            get_default_config, get_default_system_config,
        )

        output_dir = tmp_path / "scenario_out"
        path = persist_effective_config(
            scenario_id="S_TEST",
            alpha_search_config=get_default_config(),
            system_config=get_default_system_config(),
            strategy_config={"decision": {"threshold": 0.1}},
            output_dir=output_dir,
        )

        assert path.exists()
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["scenario_id"] == "S_TEST"
        assert "alpha_search" in data
        assert "strategy" in data

    def test_creates_missing_dirs(self, tmp_path):
        """Parent directories created if missing."""
        from apps.reference.domains.alpha_search.config_models import (
            get_default_config, get_default_system_config,
        )

        output_dir = tmp_path / "deep" / "nested" / "dir"
        path = persist_effective_config(
            scenario_id="S_DEEP",
            alpha_search_config=get_default_config(),
            system_config=get_default_system_config(),
            strategy_config={},
            output_dir=output_dir,
        )
        assert path.exists()


# ---------------------------------------------------------------------------
# Unknown Config Mode
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUnknownConfigMode:

    def test_unknown_mode_raises(self, tmp_path):
        """Unknown config_mode raises ConfigResolutionError."""
        # Bypass Pydantic Literal validation with a mock
        spec = MagicMock()
        spec.config_mode = "magic"
        spec.scenario_id = "S_MAGIC"

        with pytest.raises(ConfigResolutionError, match="Unknown config_mode"):
            resolve_scenario_config(spec, tmp_path)
