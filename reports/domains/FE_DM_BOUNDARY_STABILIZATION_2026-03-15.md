# FE↔DM Boundary Stabilization Report

**Date:** 2026-03-15
**Package:** FE-DM-BOUNDARY-STABILIZATION
**Status:** COMPLETE

---

## 1. Executive Verdict

The FE↔DM domain boundary leak was caused by 3 strategy-domain files living in `feature_engineering/` while being consumed by `decision_making/`. The leak affected 5 import sites in DM production code and 27+ import sites in test code.

**Chosen stabilization:** Create a DM-facing `strategy_bridge.py` re-export facade. Migrate all DM production imports to use the bridge. Add 6 guardrail tests preventing leak expansion. Do NOT physically move files (blast radius: 40+ files, 1,143 tests).

**Result:** DM production code now has zero direct FE strategy imports. The boundary is documented, guarded by tests, and ready for a future physical migration package.

---

## 2. Exact Leaked Artifacts

### Files in FE with strategy-domain semantics
| File | LOC | True Owner |
|------|-----|-----------|
| `mean_reversion_strategy.py` | 774 | decision_making |
| `md_amr_strategy.py` | 362 | decision_making |
| `regime_mapping.py` | 335 | decision_making |

### DM production files with direct FE strategy imports (BEFORE fix)
| File | Direct FE imports |
|------|-------------------|
| `mean_reversion_handler.py` | `mean_reversion_strategy` (4 symbols), `regime_mapping` (1 symbol), `bar_resampler` (Bar, lazy) |
| `md_amr_handler.py` | `md_amr_strategy` (2 symbols) |
| `mean_reversion_logger.py` | `bar_resampler` (Bar) |

---

## 3. Classification Table

| File | Imported By | Runtime Role | True Owner | Action | Risk |
|------|------------|-------------|-----------|--------|------|
| `mean_reversion_strategy.py` | DM handler, 8 test files | MR signal engine (BB/RSI/ATR → signals) | decision_making | WRAP_BEHIND_DM_FACADE | LOW |
| `md_amr_strategy.py` | DM handler | MD-AMR signal engine | decision_making | WRAP_BEHIND_DM_FACADE | LOW |
| `regime_mapping.py` | DM handler, 6 test files | Regime → FlatRegime → MR params | decision_making | WRAP_BEHIND_DM_FACADE | LOW |
| `bar_resampler.py` | DM, MD, bootstrap, FE, shared, 12 test files | OHLCV bar construction | SHARED (FE correct home) | KEEP_IN_FE_AS_PURE_HELPER | NONE |
| `indicators.py` | FE-internal only | Pure math (SMA, ATR, RSI, BB) | feature_engineering | KEEP_IN_FE_AS_PURE_HELPER | NONE |

---

## 4. Stabilization Approach

### Chosen: DM re-export facade (`strategy_bridge.py`)

**Why this approach:**
- Physical file move has 40+ file blast radius (17 files with 27 strategy imports + 22 files with 24 bar imports)
- All 1,143 tests pass with zero changes to test code
- Bridge creates a clear architectural boundary with zero runtime behavior change
- Guardrail tests prevent regression (new direct imports fail CI)
- Future migration is simplified: move files to DM → bridge becomes backward-compat shim in FE

**What `strategy_bridge.py` provides:**
- `MeanReversion1mStrategy`, `MRSignal`, `MRSignalType`, `MRStrategyConfig`, `MRSymbolState`
- `MDAMRStrategyV11`, `MDAMRSignal`
- `FlatRegime`, `FlatRegimeThresholds`, `map_to_flat_regime`, `is_flat_regime`, `get_mr_parameters`, `MRParameters`

### DM production imports migrated:
| File | Before | After |
|------|--------|-------|
| `mean_reversion_handler.py` | 3 FE direct imports | 1 bridge import + 1 shared/types.Bar |
| `md_amr_handler.py` | 1 FE direct import | 1 bridge import |
| `mean_reversion_logger.py` | 1 FE bar_resampler import | 1 shared/types.Bar import |

---

## 5. Files Changed

| File | Action | What |
|------|--------|------|
| `decision_making/strategy_bridge.py` | **NEW** | DM-facing re-export facade (13 symbols) |
| `decision_making/mean_reversion_handler.py` | Modified | Strategy imports → bridge, Bar → shared/types |
| `decision_making/md_amr_handler.py` | Modified | Strategy import → bridge |
| `decision_making/mean_reversion_logger.py` | Modified | Bar import → shared/types |
| `decision_making/README.md` | Modified | Added strategy_bridge to file map + §FE↔DM Boundary Policy |
| `decision_making/domain_dict.json` | Modified | Added strategy_bridge ssot_note |
| `feature_engineering/README.md` | Modified | Updated cross-domain coupling section with boundary policy |
| `feature_engineering/domain_dict.json` | Modified | Updated strategy_infra ssot_note |

---

## 6. Tests Added

**File:** `tests/domains/decision_making/test_fe_dm_boundary_guardrails.py` — 6 tests

| Test Class | Count | What it guards |
|------------|-------|----------------|
| `TestDMProductionNoDirectFEStrategyImports` | 1 | AST-scans all DM production files for forbidden FE strategy imports |
| `TestDMBarImportsUseSharedTypes` | 1 | DM production Bar imports must use shared/types.py |
| `TestStrategyBridgeCompleteness` | 3 | Bridge exports MR, MD-AMR, regime_mapping symbols |
| `TestNoNewStrategyFilesInFE` | 1 | No new *_strategy.py or regime_*.py in FE without exemption |

**Test results:** 1,143 passed, 20 skipped, 0 failures (full domain suite).

---

## 7. Remaining Debt

| Priority | Item |
|----------|------|
| P2 | **Physical file migration:** Move `mean_reversion_strategy.py`, `md_amr_strategy.py`, `regime_mapping.py` from FE to DM. Convert `strategy_bridge.py` into backward-compat shim. Requires updating 40+ test files. |
| P3 | **Test import migration:** Update ~17 test files to import from bridge or DM paths (tests still use direct FE imports — acceptable during transition). |

---

## 8. Recommended Next Package

**market_data domain audit** — the remaining upstream domain that feeds both feature_engineering and regime_detector. Completing it would close the full upstream signal chain audit: market_data → feature_engineering → regime_detector → decision_making → execution_position → risk_management.
