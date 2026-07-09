AGENT_IDENTITY:
  agent_number: 2
  agent_name: primary-agent-arena-event-contract-builder
  machine: primary
  task_id: P37B_AGENT_ARENA_EVENT_CONTRACT
  branch: p37b-agent-arena-event-contract-primary-20260709
  worktree: C:\Users\wekab\Music\Phenix-p37b-event
  commit: 8323fee421b7a82c0ffbbdcb9755cbd166663fc2
  started_at: 2026-07-09T18:02:24+03:00
  finished_at: 2026-07-09T18:10:00+03:00

# Event Contract

This document outlines the validation rules for the `AgentArenaCommandEnvelope` Pydantic schema model.

---

## 1. Schema Properties
All commands and events carry the following attributes:
* **schema_version**: `int` (always default = `1`)
* **event_id**: `str` (auto-generated UUID prefix `event-`)
* **command_id**: `str` (auto-generated UUID prefix `cmd-`)
* **session_id**: `str` (required, non-empty)
* **agent_id**: `str` (required, non-empty)
* **agent_number**: `int` (required, ge=0)
* **created_at**: `str` (auto-populated UTC ISO timestamp)
* **received_at**: `str` (optional)
* **symbol**: `str` (optional; mandatory for trade commands)
* **command_kind**: `Literal` (one of the 8 required kinds)
* **rationale**: `str` (required, non-empty)
* **payload**: `dict` (extra context parameters)
* **testnet_only**: `True` (strictly enforces testnet authorization)
* **execution_authority**: `"agent_testnet_arena"`
* **source**: `Literal["cockpit", "cli", "api", "subagent"]`

---

## 2. Hard Security Constraints (Fail-Closed)
1. **Forbidden Live Flags**: Recursive audit rejects any occurrences of keys like `mainnet`, `live`, `production`, `prod`, `real` set to `True` (or equivalent truthy string values) inside the `payload` dictionary.
2. **Forbidden Credentials**: Rejects any keys containing strings like `api_key`, `secret`, `secret_key`, `passphrase`, `password`, `token`, or `credentials` anywhere in the payload hierarchy.
3. **Explicit Order Defaults**: For `AGENT_TESTNET_ORDER_REQUESTED`, either `quantity`/`qty` or `notional` must be explicitly defined and strictly positive (>0). The `order_type` is required, and limit orders must carry a positive `price`.
4. **Explicit Cancel References**: For `AGENT_TESTNET_CANCEL_REQUESTED`, either `exchange_order_id` or `client_order_id` must be explicitly defined.
5. **Symbol Mapping**: `symbol` must not be None or empty for order, close, and cancel requests.
