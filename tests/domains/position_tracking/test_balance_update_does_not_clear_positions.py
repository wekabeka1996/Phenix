"""
Tests for POSITION-TRACKING-BALANCE-UPDATE-BUGFIX-007.

Critical bug fix: Balance updates MUST NOT clear positions cache.
Only authoritative position snapshots (positionRisk API) can clear positions.
"""

import decimal
import time
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest


class _DummyFsm:
    """Mock FSM for testing."""
    def __init__(self):
        self.emitted: list[tuple[str, dict, str | None]] = []
        self._listeners: dict[str, list] = {}

    def emit(self, event_name: str, payload=None, why=None, *_args, **_kwargs) -> None:
        self.emitted.append((event_name, payload or {}, why))

    def listen(self, event_name: str, callback) -> None:
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append(callback)


@pytest.fixture
def mock_config():
    """Create mock config for position tracking."""
    from apps.reference.config_loader import ConfigLoader
    return ConfigLoader().load_config()


@pytest.fixture
def position_tracking(mock_config):
    """Create PositionTracking instance with mock FSM."""
    from apps.reference.domains.position_tracking.position_tracking import PositionTracking
    
    fsm = _DummyFsm()
    pt = PositionTracking(fsm=fsm, config=mock_config)
    return pt


class TestBalanceUpdateDoesNotClearPositions:
    """
    BUGFIX-007: Balance updates must not clear positions cache.
    
    Root cause of incident:
    - on_balance_update called _calc_margin_used_usd([])
    - _calc_margin_used_usd interpreted [] as "authoritative empty snapshot"
    - self._positions.clear() was called
    - DecisionMaking thought position was 0 → allowed re-entry
    - Result: -8 SOL position (double entry disaster)
    """
    
    def test_balance_update_does_not_clear_positions_cache(self, position_tracking):
        """
        REPRO INCIDENT: Balance update must not clear positions.
        
        Scenario:
        1. Internal cache has SOL -4 position
        2. Balance update arrives (no position data)
        3. Verify: positions cache NOT cleared
        """
        # Setup: Add SOL -4 position to internal cache
        position_tracking._positions["SOLUSDT"] = {
            "quantity": decimal.Decimal("-4"),
            "avg_price": decimal.Decimal("100.0"),
            "venues": ["binance"],
        }
        
        # Verify setup
        assert "SOLUSDT" in position_tracking._positions
        assert position_tracking._positions["SOLUSDT"]["quantity"] == decimal.Decimal("-4")
        
        # Simulate balance update (has no position data, only equity)
        # Previously this would call _calc_margin_used_usd([]) → positions.clear()
        result = position_tracking._calc_margin_used_usd(None, authoritative=False)
        
        # CRITICAL: Position must still be in cache
        assert "SOLUSDT" in position_tracking._positions, \
            "BUGFIX-007 FAILED: Balance update cleared positions cache!"
        assert position_tracking._positions["SOLUSDT"]["quantity"] == decimal.Decimal("-4"), \
            "BUGFIX-007 FAILED: Position was modified!"
    
    def test_empty_list_with_authoritative_false_does_not_clear(self, position_tracking):
        """
        Even if [] is passed, authoritative=False must prevent clearing.
        """
        # Setup: Add BTC position
        position_tracking._positions["BTCUSDT"] = {
            "quantity": decimal.Decimal("0.5"),
            "avg_price": decimal.Decimal("50000.0"),
            "venues": ["binance"],
        }
        
        # Call with empty list but authoritative=False
        result = position_tracking._calc_margin_used_usd([], authoritative=False)
        
        # Position must remain
        assert "BTCUSDT" in position_tracking._positions
    
    def test_authoritative_snapshot_can_clear_positions(self, position_tracking):
        """
        Authoritative snapshot with empty positions CAN clear cache.
        This is the correct behavior when Binance says "you have no positions".
        """
        # Setup: Add position
        position_tracking._positions["ETHUSDT"] = {
            "quantity": decimal.Decimal("1.0"),
            "avg_price": decimal.Decimal("3000.0"),
            "venues": ["binance"],
        }
        
        # Authoritative empty snapshot (from positionRisk API)
        result = position_tracking._calc_margin_used_usd([], authoritative=True)
        
        # Position should be cleared (Binance says no positions)
        assert "ETHUSDT" not in position_tracking._positions, \
            "Authoritative snapshot should clear positions"
    
    def test_authoritative_snapshot_with_positions_updates_cache(self, position_tracking):
        """
        Authoritative snapshot with positions should NOT clear cache
        (positions list is not empty).
        """
        # Setup: Internal cache is empty
        position_tracking._positions.clear()
        
        # Authoritative snapshot with SOL position
        positions_from_api = [
            {
                "symbol": "SOLUSDT",
                "positionAmt": "5.0",
                "entryPrice": "100.0",
                "leverage": "5",
                "notional": "500.0",
            }
        ]
        
        result = position_tracking._calc_margin_used_usd(positions_from_api, authoritative=True)
        
        # Result should be margin = 500/5 = 100 USD
        assert result == decimal.Decimal("100.00")
    
    def test_none_uses_fallback_mode(self, position_tracking):
        """
        None triggers fallback mode (use internal cache).
        """
        # Setup: Add position to internal cache
        position_tracking._positions["XRPUSDT"] = {
            "quantity": decimal.Decimal("1000"),
            "avg_price": decimal.Decimal("0.5"),
            "venues": ["binance"],
        }
        
        # Call with None (fallback mode)
        result = position_tracking._calc_margin_used_usd(None, authoritative=False)
        
        # Position should remain and margin should be calculated from cache
        assert "XRPUSDT" in position_tracking._positions
        # Margin depends on leverage config, but should be > 0
        assert result >= decimal.Decimal("0")


class TestCalcMarginUsedUsdAuthoritativeParameter:
    """Tests for the authoritative parameter behavior."""
    
    def test_authoritative_defaults_to_false(self, position_tracking):
        """
        Default authoritative value must be False for safety.
        """
        # Add position
        position_tracking._positions["DOGEUSDT"] = {
            "quantity": decimal.Decimal("-10000"),
            "avg_price": decimal.Decimal("0.1"),
            "venues": ["binance"],
        }
        
        # Call WITHOUT explicit authoritative parameter
        result = position_tracking._calc_margin_used_usd([])
        
        # Position should NOT be cleared (authoritative defaults to False)
        assert "DOGEUSDT" in position_tracking._positions
    
    def test_warning_logged_on_non_authoritative_clear_attempt(self, position_tracking, caplog):
        """
        Non-authoritative clear attempt should log warning.
        """
        import logging
        
        # Add position
        position_tracking._positions["BNBUSDT"] = {
            "quantity": decimal.Decimal("2.0"),
            "avg_price": decimal.Decimal("300.0"),
            "venues": ["binance"],
        }
        
        # Try to clear with authoritative=False
        with caplog.at_level(logging.WARNING):
            position_tracking._calc_margin_used_usd([], authoritative=False)
        
        # Should have warning about non-authoritative clear attempt
        assert any("NON_AUTHORITATIVE" in record.message for record in caplog.records), \
            "Expected warning about non-authoritative clear attempt"


class TestDecisionMakingPositionIntegrity:
    """
    Integration: DecisionMaking should not see position=0 after balance update
    if internal cache has position.
    """
    
    def test_portfolio_snapshot_preserves_positions_after_balance_update(self, position_tracking):
        """
        After balance update, _get_positions_snapshot should still return positions.
        """
        # Setup: Add position
        position_tracking._positions["SOLUSDT"] = {
            "quantity": decimal.Decimal("-4"),
            "avg_price": decimal.Decimal("100.0"),
            "venues": ["binance"],
        }
        
        # Simulate what on_balance_update does internally
        position_tracking._calc_margin_used_usd(None, authoritative=False)
        
        # Get positions snapshot
        snapshot = position_tracking._get_positions_snapshot()
        
        # Must still have SOLUSDT
        assert any(p["symbol"] == "SOLUSDT" for p in snapshot), \
            "SOLUSDT should be in positions snapshot after balance update"
