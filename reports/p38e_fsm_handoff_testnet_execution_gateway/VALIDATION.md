# Validation Proofs

## 1. Test Command Executed
All validations and execution scenarios are fully tested in `tools/deepseek-terminal-agent/tests/test_agent_action_audit.py` using `pytest`.

```bash
python -m pytest tools/deepseek-terminal-agent/tests/test_agent_action_audit.py
```

## 2. Test Execution Output Proof
```
platform win32 -- Python 3.14.3, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\user\Phenix\Phenix\tools\deepseek-terminal-agent
configfile: pyproject.toml
plugins: anyio-4.11.0, aiohttp-1.1.0, asyncio-1.2.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 5 items

tools\deepseek-terminal-agent\tests\test_agent_action_audit.py .....     [100%]

======================== 5 passed, 3 warnings in 0.62s ========================
```

## 3. Proven Status Sequences
The following test scenarios succeed and verify status paths:
1. **Invalid kind rejection**: status transitions to `rejected_by_fsm` on `UNKNOWN_KIND`.
2. **Missing/invalid side rejection**: status transitions to `rejected_by_fsm` when `side` is not present or invalid.
3. **Missing explicit quantity/notional rejection**: status transitions to `rejected_by_fsm` when order payload is empty.
4. **Invalid quantity <= 0 rejection**: status transitions to `rejected_by_fsm` when quantity is `0` or negative.
5. **Missing adapter rejection**: status transitions to `rejected_by_fsm` if `execution_adapter` is `None`.
6. **Non-testnet base URL adapter rejection**: status transitions to `rejected_by_fsm` when adapter base URL points to a production environment.
7. **Valid handoff and successful execution**: transitions sequence:
   `recorded` -> `pending_fsm` -> `accepted_by_fsm` -> `submitted_testnet` -> `exchange_ack` -> `lifecycle_closed`.
8. **Valid handoff but execution failure**: transitions sequence:
   `recorded` -> `pending_fsm` -> `accepted_by_fsm` -> `submitted_testnet` -> `exchange_reject` -> `lifecycle_closed`.
