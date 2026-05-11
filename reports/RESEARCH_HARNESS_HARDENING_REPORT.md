# RESEARCH HARNESS HARDENING REPORT

## Scope

PKG-5 hardens the repo so the next bounded search can be technically honest.

This package did not run a search grid. It only established:

- artifact-visible scoring telemetry,
- a strict-config-compatible proxy harness,
- a formal proxy-universe contract,
- reproducible March proxy benchmarks on that harness.

## Reference Freeze

- git sha: `cf074c7229252aaca83aed7dc70331115018866d`
- `config/aurora/strategies.yaml`: `67107c2528f58fc2eb61a20a33c62e52fcf0395a449dc88571ec9ef4112e3cc1`
- `config/aurora/strategies/aurora.yaml`: `9760d13d91ef101e2aa502c5629d8a327a2a77aa0b7aed077871842963b97fb7`
- `scripts/diagnostics/run_single_backtest.py`: `33df421f8df79ad807a5c29e48d6c611e7073df20be59bce1b56cf47f7992273`
- `optimization/backtest_interface.py`: `ec62d5a8fcafd47905a3b2967aecbff0a0f023a6cc2c313f42d6f785861c7b28`
- `optimization/research/selective_optimizer.py`: `25ffc4738a053c5dbede87d62ee89f882425ba6cb21ea5f33c8c59805538546c`

Reference March runs already established before PKG-5:

- full-surface March baseline: `20260314_041537`
- full-surface March v1 reference: `20260314_041758`

## What Changed

### 1. Scoring telemetry is now persisted in bundle artifacts

Runtime Aurora scoring now exports:

- `quadratic_engine_selected_count`
- `quadratic_fallback_count`
- `fallback_also_failed_count`
- `selected_engine_counts`
- `observed_engine_counts`
- `engine_names_observed`
- `per_symbol` telemetry with the same counters

That telemetry is written into:

- raw backtest report JSON
- compact `.summary.json`

### 2. Research proxy contract moved into typed runtime metadata

Instead of overlaying invalid SSOT-derived fields like `trading.symbols_to_track`, PKG-5 adds typed runtime metadata under:

- `system_meta.runtime.research_proxy`

This allows the harness to express:

- tracked symbols
- tradable symbols
- context symbols
- strategy assignments
- fail-closed fallback policy

without violating strict config expectations.

### 3. Dedicated strict-compatible proxy runner added

PKG-5 adds a new proxy-only research path instead of mutating `SelectiveOptimizer` semantics:

- `optimization/research/proxy_runner.py`
- `scripts/diagnostics/run_research_proxy_backtest.py`

This harness:

- mutates proxy runtime state after config load,
- enforces tracked/tradable/context symbol consistency,
- returns artifact metadata needed for bounded search,
- can fail closed if any quadratic fallback is observed.

### 4. Runtime/plugin boundary bug was found and fixed during real benchmark execution

The first real baseline proxy run completed simulation but failed while building the report because `apps/reference/main.py` requested telemetry from the Aurora plugin wrapper, and that wrapper did not proxy `get_scoring_telemetry()`.

Fix applied:

- `_AuroraHandlerWrapper` now exposes `get_scoring_telemetry()` and delegates to the real handler.

This was validated by focused pytest before rerunning the benchmarks.

### 5. Windows benchmark reproducibility requires UTF-8-safe shell setup

The first baseline attempt also surfaced a non-business operational defect:

- CP1251 console encoding caused `UnicodeEncodeError` when runtime logs emitted emoji / Unicode labels.

PKG-5 benchmark commands were rerun under explicit UTF-8-safe PowerShell environment variables and console encodings.

## Tests Added / Run

Added:

- `tests/domains/decision_making/test_aurora_scoring_telemetry.py`
- `tests/backtest_engine/test_scoring_telemetry_reporting.py`
- `tests/optimization/test_research_proxy_runner.py`
- wrapper telemetry passthrough coverage in `tests/domains/decision_making/test_aurora_builtin_plugin.py`

Focused validation result:

- `9 passed in 0.47s`

## Package Result

PKG-5 succeeded.

The repo now has a valid research harness for future bounded search on the ETH+BTC proxy surface, with artifact-visible engine telemetry and fail-closed fallback enforcement.