import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.config import (
    ExecutionPositionConfig,
    AggregatedOcoConfig,
    TrailingConfig,
    CloseConfig,
    SnapshotConfig,
)
from apps.reference.domains.execution_position.shadow_execpos.types import WatchdogRecommendation, WatchdogAction


def _runtime() -> ExecPosRuntimeV2:
    ep_cfg = ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(enabled=True),
        trailing=TrailingConfig(),
        close=CloseConfig(),
        snapshot=SnapshotConfig(),
    )
    rt = ExecPosRuntimeV2(config={}, adapter=None,
                          price_service=None, ep_config=ep_cfg)
    return rt


@pytest.mark.asyncio
async def test_watchdog_force_snapshot_triggers_hook():
    runtime = _runtime()
    hook = AsyncMock()
    runtime.set_snapshot_refresh_hook(hook)

    rec = WatchdogRecommendation(
        symbol="ETHUSDT",
        side="LONG",
        kind="ALERT",
        action=WatchdogAction.FORCE_SNAPSHOT,
        target_id=None,
        reason="missing_snapshot",
        orders_to_cancel=[],
        details={},
    )

    # Stub watchdog analyze to return our recommendation
    runtime.watchdog.analyze = lambda open_orders, positions: [rec]

    await runtime._run_watchdog_analysis()

    hook.assert_awaited_once_with("ETHUSDT")


@pytest.mark.asyncio
async def test_watchdog_force_snapshot_throttled():
    runtime = _runtime()
    hook = AsyncMock()
    runtime.set_snapshot_refresh_hook(hook)
    runtime._snapshot_request_interval_sec = 10.0

    rec = WatchdogRecommendation(
        symbol="ETHUSDT",
        side="LONG",
        kind="ALERT",
        action=WatchdogAction.FORCE_SNAPSHOT,
        target_id=None,
        reason="missing_snapshot",
        orders_to_cancel=[],
        details={},
    )
    runtime.watchdog.analyze = lambda open_orders, positions: [rec]

    await runtime._run_watchdog_analysis()
    await runtime._run_watchdog_analysis()

    # Second call should be throttled
    hook.assert_awaited_once_with("ETHUSDT")
