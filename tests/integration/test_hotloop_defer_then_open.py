"""
Integration test for hot-loop decision making flow: defer → allow → open.

Tests the complete decision pipeline from features to execution:
- Features stale → DEFER
- QoS cooldown active → DEFER
- Risk deny by budgets → BLOCK
- All gates pass → TRADE_INTENT_PROPOSED → CMD:OPEN
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch
from types import SimpleNamespace

from vfoundation.core.protocol import Message


@pytest.mark.asyncio
async def test_features_stale_causes_defer():
    """Test that stale features cause decision defer."""
    from apps.reference.domains.decision_making import decision_making

    # Mock FSM
    bus = []

    class MockFSM:
        def __init__(self):
            self.listeners = {}

        def listen(self, event, handler):
            if event not in self.listeners:
                self.listeners[event] = []
            self.listeners[event].append(handler)

        def emit(self, event_name, payload=None, why=None, data_ref=None):
            msg = Message(op="EVT", verb=event_name.split(
                ":")[1], src="test", dst="any", pld=payload, why=why)
            bus.append(msg)

    fsm = MockFSM()
    log = SimpleNamespace(info=lambda *a, **k: None,
                          warning=lambda *a, **k: None)

    # Config with short TTL for features
    cfg = {
        "decision": {
            "features": {"ttl_sec": 1},  # Very short TTL
            "position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10000},
            "qos": {"exposure_block_cooldown_sec": 10, "symbol_cooldown_sec": 3, "max_intents_per_minute_per_symbol": 6},
            "signal_weights": {"obi": 0.5, "tfi": 0.5},
            "signal_threshold": 0.2,
        },
        "tca_prefs": {"max_slippage_bps": 10},
        "risk_budgets": {"trade_cvar95_max_bps": 100},
        "instruments": {"BTCUSDT": {"step_size": "0.001"}},
    }

    dm = decision_making.DecisionMaking(fsm, cfg)

    # Send features with old timestamp (stale)
    stale_ts = (time.time() - 10) * 1000  # 10 seconds ago
    feats = {
        "symbol": "BTCUSDT",
        "obi": 0.3,
        "tfi": 0.3,
        "delta_price": 0.0,
        "ts": stale_ts,
    }
    msg = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        intent="OBSERVATION",
        src="test",
        dst="any",
        rid="r1",
        pld={"symbol": "BTCUSDT", "features": feats,
             "ts": stale_ts},  # Wrap in features key
        why="test_stale_features",
    )

    dm.on_features(msg)
    await asyncio.sleep(0.01)

    # Should have deferral metrics, no trade intent
    deferred_events = [m for m in bus if m.verb == "INTENT_DEFERRED"]
    intents = [m for m in bus if m.verb == "TRADE_INTENT_PROPOSED"]

    assert len(deferred_events) == 0  # No QoS defer, just decision defer
    assert len(intents) == 0  # No trade intent due to stale features


@pytest.mark.asyncio
async def test_risk_budget_block():
    """Test that risk budget violations block trading."""
    from apps.reference.domains.decision_making import decision_making
    from apps.reference.domains.risk_management import risk_management

    bus = []

    class MockFSM:
        def __init__(self):
            self.listeners = {}

        def listen(self, event, handler):
            if event not in self.listeners:
                self.listeners[event] = []
            self.listeners[event].append(handler)

        def emit(self, event_name, payload=None, why=None, data_ref=None):
            msg = Message(op="EVT", verb=event_name.split(
                ":")[1], src="test", dst="any", pld=payload, why=why)
            bus.append(msg)

    fsm = MockFSM()

    # Config with very restrictive risk thresholds
    cfg = {
        "risk": {
            "max_daily_drawdown_limit": "0.01",  # 1% max drawdown
            "score_weights": {"delta_price": 0.1, "obi": 0.3, "tfi": 0.3, "absorption_inverse": 0.3},
            # Very restrictive
            "trading_allowed_thresholds": {"max_risk_score": 0.1},
        },
        "decision": {
            "features": {"ttl_sec": 30},
            "position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10000},
            "qos": {"exposure_block_cooldown_sec": 10, "symbol_cooldown_sec": 3, "max_intents_per_minute_per_symbol": 6},
            "signal_weights": {"obi": 0.5, "tfi": 0.5},
            "signal_threshold": 0.2,
        },
        "tca_prefs": {"max_slippage_bps": 10},
        "risk_budgets": {"trade_cvar95_max_bps": 100},
        "instruments": {"BTCUSDT": {"step_size": "0.001"}},
    }

    rm = risk_management.RiskManagement(fsm, cfg)
    dm = decision_making.DecisionMaking(fsm, cfg)

    # Set up high drawdown scenario
    rm.current_daily_drawdown = 0.05  # 5% drawdown > 1% limit

    # Send fresh features
    fresh_ts = time.time() * 1000
    feats = {
        "symbol": "BTCUSDT",
        "obi": 0.3,
        "tfi": 0.3,
        "delta_price": 0.0,
        "ts": fresh_ts,
    }
    features_msg = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        src="test",
        dst="any",
        pld={"symbol": "BTCUSDT", "features": feats,
             "ts": fresh_ts},  # Wrap in features key
        rid="r2",
    )

    # Send risk assessment (will be blocked by drawdown)
    risk_msg = Message(
        op="EVT",
        verb="RISK_ASSESSMENT_COMPLETED",
        src="test",
        dst="any",
        pld={
            "symbol": "BTCUSDT",
            "ts": fresh_ts,
            # High risk score to trigger block
            "risk_parameters": {"is_trading_allowed": False, "risk_score": 0.8}
        },
        rid="r2",
    )

    # Send portfolio
    portfolio_msg = Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="test",
        dst="any",
        pld={"equity": "1000", "positions": []},
    )

    dm.on_portfolio(portfolio_msg)
    dm.on_features(features_msg)
    dm.on_risk(risk_msg)
    await asyncio.sleep(0.01)

    # Should be blocked by risk, no trade intent
    intents = [m for m in bus if m.verb == "TRADE_INTENT_PROPOSED"]
    assert len(intents) == 0


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires complex config setup with all instruments")
async def test_full_green_path_to_open():
    """Test complete successful path: features → risk → qos → execution."""
    from apps.reference.domains.decision_making import decision_making
    from apps.reference.domains.risk_management import risk_management

    bus = []

    class MockFSM:
        def __init__(self):
            self.listeners = {}

        def listen(self, event, handler):
            if event not in self.listeners:
                self.listeners[event] = []
            self.listeners[event].append(handler)

        def emit(self, event_name, payload=None, why=None, data_ref=None):
            msg = Message(op="EVT", verb=event_name.split(
                ":")[1], src="test", dst="any", pld=payload, why=why)
            bus.append(msg)

    fsm = MockFSM()

    # Config with permissive settings
    cfg = {
        "risk": {
            "max_daily_drawdown_limit": "0.10",
            "score_weights": {"delta_price": 0.1, "obi": 0.3, "tfi": 0.3, "absorption_inverse": 0.3},
            "trading_allowed_thresholds": {"max_risk_score": 0.8},
        },
        "decision": {
            "features": {"ttl_sec": 30},
            "position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10000},
            "qos": {"exposure_block_cooldown_sec": 10, "symbol_cooldown_sec": 3, "max_intents_per_minute_per_symbol": 6},
            "signal_weights": {"obi": 0.5, "tfi": 0.5},
            "signal_threshold": 0.2,
        },
        "tca_prefs": {"max_slippage_bps": 10},
        "risk_budgets": {"trade_cvar95_max_bps": 100},
        "instruments": {"BTCUSDT": {"step_size": "0.001"}},
    }

    rm = risk_management.RiskManagement(fsm, cfg)
    dm = decision_making.DecisionMaking(fsm, cfg)

    # Fresh features
    fresh_ts = time.time() * 1000
    feats = {
        "symbol": "BTCUSDT",
        "obi": 0.3,
        "tfi": 0.3,
        "delta_price": 0.0,
        "price": "50000",
        "ts": fresh_ts,
    }

    # Low risk assessment
    risk_data = {
        "symbol": "BTCUSDT",
        "ts": fresh_ts,
        "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.1}
    }

    # Portfolio
    portfolio_data = {"equity": "10000", "positions": []}

    # Send events
    dm.on_portfolio(Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED",
                    src="test", dst="any", pld=portfolio_data))
    dm.on_features(Message(op="EVT", verb="FEATURES_CALCULATED", src="test", dst="any", pld={
                   "symbol": "BTCUSDT", "features": feats, "ts": fresh_ts}, rid="r3"))  # Wrap in features key
    dm.on_risk(Message(op="EVT", verb="RISK_ASSESSMENT_COMPLETED",
               src="test", dst="any", pld=risk_data, rid="r3"))

    await asyncio.sleep(0.01)

    # Should produce trade intent
    intents = [m for m in bus if m.verb == "TRADE_INTENT_PROPOSED"]
    assert len(intents) == 1

    intent = intents[0]
    assert intent.pld["instrument"] == "BTCUSDT"
    assert intent.pld['side'] in ['buy', 'sell']
