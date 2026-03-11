"""
Production-shadow gate evaluation contracts for neocortex.
"""

from .shadow import (
    ShadowGateEvaluator,
    ShadowGateResult,
    ShadowGateViolationError,
    ShadowReadinessReport,
)

__all__ = [
    "ShadowGateEvaluator",
    "ShadowGateResult",
    "ShadowGateViolationError",
    "ShadowReadinessReport",
]
