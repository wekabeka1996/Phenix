"""
Market data domain package.

Keep imports lightweight so test collection does not fail when optional deps
(`aiohttp`, websocket libs) are not installed.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .market_data_connector import MarketDataConnector as MarketDataConnector
    from .market_ws_client import MarketWSClient as MarketWSClient
    from .websocket_aggregator import WebSocketAggregator as WebSocketAggregator

def __getattr__(name: str):  # type: ignore[no-untyped-def]
    if name == "MarketDataConnector":
        from .market_data_connector import MarketDataConnector

        return MarketDataConnector
    if name == "MarketWSClient":
        from .market_ws_client import MarketWSClient

        return MarketWSClient
    if name == "WebSocketAggregator":
        from .websocket_aggregator import WebSocketAggregator

        return WebSocketAggregator
    raise AttributeError(name)

__all__ = ["MarketDataConnector", "MarketWSClient", "WebSocketAggregator"]
