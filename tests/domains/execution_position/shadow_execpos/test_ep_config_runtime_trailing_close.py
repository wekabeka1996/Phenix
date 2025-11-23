import asyncio
from pathlib import Path

import pytest
import yaml

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.trailing import (
    TrailingStopService,
    TrailingDecision,
    TrailingState,
)
from apps.reference.domains.execution_position.shadow_execpos.close_flow import (
    CloseFlowService,
    CloseDecision,
)
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState
from apps.reference.domains.execution_position.config import (
    ExecutionPositionConfig,
    AggregatedOcoConfig,
    TrailingConfig as EpTrailingConfig,
    CloseConfig as EpCloseConfig,
)
from apps.reference.config.execution_position import resolve_execution_position_config


class RecordingTrailingService(TrailingStopService):
    def __init__(self):
        super().__init__()
        self.seen_cfg = None

    def eval_trailing(self, position, price, trail_state, cfg, now=None):
        self.seen_cfg = cfg
        return TrailingDecision(
            sl_price=None,
            trail_state=TrailingState(),
            reason_code="TEST",
            why="test",
            exit=False,
            timestamp=now or 0.0,
        )


class RecordingCloseFlowService(CloseFlowService):
    def __init__(self):
        super().__init__()
        self.seen_cfg = None

    def plan_close(self, position, ctx, cfg=None):
        self.seen_cfg = cfg
        return CloseDecision(action="NOOP", target_qty=0.0, reason_code="TEST", why="test", timestamp=ctx.timestamp or 0.0)


def _agg_cfg():
    return AggregatedOcoConfig()


def test_trailing_uses_ep_config_when_present():
    ep_cfg = ExecutionPositionConfig(
        aggregated_oco=_agg_cfg(),
        trailing=EpTrailingConfig(
            trail_distance_bps=12.3,
            activate_after_bps=45.6,
            breakeven_rr=1.5,
            hard_time_exit_sec=789.0,
        ),
        close=EpCloseConfig(),
    )
    rt = ExecPosRuntimeV2(config={}, adapter=None, price_service=None, ep_config=ep_cfg)
    recorder = RecordingTrailingService()
    rt.trailing_service = recorder

    rt._evaluate_trailing("BTCUSDT", PositionState(symbol="BTCUSDT", qty=1.0, avg_entry_price=10.0), price=11.0)

    cfg = recorder.seen_cfg
    assert cfg is not None
    assert cfg.trail_distance_bps == pytest.approx(12.3)
    assert cfg.activate_after_bps == pytest.approx(45.6)
    assert cfg.breakeven_rr == pytest.approx(1.5)
    assert cfg.hard_time_exit_sec == pytest.approx(789.0)


def test_trailing_falls_back_to_legacy_when_ep_cfg_missing():
    rt = ExecPosRuntimeV2(
        config={
            "execution_position": {
                "trailing": {
                    "trail_distance_bps": 77.0,
                    "activate_after_bps": 10.0,
                    "breakeven_rr": 0.25,
                    "hard_time_exit_sec": 3600,
                }
            }
        },
        adapter=None,
        price_service=None,
        ep_config=None,
    )
    recorder = RecordingTrailingService()
    rt.trailing_service = recorder

    rt._evaluate_trailing("ETHUSDT", PositionState(symbol="ETHUSDT", qty=2.0, avg_entry_price=100.0), price=110.0)

    cfg = recorder.seen_cfg
    assert cfg is not None
    assert cfg.trail_distance_bps == pytest.approx(77.0)
    assert cfg.activate_after_bps == pytest.approx(10.0)
    assert cfg.breakeven_rr == pytest.approx(0.25)
    assert cfg.hard_time_exit_sec == pytest.approx(3600.0)


@pytest.mark.asyncio
async def test_close_uses_ep_config_when_present():
    ep_cfg = ExecutionPositionConfig(
        aggregated_oco=_agg_cfg(),
        trailing=EpTrailingConfig(),
        close=EpCloseConfig(
            max_hold_time_sec=123.0,
            reason_policy="strict",
            allow_time_exit=False,
            allow_profit_exit=False,
        ),
    )
    rt = ExecPosRuntimeV2(config={}, adapter=None, price_service=None, ep_config=ep_cfg)
    recorder = RecordingCloseFlowService()
    rt.close_flow_service = recorder

    await rt._handle_close_intent("BTCUSDT", payload={"reason": "MANUAL"})

    cfg = recorder.seen_cfg
    assert cfg is not None
    assert cfg.max_hold_time_sec == pytest.approx(123.0)
    assert cfg.reason_policy == "strict"
    assert cfg.allow_time_exit is False
    assert cfg.allow_profit_exit is False


@pytest.mark.asyncio
async def test_close_falls_back_to_legacy_when_ep_cfg_missing():
    rt = ExecPosRuntimeV2(
        config={
            "execution_position": {
                "close": {
                    "max_hold_time_sec": 321,
                    "reason_policy": "permissive",
                    "allow_time_exit": False,
                    "allow_profit_exit": True,
                    "allow_partial": True,
                    "min_close_qty": 0.5,
                }
            }
        },
        adapter=None,
        price_service=None,
        ep_config=None,
    )
    recorder = RecordingCloseFlowService()
    rt.close_flow_service = recorder

    await rt._handle_close_intent("ETHUSDT", payload={"reason": "MANUAL", "quantity": 0.4})

    cfg = recorder.seen_cfg
    assert cfg is not None
    assert cfg.max_hold_time_sec == pytest.approx(321.0)
    assert cfg.reason_policy == "permissive"
    assert cfg.allow_time_exit is False
    assert cfg.allow_profit_exit is True
    assert cfg.allow_partial is True
    assert cfg.min_close_qty == pytest.approx(0.5)


def test_runtime_behavior_unchanged_for_existing_yaml_profiles():
    example_path = Path("config/examples/execution_position_safe.yaml")
    raw = yaml.safe_load(example_path.read_text(encoding="utf-8"))
    ep_cfg = resolve_execution_position_config(raw)

    rt_typed = ExecPosRuntimeV2(config=raw, adapter=None, price_service=None, ep_config=ep_cfg)
    rt_legacy = ExecPosRuntimeV2(config=raw, adapter=None, price_service=None, ep_config=None)

    assert rt_typed._get_trailing_config() == rt_legacy._get_trailing_config()
    assert rt_typed._get_close_config() == rt_legacy._get_close_config()
