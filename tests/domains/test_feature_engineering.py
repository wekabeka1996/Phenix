"""Unit tests for FeatureEngineering domain."""

import decimal
import time
from unittest import mock

import pytest

from vfoundation.core.protocol import Message


class FSMCoreMock:
    def __init__(self):
        self.listeners = {}
        self.emitted = []

    def listen(self, event_name: str, callback):
        self.listeners.setdefault(event_name, []).append(callback)

    def emit(self, event_name: str, payload: dict, why: str = ""):
        self.emitted.append((event_name, payload, why))


@pytest.fixture
def fsm():
    return FSMCoreMock()


@pytest.fixture
def config():
    return {}


def make_tick(
    ts=None,
    price="50000.00",
    bid_size="10",
    ask_size="8",
    buy_volume="50",
    sell_volume="30",
):
    if ts is None:
        ts = int(time.time() * 1000)
    return {
        "ts": ts,
        "symbol": "BTCUSDT",
        "price": decimal.Decimal(price),
        "bid": decimal.Decimal(price),
        "ask": decimal.Decimal(price),
        "mid": decimal.Decimal(price),
        "bid_size": decimal.Decimal(bid_size),
        "ask_size": decimal.Decimal(ask_size),
        "buy_volume": decimal.Decimal(buy_volume),
        "sell_volume": decimal.Decimal(sell_volume),
        "data_source": "test",
    }


def test_no_symbol_no_emit(fsm, config):
    from apps.reference.domains.feature_engineering.feature_engineering import (
        FeatureEngineering,
    )

    fe = FeatureEngineering(fsm=fsm, config=config)

    # Create a message without symbol
    msg = Message(op="EVT", verb="MARKET_TICK_RECEIVED", src="test", dst="fe", pld={})
    # Should not raise and should not emit
    fe.on_market_tick(msg)
    assert len(fsm.emitted) == 0


def test_first_tick_only_stored(fsm, config):
    from apps.reference.domains.feature_engineering.feature_engineering import (
        FeatureEngineering,
    )

    fe = FeatureEngineering(fsm=fsm, config=config)

    tick = make_tick()
    msg = Message(op="EVT", verb="MARKET_TICK_RECEIVED", src="test", dst="fe", pld=tick)
    fe.on_market_tick(msg)

    # No emission on first tick
    assert len(fsm.emitted) == 0


def test_calculate_and_emit_features_basic(fsm, config):
    from apps.reference.domains.feature_engineering.feature_engineering import (
        FeatureEngineering,
    )

    fe = FeatureEngineering(fsm=fsm, config=config)

    ts0 = int(time.time() * 1000)
    last = make_tick(
        ts=ts0,
        price="50000.00",
        bid_size="10",
        ask_size="8",
        buy_volume="50",
        sell_volume="30",
    )
    current = make_tick(
        ts=ts0 + 500,
        price="50050.00",
        bid_size="12",
        ask_size="6",
        buy_volume="60",
        sell_volume="20",
    )

    fe.last_tick_data["BTCUSDT"] = last

    msg = Message(
        op="EVT", verb="MARKET_TICK_RECEIVED", src="test", dst="fe", pld=current
    )
    fe.on_market_tick(msg)

    # One FEATURES_CALCULATED should be emitted
    assert len(fsm.emitted) == 1
    event_name, payload, why = fsm.emitted[0]
    assert event_name == "EVT:FEATURES_CALCULATED"
    assert payload["symbol"] == "BTCUSDT"
    features = payload["features"]
    # obi = (bid_size - ask_size) / (bid_size + ask_size) = (12-6)/(18)=6/18=0.333...
    assert float(features["obi"]) == pytest.approx(0.3333333, rel=1e-3)
    # tfi = (buy - sell)/(buy+sell) = (60-20)/(80)=40/80=0.5
    assert float(features["tfi"]) == pytest.approx(0.5, rel=1e-6)
    # delta_price = 50050 - 50000 = 50 (time_diff < 1000)
    assert float(features["delta_price"]) == pytest.approx(50.0, rel=1e-6)


def test_delta_price_suppressed_when_time_diff_large(fsm, config):
    from apps.reference.domains.feature_engineering.feature_engineering import (
        FeatureEngineering,
    )

    fe = FeatureEngineering(fsm=fsm, config=config)

    ts0 = int(time.time() * 1000)
    last = make_tick(ts=ts0, price="50000.00")
    current = make_tick(ts=ts0 + 2000, price="50050.00")

    fe.last_tick_data["BTCUSDT"] = last
    msg = Message(
        op="EVT", verb="MARKET_TICK_RECEIVED", src="test", dst="fe", pld=current
    )
    fe.on_market_tick(msg)

    assert len(fsm.emitted) == 1
    _, payload, _ = fsm.emitted[0]
    features = payload["features"]
    assert float(features["delta_price"]) == pytest.approx(0.0, rel=1e-9)


"""
Integration test for feature_engineering domain.
"""
from unittest import mock
import pytest
import time
from vfoundation.core.protocol import Message
from apps.reference.domains.feature_engineering.feature_engineering import (
    FeatureEngineering,
)


@pytest.fixture
def mock_config():
    """Mock configuration for feature engineering tests."""
    return {}


class FSMCore:
    """Simple FSM core interface for testing."""

    def __init__(self):
        self.listeners = {}

    def listen(self, event_name, callback):
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def emit(self, event_name, payload, why):
        if event_name in self.listeners:
            for callback in self.listeners[event_name]:
                callback(
                    Message(
                        op="EVT",
                        verb=event_name.split(":")[1],
                        src="test",
                        dst="any",
                        pld=payload,
                        why=why,
                    )
                )


def test_feature_engineering_consumes_tick_and_emits_features(mock_config):
    """Test that feature_engineering consumes a tick and emits features."""
    fsm = FSMCore()
    mock_listener = mock.Mock()
    fsm.listen("EVT:FEATURES_CALCULATED", mock_listener)
    feature_component = FeatureEngineering(fsm=fsm, config=mock_config)

    # Send two ticks to get a delta_price
    tick1 = {
        "ts": int(time.time() * 1000) - 100,
        "symbol": "BTCUSDT",
        "price": "50000",
        "bid_size": "1",
        "ask_size": "1",
        "buy_volume": "1",
        "sell_volume": "1",
    }
    tick2 = {
        "ts": int(time.time() * 1000),
        "symbol": "BTCUSDT",
        "price": "50010",
        "bid_size": "1",
        "ask_size": "1",
        "buy_volume": "1",
        "sell_volume": "1",
    }

    feature_component.on_market_tick(
        Message(
            op="EVT", verb="MARKET_TICK_RECEIVED", src="test", dst="test", pld=tick1
        )
    )
    feature_component.on_market_tick(
        Message(
            op="EVT", verb="MARKET_TICK_RECEIVED", src="test", dst="test", pld=tick2
        )
    )

    mock_listener.assert_called_once()
    features = mock_listener.call_args[0][0].pld["features"]
    assert features["delta_price"] == "10"
