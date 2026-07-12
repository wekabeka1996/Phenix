# Validation

## FACTS

Commands and results:

```powershell
python -m pytest tests/test_config.py tests/test_single_memory_kernel.py -q
# 22 passed

$env:PYTHONPATH="$repo;$repo/tools/deepseek-terminal-agent/src"
python -m pytest tools/deepseek-terminal-agent/tests/test_config.py tools/deepseek-terminal-agent/tests/test_single_memory_kernel.py tools/deepseek-terminal-agent/tests/test_canonical_memory_runtime_cutover.py tools/deepseek-terminal-agent/tests/test_memory_lifecycle_cockpit_smoke.py tools/deepseek-terminal-agent/tests/test_agent_order_lifecycle_harness.py tools/deepseek-terminal-agent/tests/test_p42g_unified_smoke.py -q
# 42 passed before final read-only tightening

python -m pytest tools/deepseek-terminal-agent/tests -q
# 578 passed, 13 skipped, 3 warnings

git diff --check
# passed
```

The 13 skips are not used as proof. Three warnings come from existing dev defaults in `vfoundation/config.py` exercised by a mocked adapter test; no credentials were read or printed.

Static searches covered legacy constructors/imports, canonical constructors, JSONL append helpers, direct append opens, hardcoded `.agent_memory`, and P42N markers.

## INFERENCES

- Unit, route, harness, restart, negative, and full regression evidence jointly support the package verdict.

## ASSUMPTIONS

- The test environment matches the repository's supported local Python setup.

## UNKNOWNS

- No external runtime or provider/exchange proof was attempted.

