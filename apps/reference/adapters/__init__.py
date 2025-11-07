"""
Adapters for apps.reference

Contains exchange adapters and related utilities.

Adapter Types:
1. HTTP REST adapters (BinanceAdapter) - for direct REST API usage
2. SDK adapters (SdkAdapterBinance) - wrapper around python-binance SDK
   Inherits from vfoundation.core.adapters.ExecutionAdapter (framework abstraction)
"""

from .binance_adapter import BinanceAdapter, BinanceAPIError
from .sdk_adapter_binance import SdkAdapterBinance

__all__ = ["BinanceAdapter", "BinanceAPIError", "SdkAdapterBinance"]
