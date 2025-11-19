
import pytest
from unittest.mock import MagicMock, patch
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.agg_oco_watchdog import AggOcoViolationKind


@pytest.fixture
def fsm():
    config = MagicMock()
    # Setup minimal valid config
    config.trading.execution.manage.mode = "legacy"
    config.trading.execution.manage.brackets.aggregated_oco.enabled = False
    config.trading.execution.manage.brackets.aggregated_oco.aggregated_only_mode = False
    config.trading.execution.manage.brackets.aggregated_oco.watchdog.enabled = False
    config.trading.execution.manage.guardian.unified = True
    config.trading.execution.manage.guardian.emit_tidy_event = True
    config.trading.execution.manage.guardian.poll_interval_ms = 500
    config.trading.execution.manage.guardian.cleanup_ttl_ms = 6000
    config.trading.execution.manage.guardian.symbol_cooldown_ms = 4000
    config.trading.execution.manage.watchdog.ack_ttl_ms = 1000
    config.trading.execution.manage.watchdog.fill_ttl_ms = 1000
    config.trading.execution.manage.watchdog.check_interval_ms = 1000
    config.trading.execution.manage.watchdog.source = "legacy"

    # Mock get method for dict-like access if needed
    config.get.return_value = {}

    with patch('apps.reference.domains.execution_position.fsm.OrderGuardian') as MockGuardian:
        fsm = ExecPosFSM(config=config, shadow_mode=True)
        fsm.logger = MagicMock()
        return fsm


def test_circuit_breaker_blocks_open_when_unprotected(fsm):
    # Setup unprotected position state
    symbol = "BTCUSDT"
    fsm._agg_watchdog_status = {
        ("BTCUSDT", "LONG"): {
            "status": AggOcoViolationKind.NO_SL_FOR_OPEN_POSITION.value,
            "updated_ts": 1234567890
        }
    }

    msg = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test_rid",
        pld={"symbol": symbol, "qty": "0.1",
             "side": "BUY", "price_ref": "50000"}
    )

    # Mock _check_exposure_fail_closed to return False (allowed)
    fsm._check_exposure_fail_closed = MagicMock(return_value=False)

    # Mock open_flow
    open_flow = MagicMock()
    fsm.open_flows[symbol] = open_flow

    # Call handle
    result = fsm.handle(msg)

    # Assertions
    assert result is not None
    assert result.op == "ERR"
    assert result.why == "circuit_breaker_unprotected_position"
    assert "Unprotected position detected" in result.pld["error"]

    # Verify open_flow.handle was NOT called
    open_flow.handle.assert_not_called()


def test_circuit_breaker_allows_open_when_protected(fsm):
    # Setup protected position state
    symbol = "BTCUSDT"
    fsm._agg_watchdog_status = {
        ("BTCUSDT", "LONG"): {
            "status": "OK",
            "updated_ts": 1234567890
        }
    }

    msg = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test_rid",
        pld={"symbol": symbol, "qty": "0.1",
             "side": "BUY", "price_ref": "50000"}
    )

    # Mock _check_exposure_fail_closed to return False (allowed)
    fsm._check_exposure_fail_closed = MagicMock(return_value=False)

    # Mock open_flow
    open_flow = MagicMock()
    open_flow.handle.return_value = Message(
        op="DEC",
        verb="OPEN",
        rid="test_rid",
        src="execution_position",
        dst="test"
    )
    fsm.open_flows[symbol] = open_flow
    # Also populate manage_flows to prevent _get_or_create_flows from overwriting
    fsm.manage_flows[symbol] = MagicMock()
    fsm.close_flows[symbol] = MagicMock()

    # Call handle
    result = fsm.handle(msg)

    # Assertions
    assert result is not None
    assert result.op == "DEC"

    # Verify open_flow.handle WAS called
    open_flow.handle.assert_called_once()
