from __future__ import annotations

import logging
from types import SimpleNamespace

from apps.reference.domains.strategies.runtimes.md_amr.handler import MDAMRHandler


class _FSMStub:
    def get_domain(self, name: str):
        if name == "market_data":
            return SimpleNamespace(adapter=None)
        return None


class _FakeBinanceAdapter:
    last_rest_url: str | None = None

    def __init__(self, api_key: str, api_secret: str, rest_url: str) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.rest_url = rest_url
        _FakeBinanceAdapter.last_rest_url = rest_url


def _make_hybrid_handler() -> MDAMRHandler:
    handler = object.__new__(MDAMRHandler)
    handler.fsm = _FSMStub()
    handler.logger = logging.getLogger("tests.md_amr.hybrid")
    handler.mlog = logging.getLogger("tests.md_amr.hybrid")
    handler._cfg = SimpleNamespace(timeframe_sec=900)
    handler._enabled_symbols = {"XRPUSDT"}
    handler._rest_hydrated = False
    handler._rest_last_bar_ts_ms = {}
    handler._last_ingested_bar_ts_ms = {}
    handler.mandatory_warmup_until = 0
    handler.config = SimpleNamespace(
        trading_mode="hybrid_live_data_testnet_exec",
        trading=SimpleNamespace(mode="hybrid_live_data_testnet_exec"),
        binance_api=SimpleNamespace(
            live=SimpleNamespace(
                api_key="live-key",
                api_secret="live-secret",
                rest_url="https://live.example",
            ),
            testnet=SimpleNamespace(
                api_key="testnet-key",
                api_secret="testnet-secret",
                rest_url="https://testnet.example",
            ),
        ),
    )
    return handler


def test_md_amr_hybrid_startup_hydration_uses_live_market_data(monkeypatch) -> None:
    handler = _make_hybrid_handler()

    monkeypatch.setattr(
        "apps.reference.adapters.binance_adapter.BinanceAdapter",
        _FakeBinanceAdapter,
    )

    async def _fake_hydrate_state_from_rest_async(interval: str) -> int:
        adapter, temporary = handler._resolve_rest_adapter()
        assert interval == "15m"
        assert temporary is True
        assert isinstance(adapter, _FakeBinanceAdapter)
        assert adapter.rest_url == "https://live.example"
        assert _FakeBinanceAdapter.last_rest_url == "https://live.example"
        return 1

    handler._hydrate_state_from_rest_async = _fake_hydrate_state_from_rest_async

    handler._hydrate_state_from_rest()

    assert handler._rest_hydrated is True
    assert handler.mandatory_warmup_until > 0
