"""
Tests for Normalized Reject Reasons (NRR) module.
"""

import pytest
from apps.reference.domains.decision_making.normalized_reject_reasons import (
    NormalizedRejectReasons,
)


class TestNormalizedRejectReasons:
    """Test cases for NRR normalization."""

    def test_normalize_insufficient_balance(self):
        """Test normalization of insufficient balance errors."""
        test_cases = [
            "Account has insufficient balance",
            "insufficient balance for order",
            "not enough funds in account",
            "balance not sufficient",
        ]

        for raw_reason in test_cases:
            result = NormalizedRejectReasons.normalize(raw_reason)
            assert result == NormalizedRejectReasons.INSUFFICIENT_BALANCE

    def test_normalize_invalid_order_params(self):
        """Test normalization of invalid order parameter errors."""
        test_cases = [
            "Invalid order parameters",
            "order params are invalid",
            "bad request: invalid order",
        ]

        for raw_reason in test_cases:
            result = NormalizedRejectReasons.normalize(raw_reason)
            assert result == NormalizedRejectReasons.INVALID_ORDER_PARAMS

    def test_normalize_market_closed(self):
        """Test normalization of market closed errors."""
        test_cases = [
            "Market is closed",
            "trading suspended",
            "market not open for trading",
        ]

        for raw_reason in test_cases:
            result = NormalizedRejectReasons.normalize(raw_reason)
            assert result == NormalizedRejectReasons.MARKET_CLOSED

    def test_normalize_exposure_limit_exceeded(self):
        """Test normalization of exposure limit errors."""
        test_cases = [
            "exposure limit exceeded",
            "risk limit exceeded",
            "exposure exceeded maximum",
            "Trading not allowed by risk manager",
            "risk score too high",
        ]

        for raw_reason in test_cases:
            result = NormalizedRejectReasons.normalize(raw_reason)
            assert result == NormalizedRejectReasons.EXPOSURE_LIMIT_EXCEEDED

    def test_normalize_rate_limit_exceeded(self):
        """Test normalization of rate limit errors."""
        test_cases = [
            "rate limit exceeded",
            "too many requests",
            "request rate exceeded",
        ]

        for raw_reason in test_cases:
            result = NormalizedRejectReasons.normalize(raw_reason)
            assert result == NormalizedRejectReasons.RATE_LIMIT_EXCEEDED

    def test_normalize_unknown_error(self):
        """Test that unknown errors map to UNKNOWN_ERROR."""
        test_cases = ["some random error", "",
                      None, "completely unexpected message"]

        for raw_reason in test_cases:
            result = NormalizedRejectReasons.normalize(raw_reason)
            assert result == NormalizedRejectReasons.UNKNOWN_ERROR

    def test_get_description(self):
        """Test getting descriptions for NRR codes."""
        desc = NormalizedRejectReasons.get_description(
            NormalizedRejectReasons.INSUFFICIENT_BALANCE
        )
        assert desc == "Account has insufficient balance for the operation"

        desc = NormalizedRejectReasons.get_description(
            NormalizedRejectReasons.UNKNOWN_ERROR
        )
        assert desc == "Unknown or unmapped error condition"

        desc = NormalizedRejectReasons.get_description("INVALID_CODE")
        assert desc is None
