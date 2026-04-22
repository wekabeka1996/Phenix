"""Phase 6 Package 7 - tracked full-close teardown seam closure tests.

Seam: ``DEC:CLOSE tracked bracket teardown -> internal typed bridge ->
DEC:CANCEL_ORDER -> Package 4 cancel intake``.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.domains.execution_position.cancel_submission_adapter import (
    CancelSubmissionPayload,
)
from apps.reference.domains.execution_position.close_submission_adapter import (
    CLOSE_SUBMISSION_CONTRACT,
    CloseSubmissionPayload,
)
from apps.reference.domains.execution_position.close_executor import CloseExecutor
from apps.reference.domains.execution_position.tracked_close_teardown_cancel_bridge import (
    TRACKED_CLOSE_TEARDOWN_CANCEL_CONTRACT,
    TrackedCloseTeardownCancelBridgeError,
    TrackedCloseTeardownCancelRequest,
    adapt_tracked_close_teardown_to_dec_cancel,
)


def _dec_close_decision(
    *,
    symbol: str = "BTCUSDT",
    rid: str = "RID-CLOSE-PKG7",
    idempotent_key: str | None = "FULL-PKG7",
    data_ref: list[str] | None = None,
) -> SimpleNamespace:
    pld: dict[str, Any] = {"symbol": symbol}
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
    open_orders: list[Any] | None = None,
) -> tuple[SimpleNamespace, AsyncMock]:
    place_close = AsyncMock(return_value={"status": "NEW"})
    adapter = SimpleNamespace(
        get_open_positions=AsyncMock(
            return_value=[{"symbol": symbol, "positionAmt": str(position_amt)}]
        ),
        get_open_orders=AsyncMock(return_value=list(open_orders or [])),
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
        _emit_observability_event=MagicMock(),
        _emit_position_policy_close_request_state=MagicMock(),
        _orphan_metrics={"errors": 0, "reconcile_cancelled": 0},
    )
    return fsm, place_close


class TestTrackedCloseTeardownBridge:

    def test_package4_cancel_intake_accepts_tracked_teardown_context(self) -> None:
        payload = CancelSubmissionPayload.from_dec_cancel(
            payload={
                "symbol": "BTCUSDT",
                "order_id": "sl-123",
                "bracket_type": "SL",
                "trigger": "DEC:CLOSE:tracked_bracket_teardown",
            }
        )
        assert payload.symbol == "BTCUSDT"
        assert payload.order_id == "sl-123"

    def test_bridge_builds_canonical_cancel_decision_for_sl(self) -> None:
        close_decision = _dec_close_decision(symbol="BTCUSDT", rid="RID-SL")

        request, cancel_decision = adapt_tracked_close_teardown_to_dec_cancel(
            close_decision,
            symbol="BTCUSDT",
            order_id="sl-123",
            bracket_type="SL",
        )

        assert request == TrackedCloseTeardownCancelRequest(
            symbol="BTCUSDT",
            order_id="sl-123",
            bracket_type="SL",
            close_rid="RID-SL",
        )
        assert cancel_decision.verb == "CANCEL_ORDER"
        assert cancel_decision.pld["symbol"] == "BTCUSDT"
        assert cancel_decision.pld["order_id"] == "sl-123"
        assert cancel_decision.pld["bracket_type"] == "SL"
        assert cancel_decision.idempotent_key == "RID-SL:tracked_close_teardown:SL:sl-123"
        assert any(
            f"contract={TRACKED_CLOSE_TEARDOWN_CANCEL_CONTRACT}" in ref
            for ref in (cancel_decision.data_ref or [])
        )

    def test_bridge_rejects_empty_tracked_order_id(self) -> None:
        with pytest.raises(TrackedCloseTeardownCancelBridgeError):
            adapt_tracked_close_teardown_to_dec_cancel(
                _dec_close_decision(),
                symbol="BTCUSDT",
                order_id="",
                bracket_type="TP",
            )


class TestTrackedCloseTeardownRouting:

    @pytest.mark.asyncio
    async def test_tracked_sl_routes_through_execute_cancel_order_and_package4(self) -> None:
        fsm, place_close = _build_close_executor_fsm()
        fsm._symbol_brackets["BTCUSDT"] = {"sl_order_id": "sl-1"}
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision()

        with patch.object(
            executor,
            "execute_cancel_order",
            wraps=executor.execute_cancel_order,
        ) as cancel_wrapped, patch(
            "apps.reference.domains.execution_position.close_executor."
            "CancelSubmissionPayload.from_dec_cancel",
            wraps=CancelSubmissionPayload.from_dec_cancel,
        ) as package4_wrapped:
            await executor.execute_close(decision)

        assert cancel_wrapped.await_count == 1
        cancel_decision = cancel_wrapped.await_args.args[0]
        assert cancel_decision.verb == "CANCEL_ORDER"
        assert cancel_decision.pld["order_id"] == "sl-1"
        assert cancel_decision.pld["bracket_type"] == "SL"
        assert package4_wrapped.call_count == 1
        assert fsm._cancel_order.await_count == 1
        place_close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tracked_tp_routes_through_execute_cancel_order_and_package4(self) -> None:
        fsm, _ = _build_close_executor_fsm()
        fsm._symbol_brackets["BTCUSDT"] = {"tp_order_id": "tp-1"}
        executor = CloseExecutor(fsm)

        with patch.object(
            executor,
            "execute_cancel_order",
            wraps=executor.execute_cancel_order,
        ) as cancel_wrapped, patch(
            "apps.reference.domains.execution_position.close_executor."
            "CancelSubmissionPayload.from_dec_cancel",
            wraps=CancelSubmissionPayload.from_dec_cancel,
        ) as package4_wrapped:
            await executor.execute_close(_dec_close_decision())

        assert cancel_wrapped.await_count == 1
        cancel_decision = cancel_wrapped.await_args.args[0]
        assert cancel_decision.pld["order_id"] == "tp-1"
        assert cancel_decision.pld["bracket_type"] == "TP"
        assert package4_wrapped.call_count == 1

    @pytest.mark.asyncio
    async def test_each_tracked_order_id_traverses_typed_cancel_seam_exactly_once(self) -> None:
        fsm, _ = _build_close_executor_fsm()
        fsm._symbol_brackets["BTCUSDT"] = {
            "sl_order_id": "sl-1",
            "tp_order_id": "tp-1",
        }
        executor = CloseExecutor(fsm)

        with patch.object(
            executor,
            "execute_cancel_order",
            wraps=executor.execute_cancel_order,
        ) as cancel_wrapped, patch(
            "apps.reference.domains.execution_position.close_executor."
            "CancelSubmissionPayload.from_dec_cancel",
            wraps=CancelSubmissionPayload.from_dec_cancel,
        ) as package4_wrapped:
            await executor.execute_close(_dec_close_decision())

        assert cancel_wrapped.await_count == 2
        assert package4_wrapped.call_count == 2
        seen = [call.args[0].pld["order_id"] for call in cancel_wrapped.await_args_list]
        assert seen == ["sl-1", "tp-1"]

    @pytest.mark.asyncio
    async def test_tracked_teardown_segment_no_longer_uses_raw_cancel_when_execute_cancel_order_is_intercepted(self) -> None:
        fsm, place_close = _build_close_executor_fsm()
        fsm._symbol_brackets["BTCUSDT"] = {
            "sl_order_id": "sl-1",
            "tp_order_id": "tp-1",
        }
        executor = CloseExecutor(fsm)

        with patch.object(
            executor,
            "execute_cancel_order",
            new=AsyncMock(return_value={"status": "CANCELED"}),
        ) as cancel_mock:
            await executor.execute_close(_dec_close_decision())

        assert cancel_mock.await_count == 2
        fsm._cancel_order.assert_not_awaited()
        place_close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_full_close_submission_still_occurs_unchanged_with_tracked_teardown(self) -> None:
        fsm, place_close = _build_close_executor_fsm(position_amt=0.05)
        fsm._symbol_brackets["BTCUSDT"] = {
            "sl_order_id": "sl-1",
            "tp_order_id": "tp-1",
        }
        executor = CloseExecutor(fsm)
        decision = _dec_close_decision()

        with patch(
            "apps.reference.domains.execution_position.close_executor."
            "CloseSubmissionPayload.from_dec_close",
            wraps=CloseSubmissionPayload.from_dec_close,
        ) as close_wrapped:
            await executor.execute_close(decision)

        assert close_wrapped.call_count == 1
        place_close.assert_awaited_once()
        args, kwargs = place_close.await_args
        assert args == ("BTCUSDT", "SELL", "0.05")
        assert kwargs["new_client_order_id"].startswith("CLOSE-")
        assert any(
            f"contract={CLOSE_SUBMISSION_CONTRACT}" in ref
            for ref in (decision.data_ref or [])
        )

    @pytest.mark.asyncio
    async def test_second_pass_reconcile_scan_is_distinct_from_tracked_teardown(self) -> None:
        open_order = {
            "orderId": "leftover-1",
            "type": "STOP_MARKET",
            "reduceOnly": True,
        }
        fsm, _ = _build_close_executor_fsm(open_orders=[open_order])
        fsm._symbol_brackets["BTCUSDT"] = {"sl_order_id": "sl-1"}
        executor = CloseExecutor(fsm)

        with patch.object(
            executor,
            "execute_cancel_order",
            wraps=executor.execute_cancel_order,
        ) as cancel_wrapped:
            await executor.execute_close(_dec_close_decision())

        assert cancel_wrapped.await_count == 2
        seen = [call.args[0].pld["order_id"] for call in cancel_wrapped.await_args_list]
        assert seen == ["sl-1", "leftover-1"]
        triggers = [call.args[0].pld["trigger"] for call in cancel_wrapped.await_args_list]
        assert triggers == [
            "DEC:CLOSE:tracked_bracket_teardown",
            "DEC:CLOSE:reconcile_scan_cancel",
        ]
