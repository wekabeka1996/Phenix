# Execution Path Decision and Safeties

## 1. Chosen Execution Path
The `AGENT_TESTNET_ORDER_REQUESTED` command is wired as a bus listener inside `ExecPosFSM` (in `fsm.py` and `intent_router.py`).
It processes the order requests by delegating to the `FSMHandoffGateway`, which maps the parameters and calls `self.execution_adapter.create_order(...)` of the FSM's active exchange adapter.

## 2. Guardrails & Blocking
The execution gateway implements the following strict safeties:
- **Observation-Only Blocking**: On the secondary machine, `no_order_observation_mode` is configured to `True`. As a result:
  - Consequential execution listeners are not registered on the bus.
  - Any attempts to invoke execution decision paths are intercepted and blocked by `_block_no_order_action("agent_testnet_order_requested")`, logging warning telemetry instead of submitting orders.
- **Explicit Testnet URLs Only**: The gateway parses the adapter's `base_url` / `rest_url` and blocks execution if the URL does not contain `"testnet"` (unless using the simulation-only `SimulatedAdapter`).
- **No Raw Clients**: No raw Binance client or raw API endpoints are queried directly; the gateway routes strictly through `AbstractExchangeAdapter.create_order` to leverage the FSM's existing connection pool and rate-limiting.
- **Fail-Closed on Validation Failures**: Any missing quantity, notional, side, or invalid flags automatically transitions the command to `rejected_by_fsm` and prevents any downstream order calls.
