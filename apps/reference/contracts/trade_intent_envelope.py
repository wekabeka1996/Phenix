"""Shared routing envelope for EVT:TRADE_INTENT_PROPOSED.

Placed in ``contracts/`` (not ``domains/decision_making/``) so that both the
EP and DM domains can import it without triggering the EP→DM import guardrail.

DM ``boundary_models.py`` re-exports ``TradeIntentRoutingEnvelope`` from here
so existing DM-internal imports continue to work unchanged.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class TradeIntentRoutingEnvelope(BaseModel):
    """Routing-only envelope for EVT:TRADE_INTENT_PROPOSED.

    Captures only the fields needed for the route-split decision (symbol,
    strategy, rid, reduce_only) and provides resolved property accessors.

    The deeper payload (order, tca_budget, risk_budget, entry_plan, etc.) is
    NOT modeled here. That is handled by TradeIntentOpenIntake further
    downstream in the CMD:OPEN path.

    ``extra="ignore"`` is intentional: this is a routing-only envelope, not
    the full intent model.

    Runtime: produced by AuroraDecisionMixin, consumed by IntentRouter.
    Schema reference: decision_making/schemas/trade_intent_v1.json
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    # Symbol: two legacy key names co-exist in the transport contract.
    instrument: str | None = None
    symbol: str | None = None

    # Strategy correlation
    strategy: str | None = None
    strategy_id: str | None = None

    # Request correlation
    rid: str | None = None

    # Side needed for audit trail
    side: str | None = None

    # Reduce-only: top-level flag for route-split.
    reduce_only: bool | None = None

    # Order block: needed to inspect nested reduce_only keys.
    order: dict[str, Any] | None = None

    @property
    def resolved_symbol(self) -> str:
        """Return symbol from either instrument or symbol key."""
        return str(self.instrument or self.symbol or "")

    @property
    def resolved_strategy_id(self) -> str | None:
        """Return strategy id from either strategy or strategy_id key."""
        raw = self.strategy or self.strategy_id
        return str(raw) if raw else None

    @property
    def resolved_rid(self) -> str:
        """Return rid with a safe unknown fallback."""
        return str(self.rid or "unknown")

    @property
    def is_reduce_only(self) -> bool:
        """Return True if this intent should route to CMD:CLOSE.

        Checks the top-level reduce_only flag first, then the nested order
        block keys (reduce_only and reduceOnly) to handle both naming styles.
        """
        if self.reduce_only:
            return True
        order_info = self.order or {}
        return bool(order_info.get("reduce_only") or order_info.get("reduceOnly"))
