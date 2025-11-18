import pytest
import asyncio
import time
from unittest.mock import MagicMock, patch, AsyncMock
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
from apps.reference.domains.execution_position.fsm_close import CloseFlowFSM

@pytest.fixture
def mock_config():
    return {
        "execution": {
            "manage": {
                "mode": "legacy",
                "brackets": {
                    "enable": True,
                    "aggregated_oco": {
                        "enabled": False
                    }
                },
                "guardian": {
                    "unified": True,
                    "poll_interval_ms": 500,
                    "cleanup_ttl_ms": 6000,
                    "symbol_cooldown_ms": 4000,
                    "emit_tidy_event": True
                },
                "watchdog": {
                    "ack_ttl_ms": 1000,
                    "fill_ttl_ms": 5000,
                    "check_interval_ms": 1000
                }
            }
        },
        "trading": {
            "instruments": {
                "BTCUSDT": {
                    "min_qty": "0.001"
                }
            }
        }
    }

@pytest.fixture
def fsm(mock_config):
    with patch("apps.reference.domains.execution_position.fsm.BinanceAdapter"), \
         patch("apps.reference.domains.execution_position.fsm.OrderGuardian"), \
         patch("apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog"), \
         patch("apps.reference.domains.execution_position.fsm.ExposureGuard") as MockExposureGuard:

        # Setup ExposureGuard mock
        mock_exposure_guard = MockExposureGuard.return_value
        mock_exposure_guard.can_open.return_value = {"allowed": True, "reason": "ok"}
        mock_exposure_guard.state.postfill_reservations = {}

        fsm_instance = ExecPosFSM(config=mock_config, shadow_mode=True)
        fsm_instance.adapter = MagicMock()
        fsm_instance.adapter.get_open_positions = AsyncMock(return_value=[])
        fsm_instance.adapter.get_open_orders = AsyncMock(return_value=[])

        # Mock bus
        fsm_instance.bus = MagicMock()
        fsm_instance.bus.emit = MagicMock()

        return fsm_instance

def test_initialization(fsm):
    assert fsm.shadow_mode is True
    assert isinstance(fsm.open_flows, dict)
    assert isinstance(fsm.manage_flows, dict)
    assert isinstance(fsm.close_flows, dict)
    assert fsm.watchdog is not None
    assert fsm.exposure_guard is not None

def test_flow_accessors(fsm):
    # Test open_flow
    open_flow = fsm.open_flow("BTCUSDT")
    assert isinstance(open_flow, OpenFlowFSM)
    assert fsm.open_flows["BTCUSDT"] == open_flow

    # Test manage_flow
    manage_flow = fsm.manage_flow("BTCUSDT")
    assert isinstance(manage_flow, ManageFlowFSM)
    assert fsm.manage_flows["BTCUSDT"] == manage_flow

    # Test close_flow
    close_flow = fsm.close_flow("BTCUSDT")
    assert isinstance(close_flow, CloseFlowFSM)
    assert fsm.close_flows["BTCUSDT"] == close_flow

def test_on_portfolio_state_updated(fsm):
    # Setup
    msg = Message(
        op="EVT", verb="PORTFOLIO_STATE_UPDATED",
        src="test_src", dst="execution_position",
        pld={
            "positions": [
                {"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "50000"}
            ],
            "ts": 1234567890000
        }
    )

    # Execute
    fsm._on_portfolio_state_updated(msg)

    # Verify
    fsm.exposure_guard.on_portfolio.assert_called_once_with(msg.pld)

def test_on_trade_executed(fsm):
    # Setup
    msg = Message(
        op="EVT", verb="TRADE_EXECUTED",
        src="test_src", dst="execution_position",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.5",
            "price": "50000",
            "client_order_id": "test_oid",
            "order_id": "12345"
        }
    )

    # Mock _submit_async to avoid RuntimeWarning about unawaited coroutine
    fsm._submit_async = MagicMock()

    # Execute
    fsm._on_trade_executed(msg)

    # Verify
    fsm.exposure_guard.on_fill.assert_called()
    # It calls order_guardian.on_fill, not watchdog.on_order_fill
    fsm.order_guardian.on_fill.assert_called()
    # Verify delayed cleanup was scheduled
    fsm._submit_async.assert_called()

def test_check_exposure_fail_closed_allowed(fsm):
    msg = Message(
        op="CMD", verb="OPEN",
        src="test_src", dst="execution_position",
        pld={"symbol": "BTCUSDT", "qty": "1.0", "price_ref": "50000"}
    )

    # Allowed case
    fsm.exposure_guard.can_open.return_value = {"allowed": True, "reason": "ok"}
    blocked = fsm._check_exposure_fail_closed(msg)
    assert blocked is False
    fsm.exposure_guard.reserve.assert_called()

def test_check_exposure_fail_closed_blocked(fsm):
    msg = Message(
        op="CMD", verb="OPEN",
        src="test_src", dst="execution_position",
        pld={"symbol": "BTCUSDT", "qty": "1.0", "price_ref": "50000"}
    )

    # Blocked case
    fsm.exposure_guard.can_open.return_value = {"allowed": False, "reason": "limit_exceeded"}

    # Mock _emit_error_async to avoid async issues
    fsm._emit_error_async = AsyncMock()
    fsm._get_async_loop = MagicMock(return_value=MagicMock())

    blocked = fsm._check_exposure_fail_closed(msg)
    assert blocked is True
    # Should still reserve in fail-closed mode
    fsm.exposure_guard.reserve.assert_called()

def test_ws_snapshot_logic(fsm):
    # Enable WS snapshot
    fsm._ws_snapshot_enabled = True

    # Test storing snapshot
    snapshot = MagicMock()
    snapshot.symbol = "BTCUSDT"
    snapshot.side = "LONG"
    snapshot.position_amt = 1.0
    snapshot.updated_ts = time.time()

    fsm._store_ws_snapshot(snapshot, remove_opposite=True, source="test")

    # Verify retrieval
    retrieved = fsm._get_ws_snapshot("BTCUSDT", "LONG")
    assert retrieved == snapshot

    # Verify opposite side removal
    assert fsm._get_ws_snapshot("BTCUSDT", "SHORT") is None
