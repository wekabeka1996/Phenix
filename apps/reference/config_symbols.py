"""
Configuration-driven symbol management.

This module provides a single source of truth for trading symbols.
All modules should use these functions instead of hardcoding symbols.

Usage:
    from apps.reference.config_symbols import get_trading_symbols, get_first_symbol

    symbols = get_trading_symbols()  # Returns list from config
    symbol = get_first_symbol()       # Returns first configured symbol
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def get_trading_symbols() -> List[str]:
    """
    Get list of trading symbols from configuration.

    Returns:
        List of trading symbols (e.g., ['SOLUSDT', 'ETHUSDT'])
        Falls back to ['SOLUSDT', 'ETHUSDT'] if config unavailable

    Example:
        >>> symbols = get_trading_symbols()
        >>> print(symbols)
        ['SOLUSDT', 'ETHUSDT']
    """
    try:
        # Try approach 1: Direct import with Pydantic config
        from apps.reference.config_loader import get_config
        config = get_config()
        # Access Pydantic object directly
        instruments = config.trading.instruments if hasattr(
            config.trading, 'instruments') else {}
        if instruments:
            return list(instruments.keys())
    except Exception as e:
        logger.debug(f"Approach 1 (get_config) failed: {e}")

    try:
        # Try approach 2: vfoundation.config (environment-based)
        from vfoundation.config import config
        if hasattr(config, 'trading'):
            # config is vfoundation.config.Config object
            instruments = getattr(config.trading, 'instruments', {})
            if instruments:
                return list(instruments.keys())
    except Exception as e:
        logger.debug(f"Approach 2 (vfoundation.config) failed: {e}")

    # Last resort fallback - FAIL FAST
    error_msg = "No trading symbols configured! Please check 'trading.instruments' in your config."
    logger.critical(error_msg)
    raise ValueError(error_msg)


def get_first_symbol() -> str:
    """
    Get the first configured trading symbol.

    Returns:
        First configured symbol

    Example:
        >>> symbol = get_first_symbol()
        >>> print(symbol)
        'SOLUSDT'
    """
    symbols = get_trading_symbols()
    return symbols[0]


def get_symbol_config(symbol: str) -> Optional[dict]:
    """
    Get configuration for a specific symbol.

    Args:
        symbol: Trading symbol (e.g., 'SOLUSDT')

    Returns:
        Symbol configuration dict or None

    Example:
        >>> config = get_symbol_config('SOLUSDT')
        >>> print(config)
        {'step_size': '0.01', 'min_notional': '10'}
    """
    try:
        # Try approach 1: apps.reference.config_loader with Pydantic
        from apps.reference.config_loader import get_config
        config = get_config()
        instruments = config.trading.instruments if hasattr(
            config.trading, 'instruments') else {}
        if instruments and symbol in instruments:
            # Convert Pydantic model to dict
            symbol_cfg = instruments[symbol]
            if hasattr(symbol_cfg, 'model_dump'):
                return symbol_cfg.model_dump()
            elif hasattr(symbol_cfg, 'dict'):
                return symbol_cfg.dict()
            else:
                return dict(symbol_cfg) if symbol_cfg else None
    except Exception as e:
        logger.debug(f"Approach 1 (get_config) failed: {e}")

    try:
        # Try approach 2: vfoundation.config (environment-based)
        from vfoundation.config import config
        if hasattr(config, 'trading'):
            instruments = getattr(config.trading, 'instruments', {})
            if instruments and symbol in instruments:
                return instruments[symbol]
    except Exception as e:
        logger.debug(f"Approach 2 (vfoundation.config) failed: {e}")

    logger.debug(f"Could not find config for symbol {symbol}")
    return None


def validate_symbol(symbol: str) -> bool:
    """
    Validate that a symbol is configured.

    Args:
        symbol: Symbol to validate

    Returns:
        True if symbol is in trading configuration, False otherwise

    Example:
        >>> is_valid = validate_symbol('SOLUSDT')
        >>> print(is_valid)
        True
    """
    symbols = get_trading_symbols()
    return symbol in symbols
