"""
Override Allowlists per Strategy Type
======================================

Defines which config paths are safe to override per strategy family.
Prevents accidental mutation of structural config or cross-strategy contamination.

Paths use dot-notation with '*' wildcard for asset/model level.
Example: "aurora.decision.signal_weights.*" allows any signal weight override.
"""

from typing import Dict, Any, List, Set
import fnmatch
import logging

LOG = logging.getLogger(__name__)


# =============================================================================
# Aurora Strategy ΓÇö Allowlisted Override Paths
# =============================================================================

AURORA_OVERRIDE_PATHS: Set[str] = {
    # Global decision params (aurora.yaml ΓÇö for reference, adapter uses adapter.* paths)
    "aurora.decision.signal_threshold",
    "aurora.decision.neutral_threshold",
    "aurora.decision.gates.anti_flat_sigma",
    "aurora.decision.gates.anti_fomo_sigma",
    "aurora.decision.reentry_cooldown_sec",
    # Signal weights (per-signal) in aurora.yaml
    "aurora.decision.signal_weights.*",
    # Feature neutrals (per-signal) in aurora.yaml
    "aurora.decision.feature_neutrals.*",
    # Regime threshold multipliers in aurora.yaml
    "aurora.decision.regime_threshold_multipliers.*",
    # Direction strength scoring in aurora.yaml
    "aurora.decision.direction_strength_scoring.strength_alpha",
    "aurora.decision.direction_strength_scoring.strength_cap",
    "aurora.decision.direction_strength_scoring.strength_exp",
    # Per-asset overrides in aurora.yaml
    "aurora.assets.*.weights.*",
    "aurora.assets.*.regime_thresholds.*",
    "aurora.assets.*.signal_threshold",
    # ------------------------------------------------------------------
    # alpha_search adapter params (SSOT for alpha_search scoring).
    # These override the adapter directly ΓÇö no need to touch aurora.yaml.
    # ------------------------------------------------------------------
    "alpha_search.providers.aurora.threshold",
    "alpha_search.providers.aurora.symbols",
    "alpha_search.providers.aurora.adapter.base_threshold",
    "alpha_search.providers.aurora.adapter.delta_price_cap_pct",
    "alpha_search.providers.aurora.adapter.essential_features",
    "alpha_search.providers.aurora.adapter.signal_weights.*",
    "alpha_search.providers.aurora.adapter.feature_neutrals.*",
    "alpha_search.providers.aurora.adapter.regime_thresholds.*",
    "alpha_search.providers.aurora.adapter.direction_strength.strength_alpha",
    "alpha_search.providers.aurora.adapter.direction_strength.strength_cap",
    "alpha_search.objective_feedback.window_trades",
    "alpha_search.objective_feedback.min_trades_before_reweight",
    "alpha_search.objective_feedback.rebalance_every_closed_trades",
    "alpha_search.objective_feedback.quality_metric_weights.*",
    "alpha_search.objective_feedback.min_provider_weight",
    "alpha_search.objective_feedback.max_provider_weight",
}


# =============================================================================
# Mean Reversion Strategy ΓÇö Allowlisted Override Paths
# =============================================================================

MR_OVERRIDE_PATHS: Set[str] = {
    # Global MR strategy params
    "mean_reversion.strategy.bb_window",
    "mean_reversion.strategy.bb_num_std",
    "mean_reversion.strategy.entry_threshold",
    "mean_reversion.strategy.rsi_oversold",
    "mean_reversion.strategy.rsi_overbought",
    "mean_reversion.strategy.sl_atr_mult",
    "mean_reversion.strategy.cooldown_sec",
    "mean_reversion.strategy.min_bars",
    # Per-asset MR tuning
    "mean_reversion.assets.*.strategy.*",
    # Alpha search system model tuning
    "alpha_search_system.mean_reversion.weights.*",
    "alpha_search_system.mean_reversion.rsi.*",
    "alpha_search_system.mean_reversion.sma.*",
    "alpha_search_system.mean_reversion.stochastic.*",
    "alpha_search_system.mean_reversion.volume.*",
    "alpha_search_system.mean_reversion.bb_width.*",
    "alpha_search_system.mean_reversion.confidence.*",
    # Alpha search provider threshold
    "alpha_search.providers.ta_ensemble.threshold",
    # Aurora provider threshold (for cross-strategy differentiation)
    "alpha_search.providers.aurora.threshold",
    # Virtual trader behaviour tuning
    "alpha_search.virtual_trader.flip_on_reversal",
    "alpha_search.virtual_trader.notional_size",
    # Provider timeframe filter
    "alpha_search.providers.ta_ensemble.min_tf_sec",
    "alpha_search.providers.aurora.min_tf_sec",
    # Exit / cooldown tuning
    "alpha_search.virtual_trader.exit.cooldown_bars_after_close",
    "alpha_search.virtual_trader.exit.max_drawdown_exit",
    "alpha_search.virtual_trader.exit.max_bars",
    "alpha_search.objective_feedback.window_trades",
    "alpha_search.objective_feedback.min_trades_before_reweight",
    "alpha_search.objective_feedback.rebalance_every_closed_trades",
    "alpha_search.objective_feedback.quality_metric_weights.*",
    "alpha_search.objective_feedback.min_provider_weight",
    "alpha_search.objective_feedback.max_provider_weight",
}


# =============================================================================
# Ensemble Strategy ΓÇö Allowlisted Override Paths
# =============================================================================

ENSEMBLE_OVERRIDE_PATHS: Set[str] = {
    # Per-model enable/disable
    "alpha_search.providers.ta_ensemble.ensemble.models.*.enabled",
    "alpha_search.providers.ta_ensemble.ensemble.models.*.weight",
    "alpha_search.providers.ta_ensemble.threshold",
    # Aurora provider threshold (for cross-strategy differentiation)
    "alpha_search.providers.aurora.threshold",
    # Ensemble system config
    "alpha_search.providers.ta_ensemble.ensemble.rebalance_frequency_days",
    "alpha_search.providers.ta_ensemble.ensemble.risk_adjustment",
    # All model tuning params
    "alpha_search_system.ensemble.*",
    "alpha_search_system.momentum.*",
    "alpha_search_system.mean_reversion.*",
    "alpha_search_system.volatility.*",
    # Virtual trader behaviour tuning
    "alpha_search.virtual_trader.flip_on_reversal",
    "alpha_search.virtual_trader.notional_size",
    # Provider timeframe filter
    "alpha_search.providers.ta_ensemble.min_tf_sec",
    "alpha_search.providers.aurora.min_tf_sec",
    # Exit / cooldown tuning
    "alpha_search.virtual_trader.exit.cooldown_bars_after_close",
    "alpha_search.virtual_trader.exit.max_drawdown_exit",
    "alpha_search.virtual_trader.exit.max_bars",
    "alpha_search.objective_feedback.window_trades",
    "alpha_search.objective_feedback.min_trades_before_reweight",
    "alpha_search.objective_feedback.rebalance_every_closed_trades",
    "alpha_search.objective_feedback.quality_metric_weights.*",
    "alpha_search.objective_feedback.min_provider_weight",
    "alpha_search.objective_feedback.max_provider_weight",
}


# =============================================================================
# Strategy -> Allowlist mapping
# =============================================================================

STRATEGY_ALLOWLISTS: Dict[str, Set[str]] = {
    "aurora": AURORA_OVERRIDE_PATHS,
    "mean_reversion": MR_OVERRIDE_PATHS,
    "ensemble": ENSEMBLE_OVERRIDE_PATHS,
}


def _path_matches_pattern(path: str, pattern: str) -> bool:
    """Check if a dot-path matches a pattern with * wildcards."""
    return fnmatch.fnmatch(path, pattern)


def validate_overrides(
    strategy_type: str,
    overrides: Dict[str, Any],
) -> List[str]:
    """
    Validate override paths against strategy-type allowlist.

    Args:
        strategy_type: aurora | mean_reversion | ensemble
        overrides: dot-path -> value mapping

    Returns:
        List of disallowed (rejected) override paths. Empty = all valid.
    """
    allowlist = STRATEGY_ALLOWLISTS.get(strategy_type)
    if allowlist is None:
        return list(overrides.keys())  # unknown strategy -> reject all

    rejected = []
    for path in overrides.keys():
        matched = any(_path_matches_pattern(path, pattern)
                      for pattern in allowlist)
        if not matched:
            rejected.append(path)

    if rejected:
        LOG.warning(
            f"[{strategy_type}] Rejected override paths (not in allowlist): {rejected}"
        )

    return rejected


def warn_partial_aurora_overrides(overrides: Dict[str, Any]) -> List[str]:
    """
    Warn if aurora overrides are potentially inconsistent.

    Changing signal_threshold without matching feature_neutrals adjustment
    may produce suboptimal scoring. This is a soft warning, not a hard block.

    Returns list of warning messages.
    """
    warnings = []

    has_threshold = any("signal_threshold" in k for k in overrides)
    has_neutrals = any("feature_neutrals" in k for k in overrides)
    has_weights = any("signal_weights" in k for k in overrides)

    if has_threshold and not has_neutrals:
        warnings.append(
            "signal_threshold changed without feature_neutrals: "
            "scoring may be suboptimal (neutrals calibrated for original threshold)"
        )

    if has_weights and not has_neutrals:
        warnings.append(
            "signal_weights changed without feature_neutrals: "
            "neutrals may need recalibration for new weight distribution"
        )

    return warnings
