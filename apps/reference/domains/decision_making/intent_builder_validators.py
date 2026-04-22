"""Validation and normalization helpers for IntentBuilder."""

import decimal
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .tpsl_owner import clone_tpsl_owner_ctx


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


def resolve_kelly_fraction(*, config: Any, strategy_id: str) -> str:
    """Preserve the builder's compatibility-only Kelly fraction lookup."""
    try:
        strat_cfg = getattr(
            config.strategies,
            str(strategy_id),
            getattr(config.strategies, "aurora", None),
        )
        return str(getattr(getattr(strat_cfg.decision, "kelly", None), "fraction", "0.1"))
    except Exception:
        return "0.1"
