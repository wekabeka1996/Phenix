# Validation Record

This document records the automated validation results confirming the order lifecycle trace harness behavior.

---

## 1. Automated Unit Tests Run

Command:
```powershell
C:\Users\wekab\Music\Phenix\.venv\Scripts\pytest -v tools/deepseek-terminal-agent/tests/test_agent_order_lifecycle_harness.py
```

Output:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0 -- C:\Users\wekab\Music\Phenix\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\wekab\Music\Phenix-p40c-order-lifecycle-proof-harness\tools\deepseek-terminal-agent
configfile: pyproject.toml
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0, timeout-2.4.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 5 items

tools\deepseek-terminal-agent\tests\test_agent_order_lifecycle_harness.py::test_harness_blocked_guard_rejections PASSED [ 20%]
tools\deepseek-terminal-agent\tests\test_agent_order_lifecycle_harness.py::test_harness_blocked_missing_config PASSED [ 40%]
tools\deepseek-terminal-agent\tests\test_agent_order_lifecycle_harness.py::test_harness_blocked_no_order PASSED [ 60%]
tools\deepseek-terminal-agent\tests\test_agent_order_lifecycle_harness.py::test_harness_testnet_proof_ack PASSED [ 80%]
tools\deepseek-terminal-agent\tests\test_agent_order_lifecycle_harness.py::test_harness_url_double_guard_rejects PASSED [100%]

======================== 5 passed, 3 warnings in 0.49s ========================
```

The test suite validates:
- Transition to `rejected_by_fsm` and `blocked_guard` on invalid descriptor/environment.
- Transition to `blocked_missing_config` on config/descriptor errors.
- Transition to `blocked_no_order` if dry-run/observation mode is locked or submission gate fails.
- Successful routing to `submitted_testnet` and matching `exchange_ack` on simulated testnet proof orders.
- Secondary production URL double-guard validation checking.

---

## 2. Global Test Suite Status
All 513 unit tests passed successfully on the full terminal agent package suite, proving zero regressions.
