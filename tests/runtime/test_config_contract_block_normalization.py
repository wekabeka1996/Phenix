
import pytest
from unittest.mock import MagicMock, patch, ANY
import time
from decimal import Decimal

from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.config_contract import ConfigContractError
from apps.reference.contracts.reject_reasons import RejectReason
from vfoundation.core.protocol import Message

class TestConfigContractNormalization:
    """
    TASK 17 Verified:
    Ensures that ConfigContractError is:
    1. Caught by the Central Catcher.
    2. Normalizes the reject reason (CFG_MISSING:...).
    3. Metrics are incremented.
    4. Trade intent is BLOCKED (no emission).
    """

    @pytest.fixture
    def decision_making(self):
        config_mock = MagicMock()
        # Minimal mock setup to bypass __init__ checks
        config_mock.instruments = {} 
        config_mock.decision = {}
        config_mock.tca_prefs = {}
        config_mock.risk_budgets = {}
        
        # Mocking DomainConfigResolver inside __init__ is hard without patching.
        # We'll use patch context in tests or just mock the dependencies.
        
        fsm_mock = MagicMock()
        with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver, \
             patch("apps.reference.domains.decision_making.decision_making.AuroraConfig") as MockAuroraCfg, \
             patch("apps.reference.domains.decision_making.decision_making.AuroraInstrumentConfig"):
             
            # Setup valid resolver defaults to avoid init crash
            mock_res_inst = MockResolver.return_value
            mock_res_inst.get_decision_making.return_value.qos.symbol_cooldown_sec = 1
            mock_res_inst.get_decision_making.return_value.qos.exposure_block_cooldown_sec = 0
            mock_res_inst.get_decision_making.return_value.qos.max_intents_per_minute_per_symbol = 100
            mock_res_inst.get_decision_making.return_value.qos.mode = "monitor"
            
            # Position sizing Mock
            mock_res_inst.get_decision_making.return_value.position_sizing.min_position_size_usd = 10
            mock_res_inst.get_decision_making.return_value.position_sizing.liquidity_based_cap_usd = 1000

            dm = DecisionMaking(fsm_mock, config_mock)
            
            # Mock internal state for on_features
            dm.symbol_states["BTCUSDT"] = {"features": {}, "risk": {}}
            return dm

    @patch("apps.reference.domains.decision_making.decision_making.inc_config_contract_violation")
    @patch("apps.reference.domains.decision_making.decision_making.normalize_config_error")
    def test_central_catcher_normalization(self, mock_normalize, mock_inc, decision_making):
        """
        Verify that a ConfigContractError raised deep in the stack
        is caught, normalized, and logged, and NO trade is emitted.
        """
        
        # Setup: Mock alpha_registry to raise ConfigContractError
        decision_making.alpha_registry = MagicMock()
        
        # Simulate a violation deep in alpha calculation
        contract_err = ConfigContractError(path="alpha.model.conf", why="Missing weights")
        decision_making.alpha_registry.calculate_all_alpha.side_effect = contract_err
        
        mock_normalize.return_value = "CFG_MISSING:alpha.model.conf"
        
        # Trigger on_features
        msg = Message(
            name="EVT:FEATURES_CALCULATED", 
            op="EVT", verb="FEATURES_CALCULATED", src="test", dst="dm",
            pld={"symbol": "BTCUSDT", "features": {"price": 100}}
        )
        
        # Act
        decision_making.on_features(msg)
        
        # Assert 1: Normalize called
        mock_normalize.assert_called_once_with(contract_err)
        
        # Assert 2: Metric incremented
        mock_inc.assert_called_once_with(path="alpha.model.conf", symbol="BTCUSDT")
        
        # Assert 3: FSM did NOT emit intent
        # (check fsm.emit calls, ensuring none are TRADE_INTENT_PROPOSED)
        for call in decision_making.fsm.emit.call_args_list:
            args, kwargs = call
            event_name = args[0] if args else kwargs.get("name")
            assert event_name != "EVT:TRADE_INTENT_PROPOSED", "Trade intent was incorrectly emitted for blocked config!"

    @patch("apps.reference.domains.decision_making.decision_making.inc_config_contract_violation")
    def test_mr_gateway_catcher(self, mock_inc, decision_making):
        """Verify catcher in strategy signal gateway (mean_reversion)."""
        with patch.object(
            decision_making,
            "_check_strategy_arbitration",
            side_effect=ConfigContractError(path="strat.registry", why="Missing"),
        ):
            msg = Message(
                op="EVT",
                verb="STRATEGY_SIGNAL_PRODUCED",
                src="strategy",
                dst="dm",
                pld={"strategy_id": "mean_reversion", "symbol": "BTCUSDT", "side": "BUY", "ts_ms": 123456789},
            )
            decision_making._on_strategy_signal_gateway(msg)

            mock_inc.assert_called_once()
            decision_making.fsm.emit.assert_not_called()
