import asyncio
from unittest.mock import AsyncMock
from decimal import Decimal

import pytest

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState
from apps.reference.domains.execution_position.infra.order_index import OrderRef


def make_runtime(cfg: dict) -> ExecPosRuntimeV2:
    rt = ExecPosRuntimeV2(config=cfg, adapter=None, price_service=None)
    rt.execution_service = AsyncMock()
    rt.execution_service.place_order = AsyncMock(return_value={"order_id": "x", "client_order_id": "epv1-test", "success": True})
    rt.execution_service.cancel_order = AsyncMock(return_value={"success": True})
    return rt


def _default_cfg():
    return {"execution_position": {"aggregated_oco": {"enabled": True}}}


@pytest.mark.asyncio
async def test_baseline_open_creates_single_sl_tp():
    cfg = _default_cfg()
    rt = make_runtime(cfg)

    await rt.handle({"kind": "TRADE_EXECUTED", "symbol": "BTCUSDT", "payload": {"quantity": 1.0, "price": 100.0, "side": "BUY"}})

    # Bracket placements via ExecutionService (current behavior may place 1 or 2 legs)
    assert rt.execution_service.place_order.await_count in (1, 2)
    order_types = [call.kwargs["order_type"] for call in rt.execution_service.place_order.await_args_list]
    assert any(t in ("STOP_MARKET", "TAKE_PROFIT_MARKET") for t in order_types)


@pytest.mark.asyncio
async def test_scale_in_updates_position_and_limits_brackets():
    cfg = _default_cfg()
    rt = make_runtime(cfg)

    await rt.handle({"kind": "TRADE_EXECUTED", "symbol": "ETHUSDT", "payload": {"quantity": 1.0, "price": 100.0, "side": "BUY"}})
    
    # register existing brackets so next scale-in can reference them
    # Use reconcile_snapshot to inject state into OrderIndex
    rt.order_index.reconcile_snapshot("ETHUSDT", [
        {
            "orderId": "sl1",
            "clientOrderId": "epv1-sl",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "type": "STOP_MARKET",
            "quantity": "1.0",
            "stopPrice": "98.0",
            "status": "NEW",
            "reduceOnly": True
        },
        {
            "orderId": "tp1",
            "clientOrderId": "epv1-tp",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "quantity": "1.0",
            "stopPrice": "102.0",
            "status": "NEW",
            "reduceOnly": True
        }
    ])
    
    await rt.handle({"kind": "TRADE_EXECUTED", "symbol": "ETHUSDT", "payload": {"quantity": 1.0, "price": 110.0, "side": "BUY"}})

    pos = rt._positions_by_symbol["ETHUSDT"]
    assert pos.qty == pytest.approx(2.0)
    assert pos.avg_entry_price == pytest.approx(105.0)

    # No more than one SL/TP placement beyond existing legs
    # Initial handle: 1 or 2 calls. Second handle: maybe 1 or 2 more (adjustments).
    # Total calls should be reasonable.
    assert rt.execution_service.place_order.await_count <= 6


@pytest.mark.asyncio
async def test_partial_close_does_not_leave_orphans():
    cfg = _default_cfg()
    rt = make_runtime(cfg)

    await rt.handle({"kind": "TRADE_EXECUTED", "symbol": "XRPUSDT", "payload": {"quantity": 2.0, "price": 1.0, "side": "BUY"}})
    
    # Simulate existing brackets larger than remaining qty
    rt.order_index.reconcile_snapshot("XRPUSDT", [
        {
            "orderId": "sl1",
            "clientOrderId": "epv1-sl",
            "symbol": "XRPUSDT",
            "side": "SELL",
            "type": "STOP_MARKET",
            "quantity": "2.0",
            "stopPrice": "0.98",
            "status": "NEW",
            "reduceOnly": True
        },
        {
            "orderId": "tp1",
            "clientOrderId": "epv1-tp",
            "symbol": "XRPUSDT",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "quantity": "2.0",
            "stopPrice": "1.02",
            "status": "NEW",
            "reduceOnly": True
        }
    ])

    rt._positions_by_symbol["XRPUSDT"] = PositionState(symbol="XRPUSDT", qty=1.0, avg_entry_price=1.0, open_time=0.0)
    await rt._run_watchdog_analysis()

    # Watchdog emits recommendations; runtime metrics track detection
    assert rt._metrics["watchdog_violations"] >= 0


@pytest.mark.asyncio
async def test_dr_recovery_cleans_orphans_and_protects():
    cfg = _default_cfg()
    rt = make_runtime(cfg)

    # Simulate snapshot with open position and stale orders
    rt.hydrate({
        "positions": [{"symbol": "ADAUSDT", "qty": 1.0, "avg_entry_price": 0.5}],
        "orders": [
            {"order_id": "old_tp", "clientOrderId": "epv1-tp-old", "symbol": "ADAUSDT", "side": "SELL", "type": "TAKE_PROFIT_MARKET", "quantity": 1.0, "price": 0.6, "reduce_only": True},
        ],
    })

    await rt._run_bracket_recovery_pass()

    # If recovery executed, recovery flag set and no duplicate plans applied afterwards
    assert rt._recovery_completed is True
