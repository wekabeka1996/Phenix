"""Backward-compat shim for apps.reference.domains.decision_making.entry_plan.

Deprecation window: one release from 2026-04-24 Package 2.
"""

import warnings

warnings.warn(
    "apps.reference.domains.decision_making.entry_plan is moved to apps.reference.shared.decision_primitives.entry_plan",
    DeprecationWarning,
    stacklevel=2,
)

from apps.reference.shared.decision_primitives.entry_plan import *  # noqa: F401,F403
from apps.reference.shared.decision_primitives.entry_plan import EntryPlanResult  # noqa: F401
