import threading
import time

from apps.reference.main import AuroraBridge, _run_async_loop
from vfoundation.core.protocol import Message


class _FSMStub:
    def __init__(self):
        self.emitted = []

    def listen(self, *_args, **_kwargs):
        return None

    def emit(self, *args, **kwargs):
        # Prefer Message API (used by emit_compat in RetryScheduler)
        if len(args) == 1 and isinstance(args[0], Message):
            self.emitted.append(args[0])
            return None
        # Fallback: record raw emit signatures if they occur
        self.emitted.append((args, kwargs))
        return None


def test_retry_scheduler_reemits_original_event_once():
    fsm = _FSMStub()
    bridge = AuroraBridge(
        fsm=fsm,  # type: ignore[arg-type]
        config={"bridge": {"retry_scheduler": {"min_retry_delay_ms": 10, "max_attempts": 3}}},
    )

    import asyncio

    loop = asyncio.new_event_loop()
    t = threading.Thread(target=_run_async_loop, args=(loop,), daemon=True)
    t.start()
    bridge.retry_scheduler.bind_loop(loop)

    now_ms = int(time.time() * 1000)
    retry_key = "test:BTCUSDT:rid-1"
    deferred_evt = Message(
        op="EVT",
        verb="INTENT_DEFERRED",
        src="test",
        dst="*",
        rid="rid-defer-1",
        pld={
            "retry_key": retry_key,
            "symbol": "BTCUSDT",
            "reason": "NRR-PORTFOLIO-UNKNOWN",
            "next_allowed_ts": now_ms + 50,
            "attempt": 1,
            "max_attempts": 3,
            "original_event": {
                "event_name": "EVT:MR_SIGNAL_PRODUCED",
                "payload_min": {"symbol": "BTCUSDT", "side": "BUY", "rid": "rid-1", "ts": now_ms},
            },
            "why_chain": ["test"],
            "created_ts": now_ms,
        },
    )

    # Register twice: must remain idempotent by retry_key (SSOT)
    bridge.on_intent_deferred_sync(deferred_evt)
    bridge.on_intent_deferred_sync(deferred_evt)

    time.sleep(0.3)

    reemitted = [m for m in fsm.emitted if isinstance(m, Message) and m.verb == "MR_SIGNAL_PRODUCED"]
    assert len(reemitted) == 1

    loop.call_soon_threadsafe(loop.stop)
    t.join(timeout=2)
    loop.close()

