# -*- coding: utf-8 -*-
"""Execution manage configuration resolver.

Centralises reads of ``trading.execution.manage.*`` so runtime code avoids
navigating raw config structures. Mirrors the approach used by
``brackets_config`` for TP/SL values, but focuses on manage metadata
(orphan monitor, quick profit, trailing, emergency, brackets flags, etc.).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

from vfoundation.errors import ConfigError

LOG = logging.getLogger(__name__)

_MANAGE_CACHE: Dict[int, Tuple[Any, "ExecutionManageConfig"]] = {}
_ALLOWED_MANAGE_MODES = {"legacy", "aggregated_only"}


def _get_v2_execution_manage_cfg(cfg: Any) -> Optional[Dict[str, Any]]:
    """
    Повертає manage-конфіг із cfg.config_v2.domains["execution"]["manage"], якщо він існує і не порожній.
    Інакше повертає None.
    """
    # Check if cfg is AuroraConfig with config_v2
    config_v2 = None
    if hasattr(cfg, 'config_v2'):
        config_v2 = getattr(cfg, 'config_v2')
    elif isinstance(cfg, dict):
        config_v2 = cfg.get('config_v2')
    if config_v2 is None:
        return None
    domains = getattr(config_v2, 'domains', None)
    if domains is None and isinstance(config_v2, dict):
        domains = config_v2.get('domains')
    if domains is None:
        return None
    if isinstance(domains, dict):
        execution_domain = domains.get("execution")
    else:
        execution_domain = getattr(domains, "execution", None)
    if execution_domain is None:
        return None
    if isinstance(execution_domain, dict):
        manage_cfg = execution_domain.get("manage")
    else:
        manage_cfg = getattr(execution_domain, "manage", None)
    if manage_cfg is None:
        return None
    if hasattr(manage_cfg, "model_dump"):
        try:
            manage_cfg = manage_cfg.model_dump()
        except Exception:
            manage_cfg = None
    if isinstance(manage_cfg, dict) and manage_cfg:
        return manage_cfg
    return None


def _strict_coerce_decimal(value: Any, default: Decimal) -> Decimal:
    """Coerce to Decimal, but raise ValueError on invalid input instead of returning default."""
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            raise ValueError(
                f"Cannot parse decimal from string value '{value}'")
    raise ValueError(f"Invalid type for decimal: {type(value)}")


def _pluck(obj: Any, *path: str) -> Any:
    """Traverse nested dict / object attributes safely."""
    current = obj
    for key in path:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(key)
            continue
        try:
            current = getattr(current, key)
        except AttributeError:
            return None
    return current


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    try:
        return bool(value)
    except Exception:
        return default


def _coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):  # guard: bool is subclass of int
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _coerce_decimal(value: Any, default: Decimal) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            return default
    return default


def _coerce_sequence(values: Any) -> Tuple[int, ...]:
    if values is None:
        return ()
    if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
        result = []
        for item in values:
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
        return tuple(result)
    try:
        return (int(values),)
    except (TypeError, ValueError):
        return ()


def _extract_manage_node(config: Any) -> Any:
    node = _pluck(config, "trading", "execution", "manage")
    if node is not None:
        return node
    fallback = _pluck(config, "execution", "manage")
    if fallback is not None:
        LOG.debug("Using legacy execution.manage fallback for manage config")
    return fallback or {}


@dataclass(frozen=True)
class OrphanMonitorConfig:
    enabled: bool = True
    run_on_startup: bool = True
    periodic_interval_sec: int = 300
    min_order_age_sec: int = 0
    batch_cancel_limit: int = 50
    rate_limit_per_min: int = 120


@dataclass(frozen=True)
class QuickProfitConfig:
    enabled: bool = False
    mode: str = "fixed_usd"
    target_usd: Decimal = Decimal("2.0")
    priority: str = "highest"
    ignore_other_rules: bool = False


@dataclass(frozen=True)
class TrailingConfig:
    enabled: bool = False
    activation_profit_atr_k: float = 1.0
    cooldown_sec: float = 0.0
    step_bps: Decimal = Decimal("0")


@dataclass(frozen=True)
class EmergencyConfig:
    enabled: bool = False
    sl_bps: Decimal = Decimal("100")
    wait_mode_bars: int = 2


@dataclass(frozen=True)
class AggregatedOcoWatchdogConfig:
    enabled: bool = False
    interval_sec: int = 5
    auto_heal_orphans: bool = True


@dataclass(frozen=True)
class AggregatedOcoConfig:
    enabled: bool = False
    aggregated_only_mode: bool = False
    recalc_on_scale_in: bool = True
    recalc_on_partial_close: bool = False
    ttl_protect_new_bracket_ms: int = 3000
    allow_unprotected_position: bool = False
    watchdog: AggregatedOcoWatchdogConfig = field(
        default_factory=AggregatedOcoWatchdogConfig
    )


@dataclass(frozen=True)
class BracketsMetaConfig:
    enable: bool = False
    oco_emulation: bool = False
    working_type_default: str = "MARK_PRICE"
    price_protect: bool = False
    keep_single_bracket_set: bool = True
    atomic_close: bool = True
    bracket_tracking: bool = True
    retry_backoff_ms: Tuple[int, ...] = (120, 250, 400)
    retry_max_attempts: int = 3
    retry_fallback_to_limit: bool = True
    aggregated_oco: AggregatedOcoConfig = AggregatedOcoConfig()


@dataclass(frozen=True)
class WsSnapshotConfig:
    enabled: bool = False
    max_age_ms: int = 1500
    rest_fallback_enabled: bool = True


@dataclass(frozen=True)
class PositionsConfig:
    ws_snapshot: WsSnapshotConfig = WsSnapshotConfig()


@dataclass(frozen=True)
class GuardianConfig:
    unified: bool = True
    emit_tidy_event: bool = True
    poll_interval_ms: int = 500
    cleanup_ttl_ms: int = 6000
    symbol_cooldown_ms: int = 4000


@dataclass(frozen=True)
class WatchdogConfig:
    ack_ttl_ms: int = 8000
    fill_ttl_ms: int = 30000
    check_interval_ms: int = 1000
    source: str = "execution.watchdog"


@dataclass(frozen=True)
class ExecutionManageConfig:
    auto: bool
    orphan_monitor: OrphanMonitorConfig
    quick_profit: QuickProfitConfig
    trailing: TrailingConfig
    emergency: EmergencyConfig
    brackets: BracketsMetaConfig
    guardian: GuardianConfig
    watchdog: WatchdogConfig
    positions: PositionsConfig
    source: str = "legacy"
    mode: str = "legacy"


def _resolve_orphan_monitor(node: Any) -> OrphanMonitorConfig:
    cfg = _pluck(node, "orphan_monitor") or {}
    return OrphanMonitorConfig(
        enabled=_coerce_bool(_pluck(cfg, "enabled"), True),
        run_on_startup=_coerce_bool(_pluck(cfg, "run_on_startup"), True),
        periodic_interval_sec=_coerce_int(
            _pluck(cfg, "periodic_interval_sec"), 300),
        min_order_age_sec=_coerce_int(_pluck(cfg, "min_order_age_sec"), 0),
        batch_cancel_limit=_coerce_int(_pluck(cfg, "batch_cancel_limit"), 50),
        rate_limit_per_min=_coerce_int(_pluck(cfg, "rate_limit_per_min"), 120),
    )


def _resolve_quick_profit(node: Any) -> QuickProfitConfig:
    qp_node = _pluck(node, "quick_profit")
    if qp_node is None:
        qp_node = _pluck(node, "brackets", "quick_profit")
        if qp_node is not None:
            LOG.debug(
                "Using brackets.quick_profit fallback for manage quick profit config")
    qp_node = qp_node or {}
    return QuickProfitConfig(
        enabled=_coerce_bool(_pluck(qp_node, "enabled"), False),
        mode=str(_pluck(qp_node, "mode") or "fixed_usd"),
        target_usd=_coerce_decimal(
            _pluck(qp_node, "target_usd"), Decimal("2.0")),
        priority=str(_pluck(qp_node, "priority") or "highest"),
        ignore_other_rules=_coerce_bool(
            _pluck(qp_node, "ignore_other_rules"), False),
    )


def _resolve_trailing(node: Any) -> TrailingConfig:
    trailing_node = _pluck(node, "trailing") or {}
    return TrailingConfig(
        enabled=_coerce_bool(_pluck(trailing_node, "enable"), False),
        activation_profit_atr_k=float(
            _pluck(trailing_node, "activation_profit_atr_k") or 1.0),
        cooldown_sec=float(_pluck(trailing_node, "cooldown_sec") or 0.0),
        step_bps=_coerce_decimal(
            _pluck(trailing_node, "step_bps"), Decimal("0")),
    )


def _resolve_emergency(node: Any) -> EmergencyConfig:
    emergency_node = _pluck(node, "emergency") or {}
    return EmergencyConfig(
        enabled=_coerce_bool(_pluck(emergency_node, "enable"), False),
        sl_bps=_coerce_decimal(
            _pluck(emergency_node, "emergency_sl_bps"), Decimal("100")),
        wait_mode_bars=_coerce_int(
            _pluck(emergency_node, "wait_mode_bars"), 2),
    )


def _resolve_brackets_meta(config: Any, manage_node: Any) -> BracketsMetaConfig:
    brackets_node = _pluck(manage_node, "brackets")
    if brackets_node is None:
        # Legacy path: trading.execution.brackets*
        brackets_node = _pluck(
            config, "trading", "execution", "brackets") or {}
        if brackets_node:
            LOG.debug(
                "Using trading.execution.brackets fallback for manage.brackets metadata")
        else:
            brackets_node = {}

    retry_node = _pluck(brackets_node, "retry") or {}
    retry_backoff = _coerce_sequence(_pluck(retry_node, "backoff_ms"))
    if not retry_backoff:
        retry_backoff = (120, 250, 400)

    return BracketsMetaConfig(
        enable=_coerce_bool(_pluck(brackets_node, "enable"), False),
        oco_emulation=_coerce_bool(
            _pluck(brackets_node, "oco_emulation"), False),
        working_type_default=str(
            _pluck(brackets_node, "working_type_default") or "MARK_PRICE"),
        price_protect=_coerce_bool(
            _pluck(brackets_node, "price_protect"), False),
        keep_single_bracket_set=_coerce_bool(
            _pluck(brackets_node, "keep_single_bracket_set"), True),
        atomic_close=_coerce_bool(_pluck(brackets_node, "atomic_close"), True),
        bracket_tracking=_coerce_bool(
            _pluck(brackets_node, "bracket_tracking"), True),
        retry_backoff_ms=retry_backoff,
        retry_max_attempts=_coerce_int(_pluck(retry_node, "max_attempts"), 3),
        retry_fallback_to_limit=_coerce_bool(
            _pluck(retry_node, "fallback_to_limit"), True),
        aggregated_oco=_resolve_aggregated_oco(brackets_node),
    )


def _resolve_aggregated_oco(brackets_node: Any) -> AggregatedOcoConfig:
    agg_node = _pluck(brackets_node, "aggregated_oco") or {}
    return AggregatedOcoConfig(
        enabled=_coerce_bool(_pluck(agg_node, "enabled"), False),
        aggregated_only_mode=_coerce_bool(
            _pluck(agg_node, "aggregated_only_mode"), False
        ),
        recalc_on_scale_in=_coerce_bool(
            _pluck(agg_node, "recalc_on_scale_in"), True),
        recalc_on_partial_close=_coerce_bool(
            _pluck(agg_node, "recalc_on_partial_close"), False),
        ttl_protect_new_bracket_ms=_coerce_int(
            _pluck(agg_node, "ttl_protect_new_bracket_ms"), 3000),
        allow_unprotected_position=_coerce_bool(
            _pluck(agg_node, "allow_unprotected_position"), False),
        watchdog=_resolve_aggregated_watchdog(agg_node),
    )


def _resolve_aggregated_watchdog(node: Any) -> AggregatedOcoWatchdogConfig:
    watch_node = _pluck(node, "watchdog") if node else None
    if watch_node is None and node:
        try:
            watch_node = getattr(node, "watchdog")
        except Exception:
            watch_node = None
    watch_node = watch_node or {}
    return AggregatedOcoWatchdogConfig(
        enabled=_coerce_bool(_pluck(watch_node, "enabled"), False),
        interval_sec=_coerce_int(_pluck(watch_node, "interval_sec"), 5),
        auto_heal_orphans=_coerce_bool(
            _pluck(watch_node, "auto_heal_orphans"), True
        ),
    )


def _resolve_guardian(config: Any, manage_node: Any) -> GuardianConfig:
    resolved: Dict[str, Any] = {
        "unified": True,
        "emit_tidy_event": True,
        "poll_interval_ms": 500,
        "cleanup_ttl_ms": 6000,
        "symbol_cooldown_ms": 4000,
    }

    def _update_from(source: Any) -> None:
        if not source:
            return
        keys = (
            "unified",
            "emit_tidy_event",
            "poll_interval_ms",
            "cleanup_ttl_ms",
            "symbol_cooldown_ms",
        )
        if isinstance(source, dict):
            for key in keys:
                value = source.get(key)
                if value is not None:
                    resolved[key] = value
        else:
            for key in keys:
                try:
                    value = getattr(source, key)
                except Exception:
                    value = None
                if value is not None:
                    resolved[key] = value

    _update_from(_pluck(manage_node, "order_guardian"))
    _update_from(_pluck(config, "trading", "execution", "order_guardian"))
    _update_from(_pluck(config, "execution", "order_guardian"))
    _update_from(_pluck(config, "guardian"))

    return GuardianConfig(
        unified=_coerce_bool(resolved.get("unified"), True),
        emit_tidy_event=_coerce_bool(resolved.get("emit_tidy_event"), True),
        poll_interval_ms=_coerce_int(resolved.get("poll_interval_ms"), 500),
        cleanup_ttl_ms=_coerce_int(resolved.get("cleanup_ttl_ms"), 6000),
        symbol_cooldown_ms=_coerce_int(
            resolved.get("symbol_cooldown_ms"), 4000),
    )


def _resolve_watchdog(config: Any, manage_node: Any) -> WatchdogConfig:
    node = _pluck(manage_node, "watchdog")
    source = "trading.execution.manage.watchdog"
    if node is None:
        node = _pluck(config, "execution", "watchdog")
        source = "execution.watchdog"
    if node is None:
        node = _pluck(config, "trading", "watchdog")
        source = "trading.watchdog"
    if node is None:
        source = "defaults"

    ack_ttl_ms = _coerce_int(_pluck(node, "ack_ttl_ms"), 8000)
    fill_ttl_ms = _coerce_int(_pluck(node, "fill_ttl_ms"), 30000)
    check_interval_ms = _coerce_int(
        _pluck(node, "check_interval_ms"), 1000)

    # Optional override from trading.orders.default_ttl_seconds (Balanced profile)
    orders_cfg = _pluck(config, "trading", "orders")
    if orders_cfg is None:
        orders_cfg = _pluck(config, "orders")
    default_ttl_seconds = None
    if isinstance(orders_cfg, dict):
        default_ttl_seconds = orders_cfg.get("default_ttl_seconds")
    else:
        try:
            default_ttl_seconds = getattr(
                orders_cfg, "default_ttl_seconds", None)
        except Exception:
            default_ttl_seconds = None
    if default_ttl_seconds is not None:
        try:
            fill_ttl_ms = _coerce_int(
                int(default_ttl_seconds) * 1000, fill_ttl_ms)
            source = "trading.orders.default_ttl_seconds"
        except Exception:
            LOG.debug(
                "Failed to coerce default_ttl_seconds override", exc_info=True)

    return WatchdogConfig(
        ack_ttl_ms=ack_ttl_ms,
        fill_ttl_ms=fill_ttl_ms,
        check_interval_ms=check_interval_ms,
        source=source,
    )


def _resolve_ws_snapshot(node: Any) -> WsSnapshotConfig:
    ws_node = _pluck(node, "ws_snapshot") if node is not None else None
    if ws_node is None and node is not None:
        try:
            ws_node = getattr(node, "ws_snapshot")
        except Exception:
            ws_node = None
    ws_node = ws_node or {}
    return WsSnapshotConfig(
        enabled=_coerce_bool(_pluck(ws_node, "enabled"), False),
        max_age_ms=_coerce_int(_pluck(ws_node, "max_age_ms"), 1500),
        rest_fallback_enabled=_coerce_bool(
            _pluck(ws_node, "rest_fallback_enabled"), True
        ),
    )


def _resolve_positions_config(config: Any, manage_node: Any) -> PositionsConfig:
    node = _pluck(manage_node, "positions") if manage_node else None
    if node is None:
        node = _pluck(config, "execution", "positions")
    if node is None:
        node = _pluck(config, "trading", "execution", "positions")
    return PositionsConfig(ws_snapshot=_resolve_ws_snapshot(node))


def _resolve_positions_from_v2(v2_cfg: Dict[str, Any]) -> PositionsConfig:
    node = v2_cfg.get("positions") or {}
    return PositionsConfig(ws_snapshot=_resolve_ws_snapshot(node))


def _normalize_manage_mode(raw_mode: Any, agg_cfg: AggregatedOcoConfig) -> str:
    candidate: Optional[str]
    if raw_mode is None:
        candidate = None
    else:
        if isinstance(raw_mode, str):
            candidate = raw_mode.strip().lower()
        else:
            candidate = str(raw_mode).strip().lower()
    if not candidate:
        candidate = "aggregated_only" if (
            agg_cfg.enabled and agg_cfg.aggregated_only_mode
        ) else "legacy"
    if candidate not in _ALLOWED_MANAGE_MODES:
        raise ConfigError(
            f"Unknown execution.manage.mode '{candidate}' (allowed: {_ALLOWED_MANAGE_MODES})"
        )
    _validate_manage_mode(candidate, agg_cfg)
    return candidate


def _validate_manage_mode(mode: str, agg_cfg: AggregatedOcoConfig) -> None:
    if mode == "legacy":
        if agg_cfg.enabled or agg_cfg.aggregated_only_mode:
            raise ConfigError(
                "mode=legacy requires aggregated_oco.enabled=false and aggregated_only_mode=false"
            )
        if getattr(agg_cfg.watchdog, "enabled", False):
            raise ConfigError(
                "mode=legacy does not support aggregated_oco.watchdog.enabled=true"
            )
        return

    # aggregated_only mode validations
    if not agg_cfg.enabled:
        raise ConfigError(
            "mode=aggregated_only requires aggregated_oco.enabled=true"
        )
    if not agg_cfg.aggregated_only_mode:
        raise ConfigError(
            "aggregated_only mode requires aggregated_only_mode=true"
        )
    if agg_cfg.allow_unprotected_position:
        raise ConfigError(
            "aggregated_only mode forbids allow_unprotected_position=true"
        )
    if not agg_cfg.recalc_on_partial_close:
        raise ConfigError(
            "aggregated_only mode requires recalc_on_partial_close=true"
        )


def _build_manage_from_legacy(config: Any) -> ExecutionManageConfig:
    manage_node = _extract_manage_node(config)

    brackets_meta = _resolve_brackets_meta(config, manage_node)
    mode = _normalize_manage_mode(_pluck(manage_node, "mode"),
                                  brackets_meta.aggregated_oco)

    return ExecutionManageConfig(
        auto=_coerce_bool(_pluck(manage_node, "auto"), False),
        orphan_monitor=_resolve_orphan_monitor(manage_node),
        quick_profit=_resolve_quick_profit(manage_node),
        trailing=_resolve_trailing(manage_node),
        emergency=_resolve_emergency(manage_node),
        brackets=brackets_meta,
        guardian=_resolve_guardian(config, manage_node),
        watchdog=_resolve_watchdog(config, manage_node),
        positions=_resolve_positions_config(config, manage_node),
        source="legacy",
        mode=mode,
    )


def _build_manage_from_v2(v2_cfg: Dict[str, Any], cfg: Any) -> ExecutionManageConfig:
    # Для v2, читаємо безпосередньо з v2_cfg
    # Якщо поле відсутнє, використовуємо дефолти з моделей або кидаємо виняток для критичних
    try:
        brackets_meta = _resolve_brackets_meta_from_v2(v2_cfg)
        mode = _normalize_manage_mode(
            v2_cfg.get("mode"), brackets_meta.aggregated_oco
        )
        return ExecutionManageConfig(
            auto=_coerce_bool(v2_cfg.get("auto"), False),
            orphan_monitor=_resolve_orphan_monitor(v2_cfg),
            quick_profit=_resolve_quick_profit_from_v2(v2_cfg),
            trailing=_resolve_trailing(v2_cfg),
            emergency=_resolve_emergency(v2_cfg),
            brackets=brackets_meta,
            guardian=_resolve_guardian_from_v2(v2_cfg),
            watchdog=_resolve_watchdog_from_v2(v2_cfg),
            positions=_resolve_positions_from_v2(v2_cfg),
            source="config_v2",
            mode=mode,
        )
    except ConfigError:
        raise
    except Exception as e:
        raise ValueError(f"Invalid v2 manage config: {e}") from e


def _resolve_quick_profit_from_v2(v2_cfg: Dict[str, Any]) -> QuickProfitConfig:
    qp_node = v2_cfg.get("quick_profit", {})
    enabled = _coerce_bool(qp_node.get("enabled"), False)
    mode = str(qp_node.get("mode") or "fixed_usd")
    target_usd_raw = qp_node.get("target_usd")
    if target_usd_raw is not None:
        target_usd = _strict_coerce_decimal(target_usd_raw, Decimal("2.0"))
    else:
        target_usd = Decimal("2.0")
    priority = str(qp_node.get("priority") or "highest")
    ignore_other_rules = _coerce_bool(qp_node.get("ignore_other_rules"), False)
    return QuickProfitConfig(
        enabled=enabled,
        mode=mode,
        target_usd=target_usd,
        priority=priority,
        ignore_other_rules=ignore_other_rules,
    )


def _resolve_brackets_meta_from_v2(v2_cfg: Dict[str, Any]) -> BracketsMetaConfig:
    brackets_node = v2_cfg.get("brackets", {})

    retry_node = brackets_node.get("retry", {})
    retry_backoff = _coerce_sequence(retry_node.get("backoff_ms"))
    if not retry_backoff:
        retry_backoff = (120, 250, 400)

    return BracketsMetaConfig(
        enable=_coerce_bool(brackets_node.get("enable"), False),
        oco_emulation=_coerce_bool(brackets_node.get("oco_emulation"), False),
        working_type_default=str(brackets_node.get(
            "working_type_default") or "MARK_PRICE"),
        price_protect=_coerce_bool(brackets_node.get("price_protect"), False),
        keep_single_bracket_set=_coerce_bool(
            brackets_node.get("keep_single_bracket_set"), True),
        atomic_close=_coerce_bool(brackets_node.get("atomic_close"), True),
        bracket_tracking=_coerce_bool(
            brackets_node.get("bracket_tracking"), True),
        retry_backoff_ms=retry_backoff,
        retry_max_attempts=_coerce_int(retry_node.get("max_attempts"), 3),
        retry_fallback_to_limit=_coerce_bool(
            retry_node.get("fallback_to_limit"), True),
        aggregated_oco=_resolve_aggregated_oco_from_v2(brackets_node),
    )


def _resolve_aggregated_oco_from_v2(brackets_node: Dict[str, Any]) -> AggregatedOcoConfig:
    agg_node = brackets_node.get("aggregated_oco", {})
    return AggregatedOcoConfig(
        enabled=_coerce_bool(agg_node.get("enabled"), False),
        aggregated_only_mode=_coerce_bool(
            agg_node.get("aggregated_only_mode"), False
        ),
        recalc_on_scale_in=_coerce_bool(
            agg_node.get("recalc_on_scale_in"), True
        ),
        recalc_on_partial_close=_coerce_bool(
            agg_node.get("recalc_on_partial_close"), False
        ),
        ttl_protect_new_bracket_ms=_coerce_int(
            agg_node.get("ttl_protect_new_bracket_ms"), 3000
        ),
        allow_unprotected_position=_coerce_bool(
            agg_node.get("allow_unprotected_position"), False
        ),
        watchdog=_resolve_aggregated_watchdog(agg_node),
    )


def _resolve_guardian_from_v2(v2_cfg: Dict[str, Any]) -> GuardianConfig:
    guardian_node = v2_cfg.get("guardian", {})
    return GuardianConfig(
        unified=_coerce_bool(guardian_node.get("unified"), True),
        emit_tidy_event=_coerce_bool(
            guardian_node.get("emit_tidy_event"), True),
        poll_interval_ms=_coerce_int(
            guardian_node.get("poll_interval_ms"), 500),
        cleanup_ttl_ms=_coerce_int(guardian_node.get("cleanup_ttl_ms"), 6000),
        symbol_cooldown_ms=_coerce_int(
            guardian_node.get("symbol_cooldown_ms"), 4000),
    )


def _resolve_watchdog_from_v2(v2_cfg: Dict[str, Any]) -> WatchdogConfig:
    watchdog_node = v2_cfg.get("watchdog", {})
    return WatchdogConfig(
        ack_ttl_ms=_coerce_int(watchdog_node.get("ack_ttl_ms"), 8000),
        fill_ttl_ms=_coerce_int(watchdog_node.get("fill_ttl_ms"), 30000),
        check_interval_ms=_coerce_int(
            watchdog_node.get("check_interval_ms"), 1000),
        source="config_v2",
    )


def resolve_execution_manage_config(config: Any) -> ExecutionManageConfig:
    cache_key = id(config)
    cached = _MANAGE_CACHE.get(cache_key)
    if cached is not None:
        cached_config, cached_value = cached
        if cached_config is config:
            return cached_value
        # id() reused for a different object; purge stale entry
        _MANAGE_CACHE.pop(cache_key, None)

    v2_cfg = _get_v2_execution_manage_cfg(config)
    if v2_cfg is not None:
        try:
            resolved = _build_manage_from_v2(v2_cfg, config)
        except ConfigError:
            raise
        except Exception as e:
            LOG.warning(
                "Failed to build manage config from v2, falling back to legacy: %s", e)
            resolved = _build_manage_from_legacy(config)
    else:
        resolved = _build_manage_from_legacy(config)

    _MANAGE_CACHE[cache_key] = (config, resolved)
    return resolved


def clear_manage_config_cache() -> None:
    """Utility for tests to clear the resolver cache."""
    _MANAGE_CACHE.clear()
