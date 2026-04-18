"""Pure fee and slippage helpers for Phase 5 Package 5B."""

from typing import Literal


def compute_fee_cost_bps(fee_per_cycle_bps: float) -> float:
    """Convert fee bps to a decimal return cost."""

    if fee_per_cycle_bps < 0:
        raise ValueError("fee_per_cycle_bps must be >= 0")
    return fee_per_cycle_bps / 10000.0


def compute_slippage_cost_pct(slippage_pct: float) -> float:
    """Convert slippage percentage points to a decimal return cost."""

    if slippage_pct < 0:
        raise ValueError("slippage_pct must be >= 0")
    return slippage_pct / 100.0


def _validate_prices(entry_price: float, exit_price: float) -> None:
    if entry_price <= 0:
        raise ValueError("entry_price must be > 0")
    if exit_price <= 0:
        raise ValueError("exit_price must be > 0")


def _compute_raw_return(
    entry_price: float,
    exit_price: float,
    side: Literal["LONG", "SHORT"],
) -> float:
    if side == "LONG":
        return (exit_price - entry_price) / entry_price
    if side == "SHORT":
        return (entry_price - exit_price) / entry_price
    raise ValueError(f"Unsupported side: {side}")


def compute_net_return(
    entry_price: float,
    exit_price: float,
    side: str,
    fee_per_cycle_bps: float,
    slippage_pct: float,
) -> float:
    """Compute a simple net return after modeled fee and slippage costs."""

    _validate_prices(entry_price, exit_price)
    normalized_side = side.upper()
    raw_return = _compute_raw_return(entry_price, exit_price, normalized_side)
    fee_cost = compute_fee_cost_bps(fee_per_cycle_bps)
    slippage_cost = compute_slippage_cost_pct(slippage_pct)
    return raw_return - fee_cost - slippage_cost
