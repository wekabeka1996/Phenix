"""
Tests for override_allowlist module
====================================

Validates allowlist sets, path matching, override validation,
and partial-aurora-override warning logic.

18 tests across 4 classes, all marked @pytest.mark.unit.
"""

import pytest

from apps.reference.domains.alpha_search.runtime.override_allowlist import (
    AURORA_OVERRIDE_PATHS,
    MR_OVERRIDE_PATHS,
    ENSEMBLE_OVERRIDE_PATHS,
    STRATEGY_ALLOWLISTS,
    _path_matches_pattern,
    validate_overrides,
    warn_partial_aurora_overrides,
)


# =========================================================================
# Path matching
# =========================================================================

@pytest.mark.unit
class TestPathMatchesPattern:
    """Low-level fnmatch wrapper behaviour."""

    def test_exact_match(self):
        """Exact literal path matches itself."""
        assert _path_matches_pattern(
            "aurora.decision.signal_threshold",
            "aurora.decision.signal_threshold",
        ) is True

    def test_wildcard_star(self):
        """Trailing '*' matches any single segment."""
        assert _path_matches_pattern(
            "aurora.decision.signal_weights.obi",
            "aurora.decision.signal_weights.*",
        ) is True

    def test_no_match(self):
        """A path not covered by any AURORA pattern is rejected."""
        path = "aurora.internal.secret"
        assert not any(
            _path_matches_pattern(path, pattern)
            for pattern in AURORA_OVERRIDE_PATHS
        )


# =========================================================================
# validate_overrides
# =========================================================================

@pytest.mark.unit
class TestValidateOverrides:
    """End-to-end validation of override dicts against allowlists."""

    def test_aurora_exact_match_allowed(self):
        overrides = {"aurora.decision.signal_threshold": 0.12}
        assert validate_overrides("aurora", overrides) == []

    def test_aurora_wildcard_allowed(self):
        overrides = {"aurora.decision.signal_weights.obi": 0.3}
        assert validate_overrides("aurora", overrides) == []

    def test_aurora_asset_policy_paths_allowed(self):
        overrides = {
            "aurora.assets.BTCUSDT.allowed_regimes": ["TREND_UP"],
            "aurora.assets.BTCUSDT.signal_threshold.value": 0.22,
            "aurora.assets.BTCUSDT.exit.regime_tpsl.sl_mult.DEFAULT": 1.1,
            "aurora.assets.BTCUSDT.trailing_stop.enabled": True,
            "aurora.decision.exit.signal_exit_enabled": True,
        }
        assert validate_overrides("aurora", overrides) == []

    def test_aurora_rejected_path(self):
        overrides = {"aurora.internal.secret": True}
        rejected = validate_overrides("aurora", overrides)
        assert rejected == ["aurora.internal.secret"]

    def test_mr_exact_allowed(self):
        overrides = {"mean_reversion.strategy.bb_window": 20}
        assert validate_overrides("mean_reversion", overrides) == []

    def test_mr_per_asset_wildcard(self):
        overrides = {
            "mean_reversion.assets.BTCUSDT.strategy.rsi_oversold": 25,
        }
        assert validate_overrides("mean_reversion", overrides) == []

    def test_ensemble_model_wildcard(self):
        overrides = {
            "alpha_search.providers.ta_ensemble.ensemble.models.mean_reversion_v1.weight": 0.7,
        }
        assert validate_overrides("ensemble", overrides) == []

    def test_empty_overrides_returns_empty(self):
        assert validate_overrides("aurora", {}) == []

    def test_unknown_strategy_rejects_all(self):
        overrides = {"foo.bar": 1, "baz.qux": 2}
        rejected = validate_overrides("unknown", overrides)
        assert sorted(rejected) == sorted(overrides.keys())

    def test_mixed_allowed_and_rejected(self):
        overrides = {
            "aurora.decision.signal_threshold": 0.12,   # allowed
            "aurora.decision.signal_weights.obi": 0.3,  # allowed
            "aurora.internal.secret": True,              # rejected
            "aurora.hacks.exploit": 999,                 # rejected
        }
        rejected = validate_overrides("aurora", overrides)
        assert sorted(rejected) == [
            "aurora.hacks.exploit", "aurora.internal.secret"]


# =========================================================================
# warn_partial_aurora_overrides
# =========================================================================

@pytest.mark.unit
class TestWarnPartialAurora:
    """Soft warnings for incomplete aurora override sets."""

    def test_threshold_no_neutrals_warns(self):
        overrides = {"aurora.decision.signal_threshold": 0.18}
        warnings = warn_partial_aurora_overrides(overrides)
        assert len(warnings) == 1
        assert "signal_threshold" in warnings[0]
        assert "feature_neutrals" in warnings[0]

    def test_weights_no_neutrals_warns(self):
        overrides = {"aurora.decision.signal_weights.obi": 0.5}
        warnings = warn_partial_aurora_overrides(overrides)
        assert len(warnings) == 1
        assert "signal_weights" in warnings[0]
        assert "feature_neutrals" in warnings[0]

    def test_all_present_no_warning(self):
        overrides = {
            "aurora.decision.signal_threshold": 0.18,
            "aurora.decision.signal_weights.obi": 0.5,
            "aurora.decision.feature_neutrals.obi": 0.1,
        }
        assert warn_partial_aurora_overrides(overrides) == []


# =========================================================================
# Allowlist structure sanity checks
# =========================================================================

@pytest.mark.unit
class TestAllowlistStructure:
    """Guard-rails: ensure expected keys/paths are present in allowlists."""

    def test_strategy_allowlists_has_three_keys(self):
        assert "aurora" in STRATEGY_ALLOWLISTS
        assert "mean_reversion" in STRATEGY_ALLOWLISTS
        assert "ensemble" in STRATEGY_ALLOWLISTS

    def test_aurora_provider_threshold_in_allowlist(self):
        assert "alpha_search.providers.aurora.threshold" in AURORA_OVERRIDE_PATHS

    def test_aurora_asset_signal_threshold_wildcard_is_allowlisted(self):
        assert "aurora.assets.*.signal_threshold.*" in AURORA_OVERRIDE_PATHS

    def test_aurora_blocked_regimes_is_allowlisted(self):
        assert "aurora.decision.blocked_regimes" in AURORA_OVERRIDE_PATHS

    def test_aurora_exit_policy_paths_are_allowlisted(self):
        assert "aurora.decision.exit.signal_exit_enabled" in AURORA_OVERRIDE_PATHS
        assert "aurora.assets.*.exit.regime_tpsl.*" in AURORA_OVERRIDE_PATHS
        assert "aurora.assets.*.trailing_stop.*" in AURORA_OVERRIDE_PATHS

    def test_ensemble_system_model_tuning_wildcard(self):
        assert "alpha_search_system.momentum.*" in ENSEMBLE_OVERRIDE_PATHS

    def test_objective_feedback_weight_wildcard_is_allowlisted(self):
        assert "alpha_search.objective_feedback.quality_metric_weights.*" in ENSEMBLE_OVERRIDE_PATHS
