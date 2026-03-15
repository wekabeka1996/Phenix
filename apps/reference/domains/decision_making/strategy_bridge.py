"""
Strategy Bridge — Decision Making re-export facade.

FE-DM-BOUNDARY-STABILIZATION (2026-03-15):

These strategy modules live in feature_engineering for historical reasons
but are semantically owned by decision_making. This facade provides
the sanctioned DM-facing import path.

DM production code MUST import strategy artifacts through this bridge,
NOT directly from apps.reference.domains.feature_engineering submodules.

Test code may still import directly from FE during the transition period.
A future migration package will physically move the files to DM and
convert this bridge into a backward-compatibility shim.

Canonical imports:
    from apps.reference.domains.decision_making.strategy_bridge import (
        MeanReversion1mStrategy, MRSignal, MRSignalType, MRStrategyConfig,
        MDAMRStrategyV11, MDAMRSignal,
        FlatRegime, FlatRegimeThresholds, map_to_flat_regime,
        is_flat_regime, get_mr_parameters, MRParameters,
    )
"""

# ── Mean Reversion Strategy ────────────────────────────────────────────
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MeanReversion1mStrategy,
    MRSignal,
    MRSignalType,
    MRStrategyConfig,
    MRSymbolState,
    SqueezeExpansionVetoConfig,
    MomentumSeparationVetoConfig,
)

# ── MD-AMR Strategy ────────────────────────────────────────────────────
from apps.reference.domains.feature_engineering.md_amr_strategy import (
    MDAMRStrategyV11,
    MDAMRSignal,
)

# ── Regime Mapping (MR parameters) ─────────────────────────────────────
from apps.reference.domains.feature_engineering.regime_mapping import (
    FlatRegime,
    FlatRegimeThresholds,
    map_to_flat_regime,
    is_flat_regime,
    get_mr_parameters,
    MRParameters,
)

__all__ = [
    # MR Strategy
    "MeanReversion1mStrategy",
    "MRSignal",
    "MRSignalType",
    "MRStrategyConfig",
    "MRSymbolState",
    "SqueezeExpansionVetoConfig",
    "MomentumSeparationVetoConfig",
    # MD-AMR Strategy
    "MDAMRStrategyV11",
    "MDAMRSignal",
    # Regime Mapping
    "FlatRegime",
    "FlatRegimeThresholds",
    "map_to_flat_regime",
    "is_flat_regime",
    "get_mr_parameters",
    "MRParameters",
]
