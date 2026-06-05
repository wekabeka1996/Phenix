"""
J6-S16 — Surface Key Builder

Constructs a canonical surface_key from available candidate fields.
The key format is chosen to match the surface keys in surface_evidence_v1.json.

Field priority:
  regime > side > symbol_group > tier_family

If a field is not available, it is represented as 'all_sides', 'all_symbols',
or 'all_tf' as appropriate (consistent with fixture key structure).

The builder is deterministic and stateless. It never raises — on missing
or invalid input it returns 'unknown:unknown:unknown:unknown' so that
the registry lookup returns the UNKNOWN sentinel.
"""

from __future__ import annotations

from typing import Optional


_UNKNOWN = "unknown"

# Map of known regime string variants → canonical name used in fixture keys
_REGIME_CANONICAL = {
    "HIGH_VOLATILITY": "HIGH_VOLATILITY",
    "TREND_UP": "TREND_UP",
    "TREND_DOWN": "TREND_DOWN",
    "LOW_VOLATILITY": "LOW_VOLATILITY",
    "MEAN_REVERSION": "MEAN_REVERSION",
    "UNCERTAIN": "UNCERTAIN",
    "PENDING": "regime_incomplete",
    "REGIME_CONTEXT_MISSING": "regime_incomplete",
}

# Symbol groups (lower priority lookup — matches fixture symbol_group field)
_ETH_PEPE_SYMBOLS = {"ETHUSDT", "1000PEPEUSDT"}

# Sides (BUY→BUY, SELL→SELL, None→all_sides)
_SIDE_CANONICAL = {
    "BUY": "BUY",
    "SELL": "SELL",
    "LONG": "BUY",
    "SHORT": "SELL",
}


def build_surface_key(
    *,
    regime: Optional[str],
    side: Optional[str],
    symbol: Optional[str] = None,
    tier_family: Optional[str] = None,
) -> str:
    """Build a canonical surface key for registry lookup.

    Args:
        regime:      Regime label (e.g. 'HIGH_VOLATILITY', 'TREND_UP').
                     None or unrecognised → 'regime_incomplete'.
        side:        Trade side ('BUY', 'SELL', 'LONG', 'SHORT').
                     None → 'all_sides'.
        symbol:      Symbol string for ETH/PEPE sub-surface routing.
                     None → 'all_symbols'.
        tier_family: Optional tier family hint from plan context.
                     None → omitted from key (uses 'regime_complete').

    Returns:
        A ':'-separated surface key string matching fixture key format.
    """
    try:
        regime_part = _REGIME_CANONICAL.get(regime or "", "regime_incomplete") if regime else "regime_incomplete"
        side_part = _SIDE_CANONICAL.get(side or "", "all_sides") if side else "all_sides"
        symbol_group = _resolve_symbol_group(symbol)
        tier_part = tier_family or "regime_complete"
        return f"{regime_part}:{side_part}:{symbol_group}:{tier_part}"
    except Exception:  # noqa: BLE001
        return f"{_UNKNOWN}:{_UNKNOWN}:{_UNKNOWN}:{_UNKNOWN}"


def _resolve_symbol_group(symbol: Optional[str]) -> str:
    if symbol is None:
        return "all_symbols"
    if symbol in _ETH_PEPE_SYMBOLS:
        return "ETH_PEPE"
    return "all_symbols"
