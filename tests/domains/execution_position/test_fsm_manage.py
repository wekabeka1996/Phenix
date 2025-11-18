import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState

@pytest.fixture
def mock_config():
    return {
        "execution": {
            "manage": {
                "mode": "legacy",
                "auto": True,
                "brackets": {
                    "enable": True,
                    "aggregated_oco": {
                        "enabled": False,
                        "aggregated_only_mode": False
                    },
                    "working_type_default": "MARK_PRICE",
                    "price_protect": False,
                    "offset_bps": 10
                },
                "quick_profit": {
                    "enabled": False,
                    "mode": "disabled",
                    "target_usd": 0,
                    "priority": 0
                },
                "emergency": {
                    "wait_mode_bars": 1
                }
            }
        }
    }

@pytest.fixture
def fsm(mock_config):
    return ManageFlowFSM(config=mock_config, symbol="BTCUSDT")

def test_initialization(fsm):
    assert fsm.state == ManageState.FLAT
    assert fsm.symbol == "BTCUSDT"
    assert fsm._auto_manage_enabled is True

def test_handle_flat_no_position(fsm):
    msg = Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", src="test", dst="execution_position", pld={"positions": []})
    res = fsm.handle(msg)
    assert res is None
    assert fsm.state == ManageState.FLAT

def test_handle_flat_with_position_fill(fsm):
    # Setup
    msg = Message(
        op="EVT", verb="FILL",
        src="test", dst="execution_position",
        pld={
            "symbol": "BTCUSDT",
            "qty": "1.0",
            "price": "50000",
            "side": "BUY",
            "order_type": "LIMIT"
        }
    )

    # Mock _should_place_brackets to return True
    with patch.object(fsm, "_should_place_brackets", return_value=True):
        # Mock _calculate_bracket_prices to return valid prices
        with patch.object(fsm, "_calculate_bracket_prices", return_value=(Decimal("49000"), Decimal("51000"))):
            # Mock _build_sl_tp_client_ids
            with patch.object(fsm, "_build_sl_tp_client_ids", return_value=("seed", "sl_id", "tp_id")):
                res = fsm.handle(msg)

    # Verify
    assert fsm.state == ManageState.BRACKETS_PENDING
    assert res is not None
    assert res.op == "DEC"
    assert res.verb == "PLACE_ORDER"
    assert res.pld["newClientOrderId"] == "sl_id"

    # Check queued TP order
    queued = fsm.consume_pending_decisions()
    assert len(queued) == 1
    assert queued[0].op == "DEC"
    assert queued[0].verb == "PLACE_ORDER"
    assert queued[0].pld["newClientOrderId"] == "tp_id"

def test_handle_exit_fill_ignored(fsm):
    # Setup exit fill (e.g. STOP_MARKET)
    msg = Message(
        op="EVT", verb="FILL",
        src="test", dst="execution_position",
        pld={
            "symbol": "BTCUSDT",
            "qty": "1.0",
            "price": "50000",
            "side": "SELL",
            "order_type": "STOP_MARKET"
        }
    )

    res = fsm.handle(msg)

    # Verify
    assert res is None
    assert fsm.state == ManageState.FLAT
    assert fsm.position_qty is None

def test_wait_mode_skips_actions(fsm):
    fsm.state = ManageState.WAIT_MODE
    fsm._wait_mode_until_ts = 9999999999999 # Future

    msg = Message(op="EVT", verb="UPD", src="test", dst="execution_position", pld={"ts": 1000000000000})
    res = fsm.handle(msg)

    assert res is not None
    assert res.verb == "MANAGE_SKIPPED"
    assert res.pld["reason"] == "wait_mode"

def test_auto_manage_disabled(fsm):
    fsm._auto_manage_enabled = False
    msg = Message(op="EVT", verb="FILL", src="test", dst="execution_position", pld={})
    res = fsm.handle(msg)

    assert res is not None
    assert res.verb == "MANAGE_SKIPPED"
    assert res.pld["reason"] == "auto_manage_disabled"
