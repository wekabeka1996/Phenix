"""
Canonical shared types for cross-domain use.

Re-exports types that are referenced by 2+ domains, providing a single
import path that does not create direct domain→domain coupling.

**Bar** — OHLCV bar (used by market_data, feature_engineering, decision_making)
**NormalizedRejectReasons** — NRR codes (used by decision_making, execution_position)

Convention:
    - New shared types MUST be added here (not ad-hoc cross-domain imports).
    - Original definitions stay in their home domain (SSOT).
    - This module is a re-export facade, NOT a code owner.
"""
from __future__ import annotations

# ── Bar (OHLCV) ─────────────────────────────────────────────────────
# Home: feature_engineering/bar_resampler.py
# Consumers: market_data, decision_making, strategies
from apps.reference.domains.feature_engineering.bar_resampler import Bar

# ── NormalizedRejectReasons ──────────────────────────────────────────
# Home: decision_making/normalized_reject_reasons.py
# Consumers: execution_position
from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import (
    NormalizedRejectReasons,
    TRADE_INTENT_REJECTED_CANONICAL_KEYS,
    build_trade_intent_rejected_message,
    normalize_trade_intent_rejected_payload,
    stringify_trade_intent_rejected_value,
)

__all__ = [
    "Bar",
    "NormalizedRejectReasons",
    "TRADE_INTENT_REJECTED_CANONICAL_KEYS",
    "build_trade_intent_rejected_message",
    "normalize_trade_intent_rejected_payload",
    "stringify_trade_intent_rejected_value",
]
