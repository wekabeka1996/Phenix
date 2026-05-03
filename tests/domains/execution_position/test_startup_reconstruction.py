"""Tests for StartupReconstruction contour (Package 6C)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.state.startup_reconstruction import StartupReconstruction
from apps.reference.domains.execution_position.state.restore_artifact import TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN


@pytest.fixture
def fsm_stub():
    """Create a minimal FSM stub for testing StartupReconstruction."""
    fsm = MagicMock(spec=ExecPosFSM)
    fsm.order_guardian = MagicMock()
    fsm._runtime_order_index.return_value = MagicMock()
    fsm.manage_flows = {}
    fsm._startup_truth_orchestrator = MagicMock()

    # Track observational calls
    fsm._calls = []

    def _mock_clear(symbol):
        fsm._calls.append(("clear", symbol))

    def _mock_set(symbol, sl_order_id=None, tp_order_id=None, truth_source=None):
        fsm._calls.append(
            ("set_snapshot", symbol, sl_order_id, tp_order_id, truth_source))

    def _mock_append_record(**kwargs):
        fsm._calls.append(("append_restart_truth", kwargs))

    def _mock_emit(topic, payload):
        fsm._calls.append(("emit", topic, payload))

    fsm._clear_symbol_brackets.side_effect = _mock_clear
    fsm._set_symbol_brackets_snapshot.side_effect = _mock_set
    fsm._startup_truth_orchestrator._append_restart_truth_record.side_effect = _mock_append_record
    fsm._emit_observability_event.side_effect = _mock_emit

    return fsm


def test_reconstruct_returns_zero_when_guardian_none(fsm_stub):
    """reconstruct() returns zero reconstructed when order_guardian is None"""
    fsm_stub.order_guardian = None
    target = StartupReconstruction(fsm_stub)

    result = target.reconstruct([{"symbol": "BTC", "orderId": "123"}])

    assert result["summary"]["symbols_reconstructed"] == 0
    assert result["summary"]["order_index_registrations"] == 0
    assert result["summary"]["unresolved_symbols"] == 0
    assert result["records"] == []


def test_reconstruct_skips_orders_missing_symbol_or_id(fsm_stub):
    """reconstruct() skips orders missing symbol or exchange_order_id"""
    target = StartupReconstruction(fsm_stub)

    # One valid, two missing required fields
    open_orders = [
        {"symbol": "", "orderId": "123"},
        {"symbol": "ETH", "orderId": ""},
        {"symbol": "BTC", "orderId": "123"},
    ]

    # Guardian only resolves the valid one
    fsm_stub.order_guardian.resolve_terminal_bracket_context.return_value = {
        "bracket_role": "SL",
        "tracked_bracket_order_id": "123",
        "tracked_client_order_id": "c123",
    }

    target.reconstruct(open_orders)

    # Guardian shouldn't be called for empty symbol/orderId
    fsm_stub.order_guardian.resolve_terminal_bracket_context.assert_called_once_with(
        client_order_id=None,
        exchange_order_id="123",
        symbol="BTC"
    )


def test_reconstruct_skips_unsupported_bracket_roles(fsm_stub):
    """reconstruct() skips unsupported bracket roles and marks unresolved"""
    target = StartupReconstruction(fsm_stub)

    open_orders = [{"symbol": "BTC", "orderId": "123"}]

    # Guardian returns unsupported role "MARKET"
    fsm_stub.order_guardian.resolve_terminal_bracket_context.return_value = {
        "bracket_role": "MARKET",
        "tracked_bracket_order_id": "123",
        "tracked_client_order_id": "c123",
    }

    target.reconstruct(open_orders)

    # Should clear brackets and emit unresolved
    clears = [c for c in fsm_stub._calls if c[0] == "clear"]
    assert len(clears) == 1
    assert clears[0][1] == "BTC"

    records = [c for c in fsm_stub._calls if c[0] == "append_restart_truth"]
    assert len(records) == 1
    assert records[0][1]["event_type"] == "EXECUTION_RESTART_RUNTIME_TRUTH_UNRESOLVED"
    assert "unsupported_role:MARKET" in records[0][1]["unresolved_reasons"]


def test_reconstruct_sl_tp_correctly_for_resolved_symbol(fsm_stub):
    """reconstruct() reconstructs SL/TP correctly for resolved symbol"""
    target = StartupReconstruction(fsm_stub)

    open_orders = [
        {"symbol": "BTC", "orderId": "111",
            "clientOrderId": "c1", "type": "STOP_MARKET"},
        {"symbol": "BTC", "orderId": "222", "clientOrderId": "c2", "type": "LIMIT"},
    ]

    def mock_resolve(*, client_order_id, exchange_order_id, symbol):
        if exchange_order_id == "111":
            return {
                "bracket_role": "SL",
                "tracked_bracket_order_id": "111",
                "tracked_client_order_id": "c1",
                "order_type": "STOP_MARKET"
            }
        elif exchange_order_id == "222":
            return {
                "bracket_role": "TP",
                "tracked_bracket_order_id": "222",
                "tracked_client_order_id": "c2",
                "order_type": "LIMIT"
            }
        return None

    fsm_stub.order_guardian.resolve_terminal_bracket_context.side_effect = mock_resolve

    # Order index check
    order_index = fsm_stub._runtime_order_index.return_value
    order_index.get.return_value = None  # Pretend it's not in the index yet

    # Mock a manage flow
    manage_flow = MagicMock()
    fsm_stub.manage_flows = {"BTC": manage_flow}
    fsm_stub._manage_state_value.return_value = "MANAGE_OPEN"

    result = target.reconstruct(open_orders)

    # Check registration
    assert order_index.register_bracket_child.call_count == 2

    # Check manage flow update
    manage_flow.set_bracket_ids.assert_called_once_with(
        sl_order_id="111", tp_order_id="222"
    )

    # Check snapshot set
    sets = [c for c in fsm_stub._calls if c[0] == "set_snapshot"]
    assert len(sets) == 1
    assert sets[0] == ("set_snapshot", "BTC", "111", "222",
                       TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN)

    # Check records
    records = [c for c in fsm_stub._calls if c[0] == "append_restart_truth"]
    assert len(records) == 1
    assert records[0][1]["event_type"] == "EXECUTION_RESTART_RUNTIME_TRUTH_RECONSTRUCTED"
    assert records[0][1]["sl_order_id"] == "111"
    assert records[0][1]["tp_order_id"] == "222"
    assert records[0][1]["order_index_registrations"] == 2

    # Check return schema
    assert result["summary"]["symbols_reconstructed"] == 1
    assert result["summary"]["order_index_registrations"] == 2
    assert result["summary"]["unresolved_symbols"] == 0
    assert len(result["records"]) == 1
    assert result["records"][0]["status"] == "reconstructed"


def test_reconstruct_marks_unresolved_on_duplicate_roles(fsm_stub):
    """reconstruct() marks symbol unresolved when bracket role duplicates detected"""
    target = StartupReconstruction(fsm_stub)

    open_orders = [
        {"symbol": "BTC", "orderId": "111"},
        {"symbol": "BTC", "orderId": "222"},
    ]

    # Guardian returns SL for both!
    fsm_stub.order_guardian.resolve_terminal_bracket_context.return_value = {
        "bracket_role": "SL",
        "tracked_bracket_order_id": "X",  # Needs to differ to trigger duplicate check
        "tracked_client_order_id": "cX",
    }

    # Make them differ directly in context per call
    def mock_resolve(*, client_order_id, exchange_order_id, symbol):
        return {
            "bracket_role": "SL",
            "tracked_bracket_order_id": exchange_order_id,
            "tracked_client_order_id": f"c{exchange_order_id}",
        }
    fsm_stub.order_guardian.resolve_terminal_bracket_context.side_effect = mock_resolve

    target.reconstruct(open_orders)

    # Because there are duplicate SLs, it shouldn't set the SL order ID (is excluded)
    # But because SL was the only role, both sl/tp are None, triggering clear
    clears = [c for c in fsm_stub._calls if c[0] == "clear"]
    assert len(clears) == 1

    records = [c for c in fsm_stub._calls if c[0] == "append_restart_truth"]
    assert len(records) == 1
    assert records[0][1]["event_type"] == "EXECUTION_RESTART_RUNTIME_TRUTH_UNRESOLVED"

    # Verify reason matches code string f"duplicate_{order_kind.lower()}:{existing_order_id},{tracked_order_id}"
    reasons = records[0][1]["unresolved_reasons"]
    assert any("duplicate_sl:111,222" in r for r in reasons)


def test_reconstruct_observability_event_emitted(fsm_stub):
    """_emit_observability_event called once with reconstruction summary"""
    target = StartupReconstruction(fsm_stub)

    target.reconstruct([])

    emits = [c for c in fsm_stub._calls if c[0] == "emit"]
    assert len(emits) == 1
    assert emits[0][1] == "RESTORE:EXECUTION_POSITION_RUNTIME_TRUTH_RECONCILED"
    assert emits[0][2] == {
        "symbols_reconstructed": 0,
        "order_index_registrations": 0,
        "unresolved_symbols": 0,
    }
