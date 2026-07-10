# Order Lifecycle Trace Contract

This document defines the lifecycle tracking contract specifications for the P40 order proof system.

---

## 1. Trace Object Schema

Every order execution path evaluated by the harness yields a trace object conforming to this schema (serialized as JSON):
```json
{
  "command_id": "string",
  "event_id": "string",
  "session_id": "string",
  "agent_id": "string",
  "agent_number": integer,
  "symbol": "string",
  "side": "string",
  "order_type": "string",
  "quantity/notional source": "string" (e.g. "payload.qty"),
  "created_at": "string" (ISO timestamp),
  "fsm_status": "string" (e.g. "recorded", "rejected_by_fsm"),
  "adapter_status": "string" (e.g. "submitted_testnet", "blocked_no_order", "blocked_guard", "blocked_missing_config"),
  "exchange_status": "string" (e.g. "exchange_ack", "exchange_reject", "none"),
  "lifecycle_ref": "string" (exchange order reference or "none"),
  "memory_ref": "string" (durable memory reflection ID)
}
```

---

## 2. Ingress & Routing States

### FSM Status (`fsm_status`)
- **`recorded`**: Command successfully registered and passed initial safety validation.
- **`rejected_by_fsm`**: Command failed initial safety checks (invalid env, missing descriptor, double production URL match).

### Adapter Status (`adapter_status`)
- **`blocked_guard`**: Safety gate validation rejected the handoff before submitting.
- **`blocked_no_order`**: Observation mode is active or P40A submit gate is locked.
- **`blocked_missing_config`**: Configuration keys (like adapter_id or base_url) are missing or adapter library raised an error.
- **`submitted_testnet`**: Command safely passed gates and reached the exchange adapter layer.

### Exchange Status (`exchange_status`)
- **`exchange_ack`**: Mock/Testnet API acknowledged order placement.
- **`exchange_reject`**: Mock/Testnet API rejected order placement.
- **`none`**: Order did not reach the exchange layer.

---

## 3. Storage Ledgers
Traces are persisted in two concurrent logs:
1. **Session-Specific Ledger**: `.agent_memory/sessions/{session_id}/order_lifecycle_traces.jsonl`
2. **Global System Log**: `.agent_memory/order_lifecycle_traces.jsonl`
In addition, a reflection entry with `kind="decision_review"` is appended to the durable trading session memory file `agent_trading_memory.json`.
