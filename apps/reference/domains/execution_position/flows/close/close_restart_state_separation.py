"""Phase 9.3: Exact vs UNKNOWN separation for restart state.

This module proves that we can clearly separate EXACT state (from
restore envelope or order_log) from UNKNOWN state (post-close fills,
bracket outcomes, tidy state).

Goal:
On simulated restart, explicitly mark what we KNOW vs what we DON'T know,
with no guessing or silent assumptions about post-close state.

Invariant:
- EXACT: Anything from restore envelope or order_log
- UNKNOWN: Post-close position, fills, bracket outcomes, tidy state
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, Set


class StateConfidence(str, Enum):
    """Confidence level for a state value."""
    EXACT = "EXACT"
    UNKNOWN = "UNKNOWN"


class RestartStateEntry:
    """Represents a single piece of state with confidence level."""

    def __init__(self, key: str, value: Any, confidence: StateConfidence):
        self.key = key
        self.value = value
        self.confidence = confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            'key': self.key,
            'value': self.value,
            'confidence': self.confidence.value,
        }


class RestartStateMap:
    """Container for restart state with explicit confidence separation."""

    def __init__(self):
        self.exact_state: Dict[str, Any] = {}
        self.unknown_state: Set[str] = set()
        self.entries: list[RestartStateEntry] = []

    def add_exact(self, key: str, value: Any) -> None:
        """Add an EXACT state value (from restore envelope or order_log)."""
        self.exact_state[key] = value
        self.entries.append(RestartStateEntry(
            key, value, StateConfidence.EXACT))

    def add_unknown(self, key: str, reason: str = "") -> None:
        """Mark a state value as UNKNOWN (do not guess)."""
        self.unknown_state.add(key)
        self.entries.append(RestartStateEntry(
            key, f"UNKNOWN({reason})", StateConfidence.UNKNOWN))

    def verify_no_guessing(self) -> tuple[bool, Optional[str]]:
        """Verify that no post-close state is present in exact_state."""
        post_close_keys = {
            'fills_count',
            'position_after_close',
            'bracket_outcomes',
            'tidy_state',
            'filled_amount',
        }

        for key in post_close_keys:
            if key in self.exact_state:
                return False, f"Guessed post-close state: {key}"

        return True, None

    def get_verdict(self) -> str:
        """Return verdict on state separation."""
        is_clean, reason = self.verify_no_guessing()
        if not is_clean:
            return f"CONTAMINATED: {reason}"

        if len(self.unknown_state) == 0:
            return "INCOMPLETE_SEPARATION"  # No UNKNOWN marked

        if len(self.exact_state) == 0:
            return "NO_EXACT_STATE"  # No EXACT state

        return "VERIFIED_SEPARATION"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'exact_count': len(self.exact_state),
            'unknown_count': len(self.unknown_state),
            'exact_state': self.exact_state,
            'unknown_keys': list(self.unknown_state),
            'verdict': self.get_verdict(),
            'entries': [e.to_dict() for e in self.entries],
        }


def build_restart_state_from_restore_envelope_and_order_log(
    restore_envelope: Dict[str, Any],
    order_log_entry: Dict[str, Any],
) -> RestartStateMap:
    """Build restart state from restore envelope and order_log.

    EXACT state comes from:
    - restore_envelope: original position amount, symbol
    - order_log: what was actually submitted (side, quantity, client_order_id)

    UNKNOWN state includes anything that happened post-close:
    - filled_amount (did the order fill? How much?)
    - remaining_position (how many did we close? how many still open?)
    - bracket_outcomes (were brackets filled?)
    - tidy_state (was manual close logic executed?)
    """
    state = RestartStateMap()

    # From restore envelope (EXACT)
    if 'position_amount' in restore_envelope:
        state.add_exact('position_amount_at_close_request',
                        restore_envelope['position_amount'])

    if 'symbol' in restore_envelope:
        state.add_exact('symbol', restore_envelope['symbol'])

    # From order_log (EXACT)
    if 'side' in order_log_entry:
        state.add_exact('submitted_side', order_log_entry['side'])

    if 'quantity' in order_log_entry:
        state.add_exact('submitted_quantity', order_log_entry['quantity'])

    if 'client_order_id' in order_log_entry:
        state.add_exact('client_order_id', order_log_entry['client_order_id'])

    if 'partial_close' in order_log_entry:
        state.add_exact('was_partial_close', order_log_entry['partial_close'])

    # Post-close state (UNKNOWN - no guessing!)
    state.add_unknown('filled_amount', 'ORDER_FILL_RESULT_NOT_REPLAYED')
    state.add_unknown('position_after_close', 'DEPENDENT_ON_FILLED_AMOUNT')
    state.add_unknown('bracket_outcomes', 'DEPENDENT_ON_CLOSE_SUCCESS')
    state.add_unknown('tidy_state', 'DEPENDENT_ON_POSITION_AND_BRACKETS')

    return state
