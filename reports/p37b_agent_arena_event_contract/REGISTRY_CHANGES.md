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

# Registry Changes

This document records the YAML configuration changes added to the SSOT `verb_registry_v1.yaml` file.

---

## 1. Registry File Location
- File path: `apps/reference/dictionaries/verb_registry_v1.yaml`

---

## 2. Added Commands (op: CMD)
The following command verbs have been registered under the `agent_bridge` domain owner:
1. **AGENT_ARENA_COMMAND_REQUESTED**: Triggered when a new arena intent command envelope is received.
2. **AGENT_TESTNET_ORDER_REQUESTED**: Command to create a testnet order. Requires explicit quantity/notional and price parameters.
3. **AGENT_TESTNET_CANCEL_REQUESTED**: Command to cancel a testnet order. Requires client/exchange reference ids.
4. **AGENT_TESTNET_CLOSE_REQUESTED**: Command to close active testnet position. Requires symbol reference.

---

## 3. Added Events (op: EVT)
The following event/telemetry verbs have been registered under the `agent_bridge` domain owner:
1. **AGENT_ARENA_COMMAND_REJECTED**: Fired when validation rejects a command request (e.g. live flags present, credentials present).
2. **AGENT_ARENA_COMMAND_ACCEPTED**: Fired when a command successfully passes the validation contract.
3. **AGENT_ARENA_RATIONALE_RECORDED**: Fired to record agent reasoning trails on the ledger.
4. **AGENT_ARENA_SOS_EMITTED**: Fired on emergency/SOS events.
