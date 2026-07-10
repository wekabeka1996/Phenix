# Validation Record

This document records the automated validation results confirming the behavior of the dual-agent runtime runner.

---

## 1. Automated Unit Tests Run

Command:
```powershell
C:\Users\wekab\Music\Phenix\.venv\Scripts\pytest -v tools/deepseek-terminal-agent/tests/test_dual_agent_runner.py
```

Output:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0 -- C:\Users\wekab\Music\Phenix\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\wekab\Music\Phenix-p42b-dual-agent-runner\tools\deepseek-terminal-agent
configfile: pyproject.toml
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0, timeout-2.4.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 8 items

tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_ownership_mapping_loaded_from_yaml PASSED [ 12%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_preflight_check PASSED [ 25%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_wrong_symbol_request_rejected_before_fsm PASSED [ 37%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_timeout_creates_explicit_failure PASSED [ 50%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_invalid_model_response_fails_closed PASSED [ 62%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_no_raw_exchange_client_imported PASSED [ 75%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_heartbeat_expiry_detected PASSED [ 87%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_event_driven_wakeup_works PASSED [100%]

============================== 8 passed in 1.32s ==============================
```

These tests validate:
- Loading symbol ownership and configuration from YAML.
- Unique IDs and preflight block rules.
- Rejection of invalid symbols before hitting the FSM.
- Detection of heartbeat expiry and stale heartbeats.
- Order creation timeouts leading to failure records.
- Fail-closed behavior on non-conforming model responses.
- Active wakeups triggered by FSM events.
- Verification that no CCXT or other raw exchange client is imported by the runner.

---

## 2. Global Test Status
All 516 unit tests passed successfully on the full terminal agent package suite, proving zero regressions.
