"""Backward-compat shim for apps.reference.domains.decision_making.md_amr_handler.

Deprecation window: one release from 2026-04-24 Package 2.
"""

import warnings

warnings.warn(
    "apps.reference.domains.decision_making.md_amr_handler is moved to apps.reference.domains.strategies.runtimes.md_amr.handler",
    DeprecationWarning,
    stacklevel=2,
)

from apps.reference.domains.strategies.runtimes.md_amr.handler import *  # noqa: F401,F403
from apps.reference.domains.strategies.runtimes.md_amr.handler import MDAMRHandler  # noqa: F401
