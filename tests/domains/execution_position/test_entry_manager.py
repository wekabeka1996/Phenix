import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from apps.reference.domains.execution_position.entry_manager import EntryManager
from apps.reference.core.time import get_clock

class MockFSM:
    def __init__(self, shadow_mode=False, loop=None):
        self.watchdog = MagicMock()
        self.watchdog.pending_orders = {}
        self.watchdog.acked_orders = {}
        self.watchdog.cancel_attempt_count = 0
        self.watchdog.cancel_success_count = 0
        self.adapter = AsyncMock()
        self.shadow_mode = shadow_mode
        self._loop = loop
        self._pending_entry_meta = {}
        self._is_cancel_success_response = MagicMock(return_value=True)
        self._is_unknown_order_error = MagicMock(return_value=False)
        self.config = MagicMock()
        self.metrics_collector = MagicMock()
        self.alert_manager = MagicMock()
        self._supersede_canceling = set()
        self._supersede_queue = {}
        self.fsm = MagicMock()

    def _get_async_loop(self):
        return self._loop

    async def _cancel_order(self, sym, oid):
        return await self.adapter.cancel_order(sym, oid)

    def _submit_async(self, coro, loop):
        asyncio.run_coroutine_threadsafe(coro, loop)

    async def _execute_decision(self, decision):
        pass

class MockDeadline:
    def __init__(self, symbol, order_id, rid="test_rid", timeout_type_val="TEST_TIMEOUT"):
        self.symbol = symbol
        self.order_id = order_id
        self.rid = rid
        self.corr_id = "corr123"
        self.client_order_id = "cl123"
        self.timeout_type = MagicMock()
        self.timeout_type.value = timeout_type_val

@pytest.fixture
def fsm():
    loop = asyncio.new_event_loop()
    fsm = MockFSM(loop=loop)
    yield fsm
    loop.close()

@pytest.fixture
def entry_manager(fsm):
    return EntryManager(fsm)

def test_cancel_pending_entries_no_watchdog(entry_manager, fsm):
    fsm.watchdog = None
    entry_manager.cancel_pending_entries_for_symbol("BTCUSDT", "REASON")

def test_cancel_pending_entries_sync_shadow_mode(entry_manager, fsm):
    fsm.shadow_mode = True
    fsm.watchdog.pending_orders = {"o1": MockDeadline("BTCUSDT", "o1")}
    fsm.watchdog.acked_orders = {"o2": MockDeadline("BTCUSDT", "o2")}
    fsm._pending_entry_meta = {"o1": "meta", "o2": "meta"}
    
    entry_manager.cancel_pending_entries_for_symbol("BTCUSDT", "SYNC_CANCEL")
    
    assert fsm.watchdog.on_order_cancel.call_count == 2
    assert "o1" not in fsm._pending_entry_meta
    assert "o2" not in fsm._pending_entry_meta

@pytest.mark.asyncio
async def test_cancel_pending_entries_async_success(entry_manager, fsm):
    tasks = []
    fsm._submit_async = lambda coro, loop: tasks.append(asyncio.create_task(coro))
    
    fsm.watchdog.pending_orders = {"o1": MockDeadline("BTCUSDT", "o1")}
    fsm._pending_entry_meta = {"o1": "meta"}
    
    entry_manager.cancel_pending_entries_for_symbol("BTCUSDT", "ASYNC_CANCEL", filter_order_ids={"o1"})
    
    assert len(tasks) == 1
    await asyncio.gather(*tasks)
    
    fsm.adapter.cancel_order.assert_called_with("BTCUSDT", "o1")
    fsm.watchdog.on_order_cancel.assert_called_with("o1")
    assert "o1" not in fsm._pending_entry_meta

@pytest.mark.asyncio
async def test_cancel_pending_entries_async_unknown_order(entry_manager, fsm):
    tasks = []
    fsm._submit_async = lambda coro, loop: tasks.append(asyncio.create_task(coro))
    fsm.watchdog.pending_orders = {"o1": MockDeadline("BTCUSDT", "o1")}
    fsm.adapter.cancel_order.side_effect = Exception("-2011 Unknown Order")
    fsm._is_unknown_order_error.return_value = True
    
    entry_manager.cancel_pending_entries_for_symbol("BTCUSDT", "ASYNC_CANCEL")
    await asyncio.gather(*tasks)
    
    # Should be removed from watchdog silently
    fsm.watchdog.on_order_cancel.assert_called_with("o1")

@pytest.mark.asyncio
async def test_cancel_pending_entries_async_other_error(entry_manager, fsm):
    tasks = []
    fsm._submit_async = lambda coro, loop: tasks.append(asyncio.create_task(coro))
    fsm.watchdog.pending_orders = {"o1": MockDeadline("BTCUSDT", "o1")}
    fsm.adapter.cancel_order.side_effect = Exception("General API Error")
    fsm._is_unknown_order_error.return_value = False
    
    entry_manager.cancel_pending_entries_for_symbol("BTCUSDT", "ASYNC_CANCEL")
    await asyncio.gather(*tasks)
    
    # Watchdog should NOT remove it because it failed unexpectedly
    fsm.watchdog.on_order_cancel.assert_not_called()

def test_cancel_all_pending_entries(entry_manager, fsm):
    fsm.watchdog.pending_orders = {"o1": MockDeadline("BTCUSDT", "o1")}
    fsm.watchdog.acked_orders = {"o2": MockDeadline("ETHUSDT", "o2")}
    fsm.shadow_mode = True
    
    entry_manager.cancel_all_pending_entries()
    
    assert fsm.watchdog.on_order_cancel.call_count == 2
    fsm.watchdog.on_order_cancel.assert_any_call("o1")
    fsm.watchdog.on_order_cancel.assert_any_call("o2")

def test_on_panic_killswitch_activated(entry_manager, fsm):
    fsm.shadow_mode = True
    fsm.watchdog.pending_orders = {"o1": MockDeadline("BTCUSDT", "o1")}
    
    # Enabled
    fsm.config.domains.execution_position.pending_entry_ttl.enabled = True
    fsm.config.domains.execution_position.pending_entry_ttl.cancel_on_panic = True
    
    entry_manager.on_panic_killswitch_activated()
    fsm.watchdog.on_order_cancel.assert_called_with("o1")
    
    # Disabled
    fsm.watchdog.on_order_cancel.reset_mock()
    fsm.config.domains.execution_position.pending_entry_ttl.cancel_on_panic = False
    entry_manager.on_panic_killswitch_activated()
    fsm.watchdog.on_order_cancel.assert_not_called()
    
    # Attribute error falls back to executing
    del fsm.config.domains
    entry_manager.on_panic_killswitch_activated()
    fsm.watchdog.on_order_cancel.assert_called_with("o1")

@pytest.mark.asyncio
async def test_process_queued_supersede(entry_manager, fsm):
    fsm._supersede_canceling.add("BTCUSDT")
    fsm._supersede_queue["BTCUSDT"] = {"decision": {"type": "OPEN"}, "queued_at": 1234}
    
    # Test with loop
    fsm._submit_async = MagicMock()
    entry_manager.process_queued_supersede("BTCUSDT")
    
    assert "BTCUSDT" not in fsm._supersede_canceling
    assert "BTCUSDT" not in fsm._supersede_queue
    assert fsm._submit_async.call_count == 1

def test_process_queued_supersede_no_loop(entry_manager, fsm):
    fsm._loop = None
    fsm._supersede_canceling.add("BTCUSDT")
    fsm._supersede_queue["BTCUSDT"] = {"decision": {"type": "OPEN"}}
    
    entry_manager.process_queued_supersede("BTCUSDT")
    # Should not crash, just logs an error

def test_process_queued_supersede_no_decision(entry_manager, fsm):
    fsm._supersede_queue["BTCUSDT"] = {}
    entry_manager.process_queued_supersede("BTCUSDT")
    # Logs warning

@pytest.mark.asyncio
@patch("vfoundation.core.fsm_emit_compat.emit_compat", new_callable=AsyncMock)
async def test_handle_order_timeout_success(mock_emit, entry_manager, fsm):
    deadline = MockDeadline("BTCUSDT", "o1")
    fsm.adapter.cancel_order.return_value = {"status": "CANCELED"}
    fsm._is_cancel_success_response.return_value = True

    lifecycle = MagicMock()
    with patch(
        "apps.reference.domains.execution_position.terminal_order_contracts._trade_lifecycle",
        lifecycle,
    ):
        await entry_manager.handle_order_timeout(deadline)
    
    assert fsm.watchdog.cancel_attempt_count == 1
    assert fsm.watchdog.cancel_success_count == 1
    fsm.metrics_collector.record_order_timeout.assert_called_once()
    mock_emit.assert_called_once()
    emitted = mock_emit.call_args[0][1]
    assert emitted.verb == "ORDER_TIMEOUT"
    lifecycle.on_cancel.assert_called_once_with(
        rid="test_rid",
        cancel_reason="timeout_cancellation",
    )

@pytest.mark.asyncio
@patch("vfoundation.core.fsm_emit_compat.emit_compat", new_callable=AsyncMock)
async def test_handle_order_timeout_reject(mock_emit, entry_manager, fsm):
    deadline = MockDeadline("BTCUSDT", "o1")
    fsm.adapter.cancel_order.return_value = {"status": "REJECTED"}
    fsm._is_cancel_success_response.return_value = False
    
    await entry_manager.handle_order_timeout(deadline)
    # Success count shouldn't increment
    assert fsm.watchdog.cancel_success_count == 0

@pytest.mark.asyncio
@patch("vfoundation.core.fsm_emit_compat.emit_compat", new_callable=AsyncMock)
async def test_handle_order_timeout_exception(mock_emit, entry_manager, fsm):
    deadline = MockDeadline("BTCUSDT", "o1")
    fsm.adapter.cancel_order.side_effect = Exception("API Error")
    fsm._is_unknown_order_error.return_value = False
    
    await entry_manager.handle_order_timeout(deadline)
    assert fsm.watchdog.cancel_success_count == 0

@pytest.mark.asyncio
@patch("vfoundation.core.fsm_emit_compat.emit_compat", new_callable=AsyncMock)
async def test_handle_order_timeout_unknown_order(mock_emit, entry_manager, fsm):
    deadline = MockDeadline("BTCUSDT", "o1")
    fsm.adapter.cancel_order.side_effect = Exception("-2011 Unknown Order")
    fsm._is_unknown_order_error.return_value = True

    lifecycle = MagicMock()
    with patch(
        "apps.reference.domains.execution_position.terminal_order_contracts._trade_lifecycle",
        lifecycle,
    ):
        await entry_manager.handle_order_timeout(deadline)
    # Counts as success
    assert fsm.watchdog.cancel_success_count == 1
    lifecycle.on_cancel.assert_called_once_with(
        rid="test_rid",
        cancel_reason="timeout_cancel_idempotent",
    )

@pytest.mark.asyncio
@patch("vfoundation.core.fsm_emit_compat.emit_compat", new_callable=AsyncMock)
async def test_handle_order_timeout_circuit_breaker(mock_emit, entry_manager, fsm):
    deadline = MockDeadline("BTCUSDT", "o1")
    fsm._timeout_counts = {"timeout_BTCUSDT": 2} # Next will be 3
    
    await entry_manager.handle_order_timeout(deadline)
    
    assert fsm._timeout_counts["timeout_BTCUSDT"] == 3
    fsm.alert_manager.check_circuit_breaker.assert_called_with(True, 300)
