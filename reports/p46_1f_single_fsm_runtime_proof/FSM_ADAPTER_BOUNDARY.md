# FSM and Adapter Boundary

## FACTS

```yaml
fsm_proof:
  construction_site: P46RuntimeHarness using production ExecPosFSM constructor
  instance_identity: one process-local ExecPosFSM object
  command_received_count: 1
  result: DEC:OPEN / OPEN_OK
  emitted_registered_commands: 1
  adapter_call_count: 0
adapter_proof:
  network_enabled: false
  submit_calls: 0
  cancel_calls: 0
  amend_calls: 0
  payloads: []
```

## INFERENCES

- Acceptance is FSM proof, not exchange proof.

## ASSUMPTIONS

- Recording adapter behavior is relevant only as a no-network boundary sentinel.

## UNKNOWNS

- Exchange response and lifecycle outcomes are absent by design.
