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
from copy import deepcopy
from typing import List, Optional, Dict, Any

from apps.reference.config_models import InstrumentProfile

logger = logging.getLogger(__name__)


_INSTRUMENT_DEFAULTS = {
    "exchange": "binance",
    "quote_asset": "USDT",
    "precision": {"quantity": 3, "price": 2},
    "limits": {
        "min_notional": 10.0,
        "min_qty": 0.001,
        "min_price": 0.01,
        "step_size": 0.001,
        "tick_size": 0.01,
        "max_position_size": 5.0,
        "max_leverage": 20,
    },
    "tp_sl": {},
    "risk": {},
}


def _make_default_profile(symbol: str) -> Dict[str, Any]:
    profile = deepcopy(_INSTRUMENT_DEFAULTS)
    profile["symbol"] = symbol
    profile.setdefault(
        "base_asset", symbol[:-4] if symbol.endswith("USDT") else symbol)
    return profile


def _to_float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


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
        # Try approach 1: apps.reference.config_loader with Pydantic
        from apps.reference.config_loader import get_config
        config = get_config()
        # Try v2 first
        if hasattr(config, 'config_v2') and config.config_v2 and config.config_v2.symbols:
            symbols_cfg = config.config_v2.symbols
            if 'symbols' in symbols_cfg:
                return symbols_cfg['symbols']
        # Fallback to legacy
        instruments = config.trading.instruments if hasattr(
            config.trading, 'instruments') else {}
        if instruments:
            return list(instruments.keys())
    except Exception as e:
        logger.debug(f"Approach 1 (get_config) failed: {e}")

    try:
        # Try approach 2: vfoundation.config (environment-based)
        from vfoundation.config import config as vfoundation_config
        if hasattr(vfoundation_config, 'trading'):
            # config is vfoundation.config.Config object
            instruments = getattr(
                vfoundation_config.trading, 'instruments', {})
            if instruments:
                return list(instruments.keys())
    except Exception as e:
        logger.debug(f"Approach 2 (vfoundation.config) failed: {e}")

    # Last resort fallback
    logger.warning("Using hardcoded fallback symbols: SOLUSDT, ETHUSDT")
    return ["SOLUSDT", "ETHUSDT"]


def get_first_symbol() -> str:
    """
    Get the first configured trading symbol.

    Returns:
        First configured symbol (default: 'SOLUSDT')

    Example:
        >>> symbol = get_first_symbol()
        >>> print(symbol)
        'SOLUSDT'
    """
    symbols = get_trading_symbols()
    return symbols[0] if symbols else "SOLUSDT"


def get_symbol_config(symbol: str) -> Optional[Any]:
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
        # Try v2 first
        if hasattr(config, 'config_v2') and config.config_v2 and config.config_v2.instruments:
            instruments_cfg = config.config_v2.instruments
            if 'instruments' in instruments_cfg and symbol in instruments_cfg['instruments']:
                return instruments_cfg['instruments'][symbol]
        # Fallback to legacy
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
        from vfoundation.config import config as vfoundation_config
        if hasattr(vfoundation_config, 'trading'):
            instruments = getattr(
                vfoundation_config.trading, 'instruments', {})
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


def _get_v2_instrument_profile(cfg: Any, symbol: str) -> Optional[Dict[str, Any]]:
    """Get instrument profile from config v2."""
    if not hasattr(cfg, 'config_v2') or cfg.config_v2 is None:
        return None
    instruments = cfg.config_v2.instruments
    if instruments is None:
        return None
    instruments_dict = instruments.get("instruments", {})
    return instruments_dict.get(symbol)


def _get_v2_overrides_for_symbol(cfg: Any, symbol: str) -> Optional[Dict[str, Any]]:
    """Get symbol-level overrides from config v2."""
    if not hasattr(cfg, 'config_v2') or cfg.config_v2 is None or cfg.config_v2.overrides is None:
        return None
    symbols_overrides = cfg.config_v2.overrides.get("symbols", {})
    return symbols_overrides.get(symbol)


def _build_instrument_profile_from_v2(cfg: Any, symbol: str) -> Optional[InstrumentProfile]:
    """Build instrument profile from v2 config."""
    base_profile = _get_v2_instrument_profile(cfg, symbol)
    if base_profile is None:
        return None

    profile = _make_default_profile(symbol)
    _deep_merge(profile, base_profile)

    # Apply symbol-level overrides
    overrides = _get_v2_overrides_for_symbol(cfg, symbol)
    if overrides:
        _deep_merge(profile, overrides)

    # Extract fields
    try:
        precision = profile.get("precision", {})
        limits = profile.get("limits", {})
        if "min_qty" not in limits and "step_size" in limits:
            limits["min_qty"] = limits["step_size"]
        if "min_price" not in limits and "tick_size" in limits:
            limits["min_price"] = limits["tick_size"]
        tp_sl = profile.get("tp_sl", {})
        tp_sl_overrides = tp_sl.get("overrides", {})
        risk = profile.get("risk", {})
        base_asset = profile.get("base_asset") or (
            symbol[:-4] if symbol.endswith("USDT") else symbol
        )
        quote_asset = profile.get("quote_asset", "USDT")

        precision_quantity = _to_int(precision.get("quantity"), 3)
        precision_price = _to_int(precision.get("price"), 2)
        step_size = _to_float(
            limits.get("step_size"), 10 ** (-precision_quantity)
        )
        tick_size = _to_float(
            limits.get("tick_size"), 10 ** (-precision_price)
        )
        min_qty = _to_float(limits.get("min_qty"), step_size)
        min_price = _to_float(limits.get("min_price"), tick_size)

        return InstrumentProfile(
            symbol=symbol,
            exchange=profile.get("exchange", "binance"),
            base_asset=base_asset,
            quote_asset=quote_asset,
            precision_quantity=precision_quantity,
            precision_price=precision_price,
            min_notional=_to_float(limits.get("min_notional"), 10.0),
            min_qty=min_qty,
            min_price=min_price,
            step_size=step_size,
            tick_size=tick_size,
            max_position_size=_to_float(limits.get("max_position_size"), 5.0),
            max_leverage=_to_float(limits.get("max_leverage"), 20.0),
            default_tp_bps=tp_sl.get("default_tp_bps"),
            default_sl_bps=tp_sl.get("default_sl_bps"),
            min_sl_bps=tp_sl_overrides.get("min_sl_bps"),
            min_tp_bps=tp_sl_overrides.get("min_tp_bps"),
            regime_multipliers=profile.get("regime_multipliers"),
            risk_max_drawdown_pct=risk.get("max_drawdown_pct"),
            risk_fraction=risk.get("risk_fraction"),
            source="config_v2",
        )
    except Exception as e:
        logger.warning(f"Failed to build v2 profile for {symbol}: {e}")
        return None


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    """Deep merge override into base dict."""
    for key, value in override.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _build_instrument_profile_from_legacy(cfg: Any, symbol: str) -> InstrumentProfile:
    """Build instrument profile from legacy config."""
    # Get legacy config
    legacy_cfg = get_symbol_config(symbol)
    if legacy_cfg is None:
        # Fallback defaults
        return InstrumentProfile(
            symbol=symbol,
            exchange="binance",
            base_asset=symbol[:-4],
            quote_asset="USDT",
            precision_quantity=3,
            precision_price=2,
            min_notional=10.0,
            min_qty=0.001,
            min_price=0.01,
            step_size=0.001,
            tick_size=0.01,
            max_position_size=5.0,
            max_leverage=20,
            source="legacy",
        )

    # Extract fields from legacy dict
    return InstrumentProfile(
        symbol=symbol,
        exchange=legacy_cfg.get("exchange", "binance"),
        base_asset=legacy_cfg.get("base_asset", symbol[:-4]),
        quote_asset=legacy_cfg.get("quote_asset", "USDT"),
        precision_quantity=legacy_cfg.get("precision_quantity", 3),
        precision_price=legacy_cfg.get("precision_price", 2),
        min_notional=legacy_cfg.get("min_notional", 10.0),
        min_qty=legacy_cfg.get("min_qty", 0.001),
        min_price=legacy_cfg.get("min_price", 0.01),
        step_size=legacy_cfg.get("step_size", 0.001),
        tick_size=legacy_cfg.get("tick_size", 0.01),
        max_position_size=legacy_cfg.get("max_position_size", 5.0),
        max_leverage=legacy_cfg.get("max_leverage", 20),
        default_tp_bps=legacy_cfg.get("default_tp_bps"),
        default_sl_bps=legacy_cfg.get("default_sl_bps"),
        min_sl_bps=legacy_cfg.get("min_sl_bps"),
        min_tp_bps=legacy_cfg.get("min_tp_bps"),
        regime_multipliers=legacy_cfg.get("regime_multipliers"),
        risk_max_drawdown_pct=legacy_cfg.get("risk_max_drawdown_pct"),
        risk_fraction=legacy_cfg.get("risk_fraction"),
        source="legacy",
    )


def resolve_instrument_profile(cfg: Any, symbol: str) -> InstrumentProfile:
    """
    Resolve unified instrument profile with dual-mode support.

    Priority: config v2 (instruments.yaml + overrides.yaml) -> legacy (trading.instruments.*)
    """
    # Try v2 first
    profile = _build_instrument_profile_from_v2(cfg, symbol)
    if profile is not None:
        return profile

    # Fallback to legacy
    return _build_instrument_profile_from_legacy(cfg, symbol)
