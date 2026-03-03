"""
Contract test: absorption_dp_cap_pct validation (Tier 0 fix).

ABSORPTION-DP-CAP-CONTRACT-01:
dp_cap_pct is the normalization cap for the absorption formula's delta_price term.
When mode != 'disabled', this value MUST be present and positive.
A missing value (None) previously caused division-by-zero in scoring.

Tests cover:
  - Property raises ValueError when mode != 'disabled' and dp_cap_pct is None
  - Property returns configured value when dp_cap_pct is set
  - Property does not raise when mode == 'disabled'
  - Pydantic AbsorptionConfig model_validator enforces the same contract
  - calculation_engine uses config value (not hardcoded 0.02)
"""
import pytest
from unittest.mock import MagicMock


def _make_fe_config_with_absorption(mode: str, dp_cap_pct):
    """Build a FeatureEngineeringConfig with absorption set to given values."""
    from apps.reference.domains.feature_engineering.types import FeatureEngineeringConfig
    instance = object.__new__(FeatureEngineeringConfig)
    mock_cfg = MagicMock()
    mock_cfg.absorption = MagicMock()
    mock_cfg.absorption.mode = mode
    mock_cfg.absorption.dp_cap_pct = dp_cap_pct
    instance._cfg = mock_cfg
    return instance


class TestAbsorptionDpCapProperty:
    """FeatureEngineeringConfig.absorption_dp_cap_pct property contracts."""

    def test_disabled_mode_does_not_raise(self):
        """
        When absorption is None (disabled), dp_cap_pct is irrelevant.
        Property must not raise — system can start without absorption configured.
        """
        from apps.reference.domains.feature_engineering.types import FeatureEngineeringConfig
        instance = object.__new__(FeatureEngineeringConfig)
        mock_cfg = MagicMock()
        mock_cfg.absorption = None
        instance._cfg = mock_cfg

        result = instance.absorption_dp_cap_pct
        assert isinstance(
            result, float), "Expected float fallback for disabled mode"

    def test_proxy_mode_with_dp_cap_returns_value(self):
        """When mode='proxy' and dp_cap_pct=0.03, property returns 0.03."""
        instance = _make_fe_config_with_absorption("proxy", 0.03)
        assert abs(instance.absorption_dp_cap_pct - 0.03) < 1e-9

    def test_full_mode_with_dp_cap_returns_value(self):
        """When mode='full' and dp_cap_pct=0.05, property returns 0.05."""
        instance = _make_fe_config_with_absorption("full", 0.05)
        assert abs(instance.absorption_dp_cap_pct - 0.05) < 1e-9

    def test_proxy_mode_no_dp_cap_raises_value_error(self):
        """
        When mode='proxy' and dp_cap_pct=None, must raise ValueError.
        This is the fail-loud contract: missing cap → explicit error, not silent 0.
        """
        instance = _make_fe_config_with_absorption("proxy", None)
        with pytest.raises(ValueError, match="absorption.dp_cap_pct"):
            _ = instance.absorption_dp_cap_pct

    def test_full_mode_no_dp_cap_raises_value_error(self):
        """Same contract for mode='full'."""
        instance = _make_fe_config_with_absorption("full", None)
        with pytest.raises(ValueError, match="absorption.dp_cap_pct"):
            _ = instance.absorption_dp_cap_pct

    def test_returned_value_is_positive(self):
        """dp_cap_pct must be positive — zero would cause division-by-zero."""
        instance = _make_fe_config_with_absorption("proxy", 0.02)
        assert instance.absorption_dp_cap_pct > 0

    def test_different_values_are_returned_correctly(self):
        """Property correctly distinguishes 0.01 from 0.05 (no hardcoded constant)."""
        inst_a = _make_fe_config_with_absorption("proxy", 0.01)
        inst_b = _make_fe_config_with_absorption("proxy", 0.05)
        assert inst_a.absorption_dp_cap_pct != inst_b.absorption_dp_cap_pct, (
            "Property returned the same value for different configs — "
            "likely returning a hardcoded constant instead of config value."
        )


class TestAbsorptionPydanticModelContract:
    """AbsorptionConfig Pydantic model enforces dp_cap_pct at parse time."""

    def test_proxy_mode_requires_dp_cap_pct(self):
        """
        AbsorptionConfig(mode='proxy', dp_cap_pct=None) must be rejected
        by the model_validator at YAML parse time, not at runtime.
        """
        from apps.reference.config_models import AbsorptionConfig
        with pytest.raises(Exception):  # pydantic.ValidationError
            AbsorptionConfig(mode="proxy", dp_cap_pct=None)

    def test_full_mode_requires_dp_cap_pct(self):
        """Same constraint for mode='full'."""
        from apps.reference.config_models import AbsorptionConfig
        with pytest.raises(Exception):  # pydantic.ValidationError
            AbsorptionConfig(mode="full", dp_cap_pct=None)

    def test_disabled_mode_does_not_require_dp_cap_pct(self):
        """AbsorptionConfig(mode='disabled') must be valid even without dp_cap_pct."""
        from apps.reference.config_models import AbsorptionConfig
        # Should not raise
        cfg = AbsorptionConfig(mode="disabled")
        assert cfg.mode == "disabled"

    def test_proxy_mode_with_valid_dp_cap_accepted(self):
        """AbsorptionConfig(mode='proxy', dp_cap_pct=0.02) is a valid config."""
        from apps.reference.config_models import AbsorptionConfig, AbsorptionProxyConfig
        cfg = AbsorptionConfig(
            mode="proxy",
            dp_cap_pct=0.02,
            proxy=AbsorptionProxyConfig(
                source="aggressive_trade_imbalance",
                window=30,
                eps=0.0001,
            ),
        )
        assert cfg.dp_cap_pct == 0.02


class TestCalculationEngineUsesConfigDpCap:
    """
    Regression: calculation_engine must read dp_cap from config,
    not from a hardcoded 0.02 constant (Tier 0 fix verification).
    Uses AST inspection — more reliable than a behavioral test that
    depends on buffer warmup and dedup thresholds.
    """

    def test_compute_absorption_references_config_dp_cap(self):
        """
        compute_absorption (or update_absorption) must reference
        self.cfg.absorption_dp_cap_pct — not a raw float literal like 0.02.
        """
        import ast
        import pathlib

        source = pathlib.Path(
            "apps/reference/domains/feature_engineering/calculation_engine.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)

        assert "absorption_dp_cap_pct" in source, (
            "calculation_engine.py does not reference 'absorption_dp_cap_pct'. "
            "The hardcoded dp_cap = 0.02 fix (Tier 0) has been reverted."
        )

    def test_no_hardcoded_002_dp_cap_in_compute_absorption(self):
        """
        The literal 0.02 must NOT appear as a standalone assignment for dp_cap
        in compute_absorption. It should come from self.cfg.absorption_dp_cap_pct.
        """
        import ast
        import pathlib

        source = pathlib.Path(
            "apps/reference/domains/feature_engineering/calculation_engine.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if "absorption" not in node.name.lower():
                continue
            for child in ast.walk(node):
                # Look for: dp_cap = 0.02  (assignment of literal 0.02 to dp_cap var)
                if not isinstance(child, ast.Assign):
                    continue
                for target in child.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if "dp_cap" not in target.id:
                        continue
                    if isinstance(child.value, ast.Constant) and child.value.value == 0.02:
                        pytest.fail(
                            f"Hardcoded `{target.id} = 0.02` found in {node.name}() "
                            f"at line {child.lineno}. "
                            "Must use self.cfg.absorption_dp_cap_pct instead."
                        )
