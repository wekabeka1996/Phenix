"""
Direct unit tests for AuthoritativeRestoreApply (Package 6B).

These tests exercise the apply_record method in isolation, using a minimal FSM stub
that provides only the shell helpers that apply_record calls through the back-ref.
No 6A read/parse machinery is involved.
"""

import pytest
from unittest.mock import MagicMock

from apps.reference.domains.execution_position.authoritative_restore_apply import (
    AuthoritativeRestoreApply,
)
from apps.reference.domains.execution_position.restore_artifact import (
    BRACKET_STATE_DEFERRED_PENDING_WAL,
    BRACKET_STATE_LINKED_ACTIVE,
    BRACKET_STATE_PARTIAL_LINKAGE,
    BRACKET_STATE_UNKNOWN,
    RESTORE_PHASE_UNKNOWN,
    DeferredBracketRef,
    ExecutionPositionRestoreLifecycleRecord,
    TRUTH_SOURCE_RESTORE_ARTIFACT,
)
from apps.reference.domains.execution_position.fsm_manage import ManageState
from apps.reference.domains.execution_position.fsm_close import CloseState


# ---------------------------------------------------------------------------
# Minimal FSM stub
# ---------------------------------------------------------------------------

def _make_fsm_stub(*, pending_brackets=None):
    """Return a minimal MagicMock satisfying the back-ref contract for 6B."""
    fsm = MagicMock()
    fsm._pending_brackets = pending_brackets or {}

    manage_flow = MagicMock()
    manage_flow.state = None
    manage_flow.symbol = None
    fsm._get_or_create_manage_flow.return_value = manage_flow

    close_flow = MagicMock()
    close_flow.state = None
    close_flow.position_active = None
    fsm._get_or_create_close_flow.return_value = close_flow

    return fsm, manage_flow, close_flow


def _make_record(**kwargs):
    """Build an ExecutionPositionRestoreLifecycleRecord with sensible defaults.

    The Pydantic model requires non-empty strings for manage_phase, close_phase,
    and bracket_state. Use RESTORE_PHASE_UNKNOWN / BRACKET_STATE_UNKNOWN for the
    'unknown' sentinel values.
    """
    defaults = dict(
        symbol="BTCUSDT",
        manage_phase=RESTORE_PHASE_UNKNOWN,   # "UNKNOWN"
        close_phase=RESTORE_PHASE_UNKNOWN,
        bracket_state=BRACKET_STATE_UNKNOWN,  # "UNKNOWN"
        live_reconcile_required=False,
        deferred_bracket_ref=None,
    )
    defaults.update(kwargs)
    return ExecutionPositionRestoreLifecycleRecord(**defaults)


# ---------------------------------------------------------------------------
# Part 1: manage phase apply
# ---------------------------------------------------------------------------

def test_apply_record_sets_manage_flow_state_exact():
    fsm, manage_flow, _ = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(manage_phase="TRACKING")

    result = applier.apply_record(record)

    assert manage_flow.state == ManageState.TRACKING
    assert manage_flow.symbol == "BTCUSDT"
    fsm._set_manage_truth_source.assert_called_once_with("BTCUSDT", TRUTH_SOURCE_RESTORE_ARTIFACT)
    assert result.manage_phase_restore_status == "exact"
    assert result.manage_phase_value == ManageState.TRACKING.value


def test_apply_record_manage_phase_unknown_does_not_write_flow():
    fsm, manage_flow, _ = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(manage_phase=RESTORE_PHASE_UNKNOWN)

    result = applier.apply_record(record)

    fsm._get_or_create_manage_flow.assert_not_called()
    fsm._set_manage_truth_source.assert_not_called()
    assert result.manage_phase_restore_status == "unknown"
    assert result.manage_phase_value == RESTORE_PHASE_UNKNOWN


def test_apply_record_unsupported_manage_phase_does_not_mutate():
    fsm, manage_flow, _ = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(manage_phase="INVALID_STATE_XYZ")

    result = applier.apply_record(record)

    fsm._get_or_create_manage_flow.assert_not_called()
    fsm._set_manage_truth_source.assert_not_called()
    assert any("unsupported_manage_phase" in r for r in result.unresolved_reasons)


# ---------------------------------------------------------------------------
# Part 2: close phase apply
# ---------------------------------------------------------------------------

def test_apply_record_sets_close_flow_state_exact():
    fsm, _, close_flow = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(close_phase="OPENED")

    result = applier.apply_record(record)

    assert close_flow.state == CloseState.OPENED
    assert close_flow.position_active is True  # OPENED is not FLAT or DONE
    assert result.close_phase_restore_status == "exact"
    assert result.close_phase_value == CloseState.OPENED.value


def test_apply_record_close_phase_flat_sets_position_active_false():
    fsm, _, close_flow = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(close_phase="FLAT")

    result = applier.apply_record(record)

    assert close_flow.state == CloseState.FLAT
    assert close_flow.position_active is False
    assert result.close_phase_restore_status == "exact"


def test_apply_record_close_phase_done_sets_position_active_false():
    fsm, _, close_flow = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(close_phase="DONE")

    result = applier.apply_record(record)

    assert close_flow.position_active is False


def test_apply_record_close_phase_unknown_does_not_write_flow():
    fsm, _, close_flow = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(close_phase=RESTORE_PHASE_UNKNOWN)

    result = applier.apply_record(record)

    fsm._get_or_create_close_flow.assert_not_called()
    assert result.close_phase_restore_status == "unknown"


def test_apply_record_unsupported_close_phase_does_not_mutate():
    fsm, _, close_flow = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(close_phase="NONSENSE_STATE_ZZZ")

    result = applier.apply_record(record)

    fsm._get_or_create_close_flow.assert_not_called()
    assert any("unsupported_close_phase" in r for r in result.unresolved_reasons)


# ---------------------------------------------------------------------------
# Part 3: bracket clear always runs before state adoption
# ---------------------------------------------------------------------------

def test_apply_record_always_clears_brackets_before_adoption():
    fsm, _, _ = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(bracket_state=BRACKET_STATE_UNKNOWN)

    applier.apply_record(record)

    fsm._clear_symbol_brackets.assert_called_once_with("BTCUSDT")


def test_apply_record_bracket_unknown_gives_unknown_status():
    fsm, _, _ = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(bracket_state=BRACKET_STATE_UNKNOWN)

    result = applier.apply_record(record)

    assert result.bracket_state_restore_status == "unknown"
    assert result.bracket_state_value == BRACKET_STATE_UNKNOWN


# ---------------------------------------------------------------------------
# Part 4: DEFERRED_PENDING_WAL cross-check (read-only WAL access)
# ---------------------------------------------------------------------------

def test_apply_record_deferred_pending_wal_exact_when_wal_matches():
    pending = {"symbol": "BTCUSDT", "side": "BUY"}
    fsm, _, _ = _make_fsm_stub(pending_brackets={"order123": pending})
    applier = AuthoritativeRestoreApply(fsm)

    deferred_ref = DeferredBracketRef(entry_order_id="order123")
    record = _make_record(
        bracket_state=BRACKET_STATE_DEFERRED_PENDING_WAL,
        deferred_bracket_ref=deferred_ref,
    )

    result = applier.apply_record(record)

    assert result.bracket_state_restore_status == "exact"
    assert result.bracket_state_value == BRACKET_STATE_DEFERRED_PENDING_WAL
    assert result.deferred_entry_order_id == "order123"


def test_apply_record_deferred_pending_wal_unknown_when_wal_missing():
    fsm, _, _ = _make_fsm_stub(pending_brackets={})
    applier = AuthoritativeRestoreApply(fsm)

    deferred_ref = DeferredBracketRef(entry_order_id="order123")
    record = _make_record(
        bracket_state=BRACKET_STATE_DEFERRED_PENDING_WAL,
        deferred_bracket_ref=deferred_ref,
    )

    result = applier.apply_record(record)

    assert result.bracket_state_restore_status == "unknown"
    assert "deferred_pending_missing_in_wal" in result.unresolved_reasons


def test_apply_record_deferred_pending_wal_unknown_when_symbol_mismatch():
    pending = {"symbol": "ETHUSDT", "side": "BUY"}  # different symbol
    fsm, _, _ = _make_fsm_stub(pending_brackets={"order123": pending})
    applier = AuthoritativeRestoreApply(fsm)

    deferred_ref = DeferredBracketRef(entry_order_id="order123")
    record = _make_record(
        bracket_state=BRACKET_STATE_DEFERRED_PENDING_WAL,
        deferred_bracket_ref=deferred_ref,
    )

    result = applier.apply_record(record)

    assert result.bracket_state_restore_status == "unknown"
    assert "deferred_pending_missing_in_wal" in result.unresolved_reasons


# ---------------------------------------------------------------------------
# Part 5: linked / partial linkage states deferred to 6C
# ---------------------------------------------------------------------------

def test_apply_record_linked_active_bracket_gives_unknown_with_reason():
    fsm, _, _ = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(bracket_state=BRACKET_STATE_LINKED_ACTIVE)

    result = applier.apply_record(record)

    assert result.bracket_state_restore_status == "unknown"
    assert "bracket_lineage_not_restorable_from_envelope" in result.unresolved_reasons


def test_apply_record_partial_linkage_bracket_gives_unknown_with_reason():
    fsm, _, _ = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(bracket_state=BRACKET_STATE_PARTIAL_LINKAGE)

    result = applier.apply_record(record)

    assert result.bracket_state_restore_status == "unknown"
    assert "bracket_lineage_not_restorable_from_envelope" in result.unresolved_reasons


def test_apply_record_unsupported_bracket_state_gives_unknown_with_reason():
    fsm, _, _ = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(bracket_state="TOTALLY_UNKNOWN_STATE_ZZZ")

    result = applier.apply_record(record)

    assert result.bracket_state_restore_status == "unknown"
    assert any("unsupported_bracket_state" in r for r in result.unresolved_reasons)


# ---------------------------------------------------------------------------
# Part 6: pass-through fields
# ---------------------------------------------------------------------------

def test_apply_record_live_reconcile_required_passthrough():
    fsm, _, _ = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(live_reconcile_required=True)

    result = applier.apply_record(record)

    assert result.live_reconcile_required is True


def test_apply_record_deferred_entry_order_id_none_when_no_ref():
    fsm, _, _ = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(deferred_bracket_ref=None)

    result = applier.apply_record(record)

    assert result.deferred_entry_order_id is None


# ---------------------------------------------------------------------------
# Part 7: combined — manage + close both applied exactly
# ---------------------------------------------------------------------------

def test_apply_record_exact_manage_and_close_combined():
    fsm, manage_flow, close_flow = _make_fsm_stub()
    applier = AuthoritativeRestoreApply(fsm)
    record = _make_record(
        manage_phase="TRACKING",
        close_phase="OPENED",
        bracket_state=BRACKET_STATE_UNKNOWN,
    )

    result = applier.apply_record(record)

    assert manage_flow.state == ManageState.TRACKING
    assert close_flow.state == CloseState.OPENED
    assert close_flow.position_active is True
    assert result.manage_phase_restore_status == "exact"
    assert result.close_phase_restore_status == "exact"
    assert result.bracket_state_restore_status == "unknown"
