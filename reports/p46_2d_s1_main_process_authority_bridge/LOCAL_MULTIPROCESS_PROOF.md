# Local Multiprocess Proof

Windows `multiprocessing` used the `spawn` start method.

```yaml
processes:
  main_query_runtime: distinct PID
  fastapi_edge: distinct PID
  pytest_coordinator: distinct PID
fastapi_local_authority: false
fixture_fallback_in_fastapi: false
read_model_http_status: 200
dry_run_http_status: 200
dry_run_decision: ACCEPTED
derived_quantity_present: true
command_emissions: 0
fsm_calls: 0
adapter_calls: 0
exchange_calls: 0
```

The main process used real Pydantic contracts, real `TradingSessionAuthorityStore`, real `PhenixReadModelService`, real P46-2D dry-run service, and real TCP serialization. Context/lifecycle/account/market sources were explicit deterministic no-network test fixtures in the main process and are not claimed as production runtime proof.

Cockpit Express was not process C in this test. Its unchanged baseline was validated separately.
