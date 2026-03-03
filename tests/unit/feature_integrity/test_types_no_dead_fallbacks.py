"""
Regression test: Tier 2 dead code elimination in types.py.

TIER-2-NO-DEAD-FALLBACKS-CONTRACT:
Before Tier 2, 26 properties in FeatureEngineeringConfig had this anti-pattern:

    @property
    def some_param(self):
        try:
            return self._cfg.section.some_param
        except AttributeError:
            return HARDCODED_MAGIC_NUMBER  # ← dead code & hidden failure

After Tier 2, the backing Pydantic models (MacroResidConfig, AbsorptionConfig,
SpreadHealthConfig, BarTAConfig, FeatureSanityConfig) enforce all fields.
The try/except fallbacks became unreachable dead code AND a liability:
if the real config is missing a field, Pydantic raises at load time (good),
but if it gets past Pydantic somehow, the fallback silently returns the
wrong value instead of propagating the error.

These tests guard against regression:
  - AST tests: verify no try/except in the 26 post-Tier-2 properties
  - Behavioral tests: verify properties return config values, not hardcoded ones
"""
import ast
import pathlib
import pytest
from unittest.mock import MagicMock


ROOT = pathlib.Path("apps/reference/domains/feature_engineering/types.py")


def _get_source() -> str:
    return ROOT.read_text(encoding="utf-8")


def _property_has_try_except(source: str, property_name: str) -> bool:
    """Return True if the named function/property contains ANY try block."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != property_name:
            continue
        return any(isinstance(child, ast.Try) for child in ast.walk(node))
    return False


# ── Groups of properties cleaned up in Tier 2 ────────────────────────────────

GROUP_A_MACRO_RESID = [
    "macro_resid_enabled",
    "macro_resid_beta_window",
    "macro_resid_mad_window",
    "macro_resid_winsor_percentile",
    "macro_resid_var_floor",
    "macro_resid_scale_floor",
    "macro_resid_clip",
    "macro_resid_neutral",
]

GROUP_B_ABSORPTION = [
    "absorption_mode",
    "absorption_proxy_source",
    "absorption_proxy_window",
    "absorption_proxy_eps",
    "absorption_dedup_enabled",
    "absorption_dedup_window",
    "absorption_dedup_threshold",
    "absorption_clip",
    "absorption_neutral",
]

GROUP_C_SPREAD_HEALTH = [
    "spread_health_gate_enabled",
    "spread_health_max_age_sec",
    "spread_health_min_update_events",
    "spread_health_min_trades_count",
    "spread_health_window_sec",
]

GROUP_D_BAR_TA = [
    "bar_ta_rsi_period",
    "bar_ta_bb_window",
    "bar_ta_bb_num_std",
    "bar_ta_stoch_k_period",
    "bar_ta_stoch_d_period",
]

GROUP_E_FEATURE_SANITY = [
    "feature_sanity_enabled",
    "feature_sanity_nan_inf_behavior",
    "feature_sanity_bounds",
]


# ── AST tests ─────────────────────────────────────────────────────────────────

class TestNoTryExceptInTier2Properties:
    """
    Verify that all 26 Tier-2 properties have no try/except blocks.
    A try/except here is dead code that may hide config problems.
    """

    @pytest.mark.parametrize("prop", GROUP_A_MACRO_RESID)
    def test_macro_resid_no_try_except(self, prop):
        source = _get_source()
        assert not _property_has_try_except(source, prop), (
            f"'{prop}' still contains try/except. "
            "Tier 2 requires direct config access — MacroResidConfig Pydantic "
            "model enforces field presence at load time."
        )

    @pytest.mark.parametrize("prop", GROUP_B_ABSORPTION)
    def test_absorption_no_try_except(self, prop):
        source = _get_source()
        assert not _property_has_try_except(source, prop), (
            f"'{prop}' still contains try/except. "
            "AbsorptionConfig Pydantic model enforces field presence."
        )

    @pytest.mark.parametrize("prop", GROUP_C_SPREAD_HEALTH)
    def test_spread_health_no_try_except(self, prop):
        source = _get_source()
        assert not _property_has_try_except(source, prop), (
            f"'{prop}' still contains try/except. "
            "SpreadHealthConfig Pydantic model enforces field presence."
        )

    @pytest.mark.parametrize("prop", GROUP_D_BAR_TA)
    def test_bar_ta_no_try_except(self, prop):
        source = _get_source()
        assert not _property_has_try_except(source, prop), (
            f"'{prop}' still contains try/except. "
            "BarTAConfig Pydantic model enforces field presence."
        )

    @pytest.mark.parametrize("prop", GROUP_E_FEATURE_SANITY)
    def test_feature_sanity_no_try_except(self, prop):
        source = _get_source()
        assert not _property_has_try_except(source, prop), (
            f"'{prop}' still contains try/except. "
            "FeatureSanityConfig Pydantic model enforces field presence."
        )


# ── Behavioral regression tests ───────────────────────────────────────────────

def _make_instance(inner_cfg: MagicMock):
    from apps.reference.domains.feature_engineering.types import FeatureEngineeringConfig
    inst = object.__new__(FeatureEngineeringConfig)
    inst._cfg = inner_cfg
    return inst


class TestBehavioralNoHardcodedFallbacks:
    """
    Verify properties return the value from config, not a hardcoded default.
    Each test uses a non-standard value that the old hardcoded magic wouldn't return.
    """

    def test_macro_resid_beta_window_from_config(self):
        """Must return 99 from config, not hardcoded 60."""
        mock = MagicMock()
        mock.macro_resid.beta_window = 99
        assert _make_instance(mock).macro_resid_beta_window == 99, (
            "macro_resid_beta_window returned hardcoded 60 instead of config value 99."
        )

    def test_macro_resid_mad_window_from_config(self):
        """Must return 77 from config, not hardcoded 30."""
        mock = MagicMock()
        mock.macro_resid.mad_window = 77
        assert _make_instance(mock).macro_resid_mad_window == 77, (
            "macro_resid_mad_window returned hardcoded 30 instead of config value 77."
        )

    def test_macro_resid_clip_from_config(self):
        """Must return 5.0 from config, not hardcoded 3.0."""
        mock = MagicMock()
        mock.macro_resid.clip = 5.0
        result = _make_instance(mock).macro_resid_clip
        assert abs(result - 5.0) < 1e-9, (
            f"macro_resid_clip returned {result}, expected 5.0 from config."
        )

    def test_absorption_dedup_window_from_config(self):
        """Must return 120 from config, not hardcoded 60."""
        mock = MagicMock()
        mock.absorption = MagicMock()
        mock.absorption.dedup = MagicMock()
        mock.absorption.dedup.window = 120
        result = _make_instance(mock).absorption_dedup_window
        assert result == 120, (
            f"absorption_dedup_window returned {result}, expected 120 from config."
        )

    def test_absorption_dedup_threshold_from_config(self):
        """Must return 0.75 from config, not hardcoded 0.8."""
        mock = MagicMock()
        mock.absorption = MagicMock()
        mock.absorption.dedup = MagicMock()
        mock.absorption.dedup.threshold = 0.75
        result = _make_instance(mock).absorption_dedup_threshold
        assert abs(result - 0.75) < 1e-9, (
            f"absorption_dedup_threshold returned {result}, expected 0.75 from config."
        )

    def test_spread_health_window_sec_from_config(self):
        """Must return 42.0 from config, not hardcoded 10.0."""
        mock = MagicMock()
        mock.spread_bps = MagicMock()
        mock.spread_bps.health_gate = MagicMock()
        mock.spread_bps.health_gate.window_sec = 42.0
        result = _make_instance(mock).spread_health_window_sec
        assert abs(result - 42.0) < 1e-9, (
            f"spread_health_window_sec returned {result}, expected 42.0 from config."
        )

    def test_spread_health_max_age_sec_from_config(self):
        """Must return 15.0 from config, not hardcoded 5.0."""
        mock = MagicMock()
        mock.spread_bps = MagicMock()
        mock.spread_bps.health_gate = MagicMock()
        mock.spread_bps.health_gate.max_age_sec = 15.0
        result = _make_instance(mock).spread_health_max_age_sec
        assert abs(result - 15.0) < 1e-9, (
            f"spread_health_max_age_sec returned {result}, expected 15.0 from config."
        )

    def test_bar_ta_rsi_period_from_config(self):
        """Must return 21 from config, not hardcoded 14."""
        mock = MagicMock()
        mock.bar_ta = MagicMock()
        mock.bar_ta.rsi_period = 21
        assert _make_instance(mock).bar_ta_rsi_period == 21, (
            "bar_ta_rsi_period returned hardcoded 14 instead of config value 21."
        )

    def test_bar_ta_bb_window_from_config(self):
        """Must return 50 from config, not hardcoded 20."""
        mock = MagicMock()
        mock.bar_ta = MagicMock()
        mock.bar_ta.bb_window = 50
        assert _make_instance(mock).bar_ta_bb_window == 50, (
            "bar_ta_bb_window returned hardcoded 20 instead of config value 50."
        )

    def test_feature_sanity_enabled_from_config(self):
        """Must return True from config, not hardcoded False."""
        mock = MagicMock()
        mock.feature_sanity = MagicMock()
        mock.feature_sanity.enabled = True
        assert _make_instance(mock).feature_sanity_enabled is True, (
            "feature_sanity_enabled returned hardcoded False instead of config True."
        )
