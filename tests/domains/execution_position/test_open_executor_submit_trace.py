import json
from pathlib import Path
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import jsonschema
import pytest

from apps.reference.adapters.binance_adapter import BinanceAPIError
from apps.reference.domains.execution_position.flows.open.open_submission_adapter import (
    OpenSubmissionPayload,
)


class _NoSleepClock:
    def __init__(self) -> None:
        self.sleep_sec = AsyncMock()

    def now_ms(self) -> int:
        return 0


def _limit_submission(
    *,
    symbol: str = "BNBUSDT",
    side: str = "BUY",
    price: str = "611.87",
    quantity: str = "10.03",
    tif: str = "GTX",
    client_order_id: str = "ENTRY-abc123",
) -> OpenSubmissionPayload:
    return OpenSubmissionPayload(
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type="LIMIT",
        price=price,
        time_in_force=tif,
        client_order_id=client_order_id,
    )


@pytest.mark.asyncio
async def test_collect_limit_submit_trace_includes_book_context():
    from apps.reference.domains.execution_position.flows.open.open_executor import OpenExecutor

    fsm = MagicMock()
    fsm.adapter = MagicMock()
    fsm.adapter.get_book_ticker = AsyncMock(
        return_value={"bidPrice": "100.10", "askPrice": "100.30"}
    )
    executor = OpenExecutor(fsm)
    decision = MagicMock(
        rid="RID-TRACE-1",
        pld={},
        data_ref=[
            "obs://execution_position/limit_rounding?before=100.26&after=100.3&tick=0.1&mode=ceil"
        ],
    )

    trace = await executor._collect_limit_submit_trace(
        decision=decision,
        symbol="BTCUSDT",
        side="SELL",
        price=Decimal("100.3"),
        qty=Decimal("0.001"),
        tif="GTX",
    )

    metadata = trace["metadata"]
    assert trace["event_type"] == "ORDER_INTENT"
    assert trace["source_fsm"] == "ExecPosFSM"
    assert metadata["trace_kind"] == "LIMIT_SUBMIT_TRACE"
    assert metadata["price_before_rounding"] == "100.26"
    assert metadata["price_after_rounding"] == "100.3"
    assert metadata["rounding_mode"] == "ceil"
    assert metadata["best_bid"] == "100.10"
    assert metadata["best_ask"] == "100.30"
    assert metadata["spread"] == "0.20"
    assert metadata["distance_to_touch"] == "0.20"

    schema = json.loads(
        Path("apps/reference/schemas/order_logger_v1.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=trace, schema=schema)


@pytest.mark.asyncio
async def test_collect_limit_submit_trace_fails_closed_without_book_api():
    from apps.reference.domains.execution_position.flows.open.open_executor import OpenExecutor

    fsm = MagicMock()
    fsm.adapter = object()
    executor = OpenExecutor(fsm)
    decision = MagicMock(rid="RID-TRACE-2", pld={}, data_ref=[])

    trace = await executor._collect_limit_submit_trace(
        decision=decision,
        symbol="BTCUSDT",
        side="BUY",
        price=Decimal("99.9"),
        qty=Decimal("0.001"),
        tif="GTX",
    )

    assert trace["metadata"]["book_context"] == "UNAVAILABLE"
    assert trace["metadata"]["price_after_rounding"] == "99.9"


@pytest.mark.asyncio
async def test_place_limit_entry_recovers_uncertain_submit_by_client_order_id(monkeypatch):
    from apps.reference.domains.execution_position.flows.open.open_executor import OpenExecutor

    monkeypatch.setattr(
        "apps.reference.domains.execution_position.flows.open.open_executor.order_logger.write",
        lambda *_args, **_kwargs: None,
    )

    fsm = MagicMock()
    fsm.adapter = MagicMock()
    fsm.adapter.get_book_ticker = AsyncMock(
        return_value={"bidPrice": "611.87", "askPrice": "611.89"}
    )
    fsm.adapter.place_limit_entry = AsyncMock(
        side_effect=BinanceAPIError(
            code=-1007,
            msg="Timeout waiting for response from backend server. Send status unknown; execution status unknown.",
        )
    )
    fsm.adapter.get_order_by_client_order_id = AsyncMock(
        return_value={
            "symbol": "BNBUSDT",
            "orderId": 123456789,
            "clientOrderId": "ENTRY-abc123",
            "status": "NEW",
            "side": "BUY",
            "price": "611.87",
            "origQty": "10.03",
            "executedQty": "0",
        }
    )
    fsm.adapter.register_clientorderid = AsyncMock()
    fsm._intent_boundary_audit = MagicMock()
    executor = OpenExecutor(fsm)
    decision = MagicMock(
        rid="RID-UNCERTAIN-1",
        pld={"strategy_id": "md_amr"},
        data_ref=[
            "obs://execution_position/limit_rounding?before=611.925&after=611.92&tick=0.01&mode=floor"
        ],
    )

    recovered, returned_submission, price_adjusted = await executor._place_limit_entry(
        decision=decision,
        submission=_limit_submission(),
        wal=MagicMock(),
    )

    assert recovered["orderId"] == 123456789
    assert returned_submission.client_order_id == "ENTRY-abc123"
    assert price_adjusted is False
    fsm.adapter.get_order_by_client_order_id.assert_awaited()
    fsm.adapter.register_clientorderid.assert_awaited_once_with(
        "ENTRY-abc123", "123456789", "BNBUSDT"
    )
    fsm._intent_boundary_audit.mark_submit_started.assert_called_once()
    fsm._intent_boundary_audit.mark_submit_finished.assert_called_once_with(
        rid="RID-UNCERTAIN-1"
    )


@pytest.mark.asyncio
async def test_place_limit_entry_raises_uncertain_submit_error_without_lookup(monkeypatch):
    from apps.reference.domains.execution_position.flows.open.open_executor import (
        OpenExecutor,
        UncertainSubmitRecoveryError,
    )

    monkeypatch.setattr(
        "apps.reference.domains.execution_position.flows.open.open_executor.order_logger.write",
        lambda *_args, **_kwargs: None,
    )
    fake_clock = _NoSleepClock()
    monkeypatch.setattr(
        "apps.reference.domains.execution_position.flows.open.open_executor.get_clock",
        lambda: fake_clock,
    )

    fsm = MagicMock()
    fsm.adapter = SimpleNamespace(
        get_book_ticker=AsyncMock(
            return_value={"bidPrice": "611.87", "askPrice": "611.89"}
        ),
        place_limit_entry=AsyncMock(
            side_effect=BinanceAPIError(
                code=-1007,
                msg="Timeout waiting for response from backend server. Send status unknown; execution status unknown.",
            )
        ),
    )
    fsm._intent_boundary_audit = MagicMock()
    executor = OpenExecutor(fsm)
    decision = MagicMock(
        rid="RID-UNCERTAIN-NO-LOOKUP",
        pld={"strategy_id": "md_amr"},
        data_ref=[
            "obs://execution_position/limit_rounding?before=611.925&after=611.92&tick=0.01&mode=floor"
        ],
    )

    with pytest.raises(UncertainSubmitRecoveryError) as exc_info:
        await executor._place_limit_entry(
            decision=decision,
            submission=_limit_submission(client_order_id="ENTRY-no-lookup"),
            wal=MagicMock(),
        )

    assert exc_info.value.entry_id == "ENTRY-no-lookup"
    assert exc_info.value.attempts == 0
    assert exc_info.value.binance_code == -1007
    fsm._intent_boundary_audit.mark_submit_started.assert_called_once()
    fsm._intent_boundary_audit.mark_submit_finished.assert_called_once_with(
        rid="RID-UNCERTAIN-NO-LOOKUP"
    )
    assert fake_clock.sleep_sec.await_count == 0


@pytest.mark.asyncio
async def test_place_limit_entry_raises_uncertain_submit_error_after_lookup_miss(monkeypatch):
    from apps.reference.domains.execution_position.flows.open.open_executor import (
        OpenExecutor,
        UncertainSubmitRecoveryError,
    )

    monkeypatch.setattr(
        "apps.reference.domains.execution_position.flows.open.open_executor.order_logger.write",
        lambda *_args, **_kwargs: None,
    )
    fake_clock = _NoSleepClock()
    monkeypatch.setattr(
        "apps.reference.domains.execution_position.flows.open.open_executor.get_clock",
        lambda: fake_clock,
    )

    fsm = MagicMock()
    fsm.adapter = MagicMock()
    fsm.adapter.get_book_ticker = AsyncMock(
        return_value={"bidPrice": "611.87", "askPrice": "611.89"}
    )
    fsm.adapter.place_limit_entry = AsyncMock(
        side_effect=BinanceAPIError(
            code=-1007,
            msg="Timeout waiting for response from backend server. Send status unknown; execution status unknown.",
        )
    )
    fsm.adapter.get_order_by_client_order_id = AsyncMock(return_value=None)
    fsm._intent_boundary_audit = MagicMock()
    executor = OpenExecutor(fsm)
    decision = MagicMock(
        rid="RID-UNCERTAIN-LOOKUP-MISS",
        pld={"strategy_id": "md_amr"},
        data_ref=[],
    )

    with pytest.raises(UncertainSubmitRecoveryError) as exc_info:
        await executor._place_limit_entry(
            decision=decision,
            submission=_limit_submission(client_order_id="ENTRY-lookup-miss"),
            wal=MagicMock(),
        )

    assert exc_info.value.entry_id == "ENTRY-lookup-miss"
    assert exc_info.value.attempts == 3
    assert fsm.adapter.get_order_by_client_order_id.await_count == 3
    fake_clock.sleep_sec.assert_has_awaits([call(0.35), call(0.75)])
    fsm._intent_boundary_audit.mark_submit_finished.assert_called_once_with(
        rid="RID-UNCERTAIN-LOOKUP-MISS"
    )


@pytest.mark.asyncio
async def test_place_limit_entry_raises_uncertain_submit_error_after_lookup_exceptions(monkeypatch):
    from apps.reference.domains.execution_position.flows.open.open_executor import (
        OpenExecutor,
        UncertainSubmitRecoveryError,
    )

    monkeypatch.setattr(
        "apps.reference.domains.execution_position.flows.open.open_executor.order_logger.write",
        lambda *_args, **_kwargs: None,
    )
    fake_clock = _NoSleepClock()
    monkeypatch.setattr(
        "apps.reference.domains.execution_position.flows.open.open_executor.get_clock",
        lambda: fake_clock,
    )

    fsm = MagicMock()
    fsm.adapter = MagicMock()
    fsm.adapter.get_book_ticker = AsyncMock(
        return_value={"bidPrice": "611.87", "askPrice": "611.89"}
    )
    fsm.adapter.place_limit_entry = AsyncMock(
        side_effect=BinanceAPIError(
            code=-1007,
            msg="Timeout waiting for response from backend server. Send status unknown; execution status unknown.",
        )
    )
    fsm.adapter.get_order_by_client_order_id = AsyncMock(
        side_effect=[
            RuntimeError("lookup-1"),
            RuntimeError("lookup-2"),
            RuntimeError("lookup-3"),
        ]
    )
    fsm._intent_boundary_audit = MagicMock()
    executor = OpenExecutor(fsm)
    decision = MagicMock(
        rid="RID-UNCERTAIN-LOOKUP-ERROR",
        pld={"strategy_id": "md_amr"},
        data_ref=[],
    )

    with pytest.raises(UncertainSubmitRecoveryError) as exc_info:
        await executor._place_limit_entry(
            decision=decision,
            submission=_limit_submission(client_order_id="ENTRY-lookup-error"),
            wal=MagicMock(),
        )

    assert exc_info.value.entry_id == "ENTRY-lookup-error"
    assert exc_info.value.attempts == 3
    assert fsm.adapter.get_order_by_client_order_id.await_count == 3
    fake_clock.sleep_sec.assert_has_awaits([call(0.35), call(0.75)])
    fsm._intent_boundary_audit.mark_submit_finished.assert_called_once_with(
        rid="RID-UNCERTAIN-LOOKUP-ERROR"
    )
