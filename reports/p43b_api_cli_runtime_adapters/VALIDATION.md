# Validation

Commands and results:

```powershell
$env:PYTHONPATH="$pwd\tools\deepseek-terminal-agent\src;$pwd"
python -m pytest tools/deepseek-terminal-agent/tests/test_trading_agent_runtime.py -q
# 16 passed

python -m pytest tools/deepseek-terminal-agent/tests/test_trading_agent_runtime.py tools/deepseek-terminal-agent/tests/test_dual_agent_runner.py tools/deepseek-terminal-agent/tests/test_config.py -q
# 39 passed

python -m pytest tools/deepseek-terminal-agent/tests -q
# 559 passed, 13 skipped, 3 warnings

python -m compileall -q tools/deepseek-terminal-agent/src/deepseek_terminal_agent tools/deepseek-terminal-agent/tests/test_trading_agent_runtime.py
git diff --check
```

Covered:

- API structured JSON, configured model, token accounting, retry, timeout, cancellation, missing credentials, wrong symbol, stale collective, unauthorized tool, malformed output, and secret non-logging surface;
- CLI real local subprocess JSON protocol, heartbeat, clean shutdown, timeout, cancellation path, crash, corrupt JSON, duplicate response, forbidden executable, and approved-path boundary;
- no exchange/FSM/repository execution imports or calls in the adapter module;
- no raw order placement.

Not run:

- real API smoke: blocked by missing credential;
- configured CLI smoke: blocked by explicit `cli_command: null`/empty approved paths;
- external testnet or live trading: intentionally not in scope.

