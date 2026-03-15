# Legacy Purge Wave #2 — Manual Review + Empty Structure Cleanup

**Date:** 2026-03-15
**Package:** LEGACY-PURGE-WAVE-2
**Status:** COMPLETE

---

## 1. Executive Verdict

Re-evaluated 4 NEEDS_MANUAL_DECISION test files from Wave 1 reclassification. Deleted 2 (zero-assertion schema sim + mock-only QoS burst). Kept 2 (adapter session test with real assertions, skipped integration chain with future value). Removed 17 empty directories. Zero runtime behavior changes. Zero test regressions.

**Before:** 4 unresolved manual-review candidates, 16+ empty test directories.
**After:** 2 dead tests deleted (~145 LOC), 17 empty directories removed, 2 candidates explicitly resolved as KEEP.

---

## 2. Manual Review Candidate Re-Evaluation

| # | Path | LOC | Assertions | Status | Overlap | Verdict | Reason |
|---|------|-----|------------|--------|---------|---------|--------|
| 1 | `tests/test_execution_schemas_sim.py` | 58 | 0 | Passes | `test_schema_validator.py` + `test_schema_validator_coverage.py` fully cover `patch_emit_validation()` with real assertions | **DELETE_NOW** | Zero assertions; emits events and hopes schema validation doesn't throw. Superseded by 2 stronger test files |
| 2 | `tests/integration/test_decision_qos_features_burst.py` | 87 | 1 | Passes | None — but tests a **private mock**, not production code | **DELETE_NOW** | Constructs `MockDecisionMaking` with forbidden `.get()` config pattern. Tests mock behavior, not real QoS. Zero production code exercised |
| 3 | `tests/units/test_binance_adapter_session.py` | 49 | 3 | xfail (XPASS) | `test_async_fixes.py` tests adapter lifecycle but different code paths | **KEEP** | Real assertions, distinct code path (session injection + request routing). xfail marker is stale — test passes now |
| 4 | `tests/integration/test_features_full_chain_happy.py` | 169 | 4 | Skipped | Only cross-domain integration chain test at this level | **KEEP** | Genuine integration value despite being skipped. Uses deprecated tick path but no replacement exists yet |

### Per-candidate audit answers:

**test_execution_schemas_sim.py:**
1. Does it protect real runtime behavior? **No** — zero assertions
2. Does it contain assertions that still matter? **No** — none exist
3. Is it redundant with stronger modern tests? **Yes** — `test_schema_validator.py` (edge cases, validation logic, error branches)
4. Is it skipped/dead? **Not skipped, but functionally dead** — passes vacuously

**test_decision_qos_features_burst.py:**
1. Does it protect real runtime behavior? **No** — tests a private mock class, not production DM
2. Does it contain assertions that still matter? **No** — asserts mock behavior
3. Is it redundant? **N/A** — tests nothing real
4. Is it skipped/dead? **Effectively dead** — mock doesn't reflect production interface

**test_binance_adapter_session.py:**
1. Does it protect real runtime behavior? **Yes** — verifies session injection and request routing
2. Does it contain assertions that still matter? **Yes** — 3 meaningful assertions
3. Is it redundant? **Partially** — `test_async_fixes.py` tests different adapter facets
4. Is it skipped/dead? **xfail but passing (XPASS)** — marker is stale

**test_features_full_chain_happy.py:**
1. Does it protect real runtime behavior? **Would, if enabled** — exercises real domain constructors
2. Does it contain assertions that still matter? **Yes** — 4 cross-domain event flow assertions
3. Is it redundant? **No** — only full-chain integration test
4. Is it skipped/dead? **Skipped for complexity** — not deprecated, just fragile

---

## 3. Empty Directories Removed (17)

| # | Path | Category |
|---|------|----------|
| 1 | `tests/backtest/` | Top-level placeholder |
| 2 | `tests/core/` | Top-level placeholder |
| 3 | `tests/docs/` | Top-level placeholder |
| 4 | `tests/reference/` | Top-level placeholder |
| 5 | `tests/services/` | Top-level placeholder |
| 6 | `tests/static/` | Top-level placeholder |
| 7 | `tests/unit/alpha_search/` | Nested empty (parent has real tests) |
| 8 | `tests/tools/order_trace/` | Nested empty (parent has real tests) |
| 9 | `tests/apps/reference/tools/order_trace/` | Deep empty |
| 10 | `tests/apps/reference/tools/tca_execpos/` | Deep empty |
| 11 | `tests/apps/reference/utils/` | Deep empty |
| 12 | `tests/apps/reference/tools/` | Parent of removed dirs (emptied) |
| 13 | `tests/domains/execution_position/adapters/` | EP nested placeholder |
| 14 | `tests/domains/execution_position/aggregator_oco/` | EP nested placeholder |
| 15 | `tests/domains/execution_position/fixtures/` | EP nested placeholder |
| 16 | `tests/domains/execution_position/infra/` | EP nested placeholder |
| 17 | `tests/domains/execution_position/shadow_execpos/` | EP nested placeholder |

All were completely empty (zero files). None were referenced by tooling, conftest, or test discovery.

---

## 4. Files Deleted

| # | Path | LOC | Reason |
|---|------|-----|--------|
| 1 | `tests/test_execution_schemas_sim.py` | 58 | Zero assertions, superseded by schema validator tests |
| 2 | `tests/integration/test_decision_qos_features_burst.py` | 87 | Mock-only, forbidden `.get()` config pattern, tests nothing real |

**Total deleted: 2 files, ~145 LOC**

---

## 5. References Cleaned

- No active code references to deleted files exist
- Stale mentions in `tools/batch_replace_tests.py` and `tools/maintenance/batch_replace_tests.py` are static file lists in maintenance scripts — will harmlessly skip missing files

---

## 6. Test Results

| Suite | Pass | Fail | Skip | Notes |
|-------|------|------|------|-------|
| Domain guardrails (89) | 89 | 0 | 3 | Pre-existing env skips |
| Config + contracts (524) | 524 | 0 | 3 | Clean |

---

## 7. Residual Cleanup Backlog

| Priority | Item | Notes |
|----------|------|-------|
| P1 | Remove stale `xfail` from `test_binance_adapter_session.py` | Test currently XPASS — marker is stale |
| P2 | Modernize `test_features_full_chain_happy.py` | Uses deprecated `on_market_tick()` path, dict config |
| P2 | Test location consolidation | `tests/units/` vs `tests/unit/`, split domain locations |
| P3 | Root-level build artifacts | `async_inventory.json`, `.pytest_junit.xml` not gitignored |
| P3 | `__init__.py`-only namespace dirs | `tests/apps/`, `tests/apps/reference/`, `tests/apps/reference/domains/` — only exist as package stubs |
