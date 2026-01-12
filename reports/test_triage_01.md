# TEST-TRIAGE-01 Report

**Date:** 2026-01-12
**Failed Tests:** 173 (based on map, failures + errors)
**Status:** TRIAGED

## 1. Failure Map Overview

The failures fall into 3 major clusters (80% of volume) and a long tail of specific logic breaks.

| Cluster | Count | Type | Root Cause | Action Plan |
|:---|:---:|:---|:---|:---|
| **STRICT_CONFIG** | ~40 | CONTRACT | Missing `execution` field in MR Strategy config mocks (Pydantic ValidationError). | **BULK FIX**: Update mock configs in failing files to include `execution` defaults. |
| **CONTRACT_VIOLATION** | ~45 | CONTRACT | ExecutionPosition tests pass `MagicMock` where code expects strict `dict`/`Config` (ConfigContractError). | **REFACTOR**: Update test fixtures to use real dicts/Pydantic models instead of lazy mocks. |
| **LOW_VOL_ATTR** | 15 | LEGACY | Tests call deleted/renamed private method `_check_low_vol_cost_suppress_gate`. | **REWRITE/DELETE**: Test public interface or update method name. |
| **TIME_MOCK** | ~20 | LEGACY | `time.time` usage in tests vs `monotonic` in code (Reentry, Aurora). | **MIGRATE**: Apply `MockClock` pattern (TIME-TEST-MIGRATION-01). |

---

## 2. Representative Cases (Deep Dive)

### Case A: MR Strict Config (Cluster 1)
- **Test**: `tests.domains.decision_making.test_mean_reversion_emit_trade_intent_mode`
- **Error**: `ValidationError: Field required: execution`
- **Analysis**: The `ORDER-POLICY-01` update made `execution` mandatory in `MeanReversion1mStrategyConfig`. These tests simulate config using partial dicts/mocks that lack this field.
- **Decision**: **FIX**. This is a trivial config update in test setup.

### Case B: ExecutionPosition Config Contract (Cluster 2)
- **Test**: `tests.domains.execution_position.test_execpos_cooldown_after_close_v1`
- **Error**: `ConfigContractError: Expected dict at trading.risk, got MagicMock`
- **Analysis**: The code now strictly validates configuration types. Using `MagicMock` triggers the failsafe.
- **Decision**: **REFACTOR**. Tests must respect the system's type safety contracts. Replace `MagicMock` with `dict` or properly typed Config objects.

### Case C: Low Volatility Gate (Cluster 3)
- **Test**: `tests.domains.decision_making.test_low_vol_cost_suppress`
- **Error**: `AttributeError: no attribute '_check_low_vol_cost_suppress_gate'`
- **Analysis**: The internal implementation of the gate changed (likely renamed to `_check_gates` or moved to a policy class), breaking tests that relied on the private method name.
- **Decision**: **QUARANTINE / DELETE**. These tests verify implementation details that no longer exist. If the functionality is covered by integration tests, delete these unit tests.

### Case D: Reentry Cooldown (Cluster 4)
- **Test**: `tests.domains.decision_making.test_reentry_cooldown.py`
- **Error**: `assert 0 == 1` (call count mismatch)
- **Analysis**: Classic "Clock Drift" issue identifiable by `time.time` mocks in source + failures in duration logic.
- **Decision**: **MIGRATE**. Switch to `MockClock` injection.

---

## 3. CI Gate Proposal

### 1. The "Contract Suite" (Green Gate)
Must pass 100% on every commit. Includes strict configuration, schemas, and core integration flows.

- `tests/config/*`
- `tests/integration/test_ep01_*`
- `tests/integration/test_market_tick_forwarded_emitted.py`
- `apps/reference/domains/**/tests` (excluding legacy named files)

### 2. The "Legacy Suite" (Quarantine)
Allowed to fail, but tracked. Includes tests marked with `@pytest.mark.legacy`.

- `tests/domains/decision_making/test_low_vol_cost_suppress.py` (until rewritten)
- `tests/domains/decision_making/test_reentry_cooldown.py` (until migrated)
- `tests/domains/execution_position/test_execpos_*` (until mock fix)

---

## 4. Immediate Next Actions

1.  **BATCH 1**: Execute **STRICT-CONFIG-FIX-01**. Fix `ValidationError` by adding `execution` field to mocks. (Low effort, high yield ~40 tests).
2.  **BATCH 2**: Execute **TIME-TEST-MIGRATION-01**. Fix Reentry/Aurora tests via Time Injection.
3.  **BATCH 3**: Execute **QUARANTINE-01**. Mark "AttributeError" tests and "MagicMock" contract tests as `@pytest.mark.legacy` to clean up the signal.

