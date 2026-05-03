from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.reference.domains.execution_position.flows.manage.bracket_health import BracketHealth
from apps.reference.domains.execution_position.flows.manage.fsm_manage import ManageState


def _make_health_fsm(*, raw_orders=None, raw_error=None):
    symbol = "BTCUSDT"
    symbol_brackets: dict[str, dict[str, str]] = {}

    def _set_symbol_bracket_order(tracked_symbol: str, *, order_role: str, order_id: str) -> None:
        brackets = symbol_brackets.setdefault(tracked_symbol, {})
        if order_role == "SL":
            brackets["sl_order_id"] = order_id
        elif order_role == "TP":
            brackets["tp_order_id"] = order_id

    adapter = SimpleNamespace(
        _request=MagicMock(side_effect=AssertionError(
            "private _request must not be used")),
        get_open_orders_raw=AsyncMock(
            side_effect=raw_error, return_value=raw_orders or []),
        place_stop_market_close_position=AsyncMock(
            return_value={"orderId": "sl-1"}),
        place_take_profit_market_close_position=AsyncMock(
            return_value={"orderId": "tp-1"}),
    )

    manage_flow = SimpleNamespace(
        state=ManageState.TRACKING, set_bracket_ids=MagicMock())
    fsm = SimpleNamespace(
        adapter=adapter,
        config=SimpleNamespace(
            domains=SimpleNamespace(
                execution_position=SimpleNamespace(
                    bracket_health_check=SimpleNamespace(
                        enabled=True,
                        interval_sec=1,
                        grace_period_ms=0,
                        max_placements_per_cycle=1,
                    )
                )
            )
        ),
        _preflight_position_check=AsyncMock(return_value=True),
        _set_symbol_bracket_order=_set_symbol_bracket_order,
        _emit_observability_event=MagicMock(),
        _has_active_lifecycle_for_symbol=MagicMock(return_value=True),
        _bracket_ownership=SimpleNamespace(
            remember_bracket_owner=MagicMock(
                return_value={
                    "strategy_id": "aurora",
                    "strategy_source": "runtime_cache",
                    "owner_status": "resolved",
                    "assigned_strategies": ["aurora"],
                    "detail": None,
                }
            ),
            append_bracket_ownership_record=MagicMock(),
        ),
        manage_flows={symbol: manage_flow},
        _last_regime_by_symbol={symbol: "DEFAULT"},
        order_guardian=SimpleNamespace(register_bracket=MagicMock()),
        _symbol_brackets=symbol_brackets,
    )
    return fsm, symbol, adapter, manage_flow


@pytest.mark.asyncio
async def test_check_brackets_uses_public_raw_open_orders_contract():
    raw_orders = [
        {"type": "STOP_MARKET", "reduceOnly": True, "closePosition": False},
        {"type": "TAKE_PROFIT_MARKET", "reduceOnly": False, "closePosition": True},
    ]
    fsm, symbol, adapter, _manage_flow = _make_health_fsm(
        raw_orders=raw_orders)
    health = BracketHealth(fsm)

    has_sl, has_tp = await health._check_brackets_on_exchange(symbol)

    assert (has_sl, has_tp) == (True, True)
    adapter.get_open_orders_raw.assert_awaited_once_with(symbol)
    adapter._request.assert_not_called()


@pytest.mark.asyncio
async def test_check_brackets_on_exchange_fail_closed_when_raw_inspection_fails():
    fsm, symbol, adapter, _manage_flow = _make_health_fsm(
        raw_error=RuntimeError("boom"))
    health = BracketHealth(fsm)

    has_sl, has_tp = await health._check_brackets_on_exchange(symbol)

    assert (has_sl, has_tp) == (True, True)
    adapter.get_open_orders_raw.assert_awaited_once_with(symbol)


@pytest.mark.asyncio
async def test_place_health_check_brackets_emits_rearm_event_and_records_recovery():
    fsm, symbol, adapter, manage_flow = _make_health_fsm()
    health = BracketHealth(fsm)

    placed = await health._place_health_check_brackets(
        symbol=symbol,
        side="BUY",
        sl_price=99.0,
        tp_price=101.0,
        need_sl=True,
        need_tp=True,
        owner_context={
            "strategy_id": "aurora",
            "strategy_source": "runtime_cache",
            "owner_status": "resolved",
            "assigned_strategies": ["aurora"],
            "detail": None,
        },
    )

    assert placed is True
    adapter.place_stop_market_close_position.assert_awaited_once()
    adapter.place_take_profit_market_close_position.assert_awaited_once()
    fsm._emit_observability_event.assert_any_call(
        "BRACKET_HEALTH_REARMED",
        {
            "symbol": symbol,
            "need_sl": True,
            "need_tp": True,
            "sl_price": 99.0,
            "tp_price": 101.0,
        },
    )
    fsm._bracket_ownership.append_bracket_ownership_record.assert_any_call(
        event_type="EXECUTION_BRACKET_RECOVERY_PLACED",
        symbol=symbol,
        placement_path="recovery",
        strategy_id="aurora",
        strategy_source="runtime_cache",
        owner_status="resolved",
        detail=None,
        assigned_strategies=["aurora"],
        lifecycle_active=True,
        sl_order_id="sl-1",
        tp_order_id="tp-1",
    )
    manage_flow.set_bracket_ids.assert_called_once_with("sl-1", "tp-1")
