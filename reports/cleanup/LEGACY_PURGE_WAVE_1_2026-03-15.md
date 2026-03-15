# Legacy Purge Wave #1 Report

**Date:** 2026-03-15
**Package:** LEGACY-PURGE-WAVE-1
**Status:** COMPLETE

---

## 1. Executive Verdict

First safe deletion wave across the project, removing only proven dead/ghost artifacts backed by evidence from 7 completed domain audits and the FE-DM boundary stabilization. Zero runtime behavior changes. Zero speculative removals.

**Deleted:** 1 dead module (119 LOC), 2 dead imports, 2 deprecated no-op methods, 1 dead test, 7 ghost .pyc files in vfoundation, 2 orphaned vfoundation directory trees, 7 deprecated doc directories (45 files across 7 domains), all test `__pycache__/` directories (~371 orphaned test .pyc plus valid cache). Updated 1 stale comment reference.

**Result:** 165/165 guardrail tests pass. 40/40 market_data domain tests pass. No runtime behavior changed.

---

## 2. Candidate Table

| # | Path | Audit Source | Reason | Evidence | Risk | Verdict |
|---|------|-------------|--------|----------|------|---------|
| 1 | `market_data/market_ws_client.py` | MD-AUDIT | Dead module (119 LOC), 0 production importers | grep: no imports outside `__init__.py` | LOW | **DELETE_NOW** |
| 2 | `market_data/__init__.py` MarketWSClient export | MD-AUDIT | Dead export for deleted module | 3 reference sites | LOW | **CLEAN_NOW** |
| 3 | `bar_aggregator.py` `from dataclasses import asdict` | MD-AUDIT | Imported, never used | grep: single match on import line only | NONE | **DELETE_NOW** |
| 4 | `market_data_connector.py` `import time` | MD-AUDIT | Imported, never used | grep: zero `time.` or `time(` beyond import | NONE | **DELETE_NOW** |
| 5 | `proxy.py` + `connector.py` `set_feature_engineering()` | MD-AUDIT | Deprecated no-op, 0 production callers | grep: zero calls in apps/ | LOW | **DELETE_NOW** |
| 6 | 7 ghost .pyc in vfoundation/ | Ghost scan | Source files deleted, only bytecode remains | 5 unique stems: errors, binance_adapter, bracket_aggregator, fsm, price_service | NONE | **DELETE_NOW** |
| 7 | `vfoundation/apps/` tree | Ghost scan | Entirely orphaned (only __pycache__) | ls: no .py files, only bracket_aggregator.pyc | NONE | **DELETE_NOW** |
| 8 | `vfoundation/services/` dir | Ghost scan | Entirely orphaned (only __pycache__) | ls: no .py files, only price_service.pyc | NONE | **DELETE_NOW** |
| 9 | 45 deprecated docs (7 domains) | All domain audits | Non-runtime, explicitly deprecated, 0 code refs | grep: zero .py imports of docs/deprecated paths | NONE | **DELETE_NOW** |
| 10 | All `tests/**/__pycache__/` | Ghost scan | ~371 orphaned test .pyc + valid cache (regenerated) | Standard bytecode cache cleanup | NONE | **DELETE_NOW** |
| 11 | `market_data/__pycache__/market_ws_client.*.pyc` | MD-AUDIT | Ghost .pyc for deleted module | source file deleted | NONE | **DELETE_NOW** |

---

## 3. Files Actually Deleted

### Dead source module
| File | LOC | What |
|------|-----|------|
| `apps/reference/domains/market_data/market_ws_client.py` | 119 | Dead module — zero production importers |

### Ghost .pyc files (vfoundation)
| File | Source Stem | Context |
|------|-----------|---------|
| `vfoundation/__pycache__/errors.cpython-311.pyc` | errors | Moved to vfoundation/core/errors.py |
| `vfoundation/adapters/__pycache__/binance_adapter.cpython-311.pyc` | binance_adapter | Moved to adapters/exchange/ |
| `vfoundation/adapters/__pycache__/binance_adapter.cpython-314.pyc` | binance_adapter | Moved to adapters/exchange/ |
| `vfoundation/core/__pycache__/fsm.cpython-311.pyc` | fsm | Renamed to fsm_core.py / fsm_v2.py |
| `market_data/__pycache__/market_ws_client.*.pyc` | market_ws_client | Source deleted in this wave |

### Orphaned directory trees
| Directory | Contents | What |
|-----------|---------|------|
| `vfoundation/apps/` (full tree) | Only `reference/domains/execution_position/__pycache__/bracket_aggregator.*.pyc` | Entirely orphaned |
| `vfoundation/services/` | Only `__pycache__/price_service.cpython-311.pyc` | Entirely orphaned |

### Deprecated doc directories (45 files total)
| Domain | Files Removed |
|--------|--------------|
| alpha_search | 6 (ANALYSIS_SUMMARY, API_DEPENDENCIES, EVENTS, PHASE3_INTEGRATION_GUIDE, README, TESTING) |
| execution_position | 4 (DOMAIN_DOCUMENTATION, DOMAIN_DOCUMENTATION_EXPANDED, FSM_DEEP_DIVE, execpos_fsm_analysis) |
| feature_engineering | 7 (ANALYSIS_SUMMARY, API_DEPENDENCIES, DOMAIN_DOCUMENTATION_DEEP_DIVE, EVENTS, FTR_FEATURES_FUTURES_V2_DESIGN, README, TESTING) |
| market_data | 9 (ANALYSIS_SUMMARY, API_DEPENDENCIES, CHANGELOG, DEPLOYMENT, DOMAIN_DOCUMENTATION_MARKET_DATA, EVENTS, README, TESTING, TROUBLESHOOTING) |
| position_tracking | 8 (ANALYSIS_SUMMARY, API_DEPENDENCIES, CHANGELOG, DEPLOYMENT, EVENTS, README, TESTING, TROUBLESHOOTING) |
| regime_detector | 6 (ANALYSIS_SUMMARY, API_DEPENDENCIES, domain_dict.json, EVENTS, README, TESTING) |
| risk_management | 5 (ANALYSIS_SUMMARY, API_DEPENDENCIES, EVENTS, README, TESTING) |

### Bytecode cache cleanup
- All `tests/**/__pycache__/` directories — ~371 orphaned test .pyc removed along with valid cache (instantly regenerated)

---

## 4. Code Removed (inline edits, done by user/linter before this wave)

| File | What Removed |
|------|-------------|
| `market_data/__init__.py` | `MarketWSClient` from TYPE_CHECKING, `__getattr__`, `__all__` |
| `bar_aggregator.py` | `from dataclasses import asdict` (dead import) |
| `market_data_connector.py` | `import time` (dead import) + `set_feature_engineering()` (deprecated no-op) |
| `proxy.py` | `set_feature_engineering()` (deprecated no-op) + docstring reference |
| `test_market_data_proxy.py` | `test_set_feature_engineering_is_noop` test (tested deleted method) |

---

## 5. References Cleaned

| File | What Updated |
|------|-------------|
| `market_data/domain_dict.json` | `dead_code` ssot_note updated to reflect deletion |
| `market_data/README.md` | File map updated, debt table items struck through |
| `decision_making/decision_context.py` | Comment reference to deleted FTR_FEATURES_FUTURES_V2_DESIGN.md annotated |
| `test_md_domain_structural_guardrails.py` | `TestDeadCodeMarker` replaced with `TestDeletedDeadCode` (3 tests) |

---

## 6. Tests Added/Updated

### Updated: market_data guardrails
`TestDeadCodeMarker` (1 test) → `TestDeletedDeadCode` (3 tests):

| Test | What it guards |
|------|---------------|
| `test_market_ws_client_deleted` | market_ws_client.py must not reappear |
| `test_no_init_export_of_market_ws_client` | __init__.py must not reference deleted module |
| `test_no_set_feature_engineering_method` | proxy/connector must not reintroduce deprecated no-op |

### New: cross-project purge guardrails
`tests/test_legacy_purge_wave1_guardrails.py` (3 tests):

| Test | What it guards |
|------|---------------|
| `test_no_deprecated_docs_dirs` | docs/deprecated/ must not reappear in 7 purged domains |
| `test_orphaned_vf_dirs_stay_deleted` | vfoundation/apps/ and vfoundation/services/ must not reappear |
| `test_no_ghost_pyc_reintroduced` | 3 purged .pyc stems in vfoundation must not reappear |

---

## 7. Test Results

| Suite | Pass | Fail |
|-------|------|------|
| market_data domain | 40 | 0 |
| All guardrails (7 domains + boundary + purge) | 165 | 0 |

---

## 8. Residual Deletion Backlog (Wave 2 candidates)

| Priority | Item | Blocking Factor |
|----------|------|----------------|
| P2 | Skipped integration tests for MARKET_TICK_FORWARDED (`test_market_tick_forwarded_emitted.py`, `test_mr_receives_forwarded_tick_smoke.py`) | Need verification that no diagnostic workflow depends on them |
| P2 | `scripts/diagnostics/mr_restore_002_probe.py` reference to MARKET_TICK_FORWARDED | Diagnostic script — needs manual review |
| P2 | `absorption` hardcoded stub in websocket_aggregator.py | Functional decision needed: implement or formally remove |
| P3 | `seen_trade_ids` unbounded set in WebSocketAggregator | Requires code change (eviction), not pure deletion |
| P3 | Auto-generated `docs/` content (non-deprecated) across domains | May need refresh or staleness policy |
