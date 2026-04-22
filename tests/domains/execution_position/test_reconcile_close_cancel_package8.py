"""Phase 6 Package 8 - executor second-pass reconcile cancel seam closure tests.

Seam: ``DEC:CLOSE second-pass reconcile scan -> internal typed bridge ->
DEC:CANCEL_ORDER -> Package 4 cancel intake``.
"""

from __future__ import annotations

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
from apps.reference.domains.execution_position.reconcile_close_cancel_bridge import (
    RECONCILE_CLOSE_CANCEL_CONTRACT,
    RECONCILE_CLOSE_CANCEL_TRIGGER,
    ReconcileCloseCancelBridgeError,
    ReconcileCloseCancelRequest,
    adapt_reconcile_close_to_dec_cancel,
)


def _dec_close_decision(
    *,
    symbol: str = "BTCUSDT",
    rid: str = "RID-CLOSE-PKG8",
    idempotent_key: str | None = "FULL-PKG8",
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


class TestReconcileCloseCancelBridge:

    def test_package4_cancel_intake_accepts_reconcile_context(self) -> None:
        payload = CancelSubmissionPayload.from_dec_cancel(
            payload={
                "symbol": "BTCUSDT",
                "order_id": "ord-123",
                "order_type": "STOP_MARKET",
                "trigger": RECONCILE_CLOSE_CANCEL_TRIGGER,
            }
        )
        assert payload.symbol == "BTCUSDT"
        assert payload.order_id == "ord-123"

    def test_bridge_builds_canonical_cancel_decision_for_discovered_order(self) -> None:
        request, cancel_decision = adapt_reconcile_close_to_dec_cancel(
            _dec_close_decision(rid="RID-REC-1"),
            symbol="BTCUSDT",
            order_id="ord-123",
            order_type="STOP_MARKET",
        )

        assert request == ReconcileCloseCancelRequest(
            symbol="BTCUSDT",
            order_id="ord-123",
            order_type="STOP_MARKET",
            close_rid="RID-REC-1",
        )
        assert cancel_decision.verb == "CANCEL_ORDER"
        assert cancel_decision.pld["symbol"] == "BTCUSDT"
        assert cancel_decision.pld["order_id"] == "ord-123"
        assert cancel_decision.pld["order_type"] == "STOP_MARKET"
        assert cancel_decision.pld["trigger"] == RECONCILE_CLOSE_CANCEL_TRIGGER
        assert cancel_decision.idempotent_key == "RID-REC-1:reconcile_close_cancel:STOP_MARKET:ord-123"
        assert any(
            f"contract={RECONCILE_CLOSE_CANCEL_CONTRACT}" in ref
            for ref in (cancel_decision.data_ref or [])
        )

    def test_bridge_rejects_missing_discovered_order_id(self) -> None:
        with pytest.raises(ReconcileCloseCancelBridgeError):
            adapt_reconcile_close_to_dec_cancel(
                _dec_close_decision(),
                symbol="BTCUSDT",
                order_id="",
                order_type="LIMIT",
            )


class TestReconcileCloseCancelRouting:

    @pytest.mark.asyncio
    async def test_discovered_reconcile_order_routes_through_execute_cancel_order_and_package4(self) -> None:
        open_order = {"orderId": "leftover-1", "type": "STOP_MARKET", "reduceOnly": True}
        fsm, place_close = _build_close_executor_fsm(open_orders=[open_order])
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
        assert cancel_decision.pld["order_id"] == "leftover-1"
        assert cancel_decision.pld["order_type"] == "STOP_MARKET"
        assert cancel_decision.pld["trigger"] == RECONCILE_CLOSE_CANCEL_TRIGGER
        assert package4_wrapped.call_count == 1
        assert fsm._cancel_order.await_count == 1
        place_close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_discovered_orders_each_traverse_typed_cancel_seam_exactly_once(self) -> None:
        open_orders = [
            {"orderId": "leftover-1", "type": "STOP_MARKET", "reduceOnly": True},
            {"orderId": "leftover-2", "type": "LIMIT", "closePosition": True},
        ]
        fsm, _ = _build_close_executor_fsm(open_orders=open_orders)
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
        assert seen == ["leftover-1", "leftover-2"]

    @pytest.mark.asyncio
    async def test_reconcile_segment_no_longer_uses_raw_cancel_when_execute_cancel_order_is_intercepted(self) -> None:
        open_orders = [{"orderId": "leftover-1", "type": "STOP_MARKET", "reduceOnly": True}]
        fsm, place_close = _build_close_executor_fsm(open_orders=open_orders)
        executor = CloseExecutor(fsm)

        with patch.object(
            executor,
            "execute_cancel_order",
            new=AsyncMock(return_value={"status": "CANCELED"}),
        ) as cancel_mock:
            await executor.execute_close(_dec_close_decision())

        assert cancel_mock.await_count == 1
        fsm._cancel_order.assert_not_awaited()
        place_close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tracked_teardown_package7_remains_unchanged_while_reconcile_also_uses_typed_seam(self) -> None:
        open_orders = [{"orderId": "leftover-1", "type": "STOP_MARKET", "reduceOnly": True}]
        fsm, _ = _build_close_executor_fsm(open_orders=open_orders)
        fsm._symbol_brackets["BTCUSDT"] = {"sl_order_id": "sl-1"}
        executor = CloseExecutor(fsm)

        with patch.object(
            executor,
            "execute_cancel_order",
            wraps=executor.execute_cancel_order,
        ) as cancel_wrapped:
            await executor.execute_close(_dec_close_decision())

        seen = [call.args[0].pld["order_id"] for call in cancel_wrapped.await_args_list]
        assert seen == ["sl-1", "leftover-1"]
        triggers = [call.args[0].pld["trigger"] for call in cancel_wrapped.await_args_list]
        assert triggers == [
            "DEC:CLOSE:tracked_bracket_teardown",
            RECONCILE_CLOSE_CANCEL_TRIGGER,
        ]

    @pytest.mark.asyncio
    async def test_full_close_submission_still_occurs_unchanged_with_reconcile_bridge(self) -> None:
        open_order = {"orderId": "leftover-1", "type": "TAKE_PROFIT_MARKET", "reduceOnly": True}
        fsm, place_close = _build_close_executor_fsm(open_orders=[open_order], position_amt=0.05)
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
    async def test_order_guardian_cleanup_and_reconcile_remain_untouched(self) -> None:
        open_order = {"orderId": "leftover-1", "type": "STOP_MARKET", "reduceOnly": True}
        fsm, _ = _build_close_executor_fsm(open_orders=[open_order])
        executor = CloseExecutor(fsm)

        await executor.execute_close(_dec_close_decision())

        fsm.order_guardian.cleanup_orphans.assert_awaited_once()
        fsm.order_guardian.reconcile_symbol.assert_awaited_once()
