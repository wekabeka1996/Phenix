from __future__ import annotations

import asyncio
import time
from pathlib import Path

from apps.reference.domains.decision_making.authority_bridge import (
    NeocortexAuthorityBridge,
)
from apps.reference.domains.decision_making.authority_process_runner import (
    BaselineAuthorityProcessRunner,
)
from apps.reference.domains.decision_making.schemas.control_decision import (
    ControlDecisionAction,
    ControlDecisionRequest,
)


class _FakeBaselineController:
    feature_columns = ["x"]

    def __init__(self, *, sleep_sec: float = 0.0, action: str = "ALLOW") -> None:
        self.sleep_sec = sleep_sec
        self.action = action

    def state_vector_from_snapshot(self, snapshot):
        return [snapshot.get("x", 1.0)]

    def predict_intent(self, state_vector):
        if self.sleep_sec:
            time.sleep(self.sleep_sec)
        return self.action


def _request(symbol: str = "BTCUSDT") -> ControlDecisionRequest:
    return ControlDecisionRequest(
        decision_id=f"decision-{symbol}",
        rid=f"rid-{symbol}",
        symbol=symbol,
        proposed_action="OPEN",
        deadline_ms=int(time.time() * 1000) + 5_000,
        decision_basis_ts=int(time.time() * 1000),
        causal_state_snapshot={"state_vector": [1.0]},
    )


def test_baseline_timeout_kills_worker_and_fails_closed() -> None:
    runner = BaselineAuthorityProcessRunner(
        baseline_controller=_FakeBaselineController(sleep_sec=1.0),
        max_queue_depth=1,
        max_inflight_per_symbol=1,
    )
    bridge = NeocortexAuthorityBridge(
        process_runner=runner,
        process_timeout_ms=50,
    )

    response = asyncio.run(bridge.request_authority(_request(), timeout_ms=250))

    assert response.action == ControlDecisionAction.FALLBACK
    assert response.fallback_reason == "BRIDGE_TIMEOUT"
    assert runner.telemetry.timeout == 1
    assert runner.telemetry.killed_worker == 1


def test_baseline_process_runner_queue_full_fails_closed() -> None:
    runner = BaselineAuthorityProcessRunner(
        baseline_controller=_FakeBaselineController(sleep_sec=0.25),
        max_queue_depth=1,
        max_inflight_per_symbol=1,
    )
    bridge = NeocortexAuthorityBridge(process_runner=runner, process_timeout_ms=500)

    async def run_two():
        first = asyncio.create_task(bridge.request_authority(_request("ETHUSDT"), 500))
        await asyncio.sleep(0.05)
        second = await bridge.request_authority(_request("BTCUSDT"), 500)
        await first
        return second

    response = asyncio.run(run_two())

    assert response.action == ControlDecisionAction.FALLBACK
    assert response.fallback_reason == "BRIDGE_QUEUE_FULL"
    assert runner.telemetry.queue_full == 1


def test_authority_bridge_no_threadpool_baseline_fallback() -> None:
    source = Path(
        "apps/reference/domains/decision_making/authority_bridge.py"
    ).read_text(encoding="utf-8")

    assert "asyncio.to_thread" not in source
