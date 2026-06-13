"""Backward-compat shim for apps.reference.domains.decision_making.normalized_reject_reasons.

Deprecation window: one release from 2026-04-24 Package 2.
"""

import warnings

warnings.warn(
    "apps.reference.domains.decision_making.normalized_reject_reasons is moved to apps.reference.domains.decision_making.contracts.normalized_reject_reasons",
    DeprecationWarning,
    stacklevel=2,
)

from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import (
    NormalizedRejectReasons,
    build_trade_intent_rejected_message,
    normalize_trade_intent_rejected_payload,
    resolve_trade_intent_rejected_rid,
    stringify_trade_intent_rejected_value,
)

__all__ = [
    "NormalizedRejectReasons",
    "build_trade_intent_rejected_message",
    "normalize_trade_intent_rejected_payload",
    "resolve_trade_intent_rejected_rid",
    "stringify_trade_intent_rejected_value",
]
