"""
Config Resolver for Execution Position Domain

RID: EP-CONFIG-SSOT-S1

Purpose:
- Transform raw YAML dict → ExecutionPositionConfig (Pydantic models)
- Handle defaults, validation, nested structures
- Centralize config loading logic (avoid scattered dict.get() calls)

Design Principles:
- Single entry point: resolve_execution_position_config()
- Fail early on invalid config (ValidationError)
- Preserve backward compatibility with current YAML structure
- Does NOT modify runtime code (used by future integrations only)

Usage Example:
    from apps.reference.config.execution_position import resolve_execution_position_config
    import yaml

    with open("config/domains/execution.yaml") as f:
        raw = yaml.safe_load(f)

    ep_cfg = resolve_execution_position_config(raw)

    # Type-safe access
    sl_pct = ep_cfg.aggregated_oco.sl_pct
    trail_distance = ep_cfg.trailing.trail_distance_bps
"""

import logging
from typing import Dict, Any, Optional

from apps.reference.domains.execution_position.config import (
    ExecutionPositionConfig,
    AggregatedOcoConfig,
    AggregatedOcoWatchdogConfig,
    AggregatedOcoWatchdogGraceConfig,
    TrailingConfig,
    CloseConfig,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================

def _get_nested(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """
    Safely extract nested dict value.

    Example:
        _get_nested({"a": {"b": {"c": 42}}}, "a", "b", "c")  # 42
        _get_nested({"a": {}}, "a", "b", "c", default=0)    # 0
    """
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is default:
            return default
    return current


def _coerce_bool(value: Any, default: bool) -> bool:
    """Coerce value to bool with fallback"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes", "on"}
    return bool(value)


def _coerce_int(value: Any, default: int) -> int:
    """Coerce value to int with fallback"""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning(
            f"Cannot coerce {value!r} to int, using default {default}")
        return default


def _coerce_float(value: Any, default: float) -> float:
    """Coerce value to float with fallback"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        logger.warning(
            f"Cannot coerce {value!r} to float, using default {default}")
        return default


# ============================================================================
# Resolver Functions
# ============================================================================

def _resolve_aggregated_oco_watchdog_grace(
    grace_node: Dict[str, Any]
) -> AggregatedOcoWatchdogGraceConfig:
    """Resolve watchdog grace config from YAML node"""
    return AggregatedOcoWatchdogGraceConfig(
        enabled=_coerce_bool(grace_node.get("enabled"), False),
        period_sec=_coerce_float(grace_node.get("period_sec"), 0.0),
        kinds=grace_node.get("kinds", []),
    )


def _resolve_aggregated_oco_watchdog(
    watchdog_node: Dict[str, Any]
) -> AggregatedOcoWatchdogConfig:
    """Resolve watchdog config from YAML node"""
    grace_node = watchdog_node.get("grace", {})

    return AggregatedOcoWatchdogConfig(
        enabled=_coerce_bool(watchdog_node.get("enabled"), False),
        interval_sec=_coerce_int(watchdog_node.get("interval_sec"), 5),
        auto_heal_orphans=_coerce_bool(
            watchdog_node.get("auto_heal_orphans"), True),
        grace=_resolve_aggregated_oco_watchdog_grace(grace_node),
    )


def _resolve_aggregated_oco(
    raw_cfg: Dict[str, Any],
    path: tuple = ("manage", "brackets", "aggregated_oco")
) -> AggregatedOcoConfig:
    """
    Resolve AggregatedOcoConfig from raw YAML config.

    YAML path: config.domains.execution.manage.brackets.aggregated_oco
    Alternative: config.domains.execution.brackets.aggregated_oco

    Args:
        raw_cfg: Raw YAML config dict (typically from execution.yaml)
        path: Tuple of keys to navigate to aggregated_oco node

    Returns:
        AggregatedOcoConfig with validated fields

    Raises:
        ValidationError: If config values are invalid (e.g., sl_pct <= 0)
    """
    # Try primary path (manage.brackets.aggregated_oco)
    agg_node = _get_nested(raw_cfg, *path, default={})

    # Fallback to flat brackets.aggregated_oco if primary path empty
    if not agg_node:
        agg_node = _get_nested(raw_cfg, "brackets",
                               "aggregated_oco", default={})

    # Extract watchdog
    watchdog_node = agg_node.get("watchdog", {})

    return AggregatedOcoConfig(
        enabled=_coerce_bool(agg_node.get("enabled"), False),
        aggregated_only_mode=_coerce_bool(
            agg_node.get("aggregated_only_mode"), False),
        sl_pct=_coerce_float(agg_node.get("sl_pct"), 0.02),
        tp_rr=_coerce_float(agg_node.get("tp_rr"), 2.0),
        sl_roi_pct=_coerce_float(agg_node.get("sl_roi_pct"), 35.0),
        tp_roi_pct=_coerce_float(agg_node.get("tp_roi_pct"), 50.0),
        roi_basis=str(agg_node.get("roi_basis", "margin")),
        leverage_source=str(agg_node.get("leverage_source", "instrument_max")),
        recalc_on_scale_in=_coerce_bool(
            agg_node.get("recalc_on_scale_in"), True),
        recalc_on_partial_close=_coerce_bool(
            agg_node.get("recalc_on_partial_close"), False),
        ttl_protect_new_bracket_ms=_coerce_int(
            agg_node.get("ttl_protect_new_bracket_ms"), 3000),
        allow_unprotected_position=_coerce_bool(
            agg_node.get("allow_unprotected_position"), False),
        max_sl_legs=_coerce_int(agg_node.get("max_sl_legs"), 1),
        max_tp_legs=_coerce_int(agg_node.get("max_tp_legs"), 1),
        watchdog=_resolve_aggregated_oco_watchdog(watchdog_node),
    )


def _resolve_trailing(
    raw_cfg: Dict[str, Any],
    path: tuple = ("manage", "trailing")
) -> TrailingConfig:
    """
    Resolve TrailingConfig from raw YAML config.

    YAML path: config.domains.execution.manage.trailing
    Alternative: config.domains.execution.trailing

    Args:
        raw_cfg: Raw YAML config dict
        path: Tuple of keys to navigate to trailing node

    Returns:
        TrailingConfig with validated fields
    """
    # Try primary path (manage.trailing)
    trailing_node = _get_nested(raw_cfg, *path, default={})

    # Fallback to flat trailing if primary path empty
    if not trailing_node:
        trailing_node = _get_nested(raw_cfg, "trailing", default={})

    return TrailingConfig(
        enabled=_coerce_bool(trailing_node.get("enabled"), False),
        trail_distance_bps=_coerce_float(
            trailing_node.get("trail_distance_bps"), 100.0),
        activate_after_bps=_coerce_float(
            trailing_node.get("activate_after_bps"), 0.0),
        breakeven_rr=_coerce_float(trailing_node.get("breakeven_rr"), 0.0),
        hard_time_exit_sec=trailing_node.get(
            "hard_time_exit_sec"),  # Optional[float]
        activation_profit_atr_k=_coerce_float(
            trailing_node.get("activation_profit_atr_k"), 1.0),
        cooldown_sec=_coerce_float(trailing_node.get("cooldown_sec"), 0.0),
        step_bps=_coerce_float(trailing_node.get("step_bps"), 0.0),
    )


def _resolve_close(
    raw_cfg: Dict[str, Any],
    path: tuple = ("manage", "close")
) -> CloseConfig:
    """
    Resolve CloseConfig from raw YAML config.

    YAML path: config.domains.execution.manage.close (if exists)
    Note: This section does NOT exist in current execution.yaml yet.

    Args:
        raw_cfg: Raw YAML config dict
        path: Tuple of keys to navigate to close node

    Returns:
        CloseConfig with validated fields (mostly defaults)
    """
    # Try primary path (manage.close)
    close_node = _get_nested(raw_cfg, *path, default={})

    # Fallback to flat close if primary path empty
    if not close_node:
        close_node = _get_nested(raw_cfg, "close", default={})

    return CloseConfig(
        max_hold_time_sec=_coerce_int(close_node.get("max_hold_time_sec"), 0),
        reason_policy=close_node.get("reason_policy", "default"),
        allow_time_exit=_coerce_bool(close_node.get("allow_time_exit"), True),
        allow_profit_exit=_coerce_bool(
            close_node.get("allow_profit_exit"), True),
    )


def resolve_execution_position_config(
    raw_cfg: Dict[str, Any],
    *,
    aggregated_oco_path: tuple = ("manage", "brackets", "aggregated_oco"),
    trailing_path: tuple = ("manage", "trailing"),
    close_path: tuple = ("manage", "close"),
) -> ExecutionPositionConfig:
    """
    Resolve ExecutionPositionConfig from raw YAML config dict.

    Main entry point for config loading. Transforms raw dict → typed Pydantic models.

    Args:
        raw_cfg: Raw YAML config dict (typically from execution.yaml)
        aggregated_oco_path: Path to aggregated_oco node (default: manage.brackets.aggregated_oco)
        trailing_path: Path to trailing node (default: manage.trailing)
        close_path: Path to close node (default: manage.close)

    Returns:
        ExecutionPositionConfig with validated typed fields

    Raises:
        ValidationError: If any config value violates Pydantic Field constraints

    Example:
        import yaml
        from apps.reference.config.execution_position import resolve_execution_position_config

        with open("config/domains/execution.yaml") as f:
            raw = yaml.safe_load(f)

        ep_cfg = resolve_execution_position_config(raw)

        # Type-safe access
        assert ep_cfg.aggregated_oco.sl_pct > 0
        assert ep_cfg.trailing.trail_distance_bps >= 0
        assert ep_cfg.close.max_hold_time_sec >= 0

    YAML Structure Expected:
        manage:
          brackets:
            aggregated_oco:
              enabled: true
              sl_pct: 0.02
              tp_rr: 2.0
              watchdog:
                enabled: true
                grace:
                  enabled: true
                  period_sec: 2.0
          trailing:
            enabled: false
            trail_distance_bps: 100.0
          close:
            max_hold_time_sec: 0
    """
    aggregated_oco = _resolve_aggregated_oco(raw_cfg, path=aggregated_oco_path)
    trailing = _resolve_trailing(raw_cfg, path=trailing_path)
    close = _resolve_close(raw_cfg, path=close_path)

    return ExecutionPositionConfig(
        aggregated_oco=aggregated_oco,
        trailing=trailing,
        close=close,
    )


# ============================================================================
# Public API
# ============================================================================

__all__ = [
    "resolve_execution_position_config",
    "resolve_effective_leverage",
    "compute_sl_tp_from_roi",
]


def resolve_effective_leverage(symbol: str, config: Any, default: float = 10.0) -> float:
    """
    Resolve effective leverage for a symbol using config_v2 instruments/execution.

    Priority:
    1) config.trading.instruments.<symbol>.model_extra.limits.max_leverage (merged from v2)
    2) config.instruments.<symbol>.limits.max_leverage (system_config.yaml format)
    3) config_v2.domains.instruments.instruments.<symbol>.limits.max_leverage
    4) config.domains.instruments.instruments.<symbol>.limits.max_leverage
    5) config_v2.domains.execution.exposure.leverage_defaults.max_leverage
    6) fallback default (10.0)
    """
    candidates = []

    # Primary: merged trading.instruments from v2 (Pydantic models with extra fields)
    trading = getattr(config, 'trading', None)
    if trading:
        instruments = getattr(trading, 'instruments', None)
        if instruments and isinstance(instruments, dict) and symbol in instruments:
            instr_spec = instruments[symbol]
            if hasattr(instr_spec, 'model_extra') and isinstance(instr_spec.model_extra, dict):
                limits = instr_spec.model_extra.get('limits', {})
                if isinstance(limits, dict):
                    candidates.append(limits.get('max_leverage'))

    # ROIFIX: system_config.yaml format
    candidates.append(_get_nested(config, "instruments", symbol, "limits", "max_leverage"))

    # Legacy config_v2 paths
    candidates.append(_get_nested(config, "config_v2", "domains", "instruments",
                    "instruments", symbol, "limits", "max_leverage"))
    candidates.append(_get_nested(config, "domains", "instruments",
                    "instruments", symbol, "limits", "max_leverage"))
    candidates.append(_get_nested(config, "config_v2", "domains", "execution",
                    "exposure", "leverage_defaults", "max_leverage"))

    for cand in candidates:
        try:
            if cand is None:
                continue
            lev = float(cand)
            if lev > 0:
                return lev
        except (TypeError, ValueError):
            continue
    return float(default)


def compute_sl_tp_from_roi(
    ep_cfg: ExecutionPositionConfig,
    symbol: str,
    leverage: float,
) -> tuple[float, float]:
    """
    Compute (sl_pct_price, tp_rr) using ROI targets and leverage.

    Args:
        ep_cfg: Typed execution_position config
        symbol: Trading symbol (unused currently, reserved for per-symbol overrides)
        leverage: Effective leverage to translate ROI% to price distance

    Returns:
        tuple of (sl_pct_price, tp_rr)
    """
    agg = getattr(ep_cfg, "aggregated_oco", None)
    if not agg:
        return (0.0, 0.0)

    try:
        lev = float(leverage)
    except (TypeError, ValueError):
        lev = 1.0
    if lev <= 0:
        lev = 1.0

    sl_roi = getattr(agg, "sl_roi_pct", None)
    tp_roi = getattr(agg, "tp_roi_pct", None)
    if sl_roi is not None and tp_roi is not None and sl_roi > 0 and tp_roi > 0:
        sl_pct_price = (sl_roi / 100.0) / lev
        tp_pct_price = (tp_roi / 100.0) / lev
        tp_rr = tp_pct_price / sl_pct_price if sl_pct_price else agg.tp_rr
        return sl_pct_price, tp_rr

    return agg.sl_pct, agg.tp_rr
