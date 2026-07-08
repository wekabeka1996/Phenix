"""DeepSeek to FSM decision-making gateway adapter.

Maps AgentTradeDecisionV0 decisions into the FSM's EVT:STRATEGY_SIGNAL_PRODUCED signal ingress seam.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional
from .contracts_p26 import AgentTradeDecisionV0

class AgentTradeDecisionToSignalMapper:
    """Mapper that converts AgentTradeDecisionV0 to the canonical FSM signal payload.

    Enforces strict exclusions and maps actions to FSM intent_kind and side values.
    """

    @staticmethod
    def map_decision(
        decision: AgentTradeDecisionV0,
        decision_id: Optional[str] = None,
        ts_ms: Optional[int] = None,
        price_ctx: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Map AgentTradeDecisionV0 to EVT:STRATEGY_SIGNAL_PRODUCED payload.

        Args:
            decision: The validated AgentTradeDecisionV0 object.
            decision_id: Optional decision ID override. If not provided, maps from decision/UUID.
            ts_ms: Optional timestamp override. If not provided, maps to current time.
            price_ctx: Optional price context (e.g. entry_price, mark_price).

        Returns:
            A dictionary containing the mapped event payload, compliant with FSM signal contracts.
        """
        # Validate action and side alignment (fail-closed if mismatch)
        if decision.action == "TESTNET_OPEN_LONG" and decision.side != "BUY":
            raise ValueError("Open long requires side BUY")
        if decision.action == "TESTNET_OPEN_SHORT" and decision.side != "SELL":
            raise ValueError("Open short requires side SELL")
        if decision.action in ("TESTNET_CLOSE", "TESTNET_REDUCE") and decision.side not in ("BUY", "SELL"):
            raise ValueError("Close/Reduce actions require active side")
        if decision.action in ("WAIT", "OBSERVE", "NO_ACTION") and decision.side != "NONE":
            raise ValueError("Passive actions require side NONE")

        # Map actions to intent_kind and side
        if decision.action == "TESTNET_OPEN_LONG":
            intent_kind = "ENTRY"
            side = "BUY"
        elif decision.action == "TESTNET_OPEN_SHORT":
            intent_kind = "ENTRY"
            side = "SELL"
        elif decision.action == "TESTNET_CLOSE":
            intent_kind = "FULL_CLOSE"
            side = decision.side
        elif decision.action == "TESTNET_REDUCE":
            intent_kind = "PARTIAL_CLOSE"
            side = decision.side
        else:
            # Passive action -> non-executable observation event
            intent_kind = "OBSERVE"
            side = "NONE"

        resolved_decision_id = decision_id or f"ds-dec-{uuid.uuid4()}"
        resolved_ts_ms = ts_ms or int(time.time() * 1000)

        # Build payload copy
        payload: Dict[str, Any] = {
            "symbol": decision.symbol,
            "side": side,
            "strategy_id": decision.agent_id,  # Agent id becomes strategy/source id
            "rid": resolved_decision_id,       # Correlation RID
            "why_chain": [decision.thesis],
            "intent_kind": intent_kind,
            "ts_ms": resolved_ts_ms,
            "price_ctx": price_ctx or {},
            "agent_id": decision.agent_id,
            "decision_id": resolved_decision_id,
            "packet_ref": decision.packet_ref,
            "testnet_only": decision.testnet_only,
            "source": "deepseek_agent",
            "readiness": {"warmup_ok": True}
        }

        # Strict exclusions validation
        excluded_keys = {
            "qty", "quantity", "notional", "max_notional_per_order",
            "leverage", "target_leverage", "margin_mode", "step_size",
            "tick_size", "min_qty", "min_notional", "order_type", "tif",
            "time_in_force"
        }
        for k in excluded_keys:
            if k in payload:
                raise ValueError(f"Strict exclusion violation: '{k}' must not be in mapped payload")

        return payload
