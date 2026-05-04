# R7H Test Outputs

## Validation Commands

### Core code health
```text
get_errors on:
- apps/reference/domains/position_tracking/position_tracking.py
- apps/reference/domains/decision_making/contracts/schemas.py
```
Result: no errors found.

### Focused package validation
```text
Set-Location 'c:/Users/user/Music/Phenix'; .\.venv\Scripts\python.exe -m pytest tests\contracts\test_portfolio_state_symbol_economics_schema.py tests\domains\decision_making\test_portfolio_state_payload_schema_v1.py tests\domains\position_tracking\test_portfolio_state_symbol_economics_export.py tests\domains\execution_position\test_position_policy_sidecar.py tests\domains\execution_position\test_position_policy_sidecar_peak_giveback.py tests\domains\execution_position\test_portfolio_field_splitbrain_fix.py -q
```
Result: 55 passed in 1.86s.

## Coverage Notes
- Contract validation covered valid, nullable, unknown-field, and malformed-economics cases for the portfolio-state schema.
- PositionTracking validation covered long, short, and missing-mark export behavior.
- Sidecar validation covered canonical `markPrice` / `unrealizedPnl` / `unrealizedPnlPct` consumption and preserved null-reason fail-closed behavior.

## Tooling Note
- The VS Code `runTests` helper did not resolve the file paths in this workspace, so the authoritative validation was the terminal `pytest` run above.
