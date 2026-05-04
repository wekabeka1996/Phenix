# R7C Test Outputs

## Command 1

`c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_position_policy_sidecar_peak_giveback.py -q`

- Result: `3 passed in 2.68s`
- Purpose: verify no peak-giveback behavior drift after the first sidecar observability edit.

## Command 2

`c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_position_policy_sidecar_peak_giveback.py tests/domains/execution_position/test_position_policy_sidecar.py::test_position_policy_sidecar_recommends_and_emits_bounded_close_request_in_enable_mode tests/domains/execution_position/test_position_policy_sidecar.py::test_execpos_position_policy_sidecar_mode_wiring_and_ordering tests/contracts/test_position_policy_sidecar_contracts.py -q`

- Result: `14 passed in 1.11s`
- Purpose: validate startup config snapshot, peak-giveback observability fields, recommendation provenance, and schema conformance.

## Command 3

`c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/tools/test_position_policy_sidecar_validation.py -q`

- Result: `13 passed in 1.18s`
- Purpose: confirm richer sidecar runtime rows remain compatible with the existing forensic validation tool.

## Coverage of Package Intent

- Startup/config observability: covered by the mode-active wiring test and schema contract test.
- Economics on evaluated/scores/suppressed/recommended/close-request rows: covered by runtime peak-giveback tests and schema contract tests.
- Explicit null-reason semantics: covered by the missing-economics runtime test and the schema requirement for `peak_giveback_snapshot.null_reasons`.
- Trigger provenance: covered by runtime tests asserting recommendation/request `policy_source` and trigger threshold fields.
