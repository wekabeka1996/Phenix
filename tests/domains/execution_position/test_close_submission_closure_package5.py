"""Phase 6 Package 5 — close submission seam closure tests.

Seam: ``DEC:CLOSE -> adapter.place_market_reduce_only``.

These tests prove that the typed :class:`CloseSubmissionPayload` is the
single runtime normalization owner of the close-submission boundary across
both partial-close and full-close branches, that the ad-hoc local
side/qty/client_order_id derivation no longer governs, and that
bracket teardown / reconcile / sidecar / exchange-position re-read ownership
is preserved.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.domains.execution_position.close_submission_adapter import (
    CLOSE_SUBMISSION_CONTRACT,
    CLOSE_SUBMISSION_PATH,
    CloseSubmissionAdapterError,
    CloseSubmissionPayload,
    build_close_submission_trace_ref,
)
from apps.reference.domains.execution_position.close_executor import CloseExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dec_close_decision(
    *,
    symbol: str = "BTCUSDT",
    qty: str | None = None,
    rid: str = "RID-CLOSE-1",
    idempotent_key: str | None = None,
    data_ref: list[str] | None = None,
) -> SimpleNamespace:
    pld: dict[str, Any] = {"symbol": symbol}
    if qty is not None:
        pld["qty"] = qty
    if idempotent_key is not None:
        pld["idempotent_key"] = idempotent_key
    return SimpleNamespace(
        op="DEC",
        verb="CLOSE",
        rid=rid,
        ts=0,
        pld=pld,
        data_ref=list(data_ref or []),
    )


def _build_close_executor_fsm(
    *,
    position_amt: float = 0.05,
    symbol: str = "BTCUSDT",
) -> tuple[SimpleNamespace, AsyncMock]:
    """Build a minimal fsm harness exercising only close-seam dependencies.

    Out-of-scope collaborators (reconcile, observability, sidecar, restore,
    bracket teardown) are stubbed as MagicMocks so the test asserts only the
    submission seam.
    """
    place_close = AsyncMock(return_value={"status": "NEW"})
    adapter = SimpleNamespace(
        get_open_positions=AsyncMock(
            return_value=[{"symbol": symbol, "positionAmt": str(position_amt)}]
        ),
        get_open_orders=AsyncMock(return_value=[]),
        place_market_reduce_only=place_close,
    )
    order_guardian = SimpleNamespace(
        reconcile_symbol=AsyncMock(return_value=None),
        cleanup_orphans=AsyncMock(return_value=None),
    )
    lifecycle_cfg = SimpleNamespace(
        fill_settlement_delay_ms=0,
        position_close_cleanup_delay_ms=0,
    )
    config = SimpleNamespace(
        domains=SimpleNamespace(
            execution_position=SimpleNamespace(order_lifecycle=lifecycle_cfg)
        )
    )
    fsm = SimpleNamespace(
        adapter=adapter,
        config=config,
        manage_flows={},
        _symbol_brackets={},
        order_guardian=order_guardian,
        _cancel_order=AsyncMock(return_value={"status": "CANCELED"}),
        _is_unknown_order_error=MagicMock(return_value=False),
        _is_cancel_success_response=MagicMock(return_value=True),
        _cancel_status_str=MagicMock(return_value="CANCELED"),
        _clear_symbol_brackets=MagicMock(),
        _persist_restore_artifact_snapshot=MagicMock(),
        _startup_truth_orchestrator=SimpleNamespace(
            _persist_restore_artifact_snapshot=MagicMock(),
        ),
        _emit_observability_event=MagicMock(),
        _emit_position_policy_close_request_state=MagicMock(),
        _orphan_metrics={"errors": 0, "reconcile_cancelled": 0},
    )
    return fsm, place_close


# ---------------------------------------------------------------------------
# Typed payload unit tests
# ---------------------------------------------------------------------------


class TestCloseSubmissionPayload:

    def test_full_close_long_derives_sell(self) -> None:
        payload = CloseSubmissionPayload.from_dec_close(
            symbol="BTCUSDT",
            position_amt=Decimal("0.1"),
            requested_qty=None,
            idempotent_key="K1",
        )
        assert payload.symbol == "BTCUSDT"
        assert payload.side == "SELL"
        assert payload.quantity == "0.1"
        assert payload.partial_close is False
        assert payload.client_order_id.startswith("CLOSE-")

    def test_full_close_short_derives_buy(self) -> None:
        payload = CloseSubmissionPayload.from_dec_close(
            symbol="ETHUSDT",
            position_amt=Decimal("-2.5"),
            requested_qty=None,
            idempotent_key="K2",
        )
        assert payload.side == "BUY"
        assert payload.quantity == "2.5"
        assert payload.partial_close is False

    def test_partial_close_when_requested_less_than_position(self) -> None:
        payload = CloseSubmissionPayload.from_dec_close(
            symbol="BTCUSDT",
            position_amt=Decimal("0.10"),
            requested_qty=Decimal("0.04"),
            idempotent_key="K3",
        )
        assert payload.side == "SELL"
        assert payload.quantity == "0.04"
        assert payload.partial_close is True

    def test_requested_equal_to_position_is_full_close(self) -> None:
        payload = CloseSubmissionPayload.from_dec_close(
            symbol="BTCUSDT",
            position_amt=Decimal("0.10"),
            requested_qty=Decimal("0.10"),
            idempotent_key="K4",
        )
        assert payload.partial_close is False
        assert payload.quantity == "0.10"

    def test_requested_larger_than_position_clamps_to_full(self) -> None:
        payload = CloseSubmissionPayload.from_dec_close(
            symbol="BTCUSDT",
            position_amt=Decimal("0.10"),
            requested_qty=Decimal("0.50"),
            idempotent_key="K5",
        )
        assert payload.partial_close is False
        assert payload.quantity == "0.10"

    def test_client_order_id_deterministic_from_idempotent_key(self) -> None:
        a = CloseSubmissionPayload.from_dec_close(
            symbol="BTCUSDT", position_amt=Decimal("0.1"),
            requested_qty=None, idempotent_key="STABLE",
        )
        b = CloseSubmissionPayload.from_dec_close(
            symbol="BTCUSDT", position_amt=Decimal("0.1"),
            requested_qty=None, idempotent_key="STABLE",
        )
        assert a.client_order_id == b.client_order_id
        c = CloseSubmissionPayload.from_dec_close(
            symbol="BTCUSDT", position_amt=Decimal("0.1"),
            requested_qty=None, idempotent_key="OTHER",
        )
        assert c.client_order_id != a.client_order_id

    def test_rejects_empty_symbol(self) -> None:
        with pytest.raises(CloseSubmissionAdapterError):
            CloseSubmissionPayload.from_dec_close(
                symbol="   ", position_amt=Decimal("0.1"),
                requested_qty=None, idempotent_key="K",
            )

    def test_rejects_zero_position(self) -> None:
        with pytest.raises(CloseSubmissionAdapterError):
            CloseSubmissionPayload.from_dec_close(
                symbol="BTCUSDT", position_amt=Decimal("0"),
                requested_qty=None, idempotent_key="K",
            )

    def test_rejects_non_positive_requested(self) -> None:
        with pytest.raises(CloseSubmissionAdapterError):
            CloseSubmissionPayload.from_dec_close(
                symbol="BTCUSDT", position_amt=Decimal("0.1"),
                requested_qty=Decimal("0"), idempotent_key="K",
            )

    def test_rejects_empty_idempotent_key(self) -> None:
        with pytest.raises(CloseSubmissionAdapterError):
            CloseSubmissionPayload.from_dec_close(
                symbol="BTCUSDT", position_amt=Decimal("0.1"),
                requested_qty=None, idempotent_key="",
            )

    def test_model_extra_forbid(self) -> None:
        with pytest.raises(Exception):
            CloseSubmissionPayload(  # type: ignore[call-arg]
                symbol="BTCUSDT", side="SELL", quantity="0.1",
                client_order_id="CLOSE-abc", partial_close=False, foo="bar",
            )


class TestCloseSubmissionTraceRef:

    def test_success_full_ref_shape(self) -> None:
        ref = build_close_submission_trace_ref(
            status="success", partial_close=False
        )
        assert ref.startswith("obs://execution_position/close_submission?")
        assert f"contract={CLOSE_SUBMISSION_CONTRACT}" in ref
        assert "path=DEC%3ACLOSE-%3Eadapter" in ref
        assert "status=success" in ref
        assert "partial=false" in ref
        assert "reason=" not in ref

    def test_success_partial_ref_shape(self) -> None:
        ref = build_close_submission_trace_ref(
            status="success", partial_close=True
        )
        assert "partial=true" in ref
        assert "status=success" in ref

    def test_reject_ref_carries_reason(self) -> None:
        ref = build_close_submission_trace_ref(
            status="reject", partial_close=False, reason="adapter_validation"
        )
        assert "status=reject" in ref
        assert "reason=adapter_validation" in ref


# ---------------------------------------------------------------------------
# Executor wiring tests
# ---------------------------------------------------------------------------


class TestCloseExecutorFullCloseBranch:

    @pytest.mark.asyncio
    async def test_full_close_routes_through_typed_payload_to_adapter(self) -> None:
        fsm, place_close = _build_close_executor_fsm(position_amt=0.05)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(
            symbol="BTCUSDT", idempotent_key="FULL-1"
        )

        with patch(
            "apps.reference.domains.execution_position.close_executor."
            "CloseSubmissionPayload.from_dec_close",
            wraps=CloseSubmissionPayload.from_dec_close,
        ) as wrapped:
            await executor.execute_close(decision)

        assert wrapped.call_count == 1
        place_close.assert_awaited_once()
        args, kwargs = place_close.await_args
        assert args[0] == "BTCUSDT"
        assert args[1] == "SELL"
        assert args[2] == "0.05"
        assert kwargs["new_client_order_id"].startswith("CLOSE-")

        success_ref = build_close_submission_trace_ref(
            status="success", partial_close=False
        )
        assert success_ref in list(decision.data_ref)

    @pytest.mark.asyncio
    async def test_full_close_short_position_derives_buy(self) -> None:
        fsm, place_close = _build_close_executor_fsm(
            position_amt=-0.2, symbol="ETHUSDT"
        )
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(
            symbol="ETHUSDT", idempotent_key="SHORT-1"
        )

        await executor.execute_close(decision)

        place_close.assert_awaited_once()
        args, _ = place_close.await_args
        assert args[1] == "BUY"
        assert args[2] == "0.2"


class TestCloseExecutorPartialCloseBranch:

    @pytest.mark.asyncio
    async def test_partial_close_routes_through_typed_payload(self) -> None:
        fsm, place_close = _build_close_executor_fsm(position_amt=0.10)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(
            symbol="BTCUSDT", qty="0.04", idempotent_key="PART-1"
        )

        with patch(
            "apps.reference.domains.execution_position.close_executor."
            "CloseSubmissionPayload.from_dec_close",
            wraps=CloseSubmissionPayload.from_dec_close,
        ) as wrapped:
            await executor.execute_close(decision)

        assert wrapped.call_count == 1
        place_close.assert_awaited_once()
        args, kwargs = place_close.await_args
        assert args == ("BTCUSDT", "SELL", "0.04")
        assert kwargs["new_client_order_id"].startswith("CLOSE-")

        success_ref = build_close_submission_trace_ref(
            status="success", partial_close=True
        )
        assert success_ref in list(decision.data_ref)
        # Reconcile collaborator still called on partial branch.
        fsm.order_guardian.reconcile_symbol.assert_awaited_once()
        # Partial branch does NOT trigger the full-branch restore persistence.
        fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_close_short_derives_buy_side(self) -> None:
        fsm, place_close = _build_close_executor_fsm(
            position_amt=-0.10, symbol="SOLUSDT"
        )
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(
            symbol="SOLUSDT", qty="0.03", idempotent_key="PART-SHORT"
        )

        await executor.execute_close(decision)

        place_close.assert_awaited_once()
        args, _ = place_close.await_args
        assert args == ("SOLUSDT", "BUY", "0.03")


class TestCloseExecutorFailClosed:

    @pytest.mark.asyncio
    async def test_full_close_with_zero_position_does_not_reach_seam(self) -> None:
        """Pre-existing executor logic returns early on zero position; the
        typed seam must not be invoked and the adapter must not be called.
        """
        fsm, place_close = _build_close_executor_fsm(position_amt=0.0)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(symbol="BTCUSDT")

        with patch(
            "apps.reference.domains.execution_position.close_executor."
            "CloseSubmissionPayload.from_dec_close",
            wraps=CloseSubmissionPayload.from_dec_close,
        ) as wrapped:
            await executor.execute_close(decision)

        wrapped.assert_not_called()
        place_close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_seam_reject_prevents_adapter_call_and_emits_reject_trace(self) -> None:
        """Force a typed-reject at the seam via ``from_dec_close`` raising,
        and prove the adapter is not invoked and the reject trace ref is
        attached to ``decision.data_ref``.
        """
        fsm, place_close = _build_close_executor_fsm(position_amt=0.05)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(
            symbol="BTCUSDT", idempotent_key="FORCE-REJ"
        )

        def _always_raise(**kwargs):
            raise CloseSubmissionAdapterError("forced reject for test")

        with patch(
            "apps.reference.domains.execution_position.close_executor."
            "CloseSubmissionPayload.from_dec_close",
            side_effect=_always_raise,
        ):
            await executor.execute_close(decision)

        place_close.assert_not_awaited()
        reject_ref = build_close_submission_trace_ref(
            status="reject", partial_close=False, reason="adapter_validation"
        )
        assert reject_ref in list(decision.data_ref)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("qty", ["not-a-number", "-0.01"])
    async def test_invalid_explicit_qty_rejects_before_adapter_call(self, qty: object) -> None:
        fsm, place_close = _build_close_executor_fsm(position_amt=0.05)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(
            symbol="BTCUSDT",
            qty=qty,  # type: ignore[arg-type]
            idempotent_key="BAD-QTY",
        )

        await executor.execute_close(decision)

        place_close.assert_not_awaited()
        reject_ref = build_close_submission_trace_ref(
            status="reject",
            partial_close=True,
            reason="invalid_requested_qty",
        )
        assert reject_ref in list(decision.data_ref)

    @pytest.mark.asyncio
    async def test_object_requested_qty_rejects_before_adapter_call(self) -> None:
        fsm, place_close = _build_close_executor_fsm(position_amt=0.05)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(
            symbol="BTCUSDT",
            qty=object(),  # type: ignore[arg-type]
            idempotent_key="OBJ-QTY",
        )

        await executor.execute_close(decision)

        place_close.assert_not_awaited()
        reject_ref = build_close_submission_trace_ref(
            status="reject",
            partial_close=True,
            reason="invalid_requested_qty",
        )
        assert reject_ref in list(decision.data_ref)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("qty", ["", "0", "0.0", "0.00", 0])
    async def test_zero_like_requested_qty_preserves_full_close_semantics(self, qty: object) -> None:
        fsm, place_close = _build_close_executor_fsm(position_amt=0.05)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(
            symbol="BTCUSDT",
            qty=qty,  # type: ignore[arg-type]
            idempotent_key="ZERO-LIKE",
        )

        await executor.execute_close(decision)

        place_close.assert_awaited_once()
        args, kwargs = place_close.await_args
        assert args == ("BTCUSDT", "SELL", "0.05")
        assert kwargs["new_client_order_id"].startswith("CLOSE-")


class TestCloseExecutorNonBypass:

    @pytest.mark.asyncio
    async def test_no_adapter_call_without_typed_construction_full_branch(self) -> None:
        fsm, place_close = _build_close_executor_fsm(position_amt=0.07)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(symbol="BTCUSDT")

        with patch(
            "apps.reference.domains.execution_position.close_executor."
            "CloseSubmissionPayload.from_dec_close",
            wraps=CloseSubmissionPayload.from_dec_close,
        ) as wrapped:
            await executor.execute_close(decision)

        assert wrapped.call_count == 1
        assert place_close.await_count == 1

    @pytest.mark.asyncio
    async def test_no_adapter_call_without_typed_construction_partial_branch(self) -> None:
        fsm, place_close = _build_close_executor_fsm(position_amt=0.10)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(symbol="BTCUSDT", qty="0.04")

        with patch(
            "apps.reference.domains.execution_position.close_executor."
            "CloseSubmissionPayload.from_dec_close",
            wraps=CloseSubmissionPayload.from_dec_close,
        ) as wrapped:
            await executor.execute_close(decision)

        assert wrapped.call_count == 1
        assert place_close.await_count == 1


class TestCloseExecutorTraces:

    @pytest.mark.asyncio
    async def test_success_full_log_line(self, caplog) -> None:
        fsm, _ = _build_close_executor_fsm(position_amt=0.1)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(symbol="BTCUSDT")

        with caplog.at_level("INFO"):
            await executor.execute_close(decision)

        messages = "\n".join(caplog.messages)
        assert "CLOSE_SUBMISSION_SUCCESS" in messages
        assert f"contract={CLOSE_SUBMISSION_CONTRACT}" in messages
        assert "partial=False" in messages

    @pytest.mark.asyncio
    async def test_success_partial_log_line(self, caplog) -> None:
        fsm, _ = _build_close_executor_fsm(position_amt=0.1)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(symbol="BTCUSDT", qty="0.04")

        with caplog.at_level("INFO"):
            await executor.execute_close(decision)

        messages = "\n".join(caplog.messages)
        assert "CLOSE_SUBMISSION_SUCCESS" in messages
        assert "partial=True" in messages


# ---------------------------------------------------------------------------
# Downstream ownership preservation (scope-discipline proof)
# ---------------------------------------------------------------------------


class TestDownstreamOwnershipUnchanged:

    def test_open_submission_payload_untouched(self) -> None:
        from apps.reference.domains.execution_position.open_submission_adapter import (
            OpenSubmissionPayload,
        )

        assert hasattr(OpenSubmissionPayload, "from_dec_open")
        assert hasattr(OpenSubmissionPayload, "from_dec_open_with_key")

    def test_cancel_submission_payload_untouched(self) -> None:
        from apps.reference.domains.execution_position.cancel_submission_adapter import (
            CancelSubmissionPayload,
        )

        assert hasattr(CancelSubmissionPayload, "from_dec_cancel")

    def test_idempotent_cancel_helper_unchanged(self) -> None:
        from apps.reference.domains.execution_position.idempotent_cancel import (
            IdempotentCancelHelper,
        )

        assert hasattr(IdempotentCancelHelper, "cancel_order_idempotent")

    def test_cancel_order_bridge_signature_unchanged(self) -> None:
        import inspect
        from apps.reference.domains.execution_position.fsm import ExecPosFSM

        sig = inspect.signature(ExecPosFSM._cancel_order)
        assert list(sig.parameters) == ["self", "symbol", "order_id"]

    def test_terminal_order_contracts_unchanged(self) -> None:
        from apps.reference.domains.execution_position import terminal_order_contracts

        assert hasattr(terminal_order_contracts,
                       "TERMINAL_NON_FILL_STATUS_MAP")
