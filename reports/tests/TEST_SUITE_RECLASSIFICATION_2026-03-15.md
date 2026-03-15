# Test Suite Reclassification Report

**Date:** 2026-03-15
**Package:** TEST-SUITE-RECLASSIFICATION
**Status:** COMPLETE

---

## 1. Executive Verdict

Full classification of the test suite: **684 test files, 5,368 test functions** across ~60 directories. Identified 16 dead/stub/deprecated test files backed by evidence; 15 deleted in this wave. 4 files flagged for manual review. 93 files contain skip markers. No runtime behavior changed.

**Before:** 684 test files (16 dead weight: empty stubs, debug scripts masquerading as tests, deprecated-event tests, deleted-class references).
**After:** 669 test files. 15 dead files removed (~1,254 LOC). 162/162 guardrails pass. 1,681/1,682 broader tests pass (1 pre-existing failure).

---

## 2. Inventory Summary by Classification

| Classification | Directories | Files | Tests | Notes |
|---------------|-------------|-------|-------|-------|
| **RUNTIME_CRITICAL** | `domains/decision_making`, `domains/execution_position`, `domains/feature_engineering`, `domains/market_data`, `domains/risk_management`, `domains/regime_detector` | ~132 | ~882 | Domain regression tests — protect signal chain |
| **ARCH_GUARDRAIL** | `domains/*/test_*guardrail*`, `domains/*/test_*structural*`, `audit/`, `api/test_api_no_deprecated_imports` | ~12 | ~162 | Structural invariant enforcement |
| **CONFIG_VALIDATION** | `config/`, `contracts/` | ~61 | ~400 | Config strictness, schema compliance, contract SSOT |
| **INTEGRATION_E2E** | `integration/`, `e2e/` | ~81 | ~369 | Cross-domain pipeline tests |
| **VFOUNDATION_CORE** | `vfoundation/` | ~112 | ~1,231 | FSM, adapters, CLI, DR, observability |
| **ALPHA_SEARCH** | `apps/reference/domains/alpha_search/tests/` | ~21 | ~281 | Alpha search domain (self-contained) |
| **NEOCORTEX** | `apps/reference/domains/neocortex/tests/` | ~32 | ~289 | Neural/PPO domain (self-contained) |
| **FORENSIC_DIAGNOSTIC** | `investigation/`, `simulation/`, `audit_*.py` | ~10 | ~55 | Historical probes, not regression CI |
| **UNIT_MISC** | `unit/`, `units/`, `(root)` | ~113 | ~958 | Mixed unit tests, legacy locations |
| **OTHER** | `bootstrap/`, `adapters/`, `idempotency/`, `order_guardian/`, etc. | ~95 | ~741 | Specialized subsystem tests |

---

## 3. Skipped Test Summary

**93 files** contain skip markers. Major categories:

| Category | Count | Examples |
|----------|-------|---------|
| Conditional environment skips | ~40 | Config-dependent, optional deps |
| Complex async integration | ~15 | Full-chain tests too fragile for CI |
| Refactoring/deleted class | 2 | AuroraBridge references (DELETED in this wave) |
| Deprecated event | 2 | EVT:MARKET_TICK_FORWARDED (DELETED in this wave) |
| Live service dependency | ~5 | Requires running WS server, exchange API |
| Neocortex/alpha_search internal | ~25 | Self-contained domain skips (performance, regression) |
| Other | ~4 | Flaky/xfail, known issues |

---

## 4. Deprecated/Dead Test Summary

### DELETE_NOW — Executed (15 files)

| # | Path | LOC | Reason | Evidence |
|---|------|-----|--------|----------|
| 1 | `test_binance_execution_adapter_v2.py` | 1 | Empty file | Zero content |
| 2 | `test_config_load.py` | 29 | Debug script, no test functions | `print()` only, no assertions |
| 3 | `test_config_structure.py` | 14 | Debug script, no test functions | `print()` only |
| 4 | `test_dynamic_integration.py` | 62 | Debug script, no test functions | Emoji-decorated print output |
| 5 | `test_order_40usd.py` | 231 | Calculator script, no test functions | `__main__` print block |
| 6 | `test_env.py` | 22 | Debug script, permanently skipped | Prints API key prefixes |
| 7 | `test_feature_collection.py` | 182 | Data collection utility, not a test | Opens live WS for 30s, no assertions |
| 8 | `test_resolve.py` | 37 | Debug script, permanently skipped | Env var interpolation test, no `test_*` |
| 9 | `test_ws_direct.py` | 43 | Manual WS debug, permanently skipped | Requires localhost:8000 |
| 10 | `integration/test_bridge_intent_deferred_v1_retry.py` | 96 | References deleted `AuroraBridge` | Class deleted from main.py |
| 11 | `integration/test_live_bridge_to_marketdata.py` | 96 | Skipped, hardcoded path, brittle | Absolute path, config-dependent assertions |
| 12 | `integration/test_market_tick_forwarded_emitted.py` | 83 | Deprecated event, never implemented | EVT:MARKET_TICK_FORWARDED has 0 emitters |
| 13 | `integration/test_mr_receives_forwarded_tick_smoke.py` | 91 | Deprecated event path | MR uses on_bar() now, not tick forwarding |
| 14 | `domains/position_tracking/test_task47_disable_stale_gate.py` | 105 | All tests skip, references deleted `AuroraBridge` | Class deleted from main.py |
| 15 | `domains/decision_making/test_mean_reversion_bar_logging.py` | 118 | Zero test methods, deprecated `on_tick()` | Comment explains methods removed |

**Total deleted: 15 files, ~1,210 LOC**

---

## 5. Immediate Safe Purge Candidates NOT Executed

These were identified but left for Wave 2+ due to needing manual review:

| Path | LOC | Issue | Action |
|------|-----|-------|--------|
| `test_execution_schemas_sim.py` | 58 | Smoke test with zero assertions | NEEDS_MANUAL_DECISION |
| `integration/test_decision_qos_features_burst.py` | 87 | Self-contained mock only, may not test real QoS | NEEDS_MANUAL_DECISION |
| `units/test_binance_adapter_session.py` | 49 | xfail/flaky, needs stabilization | NEEDS_MANUAL_DECISION |
| `integration/test_features_full_chain_happy.py` | 169 | Skipped full-chain integration | NEEDS_MANUAL_DECISION |

---

## 6. Manual Review Backlog

### Files misclassified by initial scan as empty (actually valid):
All confirmed KEEP — `test_order_guardian_grace_period.py`, `test_watchdog_polling_fix.py`, `test_guardian_tidy_delivery.py`, `test_fsm_emit_compat*.py`, `test_order_guardian_emit.py`, `test_vfoundation_binance_adapter_json_coerce.py`, `test_exec_adapter_deep.py`, `test_retry_scheduler_async.py`, `bugfixes/test_p1_002_adapter_precision.py`.

### Structural observations for future cleanup:
- `tests/units/` vs `tests/unit/` — dual naming convention (62 vs 137 tests)
- `tests/domains/execution_position/` (357 tests) + `tests/execution_position/` (12 tests) — split locations
- `tests/domains/decision_making/` (307 tests) + `tests/decision_making/` (20 tests) — split locations
- `tests/(root)` has 82 files with 859 tests — many could be relocated to domain-specific dirs
- 14 empty directories with no .py files (e.g., `tests/backtest/`, `tests/core/`, `tests/docs/`)

---

## 7. Changes Applied

| Action | Count | Detail |
|--------|-------|--------|
| Test files deleted | 15 | Dead stubs, debug scripts, deprecated-class/event tests |
| Test files created | 0 | — |
| Production files changed | 0 | — |
| Total LOC removed | ~1,210 | From dead test files only |

---

## 8. Test Results

| Suite | Pass | Fail | Skip | Notes |
|-------|------|------|------|-------|
| All guardrails (162) | 162 | 0 | 0 | Clean |
| Domains + contracts + config + bootstrap + audit | 1,681 | 1* | 37 | *Pre-existing: `test_no_forbidden_config_get_patterns` (unrelated) |

---

## 9. Recommended Next Packages

| Priority | Package | Scope |
|----------|---------|-------|
| P1 | **Legacy Purge Wave #2** | Delete 4 NEEDS_MANUAL_DECISION files after review + 14 empty dirs + stale non-test scripts under tests/ |
| P2 | **Test Location Consolidation** | Resolve `units/` vs `unit/`, root-level orphans, split domain test locations |
| P3 | **Skip Audit** | Review ~93 skipped files — resurface or delete permanently |
| P4 | **Forbidden Config Pattern Fix** | Fix 4 `.get()` patterns in `mean_reversion_strategy.py` to resolve pre-existing test failure |
