"""
TA Features Domain.

Isolated bar-based technical indicator computation engine.

Exposes:
  TAFeaturesEngine — subscribe to EVT:BAR_CLOSED, emit EVT:TA_FEATURES_CALCULATED.
"""

from apps.reference.domains.ta_features.ta_features import TAFeaturesEngine

__all__ = ["TAFeaturesEngine"]
