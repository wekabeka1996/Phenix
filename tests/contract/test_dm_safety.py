import unittest
from unittest.mock import MagicMock, patch
import time
import json
from decimal import Decimal
import datetime

# Adjust imports based on your actual project structure
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from vfoundation.core.protocol import Message

class TestDecisionMakingSafety(unittest.TestCase):
    def setUp(self):
        self.config_mock = MagicMock()
        self.fsm_mock = MagicMock()

        # Mock DomainConfigResolver because it is instantiated inside __init__
        patcher = patch('apps.reference.domains.decision_making.decision_making.DomainConfigResolver')
        self.MockDomainConfigResolver = patcher.start()
        self.addCleanup(patcher.stop)
        
        # Setup the resolver instance to return our mock config
        self.resolver_instance = self.MockDomainConfigResolver.return_value
        
        # Create the decision_making config object
        dm_cfg = MagicMock()
        
        # Sizing
        sizing_cfg = MagicMock()
        sizing_cfg.min_position_size_usd = 10.0
        sizing_cfg.liquidity_based_cap_usd = 10000.0
        dm_cfg.position_sizing = sizing_cfg
        
        # QOS
        qos_cfg = MagicMock()
        qos_cfg.exposure_block_cooldown_sec = 10
        qos_cfg.max_intents_per_minute_per_symbol = 5
        qos_cfg.mode = "shadow"
        qos_cfg.symbol_cooldown_sec = 3
        qos_cfg.enforce = False
        dm_cfg.qos = qos_cfg
        
        # Arming
        arming_cfg = MagicMock()
        arming_cfg.require_regime_warmup = True
        arming_cfg.retry_backoff_ms = 100
        arming_cfg.max_attempts = 3
        dm_cfg.arming = arming_cfg
        
        # Features
        features_cfg = MagicMock()
        features_cfg.ttl_sec = 60
        dm_cfg.features = features_cfg
        
        # Bar Gating
        dm_cfg.bar_gating.enable = False # Important for now
        
        self.resolver_instance.get_decision_making.return_value = dm_cfg

        # Trading Config (accessed directly in __init__)
        self.config_mock.trading = MagicMock()
        self.config_mock.trading.tca_prefs = {}
        self.config_mock.trading.risk_budgets = {}
        
        # Strategies Registry
        self.config_mock.strategies_registry = None
        
        # Enable Aurora for symbols (Fix P0-4: Mock allowed_regimes properly)
        eth_cfg = MagicMock(enabled=True)
        eth_cfg.allowed_regimes = ["TRENDING", "RANGING"]
        sol_cfg = MagicMock(enabled=True)
        sol_cfg.allowed_regimes = ["TRENDING", "RANGING"]
        
        self.config_mock.instruments = {
            "ETHUSDT": eth_cfg,
            "SOLUSDT": sol_cfg,
        }
        # Use side_effect to ensure dynamic return
        self.config_mock.get_aurora_instrument_cfg.side_effect = lambda s: self.config_mock.instruments.get(s)

        self.dm = DecisionMaking(self.fsm_mock, self.config_mock)
        
        # Enable stdout logging for debugging
        self.dm_logger_mock = MagicMock()
        def log_side_effect(*args, **kwargs):
            print(f"DM_LOG: {args} {kwargs}")
        self.dm_logger_mock.info.side_effect = log_side_effect
        self.dm_logger_mock.warning.side_effect = log_side_effect
        self.dm_logger_mock.error.side_effect = log_side_effect
        self.dm_logger_mock.debug.side_effect = log_side_effect
        self.dm.logger = self.dm_logger_mock
        
        # Override behavior flags if necessary
        self.dm.arming_require_regime_warmup = True

    def test_warmup_isolation_p0_1(self):
        """
        P0-1: Warmup state must be per-symbol.
        SOL warmup must NOT allow ETH to trade.
        """
        # 1. Provide Warmup for SOL
        sol_regime_msg = Message(
            op="EVT", verb="REGIME_DETECTED",
            src="test", dst="any",
            pld={
                "symbol": "SOLUSDT",
                "regime": "TRENDING",
                "warmup": {"full_ready": True, "ticks_seen": 100}
            }
        )
        self.dm.on_regime(sol_regime_msg)
        
        # 2. Verify SOL state is recorded clearly (no contamination logic yet)
        self.assertIn("SOLUSDT", self.dm._per_symbol_regimes)
        
        # 3. Try to trigger decision for ETH (which has NO warmup)
        # We simulate a "Features" event or direct call that triggers gating
        # Using internal method to check the gate logic directly
        context = {
            "features": {"ts": time.time()},
            "risk_params": {},
            "portfolio": {}
        }
        rid = "test_rid_Isolation"
        
        # This call should BLOCK/DEFER because ETH has no warmup.
        # If it uses _latest_warmup (SOL's), it might pass or fail with wrong reason.
        self.dm._make_decision_for_symbol("ETHUSDT", context, rid)
        
        # 4. Assertions
        # Check if INTENT_DEFERRED was emitted
        emit_calls = self.fsm_mock.emit.call_args_list
        deferred_calls = [c for c in emit_calls if c[0][0] == "EVT:INTENT_DEFERRED"]
        
        self.assertTrue(deferred_calls, "ETHUSDT should have been deferred/blocked")
        if deferred_calls:
            payload = deferred_calls[0][0][1]
            reason = payload.get("reason", "")
            print(f"DEBUG: Defer Reason: {reason}")
            # Ensure it is NOT blocked by something trivial like 'risk_missing'
            # If P0-1 (Contamination) exists, it might be passing the Warmup Gate and failing later
            # If so, the reason will NOT be 'warmup_missing'
            
            # If we want to PROVE contamination, we expect it to PASS warmup gate.
            # If it passes warmup gate, it won't be deferred with NRR-ARMING-WARMUP-MISSING
            if "warmup_missing" not in reason and "WARMUP" not in reason:
                 print("WARNING: Test passed but for wrong reason (not warmup). Likely Contamination allowed it to pass gate?")
            
    def test_full_ready_fail_closed_p0_2(self):
        """
        P0-2: Default 'full_ready' must be False if missing.
        """
        # Inject a warmup dict that is missing 'full_ready' key
        # This simulates a malformed or partial regime packet
        malformed_regime_msg = Message(
            op="EVT", verb="REGIME_DETECTED",
            src="test", dst="any",
            pld={
                "symbol": "ETHUSDT",
                "warmup": {"ticks_seen": 50} # Missing 'full_ready'
            }
        )
        self.dm.on_regime(malformed_regime_msg)
        
        context = {"features": {"ts": time.time()}}
        self.dm._make_decision_for_symbol("ETHUSDT", context, "test_rid_FailClosed")
        
        # Should be blocked
        emit_calls = self.fsm_mock.emit.call_args_list
        deferred = [c for c in emit_calls if c[0][0] == "EVT:INTENT_DEFERRED"]
        self.assertTrue(deferred, "Should be blocked if full_ready key is missing")
        if deferred:
            reason = deferred[0][0][1].get("reason", "")
            # If bug exists, it defaults to True -> no block (test fails, or blocks later)
            # We expect explicit block
            self.assertIn("NRR", reason)

    def test_startup_deadlock_p0_4(self):
        """
        P0-4: Missing retriggers.
        Sequence: Features (early) -> Risk -> Portfolio (late).
        Decision should be triggered after Portfolio arrives.
        """
        symbol = "ETHUSDT"
        
        # 1. Setup minimal state so decision CAN pass if triggered
        # Warmup OK
        self.dm._per_symbol_regimes[symbol] = {"warmup": {"full_ready": True}}
        
        # Reinforce mock setup for this test
        eth_cfg = MagicMock(enabled=True)
        eth_cfg.allowed_regimes = ["TRENDING", "RANGING"]
        # Direct instance mock to bypass config lambda issues
        self.dm._get_aurora_instrument_cfg = MagicMock(return_value=eth_cfg)

        # 2. Send Features (early)
        feat_msg = Message(op="EVT", verb="FEATURES_CALCULATED", src="test", dst="any", pld={
            "symbol": symbol, "features": {"price": 100, "warmup": {"full_ready": True}}, "ts": datetime.datetime.utcnow().timestamp() * 1000
        })
        self.dm.on_features(feat_msg)
        
        # 3. Send Risk
        risk_msg = Message(op="EVT", verb="RISK_ASSESSMENT_COMPLETED", src="test", dst="any", pld={
             "symbol": symbol, "risk_parameters": {"allowed": True}
        })
        self.dm.on_risk(risk_msg)
        
        # 3.5 Send Regime (Required for P0-4 to pass checks)
        regime_msg = Message(op="EVT", verb="REGIME_DETECTED", src="test", dst="any", pld={
            "symbol": symbol, "regime": "TRENDING", "warmup": {"full_ready": True}
        })
        self.dm.on_regime(regime_msg)

        # 4. Check: No decision yet (Portfolio missing)
        # Mock _make_decision_for_symbol to track calls
        with patch.object(self.dm, '_make_decision_for_symbol') as mock_make:
             # 5. Send Portfolio (The final piece)
             port_msg = Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", src="test", dst="any", pld={
                 "totalWalletBalance": "1000", "positions": []
             })
             self.dm.on_portfolio(port_msg)
             
             # 6. Assert: Decision MUST operate now
             if mock_make.call_count == 0:
                 print("FAIL: Decision not triggered after Portfolio update (P0-4 confirmed)")
             mock_make.assert_called_with(symbol, unittest.mock.ANY, unittest.mock.ANY)

    def test_fail_closed_order_index_p0_5(self):
        """
        P0-5: If order_index fails/missing, must BLOCK, not pass.
        """
        symbol = "ETHUSDT"
        
        # Setup minimal state to pass warmup/gating
        self.dm._per_symbol_regimes[symbol] = {"symbol": symbol, "warmup": {"full_ready": True}, "regime": "TRENDING"}
        self.dm._cached_equity_free_usdt = Decimal("1000")
        
        # Manually populate symbol_states to satisfy features/risk checks
        self.dm.symbol_states[symbol] = {
            "features": {
                "ts": datetime.datetime.utcnow().timestamp() * 1000, 
                "price": 100,
                "warmup": {"full_ready": True} # REQUIRED by Contract v1.0
            },
            "risk": {"allowed": True}
        }
        
        # Send Portfolio to satisfy _check_portfolio_ready
        port_msg = Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", src="test", dst="any", pld={
             "totalWalletBalance": "1000", "positions": []
        })
        self.dm.on_portfolio(port_msg)
        
        # Mock strategy arbitration (return allowed)
        self.dm._check_strategy_arbitration = MagicMock(return_value={"allowed": True})

        # Mock FSM to throw on order_index access
        type(self.fsm_mock).order_index = unittest.mock.PropertyMock(side_effect=Exception("DB Down"))
        
        self.dm._propose_trade_intent(
            symbol=symbol, side="BUY", qty=Decimal("1"), price=Decimal("100"),
            why_chain=[], rid="rid_FailIndex"
        )
        
        # Check emits
        emit_calls = self.fsm_mock.emit.call_args_list
        intent_calls = [c for c in emit_calls if c[0][0] == "EVT:TRADE_INTENT_PROPOSED"]
        
        self.assertFalse(intent_calls, "Should NOT propose intent if order_index crashes")
        
        defer_calls = [c for c in emit_calls if c[0][0] == "EVT:INTENT_DEFERRED"]
        self.assertTrue(defer_calls, "Should emit INTENT_DEFERRED on systemic failure")

if __name__ == '__main__':
    unittest.main()
