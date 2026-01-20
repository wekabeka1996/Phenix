"""
Contract definition for Exchange Adapters.
Re-exports vfoundation.core.adapters.base to ensure consistency.
"""
from vfoundation.core.adapters.base import (
    AbstractExchangeAdapter,
    ExchangeOrderParams,
    ExchangeOrderResponse,
    ExchangePosition,
)

__all__ = [
    "AbstractExchangeAdapter",
    "ExchangeOrderParams",
    "ExchangeOrderResponse",
    "ExchangePosition",
]
