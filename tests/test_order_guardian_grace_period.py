import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from apps.reference.domains.execution_position.order_guardian import OrderGuardian

@pytest.mark.asyncio
async def test_cleanup_orphans_grace_period_recovery():
    """
    Test that cleanup_orphans waits and retries if position is missing initially,
    and aborts cleanup if position reappears.
    """
    # Mock adapter
    adapter = AsyncMock()
    
    # Scenario: 
    # 1. First call: No position (empty list)
    # 2. Second call: No position
    # 3. Third call: Position appears!
    
    # We need to mock get_open_positions to return different values on consecutive calls
    # Note: The logic I plan to implement will call get_open_positions multiple times
    
    empty_pos = []
    real_pos = [MagicMock(symbol="ETHUSDT", position_amount="1.5")]
    
    adapter.get_open_positions.side_effect = [
        empty_pos, # Initial check
        empty_pos, # Retry 1
        empty_pos, # Retry 2
        real_pos   # Retry 3 (Success!)
    ]
    
    # Mock open orders to ensure we have candidates (otherwise grace period is skipped)
    adapter.get_open_orders.return_value = [
        {"symbol": "ETHUSDT", "orderId": "101", "type": "STOP_MARKET", "reduceOnly": True}
    ]
    
    # Mock clock
    clock = MagicMock()
    clock.time.return_value = 1000.0
    
    guardian = OrderGuardian(adapter=adapter, clock=clock)
    
    # We need to patch asyncio.sleep to avoid waiting 24 seconds in test
    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        # Run cleanup
        cancelled = await guardian.cleanup_orphans(symbol="ETHUSDT", hard=False)
        
        # Assertions
        assert cancelled == 0
        
        # Should have slept 3 times (for the 3 retries)
        # Wait, if it succeeds on the 3rd retry, it might sleep 3 times.
        # Let's see the logic:
        # Check 1 (Fail) -> Sleep -> Check 2 (Fail) -> Sleep -> Check 3 (Fail) -> Sleep -> Check 4 (Success) -> Return
        # Or: Check 1 (Fail) -> Loop 3 times: [Sleep, Check]. 
        
        # Expected calls to get_open_positions: Initial + 3 Retries = 4 calls max.
        # In my side_effect, the 4th call returns real_pos.
        
        assert adapter.get_open_positions.call_count == 4
        assert mock_sleep.call_count == 3
        mock_sleep.assert_called_with(8.0) # 8 seconds interval

@pytest.mark.asyncio
async def test_cleanup_orphans_grace_period_failure():
    """
    Test that cleanup_orphans proceeds to cleanup if position is missing 
    after all retries.
    """
    adapter = AsyncMock()
    
    # Always empty
    adapter.get_open_positions.return_value = []
    
    # Mock open orders to simulate cancellation
    adapter.get_open_orders.return_value = [
        {"symbol": "ETHUSDT", "orderId": "101", "type": "STOP_MARKET", "reduceOnly": True}
    ]
    adapter.cancel_order.return_value = {"status": "CANCELED"}
    
    clock = MagicMock()
    clock.time.return_value = 1000.0
    
    guardian = OrderGuardian(adapter=adapter, clock=clock)
    
    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        cancelled = await guardian.cleanup_orphans(symbol="ETHUSDT", hard=False)
        
        # Should have cancelled 1 order
        assert cancelled == 1
        
        # Should have retried 3 times
        # Initial + 3 retries = 4 calls
        assert adapter.get_open_positions.call_count == 4
        assert mock_sleep.call_count == 3

