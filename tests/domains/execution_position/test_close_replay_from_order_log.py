"""Phase 9.2 validation: Reconstruction from order log."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.reference.domains.execution_position.flows.close.close_replay_from_order_log import (
    OrderLogEntry,
    reconstruct_close_submission_from_order_log,
    reconstruct_partial_close_flag_from_side_and_position,
)


class TestOrderLogReconstruction:
    """Prove that CloseSubmissionPayload can be reconstructed from order_log."""

    def test_reconstruct_full_close_long(self) -> None:
        """Reconstruct full close for long position."""
        entry = OrderLogEntry(
            rid="RID-FULL-LONG",
            symbol="BTCUSDT",
            idempotent_key="idem-full-long",
            client_order_id="order-1",
            side="SELL",  # Closing long position
            quantity="2.0",
            partial_close=False,
            source_fsm="close_executor",
        )
        position_amt = Decimal("2.0")

        payload, error = reconstruct_close_submission_from_order_log(
            entry, position_amt)

        assert error is None
        assert payload is not None
        assert payload.symbol == "BTCUSDT"
        assert payload.side == "SELL"
        assert payload.quantity == "2.0"
        assert payload.client_order_id == "order-1"
        assert payload.partial_close is False

    def test_reconstruct_full_close_short(self) -> None:
        """Reconstruct full close for short position."""
        entry = OrderLogEntry(
            rid="RID-FULL-SHORT",
            symbol="ETHUSDT",
            idempotent_key="idem-full-short",
            client_order_id="order-2",
            side="BUY",  # Closing short position
            quantity="5.0",
            partial_close=False,
            source_fsm="close_executor",
        )
        position_amt = Decimal("-5.0")

        payload, error = reconstruct_close_submission_from_order_log(
            entry, position_amt)

        assert error is None
        assert payload is not None
        assert payload.symbol == "ETHUSDT"
        assert payload.side == "BUY"
        assert payload.quantity == "5.0"
        assert payload.partial_close is False

    def test_reconstruct_partial_close_long(self) -> None:
        """Reconstruct partial close for long position."""
        entry = OrderLogEntry(
            rid="RID-PARTIAL-LONG",
            symbol="SOLUSDT",
            idempotent_key="idem-partial-long",
            client_order_id="order-3",
            side="SELL",
            quantity="2.5",  # Partial
            partial_close=True,
            source_fsm="close_executor",
        )
        position_amt = Decimal("5.0")  # Still holding 2.5 after this

        payload, error = reconstruct_close_submission_from_order_log(
            entry, position_amt)

        assert error is None
        assert payload is not None
        assert payload.quantity == "2.5"
        assert payload.partial_close is True

    def test_reconstruct_partial_close_short(self) -> None:
        """Reconstruct partial close for short position."""
        entry = OrderLogEntry(
            rid="RID-PARTIAL-SHORT",
            symbol="XRPUSDT",
            idempotent_key="idem-partial-short",
            client_order_id="order-4",
            side="BUY",
            quantity="3.0",
            partial_close=True,
            source_fsm="close_executor",
        )
        position_amt = Decimal("-10.0")

        payload, error = reconstruct_close_submission_from_order_log(
            entry, position_amt)

        assert error is None
        assert payload is not None
        assert payload.side == "BUY"
        assert payload.quantity == "3.0"
        assert payload.partial_close is True

    def test_reconstruct_multiple_times_identical(self) -> None:
        """Verify reconstruction is deterministic (same entry → same payload)."""
        entry = OrderLogEntry(
            rid="RID-DETERMINISM",
            symbol="BTCUSDT",
            idempotent_key="idem-det",
            client_order_id="order-5",
            side="SELL",
            quantity="1.5",
            partial_close=False,
        )
        position_amt = Decimal("1.5")

        payloads = []
        for _ in range(5):
            payload, error = reconstruct_close_submission_from_order_log(
                entry, position_amt)
            assert error is None
            assert payload is not None
            payloads.append(payload.model_dump())

        # All reconstructions must be identical
        for i in range(1, 5):
            assert payloads[i] == payloads[0], f"Reconstruction {i} differs from baseline"

    def test_reconstruct_preserves_client_order_id(self) -> None:
        """Verify client_order_id is preserved exactly."""
        entry = OrderLogEntry(
            rid="RID-CLIENT-ID",
            symbol="BTCUSDT",
            idempotent_key="idem-key",
            client_order_id="unique-order-12345",
            side="SELL",
            quantity="1.0",
            partial_close=False,
        )
        position_amt = Decimal("1.0")

        payload, error = reconstruct_close_submission_from_order_log(
            entry, position_amt)

        assert error is None
        assert payload.client_order_id == "unique-order-12345"


class TestPartialCloseDetection:
    """Prove that partial vs full close can be detected from order_log data."""

    def test_full_close_when_qty_equals_position(self) -> None:
        """Detect full close when qty matches position absolute value."""
        is_partial = reconstruct_partial_close_flag_from_side_and_position(
            position_amt=Decimal("5.0"),
            quantity="5.0",
        )
        assert is_partial is False, "Full close should not be flagged as partial"

    def test_partial_close_when_qty_less_than_position(self) -> None:
        """Detect partial close when qty < position absolute value."""
        is_partial = reconstruct_partial_close_flag_from_side_and_position(
            position_amt=Decimal("10.0"),
            quantity="3.0",
        )
        assert is_partial is True, "Partial close should be flagged as partial"

    def test_partial_close_negative_position(self) -> None:
        """Detect partial close with negative position."""
        is_partial = reconstruct_partial_close_flag_from_side_and_position(
            position_amt=Decimal("-10.0"),
            quantity="4.0",
        )
        assert is_partial is True

    def test_full_close_negative_position(self) -> None:
        """Detect full close for negative position."""
        is_partial = reconstruct_partial_close_flag_from_side_and_position(
            position_amt=Decimal("-5.0"),
            quantity="5.0",
        )
        assert is_partial is False


class TestOrderLogMultipleSymbols:
    """Verify reconstruction works across different symbols."""

    @pytest.mark.parametrize(
        "symbol,side,quantity,position,partial",
        [
            ("BTCUSDT", "SELL", "0.5", Decimal("0.5"), False),
            ("ETHUSDT", "BUY", "2.0", Decimal("-2.0"), False),
            ("SOLUSDT", "SELL", "10.0", Decimal("25.0"), True),
            ("XRPUSDT", "BUY", "100.0", Decimal("-150.0"), True),
            ("DOGEUSDT", "SELL", "1000.0", Decimal("1000.0"), False),
        ],
    )
    def test_reconstruct_various_symbols(
        self, symbol: str, side: str, quantity: str, position: Decimal, partial: bool
    ) -> None:
        """Test reconstruction across multiple symbols."""
        entry = OrderLogEntry(
            rid=f"RID-{symbol}",
            symbol=symbol,
            idempotent_key=f"idem-{symbol}",
            client_order_id=f"order-{symbol}",
            side=side,
            quantity=quantity,
            partial_close=partial,
        )

        payload, error = reconstruct_close_submission_from_order_log(
            entry, position)

        assert error is None
        assert payload is not None
        assert payload.symbol == symbol
        assert payload.side == side
        assert payload.quantity == quantity
        assert payload.partial_close == partial
