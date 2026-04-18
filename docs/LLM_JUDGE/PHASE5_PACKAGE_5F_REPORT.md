# Phase 5 Package 5F Report — CLI Harness

**Date**: 2026-04-18
**Package**: 5F (CLI Harness)
**Phase**: Phase 5 — Shadow Economic Simulator
**Author**: Claude Agent (Opus 4.6)

---

## 1. Executive Verdict

**DONE**

Package 5F implements a bounded CLI harness for the Phase 5 offline judge simulator. All 133 tests pass (107 pre-existing 5A–5E + 26 new 5F). No forbidden Phase 1–4 production files were modified. No runtime behavior was changed.

---

## 2. Scope Implemented

| Component | Status |
|---|---|
| CLI harness module (`cli.py`) | DONE |
| Config loading from YAML | DONE |
| Simulation orchestration via `run_simulation()` | DONE |
| Calibration dataset write via 5D writer | DONE |
| Summary report write via 5E writer | DONE |
| Exit code policy | DONE |
| `__init__.py` export update | DONE |
| Focused tests (`test_cli.py`) | DONE |
| Package 5F report | DONE |

---

## 3. FACTS

1. `cli.py` is placed at `apps/reference/domains/alpha_search/judge/simulator/cli.py` per the blueprint.
2. `load_simulator_config()` reads YAML, extracts the `judge_simulator` key, and validates through the existing `SimulatorConfig` Pydantic model.
3. `run_from_config()` calls `run_simulation(config)`, `write_calibration_dataset()`, and `write_summary_report()` in sequence.
4. `main(argv)` provides a bounded CLI entry point with `argparse`, explicit exit codes, and minimal console output.
5. The config file path defaults to `config/judge_simulator.yaml` if `--config` is not supplied.
6. The CLI validates that `judge_logs_path` and `outcome_data_path` exist before calling the engine.
7. The calibration writer's create-only policy (fail if file exists) is preserved — the CLI does not override or pre-delete.
8. The summary writer's explicit-overwrite policy is preserved.
9. No imports from `cli.py` into any live runtime module exist.
10. 133 tests pass across the full 5A–5F suite.

---

## 4. INFERENCES

1. The `yaml` package (PyYAML) is already a project dependency, inferred from existing usage in the codebase.
2. The default config path `config/judge_simulator.yaml` is consistent with the file created in Package 5A.
3. Catching `EXIT_SIMULATION_FAILURE` for both engine errors and writer errors (since writers are called inside `run_from_config`) is acceptable because the CLI surfaces the error message to stderr.

---

## 5. ASSUMPTIONS

1. The operator will invoke the CLI manually or from a script; no auto-invocation from `main.py` or `backtest_plugin.shutdown()` is intended in 5F.
2. The `yaml` library is available in the runtime Python environment (it is a standard dependency for this project).

---

## 6. UNKNOWNS

1. Whether the calibration writer's create-only policy will require operator cleanup between repeated CLI runs (the writer raises `FileExistsError` if the calibration output already exists).

---

## 7. Files Added

| File | Purpose |
|---|---|
| `apps/reference/domains/alpha_search/judge/simulator/cli.py` | CLI harness module |
| `tests/domains/alpha_search/judge/simulator/test_cli.py` | 26 focused tests |

---

## 8. Files Modified

| File | Change |
|---|---|
| `apps/reference/domains/alpha_search/judge/simulator/__init__.py` | Added CLI exports: `load_simulator_config`, `run_from_config`, `cli_main`, exit code constants |

---

## 9. Exact CLI API Implemented

```python
# Exit codes
EXIT_SUCCESS = 0
EXIT_BAD_CONFIG = 1
EXIT_MISSING_INPUT = 2
EXIT_SIMULATION_FAILURE = 3
EXIT_WRITE_FAILURE = 4

def load_simulator_config(config_path: str | Path) -> SimulatorConfig:
    """Load and validate SimulatorConfig from a YAML file."""

def run_from_config(config: SimulatorConfig) -> SimulationResult:
    """Run simulation + write calibration dataset + write summary report."""

def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns exit code."""
```

**CLI arguments:**
- `--config PATH` — Path to simulator YAML config (default: `config/judge_simulator.yaml`)

---

## 10. Exact Config-Loading Behavior

1. Reads YAML file at specified path
2. Extracts `judge_simulator` key (required)
3. Validates the section is a mapping
4. Constructs `SimulatorConfig(**section)` — Pydantic validates all fields
5. Raises `FileNotFoundError` if file missing, `ValueError` if YAML malformed or key missing

**Config fields used:**
- `judge_logs_path` — input verdict JSONL directory/file
- `outcome_data_path` — input outcome JSON file
- `calibration_dataset_path` — output calibration JSONL
- `summary_report_path` — output summary JSON
- `fee_per_cycle_bps` — fee modeling parameter
- `slippage_pct` — slippage modeling parameter

---

## 11. Exact Output Orchestration

1. `run_simulation(config)` → `SimulationResult` (5A engine, enriched by 5B/5C/5D/5E)
2. `write_calibration_dataset(records=result.calibration_records, output_path=config.calibration_dataset_path)` → JSONL file (5D writer, create-only)
3. `write_summary_report(report=result.summary_report, output_path=config.summary_report_path)` → JSON file (5E writer, explicit-overwrite)

Each writer's file policy is preserved exactly as documented in their respective packages.

---

## 12. Validation Evidence

### Test Commands and Results

```
$ python -m pytest tests/domains/alpha_search/judge/simulator/test_config_models.py -q
9 passed

$ python -m pytest tests/domains/alpha_search/judge/simulator/test_fee_slippage_calculator.py -q
14 passed

$ python -m pytest tests/domains/alpha_search/judge/simulator/test_disagreement_analyzer.py -q
12 passed

$ python -m pytest tests/domains/alpha_search/judge/simulator/test_expert_accuracy_reporter.py -q
5 passed

$ python -m pytest tests/domains/alpha_search/judge/simulator/test_calibration_dataset_writer.py -q
11 passed

$ python -m pytest tests/domains/alpha_search/judge/simulator/test_summary_report_writer.py -q
30 passed

$ python -m pytest tests/domains/alpha_search/judge/simulator/test_simulator_engine.py -q
26 passed

$ python -m pytest tests/domains/alpha_search/judge/simulator/test_cli.py -q
26 passed

$ python -m pytest tests/domains/alpha_search/judge/simulator/ -q
133 passed
```

### CLI Success Path Proof
- `TestCLIRunPath::test_main_returns_zero_on_success` — exit code 0
- `TestCLIRunPath::test_calibration_dataset_written` — file exists with valid records
- `TestCLIRunPath::test_summary_report_written` — file exists with schema_version=1
- `TestCLIRunPath::test_run_from_config_returns_result` — SimulationResult returned with correct counts

### CLI Failure Path Proof
- `TestCLIFailureBehavior::test_missing_config_file_returns_bad_config` — exit code 1
- `TestCLIFailureBehavior::test_malformed_config_returns_bad_config` — exit code 1
- `TestCLIFailureBehavior::test_missing_input_returns_missing_input` — exit code 2
- `TestCLIFailureBehavior::test_invalid_outcome_returns_simulation_failure` — exit code 3
- `TestCLIFailureBehavior::test_calibration_writer_failure_surfaced` — exit code 3
- `TestCLIFailureBehavior::test_summary_writer_failure_surfaced` — exit code 3

### Output Correctness Proof
- `TestOutputCorrectness::test_deterministic_double_run` — identical summary across two runs
- `TestOutputCorrectness::test_calibration_records_have_correct_cohorts` — all cohorts valid
- `TestCLIRunPath::test_calibration_is_valid_jsonl` — each line is valid JSON with schema_version
- `TestCLIRunPath::test_summary_has_all_required_keys` — all 9 required top-level keys present

### Package 5A–5E Non-Regression Proof
- 107 pre-existing tests continue to pass unchanged
- `test_config_models.py`: 9 passed
- `test_fee_slippage_calculator.py`: 14 passed
- `test_disagreement_analyzer.py`: 12 passed
- `test_expert_accuracy_reporter.py`: 5 passed
- `test_calibration_dataset_writer.py`: 11 passed
- `test_summary_report_writer.py`: 30 passed
- `test_simulator_engine.py`: 26 passed

### Forbidden File Modification Proof
No modifications to:
- `apps/reference/domains/alpha_search/judge/contracts.py` ✓
- `apps/reference/domains/alpha_search/judge/config_models.py` ✓
- `apps/reference/domains/alpha_search/judge/verdict/verdict_synthesizer.py` ✓
- `apps/reference/domains/alpha_search/backtest_plugin.py` ✓
- `apps/reference/domains/decision_making/*` ✓
- `apps/reference/domains/execution_position/*` ✓
- `apps/reference/main.py` ✓
- `apps/reference/config_loader.py` ✓

---

## 13. Regression Statement

All 133 tests across the full 5A–5F simulator test suite pass. No Phase 1–4 production files were modified. No runtime behavior was changed. The `__init__.py` modification is additive only (new exports appended).

---

## 14. What Remains Deferred to Package 5G+

1. **Integration into `backtest_plugin.shutdown()`** — explicitly out of scope for 5F
2. **Test harness + shared fixtures** — Package 5G scope
3. **Config schema validation tooling** — Package 5H scope
4. **Phase 6 promotion review logic** — not in Phase 5
5. **`__main__.py` for `python -m ... simulator`** — possible 5G convenience

---

## 15. Risks / Caveats

1. **Calibration create-only policy**: The 5D writer raises `FileExistsError` if the calibration output already exists. Operators must delete or move the file between CLI runs. This is the documented 5D writer behavior, not a 5F deficiency.
2. **No `__main__.py`**: The CLI is invoked via `from simulator.cli import main; main()` or by adding a script entry point. A `__main__.py` wrapper could be added in 5G for convenience.
3. **`yaml` dependency**: The CLI depends on PyYAML for config loading. This is already used elsewhere in the project but is not explicitly declared as a simulator dependency.
