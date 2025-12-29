"""
Tests for runtime factory and V2RuntimeFacade mapping logic.
"""
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from apps.reference.domains.execution_position.infra.runtime_factory import build_execution_runtime, V2RuntimeFacade

@dataclass
class MockMessage:
    op: str
    verb: str
    pld: dict
    ts: float = 1234567890.0

class MockConfig:
    def __init__(self, data):
        self.data = data
    def to_dict(self):
        return self.data

@pytest.fixture
def mock_fsm():
    return MagicMock()

@pytest.fixture
def mock_adapter():
    return MagicMock()

def test_factory_legacy_mode_raises_error(mock_fsm, mock_adapter):
    """Ensure legacy mode raises ValueError."""
    config = MockConfig({"execution_position": {"runtime_mode": "legacy"}})

    with pytest.raises(ValueError, match="ExecPosFSM \(legacy mode\) has been removed"):
        build_execution_runtime(config, mock_fsm, mock_adapter)

def test_factory_default_mode_is_v2(mock_fsm, mock_adapter):
    """Ensure default mode builds V2."""
    config = MockConfig({}) # No runtime_mode

    # We need to mock ExecPosRuntimeV2 to avoid full instantiation
    with patch("apps.reference.domains.execution_position.infra.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_instance = MagicMock()
        MockV2.return_value = mock_instance

        runtime = build_execution_runtime(config, mock_fsm, mock_adapter)

        assert isinstance(runtime, V2RuntimeFacade)
        MockV2.assert_called_once()
        assert runtime.runtime == mock_instance

def test_factory_v2_mode(mock_fsm, mock_adapter):
    """Ensure explicit v2 mode builds V2."""
    config = MockConfig({"execution_position": {"runtime_mode": "v2"}})

    with patch("apps.reference.domains.execution_position.infra.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_instance = MagicMock()
        MockV2.return_value = mock_instance

        runtime = build_execution_runtime(config, mock_fsm, mock_adapter)

        assert isinstance(runtime, V2RuntimeFacade)
        MockV2.assert_called_once()
        assert runtime.runtime == mock_instance

def test_factory_invalid_mode_defaults_to_v2(mock_fsm, mock_adapter):
    """Ensure invalid mode defaults to V2."""
    config = MockConfig({"execution_position": {"runtime_mode": "invalid_mode"}})

    with patch("apps.reference.domains.execution_position.infra.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_instance = MagicMock()
        MockV2.return_value = mock_instance

        runtime = build_execution_runtime(config, mock_fsm, mock_adapter)

        assert isinstance(runtime, V2RuntimeFacade)
        MockV2.assert_called_once()

def test_facade_entry_intent_mapping():
    """Test mapping of CMD:OPEN to ENTRY_INTENT."""
    facade = V2RuntimeFacade(config={}, adapter=MagicMock())
    facade.runtime = MagicMock()
    facade._submit_to_loop = MagicMock()

    msg = MockMessage(
        op="CMD",
        verb="OPEN",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "1.0", "price": "50000"}
    )

    facade.handle(msg)

    assert facade.runtime.handle.called
    event = facade.runtime.handle.call_args[0][0]
    assert event.kind == "ENTRY_INTENT"
    assert event.symbol == "BTCUSDT"
    assert event.payload["side"] == "BUY"
    assert str(event.payload["quantity"]) == "1.0"

def test_facade_cancel_intent_mapping():
    """Test mapping of CMD:CANCEL to CANCEL_INTENT."""
    facade = V2RuntimeFacade(config={}, adapter=MagicMock())
    facade.runtime = MagicMock()
    facade._submit_to_loop = MagicMock()

    msg = MockMessage(
        op="CMD",
        verb="CANCEL",
        pld={"symbol": "BTCUSDT", "order_id": "123"}
    )

    facade.handle(msg)

    assert facade.runtime.handle.called
    event = facade.runtime.handle.call_args[0][0]
    assert event.kind == "CANCEL_INTENT"
    assert event.payload["order_id"] == "123"

def test_facade_trade_executed_mapping():
    """Test mapping of EVT:TRADE_EXECUTED to TRADE_EXECUTED."""
    facade = V2RuntimeFacade(config={}, adapter=MagicMock())
    facade.runtime = MagicMock()
    facade._submit_to_loop = MagicMock()

    msg = MockMessage(
        op="EVT",
        verb="TRADE_EXECUTED",
        pld={"symbol": "BTCUSDT", "order_id": "123", "last_qty": "0.5", "last_price": "50100"}
    )

    facade.handle(msg)

    assert facade.runtime.handle.called
    event = facade.runtime.handle.call_args[0][0]
    assert event.kind == "TRADE_EXECUTED"
    assert event.payload["quantity"] == "0.5"
    assert event.payload["price"] == "50100"

def test_facade_ignored_message():
    """Test that irrelevant messages are ignored."""
    facade = V2RuntimeFacade(config={}, adapter=MagicMock())
    facade.runtime = MagicMock()
    facade._submit_to_loop = MagicMock()

    msg = MockMessage(op="INFO", verb="HEARTBEAT", pld={})

    facade.handle(msg)

    assert not facade.runtime.handle.called


# ============================================================================
# New tests for runtime_factory fixes (CLEANUP-S1)
# ============================================================================

def test_facade_snapshot_interval_uses_runtime_constant():
    """Ensure facade uses constant from ExecPosRuntimeV2, not hardcoded value."""
    from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2

    with patch("apps.reference.domains.execution_position.infra.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_runtime = MagicMock()
        mock_runtime.set_snapshot_refresh_hook = MagicMock()
        MockV2.return_value = mock_runtime
        MockV2.SNAPSHOT_REQUEST_INTERVAL_SEC = 5.0

        facade = V2RuntimeFacade(config={}, adapter=MagicMock())

        # Verify it uses the constant, not a hardcoded value
        assert facade._snapshot_request_interval_sec == ExecPosRuntimeV2.SNAPSHOT_REQUEST_INTERVAL_SEC


def test_facade_get_agg_oco_state_snapshot_delegates_to_runtime():
    """Ensure get_agg_oco_state_snapshot delegates to runtime."""
    with patch("apps.reference.domains.execution_position.infra.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_runtime = MagicMock()
        mock_runtime.set_snapshot_refresh_hook = MagicMock()
        mock_runtime.get_positions_snapshot = MagicMock(return_value=[
            {"symbol": "BTCUSDT", "qty": 1.0, "side": "LONG"}
        ])
        MockV2.return_value = mock_runtime
        MockV2.SNAPSHOT_REQUEST_INTERVAL_SEC = 5.0

        facade = V2RuntimeFacade(config={}, adapter=MagicMock())

        result = facade.get_agg_oco_state_snapshot(symbol="BTCUSDT", side="LONG")

        mock_runtime.get_positions_snapshot.assert_called_once_with(
            symbol="BTCUSDT", side="LONG"
        )
        assert len(result) == 1
        assert result[0]["symbol"] == "BTCUSDT"


def test_facade_get_agg_oco_state_snapshot_no_filters():
    """Ensure get_agg_oco_state_snapshot works with no filters."""
    with patch("apps.reference.domains.execution_position.infra.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_runtime = MagicMock()
        mock_runtime.set_snapshot_refresh_hook = MagicMock()
        mock_runtime.get_positions_snapshot = MagicMock(return_value=[])
        MockV2.return_value = mock_runtime
        MockV2.SNAPSHOT_REQUEST_INTERVAL_SEC = 5.0

        facade = V2RuntimeFacade(config={}, adapter=MagicMock())

        result = facade.get_agg_oco_state_snapshot()

        mock_runtime.get_positions_snapshot.assert_called_once_with(
            symbol=None, side=None
        )
        assert result == []


# ============================================================================
# PERF-FIX: Tests for per-symbol throttle and sync execution
# ============================================================================

import time
import asyncio


class TestThrottleMechanism:
    """Test suite for per-symbol throttle logic."""

    def test_symbol_not_throttled_initially(self):
        """Symbol should not be throttled if never marked pending."""
        facade = V2RuntimeFacade(config={}, adapter=MagicMock())
        facade.runtime = MagicMock()

        assert facade._is_symbol_throttled("BTCUSDT") is False
        assert facade._is_symbol_throttled("ETHUSDT") is False

    def test_symbol_throttled_after_marking_pending(self):
        """Symbol should be throttled after being marked pending."""
        facade = V2RuntimeFacade(config={}, adapter=MagicMock())
        facade.runtime = MagicMock()

        facade._mark_symbol_pending("BTCUSDT")

        assert facade._is_symbol_throttled("BTCUSDT") is True
        # Other symbols should not be affected
        assert facade._is_symbol_throttled("ETHUSDT") is False

    def test_symbol_cleared_after_completion(self):
        """Symbol should not be throttled after pending status cleared."""
        facade = V2RuntimeFacade(config={}, adapter=MagicMock())
        facade.runtime = MagicMock()

        facade._mark_symbol_pending("BTCUSDT")
        assert facade._is_symbol_throttled("BTCUSDT") is True

        facade._clear_symbol_pending("BTCUSDT")
        assert facade._is_symbol_throttled("BTCUSDT") is False

    def test_throttle_timeout_clears_stale_lock(self):
        """Symbol lock should expire after timeout."""
        facade = V2RuntimeFacade(config={}, adapter=MagicMock())
        facade.runtime = MagicMock()
        facade._pending_timeout_sec = 0.1  # 100ms for fast test

        facade._mark_symbol_pending("BTCUSDT")
        assert facade._is_symbol_throttled("BTCUSDT") is True

        # Wait for timeout
        time.sleep(0.15)

        # Should auto-clear due to timeout
        assert facade._is_symbol_throttled("BTCUSDT") is False
        assert "BTCUSDT" not in facade._pending_symbols

    def test_multiple_symbols_independent(self):
        """Different symbols should have independent throttle state."""
        facade = V2RuntimeFacade(config={}, adapter=MagicMock())
        facade.runtime = MagicMock()

        facade._mark_symbol_pending("BTCUSDT")
        facade._mark_symbol_pending("ETHUSDT")

        assert facade._is_symbol_throttled("BTCUSDT") is True
        assert facade._is_symbol_throttled("ETHUSDT") is True
        assert facade._is_symbol_throttled("SOLUSDT") is False

        facade._clear_symbol_pending("BTCUSDT")

        assert facade._is_symbol_throttled("BTCUSDT") is False
        assert facade._is_symbol_throttled("ETHUSDT") is True


class TestThrottleInHandle:
    """Test throttle integration in handle() method."""

    def test_open_cmd_throttled_when_symbol_pending(self):
        """CMD:OPEN should be skipped if symbol already has pending order."""
        facade = V2RuntimeFacade(config={}, adapter=MagicMock())
        facade.runtime = MagicMock()
        # Mock async execution methods
        facade._execute_async_with_callback = MagicMock()
        facade._submit_to_loop = MagicMock()

        # Mark symbol as pending
        facade._mark_symbol_pending("BTCUSDT")

        msg = MockMessage(
            op="CMD",
            verb="OPEN",
            pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "1.0", "price": "50000"}
        )

        result = facade.handle(msg)

        # Should not have called runtime.handle due to throttle
        assert facade.runtime.handle.call_count == 0
        assert facade._execute_async_with_callback.call_count == 0

    def test_open_cmd_allowed_when_symbol_not_pending(self):
        """CMD:OPEN should proceed if symbol has no pending order."""
        facade = V2RuntimeFacade(config={}, adapter=MagicMock())
        facade.runtime = MagicMock()
        facade._execute_async_with_callback = MagicMock()
        facade._submit_to_loop = MagicMock()

        msg = MockMessage(
            op="CMD",
            verb="OPEN",
            pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "1.0", "price": "50000"}
        )

        facade.handle(msg)

        # Should have called runtime.handle
        assert facade.runtime.handle.call_count == 1
        # ENTRY_INTENT should use _execute_async_with_callback, not _submit_to_loop
        assert facade._execute_async_with_callback.call_count == 1
        assert facade._submit_to_loop.call_count == 0

    def test_open_cmd_different_symbol_not_blocked(self):
        """CMD:OPEN for different symbol should not be blocked."""
        facade = V2RuntimeFacade(config={}, adapter=MagicMock())
        facade.runtime = MagicMock()
        facade._execute_async_with_callback = MagicMock()
        facade._submit_to_loop = MagicMock()

        # Mark BTCUSDT as pending
        facade._mark_symbol_pending("BTCUSDT")

        # Try to open ETHUSDT
        msg = MockMessage(
            op="CMD",
            verb="OPEN",
            pld={"symbol": "ETHUSDT", "side": "BUY", "qty": "1.0", "price": "3000"}
        )

        facade.handle(msg)

        # Should have called runtime.handle for ETHUSDT
        assert facade.runtime.handle.call_count == 1
        event = facade.runtime.handle.call_args[0][0]
        assert event.symbol == "ETHUSDT"

    def test_cancel_cmd_not_affected_by_throttle(self):
        """CMD:CANCEL should not be affected by throttle."""
        facade = V2RuntimeFacade(config={}, adapter=MagicMock())
        facade.runtime = MagicMock()
        facade._execute_async_with_callback = MagicMock()
        facade._submit_to_loop = MagicMock()

        # Mark symbol as pending
        facade._mark_symbol_pending("BTCUSDT")

        msg = MockMessage(
            op="CMD",
            verb="CANCEL",
            pld={"symbol": "BTCUSDT", "order_id": "123"}
        )

        facade.handle(msg)

        # CANCEL should go through (uses _submit_to_loop, not throttled)
        assert facade.runtime.handle.call_count == 1
        assert facade._submit_to_loop.call_count == 1

    def test_entry_intent_marks_pending_before_execution(self):
        """Pending status should be set before execution starts."""
        facade = V2RuntimeFacade(config={}, adapter=MagicMock())
        facade.runtime = MagicMock()

        pending_at_call_time = [None]
        def capture_pending(coro, symbol, source):
            pending_at_call_time[0] = symbol in facade._pending_symbols

        facade._execute_async_with_callback = capture_pending
        facade._submit_to_loop = MagicMock()

        msg = MockMessage(
            op="CMD",
            verb="OPEN",
            pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "1.0", "price": "50000"}
        )

        facade.handle(msg)

        # Symbol should have been marked pending BEFORE execute was called
        assert pending_at_call_time[0] is True


class TestSyncExecution:
    """Test _execute_sync method."""

    def test_execute_sync_outside_event_loop(self):
        """_execute_sync should use asyncio.run() when not in event loop."""
        facade = V2RuntimeFacade(config={}, adapter=MagicMock())
        facade.runtime = MagicMock()

        result_value = {"success": True}

        async def mock_coro():
            return result_value

        result = facade._execute_sync(mock_coro(), source="test")

        assert result == result_value

    def test_execute_sync_handles_exception(self):
        """_execute_sync should handle exceptions gracefully."""
        facade = V2RuntimeFacade(config={}, adapter=MagicMock())
        facade.runtime = MagicMock()

        async def failing_coro():
            raise ValueError("Test error")

        # Should not raise, returns None
        result = facade._execute_sync(failing_coro(), source="test")

        assert result is None


class TestAsyncWithCallback:
    """Test _execute_async_with_callback method."""

    def test_callback_clears_pending_on_success(self):
        """Callback should clear pending status when task succeeds."""
        import asyncio

        facade = V2RuntimeFacade(config={}, adapter=MagicMock())
        facade.runtime = MagicMock()

        async def mock_coro():
            return {"success": True}

        # Run in an event loop to test callback behavior
        async def test_case():
            facade._mark_symbol_pending("BTCUSDT")
            assert "BTCUSDT" in facade._pending_symbols

            facade._execute_async_with_callback(
                mock_coro(),
                symbol="BTCUSDT",
                source="test"
            )

            # Give event loop time to process
            await asyncio.sleep(0.1)

            # Callback should have cleared pending
            assert "BTCUSDT" not in facade._pending_symbols

        asyncio.run(test_case())

    def test_callback_clears_pending_on_failure(self):
        """Callback should clear pending status even when task fails."""
        import asyncio

        facade = V2RuntimeFacade(config={}, adapter=MagicMock())
        facade.runtime = MagicMock()

        async def failing_coro():
            raise ValueError("Test error")

        async def test_case():
            facade._mark_symbol_pending("BTCUSDT")
            assert "BTCUSDT" in facade._pending_symbols

            facade._execute_async_with_callback(
                failing_coro(),
                symbol="BTCUSDT",
                source="test"
            )

            # Give event loop time to process
            await asyncio.sleep(0.1)

            # Callback should have cleared pending even on error
            assert "BTCUSDT" not in facade._pending_symbols

        asyncio.run(test_case())
