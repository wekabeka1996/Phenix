# Hybrid Testnet Execution Path

We mapped how Phenix isolates active execution for safe testnet runs.

## 1. No-Order Observation Mode
- **Setting**: `no_order_observation_mode = True` is passed to the FSM.
- **Consequence**:
  - The FSM skips registering the execution listeners (`EVT:TRADE_INTENT_PROPOSED`, `CMD:EXTERNAL_OPEN_REQUEST_V1`, etc.).
  - Methods like `_on_trade_intent_proposed` intercept payloads using `self._block_no_order_action()` and log warning diagnostics rather than dispatching orders to the adapter.

## 2. Order Logging & Audits
Execution steps are logged across three distinct layers:
1.  **Order Log**: Evaluated by `OrderLoggerV1` and written to `logs/order_log_v1.jsonl` (verifying schema compliance).
2.  **Trade Lifecycle**: Aggregated per request ID (`rid`) into `logs/trade_lifecycle.jsonl` via the `trade_lifecycle` utility.
3.  **Boundary Audit**: Tracked by `IntentBoundaryAudit` which captures `EVT_TRADE_INTENT_PROPOSED` and generates WAL records.
