# FSM Execution Path

We traced the event consumption entrypoints of the execution position FSM.

## 1. FSM Event Subscriptions
The FSM class (`ExecPosFSM` in `apps/reference/domains/execution_position/fsm.py`) registers the following subscriptions on `self.bus` during bootstrap:
- `EVT:PORTFOLIO_STATE_UPDATED` -> `self._on_portfolio_state_updated`
- `EVT:ORDER_ACK` -> `self._on_order_ack`
- `EVT:TRADE_EXECUTED` -> `self._on_trade_executed`
- `EVT:ORDER_FILL` -> `self._on_order_fill`
- `EVT:ORDER_STATE_CHANGED` -> `self._on_order_state_changed`
- `EVT:REGIME_DETECTED` -> `self._on_regime_detected`

## 2. Intent & Request Routing
When trading or external requests occur, they are dispatched via the event bus to:
- `EVT:TRADE_INTENT_PROPOSED` -> `self._on_trade_intent_proposed` (routed to `IntentRouter`)
- `CMD:EXTERNAL_OPEN_REQUEST_V1` -> `self._on_external_open_request`
- `CMD:EXTERNAL_POSITION_CLOSE_REQUEST_V1` -> `self._on_external_position_close_request`
- `CMD:EXTERNAL_BRACKET_AMEND_REQUEST_V1` -> `self._on_external_bracket_amend_request`

## 3. Safest Insertion Point for Agent Event Commands
The safest insertion path is:
1. Wrap agent decisions inside a new event type, e.g., `CMD:AGENT_EXECUTION_PROPOSAL_SUBMITTED`.
2. Register this verb in `verb_registry_v1.yaml` and `event_names.py`.
3. Add a dedicated method in `ExecPosFSM` (or a bridge gateway) that subscribes to `CMD:AGENT_EXECUTION_PROPOSAL_SUBMITTED`.
4. Validate the operator approval status first before creating a corresponding `EVT:TRADE_INTENT_PROPOSED` or forwarding it to `IntentRouter`.
