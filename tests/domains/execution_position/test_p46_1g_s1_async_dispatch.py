from __future__ import annotations

import asyncio
import threading
from decimal import Decimal

import pytest

from apps.reference.bootstrap.async_runtime import AsyncLoopRuntime
from apps.reference.domains.execution_position.adapters.async_scheduling import (
    AsyncDispatchUnavailableError,
    AsyncSchedulingMixin,
)
from tests.domains.shadow_telemetry.p46_1f_runtime_harness import P46RuntimeHarness


class SchedulingProbe(AsyncSchedulingMixin):
    def __init__(self) -> None:
        self._async_loop = None


class RecordingVenueAdapter:
    network_enabled = False
    base_url = "https://testnet.invalid"

    def __init__(self) -> None:
        self.submit_calls: list[dict[str, str]] = []
        self.submitted = threading.Event()

    async def get_mark_price(self, symbol: str, **_kwargs) -> float:
        assert symbol == "ETHUSDT"
        return 2500.0

    async def place_market_entry(
        self,
        symbol: str,
        side: str,
        quantity: str,
        new_client_order_id: str,
    ) -> dict[str, str | int]:
        self.submit_calls.append({
            "symbol": symbol,
            "side": side,
            "quantity": str(quantity),
            "client_order_id": new_client_order_id,
        })
        self.submitted.set()
        return {
            "orderId": 1,
            "clientOrderId": new_client_order_id,
            "status": "NEW",
            "executedQty": "0",
            "avgPrice": "0",
        }

    async def place_limit_entry(
        self,
        symbol: str,
        side: str,
        price: str,
        quantity: str,
        *,
        time_in_force: str,
        new_client_order_id: str,
    ) -> dict[str, str | int]:
        self.submit_calls.append({
            "symbol": symbol,
            "side": side,
            "price": str(price),
            "quantity": str(quantity),
            "time_in_force": time_in_force,
            "client_order_id": new_client_order_id,
        })
        self.submitted.set()
        return {
            "orderId": 1,
            "clientOrderId": new_client_order_id,
            "status": "NEW",
            "executedQty": "0",
            "avgPrice": "0",
        }


async def _record_call(calls: list[str], called: threading.Event) -> None:
    calls.append(threading.current_thread().name)
    called.set()


def test_def_e11_reproducer_rejects_when_no_loop_without_adapter_call() -> None:
    probe = SchedulingProbe()
    calls: list[str] = []
    called = threading.Event()

    with pytest.raises(
        AsyncDispatchUnavailableError,
        match="canonical async loop is unavailable",
    ):
        probe._submit_async(_record_call(calls, called))

    assert calls == []
    assert not called.is_set()


def test_worker_thread_dispatch_uses_one_canonical_loop() -> None:
    runtime = AsyncLoopRuntime(name="P46S1CanonicalLoop")
    loop = runtime.start()
    probe = SchedulingProbe()
    probe.set_async_loop(loop)
    calls: list[str] = []
    called = threading.Event()

    try:
        future = probe._submit_async(_record_call(calls, called))
        assert future.result(timeout=2.0) is None
        assert called.is_set()
        assert calls == ["P46S1CanonicalLoop"]
        assert probe._get_async_loop() is loop
    finally:
        runtime.stop()


@pytest.mark.asyncio
async def test_dispatch_from_canonical_loop_creates_one_task() -> None:
    probe = SchedulingProbe()
    loop = asyncio.get_running_loop()
    probe.set_async_loop(loop)
    calls: list[str] = []
    called = threading.Event()

    task = probe._submit_async(_record_call(calls, called))
    await task

    assert called.is_set()
    assert len(calls) == 1


def test_stopped_and_closed_loops_fail_closed() -> None:
    runtime = AsyncLoopRuntime(name="P46S1StoppedLoop")
    loop = runtime.start()
    runtime.stop()
    probe = SchedulingProbe()

    with pytest.raises(AsyncDispatchUnavailableError):
        probe.set_async_loop(loop)

    assert probe._get_async_loop() is None


def test_real_http_tcp_fsm_path_reproduces_def_e11_without_loop(
    tmp_path,
    monkeypatch,
    caplog,
) -> None:
    harness = P46RuntimeHarness(tmp_path, monkeypatch)
    adapter = RecordingVenueAdapter()
    harness.adapter = adapter
    harness.execution_fsm.adapter = adapter
    harness.execution_fsm.shadow_mode = False

    harness.start()
    try:
        response = harness.post(harness.payload())
        assert response.status_code == 202
        harness.wait_for(lambda: len(harness.fsm_ingress) == 1)
        harness.wait_for(
            lambda: "DEF-E11: No async loop available" in caplog.text
        )
        assert adapter.submit_calls == []
        assert "DEF-E11: No async loop available" in caplog.text
    finally:
        harness.stop()


def test_real_http_tcp_worker_dispatch_reaches_recording_adapter_once(
    tmp_path,
    monkeypatch,
) -> None:
    harness = P46RuntimeHarness(tmp_path, monkeypatch)
    adapter = RecordingVenueAdapter()
    runtime = AsyncLoopRuntime(name="P46S1ExecutionLoop")
    loop = runtime.start()
    harness.adapter = adapter
    harness.execution_fsm.adapter = adapter
    harness.execution_fsm.shadow_mode = False
    harness.execution_fsm.set_async_loop(loop)

    harness.start()
    try:
        payload = harness.payload()
        response = harness.post(payload)
        assert response.status_code == 202
        assert adapter.submitted.wait(timeout=5.0)
        assert len(harness.command_emissions) == 1
        assert len(harness.fsm_ingress) == 1
        assert len(adapter.submit_calls) == 1
        assert Decimal(adapter.submit_calls[0]["quantity"]) > 0
        assert "qty" not in payload
        assert "quantity" not in payload

        duplicate = harness.post(payload)
        assert duplicate.status_code in (200, 202)
        assert len(harness.command_emissions) == 1
        assert len(harness.fsm_ingress) == 1
        assert len(adapter.submit_calls) == 1

        harness.send_tcp({
            "request_kind": "agent_trade_intent_v2",
            "request_id": "p46-s1-duplicate-tcp",
            **payload,
        })
        harness.wait_for(lambda: harness.bridge.command_envelope_count == 2)
        assert len(harness.command_emissions) == 1
        assert len(harness.fsm_ingress) == 1
        assert len(adapter.submit_calls) == 1

        conflict = dict(payload)
        conflict["side"] = "SELL"
        assert harness.post(conflict).status_code == 409
        assert len(harness.fsm_ingress) == 1
        assert len(adapter.submit_calls) == 1
    finally:
        harness.stop()
        runtime.stop()
