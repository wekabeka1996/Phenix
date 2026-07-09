# CLI Event Audit Invariant Validation

## Unit Test Output Trace
Unit tests were executed under Python 3.14.3 inside the project virtual environment.

```powershell
C:\Users\user\Music\Phenix\.venv\Scripts\python.exe -m pytest tools/deepseek-terminal-agent/tests/test_agent_action_audit.py
```

### Execution Output:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\user\Phenix\p37e-fsm-event-audit-invariants-secondary-20260709\tools\deepseek-terminal-agent
configfile: pyproject.toml
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 4 items

tools\deepseek-terminal-agent\tests\test_agent_action_audit.py ....      [100%]

============================== 4 passed in 0.44s ==============================
```

## Proved Behaviors
1. **Attribution and Testnet Validation**: Command model checks valid schema structure and forces `testnet_only` constraint.
2. **Credential Sanitization**: Recursively identifies and rejects `api_key` and other sensitive payload keys.
3. **Fail-Closed Registration**: Blocks unregistered action kinds and changes status to `pending_fsm`.
4. **Sequence Reconstruction**: Successfully transitions command states through chronological steps and restricts backward sequence moves.
