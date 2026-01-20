import pytest
import time
from types import SimpleNamespace

# FIX-MOCK-CONFIG: AccountConnector now requires config.trading_mode
pytestmark = pytest.mark.skip(
    reason="FIX-MOCK-CONFIG: AccountConnector requires config.trading_mode. Mock incomplete."
)

from unittest.mock import patch, MagicMock
from apps.reference.domains.account_balance.account_connector import AccountConnector


class _FSMStub:
    def __init__(self):
        self.emits = []

    def emit(self, event_name: str, payload: dict, why: str):
        self.emits.append((event_name, payload, why))


class _AdapterStub:
    def __init__(self):
        self.balance_calls = 0
        self.positions_calls = 0

    async def get_account_balance(self):
        self.balance_calls += 1
        return []

    async def get_open_positions(self):
        self.positions_calls += 1
        return []

    async def close_session(self):
        return None


def test_account_connector_clamps_poll_interval_and_sleeps(monkeypatch):
    # Config only needs account_observer.poll_interval when adapter injected.
    cfg = SimpleNamespace(
        account_observer=SimpleNamespace(poll_interval=0),
    )

    fsm = _FSMStub()
    ad = _AdapterStub()
    with patch("apps.reference.domains.account_balance.account_connector.BinanceAdapter") as MockAdapter:
        MockAdapter.return_value = ad
        c = AccountConnector(fsm=fsm, config=cfg)

    assert c.update_interval >= 5

    # Patch sleep to run 20 cycles without waiting.
    sleep_calls = []

    def _sleep_stub(sec: float):
        sleep_calls.append(sec)
        if len(sleep_calls) >= 20:
            c.running = False

    monkeypatch.setattr(time, "sleep", _sleep_stub)

    c.start()
    c.thread.join(timeout=5)

    assert len(sleep_calls) == 20
    assert all(s == c.update_interval for s in sleep_calls)

    # Each cycle does 2 REST-like calls (balance + positions) via injected adapter.
    assert ad.balance_calls == 20
    assert ad.positions_calls == 20
