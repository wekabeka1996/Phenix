import pytest
from unittest.mock import MagicMock, patch, ANY
import time
from decimal import Decimal

from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.config_contract import ConfigContractError
from apps.reference.contracts.reject_reasons import RejectReason
from vfoundation.core.protocol import Message
from vfoundation.dr import wal
from tests.conftest import make_app_cfg_stub

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
        config_mock = make_app_cfg_stub(
            instruments={},
            decision={},
            tca_prefs={},
            risk_budgets={},
            domains__decision_making__flip__enabled=True
        )
        
        fsm_mock = MagicMock()
        with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver, \
             patch("apps.reference.domains.decision_making.decision_making.AuroraConfig") as MockAuroraCfg, \
             patch("apps.reference.config_models.AuroraInstrumentConfig"):
             
            # Setup valid resolver defaults to avoid init crash
            mock_res_inst = MockResolver.return_value
            mock_res_inst.get_decision_making.return_value = config_mock.domains.decision_making

            dm = DecisionMaking(fsm_mock, config_mock)
            
            # Mock internal state for on_features
            dm.symbol_states["BTCUSDT"] = {"features": {}, "risk": {}}
            return dm

    @pytest.fixture(autouse=True)
    def _isolate_wal_dir(self, tmp_path):
        prev = wal.WAL_DIR
        wal.set_wal_dir(tmp_path / "wal")
        wal.reset()
        yield
        wal.set_wal_dir(prev)

    @patch("apps.reference.domains.decision_making.event_handlers.inc_config_contract_violation")
    @patch("apps.reference.domains.decision_making.event_handlers.normalize_config_error")
    def test_central_catcher_normalization(self, mock_normalize, mock_inc, decision_making):
        """
        Verify that a ConfigContractError raised deep in the stack
        is caught, normalized, and logged, and NO trade is emitted.
        """
        
        # Setup: Mock alpha_registry to raise ConfigContractError
        decision_making.alpha_registry = MagicMock()
        decision_making._evt.alpha_registry = decision_making.alpha_registry
        
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
        
        # Assert 3: FSM did NOT emit intent but DID emit DECISION_BLOCKED
        # (check fsm.emit calls, ensuring none are TRADE_INTENT_PROPOSED)
        emitted_events = [args[0] if args else kwargs.get("name") for args, kwargs in decision_making.fsm.emit.call_args_list]
        
        assert "EVT:TRADE_INTENT_PROPOSED" not in emitted_events, "Trade intent was incorrectly emitted for blocked config!"
        assert "EVT:DECISION_BLOCKED" in emitted_events, "DECISION_BLOCKED was not emitted!"
        
        # Verify payload details for DECISION_BLOCKED
        call_args = decision_making.fsm.emit.call_args_list[-1]
        args, _ = call_args
        assert args[0] == "EVT:DECISION_BLOCKED"
        assert args[1]["reason_code"] == "NRR-CFG-001" # CFG_MISSING mapped code

    @patch("apps.reference.domains.decision_making.strategy_gateway.inc_config_contract_violation")
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
                pld={"strategy_id": "mean_reversion", "symbol": "BTCUSDT", "side": "BUY", "ts_ms": 123456789, "readiness": {"warmup_ok": True}},
            )
            decision_making._on_strategy_signal_gateway(msg)

            mock_inc.assert_called_once()
            
            # TASK-CFG-REJECT-INTEGRATE-01: Verify TRADE_INTENT_REJECTED emission
            decision_making.fsm.emit.assert_called()
            call_args = decision_making.fsm.emit.call_args_list[0]
            args, kwargs = call_args
            event_name = args[0] if args else kwargs.get("name")
            payload = args[1]
            
            assert event_name == "EVT:TRADE_INTENT_REJECTED"
            assert payload["reason_code"] == "NRR-CFG-001" # Defaults to MISSING
            assert payload["symbol"] == "BTCUSDT"
            # assert payload["stage"] == "strategy_signal_gateway" # removed, it is in details
            assert payload["details"]["stage"] == "strategy_signal_gateway"
