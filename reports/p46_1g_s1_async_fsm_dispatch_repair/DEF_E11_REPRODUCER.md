# DEF-E11 Reproducer

## FACTS

```yaml
failure_reproducer:
  calling_thread: TCP/main bridge worker
  event_loop_present: false
  event_loop_owner: production AsyncLoopRuntime, intentionally absent in reproducer
  dispatcher: ExecPosFSM._process_flow_result
  async_target: ExecPosFSM._execute_decision
  exact_failure_location: apps/reference/domains/execution_position/fsm.py
  observed_error: "DEF-E11: No async loop available"
  fsm_ingress: 1
  adapter_calls: 0
```

- Test: `test_real_http_tcp_fsm_path_reproduces_def_e11_without_loop`.
- The test uses the real V2 contract, registry, HTTP route, TCP bridge, command handler, and FSM dispatch seam. The final adapter is recording-only with network disabled.

## INFERENCES

- The failure is caused by absent loop ownership at dispatch, not by HTTP, TCP, registry, authority, or sizing serialization.

## ASSUMPTIONS

- The P46 runtime harness remains representative of the production-style ingress construction.

## UNKNOWNS

- None within the deterministic reproducer boundary.
