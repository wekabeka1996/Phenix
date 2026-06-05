# Phase 5 Package 5H Report — Config/Schema Validation Tooling

## 1. Executive Verdict

**DONE**

Package 5H implements bounded config/schema validation tooling for the offline simulator stack. New module `config_schema_validator.py` provides three public APIs: config-file validation, schema-set compilation, and preflight orchestration. All 182 simulator tests pass (133 from 5A-5F + 20 from 5G + 29 new from 5H). No forbidden files modified.

## 2. Scope Implemented

| Deliverable | Status |
|---|---|
| `config_schema_validator.py` module | Done |
| `validate_simulator_config_file()` API | Done |
| `validate_simulator_schema_set()` API | Done |
| `validate_simulator_paths()` API | Done |
| `run_simulator_preflight()` API | Done |
| `__init__.py` exports updated | Done |
| Focused test suite (29 tests) | Done |
| Report | Done |

## 3. FACTS

1. **New module**: `apps/reference/domains/alpha_search/judge/simulator/config_schema_validator.py` contains four public functions.
2. **Config validation** reuses the same loading logic as 5F CLI (`load_simulator_config`) but is independently importable without the full CLI module.
3. **Schema-set validation** compiles all three simulator-owned schemas (`outcome_input_v1.json`, `calibration_dataset_v1.json`, `summary_report_v1.json`) using `jsonschema.Draft7Validator.check_schema()`.
4. **Path checks** verify: input existence, output parent dir viability, no calibration/summary path collision, no output-input path collision.
5. **Preflight orchestration** chains config + schemas + paths and returns a structured dict without running the simulator or writing outputs.
6. **182 tests pass** across the full simulator test suite (5A-5H).
7. **No forbidden files modified**: `contracts.py`, `judge/config_models.py`, `verdict_synthesizer.py`, `decision_making/*`, `execution_position/*`, `main.py` (no 5H changes), `config_loader.py` — all verified clean.

## 4. INFERENCES

1. The `validate_simulator_config_file` function duplicates the YAML loading logic from `cli.load_simulator_config` rather than importing it. This avoids a dependency on the CLI module for preflight-only use cases, while the logic is trivial (10 lines) and unlikely to diverge.
2. The path validator creates missing output parent directories as a side effect. This is necessary because output paths often point to `./artifacts/` which may not exist yet. The behavior is documented.
3. The preflight summary always runs all three checks independently (config, schemas, paths) except that paths are skipped when config fails (since path check requires a loaded config).

## 5. ASSUMPTIONS

1. **Schema directory location**: Schemas are always at `simulator/schemas/` relative to the module. The `schemas_dir` override is provided for testing only.
2. **Path collision detection**: Uses `Path.resolve()` for comparing paths. This handles symlinks and relative paths correctly on the target platform.
3. **Output parent dir creation**: Creating missing output directories during preflight is acceptable since the simulator would need to create them anyway.

## 6. UNKNOWNS

1. Whether the operator has additional custom schemas beyond the three simulator-owned ones — the validator only checks the known inventory.
2. Whether path permissions (write access) should be checked beyond directory existence — currently not checked to avoid platform-specific filesystem edge cases.

## 7. Files Added

| File | Purpose |
|---|---|
| `apps/reference/domains/alpha_search/judge/simulator/config_schema_validator.py` | Validator module (4 public functions) |
| `tests/domains/alpha_search/judge/simulator/test_config_schema_validator.py` | 29 focused tests |

## 8. Files Modified

| File | Change |
|---|---|
| `apps/reference/domains/alpha_search/judge/simulator/__init__.py` | Added exports for 4 new public functions |

## 9. Exact Validator API Implemented

```python
# 1. Config-file validation
validate_simulator_config_file(config_path: str | Path) -> SimulatorConfig
    # Raises: FileNotFoundError, ValueError

# 2. Schema-set validation
validate_simulator_schema_set(schemas_dir: str | Path | None = None) -> dict[str, object]
    # Returns: {"ok": True, "schemas": {name: {"path": ..., "title": ...}}}
    # Raises: FileNotFoundError, ValueError

# 3. Path checks
validate_simulator_paths(config: SimulatorConfig) -> dict[str, object]
    # Returns: {"ok": True, "notes": [...]}
    # Raises: ValueError

# 4. Preflight orchestration
run_simulator_preflight(config_path: str | Path, schemas_dir: str | Path | None = None) -> dict[str, object]
    # Returns: {"config_ok", "schemas_ok", "paths_ok", "validated_config_path", "validated_schema_paths", "notes"}
    # Never raises — failures captured in notes
```

## 10. Exact Preflight/Path/Schema Checks Implemented

### Config-file checks:
- File exists and is a file
- YAML parses without error
- Root value is a mapping
- `judge_simulator` key present and is a mapping
- All fields pass `SimulatorConfig` Pydantic validation (types, ranges, non-empty paths)

### Path checks:
- `judge_logs_path` exists
- `outcome_data_path` exists
- Parent directory for `calibration_dataset_path` exists or is creatable
- Parent directory for `summary_report_path` exists or is creatable
- `calibration_dataset_path` != `summary_report_path` (resolved)
- No output path collides with any input path (resolved)

### Schema-set checks:
- All three schema files exist: `outcome_input_v1.json`, `calibration_dataset_v1.json`, `summary_report_v1.json`
- All parse as valid JSON
- All compile successfully via `Draft7Validator.check_schema()`

### Preflight orchestration:
- Runs config, schemas, paths in sequence
- Config failure skips paths (but schemas still checked)
- Returns deterministic summary with `config_ok`, `schemas_ok`, `paths_ok`, `validated_config_path`, `validated_schema_paths`, `notes`
- Never runs the simulator
- Never writes outputs (except creating missing output parent dirs)

## 11. Exact Reuse Integration Implemented

**None.** The validator is not wired into 5F CLI or 5G shutdown. It is available as a standalone preflight tool. This keeps the existing 5F/5G behavior untouched. Wiring can be added in a future package if needed.

## 12. Validation Evidence

### Test commands and results

```
$ python -m pytest tests/domains/alpha_search/judge/simulator/test_config_schema_validator.py -q
29 passed in 1.45s

$ python -m pytest tests/domains/alpha_search/judge/simulator/ -q
182 passed in 3.40s
```

### Breakdown by package:

| Test file | Tests | Status |
|---|---|---|
| `test_config_models.py` (5A) | 9 | PASS |
| `test_fee_slippage_calculator.py` (5B) | 14 | PASS |
| `test_disagreement_analyzer.py` (5C) | 12 | PASS |
| `test_expert_accuracy_reporter.py` (5C) | 5 | PASS |
| `test_calibration_dataset_writer.py` (5D) | 11 | PASS |
| `test_summary_report_writer.py` (5E) | 30 | PASS |
| `test_simulator_engine.py` (5A) | 26 | PASS |
| `test_cli.py` (5F) | 26 | PASS |
| `test_shutdown_integration.py` (5G) | 20 | PASS |
| **test_config_schema_validator.py (5H)** | **29** | **PASS** |

### Proof: config validation works
- `TestConfigFileValidation::test_valid_config_accepted` — valid config returns SimulatorConfig
- `TestConfigFileValidation::test_malformed_yaml_rejected` — tab-indent YAML raises ValueError
- `TestConfigFileValidation::test_missing_judge_simulator_key_rejected` — missing key raises ValueError
- `TestConfigFileValidation::test_missing_required_field_rejected` — incomplete config raises
- `TestConfigFileValidation::test_invalid_fee_value_rejected` — negative fee raises
- `TestConfigFileValidation::test_empty_path_rejected` — empty string raises
- `TestConfigFileValidation::test_whitespace_path_rejected` — whitespace-only raises
- `TestConfigFileValidation::test_missing_config_file_rejected` — FileNotFoundError
- `TestConfigFileValidation::test_non_mapping_yaml_rejected` — list YAML raises
- `TestConfigFileValidation::test_judge_simulator_not_mapping_rejected` — string value raises

### Proof: schema validation works
- `TestSchemaSetValidation::test_all_simulator_schemas_compile` — all 3 schemas compile
- `TestSchemaSetValidation::test_schema_titles_present` — all have titles
- `TestSchemaSetValidation::test_missing_schema_file_rejected` — FileNotFoundError
- `TestSchemaSetValidation::test_invalid_json_schema_rejected` — invalid JSON raises
- `TestSchemaSetValidation::test_schema_compilation_failure_rejected` — invalid schema raises

### Proof: preflight path checks work
- `TestPathChecks::test_valid_paths_accepted` — valid paths return ok
- `TestPathChecks::test_missing_judge_logs_path_rejected` — nonexistent logs raises
- `TestPathChecks::test_missing_outcome_data_path_rejected` — nonexistent outcomes raises
- `TestPathChecks::test_identical_calibration_summary_paths_rejected` — same file raises
- `TestPathChecks::test_output_colliding_with_input_rejected` — collision raises
- `TestPathChecks::test_output_parent_dir_created` — deep dir created

### Proof: Package 5A-5G behavior still works
All 153 pre-5H tests pass unchanged (see breakdown above).

### Proof: no forbidden Phase 1-4 production files modified
```
$ git diff HEAD -- apps/reference/domains/alpha_search/judge/contracts.py
(empty)
$ git diff HEAD -- apps/reference/domains/alpha_search/judge/config_models.py
(empty)
$ git diff HEAD -- apps/reference/domains/alpha_search/judge/verdict/verdict_synthesizer.py
(empty)
$ git diff HEAD -- apps/reference/config_loader.py
(empty)
```
`main.py` and `decision_making/*` and `execution_position/*` have pre-existing uncommitted diffs from earlier work but zero changes from Package 5H.

## 13. Regression Statement

- All 153 existing 5A-5G tests continue to pass unchanged.
- No Phase 1-4 files were touched.
- No `JudgeCortexConfig` mode admission was widened.
- No `hybrid_advisory` mode was introduced.
- No runtime events were added.
- No imports from simulator code were added to any live runtime module.
- `__init__.py` changes are additive exports only.

## 14. What Remains Deferred Beyond 5H

1. **CLI integration**: `validate_simulator_config_file()` and `run_simulator_preflight()` are not wired into 5F CLI `main()`. Can be added as a `--preflight` flag in a future package.
2. **Shutdown integration**: Preflight is not called from 5G shutdown path. Can be wired if needed.
3. **Write permission checks**: Path validation checks directory existence but not write permissions. Platform-specific permission checks are deferred.
4. **Custom schema extensions**: Only the three known simulator schemas are validated. Custom or future schemas would need inventory updates.
5. **Phase 6**: Promotion review, mode widening, advisory integration — all deferred.

## 15. Risks/Caveats

1. **Config loading duplication**: `validate_simulator_config_file()` duplicates 10 lines of YAML loading from `cli.load_simulator_config()`. This is intentional to avoid CLI module dependency, but the two should stay in sync if loading logic changes.
2. **Output dir creation side effect**: `validate_simulator_paths()` creates missing parent directories for output paths. This is a write side effect during what is otherwise a read-only preflight. Documented and intentional.
3. **Path resolution**: Uses `Path.resolve()` for collision detection. On Windows with junction points or non-standard filesystem layouts, resolution behavior may differ from Linux.
