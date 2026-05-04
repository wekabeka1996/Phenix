"""Phase 6 Package 3 closure-hardening tests.

Proves the two remaining ownership moves and the residual proof debt:
- ``idempotent_key -> client_order_id`` is now owned by
  ``OpenSubmissionPayload.from_dec_open_with_key``.
- GTX passive-side price adjustment is now owned by
  ``OpenSubmissionPayload.apply_gtx_passive_guard``.
- WAL ``ORDER_PLACED`` record carries the open_submission success trace.
- Queued supersede re-dispatch still routes through the typed seam.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.domains.execution_position.flows.open.open_executor import OpenExecutor
from apps.reference.domains.execution_position.flows.open.open_submission_adapter import (
    OPEN_SUBMISSION_CONTRACT,
    OpenSubmissionAdapterError,
    OpenSubmissionPayload,
)
from vfoundation.core.protocol import Message

pytest_plugins = ("tests.domains.execution_position.conftest",)


# ---------------------------------------------------------------------------
# Seam unit tests: from_dec_open_with_key
# ---------------------------------------------------------------------------

def test_from_dec_open_with_key_synthesises_deterministic_client_order_id() -> None:
    payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "MARKET",
        "tif": None,
    }
    a = OpenSubmissionPayload.from_dec_open_with_key(
        payload=payload,
        normalized_qty="0.010",
        idempotent_key="KEY-ABC",
    )
    b = OpenSubmissionPayload.from_dec_open_with_key(
        payload=payload,
        normalized_qty="0.010",
        idempotent_key="KEY-ABC",
    )
    c = OpenSubmissionPayload.from_dec_open_with_key(
        payload=payload,
        normalized_qty="0.010",
        idempotent_key="KEY-DIFFERENT",
    )
    assert a.client_order_id == b.client_order_id
    assert a.client_order_id != c.client_order_id
    assert a.client_order_id.startswith("ENTRY-")


def test_from_dec_open_with_key_fails_closed_on_missing_symbol() -> None:
    with pytest.raises(OpenSubmissionAdapterError):
        OpenSubmissionPayload.from_dec_open_with_key(
            payload={"side": "BUY", "order_type": "MARKET"},
            normalized_qty="0.010",
            idempotent_key="KEY-ABC",
        )


# ---------------------------------------------------------------------------
# Seam unit tests: apply_gtx_passive_guard
# ---------------------------------------------------------------------------

def _limit_gtx(side: str, price: str) -> OpenSubmissionPayload:
    return OpenSubmissionPayload(
        symbol="BTCUSDT",
        side=side,
        quantity="0.010",
        order_type="LIMIT",
        client_order_id="ENTRY-test",
        price=price,
        time_in_force="GTX",
    )


def test_apply_gtx_passive_guard_buy_crossing_ask_is_pinned_to_best_bid() -> None:
    submission = _limit_gtx("BUY", "10000.20")
    new_sub, adjusted, original = submission.apply_gtx_passive_guard(
        best_bid=Decimal("10000.00"),
        best_ask=Decimal("10000.10"),
    )
    assert adjusted is True
    assert original == "10000.20"
    assert new_sub.price == "10000.00"


def test_apply_gtx_passive_guard_sell_crossing_bid_is_pinned_to_best_ask() -> None:
    submission = _limit_gtx("SELL", "9999.90")
    new_sub, adjusted, original = submission.apply_gtx_passive_guard(
        best_bid=Decimal("10000.00"),
        best_ask=Decimal("10000.10"),
    )
    assert adjusted is True
    assert original == "9999.90"
    assert new_sub.price == "10000.10"


def test_apply_gtx_passive_guard_noop_when_price_already_passive() -> None:
    submission = _limit_gtx("BUY", "9999.50")
    new_sub, adjusted, original = submission.apply_gtx_passive_guard(
        best_bid=Decimal("10000.00"),
        best_ask=Decimal("10000.10"),
    )
    assert adjusted is False
    assert original is None
    assert new_sub is submission


def test_apply_gtx_passive_guard_noop_on_crossed_book() -> None:
    submission = _limit_gtx("BUY", "10000.20")
    new_sub, adjusted, original = submission.apply_gtx_passive_guard(
        best_bid=Decimal("10000.50"),
        best_ask=Decimal("10000.10"),
    )
    assert adjusted is False
    assert original is None
    assert new_sub is submission


def test_apply_gtx_passive_guard_noop_on_non_gtx_limit() -> None:
    submission = OpenSubmissionPayload(
        symbol="BTCUSDT",
        side="BUY",
        quantity="0.010",
        order_type="LIMIT",
        client_order_id="ENTRY-test",
        price="10000.20",
        time_in_force="GTC",
    )
    new_sub, adjusted, original = submission.apply_gtx_passive_guard(
        best_bid=Decimal("10000.00"),
        best_ask=Decimal("10000.10"),
    )
    assert adjusted is False
    assert original is None
    assert new_sub is submission


def test_apply_gtx_passive_guard_noop_on_market() -> None:
    submission = OpenSubmissionPayload(
        symbol="BTCUSDT",
        side="BUY",
        quantity="0.010",
        order_type="MARKET",
        client_order_id="ENTRY-test",
    )
    new_sub, adjusted, _ = submission.apply_gtx_passive_guard(
        best_bid=Decimal("10000.00"),
        best_ask=Decimal("10000.10"),
    )
    assert adjusted is False
    assert new_sub is submission


# ---------------------------------------------------------------------------
# Executor-level: WAL success trace propagation (Task 3)
# ---------------------------------------------------------------------------

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
        why="open_submission_package3_test",
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
    fsm = SimpleNamespace(
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
    fsm.clear_supersede_canceling = lambda symbol: fsm._supersede_canceling.discard(
        symbol)
    fsm.dequeue_supersede = lambda symbol: fsm._supersede_queue.pop(
        symbol, None)
    return fsm


@pytest.mark.asyncio
async def test_order_placed_wal_record_carries_open_submission_success_trace() -> None:
    fsm = _build_open_executor_fsm()
    executor = OpenExecutor(fsm)
    decision = _dec_open_message(
        rid="RID-WAL-TRACE-MARKET",
        order_type="MARKET",
        data_ref=[
            "obs://execution_position/open_dispatch?contract=open_dispatch_v1&status=success",
        ],
    )

    with patch(
        "vfoundation.dr.wal.append"
    ) as wal_append:
        await executor.execute_open(decision)

    wal_append.assert_called_once()
    appended = wal_append.call_args.args[0]
    assert appended["verb"] == "ORDER_PLACED"
    assert appended["src"] == "execution_position"

    data_ref = list(appended.get("data_ref") or [])
    # Upstream DEC:OPEN trace survives the handoff.
    assert any(
        "open_dispatch?contract=open_dispatch_v1" in ref for ref in data_ref
    ), f"missing upstream dispatch ref: {data_ref}"
    # Typed submission success marker is explicitly in the WAL record, not
    # only in the bus event payload.
    assert any(
        ref.startswith("obs://execution_position/open_submission?")
        and f"contract={OPEN_SUBMISSION_CONTRACT}" in ref
        and "status=success" in ref
        and "submit_kind=market" in ref
        for ref in data_ref
    ), f"missing typed submission success ref: {data_ref}"


@pytest.mark.asyncio
async def test_gtx_price_adjustment_propagates_seam_flag_into_wal_record() -> None:
    fsm = _build_open_executor_fsm()
    # Crossing book: submit price 10000.05 is above best_ask 10000.04 → pinned to best_bid.
    fsm.adapter.get_book_ticker = AsyncMock(
        return_value={"bidPrice": "10000.00", "askPrice": "10000.04"},
    )
    executor = OpenExecutor(fsm)
    executor._store_pending_brackets = MagicMock()
    decision = _dec_open_message(
        order_type="LIMIT", rid="RID-WAL-TRACE-LIMIT-GTX")

    with patch(
        "vfoundation.dr.wal.append"
    ) as wal_append:
        await executor.execute_open(decision)

    fsm.adapter.place_limit_entry.assert_awaited_once()
    # Seam adjusted the price to best_bid.
    args = fsm.adapter.place_limit_entry.await_args.args
    assert args[2] == "10000.00"

    appended = wal_append.call_args.args[0]
    data_ref = list(appended.get("data_ref") or [])
    assert any(
        ref.startswith("obs://execution_position/open_submission?")
        and "status=success" in ref
        and "submit_kind=limit" in ref
        and "price_adjusted=true" in ref
        for ref in data_ref
    ), f"seam price_adjusted flag missing in WAL trace: {data_ref}"


# ---------------------------------------------------------------------------
# Queued supersede branch proof (Task 4)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_queued_supersede_redispatch_routes_through_typed_submission() -> None:
    """When a DEC:OPEN is queued behind a supersede cancel and later
    re-dispatched via entry_manager.process_queued_supersede, it must still
    flow through OpenSubmissionPayload.from_dec_open_with_key.
    """
    fsm = _build_open_executor_fsm()
    executor = OpenExecutor(fsm)
    decision = _dec_open_message(
        rid="RID-SUPERSEDE-QUEUED",
        order_type="MARKET",
    )

    # Simulate a supersede-queued decision being drained back into execute_open.
    # (EntryManager.process_queued_supersede ultimately calls
    # fsm._execute_decision(decision), which dispatches DEC:OPEN into
    # OpenExecutor.execute_open. We invoke execute_open directly to keep the
    # test bounded to the typed submission seam.)
    with patch(
        "apps.reference.domains.execution_position.flows.open.open_executor."
        "OpenSubmissionPayload.from_dec_open_with_key",
        wraps=OpenSubmissionPayload.from_dec_open_with_key,
    ) as wrapped_seam, patch(
        "vfoundation.dr.wal.append"
    ):
        await executor.execute_open(decision)

    assert wrapped_seam.call_count == 1
    fsm.adapter.place_market_entry.assert_awaited_once()


@pytest.mark.asyncio
async def test_entry_manager_process_queued_supersede_drives_typed_seam_end_to_end() -> None:
    """End-to-end proof: ``EntryManager.process_queued_supersede(symbol)``
    pops the queued DEC:OPEN, routes it through ``_fsm._execute_decision``,
    which dispatches into ``OpenExecutor.execute_open`` and therefore through
    ``OpenSubmissionPayload.from_dec_open_with_key``. The adapter must be
    called via the typed seam exactly once; no alternate submission path.
    """
    import asyncio

    from apps.reference.domains.execution_position.flows.open.entry_manager import (
        EntryManager,
    )

    fsm = _build_open_executor_fsm()
    executor = OpenExecutor(fsm)

    # Wire the minimal fsm with everything EntryManager.process_queued_supersede
    # needs to actually re-dispatch a decision. Nothing more.
    symbol = "BTCUSDT"
    queued_decision = _dec_open_message(
        rid="RID-SUPERSEDE-QUEUED-E2E",
        order_type="MARKET",
    )
    fsm._supersede_canceling = {symbol}
    fsm._supersede_queue = {
        symbol: {"decision": queued_decision, "queued_at": 0.0},
    }

    loop = asyncio.get_running_loop()
    fsm._get_async_loop = MagicMock(return_value=loop)

    scheduled: list[asyncio.Task] = []

    def _submit_async(coro, target_loop):
        # Mirror ExecPosFSM._submit_async's same-loop branch so we can await.
        scheduled.append(target_loop.create_task(coro))

    fsm._submit_async = _submit_async

    # _execute_decision on the real FSM dispatches DEC:OPEN to
    # OpenExecutor.execute_open. We bind it explicitly to prove the queued
    # decision reaches the seam via the exact same dispatch contract.
    async def _execute_decision(decision):
        assert decision.op == "DEC" and decision.verb == "OPEN"
        await executor.execute_open(decision)

    fsm._execute_decision = _execute_decision

    with patch(
        "apps.reference.domains.execution_position.flows.open.open_executor."
        "OpenSubmissionPayload.from_dec_open_with_key",
        wraps=OpenSubmissionPayload.from_dec_open_with_key,
    ) as wrapped_seam, patch(
        "apps.reference.domains.execution_position.flows.open.open_executor."
        "OpenSubmissionPayload.from_dec_open",
        wraps=OpenSubmissionPayload.from_dec_open,
    ) as wrapped_alt_seam, patch(
        "vfoundation.dr.wal.append"
    ) as wal_append:
        entry_mgr = EntryManager(fsm)
        entry_mgr.process_queued_supersede(symbol)
        # Drain the tasks scheduled by process_queued_supersede.
        assert scheduled, "process_queued_supersede did not schedule a coroutine"
        await asyncio.gather(*scheduled)

    # Queue drained.
    assert symbol not in fsm._supersede_canceling
    assert symbol not in fsm._supersede_queue

    # Seam traversed exactly once on the redispatched decision, no alternate
    # construction bypass.
    assert wrapped_seam.call_count == 1, (
        f"typed seam not traversed once on supersede redispatch "
        f"(from_dec_open_with_key.call_count={wrapped_seam.call_count})"
    )
    # from_dec_open is only reached through from_dec_open_with_key, which
    # internally delegates to it. So call_count must also be 1 — proving no
    # alternate direct construction path is active.
    assert wrapped_alt_seam.call_count == 1

    # Adapter submitted through the typed seam exactly once.
    fsm.adapter.place_market_entry.assert_awaited_once()
    market_args = fsm.adapter.place_market_entry.await_args.args
    # client_order_id on the adapter call must match the seam-derived id.
    assert str(market_args[3]).startswith("ENTRY-")

    # WAL success-trace is still attached on the redispatched path.
    wal_append.assert_called_once()
    appended = wal_append.call_args.args[0]
    assert appended["verb"] == "ORDER_PLACED"
    data_ref = list(appended.get("data_ref") or [])
    assert any(
        ref.startswith("obs://execution_position/open_submission?")
        and f"contract={OPEN_SUBMISSION_CONTRACT}" in ref
        and "status=success" in ref
        and "submit_kind=market" in ref
        for ref in data_ref
    ), f"missing typed submission success ref on redispatch: {data_ref}"


@pytest.mark.asyncio
async def test_entry_manager_process_queued_supersede_noops_when_queue_empty() -> None:
    """Guard: when the queue is empty, no coroutine is scheduled and the
    typed seam is never traversed (proves the redispatch path itself is the
    only driver of the seam on supersede).
    """
    import asyncio

    from apps.reference.domains.execution_position.flows.open.entry_manager import (
        EntryManager,
    )

    fsm = _build_open_executor_fsm()
    fsm._supersede_canceling = set()
    fsm._supersede_queue = {}
    fsm._get_async_loop = MagicMock(return_value=asyncio.get_running_loop())
    fsm._submit_async = MagicMock()
    fsm._execute_decision = AsyncMock()

    with patch(
        "apps.reference.domains.execution_position.flows.open.open_executor."
        "OpenSubmissionPayload.from_dec_open_with_key",
        wraps=OpenSubmissionPayload.from_dec_open_with_key,
    ) as wrapped_seam:
        EntryManager(fsm).process_queued_supersede("BTCUSDT")

    fsm._submit_async.assert_not_called()
    fsm._execute_decision.assert_not_awaited()
    assert wrapped_seam.call_count == 0
