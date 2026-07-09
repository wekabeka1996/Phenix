# Guard Contract Specification

This document details the hardened FSM handoff guard safety contract implemented for the P39 Runtime MVP.

---

## 1. Schema Specifications

### AdapterCapabilityDescriptor
Every exchange adapter MUST declare an explicit capability descriptor of this structure:
```json
{
  "adapter_id": "string",
  "environment": "testnet" | "sandbox" | "mainnet" | "unknown",
  "supports_order_submit": boolean,
  "supports_no_order_observation": boolean,
  "source_of_truth": "string",
  "checked_at": "string" (ISO timestamp)
}
```

### Rejection Ledger Format
Rejected actions are persisted inside `.agent_memory/sessions/{session_id}/audit_rejections.jsonl` and the global ledger `.agent_memory/audit_rejections.jsonl` matching:
```json
{
  "agent_id": "string",
  "session_id": "string",
  "command_id": "string",
  "event_id": "string",
  "reason": "string",
  "timestamp": "string" (ISO timestamp)
}
```

---

## 2. Validation Invariants
The handoff validator rejects execution requests immediately if ANY of the following occur:
1. **Missing descriptor**: Any order submission without a resolved `AdapterCapabilityDescriptor` fails closed.
2. **Invalid environment**: If `descriptor.environment` is not `"testnet"` or `"sandbox"`, it is rejected.
3. **No-Order Mode**: If `no_order_observation_mode` is `True`, all order placements block.
4. **Missing Identity Fields**: Commands must provide valid `agent_id`, `session_id`, `command_id`, and `event_id`.
5. **No Implicit Quantities**: For order submission requests, the payload must explicitly contain a positive `qty`, `quantity`, or `notional` value.
6. **URL Double Guard**: If a configuration `base_url` points to a known production domain (e.g. `api.binance.com`), the transaction is blocked, even if the capability descriptor claims a testnet environment.
