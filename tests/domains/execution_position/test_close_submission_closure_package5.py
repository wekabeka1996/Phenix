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
from apps.reference.adapters.binance_adapter import BinanceAPIError


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


def _close_boundary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("source_fsm") == "CloseExecutor"
        and row.get("order_kind") == "CLOSE"
    ]


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
# Truth-gate seam tests
# ---------------------------------------------------------------------------


class TestCloseExecutorTruthGate:

    @pytest.mark.asyncio
    async def test_missing_symbol_successful_read_is_genuinely_flat(self) -> None:
        fsm, _ = _build_close_executor_fsm(position_amt=0.25, symbol="ETHUSDT")
        executor = CloseExecutor(fsm)

        resolution = await executor._resolve_close_position_truth(
            symbol="BTCUSDT",
        )

        assert resolution.classification.value == "GENUINELY_FLAT"
        assert resolution.position_amt == Decimal("0")
        assert resolution.reason == "missing_symbol"

    @pytest.mark.asyncio
    async def test_read_failure_is_position_truth_unresolved(self) -> None:
        fsm, _ = _build_close_executor_fsm(position_amt=0.25)
        fsm.adapter.get_open_positions.side_effect = RuntimeError("boom")
        executor = CloseExecutor(fsm)

        resolution = await executor._resolve_close_position_truth(
            symbol="BTCUSDT",
        )

        assert resolution.classification.value == "POSITION_TRUTH_UNRESOLVED"
        assert resolution.position_amt is None
        assert resolution.reason == "read_failed"

    @pytest.mark.asyncio
    async def test_present_symbol_is_submittable(self) -> None:
        fsm, _ = _build_close_executor_fsm(position_amt=0.25)
        executor = CloseExecutor(fsm)

        resolution = await executor._resolve_close_position_truth(
            symbol="BTCUSDT",
        )

        assert (
            resolution.classification.value
            == "POSITION_PRESENT_AND_SUBMITTABLE"
        )
        assert resolution.position_amt == Decimal("0.25")
        assert resolution.reason == "matched_live_position"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "open_positions, get_open_positions_side_effect, qty, expected_call_count",
        [
            (
                [{"symbol": "ETHUSDT", "positionAmt": "0.25"}],
                None,
                "0.04",
                0,
            ),
            (
                None,
                RuntimeError("boom"),
                "0.04",
                0,
            ),
            (
                [{"symbol": "BTCUSDT", "positionAmt": "0.25"}],
                None,
                "0.04",
                1,
            ),
        ],
    )
    async def test_only_present_submittable_reaches_typed_close_submission(
        self,
        open_positions: list[dict[str, str]] | None,
        get_open_positions_side_effect: Exception | None,
        qty: str,
        expected_call_count: int,
    ) -> None:
        fsm, place_close = _build_close_executor_fsm(position_amt=0.25)
        if get_open_positions_side_effect is None:
            fsm.adapter.get_open_positions = AsyncMock(
                return_value=list(open_positions or [])
            )
        else:
            fsm.adapter.get_open_positions.side_effect = (
                get_open_positions_side_effect
            )

        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(
            symbol="BTCUSDT",
            qty=qty,
            idempotent_key="GATE-1",
        )

        with patch.object(
            executor,
            "_build_close_submission",
            wraps=executor._build_close_submission,
        ) as wrapped:
            await executor.execute_close(decision)

        assert wrapped.call_count == expected_call_count
        assert place_close.await_count == expected_call_count

    @pytest.mark.asyncio
    async def test_full_close_preconditions_stay_outside_truth_helper(self) -> None:
        fsm, place_close = _build_close_executor_fsm(position_amt=0.25)
        manage = SimpleNamespace(
            _closing_position=False,
            _closing_position_ts=0.0,
        )
        fsm.manage_flows["BTCUSDT"] = manage

        def _read_positions() -> list[dict[str, str]]:
            assert manage._closing_position is True
            assert manage._closing_position_ts > 0.0
            return [{"symbol": "ETHUSDT", "positionAmt": "0.25"}]

        fsm.adapter.get_open_positions = AsyncMock(side_effect=_read_positions)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(symbol="BTCUSDT")

        with patch.object(
            executor,
            "_build_close_submission",
            wraps=executor._build_close_submission,
        ) as wrapped:
            await executor.execute_close(decision)

        assert wrapped.call_count == 0
        place_close.assert_not_awaited()
        assert manage._closing_position is False
        assert manage._closing_position_ts == 0.0

    @pytest.mark.asyncio
    async def test_full_close_read_failure_fails_closed_before_typed_submission(self) -> None:
        fsm, place_close = _build_close_executor_fsm(position_amt=0.25)
        manage = SimpleNamespace(
            _closing_position=False,
            _closing_position_ts=0.0,
        )
        fsm.manage_flows["BTCUSDT"] = manage
        fsm.adapter.get_open_positions = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(symbol="BTCUSDT")

        with patch.object(
            executor,
            "_build_close_submission",
            wraps=executor._build_close_submission,
        ) as wrapped, patch(
            "apps.reference.domains.execution_position.close_executor.order_logger.write"
        ) as order_log_write:
            await executor.execute_close(decision)

        assert wrapped.call_count == 0
        place_close.assert_not_awaited()
        order_log_write.assert_not_called()
        fsm._clear_symbol_brackets.assert_not_called()
        fsm._persist_restore_artifact_snapshot.assert_not_called()
        fsm.order_guardian.cleanup_orphans.assert_not_awaited()
        fsm.order_guardian.reconcile_symbol.assert_not_awaited()
        assert manage._closing_position is False
        assert manage._closing_position_ts == 0.0


# ---------------------------------------------------------------------------
# Executor wiring tests
# ---------------------------------------------------------------------------


class TestCloseExecutorFullCloseBranch:

    @pytest.mark.asyncio
    async def test_full_close_routes_through_typed_payload_to_adapter(self) -> None:
        fsm, place_close = _build_close_executor_fsm(position_amt=0.05)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(
            symbol="BTCUSDT",
            idempotent_key="FULL-1",
            data_ref=[
                "obs://execution_position/close_producer_bridge?contract=close_producer_bridge_v1&status=success",
            ],
        )
        records: list[dict[str, Any]] = []
        sequence: list[str] = []

        async def _capture_place(*args, **kwargs):
            sequence.append("adapter")
            return {"status": "NEW", "orderId": "close-123"}

        place_close.side_effect = _capture_place

        with patch(
            "apps.reference.domains.execution_position.close_executor."
            "CloseSubmissionPayload.from_dec_close",
            wraps=CloseSubmissionPayload.from_dec_close,
        ) as wrapped, patch(
            "apps.reference.domains.execution_position.close_executor.order_logger.write",
            side_effect=lambda entry: records.append(dict(entry)),
        ):
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

        boundary_rows = _close_boundary_rows(records)
        assert [row["event_type"] for row in boundary_rows] == [
            "ORDER_INTENT",
            "ORDER_PLACED",
        ]
        assert sequence == ["adapter"]
        assert boundary_rows[0]["metadata"]["trace_kind"] == "CLOSE_SUBMIT_ATTEMPT"
        assert "outcome" not in boundary_rows[0]["metadata"]
        assert boundary_rows[1]["metadata"]["trace_kind"] == "CLOSE_SUBMIT_OUTCOME"
        assert boundary_rows[1]["metadata"]["outcome"] == "submitted"
        assert boundary_rows[1]["adapter_response"]["orderId"] == "close-123"
        for row in boundary_rows:
            assert row["rid"] == decision.rid
            assert row["client_order_id"].startswith("CLOSE-")
            assert row["source_fsm"] == "CloseExecutor"
            assert row["order_kind"] == "CLOSE"
            assert list(row.get("data_ref") or []) == list(decision.data_ref)

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
            symbol="BTCUSDT",
            qty="0.04",
            idempotent_key="PART-1",
            data_ref=[
                "obs://execution_position/close_producer_bridge?contract=close_producer_bridge_v1&status=success",
            ],
        )
        records: list[dict[str, Any]] = []

        async def _capture_place(*args, **kwargs):
            return {"status": "NEW", "orderId": "close-partial-123"}

        place_close.side_effect = _capture_place

        with patch(
            "apps.reference.domains.execution_position.close_executor."
            "CloseSubmissionPayload.from_dec_close",
            wraps=CloseSubmissionPayload.from_dec_close,
        ) as wrapped, patch(
            "apps.reference.domains.execution_position.close_executor.order_logger.write",
            side_effect=lambda entry: records.append(dict(entry)),
        ):
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

        boundary_rows = _close_boundary_rows(records)
        assert [row["event_type"] for row in boundary_rows] == [
            "ORDER_INTENT",
            "ORDER_PLACED",
        ]
        assert boundary_rows[0]["metadata"]["partial_close"] is True
        assert boundary_rows[1]["metadata"]["partial_close"] is True
        assert boundary_rows[1]["metadata"]["outcome"] == "submitted"
        assert boundary_rows[1]["adapter_response"]["orderId"] == "close-partial-123"
        for row in boundary_rows:
            assert list(row.get("data_ref") or []) == list(decision.data_ref)

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
        ) as wrapped, patch(
            "apps.reference.domains.execution_position.close_executor.order_logger.write"
        ) as order_log_write:
            await executor.execute_close(decision)

        wrapped.assert_not_called()
        place_close.assert_not_awaited()
        order_log_write.assert_not_called()

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
        ), patch(
            "apps.reference.domains.execution_position.close_executor.order_logger.write"
        ) as order_log_write:
            await executor.execute_close(decision)

        place_close.assert_not_awaited()
        order_log_write.assert_not_called()
        reject_ref = build_close_submission_trace_ref(
            status="reject", partial_close=False, reason="adapter_validation"
        )
        assert reject_ref in list(decision.data_ref)

    @pytest.mark.asyncio
    async def test_adapter_exception_writes_seam_local_order_rejected_and_reraises(self) -> None:
        fsm, place_close = _build_close_executor_fsm(position_amt=0.05)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(
            symbol="BTCUSDT",
            idempotent_key="FAIL-1",
            data_ref=[
                "obs://execution_position/close_producer_bridge?contract=close_producer_bridge_v1&status=success",
            ],
        )
        records: list[dict[str, Any]] = []
        sequence: list[str] = []
        expected_error = RuntimeError("adapter boom")

        async def _raise_place(*args, **kwargs):
            sequence.append("adapter")
            raise expected_error

        place_close.side_effect = _raise_place

        with patch(
            "apps.reference.domains.execution_position.close_executor.order_logger.write",
            side_effect=lambda entry: records.append(dict(entry)),
        ):
            with pytest.raises(RuntimeError) as exc_info:
                await executor.execute_close(decision)

        assert exc_info.value is expected_error
        boundary_rows = _close_boundary_rows(records)
        assert [row["event_type"] for row in boundary_rows] == [
            "ORDER_INTENT",
            "ORDER_REJECTED",
        ]
        assert sequence == ["adapter"]
        assert boundary_rows[1]["metadata"]["trace_kind"] == "CLOSE_SUBMIT_OUTCOME"
        assert boundary_rows[1]["metadata"]["outcome"] == "rejected"
        assert boundary_rows[1]["metadata"]["exception_class"] == "RuntimeError"
        assert boundary_rows[1]["metadata"]["exception_message"] == "adapter boom"
        assert list(boundary_rows[1].get("data_ref")
                    or []) == list(decision.data_ref)

    @pytest.mark.asyncio
    async def test_duplicate_client_order_id_adapter_error_still_escapes_seam(self) -> None:
        fsm, place_close = _build_close_executor_fsm(position_amt=0.05)
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision(
            symbol="BTCUSDT",
            idempotent_key="DUP-1",
            data_ref=[
                "obs://execution_position/close_producer_bridge?contract=close_producer_bridge_v1&status=success",
            ],
        )
        records: list[dict[str, Any]] = []
        expected_error = BinanceAPIError(
            code=-4116,
            msg="Duplicate ClientOrderId",
        )

        async def _raise_place(*args, **kwargs):
            raise expected_error

        place_close.side_effect = _raise_place

        with patch(
            "apps.reference.domains.execution_position.close_executor.order_logger.write",
            side_effect=lambda entry: records.append(dict(entry)),
        ):
            with pytest.raises(BinanceAPIError) as exc_info:
                await executor.execute_close(decision)

        assert exc_info.value is expected_error
        boundary_rows = _close_boundary_rows(records)
        assert [row["event_type"] for row in boundary_rows] == [
            "ORDER_INTENT",
            "ORDER_REJECTED",
        ]
        assert boundary_rows[1]["metadata"]["trace_kind"] == "CLOSE_SUBMIT_OUTCOME"
        assert boundary_rows[1]["metadata"]["outcome"] == "rejected"
        assert boundary_rows[1]["metadata"]["exception_class"] == "BinanceAPIError"
        assert boundary_rows[1]["metadata"]["exchange_code"] == -4116
        assert list(boundary_rows[1].get("data_ref")
                    or []) == list(decision.data_ref)

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
