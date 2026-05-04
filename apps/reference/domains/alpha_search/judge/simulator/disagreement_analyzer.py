"""Deterministic disagreement analysis for Phase 5 Package 5C."""

from __future__ import annotations

from typing import Literal

from .fee_slippage_calculator import compute_net_return

OptimalAction = Literal["OPEN_LONG", "OPEN_SHORT", "NO_ENTRY"]
SupportedVerdictAction = Literal[
    "OPEN_LONG",
    "OPEN_SHORT",
    "NO_ENTRY",
    "UNKNOWN",
    "SUPPRESS",
]


def _compute_action_net_returns(
    *,
    matched_trade: bool,
    entry_price: float | None,
    exit_price: float | None,
    fee_per_cycle_bps: float,
    slippage_pct: float,
) -> dict[OptimalAction, float]:
    if (
        not matched_trade
        or entry_price is None
        or exit_price is None
    ):
        return {
            "OPEN_LONG": 0.0,
            "OPEN_SHORT": 0.0,
            "NO_ENTRY": 0.0,
        }

    return {
        "OPEN_LONG": compute_net_return(
            entry_price,
            exit_price,
            "LONG",
            fee_per_cycle_bps,
            slippage_pct,
        ),
        "OPEN_SHORT": compute_net_return(
            entry_price,
            exit_price,
            "SHORT",
            fee_per_cycle_bps,
            slippage_pct,
        ),
        "NO_ENTRY": 0.0,
    }


def determine_optimal_action(
    *,
    matched_trade: bool,
    entry_price: float | None,
    exit_price: float | None,
    fee_per_cycle_bps: float,
    slippage_pct: float,
) -> OptimalAction:
    """Choose the best bounded action from the realized price path.

    Rule:
    - If no matched trade or no prices exist, choose NO_ENTRY.
    - Otherwise compute modeled net returns for LONG and SHORT using the 5B
      fee/slippage model.
    - Choose OPEN_LONG when long net return is strictly positive and strictly
      better than short net return.
    - Choose OPEN_SHORT when short net return is strictly positive and strictly
      better than long net return.
    - Otherwise choose NO_ENTRY.
    """

    action_returns = _compute_action_net_returns(
        matched_trade=matched_trade,
        entry_price=entry_price,
        exit_price=exit_price,
        fee_per_cycle_bps=fee_per_cycle_bps,
        slippage_pct=slippage_pct,
    )
    long_return = action_returns["OPEN_LONG"]
    short_return = action_returns["OPEN_SHORT"]

    if long_return > 0.0 and long_return > short_return:
        return "OPEN_LONG"
    if short_return > 0.0 and short_return > long_return:
        return "OPEN_SHORT"
    return "NO_ENTRY"


def compute_disagreement(
    *,
    verdict_action: SupportedVerdictAction,
    matched_trade: bool,
    entry_price: float | None,
    exit_price: float | None,
    fee_per_cycle_bps: float,
    slippage_pct: float,
    verdict_net_return: float | None = None,
) -> dict[str, float | str] | None:
    """Return disagreement details when the verdict differs from the optimal action."""

    if verdict_action not in {
        "OPEN_LONG",
        "OPEN_SHORT",
        "NO_ENTRY",
        "UNKNOWN",
        "SUPPRESS",
    }:
        raise ValueError(f"Unsupported verdict_action: {verdict_action}")

    if verdict_action in {"UNKNOWN", "SUPPRESS"}:
        return None

    action_returns = _compute_action_net_returns(
        matched_trade=matched_trade,
        entry_price=entry_price,
        exit_price=exit_price,
        fee_per_cycle_bps=fee_per_cycle_bps,
        slippage_pct=slippage_pct,
    )
    optimal_action = determine_optimal_action(
        matched_trade=matched_trade,
        entry_price=entry_price,
        exit_price=exit_price,
        fee_per_cycle_bps=fee_per_cycle_bps,
        slippage_pct=slippage_pct,
    )
    if verdict_action == optimal_action:
        return None

    modeled_verdict_return = action_returns[verdict_action]
    if verdict_net_return is not None and verdict_action in {"OPEN_LONG", "OPEN_SHORT"}:
        modeled_verdict_return = verdict_net_return

    cost_of_disagreement = max(
        0.0,
        action_returns[optimal_action] - modeled_verdict_return,
    )

    return {
        "optimal_action": optimal_action,
        "cost_of_disagreement": cost_of_disagreement,
    }


def build_disagreement_record(
    *,
    verdict_id: str,
    strategy_id: str,
    symbol: str,
    tf_sec: int,
    bar_close_ts: int,
    verdict_action: str,
    optimal_action: str,
    cost_of_disagreement: float,
    confidence: float,
    dissent_noted: bool,
) -> dict[str, object]:
    """Build a bounded disagreement record for one cycle."""

    return {
        "verdict_id": verdict_id,
        "strategy_id": strategy_id,
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar_close_ts": bar_close_ts,
        "verdict_action": verdict_action,
        "optimal_action": optimal_action,
        "cost_of_disagreement": cost_of_disagreement,
        "confidence": confidence,
        "dissent_noted": dissent_noted,
    }
