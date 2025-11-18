import pytest
import time
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
from apps.reference.domains.execution_position.fsm import (
    ExecPosFSM,
    _parse_hhmm,
    _in_quiet,
    PositionSnapshot
)
from vfoundation.core.protocol import Message

# --- Helper Function Tests ---

def test_parse_hhmm():
    assert _parse_hhmm("00:00") == 0
    assert _parse_hhmm("01:30") == 90
    assert _parse_hhmm("23:59") == 1439

    # Invalid inputs
    assert _parse_hhmm("24:00") is None
    assert _parse_hhmm("00:60") is None
    assert _parse_hhmm("invalid") is None
    assert _parse_hhmm("12") is None

def test_in_quiet():
    # Mock datetime to control "now"
    base_time = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc) # 12:00 UTC

    # No windows
    assert _in_quiet(None, now=base_time) is False
    assert _in_quiet([], now=base_time) is False

    # Window covering time
    assert _in_quiet(["10:00-14:00"], now=base_time) is True

    # Window not covering time
    assert _in_quiet(["13:00-15:00"], now=base_time) is False

    # Cross-midnight window (e.g. 22:00 - 02:00)
    late_night = datetime(2023, 1, 1, 23, 0, tzinfo=timezone.utc)
    early_morning = datetime(2023, 1, 1, 1, 0, tzinfo=timezone.utc)

    assert _in_quiet(["22:00-02:00"], now=late_night) is True
    assert _in_quiet(["22:00-02:00"], now=early_morning) is True
    assert _in_quiet(["22:00-02:00"], now=base_time) is False

    # Full day
    assert _in_quiet(["00:00-00:00"], now=base_time) is True

    # Invalid windows ignored
    assert _in_quiet(["invalid"], now=base_time) is False
    assert _in_quiet(["10:00-invalid"], now=base_time) is False

# --- ExecPosFSM Core Tests ---

@pytest.fixture
def mock_config():
    return {
        "execution": {
            "manage": {
                "mode": "aggregated_only",
                "brackets": {
                    "enable": True,
                    "aggregated_oco": {
                        "enabled": True,
                        "aggregated_only_mode": True,
                        "recalc_on_partial_close": True,
                        "watchdog": {
                            "enabled": True,
                            "interval_sec": 1
                        }
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
                },
                "positions": {
                    "ws_snapshot": {
                        "enabled": True,
                        "max_age_ms": 1500
                    }
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
         patch("apps.reference.domains.execution_position.fsm.ExposureGuard") as MockExposureGuard, \
         patch("apps.reference.domains.execution_position.fsm.LocalBus"):

        # Setup ExposureGuard mock
        mock_exposure_guard = MockExposureGuard.return_value
        mock_exposure_guard.can_open.return_value = {"allowed": True, "reason": "ok"}

        fsm_instance = ExecPosFSM(config=mock_config, shadow_mode=False)
        fsm_instance.adapter = MagicMock()
        fsm_instance.adapter.get_open_positions = AsyncMock(return_value=[])
        fsm_instance.adapter.get_open_orders = AsyncMock(return_value=[])

        # Mock bus
        fsm_instance.bus = MagicMock()
        fsm_instance.bus.emit = MagicMock()

        return fsm_instance

def test_init_aggregated_oco_config(fsm):
    assert fsm._agg_oco_enabled is True
    assert fsm._agg_watchdog_enabled is True
    assert fsm._agg_watchdog_interval_sec == 1
    assert fsm._ws_snapshot_enabled is True

def test_on_order_ack(fsm):
    msg = Message(
        op="EVT", verb="ORDER_ACK",
        src="adapter", dst="execution_position",
        pld={"orderId": "123", "clientOrderId": "test_oid", "symbol": "BTCUSDT"}
    )

    # Mock logger to verify execution path
    fsm.logger = MagicMock()

    fsm._on_order_ack(msg)

    # Verify it processed the event (logged debug message)
    assert fsm.logger.debug.called

def test_on_order_fill_legacy(fsm):
    msg = Message(
        op="EVT", verb="ORDER_FILL",
        src="adapter", dst="execution_position",
        pld={
            "orderId": "123",
            "symbol": "BTCUSDT",
            "lastFilledQty": "0.1",
            "lastFilledPrice": "50000",
            "quantity": "0.1",
            "price": "50000"
        }
    )

    # Mock _ingest_ws_fill_payload
    fsm._ingest_ws_fill_payload = MagicMock()

    fsm._on_order_fill(msg)

    fsm._ingest_ws_fill_payload.assert_called_once()
    # Verify payload passed
    call_args = fsm._ingest_ws_fill_payload.call_args[0][0]
    assert call_args["orderId"] == "123"

def test_agg_oco_watchdog_task_lifecycle(fsm):
    # Mock loop
    fsm._async_loop = MagicMock()
    fsm._async_loop.is_closed.return_value = False
    fsm._async_loop.create_task = MagicMock()

    # Mock dependencies
    fsm.adapter = MagicMock()
    fsm.order_guardian = MagicMock()

    fsm._schedule_agg_oco_watchdog()

    # It might use call_soon_threadsafe or create_task directly depending on loop
    if fsm._async_loop.call_soon_threadsafe.called:
        callback = fsm._async_loop.call_soon_threadsafe.call_args[0][0]
        callback()

    fsm._async_loop.create_task.assert_called_once()

@pytest.mark.asyncio
async def test_run_agg_oco_watchdog_once(fsm):
    # Mock _call_adapter_fn
    fsm._call_adapter_fn = AsyncMock(side_effect=[
        [], # open_orders
        [{"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "50000"}] # positions
    ])

    # Mock internal methods
    fsm._list_guardian_bracket_sets = MagicMock(return_value=[])
    fsm._rehydrate_guardian_state = MagicMock()
    fsm._update_watchdog_snapshot = MagicMock()

    # Mock lock - locked() is sync, context manager is async
    fsm._agg_watchdog_lock = MagicMock()
    fsm._agg_watchdog_lock.locked.return_value = False
    fsm._agg_watchdog_lock.__aenter__ = AsyncMock(return_value=None)
    fsm._agg_watchdog_lock.__aexit__ = AsyncMock(return_value=None)

    await fsm._run_agg_oco_watchdog_once()

    assert fsm._call_adapter_fn.call_count == 2
    fsm._rehydrate_guardian_state.assert_called_once()
    fsm._update_watchdog_snapshot.assert_called_once()

def test_handle_open_command(fsm):
    msg = Message(
        op="CMD", verb="OPEN",
        src="test", dst="execution_position",
        pld={
            "symbol": "BTCUSDT",
            "qty": "1.0",
            "side": "BUY",
            "price_ref": "50000"
        }
    )

    # Mock flows
    mock_open = MagicMock()
    mock_manage = MagicMock()
    mock_close = MagicMock()
    fsm._get_or_create_flows = MagicMock(return_value=(mock_open, mock_manage, mock_close))

    # Mock _check_exposure_fail_closed
    fsm._check_exposure_fail_closed = MagicMock(return_value=False)

    fsm.handle(msg)

    mock_open.handle.assert_called_once_with(msg)

def test_handle_open_command_blocked_by_exposure(fsm):
    msg = Message(
        op="CMD", verb="OPEN",
        src="test", dst="execution_position",
        pld={"symbol": "BTCUSDT"}
    )

    fsm._check_exposure_fail_closed = MagicMock(return_value=True)

    # Mock flows
    mock_open = MagicMock()
    mock_manage = MagicMock()
    mock_close = MagicMock()
    fsm._get_or_create_flows = MagicMock(return_value=(mock_open, mock_manage, mock_close))

    fsm.handle(msg)

    mock_open.handle.assert_not_called()

def test_handle_close_command(fsm):
    msg = Message(
        op="CMD", verb="CLOSE",
        src="test", dst="execution_position",
        pld={"symbol": "BTCUSDT"}
    )

    # Mock flows
    mock_open = MagicMock()
    mock_manage = MagicMock()
    mock_close = MagicMock()
    fsm._get_or_create_flows = MagicMock(return_value=(mock_open, mock_manage, mock_close))

    fsm.handle(msg)

    mock_close.handle.assert_called_once_with(msg)

def test_handle_adjust_command(fsm):
    msg = Message(
        op="CMD", verb="ADJUST",
        src="test", dst="execution_position",
        pld={"symbol": "BTCUSDT"}
    )

    # Mock flows
    mock_open = MagicMock()
    mock_manage = MagicMock()
    mock_close = MagicMock()
    fsm._get_or_create_flows = MagicMock(return_value=(mock_open, mock_manage, mock_close))

    fsm.handle(msg)

    mock_manage.handle.assert_called_once_with(msg)

def test_handle_manage_command(fsm):
    msg = Message(
        op="CMD", verb="MANAGE",
        src="test", dst="execution_position",
        pld={"symbol": "BTCUSDT"}
    )

    # Mock flows
    mock_open = MagicMock()
    mock_manage = MagicMock()
    mock_close = MagicMock()
    fsm._get_or_create_flows = MagicMock(return_value=(mock_open, mock_manage, mock_close))

    fsm.handle(msg)

    mock_manage.handle.assert_called_once_with(msg)

def test_handle_unknown_verb(fsm):
    msg = Message(
        op="CMD", verb="UNKNOWN",
        src="test", dst="execution_position",
        pld={"symbol": "BTCUSDT"}
    )

    # Mock flows
    mock_open = MagicMock()
    mock_manage = MagicMock()
    mock_close = MagicMock()
    fsm._get_or_create_flows = MagicMock(return_value=(mock_open, mock_manage, mock_close))

    # Should route to manage flow by default
    fsm.handle(msg)

    mock_manage.handle.assert_called_once_with(msg)

def test_dispatch_decision(fsm):
    msg = Message(
        op="DEC", verb="OPEN",
        src="test", dst="execution_position",
        pld={"symbol": "BTCUSDT"}
    )

    fsm._submit_async = MagicMock()
    # Mock _execute_decision to return a dummy coroutine
    fsm._execute_decision = MagicMock(return_value="coro")
    fsm._get_async_loop = MagicMock(return_value=MagicMock())

    # Ensure conditions for execution are met
    fsm.shadow_mode = False
    fsm.adapter = MagicMock()

    with patch("apps.reference.domains.execution_position.fsm.wal") as mock_wal:
        fsm._dispatch_decision(msg, "BTCUSDT")

    fsm._submit_async.assert_called_once()
    fsm._execute_decision.assert_called_once_with(msg)
    assert fsm._submit_async.call_args[0][0] == "coro"

