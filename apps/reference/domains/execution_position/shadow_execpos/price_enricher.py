"""
Price Enricher for Shadow ExecPos
=================================

Enriches trade events with missing price data.
"""
from typing import Any, Dict, Optional, Union
from decimal import Decimal
import logging

from .types import EnrichedTrade

logger = logging.getLogger(__name__)

class PriceEnricher:
    """
    Enriches TRADE_EXECUTED events with valid prices.
    
    Responsibilities:
    - Extract price from trade payload if present.
    - Fallback to position entry price.
    - Fallback to current market quote.
    - Return structured enriched event or None if unable.
    """

    def enrich_trade(
        self,
        trade_payload: Dict[str, Any],
        position_entry_price: Optional[Union[str, float, Decimal]] = None,
        current_price_quote: Optional[Union[str, float, Decimal]] = None
    ) -> Optional[EnrichedTrade]:
        """
        Enrich a trade event with price data.
        
        Args:
            trade_payload: Raw trade event payload.
            position_entry_price: Entry price from ManageFlow position state.
            current_price_quote: Current market price from PriceService.
            
        Returns:
            EnrichedTrade if successful, None otherwise.
        """
        def _is_valid_price(value: Any) -> bool:
            try:
                return Decimal(str(value)) > 0
            except Exception:
                return False

        # Try payload price first
        payload_price = trade_payload.get("price")
        if _is_valid_price(payload_price):
            return {
                "original_payload": trade_payload,
                "price": str(payload_price),
                "price_source": "payload",
                "enriched": False
            }

        # Fallback to position entry price
        if _is_valid_price(position_entry_price):
            enriched_payload = trade_payload.copy()
            enriched_payload["price"] = str(position_entry_price)
            logger.info(
                f"PRICE_ENRICHED_FROM_POSITION: symbol={trade_payload.get('symbol')}, price={position_entry_price}"
            )
            return {
                "original_payload": trade_payload,
                "price": str(position_entry_price),
                "price_source": "position",
                "enriched": True
            }

        # Fallback to current quote
        if _is_valid_price(current_price_quote):
            enriched_payload = trade_payload.copy()
            enriched_payload["price"] = str(current_price_quote)
            logger.info(
                f"PRICE_ENRICHED_FROM_QUOTE: symbol={trade_payload.get('symbol')}, price={current_price_quote}"
            )
            return {
                "original_payload": trade_payload,
                "price": str(current_price_quote),
                "price_source": "quote",
                "enriched": True
            }

        # Unable to enrich
        logger.warning(
            f"PRICE_ENRICHMENT_FAILED: symbol={trade_payload.get('symbol')}, no valid price source"
        )
        return None
