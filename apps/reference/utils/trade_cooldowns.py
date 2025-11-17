"""Trade cooldown helpers for execution domain."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

_LOGGER = logging.getLogger(__name__)
_LEGACY_SYMBOLS_WARNED: set[str] = set()


def _as_dict(value: Any) -> Dict[str, Any]:
    """Best-effort conversion of config fragments to dict."""
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:  # pragma: no cover - defensive
            pass
    value_dict = getattr(value, "__dict__", None)
    if isinstance(value_dict, dict):
        return {k: v for k, v in value_dict.items() if not k.startswith("_")}
    return {}


def _to_non_negative_float(raw: Any) -> Optional[float]:
    """Convert arbitrary value to non-negative float; return None on failure."""
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _warn_legacy(symbol: str) -> None:
    """Emit deprecation warning for legacy cooldown key once per symbol."""
    if symbol in _LEGACY_SYMBOLS_WARNED:
        return
    _LEGACY_SYMBOLS_WARNED.add(symbol)
    _LOGGER.warning(
        "[trade_cooldown] Using legacy instruments.%s.cooldown_sec; "
        "prefer trade_cooldown_sec",
        symbol,
    )


def get_trade_cooldown_sec_for_symbol(config: Any, symbol: str) -> float:
    """Return effective trade cooldown (seconds) for a symbol with legacy fallback."""
    trading_cfg = None
    if hasattr(config, "trading"):
        trading_cfg = getattr(config, "trading")
    if trading_cfg is None and isinstance(config, dict):
        trading_cfg = config.get("trading")

    instruments = None
    if trading_cfg is not None:
        if isinstance(trading_cfg, dict):
            instruments = trading_cfg.get("instruments")
        else:
            instruments = getattr(trading_cfg, "instruments", None)

    instruments_dict = _as_dict(instruments)
    entry = instruments_dict.get(symbol)
    if entry is None:
        entry = instruments_dict.get("__default__")

    entry_dict = _as_dict(entry)

    canonical = _to_non_negative_float(entry_dict.get("trade_cooldown_sec"))
    if canonical is not None:
        return canonical

    legacy = _to_non_negative_float(entry_dict.get("cooldown_sec"))
    if legacy is not None:
        _warn_legacy(symbol)
        return legacy

    return 0.0


__all__ = ["get_trade_cooldown_sec_for_symbol"]
