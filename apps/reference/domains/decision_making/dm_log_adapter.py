"""Backward-compat shim for apps.reference.domains.decision_making.dm_log_adapter.

Deprecation window: one release from 2026-04-24 Package 2.
"""

import warnings

warnings.warn(
    "apps.reference.domains.decision_making.dm_log_adapter is moved to apps.reference.domains.decision_making.observability.log_adapter",
    DeprecationWarning,
    stacklevel=2,
)

from apps.reference.domains.decision_making.observability.log_adapter import *  # noqa: F401,F403
from apps.reference.domains.decision_making.observability.log_adapter import DecisionLog  # noqa: F401
