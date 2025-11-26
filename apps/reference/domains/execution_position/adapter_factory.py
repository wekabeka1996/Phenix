from typing import Any
import logging

from apps.reference.domains.execution_position.binance_execution_adapter import (
    BinanceExecutionAdapter,
)

try:
    from apps.reference.domains.execution_position.simulated_adapter import (
        SimulatedExecutionAdapter,
    )
except Exception:  # pragma: no cover - optional dependency
    SimulatedExecutionAdapter = None  # type: ignore

logger = logging.getLogger(__name__)
CANONICAL_EXECUTION_ADAPTER = BinanceExecutionAdapter


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
    Build execution adapter based on trading_mode / config.

    Rules (minimum):
    - 'testnet' → BinanceExecutionAdapter
    - 'live'    → BinanceExecutionAdapter
    - 'hybrid_live_data_testnet_exec' → BinanceExecutionAdapter (exec on testnet)
    - 'sim', 'shadow', other dev modes → Simulated/Paper adapter or None
    """
    mode = _extract_trading_mode(config)
    mode = str(mode or "testnet").lower()

    if mode in {"testnet", "live", "hybrid_live_data_testnet_exec"}:
        # Extract REST timeout from config (default 20.0s)
        rest_timeout_sec = 20.0
        try:
            # Try config v2 path: execution.adapters.binance.rest_timeout_sec
            if hasattr(config, 'config_v2') and config.config_v2:
                execution_cfg = getattr(config.config_v2, 'execution', None)
                if execution_cfg and isinstance(execution_cfg, dict):
                    adapters_cfg = execution_cfg.get('adapters', {})
                    binance_cfg = adapters_cfg.get('binance', {})
                    rest_timeout_sec = float(
                        binance_cfg.get('rest_timeout_sec', 20.0))
        except Exception as e:
            logger.debug(
                f"Failed to read rest_timeout_sec from config, using default 20.0s: {e}")

        adapter_cls = CANONICAL_EXECUTION_ADAPTER
        logger.info(
            "ExecPosRuntimeV2 using canonical adapter %s (mode=%s)",
            adapter_cls.__name__,
            mode,
        )
        return adapter_cls(
            fsm=fsm,
            config=config,
            shadow_mode=False,
            rest_timeout_sec=rest_timeout_sec
        )

    if mode in {"sim", "shadow", "paper"}:
        if SimulatedExecutionAdapter is not None:
            return SimulatedExecutionAdapter()
        logger.info(
            "SimulatedExecutionAdapter unavailable; returning None for mode=%s", mode)
        return None

    # Default to safe None if unknown mode
    logger.info("Unknown trading_mode '%s'; no execution adapter created", mode)
    return None
