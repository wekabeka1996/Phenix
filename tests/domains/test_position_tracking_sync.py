
import decimal
from unittest.mock import MagicMock
import pytest
from vfoundation.core.protocol import Message
from apps.reference.domains.position_tracking.position_tracking import PositionTracking

@pytest.fixture
def position_tracking_domain():
    """Creates a PositionTracking instance with a mock FSM for testing."""
    fsm = MagicMock()
    config = {} # No complex config needed for this unit test
    pt = PositionTracking(fsm=fsm, config=config)
    pt.logger = MagicMock() # Mock logger to suppress output during tests
    return pt

def test_reconciliation_removes_ghost_positions(position_tracking_domain):
    """
    Verify that the on_account_update reconciliation logic correctly removes positions
    that exist internally but are not present in the update from the exchange.
    """
    # 1. Arrange: Create a desynchronized state
    pt = position_tracking_domain
    
    # This position exists in our internal state but not on the exchange (a "ghost")
    pt._positions['GHOST_POS'] = {
        'net_position': decimal.Decimal('1.0'),
        'avg_entry_price': decimal.Decimal('100'),
        'realized_pnl': decimal.Decimal('10')
    }
    
    # This position exists both internally and on the exchange
    pt._positions['REAL_POS'] = {
        'net_position': decimal.Decimal('-0.5'),
        'avg_entry_price': decimal.Decimal('2000'),
        'realized_pnl': decimal.Decimal('25')
    }
    
    assert 'GHOST_POS' in pt._positions
    assert 'REAL_POS' in pt._positions

    # This is the ground truth from the exchange API, containing only the real position
    account_update_payload = {
        "wallet_balance": "10000",
        "positions": [
            {
                "symbol": "REAL_POS",
                "positionAmt": "-0.5",
                "entryPrice": "2000",
                "unRealizedProfit": "-5.0",
                "updateTime": 123456789
            }
        ]
    }
    account_update_event = Message(op="EVT", verb="ACCOUNT_UPDATE_RECEIVED", src="test", dst="test", pld=account_update_payload)

    # 2. Act: Trigger the reconciliation logic
    pt.on_account_update(account_update_event)

    # 3. Assert: Check that the internal state is now synchronized
    # The ghost position should be gone
    assert 'GHOST_POS' not in pt._positions, "Ghost position should have been removed"
    
    # The real position should still exist
    assert 'REAL_POS' in pt._positions, "Real position should be preserved"
    
    # The preserved position should have its realized PnL carried over
    assert pt._positions['REAL_POS']['realized_pnl'] == decimal.Decimal('25'), \
        "Realized PnL of existing positions should be preserved"
        
    # The logger should have been called to warn about the removed ghost position
    pt.logger.warning.assert_called_once()
    log_call_args = pt.logger.warning.call_args[0][0]
    assert "Reconciliation removed 1 ghost position(s): GHOST_POS" in log_call_args
