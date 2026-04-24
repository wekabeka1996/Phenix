"""Backward-compat shim for apps.reference.domains.decision_making.quadratic_scoring_kernel.

Deprecation window: one release from 2026-04-24 Package 2.
"""

import warnings

warnings.warn(
    "apps.reference.domains.decision_making.quadratic_scoring_kernel is moved to apps.reference.shared.decision_primitives.scoring_kernel",
    DeprecationWarning,
    stacklevel=2,
)

from apps.reference.shared.decision_primitives.scoring_kernel import *  # noqa: F401,F403
from apps.reference.shared.decision_primitives.scoring_kernel import QuadraticScoringKernel  # noqa: F401
