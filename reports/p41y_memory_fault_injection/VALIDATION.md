# Validation

## Baseline Fault Run

```powershell
$env:PYTHONPATH='src;../..'; python -m pytest -q tests/test_collective_memory_fault_injection.py
```

Result before repair: `6 passed, 7 failed`.

## Final Fault Run

Result: `14 passed`; all 15 required scenarios are covered. Three additional consecutive runs each returned `14 passed`.

## P41X/P41Y Focused

```powershell
python -m pytest -q tests/test_collective_memory_fault_injection.py tests/test_semantic_recall_benchmark.py tests/test_collective_memory_kernel.py tests/test_agent_coordination_runtime.py tests/test_collective_coordination_api.py tests/test_coordination_config.py
```

Result: `33 passed`.

## Full Cockpit Package

```powershell
$env:PYTHONPATH='src;../..'; python -m pytest -q
```

Result: `549 passed, 9 skipped, 3 existing development-default warnings`.

## Mapper/FSM Regression

Result: `13 passed` for `test_deepseek_to_fsm_adapter.py` and `test_deepseek_fsm_signal_integration.py`.

## Static

- `py_compile`: passed.
- Ruff: unavailable (`No module named ruff`).
- No live dashboard, Aurora runtime, exchange client, or testnet order was started.
