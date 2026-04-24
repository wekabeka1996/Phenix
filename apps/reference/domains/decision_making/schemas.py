"""Backward-compat shim for apps.reference.domains.decision_making.schemas.

Deprecation window: one release from 2026-04-24 Package 2.
"""

import warnings

warnings.warn(
    "apps.reference.domains.decision_making.schemas is moved to apps.reference.domains.decision_making.contracts.schemas",
    DeprecationWarning,
    stacklevel=2,
)

from apps.reference.domains.decision_making.contracts.schemas import *  # noqa: F401,F403
from apps.reference.domains.decision_making.contracts.schemas import PortfolioStatePayload  # noqa: F401
