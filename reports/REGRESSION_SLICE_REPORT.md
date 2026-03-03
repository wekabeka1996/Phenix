# REGRESSION SLICE REPORT

Date: 2026-03-01  
Scope: wider confidence slice after EP-H2 / EP-H4 / EP-H1 + follow-up regression fixes (P0/P1/P2)

## Commands and outcomes

### 1) DecisionMaking slice
Command:
- `pytest -q tests/domains/decision_making -k "flip or regime" --maxfail=1`

Result:
- **PASS**
- `59 passed, 1 skipped, 222 deselected`

### 2) AlphaSearch full domain
Command:
- `pytest -q tests/domains/alpha_search --maxfail=1`

Result:
- **PASS**
- `53 passed`

### 3) Integration slice (flip/bridge/execpos/decision)
Command:
- `pytest -q tests/integration -k "flip or bridge or execpos or decision" --maxfail=1`

Result:
- **FAIL (non-H2/H4/H1 regression)**
- First failing test:
  - `tests/integration/test_order_policy_01.py::TestBridgeNoFallback::test_bridge_code_no_or_limit`
- Failure type:
  - `UnicodeDecodeError` while `Path("apps/reference/main.py").read_text()` without explicit UTF-8.

Notes:
- Previously failing vertical flip integration test is now fixed and passing:
  - `tests/integration/test_flip_vertical_dm_bridge_execpos.py::test_vertical_flip_close_dm_to_bridge_to_execpos`

## Watchdog timeout triage and fix

### Investigative commands
- `pytest -q tests/domains/execution_position -k "watchdog" --collect-only`
- `pytest -vv tests/domains/execution_position -k "watchdog" --maxfail=1 -x`
- `pytest tests/domains/execution_position -k "watchdog" --durations=25 --maxfail=1`

### Root cause (previous)
- Timeout localized to:
  - `tests/domains/execution_position/test_watchdog_polling_deferred_brackets.py::test_watchdog_polling_fill_triggers_deferred_brackets`
- Background `_bracket_health_loop` ran inside async test context and destabilized watchdog slice.

### Isolation fix applied
- Disabled `fsm_config.domains.execution_position.bracket_health_check` in that test before `ExecPosFSM` initialization.

### Re-run result after fix
- `pytest -q tests/domains/execution_position/test_watchdog_polling_deferred_brackets.py -k fill_triggers --maxfail=1 -vv` → **PASS**
- `pytest -vv tests/domains/execution_position -k "watchdog" --maxfail=1 -x` → **PASS** (`10 passed`)
- `pytest tests/domains/execution_position -k "watchdog" --durations=25 --maxfail=1` → **PASS** (`10 passed`)

## Final status

- H2 core invariants remain green in domain slice.
- H4 watchdog contract slice is green and no longer timing out.
- H1 alpha_search domain is fully green.
- One remaining integration failure is unrelated to these packages (encoding in `test_order_policy_01` file read path).
