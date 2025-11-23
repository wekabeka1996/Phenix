"""
Tests for Shadow ExecPos Behavior Service Contracts
===================================================
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from apps.reference.domains.execution_position.shadow_execpos.watchdog import AggOcoWatchdogService
from apps.reference.domains.execution_position.shadow_execpos.gatekeeper import ExecPosGatekeeper
from apps.reference.domains.execution_position.shadow_execpos.price_enricher import PriceEnricher
from apps.reference.domains.execution_position.shadow_execpos.types import WatchdogAction, WatchdogRecommendation

# --- Watchdog Tests ---

def test_watchdog_contract():
    """Verify AggOcoWatchdogService contract."""
    watchdog = AggOcoWatchdogService()
    
    # Dummy data
    open_orders = [
        {"symbol": "BTCUSDT", "orderId": "1", "side": "SELL"}
    ]
    positions = [
        {"symbol": "BTCUSDT", "positionAmt": "0.1", "entryPrice": "50000"}
    ]
    
    recommendations = watchdog.analyze(open_orders, positions, None)
    
    # Contract: should return a list
    assert isinstance(recommendations, list)
    
    # Each item should be a WatchdogRecommendation
    for rec in recommendations:
        assert isinstance(rec, WatchdogRecommendation)

# --- PriceEnricher Tests ---

def test_price_enricher_contract():
    """Verify PriceEnricher contract."""
    enricher = PriceEnricher()
    
    # Payload with price
    trade_with_price = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "price": "50000"
    }
    
    result = enricher.enrich_trade(trade_with_price)
    
    # Contract: should return EnrichedTrade
    assert result is not None
    assert "original_payload" in result
    assert "price" in result
    assert "price_source" in result
    assert "enriched" in result
    assert result["price_source"] == "payload"
    assert result["enriched"] is False

def test_price_enricher_fallback_to_position():
    """Verify fallback to position entry price."""
    enricher = PriceEnricher()
    
    # Payload without price
    trade_no_price = {
        "symbol": "BTCUSDT",
        "side": "BUY"
    }
    
    result = enricher.enrich_trade(
        trade_no_price,
        position_entry_price="49000"
    )
    
    assert result is not None
    assert result["price"] == "49000"
    assert result["price_source"] == "position"
    assert result["enriched"] is True

def test_price_enricher_fallback_to_quote():
    """Verify fallback to current quote."""
    enricher = PriceEnricher()
    
    trade_no_price = {
        "symbol": "BTCUSDT",
        "side": "BUY"
    }
    
    result = enricher.enrich_trade(
        trade_no_price,
        position_entry_price=None,
        current_price_quote="51000"
    )
    
    assert result is not None
    assert result["price"] == "51000"
    assert result["price_source"] == "quote"
    assert result["enriched"] is True

def test_price_enricher_fails_gracefully():
    """Verify enricher returns None when unable to enrich."""
    enricher = PriceEnricher()
    
    trade_no_price = {
        "symbol": "BTCUSDT",
        "side": "BUY"
    }
    
    result = enricher.enrich_trade(trade_no_price)
    
    assert result is None
