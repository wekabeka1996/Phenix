"""
Adapters for apps.reference

Contains exchange adapters and related utilities.

Adapter Types:
1. HTTP REST adapters (BinanceAdapter) - for direct REST API usage with TimeoutConfig
   Uses config_adapter.py for timeout/retry configuration from YAML
"""

from .binance_adapter import BinanceAdapter, BinanceAPIError

__all__ = ["BinanceAdapter", "BinanceAPIError"]
