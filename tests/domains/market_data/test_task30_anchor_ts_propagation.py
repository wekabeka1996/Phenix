from types import SimpleNamespace

import pytest

from apps.reference.domains.market_data.proxy import MarketDataProxy
from apps.reference.config_contract import ConfigContractError


class _DummyFsm:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict, str]] = []

    def emit(self, event_name: str, payload: dict, why: str = "") -> None:
        self.emitted.append((event_name, payload, why))

    def listen(self, _event_name: str, _callback) -> None:
        return


class _ProxyCfg:
    def __init__(self) -> None:
        self.instruments = {"BTCUSDT": {}}
        self.system = SimpleNamespace(
            market_data=SimpleNamespace(
                queue_maxsize=1000,
                proxy_batch_size=10,
                proxy_queue_get_timeout_sec=0.01,
                proxy_idle_sleep_sec=0.01,
            )
        )
        self.system_meta = SimpleNamespace(runtime=SimpleNamespace(config_name="test", config_dir="config/aurora"))

    def model_dump(self, mode: str = "json") -> dict:
        return {
            "instruments": {"BTCUSDT": {}},
            "system": {
                "market_data": {
                    "queue_maxsize": 1000,
                    "local_queue_maxsize": 1000,
                    "emit_workers": 1,
                    "tick_ttl_ms": 2000,
                    "ws_heartbeat_sec": 20.0,
                    "ws_receive_timeout_sec": 60.0,
                    "proxy_batch_size": 10,
                    "proxy_queue_get_timeout_sec": 0.01,
                    "proxy_idle_sleep_sec": 0.01,
                }
            },
            "trading": {"market_data": {"poll_interval_sec": 1, "macro_sync": {"anchors": ["BTCUSDT"]}}},
        }


def test_proxy_preserves_anchor_ts_ms_in_evt_payload():
    fsm = _DummyFsm()
    proxy = MarketDataProxy(fsm=fsm, config=_ProxyCfg())

    proxy._emit_anchor_update({"anchor": "BTCUSDT", "price": "100.0", "ts_ms": 1234567890000})

    assert len(fsm.emitted) == 1
    evt, payload, _why = fsm.emitted[0]
    assert evt == "EVT:ANCHOR_UPDATED"
    assert payload["anchor"] == "BTCUSDT"
    assert payload["price"] == "100.0"
    assert payload["ts_ms"] == 1234567890000


def test_feature_engineering_rejects_missing_anchor_ts_ms(monkeypatch):
    from apps.reference.config_loader import get_config
    from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering

    fsm = _DummyFsm()
    config = get_config()
    fe = FeatureEngineering(fsm=fsm, config=config, feature_store=None)
    monkeypatch.setattr(fe, "_log_features_to_file", lambda *_a, **_kw: None)

    with pytest.raises(ConfigContractError):
        fe.update_anchor_price("BTCUSDT", "100.0", None)

