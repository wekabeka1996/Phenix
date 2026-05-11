from __future__ import annotations

import importlib
import sys

from fastapi.testclient import TestClient


MODULE_NAME = "apps.reference.api.main"
REQUIRED_ROUTES = {
    "/api/trading/context/latest",
    "/api/trading/positions/active",
    "/api/trading/rejections/recent",
    "/api/trading/market/overview",
}


def _load_api_module(trading_env: str):
    sys.modules.pop(MODULE_NAME, None)
    import os

    os.environ["TRADING_ENV"] = trading_env
    module = importlib.import_module(MODULE_NAME)
    return importlib.reload(module)


def _route_paths(module) -> set[str]:
    return {getattr(route, "path", None) for route in module.app.routes if getattr(route, "path", None)}


def test_trading_routes_registered_in_development():
    module = _load_api_module("development")
    assert REQUIRED_ROUTES.issubset(_route_paths(module))


def test_trading_routes_registered_in_production():
    module = _load_api_module("production")
    assert REQUIRED_ROUTES.issubset(_route_paths(module))


def test_trading_routes_use_degraded_read_models_for_ui_surfaces():
    module = _load_api_module("production")
    calls: dict[str, object] = {}

    class StubReadModels:
        def get_active_positions(self, *, allow_degraded: bool = False):
            calls["positions_allow_degraded"] = allow_degraded
            return [{"symbol": "BTCUSDT"}]

        def get_market_overview(
            self,
            *,
            symbols: list[str],
            tf_sec: int,
            allow_degraded: bool = False,
        ):
            calls["market_call"] = {
                "symbols": symbols,
                "tf_sec": tf_sec,
                "allow_degraded": allow_degraded,
            }
            return {
                "symbols": symbols,
                "snapshots": [],
                "active_positions": [],
                "recent_rejections": [],
                "risk_gate": {"available": False},
                "runtime_health": {"degraded": True},
            }

    module._trading_read_models = lambda: StubReadModels()
    client = TestClient(module.app)

    positions_response = client.get("/api/trading/positions/active")
    market_response = client.get(
        "/api/trading/market/overview",
        params={"symbols": "BTCUSDT,ETHUSDT", "tf_sec": 300},
    )

    assert positions_response.status_code == 200
    assert positions_response.json() == {"items": [{"symbol": "BTCUSDT"}]}
    assert market_response.status_code == 200
    assert calls["positions_allow_degraded"] is True
    assert calls["market_call"] == {
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "tf_sec": 300,
        "allow_degraded": True,
    }
