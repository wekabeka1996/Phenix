from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from apps.reference.domains.execution_position.flows.open.fsm_open import CmdOpenPayload
from apps.reference.domains.execution_position.flows.open.open_executor import OpenExecutor
from apps.reference.domains.execution_position.flows.open.open_submission_adapter import (
    OPEN_SUBMISSION_CONTRACT,
    OpenSubmissionAdapterError,
    OpenSubmissionPayload,
)
from apps.reference.domains.execution_position.flows.open.trade_intent_open_intake import (
    parse_trade_intent_open_intake,
)
from vfoundation.core.protocol import Message

pytest_plugins = ("tests.domains.execution_position.conftest",)


def _dec_open_message(
    *,
    rid: str = "RID-OPEN-SUBMISSION",
    order_type: str = "MARKET",
    data_ref: list[str] | None = None,
    **overrides,
) -> Message:
    payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "0.0104",
        "order_type": order_type,
        "stop_price": "9800",
        "target_price": "10200",
        "idempotent_key": f"KEY-{rid}",
    }
    if order_type == "LIMIT":
        payload["price"] = "10000.05"
        payload["tif"] = "GTX"
        payload["valid_for_ms"] = 60_000
    else:
        payload["tif"] = None
    payload.update(overrides)
    return Message(
        op="DEC",
        verb="OPEN",
        src="execution_position",
        dst="execution_position",
        rid=rid,
        pld=payload,
        why="open_submission_test",
        data_ref=list(data_ref or []),
    )


def _build_open_executor_fsm() -> SimpleNamespace:
    adapter = SimpleNamespace(
        get_mark_price=AsyncMock(return_value=10_000.0),
        place_market_entry=AsyncMock(return_value={"orderId": "900001"}),
        place_limit_entry=AsyncMock(return_value={"orderId": "900002"}),
        get_book_ticker=AsyncMock(
            return_value={"bidPrice": "10000.00", "askPrice": "10000.10"},
        ),
        track_order=MagicMock(),
    )
    instrument_spec = SimpleNamespace(
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5"),
    )
    config = SimpleNamespace(
        instruments={"BTCUSDT": instrument_spec},
        strategies=SimpleNamespace(aurora=SimpleNamespace(assets={})),
    )
    return SimpleNamespace(
        adapter=adapter,
        config=config,
        _supersede_canceling=set(),
        _supersede_queue={},
        correlation_store=SimpleNamespace(put_entry_ack=MagicMock()),
        watchdog=SimpleNamespace(
            pending_orders={},
            acked_orders={},
            ensure_started=MagicMock(),
            track_order_placed=MagicMock(),
            on_order_ack=MagicMock(),
        ),
        order_guardian=SimpleNamespace(
            register_entry=MagicMock(),
            should_place_brackets=AsyncMock(return_value=False),
        ),
        _bracket_mgr=SimpleNamespace(
            preflight_position_check=AsyncMock(return_value=False),
            place_brackets_parallel=AsyncMock(),
        ),
        _evt_handlers=SimpleNamespace(
            entry_tidy_gate_allow=MagicMock(return_value=True)),
        _resolve_strategy_owner_from_decision=MagicMock(return_value={}),
        _remember_bracket_owner=MagicMock(),
        _has_active_lifecycle_for_symbol=MagicMock(return_value=False),
        _open_strategy_by_symbol={},
        _open_regime_by_symbol={},
        _intent_boundary_audit=MagicMock(),
        fsm=SimpleNamespace(order_index=None),
        bus=MagicMock(),
        log_adapter=SimpleNamespace(log_trade_execution=MagicMock()),
    )


def _limit_submission(
    *,
    symbol: str = "BNBUSDT",
    side: str = "BUY",
    quantity: str = "10.03",
    price: str = "611.87",
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


def test_open_submission_payload_rejects_inconsistent_limit_surface() -> None:
    with pytest.raises(OpenSubmissionAdapterError, match="LIMIT submission requires price"):
        OpenSubmissionPayload.from_dec_open(
            payload={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "LIMIT",
                "tif": "GTX",
            },
            normalized_qty="0.01",
            client_order_id="ENTRY-1",
        )


@pytest.mark.parametrize("bad_qty", ["", "NaN", "Infinity", "-0.01"])
def test_cmd_open_payload_rejects_invalid_qty_strings(bad_qty: str) -> None:
    with pytest.raises(ValidationError):
        CmdOpenPayload(
            symbol="BTCUSDT",
            side="BUY",
            qty=bad_qty,
            order_type="MARKET",
        )


@pytest.mark.parametrize("bad_value", ["", "NaN", "Infinity", "-1"])
def test_open_submission_payload_rejects_invalid_numeric_strings(bad_value: str) -> None:
    with pytest.raises(OpenSubmissionAdapterError):
        OpenSubmissionPayload.from_dec_open(
            payload={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "LIMIT",
                "price": bad_value,
                "tif": "GTC",
            },
            normalized_qty=bad_value,
            client_order_id="ENTRY-1",
        )


def test_scientific_notation_survives_intake_to_open_submission_boundary() -> None:
    intake = parse_trade_intent_open_intake(
        {
            "rid": "RID-E04-E2E",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "idempotent_key": "KEY-E04-E2E",
            "valid_for_ms": 60_000,
            "order": {
                "qty": "1E-7",
                "order_type": "LIMIT",
                "price": "5E+4",
                "tif": "GTC",
            },
            "stop_price": "4.5E+4",
            "target_price": "5.5E+4",
        }
    )

    cmd_payload = CmdOpenPayload.model_validate(intake.to_cmd_open_payload())
    submission = OpenSubmissionPayload.from_dec_open_with_key(
        payload=cmd_payload.model_dump(),
        normalized_qty=cmd_payload.qty,
        idempotent_key=cmd_payload.idempotent_key,
    )

    assert cmd_payload.qty == "1E-7"
    assert cmd_payload.price == "5E+4"
    assert submission.quantity == "1E-7"
    assert submission.price == "5E+4"


@pytest.mark.asyncio
async def test_market_dec_open_routes_through_typed_submission_and_emits_trace() -> None:
    fsm = _build_open_executor_fsm()
    executor = OpenExecutor(fsm)
    decision = _dec_open_message(
        order_type="MARKET",
        data_ref=[
            "obs://execution_position/open_dispatch?contract=open_dispatch_v1&status=success",
        ],
    )

    await executor.execute_open(decision)

    fsm.adapter.place_market_entry.assert_awaited_once()
    args = fsm.adapter.place_market_entry.await_args.args
    assert args[:3] == ("BTCUSDT", "BUY", "0.010")
    assert str(args[3]).startswith("ENTRY-")
    fsm.bus.emit.assert_called_once()
    bus_args = fsm.bus.emit.call_args.args
    assert bus_args[0] == "EVT:ORDER_PLACED"
    data_ref = bus_args[3]
    assert any(
        "open_dispatch?contract=open_dispatch_v1" in ref for ref in data_ref)
    assert any(
        ref.startswith("obs://execution_position/open_submission?")
        and f"contract={OPEN_SUBMISSION_CONTRACT}" in ref
        and "status=success" in ref
        and "submit_kind=market" in ref
        for ref in data_ref
    )


@pytest.mark.asyncio
async def test_limit_dec_open_routes_through_typed_submission_and_keeps_bracket_path() -> None:
    fsm = _build_open_executor_fsm()
    executor = OpenExecutor(fsm)
    executor._store_pending_brackets = MagicMock()
    decision = _dec_open_message(order_type="LIMIT")

    await executor.execute_open(decision)

    fsm.adapter.place_limit_entry.assert_awaited_once()
    args = fsm.adapter.place_limit_entry.await_args.args
    kwargs = fsm.adapter.place_limit_entry.await_args.kwargs
    assert args[:4] == ("BTCUSDT", "BUY", "10000.05", "0.010")
    assert kwargs["time_in_force"] == "GTX"
    assert str(kwargs["new_client_order_id"]).startswith("ENTRY-")
    executor._store_pending_brackets.assert_called_once()


@pytest.mark.asyncio
async def test_open_submission_rejection_emits_internal_order_rejected_with_trace() -> None:
    fsm = _build_open_executor_fsm()
    executor = OpenExecutor(fsm)
    decision = _dec_open_message(order_type="MARKET")

    with patch(
        "apps.reference.domains.execution_position.flows.open.open_executor.OpenSubmissionPayload.from_dec_open",
        side_effect=OpenSubmissionAdapterError("forced seam rejection"),
    ), patch(
        "vfoundation.core.fsm_emit_compat.emit_compat",
        new_callable=AsyncMock,
    ) as mock_emit_compat:
        await executor.execute_open(decision)

    fsm.adapter.place_market_entry.assert_not_awaited()
    mock_emit_compat.assert_awaited_once()
    reject_msg = mock_emit_compat.await_args.args[1]
    assert reject_msg.verb == "ORDER_REJECTED"
    assert reject_msg.why == "OPEN_SUBMISSION_FAIL"
    assert any(
        ref.startswith("obs://execution_position/open_submission?")
        and "status=reject" in ref
        for ref in (reject_msg.data_ref or [])
    )


@pytest.mark.asyncio
async def test_execute_open_rejects_missing_explicit_idempotent_key_before_adapter_call() -> None:
    fsm = _build_open_executor_fsm()
    executor = OpenExecutor(fsm)
    decision = _dec_open_message(order_type="MARKET", idempotent_key=None)

    with patch(
        "vfoundation.core.fsm_emit_compat.emit_compat",
        new_callable=AsyncMock,
    ) as mock_emit_compat:
        await executor.execute_open(decision)

    fsm.adapter.place_market_entry.assert_not_awaited()
    mock_emit_compat.assert_awaited_once()
    reject_msg = mock_emit_compat.await_args.args[1]
    assert reject_msg.verb == "ORDER_REJECTED"
    assert reject_msg.why == "OPEN_SUBMISSION_FAIL"
    assert any(
        ref.startswith("obs://execution_position/open_submission?")
        and "status=reject" in ref
        for ref in (reject_msg.data_ref or [])
    )
    assert "idempotent_key is required" in str(reject_msg.pld)


@pytest.mark.asyncio
async def test_execpos_dec_open_hot_path_cannot_bypass_typed_submission(fsm_harness) -> None:
    fsm, bus, _cfg = fsm_harness
    fsm.config.get_domain_mode.return_value = "live"
    fsm.adapter = SimpleNamespace(
        base_url="https://fapi.binance.com",
        get_mark_price=AsyncMock(return_value=10_000.0),
        place_market_entry=AsyncMock(return_value={"orderId": "900101"}),
        track_order=MagicMock(),
    )
    fsm._bracket_mgr.preflight_position_check = AsyncMock(return_value=False)
    fsm.order_guardian.register_entry = MagicMock()
    fsm.order_guardian.should_place_brackets = AsyncMock(return_value=False)
    fsm.watchdog.ensure_started = MagicMock()
    fsm.watchdog.track_order_placed = MagicMock()
    fsm.watchdog.on_order_ack = MagicMock()
    fsm.log_adapter.log_trade_execution = MagicMock()
    fsm._resolve_strategy_owner_from_decision = MagicMock(return_value={})
    fsm._remember_bracket_owner = MagicMock()
    fsm._has_active_lifecycle_for_symbol = MagicMock(return_value=False)
    fsm._evt_handlers.entry_tidy_gate_allow = MagicMock(return_value=True)

    decision = _dec_open_message(
        rid="RID-OPEN-SUBMISSION-HOT-PATH",
        order_type="MARKET",
        data_ref=[
            "obs://execution_position/open_dispatch?contract=open_dispatch_v1&status=success",
        ],
    )

    with patch(
        "apps.reference.domains.execution_position.flows.open.open_executor.OpenSubmissionPayload.from_dec_open",
        wraps=OpenSubmissionPayload.from_dec_open,
    ) as wrapped_submission:
        await fsm._execute_decision(decision)

    assert wrapped_submission.call_count == 1
    assert fsm.adapter.place_market_entry.await_count == 1
    assert bus.events
    order_placed_events = [
        event for event in bus.events if event[0] == "EVT:ORDER_PLACED"]
    assert order_placed_events
    data_ref = order_placed_events[0][1][2]
    assert any(
        "open_dispatch?contract=open_dispatch_v1" in ref for ref in data_ref)
    assert any(
        ref.startswith("obs://execution_position/open_submission?")
        and f"contract={OPEN_SUBMISSION_CONTRACT}" in ref
        for ref in data_ref
    )


@pytest.mark.asyncio
async def test_dec_close_path_does_not_use_open_submission_adapter(fsm_harness) -> None:
    fsm, _bus, _cfg = fsm_harness
    fsm.config.get_domain_mode.return_value = "live"
    fsm.adapter = SimpleNamespace(base_url="https://fapi.binance.com")
    fsm._close_exec.execute_close = AsyncMock()

    decision = Message(
        op="DEC",
        verb="CLOSE",
        src="execution_position",
        dst="execution_position",
        rid="RID-CLOSE-NO-OPEN-SUBMISSION",
        pld={"symbol": "BTCUSDT"},
        why="close_path_submission_guard",
    )

    with patch(
        "apps.reference.domains.execution_position.flows.open.open_executor.OpenSubmissionPayload.from_dec_open",
        wraps=OpenSubmissionPayload.from_dec_open,
    ) as wrapped_submission:
        await fsm._execute_decision(decision)

    wrapped_submission.assert_not_called()
    fsm._close_exec.execute_close.assert_awaited_once()


def test_fill_ingress_path_does_not_use_open_submission_adapter(fsm_harness) -> None:
    fsm, _bus, _cfg = fsm_harness

    fill_msg = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="adapter",
        dst="execution_position",
        rid="RID-FILL-NO-OPEN-SUBMISSION",
        pld={"symbol": "BTCUSDT"},
        why="fill_path_submission_guard",
    )

    with patch.object(
        fsm._fill_ingress_coordinator,
        "handle_canonical_fill_ingress",
        return_value=None,
    ) as wrapped_fill, patch(
        "apps.reference.domains.execution_position.flows.open.open_executor.OpenSubmissionPayload.from_dec_open",
        wraps=OpenSubmissionPayload.from_dec_open,
    ) as wrapped_submission:
        fsm.handle(fill_msg)

    wrapped_fill.assert_called_once()
    wrapped_submission.assert_not_called()
