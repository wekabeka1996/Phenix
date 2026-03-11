from __future__ import annotations

from typing import Dict, Tuple

from ._common import require_param


def evaluate_behavior(
    *,
    recent_cancel_replace_count: int,
    recent_blocked_intent_count: int,
    recent_reentry_count: int,
    params: Dict[str, float],
) -> Tuple[float, Dict[str, float]]:
    if recent_cancel_replace_count < 0 or recent_blocked_intent_count < 0 or recent_reentry_count < 0:
        raise ValueError("behavior inputs must be >= 0")

    phi_cancel_replace = require_param(params, "phi_cancel_replace")
    phi_blocked_intents = require_param(params, "phi_blocked_intents")
    phi_reentry = require_param(params, "phi_reentry")

    cancel_penalty = -(recent_cancel_replace_count * phi_cancel_replace)
    blocked_penalty = -(recent_blocked_intent_count * phi_blocked_intents)
    reentry_penalty = -(recent_reentry_count * phi_reentry)
    total = cancel_penalty + blocked_penalty + reentry_penalty
    return total, {
        "cancel_replace_penalty": cancel_penalty,
        "blocked_intent_penalty": blocked_penalty,
        "reentry_penalty": reentry_penalty,
    }
