# VALIDATION RECORD

This document logs the validation tests for the preflight attestation and ancestry checking logic.

---

## 1. Test Suite Results

We executed the runner test suite including our newly created attestation test:

Command:
```powershell
C:\Users\wekab\Music\Phenix\.venv\Scripts\pytest tools/deepseek-terminal-agent/tests/test_dual_agent_runner.py -vv
```

Output:
```text
============================= test session starts =============================
collected 9 items

tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_ownership_mapping_loaded_from_yaml PASSED [ 11%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_preflight_check PASSED [ 22%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_wrong_symbol_request_rejected_before_fsm PASSED [ 33%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_timeout_creates_explicit_failure PASSED [ 44%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_invalid_model_response_fails_closed PASSED [ 55%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_no_raw_exchange_client_imported PASSED [ 66%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_heartbeat_expiry_detected PASSED [ 77%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_event_driven_wakeup_works PASSED [ 88%]
tools\deepseek-terminal-agent\tests\test_dual_agent_runner.py::test_preflight_attestation_validation PASSED [100%]

============================== 9 passed in 1.40s ==============================
```

---

## 2. Test Case Scenarios

The `test_preflight_attestation_validation` test systematically verifies three scenarios:

- **Scenario A (Exact Match)**: If `checkout_sha` equals `runtime_code_sha` (0 diffs), the preflight verification passes cleanly and writes the JSON attestation file.
- **Scenario B (Allowed Diff)**: If `checkout_sha` is a child of `runtime_code_sha` and all differences are restricted to `reports/**` (e.g. `reports/p42g_unified_dual_agent_runtime/RUN_READY_GATE.md`), the preflight verification passes and writes the JSON file with the new HEAD hash.
- **Scenario C (Disallowed Diff)**: If there are source modifications (e.g., changes under `apps/`), the preflight check fails closed, raising a `ValueError`.
