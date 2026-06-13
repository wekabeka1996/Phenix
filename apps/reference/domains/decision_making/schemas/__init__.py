"""Backward-compat shim for apps.reference.domains.decision_making.schemas.

Deprecation window: one release from 2026-04-24 Package 2.
"""

import warnings

warnings.warn(
    "apps.reference.domains.decision_making.schemas is moved to apps.reference.domains.decision_making.contracts.schemas",
    DeprecationWarning,
    stacklevel=2,
)

from apps.reference.domains.decision_making.contracts.schemas import (
    PortfolioStatePayload,
    PositionData,
)
from apps.reference.domains.decision_making.schemas.control_decision import (  # noqa: F401
    ControlDecisionAction,
    ControlDecisionRequest,
    ControlDecisionResponse,
)

__all__ = [
    "ControlDecisionAction",
    "ControlDecisionRequest",
    "ControlDecisionResponse",
    "PortfolioStatePayload",
    "PositionData",
]
