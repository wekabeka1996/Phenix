"""
Adapter Factory for Execution Position Runtime.

Selects the appropriate execution adapter based on trading_mode configuration.
"""
from typing import Any
import logging

from apps.reference.adapters.binance_adapter import BinanceAdapter

logger = logging.getLogger(__name__)

# Canonical adapter for all production modes
CANONICAL_EXECUTION_ADAPTER = BinanceAdapter

# Supported trading modes that require real exchange adapter
_SUPPORTED_MODES = frozenset({
    "testnet",
    "live",
    "hybrid_live_data_testnet_exec",
    "shadow_live",
    "full_live",
    "full_testnet",
})


def _extract_trading_mode(config: Any) -> str:
    """
    Best-effort extraction of trading_mode from config object or dict.
    Defaults to 'testnet' if not found.
    """
    try:
        if hasattr(config, "trading_mode"):
            mode = getattr(config, "trading_mode", None)
            if mode:
                return str(mode).lower()
    except Exception:
        pass

    try:
        cfg_dict = config.to_dict() if hasattr(config, "to_dict") else config
        if isinstance(cfg_dict, dict):
            trading = cfg_dict.get("trading") or {}
            if isinstance(trading, dict):
                mode = trading.get("trading_mode") or trading.get("mode")
                if mode:
                    return str(mode).lower()
    except Exception:
        pass

    return "testnet"


def build_execution_adapter(config: Any, fsm: Any | None = None) -> Any | None:
    """
    Build execution adapter based on trading_mode.

    Supported modes:
    - testnet, live, hybrid_live_data_testnet_exec, shadow_live → BinanceAdapter
    - Unknown modes → None (safe fallback)
    """
    mode = _extract_trading_mode(config)
    mode = str(mode or "testnet").lower()

    if mode in _SUPPORTED_MODES:
        logger.info(
            "ExecPosRuntimeV2 using canonical adapter %s (mode=%s)",
            CANONICAL_EXECUTION_ADAPTER.__name__,
            mode,
        )
        return CANONICAL_EXECUTION_ADAPTER(config=config, fsm=fsm)

    # Unknown mode - safe fallback
    logger.info("Unknown trading_mode '%s'; no execution adapter created", mode)
    return None
