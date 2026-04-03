"""Sanctioned DecisionMaking-facing facade for FE-hosted strategy artifacts.

The strategy cores below still live under feature_engineering for historical
reasons, but current DecisionMaking contracts treat this module as the only
approved production import surface. Keeping the boundary explicit here lets
guardrail tests detect accidental direct FE imports from the rest of the DM
package while the physical file move is still pending.
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

# Keep the public bridge surface explicit so boundary tests can detect drift.
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
