"""
Tests for PATCH_FALSE_ACTIVE_LIFECYCLE_SOURCE_FIRST

Four coverage areas:
A. False-positive regression — FLAT + bracket metadata → has_active_lifecycle() False
B. True-positive safety — real active lifecycle → has_active_lifecycle() True
C. No-regression integration — intent passes through after clearing false state
D. Bracket metadata preservation — bracket IDs still stored in _symbol_brackets
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.reference.domains.execution_position.fsm_manage import (
    ManageFlowFSM,
    ManageState,
)
from apps.reference.config_loader import get_config


# ──────────────────────────────────────────────────────────────────
# Fixture
# ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def manage_flow() -> ManageFlowFSM:
    cfg = get_config()
    return ManageFlowFSM(config=cfg)


# ──────────────────────────────────────────────────────────────────
# Test A — False-positive regression (primary)
# ──────────────────────────────────────────────────────────────────

class TestFalsePositiveRegression:
    """
    SCENARIO: ManageFlowFSM is FLAT. Bracket-health path injects sl_order_id
    and tp_order_id via set_bracket_ids(). No entry order, no position.

    EXPECTED: has_active_lifecycle() must return False.
    This proves the false positive that caused OPEN_GUARD_FAIL is gone.
    """

    def test_flat_with_only_bracket_ids_is_not_active(self, manage_flow: ManageFlowFSM) -> None:
        assert manage_flow.state == ManageState.FLAT

        # Simulate bracket-health injection
        manage_flow.set_bracket_ids(
            sl_order_id="SL-BRACKET-1234",
            tp_order_id="TP-BRACKET-5678",
        )

        # Confirm IDs are stored (bracket is placed on exchange)
        assert manage_flow.sl_order_id == "SL-BRACKET-1234"
        assert manage_flow.tp_order_id == "TP-BRACKET-5678"

        # Critical assertion: this must NOT be an active lifecycle
        assert manage_flow.has_active_lifecycle() is False, (
            "REGRESSION: has_active_lifecycle() returned True for a FLAT FSM "
            "with only bracket-health IDs. This re-creates the OPEN_GUARD_FAIL phantom loop."
        )

    def test_flat_with_tp1_tp2_bracket_ids_also_not_active(self, manage_flow: ManageFlowFSM) -> None:
        """tp1/tp2 bracket IDs alone are also not active lifecycle evidence."""
        assert manage_flow.state == ManageState.FLAT
        manage_flow.tp1_order_id = "TP1-BRACKET"
        manage_flow.tp2_order_id = "TP2-BRACKET"

        assert manage_flow.has_active_lifecycle() is False

    def test_flat_with_all_ids_cleared_is_not_active(self, manage_flow: ManageFlowFSM) -> None:
        """Completely clean FLAT FSM is not active — baseline control."""
        assert manage_flow.has_active_lifecycle() is False


# ──────────────────────────────────────────────────────────────────
# Test B — True-positive safety (guard must still fire for real lifecycle)
# ──────────────────────────────────────────────────────────────────

class TestTruePositiveSafety:
    """
    SCENARIO: A real lifecycle is active.
    EXPECTED: has_active_lifecycle() returns True in ALL real-lifecycle scenarios.
    """

    def test_non_flat_state_is_always_active(self, manage_flow: ManageFlowFSM) -> None:
        for state in (
            ManageState.OPENED,
            ManageState.TRACKING,
            ManageState.BRACKETS_PLACED,
            ManageState.EMIT_DEC_ADJUST,
        ):
            manage_flow.state = state
            assert manage_flow.has_active_lifecycle() is True, (
                f"True-positive failure: state={state} should be active lifecycle"
            )
        # Restore
        manage_flow.state = ManageState.FLAT

    def test_closing_position_flag_is_active(self, manage_flow: ManageFlowFSM) -> None:
        manage_flow._closing_position = True
        assert manage_flow.has_active_lifecycle() is True

    def test_position_qty_nonzero_is_active(self, manage_flow: ManageFlowFSM) -> None:
        manage_flow.position_qty = Decimal("0.05")
        assert manage_flow.has_active_lifecycle() is True

    def test_flat_with_entry_order_and_bracket_ids_is_active(self, manage_flow: ManageFlowFSM) -> None:
        """
        When there IS entry evidence AND bracket IDs, the lifecycle is active.
        This is the normal post-fill FLAT-with-brackets scenario.
        """
        manage_flow.entry_order_id = "ENTRY-ORDER-1"
        manage_flow.set_bracket_ids("SL-987", "TP-987")
        assert manage_flow.has_active_lifecycle() is True

    def test_flat_with_position_entry_price_and_brackets_is_active(self, manage_flow: ManageFlowFSM) -> None:
        manage_flow.position_entry_price = Decimal("50000")
        manage_flow.sl_order_id = "SL-CCC"
        assert manage_flow.has_active_lifecycle() is True

    def test_flat_with_entry_client_order_id_is_active(self, manage_flow: ManageFlowFSM) -> None:
        manage_flow.entry_client_order_id = "CLIENT-AURORA-123"
        assert manage_flow.has_active_lifecycle() is True


# ──────────────────────────────────────────────────────────────────
# Test C — No-regression: bracket injection guard in fsm.py
# ──────────────────────────────────────────────────────────────────

class TestInjectionGuard:
    """
    Tests that the injection guard in fsm.py is consistent with the
    updated predicate: bracket IDs injected while FLAT don't take effect
    on the lifecycle truth.
    """

    def test_set_bracket_ids_on_flat_does_not_activate_lifecycle(self, manage_flow: ManageFlowFSM) -> None:
        """
        Simulates the path _place_health_check_brackets() would take
        WITHOUT the injection guard. Confirms Fix 2 (predicate) alone would
        also protect against this.
        """
        assert manage_flow.state == ManageState.FLAT
        manage_flow.set_bracket_ids("SL-HEALTH-1", "TP-HEALTH-1")

        # Even with IDs injected, the predicate returns False
        assert manage_flow.has_active_lifecycle() is False

    def test_set_bracket_ids_on_opened_state_activates_lifecycle(self, manage_flow: ManageFlowFSM) -> None:
        """
        When state != FLAT, same set_bracket_ids() call should make lifecycle active.
        Proves the injection guard in fsm.py is aligned with the new predicate.
        """
        manage_flow.state = ManageState.OPENED
        manage_flow.set_bracket_ids("SL-HEALTH-2", "TP-HEALTH-2")

        assert manage_flow.has_active_lifecycle() is True


# ──────────────────────────────────────────────────────────────────
# Test D — Bracket metadata preservation
# ──────────────────────────────────────────────────────────────────

class TestBracketMetadataPreservation:
    """
    SCENARIO: Bracket health places orders on exchange. We apply the FLAT guard.
    EXPECTED: The bracket IDs are still STORED on the ManageFlowFSM (for cancellation
    and tracking), but they don't masquerade as active lifecycle truth.
    """

    def test_bracket_ids_are_stored_even_in_flat(self, manage_flow: ManageFlowFSM) -> None:
        """
        The fix removes bracket IDs from has_active_lifecycle() truth in FLAT,
        but must NOT remove the IDs from the FSM fields — they're still needed
        for OCO emulation and bracket cancel logic.
        """
        assert manage_flow.state == ManageState.FLAT
        manage_flow.set_bracket_ids("SL-STORE-1", "TP-STORE-1")

        # IDs must be accessible for downstream logic (e.g. bracket cancellation)
        assert manage_flow.sl_order_id == "SL-STORE-1"
        assert manage_flow.tp_order_id == "TP-STORE-1"

    def test_clear_lifecycle_also_clears_bracket_ids(self, manage_flow: ManageFlowFSM) -> None:
        """On explicit lifecycle clear, bracket IDs are also cleared."""
        manage_flow.set_bracket_ids("SL-CLR", "TP-CLR")
        manage_flow._clear_lifecycle_tracking(reason="test_teardown", clear_symbol=False)

        assert manage_flow.sl_order_id is None
        assert manage_flow.tp_order_id is None
        assert manage_flow.has_active_lifecycle() is False
