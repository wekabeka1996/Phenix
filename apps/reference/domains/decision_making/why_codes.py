"""Backward-compat shim for apps.reference.domains.decision_making.why_codes.

Deprecation window: one release from 2026-04-24 Package 2.
"""

import warnings

warnings.warn(
    "apps.reference.domains.decision_making.why_codes is moved to apps.reference.domains.decision_making.contracts.why_codes",
    DeprecationWarning,
    stacklevel=2,
)

from apps.reference.domains.decision_making.contracts.why_codes import *  # noqa: F401,F403
from apps.reference.domains.decision_making.contracts.why_codes import WhyCode  # noqa: F401
