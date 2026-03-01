# EP-H4-WATCHDOG-CONFIG-HARDENING REPORT

## Summary
Implemented targeted watchdog constructor hardening to fail fast on invalid runtime config shapes/types. This package is a **test-integrity + hardening** fix (not a runtime ImportError/MagicMock fallback remediation).

## Files changed
- `apps/reference/domains/execution_position/watchdog.py`
- `tests/domains/execution_position/test_watchdog_config_hardening.py`
- `tests/domains/execution_position/test_bracket_health_check.py`
- `JOURNAL.md`
- `TODO.md`

## Contract/result
- `OrderTimeoutWatchdog(config=None)` remains valid and uses defaults.
- Non-mapping config now raises:
  - `RuntimeError("CRITICAL: watchdog config must be mapping")`
- `rps_limit` must be strict `int`:
  - non-int raises `RuntimeError("CRITICAL: rps_limit must be int")`

## Validation commands
- `pytest -q tests/domains/execution_position/test_watchdog_config_hardening.py` → **3 passed**
- `pytest -q tests/domains/execution_position/test_bracket_health_check.py -k watchdog` → **3 passed**
- `pytest -q tests/domains/execution_position -k "watchdog"` → **timeout in unrelated async loop suite** (no watchdog contract assertion failure observed before timeout)
