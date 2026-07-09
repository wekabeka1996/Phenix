# CLI Agent Session Contract Validation

## Unit Test Output Trace
Unit tests were executed under Python 3.14.3 inside the project virtual environment.

```powershell
C:\Users\user\Music\Phenix\.venv\Scripts\python.exe -m pytest tools/deepseek-terminal-agent/tests/test_agent_session_contract.py
```

### Execution Output:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\user\Phenix\p36e-cli-agent-session-contract-secondary-20260709\tools\deepseek-terminal-agent
configfile: pyproject.toml
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 4 items

tools\deepseek-terminal-agent\tests\test_agent_session_contract.py ....  [100%]

============================== 4 passed in 0.27s ==============================
```

## Proved Behaviors
1. **Trading Fields Rejection**: Verified that introducing keys such as `order`, `sizing`, `leverage`, `quantity`, or `notional` raises a Pydantic `ValidationError`.
2. **Termination Conditions**: Confirmed that the loop continuation check returns `False` when max iterations or max runtimes are reached.
3. **SOS State Transitions**: Confirmed that `apply_timer_tick_to_session_state` properly transitions the state, clearing pending SOS flags, advancing version, and updating intervals.
4. **Action Serializers**: Verified that the proposal builder helper produces a non-executable envelope with the appropriate parameters.
