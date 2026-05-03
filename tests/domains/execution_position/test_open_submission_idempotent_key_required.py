"""
Phase 2 — Ingress and Config Fail-Closed

Tests for DEF-E10: Idempotency key must be present before adapter call.
No fallback to timestamp-based client_order_id.
"""
from __future__ import annotations

import pytest

from apps.reference.domains.execution_position.flows.open.open_submission_adapter import (
    OpenSubmissionAdapterError,
    OpenSubmissionPayload,
)


def _market_payload():
    return {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "MARKET",
        "price": None,
        "tif": None,
    }


def _limit_payload():
    return {
        "symbol": "ETHUSDT",
        "side": "SELL",
        "order_type": "LIMIT",
        "price": "3000.00",
        "tif": "GTC",
    }


class TestOpenSubmissionIdempotentKeyRequired:
    """DEF-E10: Missing idempotent_key must fail before any adapter call."""

    def test_valid_key_produces_submission(self):
        """Baseline: providing a valid idempotent_key succeeds."""
        result = OpenSubmissionPayload.from_dec_open_with_key(
            payload=_market_payload(),
            normalized_qty="0.01",
            idempotent_key="abc-123-stable-key",
        )
        assert result.symbol == "BTCUSDT"
        assert result.client_order_id  # must be non-empty

    def test_none_key_raises_before_adapter_call(self):
        """DEF-E10 regression: None idempotent_key must raise, not use timestamp fallback."""
        with pytest.raises(OpenSubmissionAdapterError, match="idempotent_key is required"):
            OpenSubmissionPayload.from_dec_open_with_key(
                payload=_market_payload(),
                normalized_qty="0.01",
                idempotent_key=None,
            )

    def test_empty_string_key_raises_before_adapter_call(self):
        """Empty string idempotent_key must also be rejected (falsy = not a key)."""
        with pytest.raises(OpenSubmissionAdapterError):
            OpenSubmissionPayload.from_dec_open_with_key(
                payload=_market_payload(),
                normalized_qty="0.01",
                idempotent_key="",
            )

    def test_same_key_produces_same_client_order_id(self):
        """Stable idempotent_key must deterministically produce same client_order_id."""
        key = "stable-idem-key-v1"
        result1 = OpenSubmissionPayload.from_dec_open_with_key(
            payload=_market_payload(),
            normalized_qty="0.01",
            idempotent_key=key,
        )
        result2 = OpenSubmissionPayload.from_dec_open_with_key(
            payload=_market_payload(),
            normalized_qty="0.01",
            idempotent_key=key,
        )
        assert result1.client_order_id == result2.client_order_id, (
            "Same idempotent_key must produce same client_order_id for idempotency."
        )

    def test_different_keys_produce_different_client_order_ids(self):
        """Different idempotent keys must produce different client_order_ids."""
        result1 = OpenSubmissionPayload.from_dec_open_with_key(
            payload=_market_payload(),
            normalized_qty="0.01",
            idempotent_key="key-alpha",
        )
        result2 = OpenSubmissionPayload.from_dec_open_with_key(
            payload=_market_payload(),
            normalized_qty="0.01",
            idempotent_key="key-beta",
        )
        assert result1.client_order_id != result2.client_order_id

    def test_limit_order_with_valid_key_succeeds(self):
        """LIMIT order with valid idempotent_key must succeed."""
        result = OpenSubmissionPayload.from_dec_open_with_key(
            payload=_limit_payload(),
            normalized_qty="1.5",
            idempotent_key="limit-order-key-001",
        )
        assert result.order_type == "LIMIT"
        assert result.price == "3000.00"
        assert result.time_in_force == "GTC"
