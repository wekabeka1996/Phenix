from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.maintenance.close_all_positions import (  # noqa: E402
    CloseTarget,
    collect_close_targets,
    flatten_positions,
    resolve_effective_mode,
)
from vfoundation.core.adapters.base import ExchangeOrderResponse  # noqa: E402


def _open_order(symbol: str, order_id: str) -> ExchangeOrderResponse:
    return ExchangeOrderResponse(
        order_id=order_id,
        client_order_id=f"cid-{order_id}",
        symbol=symbol,
        side="SELL",
        quantity="1.0",
        filled_qty="0",
        price="0",
        status="NEW",
        timestamp_ms=1,
    )


def test_collect_close_targets_maps_side_and_filter() -> None:
    positions = [
        {"symbol": "BTCUSDT", "positionAmt": "1.5", "positionSide": "BOTH"},
        {"symbol": "ETHUSDT", "positionAmt": "-0.25", "positionSide": "SHORT"},
        {"symbol": "SOLUSDT", "positionAmt": "0", "positionSide": "BOTH"},
    ]

    targets = collect_close_targets(positions, {"BTCUSDT", "ETHUSDT"})

    assert targets == [
        CloseTarget(
            symbol="BTCUSDT",
            position_side="BOTH",
            close_side="SELL",
            quantity="1.5",
        ),
        CloseTarget(
            symbol="ETHUSDT",
            position_side="SHORT",
            close_side="BUY",
            quantity="0.25",
        ),
    ]


def test_resolve_effective_mode_fails_closed_for_backtest() -> None:
    cfg = SimpleNamespace(trading_mode="backtest")

    with pytest.raises(ValueError, match="explicit --mode"):
        resolve_effective_mode(cfg, "config")


def test_flatten_positions_cancels_orders_before_both_close() -> None:
    adapter = AsyncMock()
    adapter.get_open_positions.side_effect = [
        [{"symbol": "BTCUSDT", "positionAmt": "1.0", "positionSide": "BOTH"}],
        [{"symbol": "BTCUSDT", "positionAmt": "1.0", "positionSide": "BOTH"}],
    ]
    adapter.get_open_orders.return_value = [_open_order("BTCUSDT", "123")]
    adapter.cancel_order.return_value = _open_order("BTCUSDT", "123")
    adapter.place_market_reduce_only.return_value = {"orderId": "close-1"}

    summary = asyncio.run(
        flatten_positions(adapter, cancel_open_orders=True, dry_run=False)
    )

    assert summary.cancelled_orders == 1
    assert summary.submitted_closes == 1
    adapter.place_market_reduce_only.assert_awaited_once()

    args, kwargs = adapter.place_market_reduce_only.await_args
    assert args == ("BTCUSDT", "SELL", "1")
    assert kwargs["new_client_order_id"]

    assert adapter.mock_calls[:5] == [
        call.get_open_positions(),
        call.get_open_orders("BTCUSDT"),
        call.cancel_order(symbol="BTCUSDT", order_id="123", client_order_id=None),
        call.get_open_positions(),
        call.place_market_reduce_only(
            "BTCUSDT",
            "SELL",
            "1",
            new_client_order_id=ANY,
        ),
    ]


def test_flatten_positions_uses_create_order_for_hedge_side() -> None:
    adapter = AsyncMock()
    adapter.get_open_positions.side_effect = [
        [{"symbol": "ETHUSDT", "positionAmt": "2.5", "positionSide": "LONG"}],
        [{"symbol": "ETHUSDT", "positionAmt": "2.5", "positionSide": "LONG"}],
    ]
    adapter.quantize_quantity.return_value = "2.5"
    adapter.create_order.return_value = ExchangeOrderResponse(
        order_id="hedge-close-1",
        client_order_id="cid-hedge-close-1",
        symbol="ETHUSDT",
        side="SELL",
        quantity="2.5",
        filled_qty="0",
        price="0",
        status="NEW",
        timestamp_ms=1,
    )

    summary = asyncio.run(
        flatten_positions(adapter, cancel_open_orders=False, dry_run=False)
    )

    assert summary.cancelled_orders == 0
    assert summary.submitted_closes == 1
    adapter.place_market_reduce_only.assert_not_called()
    adapter.quantize_quantity.assert_awaited_once_with("ETHUSDT", "2.5")
    adapter.create_order.assert_awaited_once()

    order_params = adapter.create_order.await_args.args[0]
    assert order_params.symbol == "ETHUSDT"
    assert order_params.side == "SELL"
    assert order_params.order_type == "MARKET"
    assert order_params.quantity == "2.5"
    assert order_params.reduce_only is True
    assert order_params.position_side == "LONG"
    assert order_params.time_in_force == ""