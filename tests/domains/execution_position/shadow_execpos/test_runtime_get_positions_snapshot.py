"""
Unit Tests for ExecPosRuntimeV2.get_positions_snapshot()

Tests the new method added for debug API support.
"""
import pytest
from unittest.mock import MagicMock, patch

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState


@pytest.fixture
def mock_runtime():
    """Create runtime with mocked dependencies."""
    with patch.object(ExecPosRuntimeV2, '__init__', lambda x, **kwargs: None):
        runtime = ExecPosRuntimeV2.__new__(ExecPosRuntimeV2)
        runtime._positions_by_symbol = {}
        runtime.config = {}
        return runtime


def _make_long_position(symbol: str, qty: float = 1.0, entry_price: float = 50000.0) -> PositionState:
    """Helper: Create LONG position (positive qty)."""
    return PositionState(symbol=symbol, qty=abs(qty), avg_entry_price=entry_price)


def _make_short_position(symbol: str, qty: float = 1.0, entry_price: float = 50000.0) -> PositionState:
    """Helper: Create SHORT position (negative qty)."""
    return PositionState(symbol=symbol, qty=-abs(qty), avg_entry_price=entry_price)


class TestGetPositionsSnapshot:
    """Tests for get_positions_snapshot method."""

    def test_empty_positions(self, mock_runtime):
        """Return empty list when no positions."""
        result = mock_runtime.get_positions_snapshot()
        assert result == []

    def test_returns_all_positions(self, mock_runtime):
        """Return all non-flat positions."""
        mock_runtime._positions_by_symbol = {
            "BTCUSDT": _make_long_position("BTCUSDT", qty=1.0, entry_price=50000.0),
            "ETHUSDT": _make_short_position("ETHUSDT", qty=2.0, entry_price=3000.0),
        }

        result = mock_runtime.get_positions_snapshot()

        assert len(result) == 2
        symbols = {p["symbol"] for p in result}
        assert symbols == {"BTCUSDT", "ETHUSDT"}

    def test_filter_by_symbol(self, mock_runtime):
        """Filter positions by symbol."""
        mock_runtime._positions_by_symbol = {
            "BTCUSDT": _make_long_position("BTCUSDT"),
            "ETHUSDT": _make_short_position("ETHUSDT"),
        }

        result = mock_runtime.get_positions_snapshot(symbol="BTCUSDT")

        assert len(result) == 1
        assert result[0]["symbol"] == "BTCUSDT"

    def test_filter_by_symbol_case_insensitive(self, mock_runtime):
        """Symbol filter is case-insensitive."""
        mock_runtime._positions_by_symbol = {
            "BTCUSDT": _make_long_position("BTCUSDT"),
        }

        result = mock_runtime.get_positions_snapshot(symbol="btcusdt")

        assert len(result) == 1
        assert result[0]["symbol"] == "BTCUSDT"

    def test_filter_by_side_long(self, mock_runtime):
        """Filter positions by LONG side."""
        mock_runtime._positions_by_symbol = {
            "BTCUSDT": _make_long_position("BTCUSDT"),
            "ETHUSDT": _make_short_position("ETHUSDT"),
        }

        result = mock_runtime.get_positions_snapshot(side="LONG")

        assert len(result) == 1
        assert result[0]["symbol"] == "BTCUSDT"

    def test_filter_by_side_buy_maps_to_long(self, mock_runtime):
        """BUY side filter matches LONG positions."""
        mock_runtime._positions_by_symbol = {
            "BTCUSDT": _make_long_position("BTCUSDT"),
            "ETHUSDT": _make_short_position("ETHUSDT"),
        }

        result = mock_runtime.get_positions_snapshot(side="BUY")

        assert len(result) == 1
        assert result[0]["symbol"] == "BTCUSDT"

    def test_filter_by_side_short(self, mock_runtime):
        """Filter positions by SHORT side."""
        mock_runtime._positions_by_symbol = {
            "BTCUSDT": _make_long_position("BTCUSDT"),
            "ETHUSDT": _make_short_position("ETHUSDT"),
        }

        result = mock_runtime.get_positions_snapshot(side="SHORT")

        assert len(result) == 1
        assert result[0]["symbol"] == "ETHUSDT"

    def test_filter_by_side_sell_maps_to_short(self, mock_runtime):
        """SELL side filter matches SHORT positions."""
        mock_runtime._positions_by_symbol = {
            "BTCUSDT": _make_long_position("BTCUSDT"),
            "ETHUSDT": _make_short_position("ETHUSDT"),
        }

        result = mock_runtime.get_positions_snapshot(side="SELL")

        assert len(result) == 1
        assert result[0]["symbol"] == "ETHUSDT"

    def test_combined_filters(self, mock_runtime):
        """Filter by both symbol and side."""
        mock_runtime._positions_by_symbol = {
            "BTCUSDT": _make_long_position("BTCUSDT"),
            "ETHUSDT": _make_long_position("ETHUSDT"),
            "SOLUSDT": _make_short_position("SOLUSDT"),
        }

        result = mock_runtime.get_positions_snapshot(symbol="ETHUSDT", side="LONG")

        assert len(result) == 1
        assert result[0]["symbol"] == "ETHUSDT"

    def test_excludes_flat_positions(self, mock_runtime):
        """Flat positions (qty=0) are excluded."""
        mock_runtime._positions_by_symbol = {
            "BTCUSDT": _make_long_position("BTCUSDT"),
            "ETHUSDT": PositionState(symbol="ETHUSDT", qty=0.0),  # Flat
        }

        result = mock_runtime.get_positions_snapshot()

        assert len(result) == 1
        assert result[0]["symbol"] == "BTCUSDT"

    def test_position_dict_structure(self, mock_runtime):
        """Verify returned dict has correct structure."""
        mock_runtime._positions_by_symbol = {
            "BTCUSDT": PositionState(
                symbol="BTCUSDT",
                qty=1.5,
                avg_entry_price=50000.0,
                realized_pnl=100.0,
                unrealized_pnl=50.0,
            ),
        }

        result = mock_runtime.get_positions_snapshot()

        assert len(result) == 1
        pos = result[0]
        assert pos["symbol"] == "BTCUSDT"
        assert pos["qty"] == 1.5
        assert pos["side"] == "LONG"
        assert pos["entry_price"] == 50000.0
        assert pos["avg_entry_price"] == 50000.0
        assert pos["realized_pnl"] == 100.0
        assert pos["unrealized_pnl"] == 50.0

    def test_no_match_returns_empty(self, mock_runtime):
        """Return empty list when no positions match filters."""
        mock_runtime._positions_by_symbol = {
            "BTCUSDT": _make_long_position("BTCUSDT"),
        }

        result = mock_runtime.get_positions_snapshot(symbol="ETHUSDT")

        assert result == []
