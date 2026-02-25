# Phase 14 Implementation Progress Log

## Baseline
- Tests: 716 passed
- Coverage: 87%
- Date: 2026-02-24

## Steps

### STEP 1.1 — `validate_reachability()`
Status: [x] DONE
Tests added: TestValidateReachability in tests/vfoundation/core/test_fsm_v2_enhancements.py
Tests result: All PASSED.
Notes: BFS detects orphan states correctly and validates reachability.

### STEP 3.2 — ExchangeContext
Status: [x] DONE
Tests added: tests/vfoundation/core/test_exchange_context.py
Notes: Typed context for exchange sessions added.

### STEP 1.2 — `to_dot()`
Status: [x] DONE
Tests added: TestToDot in tests/vfoundation/core/test_fsm_v2_enhancements.py
Notes: Exported Graphviz DOT format verified.

### STEP 3.3 — PROTOCOL MIGRATION HELPER
Status: [x] DONE
Tests added: tests/vfoundation/core/test_protocol_migration.py
Notes: Helpers for Pld conversion V1 -> V2 implemented.

### STEP 3.1 — TYPED PAYLOAD SCHEMAS
Status: [x] DONE
Tests added: tests/vfoundation/core/test_payloads.py
Notes: Pydantic schemas for DEC:OPEN, CMD:CLOSE, EVT:FILL, etc. Added Message.typed_payload().

### STEP 1.3 — `get_stats()`
Status: [x] DONE
Tests added: TestGetStats in tests/vfoundation/core/test_fsm_v2_enhancements.py
Notes: Per-state key counts implemented.

### STEP 1.4 — fsm_emit_compat.py check
Status: [x] DONE
Notes: Results found in apps/reference and tests. File NOT deleted.

### STEP 0.1 — bugfix signing_ed25519.py
Status: [x] DONE
Tests added: test_verify_short_signature_returns_false, test_verify_empty_signature_returns_false, test_verify_wrong_payload_returns_false, test_verify_correct_signature_returns_true
Tests result: 10 passed in tests/vfoundation/security/test_signing_ed25519.py
Notes: ValueError/TypeError now caught. Updated nacl shim to reflect real behavior for TDD.

### STEP 2.1 — TOPOLOGY AUDITOR: Health Monitoring
Status: [x] DONE
Tests added: tests/vfoundation/obs/test_topology_auditor_health.py
Notes: HealthCheck/HealthReport added to TopologyAuditor.

### STEP 2.2 — DOMAIN BRIDGE
Status: [x] DONE
Tests added: tests/vfoundation/obs/test_domain_bridge.py
Notes: New DomainBridge for non-FSM domains implemented.

### STEP 0.2 — BUGFIX: protocol.py truncate_why
Status: [x] DONE
Tests added: TestTruncateWhyPhase14, TestMessageProtocolPhase14 (15 tests)
64: Tests result: 60 passed in tests/vfoundation/core/test_protocol.py
Notes: Syntax and logic were already correct in the file, but re-verified with new tests.

### STEP 4.1 — Coverage & Quality Gate
Status: [x] DONE
Result: FSMv2 (100%), FSMCore (100%), Protocol (100%), DomainBridge (100%), WAL_GC (92%).
Overall vfoundation coverage: 88% (Baseline maintained with new high-quality code).

### STEP 4.2 — Orphan Domain Integration
Status: [x] DONE
Integrated: DecisionMaking and ExecPosFSM now use DomainBridge to emit EVT:DOMAIN_STATUS.
Validated: Main loop in apps/reference/main.py calls handle_tick() periodically.

## Final Verification
- [x] All 813+ tests PASSED.
- [x] Coverage gate maintained.
- [x] Orphan domains integrated with TopologyAuditor.

## Risk Management Remediation (2026-02-24)

### STEP 1 — RCA (Audit-driven)
Status: [x] DONE
Evidence captured:
- RID not propagated to `EVT:RISK_ASSESSMENT_COMPLETED`.
- `risk_assessment_v1.json` and emitted payload mismatch.
- `_to_dec` swallowed invalid values to `Decimal("0")`.
- `DailyRiskState` amnesia after state-file corruption.

### STEP 2 — Plan
Status: [x] DONE
Artifact: `docs/architectural_audits/PLAN_RISK_MANAGEMENT.md`
Notes: Atomic Wave A–E plan defined (RID, schema, lock, amnesia, strict decimal).

### STEP 3A — RID propagation (RED→GREEN)
Status: [x] DONE
Changes:
- `RiskManagement.on_features_calculated` now preserves input `event.rid`.
- `fsm.emit("EVT:RISK_ASSESSMENT_COMPLETED", ..., rid=event.rid)`.

### STEP 3B — Schema alignment (RED→GREEN)
Status: [x] DONE
Changes:
- Updated `risk_assessment_v1.json`: required now only `is_trading_allowed`.
- Added optional `risk_score` as numeric field.
- Wired verb registry schema for `EVT:RISK_ASSESSMENT_COMPLETED`.

### STEP 3C — Thread safety in DailyRiskState (RED→GREEN)
Status: [x] DONE
Changes:
- Added `self._lock = threading.Lock()`.
- Guarded mutable/read state paths (`reset`, `reference_equity` setter, `on_portfolio`, `can_open`).
- Removed lock-recursive path in `_save_state` to avoid deadlock.

### STEP 3D — State amnesia fix (RED→GREEN)
Status: [x] DONE
Changes:
- Corrupted state now enters strict recovery mode for active trading day.
- Intraday re-anchoring is blocked after corruption.
- Re-anchor allowed only after trading-day transition.

### STEP 3E — Strict decimal validation (RED→GREEN)
Status: [x] DONE
Changes:
- `_to_dec` now raises on `None`/invalid values (no silent `0`).
- Fail-closed behavior preserved by `on_features_calculated` exception boundary.

### Verification
- New tests: `tests/domains/risk_management/test_risk_management_remediation.py` → 5 passed.
- Additional branch-coverage tests: `tests/domains/risk_management/test_risk_management_coverage.py` → 21 passed.
- Domain tests: `tests/domains/risk_management` → 34 passed.
- Zero-regression invariant: `pytest tests/vfoundation -q` → 1071 passed.
- Coverage check (`tests/domains/risk_management` scoped): 99.29% (>=95% target reached).

---

## Apps Reference Remediation (2026-02-24)

### STEP 1 — Plan Artifact + Baseline Gates
Status: [x] DONE

Artifacts:
- Added `docs/architectural_audits/PLAN_APPS_REFERENCE.md`.

Baseline gate results:
- `pytest tests/` via global Python: not available (`No module named pytest`).
- `pytest tests/` via `.venv\Scripts\python.exe`: executed, baseline has pre-existing failures.
- `python -m mypy apps vfoundation tests` via global Python: not available (`No module named mypy`).
- `.venv\Scripts\python.exe -m mypy apps vfoundation tests`: skipped (`No module named mypy`).

Baseline failing tests (pre-existing in current branch):
- `tests/backtest_engine/test_decision_clock_guard.py::test_decision_clock_one_cmd_per_bar`
- `tests/backtest_engine/test_decision_clock_guard.py::test_decision_clock_duplicate_cmd_raises`
- `tests/backtest_engine/test_reporting_config_snapshot.py::test_extract_backtest_config_snapshot_includes_repro_anchors`
- `tests/config/test_btcusdt_aurora_runtime_fields.py::TestBtcusdtAuroraRuntimeFields::test_fields_load_and_reach_runtime`
- `tests/config/test_btcusdt_aurora_runtime_fields.py::TestBtcusdtAuroraRuntimeFields::test_regime_sizing_reaches_decision_making`

### STEP 2 — Relocate Dead/Debug Scripts
Status: [x] DONE

Changes:
- Created `scripts/reproductions/`.
- Moved all 10 legacy/debug files from `apps/reference/`:
  - `reproduce_backtest_exposure.py`
  - `reproduce_debug.py`
  - `reproduce_fix.py`
  - `reproduce_fix_debug.py`
  - `reproduce_fix_debug_v2.py`
  - `reproduce_fix_v2.py`
  - `reproduce_hang_v2.py`
  - `reproduce_slowness.py`
  - `analyze_trades.py`
  - `validate_syntax.py`

Validation:
- `apps/reference/reproduce_*.py`: none found.
- `apps/reference/analyze_trades.py`: absent.
- `apps/reference/validate_syntax.py`: absent.

Gate result after step:
- `.venv\Scripts\python.exe -m pytest tests/`: same 5 pre-existing failures as baseline, no new failures observed before stop.
- `.venv\Scripts\python.exe -m mypy apps vfoundation tests`: skipped (`No module named mypy`).

### STEP 3 — Migrate `dr_loader` to `vfoundation`
Status: [x] DONE

Changes:
- Added canonical module: `vfoundation/dr/dr_loader.py` (migrated implementation).
- Converted `apps/reference/dr_loader.py` to a deprecated compatibility shim re-exporting:
  - `find_latest_snapshot`
  - `replay_wal_after`
- Updated runtime import in `apps/reference/main.py` to:
  - `from vfoundation.dr.dr_loader import find_latest_snapshot, replay_wal_after`
- Updated DR test import strategy in `tests/dr/test_dr_loader.py` to canonical module import.

Import-surface check:
- `rg -n "apps\\.reference\\.dr_loader|from apps\\.reference\\.dr_loader|import apps\\.reference\\.dr_loader|apps/reference/dr_loader\\.py" -g "*.py"`
- Remaining match: deprecation warning string inside shim only.

Gate result after step:
- `.venv\Scripts\python.exe -m pytest tests/`: same 5 pre-existing failures as baseline.
- `.venv\Scripts\python.exe -m mypy apps vfoundation tests`: skipped (`No module named mypy`).

### STEP 8 — Final Sweep + DoD Verification
Status: [x] DONE (with baseline test failures unchanged)

DoD checks:
- `apps/reference/` contains zero `reproduce_*.py`: **PASS**
- `apps/reference/analyze_trades.py` absent: **PASS**
- `apps/reference/validate_syntax.py` absent: **PASS**
- Canonical modules present:
  - `vfoundation/dr/dr_loader.py`: **PASS**
  - `vfoundation/core/retry_scheduler.py`: **PASS**
- Compatibility shims present:
  - `apps/reference/dr_loader.py`: **PASS**
  - `apps/reference/retry_scheduler.py`: **PASS**
- Precision specifiers typed as `Decimal` in `config_models.py`: **PASS**
- `main.py` uses builder/runtime extraction markers:
  - `build_live_domains(...)`: **PASS**
  - `AsyncLoopRuntime`: **PASS**
  - `resolve_backtest_max_ticks(...)`: **PASS**
- Ad-hoc env bypasses removed from `main.py`: **PASS**

Final gate result:
- `.venv\Scripts\python.exe -m pytest tests/`: same 5 pre-existing failures as baseline.
- `.venv\Scripts\python.exe -m mypy apps vfoundation tests`: skipped (`No module named mypy`).

Additional targeted validation on remediated areas:
- `.venv\Scripts\python.exe -m pytest tests/dr/test_dr_loader.py tests/runtime/test_task24_retry_scheduler_contracts.py tests/integration/test_retry_scheduler_integration_v1.py tests/unit/test_config_models_direct.py`
  - Result: **43 passed**
- `PYTHONUTF8=1 .venv\Scripts\python.exe -m pytest tests/e2e/test_s5_retry_scheduler_bounded.py`
  - Result: **3 passed**
- `.venv\Scripts\python.exe -m pytest tests/runtime/test_task24_policy_gates.py`
  - Result: **6 passed**
- `.venv\Scripts\python.exe -m pytest tests/integration/test_bridge_intent_deferred_v1_retry.py`
  - Result: **1 skipped**

### STEP 6 — Async Safety + Domain Builder Extraction
Status: [x] DONE

Changes:
- Added `apps/reference/bootstrap/async_runtime.py`:
  - `AsyncLoopRuntime` with thread-safe `start()`, `submit()`, `run()`, `stop()`.
  - Unified loop lifecycle via `run_coroutine_threadsafe` and `call_soon_threadsafe`.
- Added `apps/reference/bootstrap/domain_builder.py`:
  - `LiveDomainBundle` dataclass.
  - `build_live_domains(...)` composition-root constructor for core live domains.
- Added `apps/reference/bootstrap/backtest_runner.py`:
  - `resolve_backtest_max_ticks(config)` helper (typed config only).
- Refactored `apps/reference/main.py`:
  - Domain creation now delegated to `build_live_domains(...)`.
  - Live async synchronization now uses `AsyncLoopRuntime` wrapper.
  - Removed duplicate in-main re-instantiation of `DecisionMaking`, `RegimeDetector`, and `CsvRecorder`.

Gate result after step:
- `.venv\Scripts\python.exe -m pytest tests/`: same 5 pre-existing failures as baseline.
- `.venv\Scripts\python.exe -m mypy apps vfoundation tests`: skipped (`No module named mypy`).

### STEP 7 — SSOT Enforcement in `main.py`
Status: [x] DONE

Changes:
- `apps/reference/config_models.py`:
  - Added typed flag `system.debug_event_listener_enabled: bool = False`.
- `apps/reference/main.py`:
  - Removed ad-hoc `LOG_LEVEL` env override from bootstrap logging.
  - Removed ad-hoc `AURORA_DEBUG_EVENTS` env gate; debug listener now controlled via typed config flag.
  - Removed `BACKTEST_MAX_TICKS` env override; uses `config.trading.backtest.max_ticks` via helper.
- Updated tests previously relying on `BACKTEST_MAX_TICKS` env:
  - `tests/optimization/test_optimization_integration_contracts.py` now sets `max_ticks` via config overrides.

Validation:
- `rg -n "AURORA_DEBUG_EVENTS|BACKTEST_MAX_TICKS|LOG_LEVEL|os\\.environ|getenv\\(" apps/reference/main.py` returns no matches.

Gate result after step:
- `.venv\Scripts\python.exe -m pytest tests/`: same 5 pre-existing failures as baseline.
- `.venv\Scripts\python.exe -m mypy apps vfoundation tests`: skipped (`No module named mypy`).

### STEP 5 — Decimal Typing + Hot Path Cleanup
Status: [x] DONE

Changes:
- `apps/reference/config_models.py`:
  - Changed `InstrumentSpec` fields to `Decimal`:
    - `step_size`, `tick_size`, `min_qty`, `min_notional`
  - Changed `InstrumentPrecisionSpec` fields to `Decimal`:
    - `step_size`, `tick_size`, `min_qty`, `min_notional`
  - Added pre-validation coercion for numeric strings via `_coerce_positive_decimal(...)` and `@field_validator(..., mode="before")`.
- Hot-path conversion cleanup:
  - `apps/reference/domains/decision_making/aurora_handler.py`
  - `apps/reference/domains/decision_making/position_queries.py`
  - `apps/reference/domains/execution_position/fsm_manage.py`
  - Removed repeated `Decimal(str(...))` for typed instrument precision fields.

Validation:
- `rg -n "Decimal\\(str\\(.*(tick_size|min_qty)\\)\\)" apps/reference -g "*.py"`
- Remaining matches are outside typed precision spec hot paths:
  - `apps/reference/adapters/binance_adapter.py`
  - `apps/reference/domains/execution_position/utils.py`

Gate result after step:
- `.venv\Scripts\python.exe -m pytest tests/`: same 5 pre-existing failures as baseline.
- `.venv\Scripts\python.exe -m mypy apps vfoundation tests`: skipped (`No module named mypy`).

### STEP 4 — Migrate `retry_scheduler` to `vfoundation`
Status: [x] DONE

Changes:
- Added canonical module: `vfoundation/core/retry_scheduler.py`.
- Introduced DI callback in canonical constructor:
  - `on_no_loop: Callable[[], None] | None = None`
- Removed direct app telemetry imports from canonical module; replaced with internal callback invocation.
- Replaced `apps/reference/retry_scheduler.py` with deprecated compatibility wrapper:
  - Exposes `RetryScheduler` and `emit_compat`
  - Injects default app metric callback `inc_retry_scheduler_no_loop` when not provided.
- Updated runtime import in `apps/reference/main.py`:
  - `from vfoundation.core.retry_scheduler import RetryScheduler`
- Updated policy-gate AST test target path:
  - `tests/runtime/test_task24_policy_gates.py` now reads `vfoundation/core/retry_scheduler.py`
- Updated retry-related tests to canonical import/patch path, while preserving one compatibility import test:
  - `tests/integration/test_retry_scheduler_integration_v1.py` still imports `apps.reference.retry_scheduler`.

Import-surface check:
- `rg -n "apps\\.reference\\.retry_scheduler|from apps\\.reference\\.retry_scheduler|import apps\\.reference\\.retry_scheduler|apps/reference/retry_scheduler\\.py" tests apps/reference -g "*.py"`
- Remaining matches:
  - shim deprecation string in `apps/reference/retry_scheduler.py`
  - compatibility test import in `tests/integration/test_retry_scheduler_integration_v1.py`

Gate result after step:
- `.venv\Scripts\python.exe -m pytest tests/`: same 5 pre-existing failures as baseline.
- `.venv\Scripts\python.exe -m mypy apps vfoundation tests`: skipped (`No module named mypy`).
