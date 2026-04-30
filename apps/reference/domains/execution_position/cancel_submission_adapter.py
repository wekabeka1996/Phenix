"""Compatibility alias for Phase 8C guardian skeleton migration."""

from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(
    "apps.reference.domains.execution_position.guardian.cancel_submission_adapter"
)
