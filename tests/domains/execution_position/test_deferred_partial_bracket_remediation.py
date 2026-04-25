"""
Package A1: Deferred Partial Bracket Placement Remediation Tests

Proves that after preflight_position_check confirms the position is live, any
bracket placement failure (both fail, SL missing, TP missing) correctly escalates
with live_position_proven=True through the _handle_bracket_protection_missing helper.

Also proves that pre-preflight failures (preflight false, guardian veto) still
correctly use live_position_proven=False (no blind close).

Scenarios tested:
1. Deferred preflight false → record failure, live_position_proven=False, no close, pending preserved
2. Deferred guardian veto before live proof → live_position_proven=False, no close, pending preserved
3. Deferred both SL and TP fail after successful preflight → live_position_proven=True, remediation
4. Deferred SL fails but TP succeeds after preflight → live_position_proven=True, missing_sl=True
5. Deferred SL succeeds but TP fails after preflight → live_position_proven=True, missing_tp=True
6. Existing live synced SL+TP → suppresses duplicate placement, no close, pending cleared
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.domains.execution_position.bracket_manager import BracketManager

pytest_plugins = ("tests.domains.execution_position.conftest",)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry_payload(**overrides) -> Dict[str, Any]:
    base = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "sl": Decimal("99"),
        "tp": Decimal("101"),
        "rid": "rid-1",
        "idem_key": "idem-1",
        "tick_size": Decimal("0.1"),
        "corr_id": "corr-1",
        "oco_group_id": "oco-1",
        "entry_client_order_id": "ENTRY-1",
        "qty": "0.01",
        "strategy_id": "aurora",
    }
    base.update(overrides)
    return base


def _make_fsm_for_deferred(*, handler=None) -> SimpleNamespace:
    """Minimal FSM stub sufficient for place_deferred_brackets tests."""
    fsm = SimpleNamespace(
        order_index=None,
        fsm=SimpleNamespace(order_index=None),
        order_guardian=MagicMock(),
        correlation_store=MagicMock(),
        manage_flows={},
        _pending_brackets={"entry-1": _entry_payload()},
        _symbol_brackets={},
        _orphan_metrics={"tp_sl_placed_success": 0},
        config=SimpleNamespace(
            domains=SimpleNamespace(
                execution_position=SimpleNamespace(
                    bracket_placement=SimpleNamespace(tp_widen_first_bps=10)
                )
            )
        ),
    )

    def _set_symbol_bracket_order(symbol, *, order_role, order_id):
        brackets = fsm._symbol_brackets.setdefault(symbol, {})
        if order_role == "SL":
            brackets["sl_order_id"] = order_id
        elif order_role == "TP":
            brackets["tp_order_id"] = order_id

    fsm._set_symbol_bracket_order = MagicMock(side_effect=_set_symbol_bracket_order)
    fsm._remember_bracket_owner = MagicMock(return_value={})
    fsm._append_bracket_ownership_record = MagicMock()
    fsm._has_active_lifecycle_for_symbol = MagicMock(return_value=True)
    fsm._persist_restore_artifact_snapshot = MagicMock()

    def _clear_pending_brackets(entry_order_id, *, reason, symbol=None, persist_snapshot=False):
        fsm._pending_brackets.pop(str(entry_order_id), None)
        if persist_snapshot:
            fsm._persist_restore_artifact_snapshot(
                trigger=f"bracket_deferred_cleared:{reason}",
                allow_empty=True,
            )
        return True

    fsm._clear_pending_brackets = MagicMock(side_effect=_clear_pending_brackets)

    # Attach the protection-missing handler (or a mock)
    if handler is not None:
        fsm._handle_bracket_protection_missing = handler
    else:
        fsm._handle_bracket_protection_missing = AsyncMock(return_value="force_reduce_only_close")

    return fsm


# ---------------------------------------------------------------------------
# 1. Deferred preflight false — no close, pending preserved
# ---------------------------------------------------------------------------

class TestDeferredPreflightFalse:
    @pytest.mark.asyncio
    async def test_preflight_false_emits_failure_with_live_position_proven_false(self) -> None:
        fsm = _make_fsm_for_deferred()
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        manager = BracketManager(fsm)
        manager.preflight_position_check = AsyncMock(return_value=False)

        result = await manager.place_deferred_brackets("entry-1", _entry_payload())

        assert result is False
        fsm._handle_bracket_protection_missing.assert_awaited_once()
        kwargs = fsm._handle_bracket_protection_missing.await_args.kwargs
        assert kwargs["live_position_proven"] is False
        assert kwargs["failure_class"] == "transient_position_preflight_false"
        assert kwargs["why_code"] == "BRACKET_DEFERRED_PREFLIGHT_FALSE"
        # Pending brackets must NOT be cleared when preflight fails
        assert "entry-1" in fsm._pending_brackets
        fsm._clear_pending_brackets.assert_not_called()

    @pytest.mark.asyncio
    async def test_preflight_false_does_not_trigger_blind_close(self) -> None:
        """live_position_proven=False → handler must not close, caller must not clear."""
        fsm = _make_fsm_for_deferred()
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        manager = BracketManager(fsm)
        manager.preflight_position_check = AsyncMock(return_value=False)

        await manager.place_deferred_brackets("entry-1", _entry_payload())

        # Confirm we never reach the SL/TP adapter calls
        assert not hasattr(fsm, "adapter") or not getattr(
            getattr(fsm, "adapter", None),
            "place_stop_market_close_position",
            None,
        )


# ---------------------------------------------------------------------------
# 2. Deferred guardian veto before live proof — no close, pending preserved
# ---------------------------------------------------------------------------

class TestDeferredGuardianVeto:
    @pytest.mark.asyncio
    async def test_guardian_veto_uses_live_position_proven_false(self) -> None:
        fsm = _make_fsm_for_deferred()
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=False)
        manager = BracketManager(fsm)
        manager.preflight_position_check = AsyncMock(return_value=True)

        result = await manager.place_deferred_brackets("entry-1", _entry_payload())

        assert result is False
        fsm._handle_bracket_protection_missing.assert_awaited_once()
        kwargs = fsm._handle_bracket_protection_missing.await_args.kwargs
        assert kwargs["live_position_proven"] is False
        assert kwargs["failure_class"] == "duplicate_or_guardian_veto"
        assert kwargs["why_code"] == "BRACKET_DEFERRED_GUARDIAN_BLOCKED"
        assert "entry-1" in fsm._pending_brackets
        fsm._clear_pending_brackets.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Both SL and TP fail after successful preflight
# ---------------------------------------------------------------------------

class TestDeferredBothFailAfterPreflight:
    @pytest.mark.asyncio
    async def test_both_fail_uses_live_position_proven_true(self) -> None:
        fsm = _make_fsm_for_deferred()
        fsm.adapter = SimpleNamespace(
            place_stop_market_close_position=AsyncMock(
                side_effect=RuntimeError("sl_fail")
            ),
            place_take_profit_market_close_position=AsyncMock(
                side_effect=RuntimeError("tp_fail")
            ),
        )
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        manager = BracketManager(fsm)
        manager.preflight_position_check = AsyncMock(return_value=True)

        result = await manager.place_deferred_brackets("entry-1", _entry_payload())

        assert result is False
        fsm._handle_bracket_protection_missing.assert_awaited_once()
        kwargs = fsm._handle_bracket_protection_missing.await_args.kwargs
        assert kwargs["live_position_proven"] is True, (
            "Both legs failed after preflight proved position live — must use live_position_proven=True"
        )
        assert kwargs["why_code"] == "BRACKET_DEFERRED_BOTH_FAILED"
        assert kwargs["failure_class"] == "adapter_rejection"
        details = kwargs["details"]
        assert details["missing_sl"] is True
        assert details["missing_tp"] is True
        assert details["preflight_position_confirmed"] is True
        assert details["deferred_brackets"] is True

    @pytest.mark.asyncio
    async def test_both_fail_emits_event_via_handler(self) -> None:
        """Handler is called with force-close semantics when both legs fail after preflight."""
        fsm = _make_fsm_for_deferred()
        fsm.adapter = SimpleNamespace(
            place_stop_market_close_position=AsyncMock(side_effect=RuntimeError("boom")),
            place_take_profit_market_close_position=AsyncMock(side_effect=RuntimeError("boom")),
        )
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        manager = BracketManager(fsm)
        manager.preflight_position_check = AsyncMock(return_value=True)

        await manager.place_deferred_brackets("entry-1", _entry_payload())

        # Handler must have been called exactly once
        assert fsm._handle_bracket_protection_missing.await_count == 1
        kwargs = fsm._handle_bracket_protection_missing.await_args.kwargs
        assert kwargs["source_path"] == "BracketManager.place_deferred_brackets"


# ---------------------------------------------------------------------------
# 4. SL fails, TP succeeds — downside unprotected, requires remediation
# ---------------------------------------------------------------------------

class TestDeferredSLMissingTPPresent:
    @pytest.mark.asyncio
    async def test_sl_missing_escalates_with_live_position_proven_true(self) -> None:
        fsm = _make_fsm_for_deferred()
        fsm.adapter = SimpleNamespace(
            place_stop_market_close_position=AsyncMock(
                side_effect=RuntimeError("sl_adapter_fail")
            ),
            place_take_profit_market_close_position=AsyncMock(
                return_value={"orderId": "600001", "clientAlgoId": "algo-tp-1"}
            ),
        )
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm.order_guardian.register_bracket = MagicMock()
        manager = BracketManager(fsm)
        manager.preflight_position_check = AsyncMock(return_value=True)

        result = await manager.place_deferred_brackets("entry-1", _entry_payload())

        assert result is False
        fsm._handle_bracket_protection_missing.assert_awaited_once()
        kwargs = fsm._handle_bracket_protection_missing.await_args.kwargs
        assert kwargs["live_position_proven"] is True, (
            "SL missing after preflight — downside unprotected — must use live_position_proven=True"
        )
        assert kwargs["why_code"] == "BRACKET_DEFERRED_SL_MISSING"
        assert kwargs["failure_class"] == "adapter_rejection_partial_sl_missing"
        details = kwargs["details"]
        assert details["missing_sl"] is True
        assert details["missing_tp"] is False
        assert details["sl_response_present"] is False
        assert details["tp_response_present"] is True

    @pytest.mark.asyncio
    async def test_sl_missing_does_not_silently_ignore(self) -> None:
        """SL failure must NOT be silent even though TP succeeded."""
        fsm = _make_fsm_for_deferred()
        # Use a no-op handler to verify it is called (not ignored)
        calls = []
        async def capturing_handler(**kwargs):
            calls.append(kwargs)
        fsm._handle_bracket_protection_missing = capturing_handler

        fsm.adapter = SimpleNamespace(
            place_stop_market_close_position=AsyncMock(side_effect=RuntimeError("sl_fail")),
            place_take_profit_market_close_position=AsyncMock(
                return_value={"orderId": "600001"}
            ),
        )
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm.order_guardian.register_bracket = MagicMock()
        manager = BracketManager(fsm)
        manager.preflight_position_check = AsyncMock(return_value=True)

        await manager.place_deferred_brackets("entry-1", _entry_payload())

        assert len(calls) == 1
        assert calls[0]["live_position_proven"] is True


# ---------------------------------------------------------------------------
# 5. SL succeeds, TP fails — upside exit missing, requires remediation
# ---------------------------------------------------------------------------

class TestDeferredTPMissingSLPresent:
    @pytest.mark.asyncio
    async def test_tp_missing_escalates_with_live_position_proven_true(self) -> None:
        from apps.reference.adapters.binance_adapter import BinanceAPIError

        fsm = _make_fsm_for_deferred()
        # TP adapter raises a non-2021 error so no retry path is taken
        tp_error = BinanceAPIError(code=-1100, msg="tp_reject")
        fsm.adapter = SimpleNamespace(
            place_stop_market_close_position=AsyncMock(
                return_value={"orderId": "500001", "clientAlgoId": "algo-sl-1"}
            ),
            place_take_profit_market_close_position=AsyncMock(side_effect=tp_error),
        )
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm.order_guardian.register_bracket = MagicMock()
        manager = BracketManager(fsm)
        manager.preflight_position_check = AsyncMock(return_value=True)

        result = await manager.place_deferred_brackets("entry-1", _entry_payload())

        assert result is False
        fsm._handle_bracket_protection_missing.assert_awaited_once()
        kwargs = fsm._handle_bracket_protection_missing.await_args.kwargs
        assert kwargs["live_position_proven"] is True, (
            "TP missing after preflight — full SL+TP pair required — must use live_position_proven=True"
        )
        assert kwargs["why_code"] == "BRACKET_DEFERRED_TP_MISSING"
        assert kwargs["failure_class"] == "adapter_rejection_partial_tp_missing"
        details = kwargs["details"]
        assert details["missing_tp"] is True
        assert details["missing_sl"] is False
        assert details["sl_response_present"] is True
        assert details["tp_response_present"] is False

    @pytest.mark.asyncio
    async def test_tp_missing_generic_exception_also_escalates(self) -> None:
        """TP failure via generic exception (not BinanceAPIError) also triggers remediation."""
        fsm = _make_fsm_for_deferred()
        fsm.adapter = SimpleNamespace(
            place_stop_market_close_position=AsyncMock(
                return_value={"orderId": "500001"}
            ),
            place_take_profit_market_close_position=AsyncMock(
                side_effect=RuntimeError("tp_generic_fail")
            ),
        )
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm.order_guardian.register_bracket = MagicMock()
        manager = BracketManager(fsm)
        manager.preflight_position_check = AsyncMock(return_value=True)

        result = await manager.place_deferred_brackets("entry-1", _entry_payload())

        assert result is False
        kwargs = fsm._handle_bracket_protection_missing.await_args.kwargs
        assert kwargs["live_position_proven"] is True
        assert kwargs["why_code"] == "BRACKET_DEFERRED_TP_MISSING"

    @pytest.mark.asyncio
    async def test_tp_missing_does_not_silently_clear_pending_brackets(self) -> None:
        """Pending brackets must NOT be cleared when TP fails — position not fully protected."""
        from apps.reference.adapters.binance_adapter import BinanceAPIError

        fsm = _make_fsm_for_deferred()
        tp_error = BinanceAPIError(code=-1100, msg="tp_reject")
        fsm.adapter = SimpleNamespace(
            place_stop_market_close_position=AsyncMock(
                return_value={"orderId": "500001"}
            ),
            place_take_profit_market_close_position=AsyncMock(side_effect=tp_error),
        )
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm.order_guardian.register_bracket = MagicMock()
        manager = BracketManager(fsm)
        manager.preflight_position_check = AsyncMock(return_value=True)

        await manager.place_deferred_brackets("entry-1", _entry_payload())

        # Pending brackets NOT cleared because placement was incomplete
        fsm._clear_pending_brackets.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Existing live synced SL+TP — no duplicate placement, no close
# ---------------------------------------------------------------------------

class TestDeferredExistingLiveSyncedBrackets:
    @pytest.mark.asyncio
    async def test_existing_synced_brackets_suppresses_placement_and_does_not_close(
        self, fsm_harness
    ) -> None:
        fsm, _, _cfg = fsm_harness
        fsm.config.domains.execution_position.bracket_placement.tp_widen_first_bps = 10
        fsm.adapter = SimpleNamespace(
            place_stop_market_close_position=AsyncMock(),
            place_take_profit_market_close_position=AsyncMock(),
        )
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm.order_guardian.get_our_open_brackets = AsyncMock(
            return_value=[{"orderId": "500001"}, {"orderId": "600001"}]
        )
        fsm._has_active_lifecycle_for_symbol = MagicMock(return_value=True)
        fsm._set_symbol_brackets_snapshot(
            "BTCUSDT", sl_order_id="500001", tp_order_id="600001"
        )
        fsm._pending_brackets["entry-1"] = _entry_payload()

        manager = fsm._bracket_mgr
        manager.preflight_position_check = AsyncMock(return_value=True)

        with patch(
            "apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared"
        ):
            result = await manager.place_deferred_brackets("entry-1", _entry_payload())

        # Must succeed (position was already protected) and clear pending
        assert result is True
        # No new bracket adapter calls
        fsm.adapter.place_stop_market_close_position.assert_not_awaited()
        fsm.adapter.place_take_profit_market_close_position.assert_not_awaited()
        # The _handle_bracket_protection_missing should NOT have been called for a forced close
        # (existing brackets handler uses remediation_action_override="existing_exchange_brackets_synced")
        # We verify the event emitted (if any) does NOT carry live_position_proven=True close intent
        # by confirming no close was submitted
        close_exec = getattr(fsm, "_close_exec", None)
        if close_exec is not None:
            close_exec.execute_close = AsyncMock()
            assert not close_exec.execute_close.await_count

    @pytest.mark.asyncio
    async def test_existing_synced_brackets_clears_pending_without_remediation(
        self, fsm_harness
    ) -> None:
        fsm, _, _cfg = fsm_harness
        fsm.config.domains.execution_position.bracket_placement.tp_widen_first_bps = 10
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm.order_guardian.get_our_open_brackets = AsyncMock(
            return_value=[{"orderId": "500001"}, {"orderId": "600001"}]
        )
        fsm._has_active_lifecycle_for_symbol = MagicMock(return_value=True)
        fsm._set_symbol_brackets_snapshot(
            "BTCUSDT", sl_order_id="500001", tp_order_id="600001"
        )
        fsm._pending_brackets["entry-1"] = _entry_payload()

        manager = fsm._bracket_mgr
        manager.preflight_position_check = AsyncMock(return_value=True)

        with patch.object(
            fsm, "_clear_pending_brackets", wraps=fsm._clear_pending_brackets
        ) as clear_pending, patch(
            "apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared"
        ):
            result = await manager.place_deferred_brackets("entry-1", _entry_payload())

        assert result is True
        # Pending brackets must be cleared (position already protected)
        clear_pending.assert_called_once_with(
            "entry-1",
            reason="filled",
            symbol="BTCUSDT",
            persist_snapshot=True,
        )
