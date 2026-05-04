"""Validation and normalization helpers for IntentBuilder."""

import decimal
from dataclasses import dataclass
from typing import Any, Callable, Optional

from apps.reference.shared.decision_primitives.tpsl_owner import clone_tpsl_owner_ctx


@dataclass(frozen=True)
class NormalizedTradeInputs:
    qty: decimal.Decimal
    price: decimal.Decimal


@dataclass(frozen=True)
class ResolvedTCAPreferences:
    max_slippage_bps: str
    max_latency_ms: Any
    maker_preference: str


@dataclass(frozen=True)
class ResolvedRiskBudgets:
    trade_cvar95_max_bps: str
    session_cvar95_max_bps: str


@dataclass(frozen=True)
class SanitizedTPSLPayload:
    stop_price: Optional[str]
    target_price: Optional[str]
    owner_ctx: Optional[dict]


@dataclass(frozen=True)
class ResolvedKellyMetadata:
    p: str
    payoff_ratio_r: str
    kelly_fraction: str
    provenance: dict[str, Any]


def normalize_trade_inputs(*, qty: Any, price: Any) -> NormalizedTradeInputs:
    """Normalize qty/price using the builder's existing Decimal coercion."""
    return NormalizedTradeInputs(
        qty=decimal.Decimal(str(qty)),
        price=decimal.Decimal(str(price)),
    )


def resolve_tca_preferences(
    *,
    tca_prefs: Any,
    max_slippage_bps: Optional[int],
    max_latency_ms: Optional[int],
    get_strict: Callable[[Any, str, str], Any],
) -> ResolvedTCAPreferences:
    """Resolve the TCA preferences consumed by the trade-intent payload."""
    if max_slippage_bps is not None:
        resolved_max_slippage = str(max_slippage_bps)
    else:
        resolved_max_slippage = str(
            get_strict(tca_prefs, "max_slippage_bps",
                       "Missing max_slippage_bps")
        )

    if max_latency_ms is not None:
        resolved_max_latency = max_latency_ms
    else:
        resolved_max_latency = get_strict(
            tca_prefs,
            "max_latency_ms",
            "Missing max_latency_ms",
        )

    maker_preference = str(
        get_strict(tca_prefs, "maker_preference", "Missing maker_preference")
    )

    return ResolvedTCAPreferences(
        max_slippage_bps=resolved_max_slippage,
        max_latency_ms=resolved_max_latency,
        maker_preference=maker_preference,
    )


def resolve_risk_budgets(
    *,
    risk_budgets: Any,
    get_strict: Callable[[Any, str, str], Any],
) -> ResolvedRiskBudgets:
    """Resolve the risk-budget fields consumed by the trade-intent payload."""
    return ResolvedRiskBudgets(
        trade_cvar95_max_bps=str(
            get_strict(
                risk_budgets,
                "trade_cvar95_max_bps",
                "Missing trade_cvar95_max_bps",
            )
        ),
        session_cvar95_max_bps=str(
            get_strict(
                risk_budgets,
                "session_cvar95_max_bps",
                "Missing session_cvar95_max_bps",
            )
        ),
    )


def sanitize_tpsl_payload(
    *,
    stop_price: Optional[str],
    target_price: Optional[str],
    safe_decimal_fn: Callable[..., Any],
    tpsl_owner_ctx: Optional[dict],
) -> SanitizedTPSLPayload:
    """Canonicalize stop/target payload fields without changing builder semantics."""
    stop_price_payload: Optional[str] = None
    target_price_payload: Optional[str] = None
    if stop_price not in (None, "", "None"):
        stop_decimal = safe_decimal_fn(stop_price, default=None)
        stop_price_payload = str(
            stop_decimal) if stop_decimal is not None else None
    if target_price not in (None, "", "None"):
        target_decimal = safe_decimal_fn(target_price, default=None)
        target_price_payload = (
            str(target_decimal) if target_decimal is not None else None
        )
    return SanitizedTPSLPayload(
        stop_price=stop_price_payload,
        target_price=target_price_payload,
        owner_ctx=clone_tpsl_owner_ctx(tpsl_owner_ctx),
    )


def _coerce_decimal_field(field_name: str, value: Any) -> decimal.Decimal:
    """Coerce a required Kelly field into Decimal without runtime defaults."""
    if value is None:
        raise ValueError(f"Missing {field_name}")
    try:
        return decimal.Decimal(str(value))
    except (decimal.InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}: {value!r}") from exc


def _resolve_kelly_config(*, config: Any, strategy_id: str) -> Any:
    """Resolve the typed Kelly config block for one strategy."""
    strategies_cfg = getattr(config, "strategies", None)
    if strategies_cfg is None:
        raise ValueError("Missing strategies config")

    strategy_cfg = getattr(strategies_cfg, str(strategy_id), None)
    if strategy_cfg is None:
        raise ValueError(f"Missing strategy config: {strategy_id}")

    decision_cfg = getattr(strategy_cfg, "decision", None)
    if decision_cfg is None:
        raise ValueError(
            f"Missing decision config for strategy: {strategy_id}")

    kelly_cfg = getattr(decision_cfg, "kelly", None)
    if kelly_cfg is None:
        raise ValueError(
            f"Missing decision.kelly config for strategy: {strategy_id}")

    return kelly_cfg


def resolve_kelly_metadata(*, config: Any, strategy_id: str) -> ResolvedKellyMetadata:
    """Resolve truthful Kelly metadata from the typed strategy config only."""
    kelly_cfg = _resolve_kelly_config(config=config, strategy_id=strategy_id)

    base_probability = _coerce_decimal_field(
        "decision.kelly.base_probability",
        getattr(kelly_cfg, "base_probability", None),
    )
    p_min = _coerce_decimal_field(
        "decision.kelly.p_min",
        getattr(kelly_cfg, "p_min", None),
    )
    p_max = _coerce_decimal_field(
        "decision.kelly.p_max",
        getattr(kelly_cfg, "p_max", None),
    )
    payoff_ratio_r = _coerce_decimal_field(
        "decision.kelly.payoff_ratio_r",
        getattr(kelly_cfg, "payoff_ratio_r", None),
    )
    kelly_cap = _coerce_decimal_field(
        "decision.kelly.kelly_cap",
        getattr(kelly_cfg, "kelly_cap", None),
    )
    kelly_alpha = _coerce_decimal_field(
        "decision.kelly.kelly_alpha",
        getattr(kelly_cfg, "kelly_alpha", None),
    )
    uplift_factor = _coerce_decimal_field(
        "decision.kelly.uplift_factor",
        getattr(kelly_cfg, "uplift_factor", None),
    )

    if payoff_ratio_r <= decimal.Decimal("0"):
        raise ValueError("decision.kelly.payoff_ratio_r must be > 0")
    if p_min > p_max:
        raise ValueError(
            "decision.kelly.p_min must be <= decision.kelly.p_max")
    if kelly_cap < decimal.Decimal("0"):
        raise ValueError("decision.kelly.kelly_cap must be >= 0")

    probability = max(decimal.Decimal("0"), min(
        decimal.Decimal("1"), base_probability))
    probability = max(p_min, min(p_max, probability))

    full_kelly_fraction = probability - (
        (decimal.Decimal("1") - probability) / payoff_ratio_r
    )
    if full_kelly_fraction < decimal.Decimal("0"):
        raise ValueError(
            "Configured Kelly inputs produce a negative kelly_fraction")

    kelly_fraction = min(full_kelly_fraction, kelly_cap)
    decision_path = f"config.strategies.{strategy_id}.decision.kelly"
    return ResolvedKellyMetadata(
        p=str(probability),
        payoff_ratio_r=str(payoff_ratio_r),
        kelly_fraction=str(kelly_fraction),
        provenance={
            "source_path": decision_path,
            "p": {
                "source": f"{decision_path}.base_probability",
                "raw": str(base_probability),
                "p_min": str(p_min),
                "p_max": str(p_max),
                "value": str(probability),
            },
            "payoff_ratio_r": {
                "source": f"{decision_path}.payoff_ratio_r",
                "value": str(payoff_ratio_r),
            },
            "kelly_fraction": {
                "formula": "p - (1 - p) / payoff_ratio_r",
                "full_kelly": str(full_kelly_fraction),
                "kelly_cap": str(kelly_cap),
                "value": str(kelly_fraction),
            },
            "unapplied_config_fields": {
                "kelly_alpha": {
                    "value": str(kelly_alpha),
                    "reason": "boundary_semantics_not_proven",
                },
                "uplift_factor": {
                    "value": str(uplift_factor),
                    "reason": "no_score01_probability_producer_on_hot_path",
                },
            },
        },
    )
