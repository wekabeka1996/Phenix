"""Backward-compat shim for apps.reference.domains.decision_making.normalized_reject_reasons.

Deprecation window: one release from 2026-04-24 Package 2.
"""

import warnings

warnings.warn(
    "apps.reference.domains.decision_making.normalized_reject_reasons is moved to apps.reference.domains.decision_making.contracts.normalized_reject_reasons",
    DeprecationWarning,
    stacklevel=2,
)

from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import *  # noqa: F401,F403
from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons  # noqa: F401
