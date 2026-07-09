# Validation Record

This document records the automated validation results confirming the FSM handoff safety checks.

---

## 1. Automated Unit Tests Run

Command:
```powershell
C:\Users\wekab\Music\Phenix\.venv\Scripts\pytest -v tools/deepseek-terminal-agent/tests/test_agent_action_audit.py
```

Output:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0 -- C:\Users\wekab\Music\Phenix\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\wekab\Music\Phenix-p39b-testnet-no-order-fsm-guard\tools\deepseek-terminal-agent
configfile: pyproject.toml
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0, timeout-2.4.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 10 items

tools\deepseek-terminal-agent\tests\test_agent_action_audit.py::test_action_command_rejects_non_testnet PASSED [ 10%]
tools\deepseek-terminal-agent\tests\test_agent_action_audit.py::test_action_command_rejects_credentials_recursively PASSED [ 20%]
tools\deepseek-terminal-agent\tests\test_agent_action_audit.py::test_action_command_missing_fsm_fails_closed PASSED [ 30%]
tools\deepseek-terminal-agent\tests\test_agent_action_audit.py::test_audit_sequence_reconstruction PASSED [ 40%]
tools\deepseek-terminal-agent\tests\test_agent_action_audit.py::test_verify_handoff_safety_non_testnet_descriptor_rejects PASSED [ 50%]
tools\deepseek-terminal-agent\tests\test_agent_action_audit.py::test_verify_handoff_safety_missing_descriptor_rejects PASSED [ 60%]
tools\deepseek-terminal-agent\tests\test_agent_action_audit.py::test_verify_handoff_safety_no_order_observation_mode_blocks PASSED [ 70%]
tools\deepseek-terminal-agent\tests\test_agent_action_audit.py::test_verify_handoff_safety_url_string_alone_insufficient PASSED [ 80%]
tools\deepseek-terminal-agent\tests\test_verify_handoff_safety_valid_passes PASSED [ 90%]
tools\deepseek-terminal-agent\tests\test_verify_handoff_safety_rejection_log_preserves_fields PASSED [100%]

============================= 10 passed in 0.15s ==============================
```

All new validation checks (non-testnet descriptors, missing descriptors, observation mode blocks, secondary URL guards, and audit trail attributes) are covered and pass.

---

## 2. Replay/Audit Log Verification
- Rejections are written out in JSON Lines format to `.agent_memory/sessions/{session_id}/audit_rejections.jsonl`.
- Tests verify the output entry fields: `agent_id`, `session_id`, `command_id`, `event_id`, `reason`, `timestamp` are fully populated.
