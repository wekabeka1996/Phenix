from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.reference.domains.execution_position.bracket_manager import BracketManager
from apps.reference.domains.execution_position.close_executor import CloseExecutor
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState
from apps.reference.domains.execution_position.open_executor import OpenExecutor
from vfoundation.core.protocol import Message

pytest_plugins = ("tests.domains.execution_position.conftest",)


def _entry_fill(**overrides) -> Message:
    payload = {
        "symbol": "BTCUSDT",
        "qty": "0.01",
        "price": "100.0",
        "side": "BUY",
        "orderId": "entry-1",
        "clientOrderId": "ENTRY-1",
    }
    payload.update(overrides)
    return Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="adapter",
        dst="execution_position",
        rid="rid-fill",
        why="test_fill",
        pld=payload,
        data_ref=[],
    )


def _make_open_executor_fsm() -> SimpleNamespace:
    instrument_spec = SimpleNamespace(
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5"),
    )
    return SimpleNamespace(
        adapter=SimpleNamespace(
            get_mark_price=AsyncMock(return_value=100.0),
            place_market_entry=AsyncMock(
                return_value={"orderId": "entry-1", "clientOrderId": "ENTRY-1"}
            ),
            track_order=MagicMock(),
        ),
        config=SimpleNamespace(
            instruments={"BTCUSDT": instrument_spec},
            strategies=SimpleNamespace(aurora=SimpleNamespace(assets={})),
        ),
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
            should_place_brackets=AsyncMock(return_value=True),
        ),
        _bracket_mgr=SimpleNamespace(
            preflight_position_check=AsyncMock(return_value=False),
            place_brackets_parallel=AsyncMock(),
        ),
        _evt_handlers=SimpleNamespace(entry_tidy_gate_allow=MagicMock(return_value=True)),
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


def _dec_open() -> Message:
    return Message(
        op="DEC",
        verb="OPEN",
        src="execution_position",
        dst="execution_position",
        rid="rid-open",
        why="test_open",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.1004",
            "order_type": "MARKET",
            "stop_price": "98",
            "target_price": "102",
            "tif": None,
            "idempotent_key": "idem-open",
        },
        data_ref=[],
    )


def test_manageflow_missing_sl_pct_enters_protection_missing_and_emits_event(fsm_config) -> None:
    fsm_config.strategies.aurora.assets = {}
    flow = ManageFlowFSM(config=fsm_config)
    events: list[tuple[str, dict]] = []
    flow.set_observability_hook(lambda topic, payload: events.append((topic, payload)))

    result = flow.handle(_entry_fill())

    assert flow.state == ManageState.PROTECTION_MISSING
    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "CLOSE"
    assert result.pld["trigger"] == "BRACKET_PROTECTION_MISSING"
    failure_events = [payload for topic, payload in events if topic == "EVT:BRACKET_PLACEMENT_FAILED"]
    assert failure_events
    assert failure_events[0]["failure_class"] == "config_contract_error"
    assert failure_events[0]["remediation_action"] == "force_reduce_only_close"


@pytest.mark.parametrize("missing_field", ["price", "side"])
def test_manageflow_missing_runtime_fill_data_does_not_silently_track(fsm_config, missing_field: str) -> None:
    flow = ManageFlowFSM(config=fsm_config)
    events: list[tuple[str, dict]] = []
    flow.set_observability_hook(lambda topic, payload: events.append((topic, payload)))
    payload = _entry_fill().pld
    payload.pop(missing_field, None)
    msg = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="adapter",
        dst="execution_position",
        rid="rid-fill",
        why="test_fill",
        pld=payload,
        data_ref=[],
    )

    result = flow.handle(msg)

    assert flow.state == ManageState.PROTECTION_MISSING
    assert result is None
    failure_events = [payload for topic, payload in events if topic == "EVT:BRACKET_PLACEMENT_FAILED"]
    assert failure_events
    assert failure_events[0]["failure_class"] == "runtime_data_missing"
    assert failure_events[0]["remediation_action"] == "position_not_proven_no_close"


@pytest.mark.asyncio
async def test_market_entry_preflight_false_emits_bracket_failure_without_blind_close() -> None:
    fsm = _make_open_executor_fsm()
    fsm._handle_bracket_protection_missing = AsyncMock()
    executor = OpenExecutor(fsm)

    await executor.execute_open(_dec_open())

    fsm.adapter.place_market_entry.assert_awaited_once()
    fsm._bracket_mgr.place_brackets_parallel.assert_not_awaited()
    fsm._handle_bracket_protection_missing.assert_awaited_once()
    kwargs = fsm._handle_bracket_protection_missing.await_args.kwargs
    assert kwargs["failure_class"] == "transient_position_preflight_false"
    assert kwargs["live_position_proven"] is False


@pytest.mark.asyncio
async def test_primary_bracket_adapter_rejection_records_failure_with_live_close_remediation() -> None:
    fsm = SimpleNamespace(
        adapter=SimpleNamespace(
            place_stop_market_close_position=AsyncMock(side_effect=RuntimeError("sl boom")),
            place_take_profit_market_close_position=AsyncMock(),
            place_limit_reduce_only=AsyncMock(),
        ),
        config=SimpleNamespace(
            domains=SimpleNamespace(
                execution_position=SimpleNamespace(
                    bracket_placement=SimpleNamespace(
                        tp_widen_first_bps=10,
                        tp_widen_second_bps=20,
                        retry_backoff_ms=[1],
                    )
                )
            )
        ),
        _handle_bracket_protection_missing=AsyncMock(),
        _orphan_metrics={"tp_sl_retry_backoff": 0},
        metrics_collector=None,
    )
    manager = BracketManager(fsm)

    with pytest.raises(RuntimeError, match="sl boom"):
        await manager.place_brackets_parallel(
            symbol="BTCUSDT",
            side="BUY",
            sl=Decimal("98"),
            tp=Decimal("102"),
            qty="0.01",
            tick_size=0.01,
            idem_key="idem",
            corr_id="corr",
            oco_group_id="oco",
            entry_resp={"orderId": "entry-1", "clientOrderId": "ENTRY-1"},
            decision=SimpleNamespace(rid="rid-open", corr_id="corr", oco_group_id="oco"),
            owner_context={"strategy_id": "aurora"},
        )

    fsm._handle_bracket_protection_missing.assert_awaited_once()
    kwargs = fsm._handle_bracket_protection_missing.await_args.kwargs
    assert kwargs["failure_class"] == "adapter_rejection"
    assert kwargs["live_position_proven"] is True


@pytest.mark.asyncio
async def test_auxiliary_bracket_place_order_failure_is_not_log_only() -> None:
    manage_flow = MagicMock()
    manage_flow.state = ManageState.TRACKING
    manage_flow.entry_order_id = "entry-1"
    fsm = SimpleNamespace(
        adapter=SimpleNamespace(
            place_stop_market_close_position=AsyncMock(side_effect=RuntimeError("adapter reject")),
        ),
        manage_flows={"BTCUSDT": manage_flow},
        _handle_bracket_protection_missing=AsyncMock(),
    )
    executor = CloseExecutor(fsm)
    decision = SimpleNamespace(
        pld={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "qty": "0.01",
            "order_type": "STOP_MARKET",
            "stopPrice": "98",
            "newClientOrderId": "SL-aux-1",
        },
        rid="rid-aux",
        corr_id="corr-aux",
    )

    await executor.execute_place_order(decision)

    fsm._handle_bracket_protection_missing.assert_awaited_once()
    kwargs = fsm._handle_bracket_protection_missing.await_args.kwargs
    assert kwargs["source_path"] == "CloseExecutor.execute_place_order"
    assert kwargs["failure_class"] == "adapter_rejection"
    assert kwargs["live_position_proven"] is True


@pytest.mark.asyncio
async def test_execpos_helper_force_close_uses_existing_close_executor(fsm_harness) -> None:
    fsm, bus, _cfg = fsm_harness
    fsm._close_exec.execute_close = AsyncMock()

    action = await fsm._handle_bracket_protection_missing(
        symbol="BTCUSDT",
        source_path="test",
        failure_class="adapter_rejection",
        reason="boom",
        why_code="BRACKET_PRIMARY_ADAPTER_REJECTION",
        rid="rid-close",
        side="BUY",
        qty="0.01",
        live_position_proven=True,
    )

    assert action == "force_reduce_only_close"
    assert any(event[0] == "EVT:BRACKET_PLACEMENT_FAILED" for event in bus.events)
    fsm._close_exec.execute_close.assert_awaited_once()
    close_msg = fsm._close_exec.execute_close.await_args.args[0]
    assert close_msg.verb == "CLOSE"
    assert close_msg.pld["trigger"] == "BRACKET_PROTECTION_MISSING"
