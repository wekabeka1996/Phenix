
import logging
import time
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import Dict, Any, Optional

# Mock Message
@dataclass
class Message:
    op: str
    verb: str
    pld: Any
    rid: str = "test_rid"

# Mock Config Structures
class MockSystemMarketData:
    bar_ttl_ms = 10000
    bar_event_age_mode = "received"
    tick_ttl_ms = 2000

class MockSystem:
    market_data = MockSystemMarketData()

class MockFeaturesConfig:
    ttl_sec = 2.0  # Tick TTL

class MockDomainConfig:
    def __init__(self):
        self.features = MockFeaturesConfig()
        self.arming = MagicMock()
        self.qos = MagicMock()
        self.position_sizing = MagicMock()
        self.risk_skew = MagicMock()
        self.regime_thresholds = {}
        self.regime_threshold_multipliers = {}
        self.gates = MagicMock()
        self.behavior_fsm = MagicMock()
        self.bar_gating = MagicMock()
        # Defaults
        self.arming.require_regime_warmup = False
        self.arming.retry_backoff_ms = 100
        self.arming.max_attempts = 1
        self.features.ttl_sec = 2.0
        self.qos.mode = "performance"
        self.qos.symbol_cooldown_sec = 0
        self.qos.enforce = False
        
        self.position_sizing.min_position_size_usd = 10.0
        self.position_sizing.max_position_notional = 1000.0
        self.position_sizing.min_notional_hard_stop = 5.0
        self.position_sizing.liquidity_based_cap_usd = 50000.0
        self.position_sizing.max_position_notional_hard_stop = 2000.0
        
        self.risk_skew.enabled = False
        
        # Ensure gate configs are present (mocks by default)

class MockThresholds:
    max_risk_score = 100.0

class MockRiskMgmt:
    trading_allowed_thresholds = MockThresholds()

class MockDMCfg:
    enabled = True

class MockDomainsConfig:
    risk_management = MockRiskMgmt()
    position_tracking = MagicMock() # Just in case
    decision_making = MockDMCfg()

class MockConfig:
    system = MockSystem()
    trading = MagicMock()
    strategies_registry = None
    domains = MockDomainsConfig()

class MockClock:
    def __init__(self):
        self._now = 100000.0  # ms
        
    def now_ms(self):
        return self._now
    
    def now_sec(self):
        return self._now / 1000.0
    
    def advance(self, ms):
        self._now += ms

# Import target
from apps.reference.domains.decision_making.decision_making import DecisionMaking

class TestBarTTLFreshness:
    
    @pytest.fixture
    def clock(self):
        return MockClock()
        
    @pytest.fixture
    def dm(self, clock):
        with patch('apps.reference.domains.decision_making.decision_making.DomainConfigResolver') as mock_resolver:
            mock_resolver.return_value.get_decision_making.return_value = MockDomainConfig()
            
            # Instantiate (fsm first, config second)
            dm = DecisionMaking(MagicMock(), MockConfig())
            dm._clock = clock
            # Do NOT overwrite symbol_states (it's a defaultdict)
            # dm.symbol_states = {}
            
            # Setup mocks
            dm._record_blocked_intent = MagicMock()
            dm.logger = MagicMock()
            # Stubs
            dm._precheck_exposure_cache = MagicMock(return_value=True)
            dm._warmup_gate_before_trade_intent = MagicMock(return_value=True)
            dm._check_regime_thresholds = MagicMock(return_value=True)
            dm._check_anti_pyramiding = MagicMock(return_value=False)
            dm._check_min_notional = MagicMock(return_value=True)
            dm._evaluate_side_bias = MagicMock(return_value=1.0)
            dm._handle_flip_orchestration = MagicMock(return_value=None) # Assume no flip needed
            
            # Setup symbol state manually if needed or rely on on_features
            
            return dm

    def test_bar_late_arrival_accepted(self, dm, clock):
        """
        Verify that a Bar event arriving late (e.g. 5s lag) is ACCEPTED
        because bar_ttl_ms=10s and mode=received uses arrival time.
        """
        symbol = "BTCUSDT"
        
        # 1. Simulate Bar Event emission 5s ago
        emit_ts = clock.now_ms() - 5000 
        payload = {
            "symbol": symbol,
            "ts": emit_ts,
            "tf_sec": 300,  # Is Bar
            "features": {"price": 100.0}
        }
        
        # 2. Receive NOW 
        # on_features injects _received_ts = now
        dm.on_features(Message("EVT", "FEATURES", payload))
        
        # Inject valid Risk state state to pass risk gate
        dm.symbol_states[symbol]["risk"] = {
             "risk_parameters": {
                 "is_trading_allowed": True,
                 "risk_score": 0.0
             }
        }
        
        # Verify state
        state = dm.symbol_states[symbol]["features"]
        assert state["ts"] == emit_ts
        assert state["_received_ts"] == clock.now_ms()
        
        # 3. Process Signal
        signal_pld = {
            "symbol": symbol,
            "side": "LONG",
            "qty": "1.0",
            "price": "100.0",
            "strategy_id": "test_strat",
            "rid": "test_rid"
        }
        msg = Message("EVT", "SIGNAL", signal_pld)
        
        # Act
        dm._on_strategy_signal_gateway(msg)
        
        # Assert: Blocked count NOT incremented
        dm._record_blocked_intent.assert_not_called()

    def test_tick_late_arrival_rejected(self, dm, clock):
        """
        Verify that a Tick event arriving late (5s lag) is REJECTED
        because tick_ttl=2s (uses domain config).
        """
        symbol = "ETHUSDT"
        
        emit_ts = clock.now_ms() - 5000 
        payload = {
            "symbol": symbol,
            "ts": emit_ts,
            "tf_sec": 0,  # Is Tick
            "features": {"price": 100.0}
        }
        
        dm.on_features(Message("EVT", "FEATURES", payload))
        
        # Inject valid Risk
        dm.symbol_states[symbol]["risk"] = {
             "risk_parameters": {
                 "is_trading_allowed": True,
                 "risk_score": 0.0
             }
        }
        
        signal_pld = {
            "symbol": symbol,
            "side": "LONG",
            "qty": "1.0",
            "price": "100.0",
            "strategy_id": "test_strat",
            "rid": "test_rid"
        }
        msg = Message("EVT", "SIGNAL", signal_pld)
        
        dm._on_strategy_signal_gateway(msg)
        
        # Assert: Blocked called
        dm._record_blocked_intent.assert_called_with(symbol)
        
        # Verify log message mentioning stale
        args, _ = dm.logger.info.call_args
        assert "Features stale" in args[0]

    def test_bar_excessive_lag_rejected(self, dm, clock):
        """
        Verify that a Bar event arriving VERY late (>10s) is REJECTED
        even with bar logic.
        """
        symbol = "SOLUSDT"
        
        # Emit 15s ago
        emit_ts = clock.now_ms() - 15000
        
        payload = {
            "symbol": symbol,
            "ts": emit_ts,
            "tf_sec": 300, 
            "features": {"price": 100.0}
        }
        
        dm.on_features(Message("EVT", "FEATURES", payload))
        
        # Inject valid Risk
        dm.symbol_states[symbol]["risk"] = {
             "risk_parameters": {
                 "is_trading_allowed": True,
                 "risk_score": 0.0
             }
        }
        
        signal_pld = {
            "symbol": symbol,
            "side": "LONG",
            "qty": "1.0",
            "price": "100.0",
            "strategy_id": "test_strat",
            "rid": "test_rid"
        }
        msg = Message("EVT", "SIGNAL", signal_pld)
        
        # 1. received mode (age=0) -> Accepted
        dm._on_strategy_signal_gateway(msg)
        dm._record_blocked_intent.assert_not_called()
        
        # 2. close_ts mode (age=15s) -> Rejected
        dm.config.system.market_data.bar_event_age_mode = "close_ts"
        
        dm._on_strategy_signal_gateway(msg)
        dm._record_blocked_intent.assert_called_with(symbol)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
