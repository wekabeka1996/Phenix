# Phase 5 Package 5G Report — Shutdown Integration

## 1. Executive Verdict

**DONE**

Package 5G implements bounded simulator invocation from `alpha_search/backtest_plugin.shutdown()`, config-gated enable/disable, deterministic artifact writing via existing 5F/5D/5E writers, and focused tests. All 153 simulator tests pass (133 existing 5A-5F + 20 new 5G). No forbidden files modified.

## 2. Scope Implemented

| Deliverable | Status |
|---|---|
| Config surface (`SimulatorShutdownExportConfig`) | Done |
| Alpha search YAML section | Done |
| Shutdown integration in `backtest_plugin.py` | Done |
| Config gating (disabled/enabled/invalid) | Done |
| Reuse of 5F `load_simulator_config` + `run_from_config` | Done |
| Fail-closed error handling | Done |
| Focused test suite (20 tests) | Done |
| Report | Done |

## 3. FACTS

1. **`backtest_plugin.shutdown()`** previously only generated diagnostics when `run_dir` was provided. Now it additionally calls `_run_simulator_shutdown_export()`.
2. **`SimulatorShutdownExportConfig`** is a new Pydantic model with `enabled: bool = False` and `config_path: str = ""`, with `extra="forbid"` and a model validator that rejects `enabled=True` with empty/whitespace `config_path`.
3. **`AlphaSearchConfig`** gains an optional `simulator_shutdown_export` field (default `None`).
4. **`config/alpha_search.yaml`** gains a `simulator_shutdown_export` section with `enabled: false` and `config_path: "config/judge_simulator.yaml"`.
5. **Shutdown path** reuses `cli.load_simulator_config()` (5F) and `cli.run_from_config()` (5F) which internally calls `run_simulation()` (5A), `write_calibration_dataset()` (5D), and `write_summary_report()` (5E).
6. **No code was duplicated** from 5A-5F — pure reuse via the existing public API.
7. **153 tests pass** across the full simulator test suite.
8. **No forbidden files were modified**: `contracts.py`, `judge/config_models.py`, `verdict_synthesizer.py`, `decision_making/*`, `execution_position/*`, `main.py`, `config_loader.py` — all zero diff.

## 4. INFERENCES

1. The two-gate design (alpha_search YAML `enabled` + judge_simulator YAML `enabled`) provides defense-in-depth: an operator must explicitly enable both to trigger the simulator on shutdown.
2. Using `run_from_config` as the single orchestration entry point ensures writer semantics (calibration create-only, summary overwrite) are preserved exactly as 5F defines them.
3. The fail-closed `try/except` in `_run_simulator_shutdown_export` ensures simulator failures cannot crash the broader shutdown sequence or any earlier runtime paths.

## 5. ASSUMPTIONS

1. **Shutdown ordering**: The simulator export runs after diagnostics generation. This ordering is acceptable because both are independent artifact-writing steps.
2. **No concurrency**: `shutdown()` is called once, sequentially, at end of backtest/trading session. No concurrent invocation protection was added.
3. **Writer semantics preserved**: Since we call `run_from_config` unchanged, calibration dataset writer's create-only policy and summary report writer's overwrite policy apply as-is.

## 6. UNKNOWNS

1. Whether the operator has populated `data/simulator/outcomes.json` with real outcome data — the simulator will fail with a clear error if this file is missing, which is correct fail-closed behavior.
2. Performance impact of running the full simulation pipeline at shutdown for large verdict/outcome datasets — not benchmarked.

## 7. Files Added

| File | Purpose |
|---|---|
| `tests/domains/alpha_search/judge/simulator/test_shutdown_integration.py` | 20 focused tests for 5G |

## 8. Files Modified

| File | Change |
|---|---|
| `apps/reference/domains/alpha_search/config_models.py` | Added `SimulatorShutdownExportConfig` class + `simulator_shutdown_export` field on `AlphaSearchConfig` |
| `apps/reference/domains/alpha_search/backtest_plugin.py` | Added `_run_simulator_shutdown_export()` method + call from `shutdown()` |
| `config/alpha_search.yaml` | Added `simulator_shutdown_export` section (disabled by default) |

## 9. Exact Shutdown Integration Implemented

```
shutdown(run_dir=...)
  ├── existing diagnostics generation (unchanged)
  └── _run_simulator_shutdown_export()
        ├── check config.simulator_shutdown_export is not None and enabled
        │   └── if disabled/None → return (no-op)
        ├── import cli.load_simulator_config + cli.run_from_config
        │   └── ImportError → LOG.error + return
        ├── load_simulator_config(config_path)
        │   └── FileNotFoundError/ValueError → LOG.error + return
        ├── check sim_config.enabled
        │   └── if False → LOG.info + return
        └── run_from_config(sim_config)
            ├── run_simulation() [5A]
            ├── write_calibration_dataset() [5D]
            ├── write_summary_report() [5E]
            └── Exception → LOG.error + return
```

## 10. Exact Config-Gating Behavior

| `simulator_shutdown_export` | `judge_simulator.yaml enabled` | Result |
|---|---|---|
| `None` | N/A | No-op |
| `enabled=False` | N/A | No-op |
| `enabled=True, config_path=""` | N/A | Pydantic validation error at config load |
| `enabled=True, config_path="valid"` | `False` | Config loaded, simulator skipped |
| `enabled=True, config_path="valid"` | `True` | Full simulation + write |

## 11. Exact Failure Behavior

| Failure | Handling |
|---|---|
| Missing config file | `FileNotFoundError` caught → `LOG.error` → return |
| Invalid YAML / missing key | `ValueError` caught → `LOG.error` → return |
| Import failure | `ImportError` caught → `LOG.error` → return |
| Simulation engine failure | `Exception` caught → `LOG.error` → return |
| Calibration write failure | Propagates as `Exception` from `run_from_config` → caught → `LOG.error` → return |
| Summary write failure | Propagates as `Exception` from `run_from_config` → caught → `LOG.error` → return |

All failures are fail-closed: logged and returned, never crashing the broader shutdown path.

## 12. Validation Evidence

### Test commands and results

```
$ python -m pytest tests/domains/alpha_search/judge/simulator/test_shutdown_integration.py -q
20 passed in 0.95s

$ python -m pytest tests/domains/alpha_search/judge/simulator/ -q
153 passed in 2.82s
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
| **test_shutdown_integration.py (5G)** | **20** | **PASS** |

### Proof: shutdown success path works
- `TestShutdownIntegration::test_shutdown_invokes_simulator_exactly_once` — `run_from_config` called exactly once
- `TestShutdownIntegration::test_shutdown_passes_loaded_config_to_run` — correct config propagated
- `TestConfigGating::test_enabled_config_invokes_simulator_path` — simulator path invoked when enabled

### Proof: shutdown disabled path does nothing
- `TestConfigGating::test_disabled_config_no_simulator_invocation` — `load_simulator_config` never called
- `TestConfigGating::test_none_config_no_simulator_invocation` — `load_simulator_config` never called
- `TestShutdownIntegration::test_simulator_disabled_in_yaml_skips_run` — loaded but `run_from_config` not called

### Proof: shutdown failure paths handled
- `TestFailureBehavior::test_missing_simulator_config_file_handled` — no crash on missing file
- `TestFailureBehavior::test_invalid_yaml_content_handled` — no crash on bad YAML
- `TestFailureBehavior::test_simulation_runtime_failure_handled` — no crash on engine failure
- `TestFailureBehavior::test_calibration_writer_failure_surfaces_via_run_from_config` — no crash
- `TestFailureBehavior::test_summary_writer_failure_surfaces_via_run_from_config` — no crash

### Proof: no forbidden files modified

```
$ git diff HEAD -- apps/reference/domains/alpha_search/judge/contracts.py
(empty — no changes)

$ git diff HEAD -- apps/reference/domains/alpha_search/judge/config_models.py
(empty — no changes)

$ git diff HEAD -- apps/reference/domains/alpha_search/judge/verdict/verdict_synthesizer.py
(empty — no changes)

$ git diff HEAD -- apps/reference/domains/decision_making/
(empty — no changes from this package)

$ git diff HEAD -- apps/reference/domains/execution_position/
(empty — no changes from this package)

$ git diff HEAD -- apps/reference/main.py
(empty — no changes from this package)

$ git diff HEAD -- apps/reference/config_loader.py
(empty — no changes from this package)
```

## 13. Regression Statement

- All 133 existing 5A-5F tests continue to pass unchanged.
- No Phase 1-4 files were touched.
- No `JudgeCortexConfig` mode admission was widened.
- No `hybrid_advisory` mode was introduced.
- No runtime events were added.
- No imports from simulator code were added to any live runtime module other than the bounded `backtest_plugin.py`.

## 14. What Remains Deferred Beyond 5G

1. **Package 5H**: Config schema validation tooling (next in Phase 5 sequence)
2. **Phase 6**: Promotion review decision — whether to admit `hybrid_advisory` or other modes
3. **CLI enhancements**: No CLI changes made; simulator CLI remains as-is from 5F
4. **Runtime integration**: Simulator remains offline-only; no `decision_making` advisory bridge
5. **Performance benchmarking**: No profiling of shutdown-time simulator execution for large datasets
6. **Outcome data population**: Operators must supply `outcomes.json` — no auto-generation

## 15. Risks/Caveats

1. **Double gating**: Both `simulator_shutdown_export.enabled` (alpha_search.yaml) AND `judge_simulator.enabled` (judge_simulator.yaml) must be True for the simulator to run. This is intentional defense-in-depth but operators must enable both.
2. **Shutdown timing**: The simulator runs synchronously during shutdown. For very large datasets this could delay process exit. Acceptable for offline/backtest use; operators should size expectations.
3. **Late import pattern**: `_run_simulator_shutdown_export` uses late imports from `judge.simulator.cli` to avoid loading heavy simulator dependencies at plugin init time. This matches the existing pattern in `cli.py:run_from_config()`.
