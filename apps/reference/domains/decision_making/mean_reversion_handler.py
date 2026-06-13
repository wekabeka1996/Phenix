"""Backward-compat shim for apps.reference.domains.decision_making.mean_reversion_handler.

Deprecation window: one release from 2026-04-24 Package 2.
"""

import warnings

warnings.warn(
    "apps.reference.domains.decision_making.mean_reversion_handler is moved to apps.reference.domains.strategies.runtimes.mean_reversion.handler",
    DeprecationWarning,
    stacklevel=2,
)

from apps.reference.domains.strategies.runtimes.mean_reversion.handler import (
    MeanReversionHandler,
)

__all__ = ["MeanReversionHandler"]
