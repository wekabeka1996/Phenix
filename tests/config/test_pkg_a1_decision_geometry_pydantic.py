"""PKG-A1: Prove Pydantic decision_geometry is parsed and NOT silently dropped.

Unknown U1 from the baseline report: whether config_loader uses getattr chains
that would silently fall back to "quadratic" if decision_geometry is not exposed
by the Pydantic model.

This test:
1. Loads the real aurora.yaml config through Pydantic.
2. Asserts that decision_geometry.admission_mode == "linear" is present.
3. Instantiates AuroraConfigLoaderMixin with the real config and calls _load_config().
4. Asserts that handler.decision_admission_mode == "linear" (not the kernel default "quadratic").
5. If decision_geometry were silently dropped, getattr fallback returns "quadratic" -- this test fails.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.strategies.runtimes.aurora.config_loader import (
    AuroraConfigLoaderMixin,
)

_AURORA_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config" / "aurora"


class _DummyHandler(AuroraConfigLoaderMixin):
    def __init__(self, config):
        self.config = config
        self.logger = MagicMock()
        self._build_shield_cascade = MagicMock()


def _load_aurora_config():
    return ConfigLoader(config_dir=_AURORA_CONFIG_DIR).load_config()


class TestDecisionGeometryPydanticParsing:
    """decision_geometry must survive Pydantic parsing with correct values."""

    def test_decision_geometry_is_not_none_after_pydantic_load(self):
        config = _load_aurora_config()
        decision = config.strategies.aurora.decision
        assert decision.decision_geometry is not None, (
            "decision_geometry was silently dropped by Pydantic — "
            "check that DecisionConfig.decision_geometry is not Optional without default"
        )

    def test_admission_mode_is_linear_in_pydantic_object(self):
        config = _load_aurora_config()
        decision = config.strategies.aurora.decision
        assert decision.decision_geometry.admission_mode == "linear", (
            f"Expected admission_mode='linear' from aurora.yaml; "
            f"got {decision.decision_geometry.admission_mode!r}"
        )

    def test_sizing_mode_is_soft_power_in_pydantic_object(self):
        config = _load_aurora_config()
        decision = config.strategies.aurora.decision
        assert decision.decision_geometry.sizing_mode == "soft_power"

    def test_admission_shield_floor_is_set(self):
        config = _load_aurora_config()
        decision = config.strategies.aurora.decision
        assert decision.decision_geometry.admission_shield_floor == pytest.approx(
            0.75)


class TestConfigLoaderReadsDecisionGeometry:
    """AuroraConfigLoaderMixin must read decision_geometry and not fall back to kernel default."""

    def test_decision_admission_mode_is_linear_not_quadratic(self):
        config = _load_aurora_config()
        handler = _DummyHandler(config)
        handler._load_config()

        assert handler.decision_admission_mode == "linear", (
            f"Expected handler.decision_admission_mode='linear'; "
            f"got {handler.decision_admission_mode!r}. "
            "If 'quadratic': config_loader's getattr fallback is masking decision_geometry loss."
        )

    def test_decision_sizing_mode_is_soft_power(self):
        config = _load_aurora_config()
        handler = _DummyHandler(config)
        handler._load_config()
        assert handler.decision_sizing_mode == "soft_power"

    def test_decision_admission_shield_floor_propagates(self):
        config = _load_aurora_config()
        handler = _DummyHandler(config)
        handler._load_config()
        assert handler.decision_admission_shield_floor == pytest.approx(0.75)

    def test_if_decision_geometry_none_falls_back_to_quadratic(self):
        """Document the fallback behavior when decision_geometry is absent."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        mock_config = MagicMock()
        mock_config.strategies.aurora.timeframe_sec = 60
        mock_config.strategies.aurora.decision = SimpleNamespace(
            signal_threshold="0.1",
            side_bias_window_sec=60,
            side_bias_target_ratio=0.5,
            side_bias_penalty_factor=0.5,
            side_bias_min_intents=1,
            regime_threshold_multipliers={"DEFAULT": 1.0},
            decision_geometry=None,  # simulate missing
        )

        handler = _DummyHandler(mock_config)
        handler._load_config()

        # The getattr fallback returns "quadratic" — this is a known risk.
        # A real config MUST have decision_geometry; the live test above proves it does.
        assert handler.decision_admission_mode == "quadratic", (
            "Known: when decision_geometry is None, fallback is 'quadratic'. "
            "This test documents the risk, not endorses it."
        )
