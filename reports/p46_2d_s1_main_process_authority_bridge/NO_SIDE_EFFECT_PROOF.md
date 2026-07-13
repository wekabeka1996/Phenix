# No-Side-Effect Proof

The accepted deterministic dry-run returned:

```yaml
session_mutations: 0
lease_mutations: 0
exposure_reservations: 0
command_emissions: 0
fsm_calls: 0
adapter_calls: 0
exchange_calls: 0
provider_calls: 0
```

The main bridge query test additionally proved `command_envelope_count=0`, `v2_handler_count=0`, and no emitted FSM events. No Testnet or mainnet operation was run.
