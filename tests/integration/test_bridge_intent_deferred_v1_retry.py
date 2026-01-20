import pytest

pytestmark = pytest.mark.skip(reason="Refactoring: AuroraBridge class deleted")

import asyncio
import time
from types import SimpleNamespace

import pytest

from vfoundation.core.protocol import Message


class _FakeFSM:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}

    def listen(self, event: str, handler) -> None:  # type: ignore[no-untyped-def]
        self.listeners.setdefault(event, []).append(handler)

    def emit(self, _event: str, _payload: dict | None = None, _why: str | None = None, data_ref=None) -> None:  # type: ignore[no-untyped-def]
        return


@pytest.mark.asyncio
async def test_bridge_registers_v1_deferred_and_retry_scheduler_reemits(monkeypatch):
    """Integration: AuroraBridge.on_intent_deferred_sync -> RetryScheduler -> emit_compat(original_event)."""

    from apps.reference.main import AuroraBridge

    emitted = []

    async def _fake_emit_compat(_fsm, msg, logger=None):  # type: ignore[no-untyped-def]
        emitted.append(msg)

    monkeypatch.setattr("apps.reference.retry_scheduler.emit_compat", _fake_emit_compat)

    # Minimal config object (not dict) satisfying AuroraBridge init.
    # We avoid strict AuroraConfig here; only required fields are accessed.
    cfg = SimpleNamespace(
        domains=SimpleNamespace(position_tracking=SimpleNamespace(positions_stale_ttl_sec=15)),
        bridge=SimpleNamespace(
            retry_scheduler=SimpleNamespace(
                max_attempts=3,
                min_retry_delay_ms=0,
                backoff_factor=1.0,
                jitter_ms=0,
            )
        ),
        trading=SimpleNamespace(mode="testnet"),
    )

    fsm = _FakeFSM()
    bridge = AuroraBridge(fsm=fsm, config=cfg)  # type: ignore[arg-type]

    loop = asyncio.get_running_loop()
    bridge.retry_scheduler.bind_loop(loop)

    now_ms = int(time.time() * 1000)
    evt = Message(
        op="EVT",
        verb="INTENT_DEFERRED",
        src="decision_making",
        dst="bridge",
        rid="r1",
        pld={
            "retry_key": "flip:BTCUSDT:SELL:r1",
            "symbol": "BTCUSDT",
            "reason": "FLIP_CLOSE_PENDING",
            "next_allowed_ts": now_ms,
            "attempt": 1,
            "max_attempts": 3,
            "original_event": {
                "event_name": "EVT:FEATURES_CALCULATED",
                "payload_min": {"symbol": "BTCUSDT", "side": "SELL", "rid": "r1"},
            },
            "created_ts": now_ms,
            "why_chain": ["opposite_position_exists"],
        },
        why="intent_deferred:FLIP_CLOSE_PENDING",
    )

    bridge.on_intent_deferred_sync(evt)

    # Wait for retry task to run
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not emitted:
        await asyncio.sleep(0.01)

    assert emitted, "Expected RetryScheduler to emit original_event via emit_compat"
    msg = emitted[0]
    assert getattr(msg, "op", None) == "EVT"
    assert getattr(msg, "verb", None) == "FEATURES_CALCULATED"
    assert getattr(msg, "pld", None) == {"symbol": "BTCUSDT", "side": "SELL", "rid": "r1"}
