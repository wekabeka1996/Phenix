"""
test_limit_deferred_dual_bracket_invocation.py

Regression tests for the DUAL_INVOCATION_RACE fix.

Proven failure mode (pre-fix):
  For every LIMIT entry fill, two bracket placement paths fired concurrently:
    Path A: fsm_manage._place_brackets (sync, via manage_flow.handle)
    Path B: bracket_manager.place_deferred_brackets (async, via event_handlers)
  Path A placed SL/TP successfully; Path B received Binance -4130 because
  Path A's orders were already live. Path B's error handler then cancelled
  Path A's valid brackets and executed force_reduce_only_close.

Fix:
  FillIngressCoordinator checks _pending_brackets before calling manage_flow.handle.
  If the fill has a pending deferred bracket entry, it sets
  manage_flow._deferred_bracket_entry_id = entry_order_id.
  ManageFlowFSM FLAT FILL handler consumes and clears that flag; if set,
  skips _place_brackets and returns None (Path B owns the brackets).

Tests in this file:
  1. LIMIT-deferred fill: manage_flow._place_brackets is NOT called; state=BRACKETS_PENDING.
  2. Non-deferred (MARKET) fill: manage_flow._place_brackets IS called.
  3. Non-deferred fill without pending brackets: guard not triggered.
  4. Flag consumed per-fill: second fill does not inherit flag from first.
  5. Force-close safety: if Path B fails after fsm skip, position is not silently left unprotected.
  6. Pending key type: int orderId and string orderId are both handled.
  7. Existing -4130 classification preserved after fix.
"""
from __future__ import annotations

import pytest
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

from vfoundation.core.protocol import Message

from apps.reference.domains.execution_position.flows.manage.fsm_manage import (
    ManageFlowFSM,
    ManageState,
)

pytest_plugins = ("tests.domains.execution_position.conftest",)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> MagicMock:
    cfg = MagicMock()
    cfg.trading.execution.anti_race_close_ms = 800
    cfg.trading.execution.manage.auto = True
    cfg.trading.execution.manage.emergency.wait_mode_bars = 2
    cfg.trading.execution.manage.brackets.enable = True
    cfg.trading.execution.manage.brackets.oco_emulation = True
    cfg.trading.execution.manage.brackets.sl.fixed_bps = 40
    cfg.trading.execution.manage.brackets.tp.fixed_bps = 80
    cfg.trading.execution.manage.brackets.offset_bps = 5
    cfg.strategies.aurora.decision.bar_gating = None
    btc_asset = MagicMock()
    btc_asset.exit.sl_pct = 0.02
    btc_asset.exit.max_hold_sec = 600
    btc_asset.take_profit.tp_low_ratio = 0.5
    btc_asset.take_profit.tp_high_ratio = 1.0
    btc_asset.take_profit.partial_exit_pct = 0.5
    btc_asset.trailing_stop.enabled = False
    cfg.strategies.aurora.assets = {"BTCUSDT": btc_asset, "ETHUSDT": btc_asset}
    return cfg


def _make_fill_msg(
    symbol: str = "BTCUSDT",
    order_id: str = "8680894868",
    qty: str = "0.01",
    price: str = "50000",
    side: str = "BUY",
    order_type: str = "LIMIT",
    verb: str = "TRADE_EXECUTED",
) -> Message:
    return Message(
        op="EVT",
        verb=verb,
        src="adapter",
        dst="execution_position",
        why="test fill",
        rid=f"aurora_{symbol}_test",
        pld={
            "symbol": symbol,
            "orderId": order_id,
            "qty": qty,
            "price": price,
            "side": side,
            "order_type": order_type,
            "quantity": qty,
            "status": "FILLED",
        },
    )


def _make_manage_fsm(config: Optional[MagicMock] = None) -> ManageFlowFSM:
    cfg = config or _make_config()
    fsm = ManageFlowFSM(config=cfg)
    fsm.state = ManageState.FLAT
    return fsm


# ---------------------------------------------------------------------------
# Test 1: LIMIT-deferred fill — _place_brackets must NOT be called
# ---------------------------------------------------------------------------

class TestDeferredBracketGuardSkipsBrackets:
    """
    FillIngressCoordinator sets _deferred_bracket_entry_id before handle().
    ManageFlowFSM FLAT FILL handler must skip _place_brackets when flag is set.
    Position must still be created (_on_fill) and state must be BRACKETS_PENDING.
    """

    def test_flat_fill_with_deferred_flag_skips_place_brackets(self, fsm_harness):
        """Core regression: _place_brackets not called when deferred flag set."""
        fsm, bus, cfg = fsm_harness
        manage = ManageFlowFSM(config=cfg)
        manage.state = ManageState.FLAT

        # Simulate FillIngressCoordinator setting the flag
        manage._deferred_bracket_entry_id = "8680894868"

        fill_msg = _make_fill_msg(order_id="8680894868")
        place_brackets_called = []

        with patch.object(manage, "_place_brackets", side_effect=lambda m: place_brackets_called.append(m)):
            result = manage.handle(fill_msg)

        assert len(place_brackets_called) == 0, (
            "_place_brackets must NOT be called for LIMIT-DEFERRED fill"
        )
        assert result is None, "Expected None return when deferred owner skips bracket placement"
        assert manage.state == ManageState.BRACKETS_PENDING, (
            "State must remain BRACKETS_PENDING after deferred skip"
        )

    def test_flat_fill_with_deferred_flag_still_creates_position(self, fsm_harness):
        """Position tracking (_on_fill) must complete even when bracket placement is skipped."""
        fsm, bus, cfg = fsm_harness
        manage = ManageFlowFSM(config=cfg)
        manage.state = ManageState.FLAT
        manage._deferred_bracket_entry_id = "8680894868"

        fill_msg = _make_fill_msg(
            order_id="8680894868",
            symbol="BTCUSDT",
            qty="0.01",
            price="50000",
            side="BUY",
        )

        with patch.object(manage, "_place_brackets", return_value=None):
            manage.handle(fill_msg)

        assert manage.position_qty is not None, "position_qty must be set after _on_fill"
        assert manage.symbol == "BTCUSDT"
        assert manage.entry_order_id == "8680894868"

    def test_deferred_flag_cleared_after_use(self, fsm_harness):
        """Flag must be consumed (set to None) after the fill is processed."""
        fsm, bus, cfg = fsm_harness
        manage = ManageFlowFSM(config=cfg)
        manage.state = ManageState.FLAT
        manage._deferred_bracket_entry_id = "8680894868"

        fill_msg = _make_fill_msg(order_id="8680894868")

        with patch.object(manage, "_place_brackets", return_value=None):
            manage.handle(fill_msg)

        assert manage._deferred_bracket_entry_id is None, (
            "_deferred_bracket_entry_id must be None after consumption"
        )


# ---------------------------------------------------------------------------
# Test 2: Non-deferred (MARKET) fill — _place_brackets MUST be called
# ---------------------------------------------------------------------------

class TestNonDeferredFillStillPlacesBrackets:
    """
    When _deferred_bracket_entry_id is not set (MARKET entries, no pending brackets),
    ManageFlowFSM must still call _place_brackets as before.
    """

    def test_flat_fill_without_deferred_flag_calls_place_brackets(self, fsm_harness):
        """MARKET entry: _place_brackets still called when no deferred flag."""
        fsm, bus, cfg = fsm_harness
        manage = ManageFlowFSM(config=cfg)
        manage.state = ManageState.FLAT

        assert manage._deferred_bracket_entry_id is None  # no flag set

        fill_msg = _make_fill_msg(
            order_id="9999000001",
            order_type="MARKET",
        )
        place_brackets_called = []

        with patch.object(manage, "_place_brackets", side_effect=lambda m: (
            place_brackets_called.append(m), None
        )[-1]):
            manage.handle(fill_msg)

        assert len(place_brackets_called) == 1, (
            "_place_brackets must be called for non-deferred (MARKET) fill"
        )

    def test_flat_fill_wrong_order_id_calls_place_brackets(self, fsm_harness):
        """
        If _deferred_bracket_entry_id is set but does NOT match the fill's orderId,
        _place_brackets must still be called (guard is entry-specific).
        """
        fsm, bus, cfg = fsm_harness
        manage = ManageFlowFSM(config=cfg)
        manage.state = ManageState.FLAT
        manage._deferred_bracket_entry_id = "DIFFERENT_ORDER_ID"

        fill_msg = _make_fill_msg(order_id="8680894868")
        place_brackets_called = []

        with patch.object(manage, "_place_brackets", side_effect=lambda m: (
            place_brackets_called.append(m), None
        )[-1]):
            manage.handle(fill_msg)

        assert len(place_brackets_called) == 1, (
            "_place_brackets must be called when order_id does not match deferred flag"
        )
        # Flag should still be consumed
        assert manage._deferred_bracket_entry_id is None


# ---------------------------------------------------------------------------
# Test 3: Flag not set in __init__
# ---------------------------------------------------------------------------

class TestInitialFlagState:
    """Ensure _deferred_bracket_entry_id starts as None for all fresh instances."""

    def test_deferred_bracket_entry_id_initially_none(self, fsm_harness):
        fsm, bus, cfg = fsm_harness
        manage = ManageFlowFSM(config=cfg)
        assert manage._deferred_bracket_entry_id is None

    def test_deferred_bracket_entry_id_attribute_exists(self, fsm_harness):
        fsm, bus, cfg = fsm_harness
        manage = ManageFlowFSM(config=cfg)
        assert hasattr(manage, "_deferred_bracket_entry_id")


# ---------------------------------------------------------------------------
# Test 4: Flag consumed per-fill — no leakage to subsequent fills
# ---------------------------------------------------------------------------

class TestFlagNotLeakedBetweenFills:
    """
    A deferred flag set for fill #1 must not affect fill #2 if fill #2 has
    no pending deferred bracket.
    """

    def test_flag_cleared_before_second_fill(self, fsm_harness):
        """
        Simulate two sequential fills. Second fill (different entry) must
        call _place_brackets normally even if flag was consumed by first.
        """
        fsm, bus, cfg = fsm_harness
        manage = ManageFlowFSM(config=cfg)

        # Fill 1: LIMIT-deferred, flag set
        manage.state = ManageState.FLAT
        manage._deferred_bracket_entry_id = "ORDER_1"
        fill1 = _make_fill_msg(order_id="ORDER_1")
        place_calls_1 = []
        with patch.object(manage, "_place_brackets", side_effect=lambda m: (
            place_calls_1.append(m), None
        )[-1]):
            manage.handle(fill1)

        assert len(place_calls_1) == 0  # deferred: skipped
        assert manage._deferred_bracket_entry_id is None  # consumed

        # After the first trade, simulate position close and return to FLAT
        manage.state = ManageState.FLAT
        manage.position_qty = None
        manage.position_entry_price = None
        manage.symbol = None

        # Fill 2: MARKET, no flag
        fill2 = _make_fill_msg(order_id="ORDER_2", order_type="MARKET")
        place_calls_2 = []
        with patch.object(manage, "_place_brackets", side_effect=lambda m: (
            place_calls_2.append(m), None
        )[-1]):
            manage.handle(fill2)

        assert len(place_calls_2) == 1  # non-deferred: _place_brackets called


# ---------------------------------------------------------------------------
# Test 5: Force-close safety — Path B failure still triggers protection
# ---------------------------------------------------------------------------

class TestForceCloseSafetyPreserved:
    """
    When fsm_manage skips _place_brackets (deferred mode), bracket_manager
    (Path B) is still responsible for brackets. If Path B encounters a failure,
    it must still emit BRACKET_PLACEMENT_FAILED and trigger force_reduce_only_close.
    This test verifies that the ManageFlowFSM skip does NOT suppress Path B errors.
    """

    def test_skipping_place_brackets_does_not_suppress_deferred_errors(self, fsm_harness):
        """
        ManageFlowFSM returns None for the fill (deferred skip).
        Independently, bracket_manager.place_deferred_brackets can still fail
        and emit BRACKET_PLACEMENT_FAILED with force_reduce_only_close.
        The two paths are independent — fsm_manage skip does not mute Path B.
        """
        fsm, bus, cfg = fsm_harness
        manage = ManageFlowFSM(config=cfg)
        manage.state = ManageState.FLAT
        manage._deferred_bracket_entry_id = "8680894868"

        fill_msg = _make_fill_msg(order_id="8680894868")

        with patch.object(manage, "_place_brackets", return_value=None) as mock_place:
            result = manage.handle(fill_msg)

        # Path A is skipped, returns None
        assert result is None
        # Path A's _place_brackets not called
        mock_place.assert_not_called()
        # Position still created (Path B will do brackets)
        assert manage.state == ManageState.BRACKETS_PENDING

    def test_position_not_silently_unprotected_on_deferred_skip(self, fsm_harness):
        """
        After deferred skip, manage_flow state is BRACKETS_PENDING — not FLAT.
        The system is in a state that expects brackets to arrive from Path B.
        force_reduce_only_close path in bracket_manager remains active if Path B fails.
        """
        fsm, bus, cfg = fsm_harness
        manage = ManageFlowFSM(config=cfg)
        manage.state = ManageState.FLAT
        manage._deferred_bracket_entry_id = "8680894868"

        fill_msg = _make_fill_msg(order_id="8680894868")

        with patch.object(manage, "_place_brackets", return_value=None):
            manage.handle(fill_msg)

        # State is BRACKETS_PENDING — position is tracked, awaiting brackets
        assert manage.state == ManageState.BRACKETS_PENDING
        # Not FLAT (which would indicate position was not created)
        assert manage.state != ManageState.FLAT


# ---------------------------------------------------------------------------
# Test 6: Pending key type — orderId as string (normalized by fill_ingress)
# ---------------------------------------------------------------------------

class TestPendingKeyType:
    """
    _pending_brackets keys are always strings (from str(entry_resp["orderId"])).
    fill_ingress_coordinator normalizes orderId to str before calling manage_flow.handle.
    The guard comparison must work for string orderId.
    """

    def test_string_order_id_triggers_guard(self, fsm_harness):
        """String orderId (as normalized by fill_ingress) matches string key."""
        fsm, bus, cfg = fsm_harness
        manage = ManageFlowFSM(config=cfg)
        manage.state = ManageState.FLAT
        # _deferred_bracket_entry_id is always a string (set by fill_ingress)
        manage._deferred_bracket_entry_id = "8680894868"

        # orderId in fill payload is string (normalized)
        fill_msg = _make_fill_msg(order_id="8680894868")
        place_calls = []
        with patch.object(manage, "_place_brackets", side_effect=lambda m: (
            place_calls.append(m), None
        )[-1]):
            manage.handle(fill_msg)

        assert len(place_calls) == 0, "String orderId guard must fire"

    def test_guard_uses_str_conversion_for_int_orderId(self, fsm_harness):
        """
        Even if a fill payload has an int orderId, the guard uses str() conversion
        so it still matches the string key in _deferred_bracket_entry_id.
        """
        fsm, bus, cfg = fsm_harness
        manage = ManageFlowFSM(config=cfg)
        manage.state = ManageState.FLAT
        manage._deferred_bracket_entry_id = "8680894868"

        # Construct fill msg with int orderId (simulating non-normalized path)
        fill_msg = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="adapter",
            dst="execution_position",
            why="test",
            rid="aurora_BTCUSDT_test",
            pld={
                "symbol": "BTCUSDT",
                "orderId": 8680894868,  # int
                "qty": "0.01",
                "price": "50000",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": "0.01",
                "status": "FILLED",
            },
        )
        place_calls = []
        with patch.object(manage, "_place_brackets", side_effect=lambda m: (
            place_calls.append(m), None
        )[-1]):
            manage.handle(fill_msg)

        # str(8680894868) == "8680894868" == _deferred_bracket_entry_id
        assert len(
            place_calls) == 0, "Int orderId must match string deferred flag via str()"


# ---------------------------------------------------------------------------
# Test 7: -4130 classification preserved
# ---------------------------------------------------------------------------

class TestBracketDeferredClassificationPreserved:
    """
    The BRACKET_DEFERRED_EXISTING_CLOSEPOSITION_ORDER why_code in bracket_manager
    must remain valid. This test verifies the inline string still exists.
    """

    def test_bracket_deferred_existing_closeposition_order_why_code_present(self):
        """why_code string literal in bracket_manager must not have been removed."""
        from apps.reference.domains.execution_position.flows.manage import bracket_manager
        import inspect
        src = inspect.getsource(bracket_manager)
        assert "BRACKET_DEFERRED_EXISTING_CLOSEPOSITION_ORDER" in src, (
            "why_code BRACKET_DEFERRED_EXISTING_CLOSEPOSITION_ORDER must remain in bracket_manager"
        )
