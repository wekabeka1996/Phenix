"""Tests for SystemStressConfig (Phase 0.0) — Pydantic validation.

PKG-0.0A: system_stress SSOT in regime.yaml.

Pattern 1: Direct model unit tests (no YAML, no ConfigLoader).
Pattern 2: Integration test via ConfigLoader (copy + mutate YAML).
"""

import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_models import (
    SystemStressAggregationConfig,
    SystemStressConfig,
    SystemStressStateMappingConfig,
    SystemStressThresholdsConfig,
)


# ═══════════════════════════════════════════════════════════════════
# Helpers — valid fixtures
# ═══════════════════════════════════════════════════════════════════

def _valid_thresholds(**overrides) -> dict:
    base = dict(
        atr_sigma=2.0, vol_sigma=2.0, gap_sigma=3.0, range_sigma=2.5,
        volume_sigma=0.0, spread_sigma=0.0, depth_drop_pct=0.0,
    )
    base.update(overrides)
    return base


def _valid_aggregation(**overrides) -> dict:
    base = dict(
        method="weighted_vote",
        weights={"atr": 0.30, "vol": 0.30, "gap": 0.20, "range": 0.20},
        k=None,
    )
    base.update(overrides)
    return base


def _valid_state_mapping(**overrides) -> dict:
    base = dict(
        enter_stress=0.60, exit_stress=0.40,
        enter_extreme=0.85, exit_extreme=0.70,
        consecutive_bars_enter=3, consecutive_bars_exit=2,
        min_duration_bars=5, switch_window_bars=50,
        max_switches_per_window=3, circuit_breaker_mode="halt",
    )
    base.update(overrides)
    return base


def _valid_system_stress(**overrides) -> dict:
    base = dict(
        enabled=False,
        sources_enabled=["price"],
        require_l2_if_enabled=True,
        baseline_method="rolling",
        baseline_window=100,
        burn_in_bars=120,
        robust_method="none",
        thresholds=_valid_thresholds(),
        aggregation=_valid_aggregation(),
        state_mapping=_valid_state_mapping(),
    )
    base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════════════
# Unit tests: SystemStressThresholdsConfig
# ═══════════════════════════════════════════════════════════════════

class TestSystemStressThresholds:
    def test_valid_thresholds(self):
        cfg = SystemStressThresholdsConfig(**_valid_thresholds())
        assert cfg.atr_sigma == 2.0
        assert cfg.volume_sigma == 0.0

    def test_negative_sigma_rejected(self):
        with pytest.raises(ValidationError):
            SystemStressThresholdsConfig(**_valid_thresholds(atr_sigma=-1.0))

    def test_sigma_above_max_rejected(self):
        with pytest.raises(ValidationError):
            SystemStressThresholdsConfig(**_valid_thresholds(vol_sigma=11.0))

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError) as exc_info:
            SystemStressThresholdsConfig(**_valid_thresholds(), unknown_field=1.0)
        assert "Extra inputs" in str(exc_info.value) or "unknown_field" in str(exc_info.value)


# ═══════════════════════════════════════════════════════════════════
# Unit tests: SystemStressAggregationConfig
# ═══════════════════════════════════════════════════════════════════

class TestSystemStressAggregation:
    def test_valid_weighted_vote(self):
        cfg = SystemStressAggregationConfig(**_valid_aggregation())
        assert cfg.method == "weighted_vote"
        assert abs(sum(cfg.weights.values()) - 1.0) < 0.01

    def test_weights_sum_not_one_rejected(self):
        with pytest.raises(ValidationError, match="sum to ~1.0"):
            SystemStressAggregationConfig(
                method="weighted_vote",
                weights={"atr": 0.50, "vol": 0.10},  # sum = 0.60
            )

    def test_weights_required_for_weighted_vote(self):
        with pytest.raises(ValidationError, match="weights required"):
            SystemStressAggregationConfig(method="weighted_vote", weights=None)

    def test_invalid_weight_key_rejected(self):
        with pytest.raises(ValidationError, match="invalid keys"):
            SystemStressAggregationConfig(
                method="weighted_vote",
                weights={"atr": 0.5, "vol_sigam": 0.5},  # typo: vol_sigam
            )

    def test_k_required_for_k_of_n(self):
        with pytest.raises(ValidationError, match="k required"):
            SystemStressAggregationConfig(method="k_of_n", k=None)

    def test_valid_k_of_n(self):
        cfg = SystemStressAggregationConfig(method="k_of_n", k=3)
        assert cfg.k == 3

    def test_valid_max_method(self):
        cfg = SystemStressAggregationConfig(method="max")
        assert cfg.method == "max"


# ═══════════════════════════════════════════════════════════════════
# Unit tests: SystemStressStateMappingConfig
# ═══════════════════════════════════════════════════════════════════

class TestSystemStressStateMapping:
    def test_valid_mapping(self):
        cfg = SystemStressStateMappingConfig(**_valid_state_mapping())
        assert cfg.enter_stress == 0.60
        assert cfg.circuit_breaker_mode == "halt"

    def test_exit_stress_ge_enter_stress_rejected(self):
        """Hysteresis: exit_stress must be < enter_stress."""
        with pytest.raises(ValidationError, match="exit_stress.*must be < enter_stress"):
            SystemStressStateMappingConfig(
                **_valid_state_mapping(enter_stress=0.50, exit_stress=0.50)
            )

    def test_exit_stress_gt_enter_stress_rejected(self):
        with pytest.raises(ValidationError, match="exit_stress.*must be < enter_stress"):
            SystemStressStateMappingConfig(
                **_valid_state_mapping(enter_stress=0.50, exit_stress=0.60)
            )

    def test_exit_extreme_ge_enter_extreme_rejected(self):
        with pytest.raises(ValidationError, match="exit_extreme.*must be < enter_extreme"):
            SystemStressStateMappingConfig(
                **_valid_state_mapping(enter_extreme=0.80, exit_extreme=0.80)
            )

    def test_enter_stress_ge_enter_extreme_rejected(self):
        with pytest.raises(ValidationError, match="enter_stress.*must be < enter_extreme"):
            SystemStressStateMappingConfig(
                **_valid_state_mapping(enter_stress=0.90, enter_extreme=0.85)
            )

    def test_circuit_breaker_only_halt_allowed(self):
        with pytest.raises(ValidationError):
            SystemStressStateMappingConfig(
                **_valid_state_mapping(circuit_breaker_mode="resume")
            )


# ═══════════════════════════════════════════════════════════════════
# Unit tests: SystemStressConfig (top-level)
# ═══════════════════════════════════════════════════════════════════

class TestSystemStressConfig:
    def test_valid_config_disabled(self):
        """enabled=false still validates all fields (no silent garbage)."""
        cfg = SystemStressConfig(**_valid_system_stress(enabled=False))
        assert cfg.enabled is False
        assert cfg.burn_in_bars == 120

    def test_valid_config_enabled(self):
        cfg = SystemStressConfig(**_valid_system_stress(enabled=True))
        assert cfg.enabled is True

    def test_rolling_without_window_rejected(self):
        with pytest.raises(ValidationError, match="baseline_window required"):
            SystemStressConfig(
                **_valid_system_stress(baseline_method="rolling", baseline_window=None)
            )

    def test_expanding_without_window_ok(self):
        cfg = SystemStressConfig(
            **_valid_system_stress(baseline_method="expanding", baseline_window=None)
        )
        assert cfg.baseline_window is None

    def test_spread_sigma_without_orderbook_rejected(self):
        """spread_sigma > 0 requires 'orderbook' in sources_enabled."""
        with pytest.raises(ValidationError, match="spread_sigma.*requires.*orderbook"):
            SystemStressConfig(
                **_valid_system_stress(
                    sources_enabled=["price"],
                    thresholds=_valid_thresholds(spread_sigma=3.0),
                )
            )

    def test_depth_drop_without_orderbook_rejected(self):
        with pytest.raises(ValidationError, match="depth_drop_pct.*requires.*orderbook"):
            SystemStressConfig(
                **_valid_system_stress(
                    sources_enabled=["price"],
                    thresholds=_valid_thresholds(depth_drop_pct=50.0),
                )
            )

    def test_spread_with_orderbook_ok(self):
        cfg = SystemStressConfig(
            **_valid_system_stress(
                sources_enabled=["price", "orderbook"],
                thresholds=_valid_thresholds(spread_sigma=3.0),
                aggregation=dict(
                    method="weighted_vote",
                    weights={"atr": 0.25, "vol": 0.25, "gap": 0.15, "range": 0.15, "spread": 0.20},
                ),
            )
        )
        assert cfg.thresholds.spread_sigma == 3.0

    def test_weight_key_for_disabled_trigger_rejected(self):
        """Weight for trigger with sigma=0 is wasted → rejected."""
        with pytest.raises(ValidationError, match="disabled triggers"):
            SystemStressConfig(
                **_valid_system_stress(
                    thresholds=_valid_thresholds(volume_sigma=0.0),
                    aggregation=dict(
                        method="weighted_vote",
                        # 'volume' has sigma=0, so weight for it is wasted
                        weights={"atr": 0.25, "vol": 0.25, "gap": 0.20, "volume": 0.30},
                    ),
                )
            )

    def test_robust_method_mad(self):
        cfg = SystemStressConfig(**_valid_system_stress(robust_method="mad"))
        assert cfg.robust_method == "mad"

    def test_invalid_robust_method_rejected(self):
        with pytest.raises(ValidationError):
            SystemStressConfig(**_valid_system_stress(robust_method="iqr"))

    def test_burn_in_bars_zero_rejected(self):
        with pytest.raises(ValidationError):
            SystemStressConfig(**_valid_system_stress(burn_in_bars=0))

    def test_sources_enabled_empty_rejected(self):
        with pytest.raises(ValidationError):
            SystemStressConfig(**_valid_system_stress(sources_enabled=[]))


# ═══════════════════════════════════════════════════════════════════
# Integration: ConfigLoader round-trip
# ═══════════════════════════════════════════════════════════════════

def _write_yaml(path: Path, obj) -> None:
    path.write_text(yaml.safe_dump(obj, sort_keys=False), encoding="utf-8")


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    """Copy production config to tmp for mutation."""
    cfg_dir = tmp_path / "aurora"
    repo_root = Path(__file__).resolve().parents[2]
    shutil.copytree(repo_root / "config" / "aurora", cfg_dir)
    return cfg_dir


class TestSystemStressConfigLoader:
    """Integration: system_stress loaded through real ConfigLoader."""

    def test_config_loads_without_system_stress(self, tmp_path: Path):
        """Existing config without system_stress → None (backward compat)."""
        from apps.reference.config_loader import ConfigLoader

        cfg_dir = _copy_config_to_tmp(tmp_path)

        # Ensure regime.yaml does NOT have system_stress
        regime_path = cfg_dir / "regime.yaml"
        regime = yaml.safe_load(regime_path.read_text(encoding="utf-8"))
        regime.pop("system_stress", None)
        _write_yaml(regime_path, regime)

        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        assert config.system_stress is None

    def test_config_loads_with_valid_system_stress(self, tmp_path: Path):
        """regime.yaml with valid system_stress → parsed SystemStressConfig."""
        from apps.reference.config_loader import ConfigLoader

        cfg_dir = _copy_config_to_tmp(tmp_path)

        regime_path = cfg_dir / "regime.yaml"
        regime = yaml.safe_load(regime_path.read_text(encoding="utf-8"))
        regime["system_stress"] = _valid_system_stress(enabled=False)
        _write_yaml(regime_path, regime)

        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        assert config.system_stress is not None
        assert config.system_stress.enabled is False
        assert config.system_stress.burn_in_bars == 120
        assert config.system_stress.aggregation.method == "weighted_vote"

    def test_config_rejects_invalid_system_stress(self, tmp_path: Path):
        """Invalid system_stress in YAML → ValidationError at startup."""
        from apps.reference.config_loader import ConfigLoader

        cfg_dir = _copy_config_to_tmp(tmp_path)

        regime_path = cfg_dir / "regime.yaml"
        regime = yaml.safe_load(regime_path.read_text(encoding="utf-8"))
        # Bad: exit_stress > enter_stress
        regime["system_stress"] = _valid_system_stress()
        regime["system_stress"]["state_mapping"]["exit_stress"] = 0.99
        regime["system_stress"]["state_mapping"]["enter_stress"] = 0.10
        _write_yaml(regime_path, regime)

        loader = ConfigLoader(config_dir=cfg_dir)
        with pytest.raises(ValidationError):
            loader.load_config()

    def test_config_rejects_unknown_field_in_system_stress(self, tmp_path: Path):
        """Extra field in system_stress → extra='forbid' crash."""
        from apps.reference.config_loader import ConfigLoader

        cfg_dir = _copy_config_to_tmp(tmp_path)

        regime_path = cfg_dir / "regime.yaml"
        regime = yaml.safe_load(regime_path.read_text(encoding="utf-8"))
        regime["system_stress"] = _valid_system_stress()
        regime["system_stress"]["mysterious_knob"] = 42
        _write_yaml(regime_path, regime)

        loader = ConfigLoader(config_dir=cfg_dir)
        with pytest.raises(ValidationError):
            loader.load_config()
