from __future__ import annotations

import logging
import warnings
from typing import Callable

from apps.reference.telemetry.metrics import inc_retry_scheduler_no_loop
from vfoundation.core import FSMCore
from vfoundation.core.fsm_emit_compat import emit_compat
from vfoundation.core.retry_scheduler import RetryScheduler as _VFoundationRetryScheduler

warnings.warn(
    "apps.reference.retry_scheduler is deprecated; use vfoundation.core.retry_scheduler",
    DeprecationWarning,
    stacklevel=2,
)


class RetryScheduler(_VFoundationRetryScheduler):
    """Compatibility wrapper that injects app-level telemetry callback by default."""

    def __init__(
        self,
        fsm: FSMCore,
        logger: logging.Logger | None = None,
        default_max_attempts: int = 5,
        min_retry_delay_ms: int = 500,
        backoff_factor: float = 2.0,
        jitter_ms: int = 0,
        on_no_loop: Callable[[], None] | None = None,
    ):
        super().__init__(
            fsm=fsm,
            logger=logger,
            default_max_attempts=default_max_attempts,
            min_retry_delay_ms=min_retry_delay_ms,
            backoff_factor=backoff_factor,
            jitter_ms=jitter_ms,
            on_no_loop=on_no_loop or inc_retry_scheduler_no_loop,
        )


__all__ = ["RetryScheduler", "emit_compat"]
