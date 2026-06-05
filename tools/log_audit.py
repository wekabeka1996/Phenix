"""Backward-compatible shim for log audit tooling."""

from tools.diagnostics import log_audit as _impl
from tools.diagnostics.log_audit import *  # noqa: F401,F403

__all__ = getattr(_impl, "__all__", [])
