"""Backward-compatible shim for metrics summary tooling."""

from tools.monitoring import metrics_summary as _impl
from tools.monitoring.metrics_summary import *  # noqa: F401,F403

_mget = _impl._mget
