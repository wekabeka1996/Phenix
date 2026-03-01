# EP-WATCHDOG-POLLING-DEFERRED-BRACKETS-TIMEOUT-ISOLATION REPORT

## Summary
Isolated and fixed watchdog timeout in deferred-brackets polling test by disabling unintended background bracket health loop in async test context.

## Files changed
- `tests/domains/execution_position/test_watchdog_polling_deferred_brackets.py`

## Root cause
- In async test run, `ExecPosFSM` scheduled `_bracket_health_loop` from config.
- Fixture carried dynamic/mocked config values causing repeated background loop errors/noise, leading to watchdog slice timeouts.

## Fix
- Explicitly disable `fsm_config.domains.execution_position.bracket_health_check` in the test before `ExecPosFSM` initialization.

## Validation commands
- `pytest -q tests/domains/execution_position/test_watchdog_polling_deferred_brackets.py -k fill_triggers --maxfail=1 -vv` → **1 passed**
- `pytest -vv tests/domains/execution_position -k "watchdog" --maxfail=1 -x` → **10 passed**
- `pytest tests/domains/execution_position -k "watchdog" --durations=25 --maxfail=1` → **10 passed**
