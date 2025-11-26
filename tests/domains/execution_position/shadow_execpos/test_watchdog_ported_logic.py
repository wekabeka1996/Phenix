"""
Tests for Aggre OCO Watchdog Ported Logic
==========================================

Validation of detect-only behavior backed by BracketService.
"""
import pytest

from apps.reference.domains.execution_position.shadow_execpos.watchdog import AggOcoWatchdogService
from apps.reference.domains.execution_position.shadow_execpos.types import WatchdogAction


@pytest.fixture
def watchdog():
    return AggOcoWatchdogService(cfg={"aggregated_oco": {"enabled": True}})


# --- NO VIOLATIONS ---

def test_analyze_no_violations(watchdog):
    """Test valid state - position with SL AND TP -> no ALERT recs (WARN for recalc is acceptable)."""
    positions = [{"symbol": "BTCUSDT", "positionAmt": "0.1",
                  "side": "BUY", "entryPrice": "100"}]
    orders = [
        {
            "symbol": "BTCUSDT",
            "orderId": "sl_123",
            "type": "STOP_MARKET",
            "side": "SELL",
            "reduceOnly": True,
            "quantity": "0.1",
            "stopPrice": "98",
        },
        {
            "symbol": "BTCUSDT",
            "orderId": "tp_123",
            "type": "TAKE_PROFIT_MARKET",
            "side": "SELL",
            "reduceOnly": True,
            "quantity": "0.1",
            "stopPrice": "105",
        }
    ]

    recommendations = watchdog.analyze(orders, positions)

    # No ALERT recommendations (missing_sl/missing_tp) when both brackets present
    # WARN for recalc (stale_levels) is acceptable
    alert_recs = [r for r in recommendations if r.kind == "ALERT"]
    assert alert_recs == [
    ], f"Expected no ALERT (missing brackets), got {alert_recs}"


# --- NO SL FOR OPEN POSITION ---

def test_no_sl_for_open_position(watchdog):
    """Test position without SL protection produces WARN/ALERT severity."""
    positions = [{"symbol": "ETHUSDT",
                  "positionAmt": "1.5", "entryPrice": "1800"}]
    orders = []  # No SL order

    recommendations = watchdog.analyze(orders, positions)

    assert recommendations
    assert any(rec.symbol == "ETHUSDT" and rec.kind in ("WARN", "ALERT")
               for rec in recommendations)
    # May have mixed ALERT (missing_sl) and WARN (missing_tp) actions
    assert any(rec.kind in ("WARN", "ALERT") for rec in recommendations)


# --- ORPHAN SL ---

def test_orphan_sl_for_zero_position(watchdog):
    """Test SL order without corresponding position -> WARN cancel rec."""
    positions = []  # No position
    orders = [
        {
            "symbol": "BTCUSDT",
            "orderId": "orphan_sl_1",
            "type": "STOP_MARKET",
            "side": "SELL",
            "reduceOnly": True,
            "quantity": "0.1",
            "stopPrice": "95",
        }
    ]

    recommendations = watchdog.analyze(orders, positions)

    assert recommendations
    assert any(rec.kind == "WARN" for rec in recommendations)
    assert any("orphan" in rec.reason for rec in recommendations)
    assert any("orphan_sl_1" in rec.orders_to_cancel for rec in recommendations)


# --- TOO MANY SL ---

def test_too_many_sl_orders(watchdog):
    """Test position with multiple SL orders -> WARN and cancel extras."""
    positions = [{"symbol": "SOLUSDT",
                  "positionAmt": "10.0", "entryPrice": "50"}]
    orders = [
        {"symbol": "SOLUSDT", "orderId": "sl_1", "type": "STOP_MARKET",
            "side": "SELL", "reduceOnly": True, "stopPrice": "45", "quantity": "10"},
        {"symbol": "SOLUSDT", "orderId": "sl_2", "type": "STOP_MARKET",
            "side": "SELL", "reduceOnly": True, "stopPrice": "44", "quantity": "10"},
        {"symbol": "SOLUSDT", "orderId": "sl_3", "type": "STOP_MARKET",
            "side": "SELL", "reduceOnly": True, "stopPrice": "43", "quantity": "10"},
    ]

    recommendations = watchdog.analyze(orders, positions)

    assert recommendations
    assert any(rec.kind == "WARN" for rec in recommendations)
    assert any(
        "sl_2" in rec.orders_to_cancel or "sl_3" in rec.orders_to_cancel for rec in recommendations)


# --- COMBINED SCENARIOS ---

def test_multiple_symbols(watchdog):
    """Test analysis across multiple symbols: ETH missing SL is flagged."""
    positions = [
        {"symbol": "BTCUSDT", "positionAmt": "0.1",
            "entryPrice": "100"},  # Has SL - OK
        {"symbol": "ETHUSDT", "positionAmt": "1.0",
            "entryPrice": "1800"},   # No SL - violation
    ]
    orders = [
        {"symbol": "BTCUSDT", "orderId": "sl_btc", "type": "STOP_MARKET",
            "side": "SELL", "reduceOnly": True, "stopPrice": "98", "quantity": "0.1"}
        # No ETH SL
    ]

    recommendations = watchdog.analyze(orders, positions)

    assert recommendations
    assert any(rec.symbol == "ETHUSDT" and rec.kind ==
               "ALERT" for rec in recommendations)


# --- EMPTY INPUTS ---

def test_empty_snapshot(watchdog):
    """Test empty snapshot (no orders/positions)."""
    recommendations = watchdog.analyze([], [])

    assert recommendations == []


# --- NORMALIZATION ---

def test_position_normalization_various_formats(watchdog):
    """Test position normalization handles various formats and surfaces missing SL/TP."""
    positions = [
        {"symbol": "btcusdt", "positionAmt": "0.5", "entryPrice": "100"},
        {"symbol": "ETHUSDT", "position_amt": "1.0", "entryPrice": "200"},
        {"symbol": "SOLUSDT", "qty": "2.0", "entry_price": "50"},
    ]
    orders = []

    recommendations = watchdog.analyze(orders, positions)

    # Each position may get both missing_sl (ALERT) and missing_tp (WARN)
    assert len(recommendations) >= 3  # At least one rec per position
    assert all(rec.kind in ("WARN", "ALERT") for rec in recommendations)
    # Check all symbols are represented
    symbols = {rec.symbol for rec in recommendations}
    assert "BTCUSDT" in symbols
    assert "ETHUSDT" in symbols
    assert "SOLUSDT" in symbols


def test_order_normalization_stop_detection(watchdog):
    """Test SL order detection logic with mixed order payloads."""
    positions = [{"symbol": "BTCUSDT",
                  "positionAmt": "0.1", "entryPrice": "100"}]

    # Various SL order formats
    orders = [
        {"symbol": "BTCUSDT", "orderId": "sl_1", "type": "STOP_MARKET",
            "side": "SELL", "reduceOnly": True, "stopPrice": "95", "quantity": "0.1"},
        {"symbol": "BTCUSDT", "orderId": "sl_2", "type": "LIMIT",
            "stopPrice": "90", "reduceOnly": True, "side": "SELL", "quantity": "0.1"},
    ]

    recommendations = watchdog.analyze(orders, positions)

    assert recommendations
    assert any(rec.kind == "WARN" for rec in recommendations)
    assert any(rec.orders_to_cancel == ["sl_2"] for rec in recommendations)


# --- ERROR HANDLING ---

def test_malformed_input_graceful_handling(watchdog):
    """Test that malformed inputs don't crash analysis."""
    positions = [
        {"symbol": "BTCUSDT", "positionAmt": "invalid"},  # Invalid qty
        {},  # Missing symbol
        None,  # None value (if passed)
    ]
    orders = [
        {"symbol": "BTCUSDT"},  # Missing orderId
        {"orderId": "123"},  # Missing symbol
    ]

    recommendations = watchdog.analyze(orders, positions)

    assert isinstance(recommendations, list)
