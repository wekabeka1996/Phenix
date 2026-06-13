"""Backward-compat shim for apps.reference.domains.decision_making.aurora_handler.

Deprecation window: one release from 2026-04-24 Package 2.
"""

import warnings

warnings.warn(
    "apps.reference.domains.decision_making.aurora_handler is moved to apps.reference.domains.strategies.runtimes.aurora.handler",
    DeprecationWarning,
    stacklevel=2,
)

from apps.reference.domains.strategies.runtimes.aurora.handler import (
    AuroraHandler,
    SymbolState,
)

__all__ = ["AuroraHandler", "SymbolState"]
