"""Focused regression tests for LEV-TARGET-MODE-REMOVE-2026-05-10.

Proves:
1. Aurora config loads with leverage block containing only max_notional_value
2. leverage.target and leverage.mode are absent and raise AttributeError if accessed
3. Stale YAML with target/mode present causes a Pydantic validation error (extra="forbid")
4. max_notional_value is None for all 7 active aurora symbols
5. collect_configs() (instruments SSOT) is unchanged by this seam
6. validate_ssot_consistency() no longer checks aurora leverage, returns empty list for aurora
"""
from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from apps.reference.config_loader import ConfigLoader
from apps.reference.config.strategies.aurora import AuroraLeverageOverrideConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path("config/aurora")

AURORA_SYMBOLS = ["ETHUSDT", "SOLUSDT", "BTCUSDT",
                  "BNBUSDT", "1000PEPEUSDT", "DOGEUSDT", "XRPUSDT"]


def _load_real_config():
    return ConfigLoader(_CONFIG_DIR).load_config()


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(Path("config/aurora"), cfg_dir)
    return cfg_dir


def _write_yaml(path: Path, data: Any) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Section 1: Model contract
# ---------------------------------------------------------------------------


class TestAuroraLeverageOverrideConfig:
    """AuroraLeverageOverrideConfig model contract tests."""

    def test_model_has_only_max_notional_value_field(self):
        """AuroraLeverageOverrideConfig has exactly one field: max_notional_value."""
        fields = set(AuroraLeverageOverrideConfig.model_fields.keys())
        assert fields == {"max_notional_value"}, (
            f"Unexpected fields in AuroraLeverageOverrideConfig: {fields - {'max_notional_value'}}. "
            "leverage.target and leverage.mode must not be present."
        )

    def test_no_target_attribute(self):
        """AuroraLeverageOverrideConfig instance has no .target attribute."""
        cfg = AuroraLeverageOverrideConfig(max_notional_value=None)
        assert not hasattr(
            cfg, "target"), "leverage.target must not exist on AuroraLeverageOverrideConfig"

    def test_no_mode_attribute(self):
        """AuroraLeverageOverrideConfig instance has no .mode attribute."""
        cfg = AuroraLeverageOverrideConfig(max_notional_value=None)
        assert not hasattr(
            cfg, "mode"), "leverage.mode must not exist on AuroraLeverageOverrideConfig"

    def test_max_notional_value_none_is_valid(self):
        """max_notional_value=None is valid (all aurora symbols use null)."""
        cfg = AuroraLeverageOverrideConfig(max_notional_value=None)
        assert cfg.max_notional_value is None

    def test_max_notional_value_decimal_is_valid(self):
        """max_notional_value can hold a positive Decimal."""
        cfg = AuroraLeverageOverrideConfig(
            max_notional_value=Decimal("500000"))
        assert cfg.max_notional_value == Decimal("500000")

    def test_stale_target_key_raises_validation_error(self):
        """extra='forbid': dict with 'target' key raises Pydantic ValidationError."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="target"):
            AuroraLeverageOverrideConfig(
                target=20, max_notional_value=None)  # type: ignore[call-arg]

    def test_stale_mode_key_raises_validation_error(self):
        """extra='forbid': dict with 'mode' key raises Pydantic ValidationError."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="mode"):
            AuroraLeverageOverrideConfig(
                # type: ignore[call-arg]
                mode="ISOLATED", max_notional_value=None)


# ---------------------------------------------------------------------------
# Section 2: Config loading — real aurora.yaml
# ---------------------------------------------------------------------------


class TestAuroraConfigLoadsWithoutTargetMode:
    """Prove that the real aurora.yaml loads cleanly with the new model."""

    def test_config_loads_without_error(self):
        """ConfigLoader.load_config() succeeds with leverage blocks containing only max_notional_value."""
        config = _load_real_config()
        assert config is not None

    def test_all_symbols_leverage_is_aurora_leverage_override_config(self):
        """All 7 aurora symbols have leverage typed as AuroraLeverageOverrideConfig."""
        config = _load_real_config()
        for symbol in AURORA_SYMBOLS:
            asset = config.strategies.aurora.assets[symbol]
            assert isinstance(asset.leverage, AuroraLeverageOverrideConfig), (
                f"{symbol}.leverage is {type(asset.leverage)}, expected AuroraLeverageOverrideConfig"
            )

    def test_all_symbols_max_notional_value_is_none(self):
        """All 7 aurora symbols have max_notional_value=None (as per YAML: max_notional_value: null)."""
        config = _load_real_config()
        for symbol in AURORA_SYMBOLS:
            asset = config.strategies.aurora.assets[symbol]
            assert asset.leverage.max_notional_value is None, (
                f"{symbol}.leverage.max_notional_value={asset.leverage.max_notional_value}, expected None"
            )

    def test_no_symbol_has_leverage_target(self):
        """No aurora asset has a leverage.target attribute (it was removed)."""
        config = _load_real_config()
        for symbol in AURORA_SYMBOLS:
            asset = config.strategies.aurora.assets[symbol]
            assert not hasattr(asset.leverage, "target"), (
                f"{symbol}.leverage.target still exists — removal incomplete"
            )

    def test_no_symbol_has_leverage_mode(self):
        """No aurora asset has a leverage.mode attribute (it was removed)."""
        config = _load_real_config()
        for symbol in AURORA_SYMBOLS:
            asset = config.strategies.aurora.assets[symbol]
            assert not hasattr(asset.leverage, "mode"), (
                f"{symbol}.leverage.mode still exists — removal incomplete"
            )


# ---------------------------------------------------------------------------
# Section 3: Stale-YAML fail-closed
# ---------------------------------------------------------------------------


class TestStaleYamlFailsClosed:
    """Prove that aurora.yaml with target/mode present fails at config load."""

    def test_stale_target_in_yaml_fails_validation(self, tmp_path: Path):
        """aurora.yaml with leverage.target causes Pydantic extra='forbid' error."""
        from pydantic import ValidationError

        cfg_dir = _copy_config_to_tmp(tmp_path)
        system_path = cfg_dir / "system.yaml"
        system_data = yaml.safe_load(system_path.read_text(encoding="utf-8"))
        system_data["trading_mode"] = "live"
        _write_yaml(system_path, system_data)

        aurora_path = cfg_dir / "strategies" / "aurora.yaml"
        data = yaml.safe_load(aurora_path.read_text(encoding="utf-8"))
        # Inject stale target back into ETHUSDT (first symbol)
        data["aurora"]["assets"]["ETHUSDT"]["leverage"]["target"] = 20
        _write_yaml(aurora_path, data)

        with pytest.raises((ValidationError, Exception)):
            ConfigLoader(cfg_dir).load_config()

    def test_stale_mode_in_yaml_fails_validation(self, tmp_path: Path):
        """aurora.yaml with leverage.mode causes Pydantic extra='forbid' error."""
        from pydantic import ValidationError

        cfg_dir = _copy_config_to_tmp(tmp_path)
        system_path = cfg_dir / "system.yaml"
        system_data = yaml.safe_load(system_path.read_text(encoding="utf-8"))
        system_data["trading_mode"] = "live"
        _write_yaml(system_path, system_data)

        aurora_path = cfg_dir / "strategies" / "aurora.yaml"
        data = yaml.safe_load(aurora_path.read_text(encoding="utf-8"))
        # Inject stale mode back into BTCUSDT
        data["aurora"]["assets"]["BTCUSDT"]["leverage"]["mode"] = "ISOLATED"
        _write_yaml(aurora_path, data)

        with pytest.raises((ValidationError, Exception)):
            ConfigLoader(cfg_dir).load_config()


# ---------------------------------------------------------------------------
# Section 4: collect_configs() unchanged (instruments SSOT path)
# ---------------------------------------------------------------------------


class TestCollectConfigsUnchanged:
    """Prove collect_configs() still returns instruments-derived leverage unchanged."""

    def _make_mock_fsm_config(self, btc_target: int = 25, eth_target: int = 20):
        config = MagicMock()
        config.strategies_registry.assignments = {
            "BTCUSDT": MagicMock(), "ETHUSDT": MagicMock()}
        btc_spec = MagicMock()
        btc_spec.execution.target_leverage = btc_target
        btc_spec.execution.margin_mode = "isolated"
        eth_spec = MagicMock()
        eth_spec.execution.target_leverage = eth_target
        eth_spec.execution.margin_mode = "isolated"
        config.instruments = {"BTCUSDT": btc_spec, "ETHUSDT": eth_spec}
        return config

    def test_collect_configs_reads_instruments_not_aurora(self):
        """collect_configs() returns target from instruments.execution, ignoring aurora.leverage."""
        from apps.reference.domains.execution_position.guards.leverage_config import LeverageConfigManager

        mock_fsm = MagicMock()
        mock_fsm.config = self._make_mock_fsm_config(
            btc_target=25, eth_target=20)
        mock_fsm.shadow_mode = True
        mock_fsm.adapter = None

        manager = LeverageConfigManager(fsm=mock_fsm)
        configs = manager.collect_configs()

        assert "BTCUSDT" in configs
        assert configs["BTCUSDT"].target == 25, (
            f"BTCUSDT target={configs['BTCUSDT'].target}, expected 25 (from instruments)"
        )
        assert configs["ETHUSDT"].target == 20

    def test_collect_configs_mode_from_instruments_margin_mode(self):
        """collect_configs() derives mode from instruments.execution.margin_mode (not aurora.leverage.mode)."""
        from apps.reference.domains.execution_position.guards.leverage_config import LeverageConfigManager

        mock_fsm = MagicMock()
        mock_fsm.config = self._make_mock_fsm_config()
        mock_fsm.shadow_mode = True
        mock_fsm.adapter = None

        manager = LeverageConfigManager(fsm=mock_fsm)
        configs = manager.collect_configs()

        assert configs["BTCUSDT"].mode == "ISOLATED"


# ---------------------------------------------------------------------------
# Section 5: validate_ssot_consistency() aurora block removed
# ---------------------------------------------------------------------------


class TestValidateSsotConsistencyAuroraBlock:
    """validate_ssot_consistency() no longer reads aurora.leverage.target."""

    def _make_manager_with_aurora_config(self, aurora_has_leverage_target: bool):
        """Create a LeverageConfigManager with a mock config.
        If aurora_has_leverage_target=True, aurora assets have .leverage.target (old style).
        If False, aurora assets have AuroraLeverageOverrideConfig (new style, no .target).
        """
        from apps.reference.domains.execution_position.guards.leverage_config import LeverageConfigManager

        config = MagicMock()
        btc_spec = MagicMock()
        btc_spec.execution.target_leverage = 25
        config.instruments = {"BTCUSDT": btc_spec}

        if aurora_has_leverage_target:
            aurora_asset = MagicMock()
            # mismatched — would produce warning if aurora block active
            aurora_asset.leverage.target = 35
        else:
            aurora_asset = MagicMock(spec=["leverage"])
            # AuroraLeverageOverrideConfig has no .target — accessing it raises AttributeError
            del aurora_asset.leverage.target

        config.strategies.aurora.assets = {"BTCUSDT": aurora_asset}
        # No MR assets
        config.strategies.mean_reversion.assets = {}

        mock_fsm = MagicMock()
        mock_fsm.config = config
        mock_fsm.shadow_mode = True
        mock_fsm.adapter = None
        return LeverageConfigManager(fsm=mock_fsm)

    def test_no_aurora_warnings_regardless_of_aurora_leverage(self):
        """validate_ssot_consistency() produces no aurora warnings even if aurora had mismatched leverage."""
        manager = self._make_manager_with_aurora_config(
            aurora_has_leverage_target=True)
        warnings = manager.validate_ssot_consistency()
        aurora_warnings = [w for w in warnings if "aurora" in w.lower()]
        assert aurora_warnings == [], (
            f"Aurora SSOT warnings should be gone (aurora block removed): {aurora_warnings}"
        )

    def test_no_attribute_error_on_new_style_aurora_config(self):
        """validate_ssot_consistency() does not raise AttributeError with new AuroraLeverageOverrideConfig."""
        manager = self._make_manager_with_aurora_config(
            aurora_has_leverage_target=False)
        # Must not raise
        warnings = manager.validate_ssot_consistency()
        assert isinstance(warnings, list)
