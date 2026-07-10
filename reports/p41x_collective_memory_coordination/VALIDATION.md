# Validation

## P41X Unit/API Proof

```powershell
python -m pytest -q tests/test_collective_memory_kernel.py tests/test_agent_coordination_runtime.py tests/test_collective_coordination_api.py tests/test_coordination_config.py
```

Result: `18 passed`.

## Full Cockpit Regression

```powershell
$env:PYTHONPATH='src;../..'; python -m pytest -q
```

Result: `534 passed, 9 skipped, 3 warnings`. Warnings are existing vfoundation development defaults used by the P40 shadow harness test.

## Aurora Mapper/FSM Regression

```powershell
python -m pytest -q tests/domains/agent_bridge/test_deepseek_to_fsm_adapter.py tests/domains/agent_bridge/test_deepseek_fsm_signal_integration.py
```

Result: `13 passed`.

## Benchmark

`600` configured market events produced `664` evidence events; bounded context, retention, and replay checks passed. See `LONG_SESSION_BENCHMARK.md`.

## Static Checks

- `python -m py_compile` passed for all new/edited Python modules.
- Ruff was unavailable: `No module named ruff`.
- Source test confirms no `BinanceAdapter`, `ExchangeACL`, `httpx`, or `requests` import in agent-facing tool code.

## Runtime Boundary

TestClient API smoke and local filesystem concurrency are proven. A real dashboard server, two external agent processes, Aurora runtime, and exchange testnet were not started.
