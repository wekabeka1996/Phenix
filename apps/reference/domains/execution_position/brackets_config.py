"""Brackets configuration resolver for execution_position domain.

This helper centralises TP/SL resolution so that:
- ManageFlowFSM, ExecPosFSM and other consumers share the same precedence rules.
- Canonical keys (`sl.fixed_bps`, `tp.fixed_bps`, `offset_bps`) are treated as
  single source of truth.
- Legacy keys (`stop_loss_bps`, `take_profit_low_ratio`, `take_profit_high_ratio`)
  remain as fallbacks with warning instrumentation.

Kelly-specific behaviour:
- When only legacy ratios are present, the resolver translates them into
    `tp_bps` for downstream Kelly payoff calculations. Consumers do not need to
    read ratio keys directly.

Inventory of current readers (2025-11-13):
- ManageFlowFSM (`fsm_manage.py`): bracket placement + validation.
- ExecPosFSM (`fsm.py`): TP/SL preview during DEC:OPEN path.
- DecisionMaking (`decision_making.py`): Kelly payoff ratio computation.

The resolver works with both dict configs and Pydantic `AuroraConfig` models
without mutating the original structure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

LOG = logging.getLogger(__name__)

_LEGACY_WARNINGS_EMITTED: set[tuple[str, Optional[str]]] = set()
_MANAGE_BRACKETS_WARNED = False


def _ensure_mapping(candidate: Any) -> Optional[Dict[str, Any]]:
    """Return candidate as dict if possible and non-empty."""
    if candidate is None:
        return None
    if isinstance(candidate, dict):
        return candidate if candidate else None
    if hasattr(candidate, "model_dump"):
        data = candidate.model_dump()
        if isinstance(data, dict) and data:
            return data
    return None


def _get_v2_execution_brackets_cfg(cfg: Any) -> Optional[Dict[str, Any]]:
    """Return canonical execution.brackets block (or manage.brackets fallback) if present."""
    global _MANAGE_BRACKETS_WARNED

    # Check if cfg is AuroraConfig with config_v2
    if not hasattr(cfg, 'config_v2') or cfg.config_v2 is None:
        return None

    primary_cfg = _ensure_mapping(
        _pluck(cfg, 'config_v2', 'domains', 'execution', 'brackets'))
    if primary_cfg is not None:
        return primary_cfg

    manage_cfg = _ensure_mapping(
        _pluck(cfg, 'config_v2', 'domains', 'execution', 'manage', 'brackets'))
    if manage_cfg is not None and not _MANAGE_BRACKETS_WARNED:
        LOG.warning(
            "config_v2.execution.manage.brackets is deprecated; move data to execution.brackets"
        )
        _MANAGE_BRACKETS_WARNED = True
    return manage_cfg


def _pluck(obj: Any, *path: str) -> Any:
    """Safely traverse nested dict/Pydantic/object attributes."""
    current = obj
    for key in path:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(key)
            continue
        # Handle Pydantic BaseModel / SimpleNamespace like objects
        try:
            current = getattr(current, key)
        except AttributeError:
            return None
    return current


def _coerce_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            LOG.warning("Cannot parse decimal from string value '%s'", value)
            return None
    return None


def _log_legacy_once(key: str, symbol: Optional[str]) -> None:
    cache_key = (key, symbol)
    if cache_key in _LEGACY_WARNINGS_EMITTED:
        return
    _LEGACY_WARNINGS_EMITTED.add(cache_key)
    scope = f" for symbol {symbol}" if symbol else ""
    LOG.warning(
        "Using legacy trading.execution.manage.brackets.%s%s; migrate to canonical fixed_bps keys",
        key,
        scope,
    )


def clear_brackets_warning_cache() -> None:
    """Reset module-level warning caches (intended for tests)."""
    global _MANAGE_BRACKETS_WARNED
    _LEGACY_WARNINGS_EMITTED.clear()
    _MANAGE_BRACKETS_WARNED = False


@dataclass(frozen=True)
class ResolvedBrackets:
    sl_bps: Decimal
    tp_bps: Decimal
    offset_bps: int
    sl_source: str
    tp_source: str
    source: str = "legacy"


DEFAULT_SL_BPS = Decimal("50")
DEFAULT_TP_BPS = Decimal("100")
DEFAULT_OFFSET_BPS = 5


def _build_brackets_from_legacy(config: Any, symbol: Optional[str] = None) -> ResolvedBrackets:
    """Legacy logic for brackets config."""
    # Allow configs that embed trading.* at top-level
    brackets_cfg = _pluck(config, "trading", "execution", "manage", "brackets")
    if not brackets_cfg:
        brackets_cfg = _pluck(config, "trading", "execution", "brackets")

    sl_bps = DEFAULT_SL_BPS
    tp_bps = DEFAULT_TP_BPS
    sl_source = "default"
    tp_source = "default"

    if brackets_cfg:
        sl_cfg = _pluck(brackets_cfg, "sl")
        sl_fixed = _coerce_decimal(
            _pluck(sl_cfg, "fixed_bps")) if sl_cfg else None
        if sl_fixed is not None:
            sl_bps = sl_fixed
            sl_source = "sl.fixed_bps"
        else:
            legacy_sl = _coerce_decimal(_pluck(brackets_cfg, "stop_loss_bps"))
            if legacy_sl is not None:
                sl_bps = legacy_sl
                sl_source = "stop_loss_bps"
                _log_legacy_once("stop_loss_bps", symbol)

        tp_cfg = _pluck(brackets_cfg, "tp")
        tp_fixed = _coerce_decimal(
            _pluck(tp_cfg, "fixed_bps")) if tp_cfg else None
        if tp_fixed is not None:
            tp_bps = tp_fixed
            tp_source = "tp.fixed_bps"
        else:
            legacy_high = _coerce_decimal(
                _pluck(brackets_cfg, "take_profit_high_ratio")
            )
            legacy_low = _coerce_decimal(
                _pluck(brackets_cfg, "take_profit_low_ratio")
            )
            if legacy_high is not None and sl_bps is not None:
                tp_bps = Decimal(
                    str(int(round(float(sl_bps) * float(legacy_high))))
                )
                tp_source = "take_profit_high_ratio"
                _log_legacy_once("take_profit_high_ratio", symbol)
            elif legacy_low is not None and sl_bps is not None:
                tp_bps = Decimal(
                    str(int(round(float(sl_bps) * float(legacy_low))))
                )
                tp_source = "take_profit_low_ratio"
                _log_legacy_once("take_profit_low_ratio", symbol)

    offset_raw = _pluck(brackets_cfg, "offset_bps") if brackets_cfg else None
    offset_bps = DEFAULT_OFFSET_BPS
    if isinstance(offset_raw, (int, float)):
        offset_bps = int(offset_raw)
    elif isinstance(offset_raw, str):
        try:
            offset_bps = int(float(offset_raw))
        except ValueError:
            LOG.warning(
                "Invalid offset_bps '%s' in trading.execution.manage.brackets", offset_raw
            )

    return ResolvedBrackets(
        sl_bps=sl_bps,
        tp_bps=tp_bps,
        offset_bps=offset_bps,
        sl_source=sl_source,
        tp_source=tp_source,
        source="legacy",
    )


def _build_brackets_from_v2(v2_cfg: Dict[str, Any], symbol: Optional[str] = None) -> ResolvedBrackets:
    """Build brackets from v2 config."""
    sl_bps = DEFAULT_SL_BPS
    tp_bps = DEFAULT_TP_BPS
    sl_source = "default"
    tp_source = "default"

    sl_cfg = v2_cfg.get("sl", {})
    sl_fixed_raw = sl_cfg.get("fixed_bps")
    if sl_fixed_raw is not None:
        sl_fixed = _coerce_decimal(sl_fixed_raw)
        if sl_fixed is None:
            raise ValueError(f"Invalid sl.fixed_bps value: {sl_fixed_raw}")
        sl_bps = sl_fixed
        sl_source = "sl.fixed_bps"

    tp_cfg = v2_cfg.get("tp", {})
    tp_fixed_raw = tp_cfg.get("fixed_bps")
    if tp_fixed_raw is not None:
        tp_fixed = _coerce_decimal(tp_fixed_raw)
        if tp_fixed is None:
            raise ValueError(f"Invalid tp.fixed_bps value: {tp_fixed_raw}")
        tp_bps = tp_fixed
        tp_source = "tp.fixed_bps"

    offset_raw = v2_cfg.get("offset_bps")
    offset_bps = DEFAULT_OFFSET_BPS
    if offset_raw is not None:
        if isinstance(offset_raw, (int, float)):
            offset_bps = int(offset_raw)
        elif isinstance(offset_raw, str):
            try:
                offset_bps = int(float(offset_raw))
            except ValueError:
                raise ValueError(f"Invalid offset_bps value: {offset_raw}")
        else:
            raise ValueError(f"Invalid offset_bps type: {type(offset_raw)}")

    return ResolvedBrackets(
        sl_bps=sl_bps,
        tp_bps=tp_bps,
        offset_bps=offset_bps,
        sl_source=sl_source,
        tp_source=tp_source,
        source="config_v2",
    )


def resolve_brackets_config(config: Any, *, symbol: Optional[str] = None) -> ResolvedBrackets:
    """Resolve TP/SL basis points and offset_bps from trading config.

    Precedence rules (per task spec):
    1. Canonical keys `sl.fixed_bps` / `tp.fixed_bps` / `offset_bps`.
    2. Legacy `stop_loss_bps`, `take_profit_high_ratio`, `take_profit_low_ratio`.
    3. Defaults (50/100/5) if nothing configured.
    """

    v2_cfg = _get_v2_execution_brackets_cfg(config)
    if v2_cfg is not None:
        try:
            return _build_brackets_from_v2(v2_cfg, symbol)
        except Exception as e:
            LOG.warning(
                "Failed to build brackets config from v2, falling back to legacy: %s", e)
            return _build_brackets_from_legacy(config, symbol)
    else:
        return _build_brackets_from_legacy(config, symbol)
