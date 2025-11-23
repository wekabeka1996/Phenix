from unittest.mock import AsyncMock

import pytest

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState
from apps.reference.domains.execution_position.shadow_execpos.close_flow import CloseFlowService, CloseConfig
from apps.reference.domains.execution_position.config import (
    ExecutionPositionConfig,
    AggregatedOcoConfig,
    TrailingConfig,
    CloseConfig as EpCloseConfig,
)


def test_timeexit_not_triggered_when_disabled():
    cfg = CloseConfig(max_hold_time_sec=0, allow_time_exit=True)
    svc = CloseFlowService()
    position = PositionState(symbol="BTCUSDT", qty=1.0, avg_entry_price=100.0, open_time=0.0)
    ctx = type("Ctx", (), {"reason": "MANUAL", "requested_qty": None, "price": None, "timestamp": 10_000.0})()

    decision = svc.plan_close(position, ctx, cfg)

    assert decision.reason_code != "TIME_CLOSE"


@pytest.mark.asyncio
async def test_timeexit_triggers_after_max_hold_time():
    cfg = ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(),
        trailing=TrailingConfig(),
        close=EpCloseConfig(max_hold_time_sec=100.0, allow_time_exit=True),
    )
    rt = ExecPosRuntimeV2(config={}, adapter=None, price_service=None, ep_config=cfg)
    rt.execution_service = AsyncMock()
    rt.close_flow_service = CloseFlowService()

    rt._positions_by_symbol["ETHUSDT"] = PositionState(symbol="ETHUSDT", qty=2.0, avg_entry_price=50.0, open_time=0.0)

    await rt._handle_close_intent("ETHUSDT", payload={"reason": "MANUAL", "timestamp": 150.0})

    rt.execution_service.close_position.assert_awaited_once()
    kwargs = rt.execution_service.close_position.await_args.kwargs
    assert kwargs["symbol"] == "ETHUSDT"
    assert kwargs["quantity"] == pytest.approx(2.0)


def test_timeexit_behavior_matches_legacy_reference():
    # Legacy: elapsed > max_hold_time triggers full close with reason TIME_CLOSE
    svc = CloseFlowService()
    position = PositionState(symbol="BTCUSDT", qty=3.0, avg_entry_price=20.0, open_time=0.0)
    ctx = type("Ctx", (), {"reason": "MANUAL", "requested_qty": None, "price": None, "timestamp": 101.0})()
    cfg = CloseConfig(max_hold_time_sec=100.0, allow_time_exit=True)

    decision = svc.plan_close(position, ctx, cfg)

    assert decision.action == "CLOSE_FULL"
    assert decision.target_qty == pytest.approx(3.0)
    assert decision.reason_code == "TIME_CLOSE"
    assert decision.why == "time_exit_threshold"


def test_timeexit_safe_profile_remains_unchanged():
    cfg = CloseConfig(max_hold_time_sec=14_400, allow_time_exit=True)
    svc = CloseFlowService()
    position = PositionState(symbol="SOLUSDT", qty=1.5, avg_entry_price=25.0, open_time=1_000.0)
    ctx = type("Ctx", (), {"reason": "MANUAL", "requested_qty": None, "price": None, "timestamp": 2_000.0})()

    decision = svc.plan_close(position, ctx, cfg)
    assert decision.reason_code != "TIME_CLOSE"
