"""
Tests for ExecutionPositionConfig loading from YAML dict.

LEVERAGE-FIX: Verify that ROI-based bracket config is properly loaded.
"""

import pytest

from apps.reference.domains.execution_position.infra.runtime_factory import (
    _build_ep_config,
    V2RuntimeFacade,
)


class TestBuildEpConfig:
    """Test _build_ep_config factory function."""

    def test_loads_config_from_execution_aggregated_oco(self):
        """Config is loaded from execution.aggregated_oco path."""
        config_dict = {
            "execution": {
                "aggregated_oco": {
                    "enabled": True,
                    "sl_roi_pct": 35.0,
                    "tp_roi_pct": 50.0,
                    "sl_pct": 0.02,
                    "tp_rr": 2.0,
                }
            }
        }
        ep_cfg = _build_ep_config(config_dict)
        assert ep_cfg is not None
        assert ep_cfg.aggregated_oco.sl_roi_pct == 35.0
        assert ep_cfg.aggregated_oco.tp_roi_pct == 50.0
        assert ep_cfg.aggregated_oco.enabled is True

    def test_loads_config_from_execution_position_aggregated_oco(self):
        """Config is loaded from execution_position.aggregated_oco fallback path."""
        config_dict = {
            "execution_position": {
                "aggregated_oco": {
                    "enabled": True,
                    "sl_roi_pct": 40.0,
                    "tp_roi_pct": 60.0,
                }
            }
        }
        ep_cfg = _build_ep_config(config_dict)
        assert ep_cfg is not None
        assert ep_cfg.aggregated_oco.sl_roi_pct == 40.0
        assert ep_cfg.aggregated_oco.tp_roi_pct == 60.0

    def test_returns_none_if_no_aggregated_oco(self):
        """Returns None when no aggregated_oco config found."""
        config_dict = {"execution": {}}
        ep_cfg = _build_ep_config(config_dict)
        assert ep_cfg is None

    def test_uses_defaults_for_missing_fields(self):
        """Missing fields use defaults."""
        config_dict = {
            "execution": {
                "aggregated_oco": {
                    "enabled": True,
                }
            }
        }
        ep_cfg = _build_ep_config(config_dict)
        assert ep_cfg is not None
        # Defaults
        assert ep_cfg.aggregated_oco.sl_roi_pct == 35.0
        assert ep_cfg.aggregated_oco.tp_roi_pct == 50.0
        assert ep_cfg.aggregated_oco.sl_pct == 0.02
        assert ep_cfg.aggregated_oco.tp_rr == 2.0

    def test_loads_throttle_settings(self):
        """Throttle settings are loaded from config."""
        config_dict = {
            "execution": {
                "aggregated_oco": {
                    "enabled": True,
                    "bracket_throttle_sec": 5.0,
                    "bracket_suppression_sec": 15.0,
                }
            }
        }
        ep_cfg = _build_ep_config(config_dict)
        assert ep_cfg is not None
        assert ep_cfg.aggregated_oco.bracket_throttle_sec == 5.0
        assert ep_cfg.aggregated_oco.bracket_suppression_sec == 15.0


class TestV2RuntimeFacadeWithEpConfig:
    """Test that V2RuntimeFacade passes ep_config to runtime."""

    def test_facade_passes_ep_config_to_runtime(self):
        """Verify ep_config is passed through to ExecPosRuntimeV2."""
        config_dict = {
            "execution": {
                "aggregated_oco": {
                    "enabled": True,
                    "sl_roi_pct": 35.0,
                    "tp_roi_pct": 50.0,
                }
            }
        }
        ep_cfg = _build_ep_config(config_dict)
        assert ep_cfg is not None

        # Create facade with ep_config
        facade = V2RuntimeFacade(
            config=config_dict,
            adapter=None,
            price_service=None,
            ep_config=ep_cfg,
        )

        # Verify runtime has the config
        assert facade.runtime._ep_cfg is not None
        assert facade.runtime._ep_cfg.aggregated_oco.sl_roi_pct == 35.0
        assert facade.runtime._ep_cfg.aggregated_oco.tp_roi_pct == 50.0

    def test_facade_without_ep_config_uses_none(self):
        """Verify facade works without ep_config (legacy path)."""
        config_dict = {}

        facade = V2RuntimeFacade(
            config=config_dict,
            adapter=None,
            price_service=None,
            ep_config=None,
        )

        # Runtime should have None ep_cfg (legacy path)
        assert facade.runtime._ep_cfg is None
