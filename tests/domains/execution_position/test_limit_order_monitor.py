import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from apps.reference.domains.execution_position.limit_order_monitor import LimitOrderMonitor, LimitOrderState
from vfoundation.core.protocol import Message

class DummyObj:
    pass

class MockConfig:
    def __init__(self, enabled=True, timeout=30, auto_cancel=True, max_orders=3):
        self.trading = DummyObj()
        self.trading.execution = DummyObj()
        self.trading.execution.limit_orders = DummyObj()
        self.trading.execution.limit_orders.enable_monitoring = enabled
        self.trading.execution.limit_orders.default_timeout_sec = timeout
        self.trading.execution.limit_orders.auto_cancel_expired = auto_cancel
        self.trading.execution.limit_orders.max_limit_orders_per_symbol = max_orders

@pytest.fixture
def adapter_mock():
    adapter = AsyncMock()
    adapter.cancel_order = AsyncMock()
    return adapter

@pytest.fixture
def bus_mock():
    bus = MagicMock()
    bus.emit = MagicMock()
    return bus

@pytest.fixture
def monitor(adapter_mock, bus_mock):
    config = MockConfig(enabled=True, timeout=1, auto_cancel=True, max_orders=2)
    return LimitOrderMonitor(adapter=adapter_mock, config=config, bus=bus_mock)

@pytest.mark.asyncio
async def test_init_config_parsing(adapter_mock, bus_mock):
    # Test initialization with empty obj fails safely to defaults
    m = LimitOrderMonitor(adapter=adapter_mock, config=DummyObj())
    assert m._enabled is True
    assert m._default_timeout_sec == 30
    assert m._auto_cancel is True
    assert m._max_per_symbol == 3
    
    # Test valid config parsing
    config = MockConfig(enabled=False, timeout=10, auto_cancel=False, max_orders=5)
    m2 = LimitOrderMonitor(adapter=adapter_mock, config=config, bus=bus_mock)
    assert m2._enabled is False
    assert m2._default_timeout_sec == 10
    assert m2._auto_cancel is False
    assert m2._max_per_symbol == 5

class MockConfigErr:
    @property
    def trading(self):
        raise AttributeError("Mock Error")

@pytest.mark.asyncio
async def test_init_config_attribute_error(adapter_mock):
    # Test hasattr or attribute access raising error
    config = MockConfigErr()
    
    m = LimitOrderMonitor(adapter=adapter_mock, config=config)
    assert m._enabled is True

@pytest.mark.asyncio
async def test_start_stop(monitor):
    assert monitor._running is False
    await monitor.start()
    assert monitor._running is True
    
    # Register an order to create a task
    monitor.register_limit_order("order1", "BTCUSDT", "BUY", 50000.0, 1.0, "client1")
    assert len(monitor._timer_tasks) == 1
    task = monitor._timer_tasks["order1"]
    assert not task.done()
    
    await monitor.stop()
    assert monitor._running is False
    assert len(monitor._timer_tasks) == 0
    await asyncio.sleep(0) # yield to loop
    assert task.cancelled()

@pytest.mark.asyncio
async def test_disabled_monitor(adapter_mock, bus_mock):
    config = MockConfig(enabled=False)
    m = LimitOrderMonitor(adapter=adapter_mock, config=config, bus=bus_mock)
    await m.start()
    assert m._running is False
    
    m.register_limit_order("order1", "BTCUSDT", "BUY", 50000.0, 1.0, "client1")
    assert len(m._active_orders) == 0

@pytest.mark.asyncio
async def test_max_orders_per_symbol(monitor):
    await monitor.start()
    # Limit is 2 in fixture config
    monitor.register_limit_order("o1", "BTCUSDT", "BUY", 50000, 1, "c1")
    monitor.register_limit_order("o2", "BTCUSDT", "BUY", 50000, 1, "c2")
    assert monitor.get_symbol_count("BTCUSDT") == 2
    
    # Third should be rejected
    monitor.register_limit_order("o3", "BTCUSDT", "BUY", 50000, 1, "c3")
    assert monitor.get_symbol_count("BTCUSDT") == 2
    assert "o3" not in monitor._active_orders
    assert monitor._metrics['orders_cancelled_limit'] == 1
    
    assert monitor.can_place_limit_order("BTCUSDT") is False
    assert monitor.can_place_limit_order("ETHUSDT") is True

@pytest.mark.asyncio
async def test_unregister_order(monitor):
    await monitor.start()
    monitor.register_limit_order("o1", "BTCUSDT", "BUY", 50000, 1, "c1")
    assert "o1" in monitor._active_orders
    assert "o1" in monitor._timer_tasks
    
    task = monitor._timer_tasks["o1"]
    monitor.unregister_order("o1")
    
    assert "o1" not in monitor._active_orders
    assert "o1" not in monitor._timer_tasks
    await asyncio.sleep(0) # yield to loop
    assert task.cancelled()
    assert monitor.get_symbol_count("BTCUSDT") == 0

@pytest.mark.asyncio
async def test_unregister_nonexistent_order(monitor):
    monitor.unregister_order("not_an_order") # Should safely return None and do nothing
    assert len(monitor._active_orders) == 0

@pytest.mark.asyncio
async def test_expire_auto_cancel_and_event_emission(monitor, adapter_mock, bus_mock):
    await monitor.start()
    # Mock sleep to run fast
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        monitor.register_limit_order("o1", "BTCUSDT", "BUY", 50000, 1, "c1", timeout_sec=10, rid="req-123")
        
        # Manually await the task
        task = monitor._timer_tasks["o1"]
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        mock_sleep.assert_called_once_with(10)
        adapter_mock.cancel_order.assert_called_once_with("BTCUSDT", "o1")
        
        # Verify event emission
        assert bus_mock.emit.call_count == 1
        emitted_msg = bus_mock.emit.call_args[0][0]
        assert isinstance(emitted_msg, Message)
        assert emitted_msg.op == "EVT"
        assert emitted_msg.verb == "LIMIT_ORDER_TIMEOUT"
        assert emitted_msg.pld["symbol"] == "BTCUSDT"
        assert emitted_msg.pld["order_id"] == "o1"
        assert emitted_msg.pld["timeout_sec"] == 10
        assert emitted_msg.rid == "req-123"
        
        assert "o1" not in monitor._active_orders
        assert monitor._metrics['orders_cancelled_timeout'] == 1

@pytest.mark.asyncio
async def test_expire_no_auto_cancel(adapter_mock, bus_mock):
    config = MockConfig(enabled=True, timeout=10, auto_cancel=False, max_orders=3)
    monitor = LimitOrderMonitor(adapter=adapter_mock, config=config, bus=bus_mock)
    await monitor.start()
    
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        monitor.register_limit_order("o1", "BTCUSDT", "BUY", 50000, 1, "c1")
        task = monitor._timer_tasks["o1"]
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        adapter_mock.cancel_order.assert_not_called()
        bus_mock.emit.assert_not_called()
        assert "o1" not in monitor._active_orders # Still unregisters
        assert monitor.get_symbol_count("BTCUSDT") == 0

@pytest.mark.asyncio
async def test_cancel_error_handling(monitor, adapter_mock, bus_mock):
    await monitor.start()
    adapter_mock.cancel_order.side_effect = Exception("API error")
    
    with patch("asyncio.sleep", new_callable=AsyncMock):
        monitor.register_limit_order("o1", "BTCUSDT", "BUY", 50000, 1, "c1")
        task = monitor._timer_tasks["o1"]
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        # Should catch the error, log it, increment error metric, and unregister
        assert monitor._metrics['errors'] == 1
        assert "o1" not in monitor._active_orders

@pytest.mark.asyncio
async def test_get_active_orders_and_metrics(monitor):
    monitor.register_limit_order("o1", "BTCUSDT", "BUY", 50000, 1, "c1")
    monitor.register_limit_order("o2", "ETHUSDT", "BUY", 3000, 1, "c2")
    
    all_orders = monitor.get_active_orders()
    assert len(all_orders) == 2
    
    btc_orders = monitor.get_active_orders("BTCUSDT")
    assert len(btc_orders) == 1
    assert "o1" in btc_orders
    
    metrics = monitor.get_metrics()
    assert metrics['active_orders'] == 2
    assert metrics['tracked_symbols'] == 2

@pytest.mark.asyncio
async def test_limit_order_state_methods():
    state = LimitOrderState(
        order_id="o1",
        symbol="BTC",
        side="BUY",
        price=Decimal("100"),
        qty=Decimal("1"),
        client_order_id="c1",
        placed_ts=100.0,
        timeout_sec=10
    )
    
    assert state.age_seconds(105.0) == 5.0
    assert state.is_expired(105.0) is False
    assert state.is_expired(115.0) is True

@pytest.mark.asyncio
async def test_timer_creation_without_loop(adapter_mock, bus_mock):
    # If no event loop is running (which raises RuntimeError in get_event_loop),
    # it shouldn't crash
    monitor = LimitOrderMonitor(adapter=adapter_mock, bus=bus_mock)
    
    with patch("asyncio.get_event_loop", side_effect=RuntimeError("no loop")):
        monitor.register_limit_order("o1", "BTCUSDT", "BUY", 50000, 1, "c1")
        
        assert "o1" in monitor._active_orders
        assert "o1" not in monitor._timer_tasks # Task not created gracefully
