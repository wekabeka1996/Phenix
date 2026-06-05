from apps.reference.domains.market_data.proxy import MarketDataProxy


class _DummyConfig:
    def __init__(self):
        self.instruments = {"BTCUSDT": object()}

    def model_dump(self, mode="json"):
        return {"instruments": {"BTCUSDT": {}}}

    def to_dict(self):
        raise AssertionError("MarketDataProxy must not call config.to_dict()")


def test_task25_market_data_proxy_no_config_to_dict():
    proxy = MarketDataProxy(fsm=object(), config=_DummyConfig())
    cfg = proxy._get_config_dict()
    assert isinstance(cfg, dict)

