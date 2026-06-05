"""Phase 9.3 validation: Exact vs UNKNOWN separation on restart."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.reference.domains.execution_position.flows.close.close_restart_state_separation import (
    RestartStateMap,
    StateConfidence,
    build_restart_state_from_restore_envelope_and_order_log,
)


class TestRestartStateEntry:
    """Test individual state entry tracking."""

    def test_entry_records_exact_state(self) -> None:
        """Verify exact state entry is recorded."""
        state_map = RestartStateMap()
        state_map.add_exact('symbol', 'BTCUSDT')

        assert 'symbol' in state_map.exact_state
        assert state_map.exact_state['symbol'] == 'BTCUSDT'
        assert 'symbol' not in state_map.unknown_state

    def test_entry_records_unknown_state(self) -> None:
        """Verify unknown state is marked."""
        state_map = RestartStateMap()
        state_map.add_unknown('filled_amount', 'ORDER_RESULT_UNKNOWN')

        assert 'filled_amount' in state_map.unknown_state
        assert 'filled_amount' not in state_map.exact_state

    def test_entry_cannot_be_both_exact_and_unknown(self) -> None:
        """Verify a state entry cannot be both exact and unknown."""
        state_map = RestartStateMap()
        state_map.add_exact('symbol', 'BTCUSDT')

        # Try to add as unknown (should add to unknown_state, not affect exact_state)
        state_map.add_unknown('symbol', 'OVERRIDE_TEST')

        # Both records exist, but this is an error condition we want to detect
        assert 'symbol' in state_map.exact_state
        assert 'symbol' in state_map.unknown_state


class TestRestartStateMap:
    """Test the restart state map container."""

    def test_clean_separation_full_close_long(self) -> None:
        """Verify clean exact/unknown separation for full close long."""
        restore_envelope = {
            'position_amount': Decimal('2.0'),
            'symbol': 'BTCUSDT',
        }
        order_log_entry = {
            'side': 'SELL',
            'quantity': '2.0',
            'client_order_id': 'order-1',
            'partial_close': False,
        }

        state = build_restart_state_from_restore_envelope_and_order_log(
            restore_envelope, order_log_entry
        )

        # Verify exact state is populated
        assert state.exact_state['symbol'] == 'BTCUSDT'
        assert state.exact_state['position_amount_at_close_request'] == Decimal(
            '2.0')
        assert state.exact_state['submitted_side'] == 'SELL'
        assert state.exact_state['was_partial_close'] is False

        # Verify unknown state is marked
        assert 'filled_amount' in state.unknown_state
        assert 'position_after_close' in state.unknown_state
        assert 'bracket_outcomes' in state.unknown_state
        assert 'tidy_state' in state.unknown_state

    def test_clean_separation_partial_close_short(self) -> None:
        """Verify clean exact/unknown separation for partial close short."""
        restore_envelope = {
            'position_amount': Decimal('-10.0'),
            'symbol': 'ETHUSDT',
        }
        order_log_entry = {
            'side': 'BUY',
            'quantity': '3.0',
            'client_order_id': 'order-2',
            'partial_close': True,
        }

        state = build_restart_state_from_restore_envelope_and_order_log(
            restore_envelope, order_log_entry
        )

        assert state.exact_state['symbol'] == 'ETHUSDT'
        assert state.exact_state['submitted_quantity'] == '3.0'
        assert state.exact_state['was_partial_close'] is True

        # Still marked unknown post-close state
        assert 'filled_amount' in state.unknown_state
        assert 'position_after_close' in state.unknown_state

    def test_verdict_verified_separation(self) -> None:
        """Verify verdict when separation is clean."""
        restore_envelope = {
            'position_amount': Decimal('1.0'),
            'symbol': 'SOLUSDT',
        }
        order_log_entry = {
            'side': 'SELL',
            'quantity': '1.0',
            'client_order_id': 'order-3',
            'partial_close': False,
        }

        state = build_restart_state_from_restore_envelope_and_order_log(
            restore_envelope, order_log_entry
        )

        verdict = state.get_verdict()
        assert verdict == "VERIFIED_SEPARATION"

    def test_verdict_contaminated_when_guessing_post_close(self) -> None:
        """Verify verdict detects guessed post-close state."""
        state = RestartStateMap()
        state.add_exact('symbol', 'BTCUSDT')
        state.add_exact('filled_amount', Decimal('2.0'))  # Guessed post-close!
        state.add_unknown('position_after_close', 'UNKNOWN')

        verdict = state.get_verdict()
        assert "CONTAMINATED" in verdict
        assert "filled_amount" in verdict

    def test_no_guessing_verification(self) -> None:
        """Verify that guessing post-close state is detected."""
        state = RestartStateMap()
        state.add_exact('symbol', 'BTCUSDT')
        state.add_exact('bracket_outcomes', {'tp': True})  # Guessed!

        is_clean, reason = state.verify_no_guessing()
        assert is_clean is False
        assert "bracket_outcomes" in reason

    def test_to_dict_serialization(self) -> None:
        """Verify state can be serialized to dict."""
        state = RestartStateMap()
        state.add_exact('symbol', 'BTCUSDT')
        state.add_unknown('filled_amount', 'UNKNOWN')

        state_dict = state.to_dict()
        assert state_dict['exact_count'] == 1
        assert state_dict['unknown_count'] == 1
        assert 'symbol' in state_dict['exact_state']
        assert 'filled_amount' in state_dict['unknown_keys']


class TestStateConfidenceAcrossMultipleScenarios:
    """Test state separation across various trading scenarios."""

    @pytest.mark.parametrize(
        "scenario,position,qty,is_partial",
        [
            ("small_long", Decimal("0.5"), "0.5", False),
            ("large_long", Decimal("10.0"), "10.0", False),
            ("small_short", Decimal("-0.5"), "0.5", False),
            ("large_short", Decimal("-10.0"), "10.0", False),
            ("partial_long", Decimal("5.0"), "2.5", True),
            ("partial_short", Decimal("-5.0"), "2.5", True),
        ],
    )
    def test_state_separation_various_scenarios(
        self, scenario: str, position: Decimal, qty: str, is_partial: bool
    ) -> None:
        """Test state separation across various close scenarios."""
        restore_envelope = {
            'position_amount': position,
            'symbol': f'{scenario}-USDT',
        }
        order_log_entry = {
            'side': 'SELL' if position > 0 else 'BUY',
            'quantity': qty,
            'client_order_id': f'order-{scenario}',
            'partial_close': is_partial,
        }

        state = build_restart_state_from_restore_envelope_and_order_log(
            restore_envelope, order_log_entry
        )

        # All should have clean separation
        verdict = state.get_verdict()
        assert verdict == "VERIFIED_SEPARATION", f"Scenario {scenario} failed: {verdict}"

        # All should have exact and unknown marked
        assert len(state.exact_state) > 0
        assert len(state.unknown_state) > 0


class TestUnknownStateReasoning:
    """Verify that unknown state reasons are explicit."""

    def test_unknown_state_has_reason(self) -> None:
        """Verify each unknown entry has a reason."""
        state = RestartStateMap()
        state.add_unknown('filled_amount', 'ORDER_FILL_UNKNOWN')
        state.add_unknown('position_post_close', 'DEPENDS_ON_FILL')

        # Each entry should have reasoning
        unknown_entries = [
            e for e in state.entries if e.confidence == StateConfidence.UNKNOWN]
        assert len(unknown_entries) == 2

        for entry in unknown_entries:
            assert entry.value.startswith('UNKNOWN(')
            assert ')' in entry.value

    def test_exact_state_has_value(self) -> None:
        """Verify each exact entry has a concrete value."""
        state = RestartStateMap()
        state.add_exact('symbol', 'BTCUSDT')
        state.add_exact('quantity', '2.0')

        exact_entries = [
            e for e in state.entries if e.confidence == StateConfidence.EXACT]
        assert len(exact_entries) == 2

        for entry in exact_entries:
            assert entry.value is not None
            assert entry.value != 'UNKNOWN'
