from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from apps.reference.config.domains.decision_making import VolAdjGatesConfig
from apps.reference.config_contract import ConfigContractError
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.strategies.runtimes.aurora.config_loader import (
    AuroraConfigLoaderMixin,
)


class DummyHandler(AuroraConfigLoaderMixin):
    def __init__(self, config):
        self.config = config
        self.logger = MagicMock()
        self._build_shield_cascade = MagicMock()


def _build_mock_config(*, gates) -> MagicMock:
    config = MagicMock()
    config.strategies = MagicMock()
    config.strategies.aurora = MagicMock()
    config.strategies.aurora.timeframe_sec = 60
    config.strategies.aurora.decision = SimpleNamespace(
        signal_threshold="0.1",
        side_bias_window_sec=60,
        side_bias_target_ratio=0.5,
        side_bias_penalty_factor=0.5,
        side_bias_min_intents=1,
        regime_threshold_multipliers={"DEFAULT": 1.0},
        gates=gates,
    )
    return config


def test_aurora_config_loader_enabled_vol_gates_load_explicit_yaml_thresholds() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    config = ConfigLoader(config_dir=repo_root /
                          "config" / "aurora").load_config()

    handler = DummyHandler(config)
    handler._load_config()

    assert handler.vol_gates_enabled is True
    assert handler.anti_flat_sigma == pytest.approx(0.48)
    assert handler.anti_fomo_sigma == pytest.approx(10.0)
    assert handler.motion_window_sec == 300
    assert handler.vol_gates_config_state == {
        "enabled": True,
        "anti_flat_sigma": 0.48,
        "anti_fomo_sigma": 10.0,
        "motion_window_sec": 300,
        "anti_flat_sigma_value_source": "active_config",
        "anti_fomo_sigma_value_source": "active_config",
        "motion_window_sec_value_source": "active_config",
        "missing_reason": None,
    }


def test_aurora_config_loader_disabled_vol_gates_do_not_expose_active_threshold_attrs() -> None:
    handler = DummyHandler(
        _build_mock_config(
            gates=SimpleNamespace(
                enabled=False,
                anti_flat_sigma=0.48,
                anti_fomo_sigma=10.0,
                motion_window_sec=300,
            )
        )
    )

    handler._load_config()

    assert handler.vol_gates_enabled is False
    assert handler.anti_flat_sigma is None
    assert handler.anti_fomo_sigma is None
    assert handler.motion_window_sec is None
    assert handler.vol_gates_config_state == {
        "enabled": False,
        "anti_flat_sigma": 0.48,
        "anti_fomo_sigma": 10.0,
        "motion_window_sec": 300,
        "anti_flat_sigma_value_source": "disabled_config_snapshot",
        "anti_fomo_sigma_value_source": "disabled_config_snapshot",
        "motion_window_sec_value_source": "disabled_config_snapshot",
        "missing_reason": "gate_disabled",
    }


def test_aurora_config_loader_missing_gate_enabled_fails_closed_without_active_threshold_attrs() -> None:
    handler = DummyHandler(
        _build_mock_config(
            gates=SimpleNamespace(
                anti_flat_sigma=0.48,
                anti_fomo_sigma=10.0,
                motion_window_sec=300,
            )
        )
    )

    handler._load_config()

    assert handler.vol_gates_enabled is False
    assert handler.anti_flat_sigma is None
    assert handler.anti_fomo_sigma is None
    assert handler.motion_window_sec is None
    assert handler.vol_gates_config_state == {
        "enabled": False,
        "anti_flat_sigma": 0.48,
        "anti_fomo_sigma": 10.0,
        "motion_window_sec": 300,
        "anti_flat_sigma_value_source": "disabled_config_snapshot",
        "anti_fomo_sigma_value_source": "disabled_config_snapshot",
        "motion_window_sec_value_source": "disabled_config_snapshot",
        "missing_reason": "gates_enabled_missing",
    }


def test_aurora_config_loader_enabled_missing_threshold_fails_closed() -> None:
    handler = DummyHandler(
        _build_mock_config(
            gates=SimpleNamespace(
                enabled=True,
                anti_flat_sigma=0.48,
                motion_window_sec=300,
            )
        )
    )

    with pytest.raises(ConfigContractError, match="anti_fomo_sigma"):
        handler._load_config()


@pytest.mark.parametrize(
    ("payload", "expected_fragment"),
    [
        (
            {"enabled": True, "anti_flat_sigma": 0.48, "motion_window_sec": 300},
            "anti_fomo_sigma",
        ),
        (
            {
                "enabled": True,
                "anti_flat_sigma": 0.48,
                "anti_fomo_sigma": None,
                "motion_window_sec": 300,
            },
            "anti_fomo_sigma",
        ),
        (
            {
                "enabled": True,
                "anti_flat_sigma": 0.48,
                "anti_fomo_sigma": 11.0,
                "motion_window_sec": 300,
            },
            "anti_fomo_sigma",
        ),
        (
            {
                "enabled": True,
                "anti_flat_sigma": 0.48,
                "anti_fomo_sigma": 10.0,
                "motion_window_sec": 5,
            },
            "motion_window_sec",
        ),
    ],
)
def test_aurora_config_loader_vol_gates_contract_rejects_missing_null_and_invalid_values(
    payload: dict,
    expected_fragment: str,
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        VolAdjGatesConfig(**payload)

    assert expected_fragment in str(excinfo.value)
