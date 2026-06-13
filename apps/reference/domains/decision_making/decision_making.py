"""Backward-compat shim for apps.reference.domains.decision_making.decision_making.

Deprecation window: one release from 2026-04-24 Package 2.

The active DecisionMaking implementation now lives in core.facade and uses
self._clock for time operations.
"""

import warnings

warnings.warn(
    "apps.reference.domains.decision_making.decision_making is moved to apps.reference.domains.decision_making.core.facade",
    DeprecationWarning,
    stacklevel=2,
)

from apps.reference.domains.decision_making.core.facade import DecisionMaking

__all__ = ["DecisionMaking"]
