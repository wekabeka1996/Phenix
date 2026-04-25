import json
from decimal import Decimal

import pytest

from vfoundation.core.protocol import Message

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.position_policy_sidecar import (
    PositionPolicySidecar,
)


def _portfolio_event(*, rid: str, ts_ms: int, positions_last_ts_ms: int, positions: list[dict]) -> Message:
    return Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="adapter",
        dst="execution_position",
        rid=rid,
        why="proof_portfolio_event",
        pld={
            "ts_ms": ts_ms,
            "positions_last_ts_ms": positions_last_ts_ms,
            "equity_free_usdt": "1000",
            "open_positions_margin_usd": "0",
            "positions_by_side": {"long_margin": "0", "short_margin": "0"},
            "positions": positions,
        },
    )


def _fill_event(*, rid: str, order_id: str, symbol: str) -> Message:
    return Message(
        op="EVT",
        verb="ORDER_FILL",
        src="adapter",
        dst="execution_position",
        rid=rid,
        why="proof_fill_event",
        pld={
            "orderId": order_id,
            "symbol": symbol,
            "quantity": "0.01",
            "qty": "0.01",
            "price": "1000",
            "side": "BUY",
            "clientOrderId": "ENTRY-proof-1",
            "client_order_id": "ENTRY-proof-1",
        },
    )


def _attach_sidecar(fsm, tmp_path):
    config = ConfigLoader().load_config(
    ).domains.execution_position.position_policy_sidecar.model_copy(deep=True)
    config.logging.write_trade_lifecycle_jsonl = False
    config.logging.trade_lifecycle_log_path = str(
        tmp_path / "sidecar_trade_lifecycle.jsonl")
    sidecar = PositionPolicySidecar(
        config=config,
        bus=fsm.bus,
        manage_flow_getter=lambda symbol: fsm.manage_flows.get(
            str(symbol).upper()),
        known_symbols_getter=fsm._position_policy_known_symbols,
    )
    fsm._position_policy_sidecar = sidecar
    return sidecar


def _trace_entry(fsm, event: Message) -> dict:
    trace_id = fsm._portfolio_event_trace_id(event)
    traces = {
        entry["trace_id"]: entry
        for entry in fsm._startup_truth_orchestrator._portfolio_event_trace_snapshot()
    }
    return traces[trace_id]


def test_portfolio_event_trace_reaches_sidecar_after_canonical_postfill_hold(fsm_harness, tmp_path):
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    sidecar = _attach_sidecar(fsm, tmp_path)
    fsm._last_features_cache[symbol] = {"symbol": symbol}

    successful_event = _portfolio_event(
        rid="proof-portfolio-success",
        ts_ms=1_775_247_900_628,
        positions_last_ts_ms=1_775_247_900_628,
        positions=[],
    )
    fsm._on_portfolio_state_updated(successful_event)

    success_trace = _trace_entry(fsm, successful_event)
    assert success_trace["latest_portfolio_state_set"] is True
    assert success_trace["expire_stale_entered"] is True
    assert success_trace["expire_stale_failed"] is False
    assert success_trace["sidecar_portfolio_refresh_reached"] is True
    assert success_trace["sidecar_portfolio_refresh_completed"] is True

    sidecar_state = sidecar._states[symbol]
    assert sidecar_state.portfolio.ts_ms == 1_775_247_900_628
    assert sidecar_state.portfolio.payload["portfolio_snapshot_status"] == "symbol_absent"
    assert sidecar_state.portfolio.payload["portfolio_symbol_present"] is False

    fill_event = _fill_event(
        rid="proof-fill-bad-shape",
        order_id="proof-order-1",
        symbol=symbol,
    )
    fsm._evt_handlers.on_order_fill(fill_event)

    postfill_key = "postfill_BTCUSDT_proof-order-1"
    postfill_item = fsm.exposure_guard.state.postfill_reservations[postfill_key]
    assert postfill_item["symbol"] == "BTCUSDT"
    assert postfill_item["side"] == "BUY"
    assert postfill_item["qty"] == "0.01"
    assert postfill_item["rid"] == "proof-fill-bad-shape"
    assert postfill_item["notional_source"] == "fill_payload"
    assert postfill_item["notional"] == Decimal("10.00")
    assert postfill_item["margin"] == Decimal("0.50")
    assert postfill_item["leverage"] == Decimal("20")
    assert isinstance(postfill_item["exp_ts"], float)
    assert isinstance(postfill_item["ts_ms"], int)

    refreshed_event = _portfolio_event(
        rid="proof-portfolio-fail",
        ts_ms=1_775_247_910_628,
        positions_last_ts_ms=1_775_247_910_628,
        positions=[],
    )
    fsm._on_portfolio_state_updated(refreshed_event)

    refresh_trace = _trace_entry(fsm, refreshed_event)
    assert refresh_trace["latest_portfolio_state_set"] is True
    assert refresh_trace["expire_stale_entered"] is True
    assert refresh_trace["expire_stale_failed"] is False
    assert refresh_trace["sidecar_portfolio_refresh_reached"] is True
    assert refresh_trace["sidecar_portfolio_refresh_completed"] is True

    assert fsm._latest_portfolio_state["positions_last_ts_ms"] == 1_775_247_910_628
    assert sidecar._states[symbol].portfolio.ts_ms == 1_775_247_910_628
    assert sidecar._states[symbol].portfolio.payload["portfolio_snapshot_status"] == "symbol_absent"

    trade_lifecycle_path = tmp_path / "trade_lifecycle.jsonl"
    canonical_fill = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="adapter",
        dst="execution_position",
        rid="proof-exec-artifact",
        why="proof_exec_facing_artifact",
        pld={
            "rid": "proof-exec-artifact",
            "symbol": symbol,
            "orderId": "proof-order-1",
            "clientOrderId": "ENTRY-proof-1",
        },
    )

    original_log_path = fsm._trade_lifecycle_log_path
    fsm._trade_lifecycle_log_path = lambda: str(trade_lifecycle_path)
    try:
        fsm._fill_ingress_coordinator.append_execution_fill_ingress_record(
            canonical_msg=canonical_fill,
            trigger_event="TRADE_EXECUTED",
            fill_source="trade_executed",
            manage_flow_created=False,
            manage_state_before="",
            manage_state_after="",
            result=None,
        )
    finally:
        fsm._trade_lifecycle_log_path = original_log_path

    rows = [
        json.loads(line)
        for line in trade_lifecycle_path.read_text(encoding="utf-8").splitlines()
    ]
    assert rows[-1]["event_type"] == "EXECUTION_FILL_INGRESS"
    assert rows[-1]["portfolio_positions_last_ts_ms"] == 1_775_247_910_628
    assert rows[-1]["portfolio_position_signature"] is not None
    assert rows[-1]["portfolio_positions_last_ts_ms"] == sidecar._states[symbol].portfolio.ts_ms


def test_portfolio_event_still_fail_closed_on_truly_malformed_postfill_state(fsm_harness, tmp_path):
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    sidecar = _attach_sidecar(fsm, tmp_path)
    fsm._last_features_cache[symbol] = {"symbol": symbol}

    successful_event = _portfolio_event(
        rid="proof-portfolio-success",
        ts_ms=1_775_247_900_628,
        positions_last_ts_ms=1_775_247_900_628,
        positions=[],
    )
    fsm._on_portfolio_state_updated(successful_event)

    fsm.exposure_guard.state.postfill_reservations["alien-postfill"] = {
        "symbol": "BTCUSDT",
        "qty": "0.01",
        "ts_ms": 1_775_247_905_000,
        "rid": "proof-alien-reservation",
    }

    failing_event = _portfolio_event(
        rid="proof-portfolio-fail-alien",
        ts_ms=1_775_247_910_628,
        positions_last_ts_ms=1_775_247_910_628,
        positions=[],
    )

    with pytest.raises(KeyError, match="exp_ts"):
        fsm._on_portfolio_state_updated(failing_event)

    fail_trace = _trace_entry(fsm, failing_event)
    assert fail_trace["latest_portfolio_state_set"] is True
    assert fail_trace["expire_stale_entered"] is True
    assert fail_trace["expire_stale_failed"] is True
    assert fail_trace["sidecar_portfolio_refresh_reached"] is False
    assert fail_trace["sidecar_portfolio_refresh_completed"] is False
    assert fail_trace["error_type"] == "KeyError"
    assert fail_trace["error_message"] == "'exp_ts'"

    assert fsm._latest_portfolio_state["positions_last_ts_ms"] == 1_775_247_910_628
    assert sidecar._states[symbol].portfolio.ts_ms == 1_775_247_900_628
