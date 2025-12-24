import time

import pytest


class _FakeHandle:
    def __init__(self):
        self._cancelled = False

    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True


class _FakeLoop:
    def __init__(self):
        self.call_later_calls: list[float] = []

    def call_later(self, delay: float, _cb):
        self.call_later_calls.append(delay)
        return _FakeHandle()


def test_scheduler_uses_epoch_ms_for_delay(monkeypatch):
    from apps.reference.domains.decision_making.deferred_scheduler import DeferredIntentScheduler

    fake_loop = _FakeLoop()
    monkeypatch.setattr("asyncio.get_running_loop", lambda: fake_loop)

    # Freeze epoch time at 1000.000s => now_ms=1_000_000
    monkeypatch.setattr(time, "time", lambda: 1000.0)

    fired: list[str] = []

    def _cb(symbol: str) -> None:
        fired.append(symbol)

    s = DeferredIntentScheduler()
    s.schedule_once("BTCUSDT", 1_000_500, _cb)

    assert fake_loop.call_later_calls == [pytest.approx(0.5)]
    assert s.get_pending_count() == 1


def test_scheduler_deduplicates_per_symbol(monkeypatch):
    from apps.reference.domains.decision_making.deferred_scheduler import DeferredIntentScheduler

    fake_loop = _FakeLoop()
    monkeypatch.setattr("asyncio.get_running_loop", lambda: fake_loop)
    monkeypatch.setattr(time, "time", lambda: 1000.0)

    s = DeferredIntentScheduler()
    s.schedule_once("BTCUSDT", 1_001_000, lambda _s: None)
    s.schedule_once("BTCUSDT", 1_002_000, lambda _s: None)

    # Second call should be skipped due to dedup.
    assert len(fake_loop.call_later_calls) == 1
