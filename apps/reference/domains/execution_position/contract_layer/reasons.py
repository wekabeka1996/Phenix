"""Additive bridge to the existing execution_position reason-code SSOT."""

from apps.reference.domains.execution_position.reasons import (
    ALL_REASONS,
    BINANCE_POST_ONLY_REJECT_CODES,
    CANCEL_PANIC_KILL,
    CANCEL_STALE_REGIME,
    CANCEL_SUCCESS,
    CANCEL_SUPERSEDED,
    CANCEL_TTL_EXPIRED,
    CANCEL_UNKNOWN,
    CMD_OPEN_VALIDATION_FAIL,
    IDEMPOTENCY_FAIL,
    MAKER_ONLY_ENFORCEMENT_FAIL,
    MAKER_ONLY_REJECT,
    OPEN_GUARD_FAIL,
    PANIC_KILLSWITCH,
    is_maker_only_reject_error,
)

__all__ = [
    "ALL_REASONS",
    "BINANCE_POST_ONLY_REJECT_CODES",
    "CANCEL_PANIC_KILL",
    "CANCEL_STALE_REGIME",
    "CANCEL_SUCCESS",
    "CANCEL_SUPERSEDED",
    "CANCEL_TTL_EXPIRED",
    "CANCEL_UNKNOWN",
    "CMD_OPEN_VALIDATION_FAIL",
    "IDEMPOTENCY_FAIL",
    "MAKER_ONLY_ENFORCEMENT_FAIL",
    "MAKER_ONLY_REJECT",
    "OPEN_GUARD_FAIL",
    "PANIC_KILLSWITCH",
    "is_maker_only_reject_error",
]
