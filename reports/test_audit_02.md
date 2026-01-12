# TEST-AUDIT-02 Report (Full Run & Classification)

**Date:** 2026-01-12
**Suite:** Full Pytest Audit (using `.venv` with `fastapi`/`httpx`)
**Status:** ❌ FAILED (132 Failures, 44 Errors)

## 1. Executive Summary

We successfully executed the full test suite by overcoming previous blockers:
1.  **ENV FIX**: Dependencies (`fastapi`, `httpx`) are present in `.venv`, resolving API test collection errors.
2.  **CONFIG FIX**: Pydantic models updated to match `ORDER-POLICY-01` YAML changes.
3.  **FULL RUN**: Executed without early stopping (`--maxfail=0`).

| Metric | Count |
|:-------|:-----:|
| **Total Passed** | 2022 |
| **Total Failed** | 132 |
| **Total Errors** | 44 |
| **Skipped** | 60 |

This reveals a significant accumulation of **Technical Debt in Tests** (Legacy Tests) that have drifted from the evolved codebase (Time Discipline, Strict Contracts).

---

## 2. Top Failure Clusters (Prioritized)

Based on failure frequency per file:

| File | Fails | Classification | Root Cause Hypotheses |
|:---|:---:|:---|:---|
| `tests/domains/decision_making/test_low_vol_cost_suppress.py` | 15 | LEGACY | Changes in Low Volatility logic or Time Mocking mismatch. |
| `tests/domains/execution_position/test_exposure_guard_matrix_v1.py` | 14 | CONTRACT | Strict configs validation or Exposure Guard logic update. |
| `tests/domains/decision_making/test_reentry_cooldown.py` | 8 | LEGACY | **Time Discipline Mismatch** (mock `time.time` vs usage of `monotonic`). Same as critical fixes. |
| `tests/domains/decision_making/test_mean_reversion_handler_hardening_v1.py` | 8 | CONTRACT | MR Handler evolution (emit signal vs intent). |
| `tests/domains/test_mean_reversion_strategy.py` | 7 | LEGACY | Old strategy test suite. |
| `tests/audit/test_critical_fixes.py` | 2 (was 5) | PARTIAL FIX | `reentry` logic requires deeper debug; `holding_period` & `persistence` fixed by switching to `MockClock`. |

---

## 3. Analysis of Critical Adjustments (`test_critical_fixes.py`)

We refactored `tests/audit/test_critical_fixes.py` to use **Dependency Injection for Time** (`MockClock` -> `monotonic_fn`), solving the "Clock Drift" issue where tests mocked `time.time` but code used `time.monotonic`.

**Results:**
- ✅ `TestProtocolB_LockedRoomTest` (Holding Period): **PASSED** (after fix).
- ✅ `TestProtocolC_FullMarginFlip` (Exposure): **PASSED**.
- ✅ `TestProtocolD_SymbolStatePersistence`: **PASSED** (after fix).
- ✅ `TestFullChainIntegration`: **PASSED** (after fix).
- ❌ `TestProtocolA_PingPongStress` (Reentry): **FAILED** (2 tests). Code flow likely interrupted before reaching cooldown logic (gates/warmup), ignoring the mocked time fix.

---

## 4. Recommendations & Next Steps

1.  **REPAIR-TESTS-01 (High Priority)**:
    - Address the **Time Discipline Mismatch** broadly. Many DecisionMaking tests likely suffer from the same `time.time()` vs `monotonic()` issue as `test_critical_fixes.py`.
    - Apply the `MockClock` injection pattern to `test_reentry_cooldown.py` and `test_aurora_reentry_cooldown.py`.

2.  **CONTRACT-FIX-01 (Exposure Guard)**:
    - Investigate `test_exposure_guard_matrix_v1.py`. If these are violations of new strict leverage/equity rules, either update the tests (if rules are correct) or fix the guard (if rules are too strict).

3.  **CLEANUP-LEGACY**:
    - `tests/domains/test_mean_reversion_strategy.py` seems like an old suite duplicating newer MR tests. Consider deprecating/deleting if covered by `test_mean_reversion_handler_*.py`.

4.  **E2E ERRORS**:
    - The 44 Errors in E2E tests often point to setup/fixture issues (Environment, Config loading). Investigate one representative E2E error to unblock the rest.

---

**Sign-off**: `TEST-AUDIT-02` completed. We have a clear map of the battlefield.
