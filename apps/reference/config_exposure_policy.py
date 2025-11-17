"""Centralized resolver for trading execution exposure policy.

Provides normalized dataclasses for exposure caps, leverage defaults, pending
reservation TTLs, and fallback behavior. Consumers should rely on this module
instead of reaching into raw configuration structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Mapping, Tuple, Optional, Literal


def _pluck(node: Any, key: str, default: Any = None) -> Any:
    """Safely extract a key/attribute from dicts or objects."""
    if node is None:
        return default
    if isinstance(node, Mapping):
        return node.get(key, default)
    if hasattr(node, key):
        try:
            return getattr(node, key)
        except AttributeError:
            return default
    if hasattr(node, "get"):
        try:
            return node.get(key, default)
        except Exception:  # pragma: no cover - defensive
            return default
    return default


def _coerce_decimal(value: Any, fallback: Decimal) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(fallback))


def _normalize_pct(value: Any, fallback: str) -> Decimal:
    """Convert percent-style config values to ratio decimals."""
    candidate = _coerce_decimal(
        value if value is not None else fallback, Decimal(fallback))
    if candidate < Decimal("0"):
        return Decimal(fallback)
    if candidate <= Decimal("1"):
        return candidate
    return candidate / Decimal("100")


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        return fallback
    if isinstance(value, (int, float)):
        return bool(value)
    return fallback


def _pluck_multi(node: Any, keys: Tuple[str, ...], default: Any = None) -> Any:
    """Return first non-None value for provided keys using _pluck semantics."""
    for key in keys:
        value = _pluck(node, key, None)
        if value is not None:
            return value
    return default


def _get_v2_execution_domain(cfg: Any) -> Optional[Mapping[str, Any]]:
    if cfg is None or not hasattr(cfg, 'config_v2') or cfg.config_v2 is None:
        return None
    domains = getattr(cfg.config_v2, 'domains', None)
    if not isinstance(domains, Mapping):
        return None
    execution_domain = domains.get("execution")
    if not isinstance(execution_domain, Mapping) or not execution_domain:
        return None
    return execution_domain


def _get_v2_exposure_config(cfg: Any) -> Optional[Mapping[str, Any]]:
    """
    Повертає exposure-конфіг з config_v2.domains["execution"], якщо він є і непорожній.
    Якщо v2-конфігу немає або в ньому відсутній блок exposure — повертає None.
    """
    execution_domain = _get_v2_execution_domain(cfg)
    if execution_domain is None:
        return None
    exposure_cfg = execution_domain.get("exposure")
    if not isinstance(exposure_cfg, Mapping) or not exposure_cfg:
        return None
    return exposure_cfg


@dataclass(frozen=True)
class ExposureCaps:
    max_equity_utilization_ratio: Decimal
    max_portfolio_fraction: Decimal
    max_directional_ratio: Decimal
    max_side_utilization_ratio: Dict[str, Decimal]
    per_symbol_cap_ratio: Decimal


@dataclass(frozen=True)
class PendingReservations:
    pending_ttl_sec: int
    post_fill_hold_ttl_sec: int
    positions_stale_ttl_sec: int


@dataclass(frozen=True)
class LeverageDefaults:
    default: Decimal
    per_symbol: Dict[str, Decimal] = field(default_factory=dict)

    def resolve_for(self, symbol: str) -> Decimal:
        return self.per_symbol.get(symbol, self.default)


@dataclass(frozen=True)
class FallbackConfig:
    policy: str
    risk_reduction_pct: Decimal
    backoff_ms: Tuple[int, ...]
    max_attempts: int
    enabled: bool

    def backoff_sequence(self) -> Tuple[int, ...]:
        return self.backoff_ms


@dataclass(frozen=True)
class ExposurePolicy:
    caps: ExposureCaps
    reservations: PendingReservations
    leverage_defaults: LeverageDefaults
    count_pending_orders: bool
    exclude_reduce_only: bool
    fallback: FallbackConfig
    source: Literal["legacy", "config_v2"] = "legacy"


def _build_policy_from_legacy(config: Any) -> ExposurePolicy:
    """Build ExposurePolicy from legacy config paths."""
    trading = _pluck(config, "trading", {})
    execution = _pluck(trading, "execution", {})
    exposure_cfg = _pluck(execution, "exposure", {})

    max_equity = _normalize_pct(
        _pluck(exposure_cfg, "max_equity_utilization_pct", "0.20"),
        "0.20",
    )
    max_portfolio_fraction = _coerce_decimal(
        _pluck(exposure_cfg, "max_portfolio_fraction", "0.20"),
        Decimal("0.20"),
    )
    max_directional_ratio = _coerce_decimal(
        _pluck(exposure_cfg, "max_directional_ratio", "2.0"),
        Decimal("2.0"),
    )
    side_cfg = _pluck(exposure_cfg, "max_side_utilization_pct", {}) or {}
    max_side_long = _normalize_pct(_pluck(side_cfg, "long", "0.12"), "0.12")
    max_side_short = _normalize_pct(_pluck(side_cfg, "short", "0.12"), "0.12")
    per_symbol_cap = _normalize_pct(
        _pluck(exposure_cfg, "per_symbol_cap_pct", "0.08"),
        "0.08",
    )

    caps = ExposureCaps(
        max_equity_utilization_ratio=max_equity,
        max_portfolio_fraction=max_portfolio_fraction,
        max_directional_ratio=max_directional_ratio,
        max_side_utilization_ratio={
            "long": max_side_long,
            "short": max_side_short,
        },
        per_symbol_cap_ratio=per_symbol_cap,
    )

    reservations = PendingReservations(
        pending_ttl_sec=_coerce_int(
            _pluck_multi(
                exposure_cfg,
                ("pending_ttl_sec", "pending_reservation_ttl_sec"),
                90,
            ),
            90,
        ),
        post_fill_hold_ttl_sec=_coerce_int(
            _pluck_multi(
                exposure_cfg,
                ("post_fill_hold_ttl_sec", "post_fill_pending_hold_ttl_sec"),
                5,
            ),
            5,
        ),
        positions_stale_ttl_sec=_coerce_int(
            _pluck_multi(
                exposure_cfg,
                ("positions_stale_ttl_sec", "positions_stale_ttl"),
                5,
            ),
            5,
        ),
    )

    count_pending_orders = _coerce_bool(
        _pluck(exposure_cfg, "count_pending_orders", True), True
    )
    exclude_reduce_only = _coerce_bool(
        _pluck(exposure_cfg, "exclude_reduce_only", True), True
    )

    leverage_cfg = _pluck(exposure_cfg, "leverage_defaults", {}) or {}
    default_leverage_raw = (
        _pluck(leverage_cfg, "default")
        or _pluck(leverage_cfg, "__default__")
        or Decimal("20")
    )
    default_leverage = _coerce_decimal(default_leverage_raw, Decimal("20"))

    per_symbol: Dict[str, Decimal] = {}
    if isinstance(leverage_cfg, Mapping):
        for key, value in leverage_cfg.items():
            if key in {"default", "__default__"}:
                continue
            per_symbol[str(key)] = _coerce_decimal(value, default_leverage)
    elif hasattr(leverage_cfg, "__dict__"):
        for key, value in leverage_cfg.__dict__.items():
            if key.startswith("_") or key in {"default", "__default__"}:
                continue
            per_symbol[str(key)] = _coerce_decimal(value, default_leverage)

    leverage_defaults = LeverageDefaults(
        default=default_leverage,
        per_symbol=per_symbol,
    )

    fallback_cfg = _pluck(execution, "fallback", {}) or {}
    fallback_policy = str(_pluck(fallback_cfg, "policy",
                          "fail_closed") or "fail_closed")
    risk_reduction_raw = _pluck(fallback_cfg, "risk_reduction_pct", "0.5")
    risk_reduction_pct = _coerce_decimal(risk_reduction_raw, Decimal("0.5"))
    if risk_reduction_pct > Decimal("1"):
        risk_reduction_pct = risk_reduction_pct / Decimal("100")

    backoff_raw = _pluck(fallback_cfg, "backoff_ms", (200, 500, 1000))
    backoff_sequence: Tuple[int, ...]
    if isinstance(backoff_raw, (list, tuple)):
        filtered = []
        for item in backoff_raw:
            delay = _coerce_int(item, -1)
            if delay > 0:
                filtered.append(delay)
        backoff_sequence = tuple(filtered) if filtered else (200, 500, 1000)
    else:
        backoff_sequence = (200, 500, 1000)

    configured_max_attempts = _pluck(fallback_cfg, "max_attempts")
    if configured_max_attempts is None:
        max_attempts = len(backoff_sequence) + 1
    else:
        max_attempts = max(_coerce_int(
            configured_max_attempts, len(backoff_sequence) + 1), 1)

    enabled = _coerce_bool(_pluck(fallback_cfg, "enabled", True), True)

    fallback = FallbackConfig(
        policy=fallback_policy,
        risk_reduction_pct=risk_reduction_pct,
        backoff_ms=backoff_sequence,
        max_attempts=max_attempts,
        enabled=enabled,
    )

    return ExposurePolicy(
        caps=caps,
        reservations=reservations,
        leverage_defaults=leverage_defaults,
        count_pending_orders=count_pending_orders,
        exclude_reduce_only=exclude_reduce_only,
        fallback=fallback,
        source="legacy",
    )


def _build_policy_from_v2(
    v2_cfg: Mapping[str, Any],
    fallback_cfg: Optional[Mapping[str, Any]] = None,
) -> ExposurePolicy:
    """Build ExposurePolicy from config v2 exposure block."""
    if not isinstance(v2_cfg, Mapping):
        raise ValueError("v2 exposure config must be a dict")

    # Use the same logic as legacy but from v2_cfg directly
    max_equity = _normalize_pct(
        _pluck(v2_cfg, "max_equity_utilization_pct", "0.20"),
        "0.20",
    )
    max_portfolio_fraction = _coerce_decimal(
        _pluck(v2_cfg, "max_portfolio_fraction", "0.20"),
        Decimal("0.20"),
    )
    max_directional_ratio = _coerce_decimal(
        _pluck(v2_cfg, "max_directional_ratio", "2.0"),
        Decimal("2.0"),
    )
    side_cfg = _pluck(v2_cfg, "max_side_utilization_pct", {}) or {}
    max_side_long = _normalize_pct(_pluck(side_cfg, "long", "0.12"), "0.12")
    max_side_short = _normalize_pct(_pluck(side_cfg, "short", "0.12"), "0.12")
    per_symbol_cap = _normalize_pct(
        _pluck(v2_cfg, "per_symbol_cap_pct", "0.08"),
        "0.08",
    )

    caps = ExposureCaps(
        max_equity_utilization_ratio=max_equity,
        max_portfolio_fraction=max_portfolio_fraction,
        max_directional_ratio=max_directional_ratio,
        max_side_utilization_ratio={
            "long": max_side_long,
            "short": max_side_short,
        },
        per_symbol_cap_ratio=per_symbol_cap,
    )

    reservations = PendingReservations(
        pending_ttl_sec=_coerce_int(
            _pluck_multi(
                v2_cfg,
                ("pending_ttl_sec", "pending_reservation_ttl_sec"),
                90,
            ),
            90,
        ),
        post_fill_hold_ttl_sec=_coerce_int(
            _pluck_multi(
                v2_cfg,
                ("post_fill_hold_ttl_sec", "post_fill_pending_hold_ttl_sec"),
                5,
            ),
            5,
        ),
        positions_stale_ttl_sec=_coerce_int(
            _pluck_multi(
                v2_cfg,
                ("positions_stale_ttl_sec", "positions_stale_ttl"),
                5,
            ),
            5,
        ),
    )

    count_pending_orders = _coerce_bool(
        _pluck(v2_cfg, "count_pending_orders", True), True
    )
    exclude_reduce_only = _coerce_bool(
        _pluck(v2_cfg, "exclude_reduce_only", True), True
    )

    leverage_cfg = _pluck(v2_cfg, "leverage_defaults", {}) or {}
    default_leverage_raw = (
        _pluck(leverage_cfg, "default")
        or _pluck(leverage_cfg, "__default__")
        or Decimal("20")
    )
    default_leverage = _coerce_decimal(default_leverage_raw, Decimal("20"))

    per_symbol: Dict[str, Decimal] = {}
    if isinstance(leverage_cfg, Mapping):
        for key, value in leverage_cfg.items():
            if key in {"default", "__default__"}:
                continue
            per_symbol[str(key)] = _coerce_decimal(value, default_leverage)

    leverage_defaults = LeverageDefaults(
        default=default_leverage,
        per_symbol=per_symbol,
    )

    fallback_node = fallback_cfg if isinstance(
        fallback_cfg, Mapping) else {}
    backoff_raw = fallback_node.get("backoff_ms") if isinstance(
        fallback_node, Mapping) else None
    if isinstance(backoff_raw, (list, tuple)):
        filtered = []
        for item in backoff_raw:
            delay = _coerce_int(item, -1)
            if delay > 0:
                filtered.append(delay)
        backoff_sequence = tuple(filtered) if filtered else (200, 500, 1000)
    else:
        backoff_sequence = (200, 500, 1000)
    fallback = FallbackConfig(
        policy=str(fallback_node.get("policy") or "fail_closed"),
        risk_reduction_pct=_coerce_decimal(
            fallback_node.get("risk_reduction_pct"), Decimal("0.5")
        ),
        backoff_ms=backoff_sequence,
        max_attempts=_coerce_int(fallback_node.get("max_attempts"), 4),
        enabled=_coerce_bool(fallback_node.get("enabled"), True),
    )

    return ExposurePolicy(
        caps=caps,
        reservations=reservations,
        leverage_defaults=leverage_defaults,
        count_pending_orders=count_pending_orders,
        exclude_reduce_only=exclude_reduce_only,
        fallback=fallback,
        source="config_v2",
    )


def resolve_exposure_policy(config: Any) -> ExposurePolicy:
    """Resolve exposure policy with config v2 support and legacy fallback."""
    execution_domain = _get_v2_execution_domain(config)
    v2_cfg = execution_domain.get("exposure") if execution_domain else None
    if v2_cfg is not None:
        try:
            policy = _build_policy_from_v2(
                v2_cfg, execution_domain.get(
                    "fallback") if execution_domain else None
            )
            return policy
        except Exception:
            # Log warning and fallback to legacy
            # Note: No logger available here, so just fallback silently
            pass

    # Legacy path
    return _build_policy_from_legacy(config)
