# R7O Test Outputs

## Environment
- Python: `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe`
- OS: Windows

## Command 1
```powershell
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/config/test_position_policy_sidecar_config_contract.py tests/config/test_execution_position_contracts.py tests/contracts/test_position_policy_sidecar_contracts.py tests/domains/execution_position/test_position_policy_sidecar_peak_giveback.py tests/domains/execution_position/test_position_policy_sidecar_schema_refs.py tests/domains/execution_position/test_position_policy_sidecar.py tests/domains/execution_position/test_portfolio_field_splitbrain_fix.py tests/domains/execution_position/test_position_policy_sidecar_recommendation_dedup.py -q
```
Result:
- Initially failed on unresolved schema `$ref` in `tests/contracts/test_position_policy_sidecar_contracts.py`.
- Action: added local resolver store for common schema.

## Command 2
```powershell
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_position_policy_sidecar_peak_giveback.py tests/contracts/test_position_policy_sidecar_contracts.py tests/domains/execution_position/test_position_policy_sidecar_schema_refs.py -q
```
Result:
- 2 failures in shadow-nullability expectations.
- Action:
  - Runtime fix: when economics missing, notional is not synthesized.
  - Runtime fix: `threshold_met_under_current_giveback_trigger_pct` is nullable when economics/notional missing.
  - Test fix: missing-notional case reads suppressed payload path.

## Command 3
```powershell
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_position_policy_sidecar_peak_giveback.py -q
```
Result:
- `6 passed in 1.51s`

## Final Validation Command
```powershell
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/config/test_position_policy_sidecar_config_contract.py tests/config/test_execution_position_contracts.py tests/contracts/test_position_policy_sidecar_contracts.py tests/domains/execution_position/test_position_policy_sidecar_peak_giveback.py tests/domains/execution_position/test_position_policy_sidecar_schema_refs.py tests/domains/execution_position/test_position_policy_sidecar.py tests/domains/execution_position/test_portfolio_field_splitbrain_fix.py tests/domains/execution_position/test_position_policy_sidecar_recommendation_dedup.py -q
```
Result:
- `132 passed in 23.74s`
