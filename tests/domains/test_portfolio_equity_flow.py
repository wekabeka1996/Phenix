""""""""""""

Test for portfolio equity flow between domains.

Test for portfolio equity flow between domains.

Tests that equity values (equity_free_usdt, equity_cross_usdt) are correctly

computed in PositionTracking and used in DecisionMaking without zero-overwrite.Test for portfolio equity flow between domains.Test for portfolio equity flow between domains.

"""

import sysTests that equity values (equity_free_usdt, equity_cross_usdt) are correctly

from pathlib import Path

computed in PositionTracking and used in DecisionMaking without zero-overwrite.

# Add paths for imports

apps_root = Path(__file__).parent.parent.parent / "apps""""

vfoundation_root = Path(__file__).parent.parent.parent / "vfoundation"

if str(apps_root) not in sys.path:import sysTests that equity values (equity_free_usdt, equity_cross_usdt) are correctlyTests that equity values (equity_free_usdt, equity_cross_usdt) are correctly

    sys.path.insert(0, str(apps_root))

if str(vfoundation_root) not in sys.path:from pathlib import Path

    sys.path.insert(0, str(vfoundation_root))

from unittest import mockcomputed in PositionTracking and used in DecisionMaking without zero-overwrite.computed in PositionTracking and used in DecisionMaking without zero-overwrite.

def test_position_tracking_emits_equity_fields():

    """import pytest

    Test that PositionTracking emits equity_free_usdt and equity_cross_usdt fields.

    """from vfoundation.core.protocol import Message""""""

    from apps.reference.domains.position_tracking.position_tracking import PositionTracking



    # Mock FSM

    class MockFSM:# Add paths for importsimport sysimport sys

        def __init__(self):

            self.events = []apps_root = Path(__file__).parent.parent.parent / "apps"

        def emit(self, event_name, payload, why):

            self.events.append((event_name, payload, why))vfoundation_root = Path(__file__).parent.parent.parent / "vfoundation"from pathlib import Pathfrom pathlib import Path

        def listen(self, *args): pass

if str(apps_root) not in sys.path:

    fsm = MockFSM()

    config = {'position_limits': {'max_positions': 10}, 'risk_limits': {'max_drawdown': 0.1}}    sys.path.insert(0, str(apps_root))from unittest import mockfrom unittest import mock

    position_tracker = PositionTracking(fsm=fsm, config=config)

    position_tracker.start()if str(vfoundation_root) not in sys.path:



    # Simulate balance update with USDT    sys.path.insert(0, str(vfoundation_root))import pytestimport pytest

    from vfoundation.core.protocol import Message

    balance_payload = {

        'assets': [{

            'asset': 'USDT',from vfoundation.core.protocol import Messagefrom vfoundation.core.protocol import Message

            'balance': '10000.0',

            'crossWalletBalance': '9500.0',@pytest.fixture

            'crossUnPnl': '500.0',

            'updateTime': 1693526400000def mock_config():

        }]

    }    """Mock configuration for equity flow tests."""



    event = Message(op="EVT", verb="BALANCE_UPDATE_RECEIVED", src="test", dst="position_tracking", pld=balance_payload)    return {# Add paths for imports# Add paths for imports

    position_tracker.on_balance_update(event)

        'position_limits': {'max_positions': 10},

    # Verify portfolio update was emitted

    assert len(fsm.events) == 1        'risk_limits': {'max_drawdown': 0.1}apps_root = Path(__file__).parent.parent.parent / "apps"apps_root = Path(__file__).parent.parent.parent / "apps"

    event_name, payload, why = fsm.events[0]

    assert event_name == "EVT:PORTFOLIO_STATE_UPDATED"    }

    assert 'equity_free_usdt' in payload

    assert 'equity_cross_usdt' in payloadvfoundation_root = Path(__file__).parent.parent.parent / "vfoundation"vfoundation_root = Path(__file__).parent.parent.parent / "vfoundation"

    assert 'equity_ts' in payload

    assert payload['equity_free_usdt'] == '10000.0'

    assert payload['equity_cross_usdt'] == '10000.0'  # 9500 + 500

    assert payload['equity_ts'] == 1693526400000@pytest.fixtureif str(apps_root) not in sys.path:if str(apps_root) not in sys.path:



if __name__ == "__main__":def mock_decision_config():

    test_position_tracking_emits_equity_fields()

    print("✅ Test passed!")    """Mock configuration for decision making tests."""    sys.path.insert(0, str(apps_root))    sys.path.insert(0, str(apps_root))

    return {

        "system": {if str(vfoundation_root) not in sys.path:if str(vfoundation_root) not in sys.path:

            "trade_intent_validity_ms": 30000,

            "kelly": {"fraction_cap": 0.85}    sys.path.insert(0, str(vfoundation_root))    sys.path.insert(0, str(vfoundation_root))

        },

        "trading": {

            "instruments": {

                "BTCUSDT": {

                    "lot_step": 0.001,

                    "tick_size": 0.01,@pytest.fixture@pytest.fixture

                    "min_qty": 0.001,

                    "step_size": "0.001"def mock_config():def mock_config():

                }

            },    """Mock configuration for equity flow tests."""    """Mock configuration for equity flow tests."""

            "decision": {

                "payoff_ratio_r": 2.0,    return {    return {

                "signal_weights": {"obi": 1.0},

                "probability_bounds": {"base": 0.5, "max_prob": 0.8, "min_prob": 0.1},        'position_limits': {'max_positions': 10},        'position_limits': {'max_positions': 10},

                "signal_threshold": 0.1,

                "p_calibration_version": "calibrated_v1",        'risk_limits': {'max_drawdown': 0.1}        'risk_limits': {'max_drawdown': 0.1}

                "position_sizing": {

                    "kelly_conservative_factor": 0.1,    }    }

                    "kelly_alpha": 0.5,

                    "min_position_size_usd": 10.0,

                    "max_position_size_usd": 1000.0,

                    "default_notional_cap_usd": 1000.0,

                    "liquidity_based_cap_usd": 10000.0

                },@pytest.fixture@pytest.fixture

                "calib_metrics_placeholder": "ECE=0.05, Brier=0.08"

            },def mock_decision_config():def mock_decision_config():

            "tca_prefs": {"max_slippage_bps": 50.0, "max_latency_ms": 5000, "maker_preference": "allow"},

            "risk_budgets": {"trade_cvar95_max_bps": 100.0, "session_cvar95_max_bps": 200.0},    """Mock configuration for decision making tests."""    """Mock configuration for decision making tests."""

            "risk_parameters": {"cvar_confidence": 0.95, "max_leverage": 5.0}

        }    return {    return {

    }

        "system": {        "system": {



class FSMCore:            "trade_intent_validity_ms": 30000,            "trade_intent_validity_ms": 30000,

    """Simple FSM core interface for testing (minimal implementation)."""

            "kelly": {"fraction_cap": 0.85}            "kelly": {"fraction_cap": 0.85}

    def __init__(self) -> None:

        self.listeners: dict[str, list] = {}        },        },



    def listen(self, event_name: str, callback) -> None:        "trading": {        "trading": {

        """Register event listener."""

        if event_name not in self.listeners:            "instruments": {            "instruments": {

            self.listeners[event_name] = []

        self.listeners[event_name].append(callback)                "BTCUSDT": {                "BTCUSDT": {



    def emit(self, event_name: str, payload: dict, why: str) -> None:                    "lot_step": 0.001,                    "lot_step": 0.001,

        """Emit event to listeners."""

        if event_name in self.listeners:                    "tick_size": 0.01,                    "tick_size": 0.01,

            for callback in self.listeners[event_name]:

                try:                    "min_qty": 0.001,                    "min_qty": 0.001,

                    callback(Message(

                        op="EVT",                    "step_size": "0.001"                    "step_size": "0.001"

                        verb=event_name.split(":")[1],  # Extract verb from EVT:VERB

                        src="test",                }                }

                        dst="any",

                        pld=payload,            },            },

                        why=why

                    ))            "decision": {            "decision": {

                except Exception as e:

                    print(f"Error in event listener: {e}")                "payoff_ratio_r": 2.0,                "payoff_ratio_r": 2.0,



                "signal_weights": {"obi": 1.0},                "signal_weights": {"obi": 1.0},

def test_position_tracking_emits_equity_fields(mock_config):

    """                "probability_bounds": {"base": 0.5, "max_prob": 0.8, "min_prob": 0.1},                "probability_bounds": {"base": 0.5, "max_prob": 0.8, "min_prob": 0.1},

    Test that PositionTracking emits equity_free_usdt and equity_cross_usdt fields.

    """                "signal_threshold": 0.1,                "signal_threshold": 0.1,

    # Initialize FSM core

    fsm = FSMCore()                "p_calibration_version": "calibrated_v1",                "p_calibration_version": "calibrated_v1",



    # Set up mock listeners                "position_sizing": {                "position_sizing": {

    portfolio_listener = mock.Mock()

    fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", portfolio_listener)                    "kelly_conservative_factor": 0.1,                    "kelly_conservative_factor": 0.1,



    # Initialize PositionTracking                    "kelly_alpha": 0.5,                    "kelly_alpha": 0.5,

    from apps.reference.domains.position_tracking.position_tracking import PositionTracking

    position_tracker = PositionTracking(fsm=fsm, config=mock_config)                    "min_position_size_usd": 10.0,                    "min_position_size_usd": 10.0,

    position_tracker.start()

                    "max_position_size_usd": 1000.0,                    "max_position_size_usd": 1000.0,

    # Simulate balance update with USDT

    balance_payload = {                    "default_notional_cap_usd": 1000.0,                    "default_notional_cap_usd": 1000.0,

        'assets': [{

            'asset': 'USDT',                    "liquidity_based_cap_usd": 10000.0                    "liquidity_based_cap_usd": 10000.0

            'balance': '10000.0',

            'crossWalletBalance': '9500.0',                },                },

            'crossUnPnl': '500.0',

            'updateTime': 1693526400000                "calib_metrics_placeholder": "ECE=0.05, Brier=0.08"                "calib_metrics_placeholder": "ECE=0.05, Brier=0.08"

        }]

    }            },            },



    fsm.emit("EVT:BALANCE_UPDATE_RECEIVED", payload=balance_payload, why="Test balance update.")            "tca_prefs": {"max_slippage_bps": 50.0, "max_latency_ms": 5000, "maker_preference": "allow"},            "tca_prefs": {"max_slippage_bps": 50.0, "max_latency_ms": 5000, "maker_preference": "allow"},



    # Verify portfolio update was emitted            "risk_budgets": {"trade_cvar95_max_bps": 100.0, "session_cvar95_max_bps": 200.0},            "risk_budgets": {"trade_cvar95_max_bps": 100.0, "session_cvar95_max_bps": 200.0},

    portfolio_listener.assert_called_once()

    call_args = portfolio_listener.call_args            "risk_parameters": {"cvar_confidence": 0.95, "max_leverage": 5.0}            "risk_parameters": {"cvar_confidence": 0.95, "max_leverage": 5.0}

    event = call_args[0][0]

        }        }

    payload = event.pld

    assert 'equity_free_usdt' in payload    }    }

    assert 'equity_cross_usdt' in payload

    assert 'equity_ts' in payload

    assert payload['equity_free_usdt'] == '10000.0'

    assert payload['equity_cross_usdt'] == '10000.0'  # 9500 + 500

    assert payload['equity_ts'] == 1693526400000

class FSMCore:class FSMCore:



def test_decision_making_uses_cached_equity(mock_decision_config):    """Simple FSM core interface for testing (minimal implementation)."""    """Simple FSM core interface for testing (minimal implementation)."""

    """

    Test that DecisionMaking caches equity_free_usdt and doesn't overwrite with zero.

    """

    # Initialize FSM core    def __init__(self) -> None:    def __init__(self) -> None:

    fsm = FSMCore()

        self.listeners: dict[str, list] = {}        self.listeners: dict[str, list] = {}

    # Initialize DecisionMaking

    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    decision_component = DecisionMaking(fsm=fsm, config=mock_decision_config)

    def listen(self, event_name: str, callback) -> None:    def listen(self, event_name: str, callback) -> None:

    # First portfolio update with equity_free_usdt

    portfolio_payload_1 = {        """Register event listener."""        """Register event listener."""

        "ts": 1693526400000,

        "equity": "10000.0",        if event_name not in self.listeners:        if event_name not in self.listeners:

        "equity_free_usdt": "10000.0",

        "equity_cross_usdt": "10500.0",            self.listeners[event_name] = []            self.listeners[event_name] = []

        "equity_ts": 1693526400000,

        "realized_pnl": "0.0",        self.listeners[event_name].append(callback)        self.listeners[event_name].append(callback)

        "unrealized_pnl": "0.0",

        "positions": []

    }

    def emit(self, event_name: str, payload: dict, why: str) -> None:    def emit(self, event_name: str, payload: dict, why: str) -> None:

    portfolio_msg_1 = Message(

        op="EVT",        """Emit event to listeners."""        """Emit event to listeners."""

        verb="PORTFOLIO_STATE_UPDATED",

        src="position_tracking",        if event_name in self.listeners:        if event_name in self.listeners:

        dst="decision_making",

        pld=portfolio_payload_1            for callback in self.listeners[event_name]:            for callback in self.listeners[event_name]:

    )

                try:                try:

    decision_component.on_portfolio(portfolio_msg_1)

                    callback(Message(                    callback(Message(

    # Verify cached equity

    assert decision_component._cached_equity_free_usdt == "10000.0"                        op="EVT",                        op="EVT",

    assert decision_component._cached_equity_cross_usdt == "10500.0"

                        verb=event_name.split(":")[1],  # Extract verb from EVT:VERB                        verb=event_name.split(":")[1],  # Extract verb from EVT:VERB

    # Second portfolio update with zero equity (should not overwrite cache)

    portfolio_payload_2 = {                        src="test",                        src="test",

        "ts": 1693526460000,

        "equity": "0.0",                        dst="any",                        dst="any",

        "equity_free_usdt": "0.0",  # This should not overwrite cache

        "equity_cross_usdt": "0.0",                        pld=payload,                        pld=payload,

        "equity_ts": 1693526460000,

        "realized_pnl": "0.0",                        why=why                        why=why

        "unrealized_pnl": "0.0",

        "positions": []                    ))                    ))

    }

                except Exception as e:                except Exception as e:

    portfolio_msg_2 = Message(

        op="EVT",                    print(f"Error in event listener: {e}")                    print(f"Error in event listener: {e}")

        verb="PORTFOLIO_STATE_UPDATED",

        src="position_tracking",

        dst="decision_making",

        pld=portfolio_payload_2

    )

def test_position_tracking_emits_equity_fields(mock_config):def test_position_tracking_emits_equity_fields(mock_config):

    decision_component.on_portfolio(portfolio_msg_2)

    """    """

    # Verify cache was not overwritten

    assert decision_component._cached_equity_free_usdt == "10000.0"    Test that PositionTracking emits equity_free_usdt and equity_cross_usdt fields.    Test that PositionTracking emits equity_free_usdt and equity_cross_usdt fields.

    assert decision_component._cached_equity_cross_usdt == "10500.0"
    """    """

    # Initialize FSM core    # Initialize FSM core

    fsm = FSMCore()    fsm = FSMCore()



    # Set up mock listeners    # Set up mock listeners

    portfolio_listener = mock.Mock()    portfolio_listener = mock.Mock()

    fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", portfolio_listener)    fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", portfolio_listener)



    # Initialize PositionTracking    # Initialize PositionTracking

    from apps.reference.domains.position_tracking.position_tracking import PositionTracking    from apps.reference.domains.position_tracking.position_tracking import PositionTracking

    position_tracker = PositionTracking(fsm=fsm, config=mock_config)    position_tracker = PositionTracking(fsm=fsm, config=mock_config)

    position_tracker.start()    position_tracker.start()



    # Simulate balance update with USDT    # Simulate balance update with USDT

    balance_payload = {    balance_payload = {

        'assets': [{        'assets': [{

            'asset': 'USDT',            'asset': 'USDT',

            'balance': '10000.0',            'balance': '10000.0',

            'crossWalletBalance': '9500.0',            'crossWalletBalance': '9500.0',

            'crossUnPnl': '500.0',            'crossUnPnl': '500.0',

            'updateTime': 1693526400000            'updateTime': 1693526400000

        }]        }]

    }    }



    fsm.emit("EVT:BALANCE_UPDATE_RECEIVED", payload=balance_payload, why="Test balance update.")    fsm.emit("EVT:BALANCE_UPDATE_RECEIVED", payload=balance_payload, why="Test balance update.")



    # Verify portfolio update was emitted    # Verify portfolio update was emitted

    portfolio_listener.assert_called_once()    portfolio_listener.assert_called_once()

    call_args = portfolio_listener.call_args    call_args = portfolio_listener.call_args

    event = call_args[0][0]    event = call_args[0][0]



    payload = event.pld    payload = event.pld

    assert 'equity_free_usdt' in payload    assert 'equity_free_usdt' in payload

    assert 'equity_cross_usdt' in payload    assert 'equity_cross_usdt' in payload

    assert 'equity_ts' in payload    assert 'equity_ts' in payload

    assert payload['equity_free_usdt'] == '10000.0'    assert payload['equity_free_usdt'] == '10000.0'

    assert payload['equity_cross_usdt'] == '10000.0'  # 9500 + 500    assert payload['equity_cross_usdt'] == '10000.0'  # 9500 + 500

    assert payload['equity_ts'] == 1693526400000    assert payload['equity_ts'] == 1693526400000





def test_position_tracking_skips_non_usdt_balance(mock_config):def test_position_tracking_skips_non_usdt_balance(mock_config):

    """    """

    Test that PositionTracking skips emitting portfolio update when no USDT in balance.    Test that PositionTracking skips emitting portfolio update when no USDT in balance.

    """    """

    # Initialize FSM core    # Initialize FSM core

    fsm = FSMCore()    fsm = FSMCore()



    # Set up mock listeners    # Set up mock listeners

    portfolio_listener = mock.Mock()    portfolio_listener = mock.Mock()

    fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", portfolio_listener)    fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", portfolio_listener)



    # Initialize PositionTracking    # Initialize PositionTracking

    from apps.reference.domains.position_tracking.position_tracking import PositionTracking    from apps.reference.domains.position_tracking.position_tracking import PositionTracking

    position_tracker = PositionTracking(fsm=fsm, config=mock_config)    position_tracker = PositionTracking(fsm=fsm, config=mock_config)

    position_tracker.start()    position_tracker.start()



    # Simulate balance update without USDT    # Simulate balance update without USDT

    balance_payload = {    balance_payload = {

        'assets': [{        'assets': [{

            'asset': 'BTC',            'asset': 'BTC',

            'balance': '1.0',            'balance': '1.0',

            'crossWalletBalance': '1.0',            'crossWalletBalance': '1.0',

            'crossUnPnl': '0.0',            'crossUnPnl': '0.0',

            'updateTime': 1693526400000            'updateTime': 1693526400000

        }]        }]

    }    }



    fsm.emit("EVT:BALANCE_UPDATE_RECEIVED", payload=balance_payload, why="Test balance update without USDT.")    fsm.emit("EVT:BALANCE_UPDATE_RECEIVED", payload=balance_payload, why="Test balance update without USDT.")



    # Verify no portfolio update was emitted    # Verify no portfolio update was emitted

    portfolio_listener.assert_not_called()    portfolio_listener.assert_not_called()





def test_decision_making_uses_cached_equity(mock_decision_config):def test_decision_making_uses_cached_equity(mock_decision_config):

    """    """

    Test that DecisionMaking caches equity_free_usdt and doesn't overwrite with zero.    Test that DecisionMaking caches equity_free_usdt and doesn't overwrite with zero.

    """    """

    # Initialize FSM core    # Initialize FSM core

    fsm = FSMCore()    fsm = FSMCore()



    # Initialize DecisionMaking    # Initialize DecisionMaking

    from apps.reference.domains.decision_making.decision_making import DecisionMaking    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    decision_component = DecisionMaking(fsm=fsm, config=mock_decision_config)    decision_component = DecisionMaking(fsm=fsm, config=mock_decision_config)



    # First portfolio update with equity_free_usdt    # First portfolio update with equity_free_usdt

    portfolio_payload_1 = {    portfolio_payload_1 = {

        "ts": 1693526400000,        "ts": 1693526400000,

        "equity": "10000.0",        "equity": "10000.0",

        "equity_free_usdt": "10000.0",        "equity_free_usdt": "10000.0",

        "equity_cross_usdt": "10500.0",        "equity_cross_usdt": "10500.0",

        "equity_ts": 1693526400000,        "equity_ts": 1693526400000,

        "realized_pnl": "0.0",        "realized_pnl": "0.0",

        "unrealized_pnl": "0.0",        "unrealized_pnl": "0.0",

        "positions": []        "positions": []

    }    }



    portfolio_msg_1 = Message(    portfolio_msg_1 = Message(

        op="EVT",        op="EVT",

        verb="PORTFOLIO_STATE_UPDATED",        verb="PORTFOLIO_STATE_UPDATED",

        src="position_tracking",        src="position_tracking",

        dst="decision_making",        dst="decision_making",

        pld=portfolio_payload_1        pld=portfolio_payload_1

    )    )



    decision_component.on_portfolio(portfolio_msg_1)    decision_component.on_portfolio(portfolio_msg_1)



    # Verify cached equity    # Verify cached equity

    assert decision_component._cached_equity_free_usdt == "10000.0"    assert decision_component._cached_equity_free_usdt == "10000.0"

    assert decision_component._cached_equity_cross_usdt == "10500.0"    assert decision_component._cached_equity_cross_usdt == "10500.0"



    # Second portfolio update with zero equity (should not overwrite cache)    # Second portfolio update with zero equity (should not overwrite cache)

    portfolio_payload_2 = {    portfolio_payload_2 = {

        "ts": 1693526460000,        "ts": 1693526460000,

        "equity": "0.0",        "equity": "0.0",

        "equity_free_usdt": "0.0",  # This should not overwrite cache        "equity_free_usdt": "0.0",  # This should not overwrite cache

        "equity_cross_usdt": "0.0",        "equity_cross_usdt": "0.0",

        "equity_ts": 1693526460000,        "equity_ts": 1693526460000,

        "realized_pnl": "0.0",        "realized_pnl": "0.0",

        "unrealized_pnl": "0.0",        "unrealized_pnl": "0.0",

        "positions": []        "positions": []

    }    }



    portfolio_msg_2 = Message(    portfolio_msg_2 = Message(

        op="EVT",        op="EVT",

        verb="PORTFOLIO_STATE_UPDATED",        verb="PORTFOLIO_STATE_UPDATED",

        src="position_tracking",        src="position_tracking",

        dst="decision_making",        dst="decision_making",

        pld=portfolio_payload_2        pld=portfolio_payload_2

    )    )



    decision_component.on_portfolio(portfolio_msg_2)    decision_component.on_portfolio(portfolio_msg_2)



    # Verify cache was not overwritten    # Verify cache was not overwritten

    assert decision_component._cached_equity_free_usdt == "10000.0"    assert decision_component._cached_equity_free_usdt == "10000.0"

    assert decision_component._cached_equity_cross_usdt == "10500.0"    assert decision_component._cached_equity_cross_usdt == "10500.0"





def test_decision_making_uses_cached_equity_in_decision(mock_decision_config):def test_decision_making_uses_cached_equity_in_decision(mock_decision_config):

    """    """

    Test that DecisionMaking uses cached equity_free_usdt in trade decisions.    Test that DecisionMaking uses cached equity_free_usdt in trade decisions.

    """    """

    # Initialize FSM core    # Initialize FSM core

    fsm = FSMCore()    fsm = FSMCore()



    # Set up mock listener for trade intents    # Set up mock listener for trade intents

    trade_listener = mock.Mock()    trade_listener = mock.Mock()

    fsm.listen("EVT:TRADE_INTENT_PROPOSED", trade_listener)    fsm.listen("EVT:TRADE_INTENT_PROPOSED", trade_listener)



    # Initialize DecisionMaking    # Initialize DecisionMaking

    from apps.reference.domains.decision_making.decision_making import DecisionMaking    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    decision_component = DecisionMaking(fsm=fsm, config=mock_decision_config)    decision_component = DecisionMaking(fsm=fsm, config=mock_decision_config)



    # Portfolio update with equity_free_usdt    # Portfolio update with equity_free_usdt

    portfolio_payload = {    portfolio_payload = {

        "ts": 1693526400000,        "ts": 1693526400000,

        "equity": "10000.0",        "equity": "10000.0",

        "equity_free_usdt": "10000.0",        "equity_free_usdt": "10000.0",

        "equity_cross_usdt": "10500.0",        "equity_cross_usdt": "10500.0",

        "equity_ts": 1693526400000,        "equity_ts": 1693526400000,

        "realized_pnl": "0.0",        "realized_pnl": "0.0",

        "unrealized_pnl": "0.0",        "unrealized_pnl": "0.0",

        "positions": []        "positions": []

    }    }



    portfolio_msg = Message(    portfolio_msg = Message(

        op="EVT",        op="EVT",

        verb="PORTFOLIO_STATE_UPDATED",        verb="PORTFOLIO_STATE_UPDATED",

        src="position_tracking",        src="position_tracking",

        dst="decision_making",        dst="decision_making",

        pld=portfolio_payload        pld=portfolio_payload

    )    )



    decision_component.on_portfolio(portfolio_msg)    decision_component.on_portfolio(portfolio_msg)



    # Risk assessment    # Risk assessment

    risk_payload = {    risk_payload = {

        "ts": 1693526400000,        "ts": 1693526400000,

        "symbol": "BTCUSDT",        "symbol": "BTCUSDT",

        "risk_parameters": {"is_trading_allowed": True}        "risk_parameters": {"is_trading_allowed": True}

    }    }



    risk_msg = Message(    risk_msg = Message(

        op="EVT",        op="EVT",

        verb="RISK_ASSESSMENT_COMPLETED",        verb="RISK_ASSESSMENT_COMPLETED",

        src="risk_strategy",        src="risk_strategy",

        dst="decision_making",        dst="decision_making",

        pld=risk_payload        pld=risk_payload

    )    )



    decision_component.on_risk(risk_msg)    decision_component.on_risk(risk_msg)



    # Features calculated (should trigger decision)    # Features calculated (should trigger decision)

    features_payload = {    features_payload = {

        "ts": 1693526400000,        "ts": 1693526400000,

        "symbol": "BTCUSDT",        "symbol": "BTCUSDT",

        "features": {        "features": {

            "obi": 0.5,  # Strong signal            "obi": 0.5,  # Strong signal

            "price": 50000.0            "price": 50000.0

        }        }

    }    }



    features_msg = Message(    features_msg = Message(

        op="EVT",        op="EVT",

        verb="FEATURES_CALCULATED",        verb="FEATURES_CALCULATED",

        src="analyzer",        src="analyzer",

        dst="decision_making",        dst="decision_making",

        pld=features_payload        pld=features_payload

    )    )



    decision_component.on_features(features_msg)    decision_component.on_features(features_msg)



    # Verify trade intent was proposed (using cached equity)    # Verify trade intent was proposed (using cached equity)

    trade_listener.assert_called_once()    trade_listener.assert_called_once()

    call_args = trade_listener.call_args    call_args = trade_listener.call_args

    event = call_args[0][0]    event = call_args[0][0]



    assert event.pld["instrument"] == "BTCUSDT"    assert event.pld["instrument"] == "BTCUSDT"

    assert event.pld["side"] == "buy"    assert event.pld["side"] == "buy"





def test_decision_making_rejects_zero_equity(mock_decision_config):def test_decision_making_rejects_zero_equity(mock_decision_config):

    """    """

    Test that DecisionMaking rejects trades when equity is zero and no cache exists.    Test that DecisionMaking rejects trades when equity is zero and no cache exists.

    """    """

    # Initialize FSM core    # Initialize FSM core

    fsm = FSMCore()    fsm = FSMCore()



    # Set up mock listener for trade intents    # Set up mock listener for trade intents

    trade_listener = mock.Mock()    trade_listener = mock.Mock()

    fsm.listen("EVT:TRADE_INTENT_PROPOSED", trade_listener)    fsm.listen("EVT:TRADE_INTENT_PROPOSED", trade_listener)



    # Initialize DecisionMaking    # Initialize DecisionMaking

    from apps.reference.domains.decision_making.decision_making import DecisionMaking    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    decision_component = DecisionMaking(fsm=fsm, config=mock_decision_config)    decision_component = DecisionMaking(fsm=fsm, config=mock_decision_config)



    # Portfolio update with zero equity and no equity_free_usdt    # Portfolio update with zero equity and no equity_free_usdt

    portfolio_payload = {    portfolio_payload = {

        "ts": 1693526400000,        "ts": 1693526400000,

        "equity": "0.0",        "equity": "0.0",

        "realized_pnl": "0.0",        "realized_pnl": "0.0",

        "unrealized_pnl": "0.0",        "unrealized_pnl": "0.0",

        "positions": []        "positions": []

    }    }



    portfolio_msg = Message(    portfolio_msg = Message(

        op="EVT",        op="EVT",

        verb="PORTFOLIO_STATE_UPDATED",        verb="PORTFOLIO_STATE_UPDATED",

        src="position_tracking",        src="position_tracking",

        dst="decision_making",        dst="decision_making",

        pld=portfolio_payload        pld=portfolio_payload

    )    )



    decision_component.on_portfolio(portfolio_msg)    decision_component.on_portfolio(portfolio_msg)



    # Risk assessment    # Risk assessment

    risk_payload = {    risk_payload = {

        "ts": 1693526400000,        "ts": 1693526400000,

        "symbol": "BTCUSDT",        "symbol": "BTCUSDT",

        "risk_parameters": {"is_trading_allowed": True}        "risk_parameters": {"is_trading_allowed": True}

    }    }



    risk_msg = Message(    risk_msg = Message(

        op="EVT",        op="EVT",

        verb="RISK_ASSESSMENT_COMPLETED",        verb="RISK_ASSESSMENT_COMPLETED",

        src="risk_strategy",        src="risk_strategy",

        dst="decision_making",        dst="decision_making",

        pld=risk_payload        pld=risk_payload

    )    )



    decision_component.on_risk(risk_msg)    decision_component.on_risk(risk_msg)



    # Features calculated (should NOT trigger decision due to zero equity)    # Features calculated (should NOT trigger decision due to zero equity)

    features_payload = {    features_payload = {

        "ts": 1693526400000,        "ts": 1693526400000,

        "symbol": "BTCUSDT",        "symbol": "BTCUSDT",

        "features": {        "features": {

            "obi": 0.5,  # Strong signal            "obi": 0.5,  # Strong signal

            "price": 50000.0            "price": 50000.0

        }        }

    }    }



    features_msg = Message(    features_msg = Message(

        op="EVT",        op="EVT",

        verb="FEATURES_CALCULATED",        verb="FEATURES_CALCULATED",

        src="analyzer",        src="analyzer",

        dst="decision_making",        dst="decision_making",

        pld=features_payload        pld=features_payload

    )    )



    decision_component.on_features(features_msg)    decision_component.on_features(features_msg)



    # Verify no trade intent was proposed    # Verify no trade intent was proposed

    trade_listener.assert_not_called()    trade_listener.assert_not_called()
