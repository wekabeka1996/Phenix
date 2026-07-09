# FSM Handoff Contract Specifications

## 1. Schema
The handoff command schema inherits the canonical `AgentActionCommand` schema:
- `event_id`: Correlation ID for event tracking.
- `command_id`: Unique identifier for the command.
- `session_id`: ID of the executing agent session.
- `agent_id`: ID of the agent making the request.
- `agent_number`: Number of the agent.
- `command_kind`: Either `ENTRY`, `FULL_CLOSE`, `PARTIAL_CLOSE`, `OBSERVE`, or `AGENT_TESTNET_ORDER_REQUESTED`.
- `testnet_only`: Boolean enforcing testnet execution (must be `True`).
- `payload`: Contains parameters like `symbol` / `ticker`, `side` (BUY/SELL), `quantity` / `qty`, `notional`, `price`, etc.

## 2. Invariants & Validations
A command undergoes FSM handoff check transitioning from `pending_fsm` to `accepted_by_fsm` or `rejected_by_fsm`.

### 2.1 Rejection Reasons
The gateway enforces 6 distinct rejection checks:
1. **Unknown Event/Command Kind**: If `command_kind` is not registered in the `FSMAuditRegistry`.
2. **Missing Registry**: If the registry is not initialized or accessible.
3. **Missing Agent/Session Identity**: If `agent_id`, `session_id`, or `agent_number` are missing or empty.
4. **Non-Testnet Flag**: If `testnet_only` is False.
5. **Missing explicit quantity/notional or side where required**:
   - `side` must be BUY or SELL.
   - For order placement commands (e.g. `ENTRY`, `AGENT_TESTNET_ORDER_REQUESTED`), quantity/notional must be present and `> 0`.
6. **No Execution Adapter Available**: If `execution_adapter` is `None` or configured base/rest URL does not contain `"testnet"`.

## 3. Order Execution Lifecycle Transitions
- **Recorded**: Inception.
- **Pending FSM**: Sent for FSM validation.
- **Accepted by FSM**: Handoff validated.
- **Submitted Testnet**: Sent to adapter (`create_order`).
- **Exchange ACK**: Successful submission.
- **Exchange Reject**: Exchange rejection.
- **Lifecycle Closed**: Terminal state.
