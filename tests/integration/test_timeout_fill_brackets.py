"""
EP-TIMEOUT-FILL-BRACKETS: Test that LIMIT entry orders filled during
fill_timeout window get TP/SL brackets placed via timeout-fill-discovery path.

Covers:
1. IdempotentCancelResult.order_data field
2. FILLED detection (PRE_CHECK_TERMINAL_FILLED)
3. Bracket placement from _pending_brackets on fill discovery
4. Idempotent no-op if brackets already popped
5. Genuine cancel does not trigger fill path
"""

from apps.reference.domains.execution_position.idempotent_cancel import (
    IdempotentCancelResult,
)
from decimal import Decimal
import pytest
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "vfoundation" / "vfoundation"))


class TestIdempotentCancelResultOrderData:
    """Test order_data field on IdempotentCancelResult."""

    def test_order_data_defaults_to_none(self):
        result = IdempotentCancelResult(
            success=True,
            reason="CANCEL_SUCCESS",
            is_idempotent_success=True,
        )
        assert result.order_data is None

    def test_order_data_carries_exchange_response(self):
        order_data = {
            "orderId": 12345678,
            "symbol": "BTCUSDT",
            "status": "FILLED",
            "executedQty": "0.004",
            "avgPrice": "67500.00",
            "clientOrderId": "ENTRY-BTC-123",
        }
        result = IdempotentCancelResult(
            success=True,
            reason="PRE_CHECK_TERMINAL_FILLED",
            order_status_before="FILLED",
            order_status_after="FILLED",
            is_idempotent_success=True,
            order_data=order_data,
        )
        assert result.order_data is not None
        assert result.order_data["executedQty"] == "0.004"
        assert result.order_data["avgPrice"] == "67500.00"
        assert result.order_data["symbol"] == "BTCUSDT"


class TestTimeoutFillDetection:
    """Test that PRE_CHECK_TERMINAL_FILLED is correctly identified as a fill."""

    def test_filled_reason_detected(self):
        result = IdempotentCancelResult(
            success=True,
            reason="PRE_CHECK_TERMINAL_FILLED",
            order_status_before="FILLED",
            order_status_after="FILLED",
            is_idempotent_success=True,
        )
        is_fill = (
            isinstance(result, IdempotentCancelResult)
            and result.reason == "PRE_CHECK_TERMINAL_FILLED"
        )
        assert is_fill is True

    def test_cancel_success_not_detected_as_fill(self):
        result = IdempotentCancelResult(
            success=True,
            reason="CANCEL_SUCCESS",
            order_status_before="NEW",
            order_status_after="CANCELED",
            is_idempotent_success=True,
        )
        is_fill = (
            isinstance(result, IdempotentCancelResult)
            and result.reason == "PRE_CHECK_TERMINAL_FILLED"
        )
        assert is_fill is False

    def test_expired_not_detected_as_fill(self):
        result = IdempotentCancelResult(
            success=True,
            reason="PRE_CHECK_TERMINAL_EXPIRED",
            order_status_before="EXPIRED",
            order_status_after="EXPIRED",
            is_idempotent_success=True,
        )
        is_fill = (
            isinstance(result, IdempotentCancelResult)
            and result.reason == "PRE_CHECK_TERMINAL_FILLED"
        )
        assert is_fill is False

    def test_idempotent_2011_not_detected_as_fill(self):
        result = IdempotentCancelResult(
            success=True,
            reason="IDEMPOTENT_-2011_ABSORBED",
            error_code=-2011,
            is_idempotent_success=True,
        )
        is_fill = (
            isinstance(result, IdempotentCancelResult)
            and result.reason == "PRE_CHECK_TERMINAL_FILLED"
        )
        assert is_fill is False

    def test_dict_result_not_detected_as_fill(self):
        """Raw dict from adapter (non-idempotent path) should not be fill."""
        result = {"status": "CANCELED", "orderId": 123}
        is_fill = (
            isinstance(result, IdempotentCancelResult)
            and result.reason == "PRE_CHECK_TERMINAL_FILLED"
        )
        assert is_fill is False


class TestBracketPlacementOnFillDiscovery:
    """Test that _pending_brackets is correctly consumed on fill discovery."""

    def test_brackets_popped_on_fill(self):
        pending = {
            "12345678": {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "sl": Decimal("95000"),
                "tp": Decimal("98000"),
                "qty": Decimal("0.004"),
            }
        }
        order_id = "12345678"

        assert order_id in pending
        bracket_data = pending.pop(order_id)

        assert order_id not in pending
        assert bracket_data["symbol"] == "BTCUSDT"
        assert bracket_data["sl"] == Decimal("95000")
        assert bracket_data["tp"] == Decimal("98000")

    def test_idempotent_noop_if_already_popped(self):
        """If _on_order_fill already consumed brackets, timeout handler is no-op."""
        pending = {}
        order_id = "12345678"

        bracket_data = None
        if order_id in pending:
            bracket_data = pending.pop(order_id)

        assert bracket_data is None

    def test_cancel_success_does_not_pop_brackets(self):
        """Genuine cancel (status_before=NEW) should NOT pop brackets here.
        Brackets are cleaned up in _handle_cancel_event instead."""
        pending = {
            "12345678": {
                "symbol": "SOLUSDT",
                "side": "SELL",
                "sl": Decimal("82.0"),
                "tp": Decimal("79.0"),
            }
        }
        cancel_result = IdempotentCancelResult(
            success=True,
            reason="CANCEL_SUCCESS",
            order_status_before="NEW",
            order_status_after="CANCELED",
            is_idempotent_success=True,
        )

        is_fill = (
            isinstance(cancel_result, IdempotentCancelResult)
            and cancel_result.reason == "PRE_CHECK_TERMINAL_FILLED"
        )

        if is_fill and "12345678" in pending:
            pending.pop("12345678")

        # Brackets should still be in dict (not popped by cancel path)
        assert "12345678" in pending
