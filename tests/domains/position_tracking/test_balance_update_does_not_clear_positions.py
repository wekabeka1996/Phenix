import pytest
import decimal
import time
from unittest.mock import MagicMock, Mock
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from vfoundation.core.protocol import Message

@pytest.fixture
def mock_fsm():
    fsm = Mock()
    fsm.listen = Mock()
    fsm.emit = Mock()
    return fsm

@pytest.fixture
def mock_config():
    # Construct a Pure MagicMock Config, avoiding fragile imports
    config = MagicMock()
    
    # Mock domains.position_tracking config tree
    pt_config = MagicMock()
    pt_config.enable_market_tick_subscription = False
    pt_config.positions_stale_ttl_sec = 60.0
    
    precision = MagicMock()
    precision.quantity_min_threshold = 0.0001
    precision.flat_position_threshold = 0.0001
    precision.decimal_places = 4
    pt_config.precision = precision
    
    # Structure: config.domains.position_tracking
    domains = MagicMock()
    domains.position_tracking = pt_config
    config.domains = domains
    
    # Mock config.trading.execution.exposure (Required by _calculate_margin_by_side)
    exposure = MagicMock()
    exposure.leverage_defaults = {"__default__": "10.0"} # Fallback 10x leverage
    
    execution = MagicMock()
    execution.exposure = exposure
    
    trading = MagicMock()
    trading.execution = execution
    config.trading = trading
    
    return config

class TestPositionTrackingPersistence:
    
    def test_balance_update_preserves_positions(self, mock_fsm, mock_config):
        """
        Verify BUGFIX-007: Balance updates (non-authoritative) should NOT clear cached positions.
        """
        tracker = PositionTracking(mock_fsm, mock_config)
        
        # 1. Open a position via TRADE_EXECUTED
        trade_event = Message(
            op="EVT",
            verb="EVT:TRADE_EXECUTED",
            pld={
                "symbol": "BTCUSDT",
                "side": "buy",
                "price": "50000",
                "quantity": "1.0",
                "fees": "5.0",
                "venue": "binance",
                "ts": int(time.time() * 1000)
            },
            src="execution",
            dst="position_tracking",
            rid="test-rid-1"
        )
        tracker.on_trade_executed(trade_event)
        
        # Check position exists
        assert "BTCUSDT" in tracker._positions
        assert tracker._positions["BTCUSDT"]["quantity"] == decimal.Decimal("1.0")
        
        # 2. Receive BALANCE_UPDATE (authoritative=False)
        # This calls _calc_margin_used_usd([], authoritative=False)
        balance_event = Message(
            op="EVT",
            verb="EVT:BALANCE_UPDATE_RECEIVED",
            pld={
                "assets": [
                    {"asset": "USDT", "balance": "10000", "crossWalletBalance": "10000", "crossUnPnl": "0"}
                ]
            },
            src="market_data",
            dst="position_tracking",
            rid="test-rid-2"
        )
        tracker.on_balance_update(balance_event)
        
        # ASSERT: Position MUST still exist
        assert "BTCUSDT" in tracker._positions
        assert tracker._positions["BTCUSDT"]["quantity"] == decimal.Decimal("1.0")
        
        # 3. Receive ACCOUNT_UPDATE with empty positions (authoritative=True)
        account_event = Message(
            op="EVT",
            verb="EVT:ACCOUNT_UPDATE_RECEIVED",
            pld={
                "totalWalletBalance": "10000",
                "totalUnrealizedProfit": "0",
                "positions": [] # Empty list -> should clear
            },
            src="market_data",
            dst="position_tracking",
            rid="test-rid-3"
        )
        tracker.on_account_update(account_event)
        
        # ASSERT: Position SHOULD be cleared now
        assert "BTCUSDT" not in tracker._positions
        assert len(tracker._positions) == 0
