# Agent Turn Envelope

This document specifies the format of the context envelope provided to agents at each turn and the allowed structured responses.

---

## 1. Context Envelope Structure

Every agent execution turn starts by building a context envelope containing:
- **session_id**: Uniquely identifies the trading session.
- **agent_id**: Uniquely identifies the executing agent.
- **owned_symbols**: List of symbols authorized for the agent (e.g. `['ETHUSDT', 'SOLUSDT']`).
- **current_market_context**: Real-time market tick, order book, or spread details.
- **portfolio_state**: Available equity, margin usage, and balances.
- **own_positions_orders**: Currently open positions and active orders.
- **peer_publications**: Latest observation or risk warnings published by peer agents.
- **instruction_versions**: Version hash of the loaded instruction manifest files.
- **recent_decisions**: Recent logs of decisions made by the agent.
- **allowed_tools**: Allowed tool identifiers (e.g. `['submit_order', 'cancel_order']`).
- **deadline**: ISO datetime cutoff by which the agent must respond.
- **current_collective_state_version**: Correlation version of the collective memory.

---

## 2. Allowed Structured Response Options

Agents must return a JSON response matching the `AgentTurnResponse` schema:

- **`WAIT`**: No action needed this turn.
- **`SKIP`**: Pass execution loop for this cadence check.
- **`PUBLISH_OBSERVATION`**: Send an observation event to the FSM.
- **`PUBLISH_RISK_WARNING`**: Send a risk warning to the FSM.
- **`REQUEST_ORDER`**: Propose placement of a new testnet order.
- **`REQUEST_CANCEL`**: Propose cancellation of an existing active order.
- **`REQUEST_CLOSE`**: Propose closing an active position.
- **`REQUEST_REVIEW`**: Propose a manual audit review check.
- **`EMIT_SOS`**: Emit a critical distress/system failure signal.
