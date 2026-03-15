# Feature Engineering Domain Audit + Structural Cleanup Report

**Date:** 2026-03-15
**Package:** FE-DOMAIN-AUDIT
**Status:** COMPLETE

---

## 1. Executive Summary

The `feature_engineering` domain is the largest signal domain: **16 files, ~8,849 LOC, ~150+ test functions** across ~24 test files. It transforms raw market ticks/bars into normalized feature vectors consumed by regime_detector, decision_making, and risk_management. It also hosts bar-based strategy infrastructure (MR, MD-AMR).

The domain had a **stale domain_dict.json** (v1.1.0, missing V2 features, futures, pillars, price_motion, 6 of 7 consumed events, all CMD/BLOCKED events). Two ghost `.pyc` files existed (`config`, `feature_engineering_phase1`). Auto-generated docs had no staleness warning.

Architecture is solid: 60+ config properties via typed `FeatureEngineeringConfig` wrapper, feature catalog in `contracts.py` with V1/V2 metadata (range, neutral, monotonicity), 3 JSON schemas. Primary documented debt is strategy files living in FE instead of decision_making.

**Verdict:** Architecturally healthy, config coverage thorough, feature catalog well-maintained.
Score: **8/10** (was ~6/10 due to stale manifest, missing docs, strategy placement debt).

---

## 2. Context Map

### Source files: 16 .py files, ~8,849 LOC
| File | LOC | Role |
|------|-----|------|
| `feature_engineering.py` | 1847 | Core orchestrator |
| `calculation_engine.py` | 1337 | Feature computation engine |
| `types.py` | 997 | State dataclasses + config wrapper |
| `mean_reversion_strategy.py` | 774 | MR strategy (used by DM) |
| `utils.py` | 518 | Welford online stats, z-score |
| `bar_resampler.py` | 394 | Tick→Bar resampling |
| `pillar_indicators.py` | 391 | Tactician/Operator/Strategist |
| `macro_sync_resampler.py` | 386 | Cross-symbol correlation |
| `contracts.py` | 380 | Pydantic models + feature metadata |
| `indicators.py` | 365 | Pure-math (SMA, ATR, RSI, BB) |
| `md_amr_strategy.py` | 362 | MD-AMR strategy (used by DM) |
| `regime_mapping.py` | 335 | FlatRegime + MR parameters |
| `pillar_backfill.py` | 272 | Historical candle warmup |
| `large_trade_imbalance.py` | 217 | Institutional flow detection |
| `price_motion.py` | 199 | Multi-window returns + PM norm |
| `__init__.py` | 75 | Re-exports, __version__ |

### Events: 7 consumed, 3 emitted
**Consumed:** MARKET_TICK_RECEIVED, BAR_CLOSED, REGIME_DETECTED, HTF_BARS_IMPORTED, FUNDING_UPDATE, OI_UPDATE, ANCHOR_UPDATED
**Emitted:** FEATURES_CALCULATED, CMD:PROCESS_STRATEGY, PROCESS_STRATEGY_BLOCKED

### Feature families
- V1 base (6): obi, tfi, delta_price, price, absorption, liquidity_kappa
- V1 phase1 (5): ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync
- V2 additive (3): volume_zscore, large_trade_imbalance, spread_bps
- Futures (3): funding_rate_normalized, oi_delta_pct, funding_rate
- R1 (1): macro_resid
- Pillars (4): tactician, operator, strategist, pillar_sum
- Price motion (12): ret/vol_pct/pm_norm at 10s/60s/300s/900s

### Test coverage: ~150+ test functions across ~24 files
- 10 dedicated files in `tests/domains/feature_engineering/` (63 functions)
- 14+ additional files across tests/ (~87+ functions)
- 1 unconditionally skipped integration test
- 2 xfail tests (P1-1, P1-2 regressions)

---

## 3. Audit Question Answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Responsibility boundary | FE computes features (V1+V2+futures+pillars+price_motion), hosts strategy infra (MR, MD-AMR), emits bar-driven CMD:PROCESS_STRATEGY |
| 2 | Feature SSOT | contracts.py V1_FEATURE_METADATA / V2_FEATURE_METADATA is the canonical catalog. calculation_engine.py is the sole runtime computer |
| 3 | Duplicate calculators | regime_detector has independent SMA+ATR (Decimal, intentional). Two compute_sma() in indicators.py vs pillar_indicators.py (different input types) |
| 4 | Config respected at runtime | Yes — FeatureEngineeringConfig (Pydantic, extra='forbid') wraps all 60+ config fields |
| 5 | Hardcoded constants | Many in strategy files (BB/RSI defaults, dampening weights, flat regime thresholds). Not config-overridable. Documented as debt |
| 6 | Normalization / scaling | V1 base: native ranges; V1 phase1: [0,1]; V2: tanh([0,1]) or R+; neutrals defined in FEATURE_METADATA |
| 7 | Misnamed/misplaced files | MR strategy, MD-AMR strategy, regime_mapping live in FE but are DM-consumed. Historical placement, too risky to move |
| 8 | File classification | All 16 ACTIVE. 3 LEGACY_REFERENCED (strategy files). 2 DEAD_SAFE_TO_REMOVE (ghost .pyc, deleted) |
| 9 | Contract alignment | 3 FE-owned verbs in registry. CMD:PROCESS_STRATEGY owned by strategies (schema in FE). Aligned |
| 10 | Feature names stable/documented | Yes — V1_FEATURE_NAMES, V2_FEATURE_NAMES, metadata with range/neutral/monotonicity |

---

## 4. Changes Applied

| File | Action | What |
|------|--------|------|
| `domain_dict.json` | **REWRITTEN** | v2.0.0: all 7 imports, 3 exports, 10 components, feature_families map, ssot_notes |
| `README.md` | **NEW** | Authoritative domain docs: architecture, feature families, config map, fail-closed rules |
| `docs/README.md` | Modified | Staleness note added pointing to `../README.md` |
| `__pycache__/config.cpython-311.pyc` | **DELETED** | Ghost .pyc from deleted config.py |
| `__pycache__/feature_engineering_phase1.cpython-311.pyc` | **DELETED** | Ghost .pyc from deleted phase1 file |
| `test_fe_domain_structural_guardrails.py` | **NEW** | 15 guardrail tests |

---

## 5. Guardrail Tests Added

**File:** `tests/domains/feature_engineering/test_fe_domain_structural_guardrails.py` — 15 tests

| Test Class | Count | What it guards |
|------------|-------|----------------|
| `TestFeatureCatalogSSOT` | 4 | V1 has 11 features, V2 extends V1, metadata has range/neutral/group, Pydantic fields match metadata |
| `TestSchemaAlignment` | 2 | Schema required fields exist, all 3 schemas present |
| `TestDomainDictConsistency` | 5 | ssot_notes present, imports/exports complete, description not garbled, feature families listed |
| `TestNoPycacheGhosts` | 1 | No stale __pycache__ entries |
| `TestNoEmptyTestFiles` | 1 | No 0-byte test files |
| `TestInitExportsVersion` | 2 | __init__.py has __version__ and re-exports FeatureEngineering |

---

## 6. Follow-ups

| Priority | Item |
|----------|------|
| P2 | **Strategy file placement:** MR strategy, MD-AMR strategy, regime_mapping should live closer to decision_making. High blast radius (~150 tests). Needs dedicated migration package. |
| P3 | **Hardcoded strategy constants:** BB/RSI/ATR defaults in MR/MD-AMR are not config-overridable. Should be config-driven. |
| P3 | **Two compute_sma functions:** indicators.py (list) vs pillar_indicators.py (deque). Consider unifying with adapter pattern. |
| P3 | **Purge deprecated docs:** `docs/deprecated/` has 7 stale files. |
| P3 | **Fix skipped integration test:** `test_features_full_chain_happy.py` (complex async domain integration chain). |
| P3 | **Fix xfail tests:** P1-1, P1-2 regressions in `test_task24_feature_engineering_correctness.py`. |
| P4 | **Ghost test .pyc cleanup:** 15+ ghost .pyc across test __pycache__ directories (not FE source — wider cleanup). |
