"""
Tests for unrealized PnL calculation and mark price handling in position_tracking.

EXP-UNREALIZED-PNL: Tests for _calculate_unrealized_pnl() with mark prices.
EXP-LEVERAGE-002: Tests for leverage resolution helper methods.
"""

import decimal
from decimal import Decimal
from unittest import mock
import pytest
import time


class FSMCoreMock:
    """Minimal FSM core mock for testing."""

    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}
        self.emitted_events: list = []

    def listen(self, event_name: str, callback) -> None:
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def emit(self, event_name: str, payload: dict, why: str) -> None:
        self.emitted_events.append({
            "event_name": event_name,
            "payload": payload,
            "why": why,
        })


@pytest.fixture
def mock_config():
    """Basic mock configuration."""
    return {
        "position_limits": {"max_positions": 10},
        "trading": {
            "execution": {
                "exposure": {
                    "leverage_defaults": {
                        "__default__": 125,
                        "BTCUSDT": 100,
                        "ETHUSDT": 75,
                    }
                }
            }
        },
    }


@pytest.fixture
def position_tracking(mock_config):
    """Create PositionTracking instance for testing."""
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )
    
    fsm = FSMCoreMock()
    pt = PositionTracking(fsm=fsm, config=mock_config)
    return pt


# =============================================================================
# Tests for _calculate_unrealized_pnl()
# =============================================================================

class TestCalculateUnrealizedPnL:
    """Tests for unrealized PnL calculation."""

    def test_unrealized_pnl_with_positions_from_api(self, position_tracking):
        """Test unrealized PnL calculation using positionRisk API data."""
        # Simulated positionRisk API data
        positions = [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.1",  # Long 0.1 BTC
                "entryPrice": "50000",
                "markPrice": "55000",  # $5000 profit per BTC
                "leverage": "10",
            },
            {
                "symbol": "ETHUSDT",
                "positionAmt": "-1.0",  # Short 1 ETH
                "entryPrice": "2000",
                "markPrice": "1900",  # $100 profit (price went down for short)
                "leverage": "20",
            },
        ]

        # Calculate unrealized PnL
        unrealized_pnl = position_tracking._calculate_unrealized_pnl(positions)

        # Expected:
        # BTC: (55000 - 50000) * 0.1 = $500
        # ETH: (1900 - 2000) * (-1.0) = $100
        # Total: $600
        assert unrealized_pnl == Decimal("600.00")

    def test_unrealized_pnl_with_loss(self, position_tracking):
        """Test unrealized PnL with losing position."""
        positions = [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.5",  # Long 0.5 BTC
                "entryPrice": "60000",
                "markPrice": "50000",  # $10000 loss per BTC
                "leverage": "10",
            },
        ]

        unrealized_pnl = position_tracking._calculate_unrealized_pnl(positions)

        # Expected: (50000 - 60000) * 0.5 = -$5000
        assert unrealized_pnl == Decimal("-5000.00")

    def test_unrealized_pnl_short_position_loss(self, position_tracking):
        """Test unrealized PnL for short position with loss."""
        positions = [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "-0.1",  # Short 0.1 BTC
                "entryPrice": "50000",
                "markPrice": "55000",  # Price went up = loss for short
                "leverage": "10",
            },
        ]

        unrealized_pnl = position_tracking._calculate_unrealized_pnl(positions)

        # Expected: (55000 - 50000) * (-0.1) = -$500
        assert unrealized_pnl == Decimal("-500.00")

    def test_unrealized_pnl_empty_positions(self, position_tracking):
        """Test unrealized PnL with no positions."""
        unrealized_pnl = position_tracking._calculate_unrealized_pnl([])
        assert unrealized_pnl == Decimal("0.00")

    def test_unrealized_pnl_without_api_uses_cache(self, position_tracking):
        """Test unrealized PnL using cached mark prices when no API data."""
        # Set up internal position
        position_tracking._positions["BTCUSDT"] = {
            "quantity": Decimal("0.1"),
            "avg_price": Decimal("50000"),
            "venues": ["binance"],
        }

        # Update mark price cache
        position_tracking.update_mark_price(
            "BTCUSDT", 
            Decimal("55000"),
            ts_ms=int(time.time() * 1000)  # Fresh timestamp
        )

        # Calculate without API data
        unrealized_pnl = position_tracking._calculate_unrealized_pnl(None)

        # Expected: (55000 - 50000) * 0.1 = $500
        assert unrealized_pnl == Decimal("500.00")

    def test_unrealized_pnl_stale_cache_returns_zero(self, position_tracking):
        """Test that stale mark price cache results in 0 PnL for that position."""
        # Set up internal position
        position_tracking._positions["BTCUSDT"] = {
            "quantity": Decimal("0.1"),
            "avg_price": Decimal("50000"),
            "venues": ["binance"],
        }

        # Update mark price cache with OLD timestamp (10 seconds ago)
        old_ts = int(time.time() * 1000) - 10000  # 10 seconds old
        position_tracking.update_mark_price("BTCUSDT", Decimal("55000"), ts_ms=old_ts)

        # Set staleness threshold to 5 seconds
        position_tracking._mark_price_stale_ms = 5000

        # Calculate without API data - should return 0 due to stale cache
        unrealized_pnl = position_tracking._calculate_unrealized_pnl(None)

        assert unrealized_pnl == Decimal("0.00")

    def test_unrealized_pnl_mixed_fresh_and_stale(self, position_tracking):
        """Test unrealized PnL with mix of fresh and stale cached prices."""
        now_ms = int(time.time() * 1000)
        
        # Set up two positions
        position_tracking._positions["BTCUSDT"] = {
            "quantity": Decimal("0.1"),
            "avg_price": Decimal("50000"),
            "venues": ["binance"],
        }
        position_tracking._positions["ETHUSDT"] = {
            "quantity": Decimal("1.0"),
            "avg_price": Decimal("2000"),
            "venues": ["binance"],
        }

        # BTC has fresh price
        position_tracking.update_mark_price("BTCUSDT", Decimal("55000"), ts_ms=now_ms)
        
        # ETH has stale price (10 seconds old)
        position_tracking.update_mark_price("ETHUSDT", Decimal("2500"), ts_ms=now_ms - 10000)
        position_tracking._mark_price_stale_ms = 5000

        # Calculate
        unrealized_pnl = position_tracking._calculate_unrealized_pnl(None)

        # Expected: Only BTC counted (fresh), ETH skipped (stale)
        # BTC: (55000 - 50000) * 0.1 = $500
        assert unrealized_pnl == Decimal("500.00")


# =============================================================================
# Tests for update_mark_price()
# =============================================================================

class TestUpdateMarkPrice:
    """Tests for mark price cache update."""

    def test_update_mark_price_basic(self, position_tracking):
        """Test basic mark price update."""
        position_tracking.update_mark_price("BTCUSDT", Decimal("55000"), ts_ms=1234567890000)

        assert "BTCUSDT" in position_tracking._mark_prices
        assert position_tracking._mark_prices["BTCUSDT"]["mark_price"] == Decimal("55000")
        assert position_tracking._mark_prices["BTCUSDT"]["ts_ms"] == 1234567890000

    def test_update_mark_price_default_timestamp(self, position_tracking):
        """Test mark price update with default timestamp."""
        before = int(time.time() * 1000)
        position_tracking.update_mark_price("BTCUSDT", Decimal("55000"))
        after = int(time.time() * 1000)

        ts = position_tracking._mark_prices["BTCUSDT"]["ts_ms"]
        assert before <= ts <= after

    def test_update_mark_price_overwrites_old(self, position_tracking):
        """Test that new mark price overwrites old one."""
        position_tracking.update_mark_price("BTCUSDT", Decimal("50000"), ts_ms=1000)
        position_tracking.update_mark_price("BTCUSDT", Decimal("55000"), ts_ms=2000)

        assert position_tracking._mark_prices["BTCUSDT"]["mark_price"] == Decimal("55000")
        assert position_tracking._mark_prices["BTCUSDT"]["ts_ms"] == 2000


# =============================================================================
# Tests for leverage resolution helpers
# =============================================================================

class TestLeverageResolution:
    """Tests for EXP-LEVERAGE-002 helper methods."""

    def test_get_leverage_config_from_dict(self, position_tracking):
        """Test _get_leverage_config with dict config."""
        leverage_config = position_tracking._get_leverage_config()
        
        assert isinstance(leverage_config, dict)
        assert leverage_config.get("__default__") == 125
        assert leverage_config.get("BTCUSDT") == 100
        assert leverage_config.get("ETHUSDT") == 75

    def test_resolve_default_leverage_with_dunder_default(self, position_tracking):
        """Test _resolve_default_leverage prefers __default__ over default."""
        leverage_config = {
            "__default__": 125,
            "default": 20,  # Should be ignored
        }
        
        result = position_tracking._resolve_default_leverage(leverage_config)
        assert result == "125"

    def test_resolve_default_leverage_fallback_to_default(self, position_tracking):
        """Test _resolve_default_leverage falls back to 'default' key."""
        leverage_config = {
            "default": 50,  # No __default__, use this
        }
        
        result = position_tracking._resolve_default_leverage(leverage_config)
        assert result == "50"

    def test_resolve_default_leverage_ultimate_fallback(self, position_tracking):
        """Test _resolve_default_leverage returns '20' when no keys present."""
        leverage_config = {}
        
        result = position_tracking._resolve_default_leverage(leverage_config)
        assert result == "20"

    def test_resolve_symbol_leverage_specific(self, position_tracking):
        """Test _resolve_symbol_leverage with symbol-specific value."""
        leverage_config = {
            "__default__": 125,
            "BTCUSDT": 100,
        }
        default_leverage = Decimal("125")
        
        result = position_tracking._resolve_symbol_leverage(
            leverage_config, "BTCUSDT", default_leverage
        )
        assert result == Decimal("100")

    def test_resolve_symbol_leverage_uses_default(self, position_tracking):
        """Test _resolve_symbol_leverage falls back to default for unknown symbol."""
        leverage_config = {
            "__default__": 125,
            "BTCUSDT": 100,
        }
        default_leverage = Decimal("125")
        
        result = position_tracking._resolve_symbol_leverage(
            leverage_config, "SOLUSDT", default_leverage  # Not in config
        )
        assert result == Decimal("125")

    def test_resolve_symbol_leverage_minimum_one(self, position_tracking):
        """Test _resolve_symbol_leverage enforces minimum of 1."""
        leverage_config = {
            "BTCUSDT": 0,  # Invalid, should be clamped to 1
        }
        default_leverage = Decimal("20")
        
        result = position_tracking._resolve_symbol_leverage(
            leverage_config, "BTCUSDT", default_leverage
        )
        assert result == Decimal("1")


# =============================================================================
# Tests for margin calculation with new leverage resolution
# =============================================================================

class TestMarginWithNewLeverage:
    """Tests for margin calculations using new leverage helpers."""

    def test_calc_margin_uses_correct_leverage(self, position_tracking):
        """Test _calc_margin_used_usd uses __default__ key correctly."""
        # Set up internal position (fallback mode - no API data)
        position_tracking._positions["SOLUSDT"] = {
            "quantity": Decimal("10"),  # 10 SOL
            "avg_price": Decimal("100"),  # $100 per SOL
            "venues": ["binance"],
        }

        # Calculate margin without API data (uses config)
        margin = position_tracking._calc_margin_used_usd([])

        # Expected: notional = 10 * 100 = $1000
        # Leverage from __default__ = 125
        # Margin = 1000 / 125 = $8.00
        assert margin == Decimal("8.00")

    def test_calc_margin_uses_symbol_specific_leverage(self, position_tracking):
        """Test _calc_margin_used_usd uses symbol-specific leverage."""
        # Set up BTCUSDT position (has specific leverage = 100)
        position_tracking._positions["BTCUSDT"] = {
            "quantity": Decimal("0.1"),  # 0.1 BTC
            "avg_price": Decimal("50000"),  # $50000 per BTC
            "venues": ["binance"],
        }

        # Calculate margin without API data
        margin = position_tracking._calc_margin_used_usd([])

        # Expected: notional = 0.1 * 50000 = $5000
        # Leverage for BTCUSDT = 100
        # Margin = 5000 / 100 = $50.00
        assert margin == Decimal("50.00")

    def test_margin_by_side_uses_correct_leverage(self, position_tracking):
        """Test _calculate_margin_by_side uses __default__ key correctly."""
        # Set up long and short positions
        position_tracking._positions["BTCUSDT"] = {
            "quantity": Decimal("0.1"),  # Long
            "avg_price": Decimal("50000"),
            "venues": ["binance"],
        }
        position_tracking._positions["ETHUSDT"] = {
            "quantity": Decimal("-1.0"),  # Short
            "avg_price": Decimal("2000"),
            "venues": ["binance"],
        }

        # Calculate margin by side
        result = position_tracking._calculate_margin_by_side([])

        # BTC: notional = 5000, leverage = 100, margin = 50
        # ETH: notional = 2000, leverage = 75, margin = 26.67
        assert result["long_margin"] == Decimal("50.00")
        assert result["short_margin"] == Decimal("26.67")


# =============================================================================
# Integration test: Full flow with unrealized PnL
# =============================================================================

class TestIntegrationUnrealizedPnL:
    """Integration tests for unrealized PnL in portfolio state."""

    def test_account_update_includes_unrealized_pnl(self, mock_config):
        """Test that EVT:ACCOUNT_UPDATE_RECEIVED emits correct unrealized_pnl."""
        from apps.reference.domains.position_tracking.position_tracking import (
            PositionTracking,
        )
        from vfoundation.core.protocol import Message

        fsm = FSMCoreMock()
        pt = PositionTracking(fsm=fsm, config=mock_config)
        pt.start()

        # Simulate account update with positions
        account_payload = {
            "totalWalletBalance": "10000",
            "totalUnrealizedProfit": "500",  # Binance provides this
            "totalCrossWalletBalance": "9500",
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.1",
                    "entryPrice": "50000",
                    "markPrice": "55000",
                    "leverage": "10",
                },
            ],
        }

        # Trigger account update
        event = Message(
            op="EVT",
            verb="ACCOUNT_UPDATE_RECEIVED",
            src="test",
            dst="any",
            pld=account_payload,
            why="test",
        )
        
        # Mock WAL to avoid file operations
        with mock.patch('apps.reference.domains.position_tracking.position_tracking.wal') as mock_wal:
            mock_wal.append.return_value = "test_hash"
            pt.on_account_update(event)

        # Find the portfolio state event
        portfolio_events = [
            e for e in fsm.emitted_events 
            if e["event_name"] == "EVT:PORTFOLIO_STATE_UPDATED"
        ]
        assert len(portfolio_events) >= 1

        last_event = portfolio_events[-1]
        payload = last_event["payload"]

        # Verify unrealized_pnl is from Binance API data
        assert payload["unrealized_pnl"] == "500"


# =============================================================================
# Tests for on_market_tick() and market tick subscription
# =============================================================================

class TestMarketTickSubscription:
    """Tests for EVT:MARKET_TICK_RECEIVED subscription (P1)."""

    def test_market_tick_subscription_disabled_by_default(self):
        """Test that market tick subscription is disabled by default."""
        from apps.reference.domains.position_tracking.position_tracking import (
            PositionTracking,
        )
        
        fsm = FSMCoreMock()
        config = {"position_limits": {"max_positions": 10}}
        pt = PositionTracking(fsm=fsm, config=config)
        
        assert pt._market_tick_subscription_enabled == False
        # EVT:MARKET_TICK_RECEIVED should NOT be in listeners
        assert "EVT:MARKET_TICK_RECEIVED" not in fsm.listeners

    def test_market_tick_subscription_enabled_via_config(self):
        """Test that market tick subscription can be enabled via config."""
        from apps.reference.domains.position_tracking.position_tracking import (
            PositionTracking,
        )
        
        fsm = FSMCoreMock()
        config = {
            "position_limits": {"max_positions": 10},
            "domains": {
                "position_tracking": {
                    "enable_market_tick_subscription": True
                }
            }
        }
        pt = PositionTracking(fsm=fsm, config=config)
        
        assert pt._market_tick_subscription_enabled == True
        assert "EVT:MARKET_TICK_RECEIVED" in fsm.listeners

    def test_on_market_tick_updates_cache(self):
        """Test that on_market_tick updates mark price cache."""
        from apps.reference.domains.position_tracking.position_tracking import (
            PositionTracking,
        )
        from vfoundation.core.protocol import Message
        
        fsm = FSMCoreMock()
        config = {"position_limits": {"max_positions": 10}}
        pt = PositionTracking(fsm=fsm, config=config)
        
        tick_event = Message(
            op="EVT",
            verb="MARKET_TICK_RECEIVED",
            src="test",
            dst="any",
            pld={
                "symbol": "BTCUSDT",
                "mid": "55000",
                "ts": 1700000000000,
            },
            why="test",
        )
        
        pt.on_market_tick(tick_event)
        
        assert "BTCUSDT" in pt._mark_prices
        assert pt._mark_prices["BTCUSDT"]["mark_price"] == Decimal("55000")
        assert pt._mark_prices["BTCUSDT"]["ts_ms"] == 1700000000000

    def test_on_market_tick_uses_price_fallback(self):
        """Test that on_market_tick uses 'price' field if 'mid' is missing."""
        from apps.reference.domains.position_tracking.position_tracking import (
            PositionTracking,
        )
        from vfoundation.core.protocol import Message
        
        fsm = FSMCoreMock()
        config = {"position_limits": {"max_positions": 10}}
        pt = PositionTracking(fsm=fsm, config=config)
        
        tick_event = Message(
            op="EVT",
            verb="MARKET_TICK_RECEIVED",
            src="test",
            dst="any",
            pld={
                "symbol": "ETHUSDT",
                "price": "2500",  # No 'mid' field
                "ts": 1700000000000,
            },
            why="test",
        )
        
        pt.on_market_tick(tick_event)
        
        assert "ETHUSDT" in pt._mark_prices
        assert pt._mark_prices["ETHUSDT"]["mark_price"] == Decimal("2500")

    def test_on_market_tick_ignores_invalid_payload(self):
        """Test that on_market_tick handles invalid payloads gracefully."""
        from apps.reference.domains.position_tracking.position_tracking import (
            PositionTracking,
        )
        from vfoundation.core.protocol import Message
        
        fsm = FSMCoreMock()
        config = {"position_limits": {"max_positions": 10}}
        pt = PositionTracking(fsm=fsm, config=config)
        
        # Missing symbol
        tick_event = Message(
            op="EVT",
            verb="MARKET_TICK_RECEIVED",
            src="test",
            dst="any",
            pld={
                "mid": "55000",
            },
            why="test",
        )
        
        pt.on_market_tick(tick_event)
        
        # Should not add anything
        assert len(pt._mark_prices) == 0

    def test_on_market_tick_ignores_zero_price(self):
        """Test that on_market_tick ignores zero prices."""
        from apps.reference.domains.position_tracking.position_tracking import (
            PositionTracking,
        )
        from vfoundation.core.protocol import Message
        
        fsm = FSMCoreMock()
        config = {"position_limits": {"max_positions": 10}}
        pt = PositionTracking(fsm=fsm, config=config)
        
        tick_event = Message(
            op="EVT",
            verb="MARKET_TICK_RECEIVED",
            src="test",
            dst="any",
            pld={
                "symbol": "BTCUSDT",
                "mid": "0",
            },
            why="test",
        )
        
        pt.on_market_tick(tick_event)
        
        # Should not add zero price
        assert "BTCUSDT" not in pt._mark_prices


# =============================================================================
# Tests for zero quantity positions
# =============================================================================

class TestZeroQuantityPositions:
    """Tests for handling zero/near-zero quantity positions."""

    def test_unrealized_pnl_skips_zero_positions(self, position_tracking):
        """Test that zero quantity positions are skipped in PnL calculation."""
        positions = [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.0",  # Zero position
                "entryPrice": "50000",
                "markPrice": "55000",
                "leverage": "10",
            },
            {
                "symbol": "ETHUSDT",
                "positionAmt": "1.0",  # Non-zero
                "entryPrice": "2000",
                "markPrice": "2500",
                "leverage": "10",
            },
        ]

        unrealized_pnl = position_tracking._calculate_unrealized_pnl(positions)

        # Only ETH should be counted: (2500 - 2000) * 1.0 = $500
        assert unrealized_pnl == Decimal("500.00")

    def test_unrealized_pnl_skips_tiny_positions(self, position_tracking):
        """Test that positions below threshold are skipped."""
        # Set threshold
        position_tracking.quantity_min_threshold = Decimal("0.001")

        positions = [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.0001",  # Below threshold
                "entryPrice": "50000",
                "markPrice": "55000",
                "leverage": "10",
            },
        ]

        unrealized_pnl = position_tracking._calculate_unrealized_pnl(positions)
        assert unrealized_pnl == Decimal("0.00")
