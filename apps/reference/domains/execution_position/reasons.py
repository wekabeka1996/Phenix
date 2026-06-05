"""
EP-01.4-INT-B: Centralized SSOT for reason codes.

This module provides canonical reason constants for order cancellation,
rejection, and other lifecycle events. Use these constants instead of
inline strings to ensure telemetry/logging consistency.

USAGE:
    from apps.reference.domains.execution_position.reasons import (
        MAKER_ONLY_REJECT,
        CANCEL_TTL_EXPIRED,
        ...
    )
"""

from typing import Literal


# =============================================================================
# ENTRY / PLACEMENT REASONS
# =============================================================================

MAKER_ONLY_REJECT: Literal["MAKER_ONLY_REJECT"] = "MAKER_ONLY_REJECT"
"""
GTX (post-only) order rejected because it would cross the book.
Either via:
- Placement reject (Binance -5022 or similar)
- WS path: status=EXPIRED with executedQty=0 for GTX order
NO FALLBACK to market. Entry is aborted.
"""


# =============================================================================
# CANCEL REASONS
# =============================================================================

CANCEL_TTL_EXPIRED: Literal["CANCEL_TTL_EXPIRED"] = "CANCEL_TTL_EXPIRED"
"""
Pending entry order cancelled because fill TTL expired.
Order was not filled within valid_for_ms or global fill_ttl_ms.
"""

CANCEL_SUPERSEDED: Literal["CANCEL_SUPERSEDED"] = "CANCEL_SUPERSEDED"
"""
Pending entry order cancelled because a new signal superseded it.
Old order is cancelled, new order is queued.
"""

CANCEL_STALE_REGIME: Literal["CANCEL_STALE_REGIME"] = "CANCEL_STALE_REGIME"
"""
Pending entry order cancelled due to regime change.
Market regime shifted (e.g., FLAT -> TREND) invalidating entry.
"""

CANCEL_PANIC_KILL: Literal["CANCEL_PANIC_KILL"] = "CANCEL_PANIC_KILL"
"""
All pending entries cancelled due to panic killswitch activation.
System-wide emergency stop.
"""

CANCEL_SUCCESS: Literal["CANCEL_SUCCESS"] = "CANCEL_SUCCESS"
"""
Order/position successfully cancelled by user request or system logic.
"""

CANCEL_UNKNOWN: Literal["CANCEL_UNKNOWN"] = "CANCEL_UNKNOWN"
"""
Order cancelled for unknown/unclassified reason.
Used as fallback when specific reason cannot be determined.
"""


# =============================================================================
# VALIDATION / GUARD REASONS
# =============================================================================

CMD_OPEN_VALIDATION_FAIL: Literal["CMD_OPEN_VALIDATION_FAIL"] = "CMD_OPEN_VALIDATION_FAIL"
"""
CMD:OPEN payload failed strict Pydantic validation.
"""

PANIC_KILLSWITCH: Literal["PANIC_KILLSWITCH"] = "PANIC_KILLSWITCH"
"""
CMD:OPEN blocked because panic_killswitch is active.
"""

IDEMPOTENCY_FAIL: Literal["IDEMPOTENCY_FAIL"] = "IDEMPOTENCY_FAIL"
"""
Duplicate CMD:OPEN rejected by idempotency check.
"""

OPEN_GUARD_FAIL: Literal["OPEN_GUARD_FAIL"] = "OPEN_GUARD_FAIL"
"""
CMD:OPEN rejected by execution guards (qty, price, notional, etc.)
"""

MAKER_ONLY_ENFORCEMENT_FAIL: Literal["MAKER_ONLY_ENFORCEMENT_FAIL"] = "MAKER_ONLY_ENFORCEMENT_FAIL"
"""
CMD:OPEN for LIMIT entry rejected because maker_only is enabled
but tif was not GTX (fail-closed policy).
"""


# =============================================================================
# BINANCE ERROR CODE MAPPING
# =============================================================================

# Binance Futures error codes related to post-only / maker-only
BINANCE_POST_ONLY_REJECT_CODES = {
    -5022,  # "Post Only order will be rejected"
    -1131,  # "Order would immediately cross" (older code)
}

def is_maker_only_reject_error(error_code: int) -> bool:
    """Check if Binance error code indicates post-only rejection."""
    return error_code in BINANCE_POST_ONLY_REJECT_CODES


# =============================================================================
# ALL REASONS (for validation/autocomplete)
# =============================================================================

ALL_REASONS = [
    MAKER_ONLY_REJECT,
    CANCEL_TTL_EXPIRED,
    CANCEL_SUPERSEDED,
    CANCEL_STALE_REGIME,
    CANCEL_PANIC_KILL,
    CANCEL_SUCCESS,
    CANCEL_UNKNOWN,
    CMD_OPEN_VALIDATION_FAIL,
    PANIC_KILLSWITCH,
    IDEMPOTENCY_FAIL,
    OPEN_GUARD_FAIL,
    MAKER_ONLY_ENFORCEMENT_FAIL,
]
