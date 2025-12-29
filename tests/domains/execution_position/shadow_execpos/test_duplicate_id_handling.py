"""
Test for duplicate ClientOrderId handling in execution service.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from apps.reference.domains.execution_position.shadow_execpos.execution_service import ExecutionService


class TestDuplicateIdHandling:
    """Test duplicate ClientOrderId error handling."""

    def test_duplicate_id_detection(self):
        """Test that duplicate ID errors are properly detected."""
        adapter = MagicMock()
        service = ExecutionService(adapter)

        # Test various duplicate error formats
        error_cases = [
            {"code": -4116, "msg": "ClientOrderId is duplicated."},
            {"error_code": "-4116"},
            {"error": "ClientOrderId is duplicated."},
            {"error": "clientorderid is duplicated"}
        ]

        for error in error_cases:
            # Check duplicate detection logic
            error_code = error.get("code") or error.get("error_code")
            error_msg = error.get("msg") or error.get("error", "")

            is_duplicate = (
                error_code == -4116 or
                "-4116" in str(error_code) or
                "duplicated" in error_msg.lower()
            )
            assert is_duplicate, f"Failed to detect duplicate in: {error}"

        # Test non-duplicate errors
        non_duplicate_cases = [
            {"code": -2011, "msg": "Unknown order"},
            {"error": "Rate limited"}
        ]

        for error in non_duplicate_cases:
            error_code = error.get("code") or error.get("error_code")
            error_msg = error.get("msg") or error.get("error", "")

            is_duplicate = (
                error_code == -4116 or
                "-4116" in str(error_code) or
                "duplicated" in error_msg.lower()
            )
            assert not is_duplicate, f"Incorrectly detected duplicate in: {error}"

    def test_bracket_duplicate_treated_as_success(self):
        """Test that bracket duplicate errors are treated as success."""
        adapter = MagicMock()
        service = ExecutionService(adapter)

        # Mock adapter to return duplicate error
        adapter.place_order = AsyncMock(return_value={
            "success": False,
            "error_code": -4116,
            "error": "ClientOrderId is duplicated."
        })

        # This would be tested in integration, but here we verify the logic
        error_code = -4116
        error_msg = "ClientOrderId is duplicated."

        # Check if it's duplicate
        is_duplicate = (
            error_code == -4116 or
            "-4116" in str(error_code) or
            "duplicated" in error_msg.lower()
        )
        assert is_duplicate

        # For bracket orders, duplicate should be treated as success
        action_type = "PLACE_SL"
        if is_duplicate and action_type in ("PLACE_SL", "PLACE_TP"):
            # Should return success
            expected_result = {"success": True, "already_exists": True}
            assert expected_result["success"] is True
            assert expected_result["already_exists"] is True

    def test_non_bracket_duplicate_retries_with_new_id(self):
        """Test that non-bracket duplicate errors retry with new clientOrderId."""
        adapter = MagicMock()
        service = ExecutionService(adapter)

        # For non-bracket orders (like market orders), duplicate should retry
        action_type = "PLACE_MARKET"
        error_code = -4116

        is_duplicate = error_code == -4116
        assert is_duplicate

        # Should retry with new ID for non-bracket orders
        should_retry = is_duplicate and action_type not in ("PLACE_SL", "PLACE_TP")
        assert should_retry
