import pytest


class SpyFSM:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, str]] = []

    def emit(self, event_name: str, payload: dict, why: str | None = None, data_ref=None):
        self.events.append((event_name, payload, why or ""))


class DummyConfig:
    """Minimal non-dict config stub for MarketDataProxy init."""

    def __init__(self) -> None:
        # MarketDataProxy inspects instruments keys for logging
        self.instruments = {"DOGEUSDT": {}, "XRPUSDT": {}}


def test_market_data_proxy_emits_forwarded_alias():
    from apps.reference.domains.market_data.proxy import MarketDataProxy

    fsm = SpyFSM()
    cfg = DummyConfig()

    md = MarketDataProxy(fsm=fsm, config=cfg)

    tick = {
        "symbol": "DOGEUSDT",
        "data": {
            "ts": 1700000000123,
            "price": "0.1",
            "bid": "0.099",
            "ask": "0.101",
            "mid": "0.1",
            "bid_size": "1",
            "ask_size": "1",
            "buy_volume": "0",
            "sell_volume": "0",
        },
    }

    md._emit_tick(tick)

    names = [e[0] for e in fsm.events]
    assert "EVT:MARKET_TICK_RECEIVED" in names
    assert "EVT:MARKET_TICK_FORWARDED" in names

    received = next(p for (n, p, _) in fsm.events if n == "EVT:MARKET_TICK_RECEIVED")
    forwarded = next(p for (n, p, _) in fsm.events if n == "EVT:MARKET_TICK_FORWARDED")
    assert forwarded == received


def test_market_data_proxy_forwarded_guard_dedup_by_ts():
    from apps.reference.domains.market_data.proxy import MarketDataProxy

    fsm = SpyFSM()
    cfg = DummyConfig()
    md = MarketDataProxy(fsm=fsm, config=cfg)

    tick = {
        "symbol": "DOGEUSDT",
        "data": {
            "ts": 1700000000123,
            "price": "0.1",
            "bid": "0.099",
            "ask": "0.101",
            "mid": "0.1",
            "bid_size": "1",
            "ask_size": "1",
            "buy_volume": "0",
            "sell_volume": "0",
        },
    }

    md._emit_tick(tick)
    md._emit_tick(tick)  # identical ts

    forwarded_count = sum(1 for (n, _, __) in fsm.events if n == "EVT:MARKET_TICK_FORWARDED")
    assert forwarded_count == 1
