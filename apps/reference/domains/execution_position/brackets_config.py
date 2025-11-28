"""Brackets configuration resolver for execution_position domain.

This helper centralises TP/SL resolution so that:
- ManageFlowFSM (`fsm_manage.py`), ExecPosFSM (`fsm.py`), and DecisionMaking
  share the same precedence rules.
- Canonical keys (`sl.fixed_bps`, `tp.fixed_bps`, `offset_bps`) under
  `config_v2.domains.execution.brackets` serve as the single source of truth.

The resolver works with both dict configs and Pydantic `AuroraConfig` models
without mutating the original structure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

LOG = logging.getLogger(__name__)

_BRACKETS_WARNING_CACHE: set[str] = set()


def clear_brackets_warning_cache() -> None:
    """Reset warning cache to allow emitting warnings again (testing helper)."""

    _BRACKETS_WARNING_CACHE.clear()


def _warn_once(key: str, message: str) -> None:
    if key in _BRACKETS_WARNING_CACHE:
        return
    _BRACKETS_WARNING_CACHE.add(key)
    LOG.warning(message)


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

    execution_domain = _ensure_mapping(
        _pluck(cfg, "config_v2", "domains", "execution")
    )
    if not execution_domain:
        return None

    primary_cfg = _ensure_mapping(execution_domain.get("brackets"))
    if primary_cfg is not None:
        return primary_cfg

    fallback_cfg = _ensure_mapping(
        _pluck(execution_domain, "manage", "brackets")
    )
    if fallback_cfg is not None:
        _warn_once(
            "config_v2_manage_brackets",
            "execution.manage.brackets detected under config_v2; migrate to execution.brackets",
        )
        return fallback_cfg

    return None


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


@dataclass(frozen=True)
class ResolvedBrackets:
    sl_bps: Decimal
    tp_bps: Decimal
    offset_bps: int
    sl_source: str
    tp_source: str
    source: str = "config_v2"


DEFAULT_SL_BPS = Decimal("50")
DEFAULT_TP_BPS = Decimal("100")
DEFAULT_OFFSET_BPS = 5


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
    """Resolve TP/SL basis points and offset_bps from the execution domain config."""

    v2_cfg = _get_v2_execution_brackets_cfg(config)
    if v2_cfg:
        try:
            return _build_brackets_from_v2(v2_cfg, symbol)
        except ValueError as exc:
            LOG.warning(
                "Failed to build execution.brackets from config_v2: %s",
                exc,
            )
            raise

    # Fallback to defaults if no config found, but warn
    LOG.debug(
        "execution.brackets config missing; using defaults for symbol=%s",
        symbol,
    )
    return _build_brackets_from_v2({}, symbol)
