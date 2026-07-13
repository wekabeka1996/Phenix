# Deterministic Runtime Proof

## FACTS

The focused proof uses real P46 HTTP/TCP/authority/sizing/registry/FSM components and a recording venue adapter with `network_enabled=false`.

```yaml
positive_path:
  http_status: 202
  command_emissions: 1
  fsm_ingress: 1
  adapter_submit_calls: 1
  caller_quantity_present: false
  duplicate_http_second_action: false
  duplicate_tcp_second_action: false
  conflicting_duplicate_status: 409
no_loop_path:
  typed_rejection: AsyncDispatchUnavailableError
  adapter_submit_calls: 0
```

- Same-loop and worker-thread dispatch are tested separately.
- Stopped and closed loops fail closed.
- Focused run passed `6` tests with RuntimeWarnings promoted to errors.

## INFERENCES

- The repaired seam executes one coroutine on one canonical loop without an un-awaited coroutine leak.

## ASSUMPTIONS

- Recording-adapter invocation accurately identifies arrival at the final venue boundary.

## UNKNOWNS

- This deterministic proof does not establish exchange network behavior.
