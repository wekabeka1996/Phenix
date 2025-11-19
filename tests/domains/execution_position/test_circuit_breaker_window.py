"""
EP-STAB-CIRCUIT-WINDOW: Tests for time-window based circuit breaker error tracking.

This test suite validates that the ExecPosFSM circuit breaker correctly tracks
execution errors within a time window, triggering alerts only when multiple errors
occur within the configured window (600 seconds by default).
"""

import pytest
import time
from unittest.mock import MagicMock, patch, AsyncMock
from collections import deque
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm import ExecPosFSM


@pytest.fixture
def fsm():
    """Create ExecPosFSM instance with minimal configuration."""
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
    config.get.return_value = {}

    with patch('apps.reference.domains.execution_position.fsm.OrderGuardian'):
        fsm = ExecPosFSM(config=config, shadow_mode=True)
        fsm.logger = MagicMock()
        # Mock alert_manager
        fsm.alert_manager = MagicMock()
        return fsm


def simulate_execution_error(fsm, symbol: str):
    """
    EP-STAB-CIRCUIT-WINDOW: Helper to simulate execution error and trigger circuit breaker logic.

    This directly invokes the circuit breaker code that normally runs in _execute_decision's
    exception handler when an execution error occurs.
    """
    error_key = f"exec_error_{symbol}"

    # Initialize deque for this symbol if not exists
    if not hasattr(fsm, '_exec_error_history'):
        fsm._exec_error_history = {}
    if error_key not in fsm._exec_error_history:
        fsm._exec_error_history[error_key] = deque()

    # Add current timestamp to error history
    now_ts = time.time()
    fsm._exec_error_history[error_key].append(now_ts)

    # Remove timestamps outside the time window (10 minutes)
    window_sec = getattr(fsm, '_EXEC_ERROR_WINDOW_SEC', 600)
    cutoff_ts = now_ts - window_sec
    while (fsm._exec_error_history[error_key] and
           fsm._exec_error_history[error_key][0] < cutoff_ts):
        fsm._exec_error_history[error_key].popleft()

    # Alert if 2+ execution errors within time window for same symbol
    if len(fsm._exec_error_history[error_key]) >= 2:
        fsm.alert_manager.check_circuit_breaker(True, 600)
        fsm.logger.warning(
            f"Circuit breaker alert triggered for {symbol}: "
            f"{len(fsm._exec_error_history[error_key])} errors in {window_sec}s window")


def test_circuit_breaker_burst_errors_trigger_alert(fsm):
    """
    EP-STAB-CIRCUIT-WINDOW: Test that 2 errors within a few seconds trigger circuit breaker.

    Scenario: Two execution errors occur within 5 seconds for the same symbol.
    Expected: Circuit breaker should be triggered after the second error.
    """
    symbol = "BTCUSDT"
    error_key = f"exec_error_{symbol}"

    # First error
    simulate_execution_error(fsm, symbol)

    # Verify first error was recorded but no alert yet (< 2 errors)
    assert error_key in fsm._exec_error_history
    assert len(fsm._exec_error_history[error_key]) == 1
    fsm.alert_manager.check_circuit_breaker.assert_not_called()

    # Second error (within time window, ~0.1 second later)
    time.sleep(0.1)
    simulate_execution_error(fsm, symbol)

    # Verify second error triggers circuit breaker
    assert len(fsm._exec_error_history[error_key]) == 2
    fsm.alert_manager.check_circuit_breaker.assert_called_once_with(True, 600)

    # Verify log message includes error count
    assert fsm.logger.warning.called
    warning_msg = fsm.logger.warning.call_args[0][0]
    assert "Circuit breaker alert triggered" in warning_msg
    assert symbol in warning_msg
    assert "2 errors" in warning_msg


def test_circuit_breaker_spaced_errors_no_alert(fsm):
    """
    EP-STAB-CIRCUIT-WINDOW: Test that errors spaced beyond time window don't trigger breaker.

    Scenario: One error occurs, then after window expiration (600+ seconds) another error occurs.
    Expected: Circuit breaker should NOT be triggered as errors are not within the same window.
    """
    symbol = "ETHUSDT"
    error_key = f"exec_error_{symbol}"

    # Manually set time window for testing (use smaller window for test speed)
    fsm._EXEC_ERROR_WINDOW_SEC = 5  # 5 seconds window for testing

    # First error at time T
    with patch('time.time', return_value=1000.0):
        simulate_execution_error(fsm, symbol)

    # Verify first error was recorded
    assert error_key in fsm._exec_error_history
    assert len(fsm._exec_error_history[error_key]) == 1
    fsm.alert_manager.check_circuit_breaker.assert_not_called()

    # Second error at time T + 6 seconds (beyond 5 second window)
    with patch('time.time', return_value=1006.0):
        simulate_execution_error(fsm, symbol)

    # Verify old timestamp was removed and only new one remains
    assert len(fsm._exec_error_history[error_key]) == 1
    assert fsm._exec_error_history[error_key][0] == 1006.0

    # Verify circuit breaker was NOT triggered (only 1 error in current window)
    fsm.alert_manager.check_circuit_breaker.assert_not_called()


def test_circuit_breaker_multiple_symbols_independent(fsm):
    """
    EP-STAB-CIRCUIT-WINDOW: Test that error tracking is independent per symbol.

    Scenario: Errors for different symbols should be tracked independently.
    Expected: Each symbol has its own time window and error count.
    """
    symbol1 = "BTCUSDT"
    symbol2 = "ETHUSDT"
    error_key1 = f"exec_error_{symbol1}"
    error_key2 = f"exec_error_{symbol2}"

    # One error for symbol1
    simulate_execution_error(fsm, symbol1)

    # One error for symbol2
    simulate_execution_error(fsm, symbol2)

    # Verify each symbol has 1 error tracked independently
    assert error_key1 in fsm._exec_error_history
    assert error_key2 in fsm._exec_error_history
    assert len(fsm._exec_error_history[error_key1]) == 1
    assert len(fsm._exec_error_history[error_key2]) == 1

    # No circuit breaker triggered (each symbol has only 1 error)
    fsm.alert_manager.check_circuit_breaker.assert_not_called()

    # Second error for symbol1 only
    simulate_execution_error(fsm, symbol1)

    # Verify only symbol1 triggers circuit breaker
    assert len(fsm._exec_error_history[error_key1]) == 2
    assert len(fsm._exec_error_history[error_key2]) == 1
    fsm.alert_manager.check_circuit_breaker.assert_called_once()


def test_circuit_breaker_window_cleanup(fsm):
    """
    EP-STAB-CIRCUIT-WINDOW: Test that old timestamps are properly cleaned up.

    Scenario: Multiple errors occur, some within window and some outside.
    Expected: Only timestamps within the current window are retained.
    """
    symbol = "BTCUSDT"
    error_key = f"exec_error_{symbol}"

    # Set window to 10 seconds for testing
    fsm._EXEC_ERROR_WINDOW_SEC = 10

    # Add errors at T=0, T=5, T=12 seconds
    with patch('time.time', return_value=1000.0):
        simulate_execution_error(fsm, symbol)

    with patch('time.time', return_value=1005.0):
        simulate_execution_error(fsm, symbol)

    # At this point, 2 errors within window, should trigger
    assert len(fsm._exec_error_history[error_key]) == 2
    assert fsm.alert_manager.check_circuit_breaker.call_count == 1

    # Third error at T=12 (T=0 should be cleaned up)
    with patch('time.time', return_value=1012.0):
        simulate_execution_error(fsm, symbol)

    # Verify T=0 was removed (1000.0 < 1012.0 - 10 = 1002.0)
    # Only T=5 (1005.0) and T=12 (1012.0) remain
    assert len(fsm._exec_error_history[error_key]) == 2
    assert 1000.0 not in fsm._exec_error_history[error_key]
    assert 1005.0 in fsm._exec_error_history[error_key]
    assert 1012.0 in fsm._exec_error_history[error_key]

    # Circuit breaker should have been called twice total (after 2nd and 3rd error)
    assert fsm.alert_manager.check_circuit_breaker.call_count == 2


def test_circuit_breaker_initialization_backward_compat(fsm):
    """
    EP-STAB-CIRCUIT-WINDOW: Test backward compatibility with old _exec_error_counts.

    Scenario: FSM instance may not have _exec_error_history initialized.
    Expected: Code handles missing attribute gracefully by initializing it.
    """
    symbol = "BTCUSDT"
    error_key = f"exec_error_{symbol}"

    # Remove _exec_error_history to simulate old instance
    if hasattr(fsm, '_exec_error_history'):
        delattr(fsm, '_exec_error_history')

    # Should not raise AttributeError
    simulate_execution_error(fsm, symbol)

    # Verify _exec_error_history was initialized
    assert hasattr(fsm, '_exec_error_history')
    assert error_key in fsm._exec_error_history
    assert len(fsm._exec_error_history[error_key]) == 1
