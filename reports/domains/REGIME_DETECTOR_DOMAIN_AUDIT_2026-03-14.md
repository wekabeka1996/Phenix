# Regime Detector Domain Audit + Structural Cleanup Report

**Date:** 2026-03-14
**Package:** RD-DOMAIN-AUDIT
**Status:** COMPLETE

---

## 1. Executive Summary

The `regime_detector` domain is a compact, well-structured market regime classifier (2 files, 803 LOC, ~181 test functions across ~18 test files). It has a clean event-driven architecture: consumes `EVT:FEATURES_CALCULATED`, runs a priority cascade (Volatility > MeanReversion > SMATrend), applies hysteresis stabilisation and a volatility slope gate, then emits `EVT:REGIME_DETECTED` on every basis bar close.

The domain had no top-level `domain_dict.json` (only a deprecated copy in `docs/deprecated/`), 1 ghost `.pyc` (`config.cpython-311.pyc`), and auto-generated docs with no staleness warning.

**Verdict:** Architecturally sound. Clean single-emitter model. No structural debt beyond stale auto-generated docs and missing manifest.
Score: **9/10** (was ~7/10 due to missing manifest and ghost .pyc).

---

## 2. Context Map

### Source files
| File | LOC | Role |
|------|-----|------|
| `regime_detector.py` | 793 | Core: detection cascade, hysteresis, slope gate, warmup backfill |
| `__init__.py` | 10 | Package init, sets `__version__` |

### Events
- **Consumed:** EVT:FEATURES_CALCULATED (feature_engineering)
- **Emitted:** EVT:REGIME_DETECTED (to decision_making)

### Registry entries (owner: regime_detector)
| Verb | Status |
|------|--------|
| REGIME_DETECTED | active |

### Regime labels
TREND_UP, TREND_DOWN, MEAN_REVERSION, HIGH_VOLATILITY, LOW_VOLATILITY, UNCERTAIN

### Test coverage
- 3 dedicated test files in `tests/domains/regime_detector/` (27 functions)
- 15 additional files across tests/ (~154 functions)
- 1 unconditionally skipped integration test
- **Total: ~181 test functions across ~18 files**

---

## 3. Audit Question Answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Regime ownership clarity | regime_detector is sole owner of EVT:REGIME_DETECTED. No co-emitters. |
| 2 | Global regime SSOT | All regime is per-symbol, bar-clocked, STRUCTURAL layer. No global regime concept. |
| 3 | Config-to-runtime integrity | All config via AuroraConfig (Pydantic-typed, extra='forbid'). models/volatility exhaustively validated. |
| 4 | Fail-closed behaviour | dict config → TypeError. Missing models → ConfigContractError. Stale → UNCERTAIN. Missing price → no emission. Low confidence → UNCERTAIN. |
| 5 | Hidden overrides / silent fallbacks | bar_ttl_ms defaults to 10000 via getattr. tick_ttl_ms defaults to 0. clock defaults to LiveClock(). All are documented DI patterns. |
| 6 | Duplicate files / logic | No duplicate source files. Regime labels are raw strings (no shared Enum). 1 ghost .pyc (deleted). |
| 7 | Transition logic | Hysteresis-based (not formal FSM). Any→Any after hysteresis_bars confirmations. No transition matrix. |
| 8 | Cross-domain coupling | Zero direct domain imports. Pure event-driven: consumes FE→RD, emits RD→DM. |
| 9 | Test coverage | ~181 test functions across ~18 files. 1 unconditionally skipped (needs BAR-ONLY mock fix). |
| 10 | Legacy / deprecated artefacts | docs/deprecated/ has 6 stale files. Ghost config.pyc deleted. __init__.py doesn't re-export RegimeDetector. |

---

## 4. Detection Cascade (Priority Order)

| Priority | Model | Condition | Output |
|----------|-------|-----------|--------|
| P1 | volatility_v2 | ATR/baseline > threshold_multiplier | HIGH_VOLATILITY |
| P1 | volatility_v2 | ATR/baseline < low_vol_multiplier | LOW_VOLATILITY |
| P1a | slope_gate | HIGH_VOL with declining vol_ratio slope | → UNCERTAIN (suppressed) |
| P2 | mean_reversion_v2 | SMA spread + price deviations < threshold | MEAN_REVERSION |
| P3 | sma_trend_v1 | SMA crossover + price confirmation | TREND_UP / TREND_DOWN |
| – | data_quality_gate | Any data quality drops | → UNCERTAIN (override) |
| – | uncertain_cutoff_gate | confidence < uncertain_cutoff | → UNCERTAIN (demoted) |

---

## 5. Changes Applied

| File | Action | What |
|------|--------|------|
| `domain_dict.json` | **NEW** | v1.0.0 manifest: 1 import, 1 export, ssot_notes (regime_labels, cascade, hysteresis, slope_gate, config) |
| `README.md` | **NEW** | Authoritative domain documentation with architecture, regime labels, fail-closed rules, config map |
| `docs/README.md` | Modified | Staleness note added pointing to `../README.md` |
| `__pycache__/config.cpython-311.pyc` | **DELETED** | Ghost .pyc from deleted config.py |
| `test_rd_domain_structural_guardrails.py` | **NEW** | 10 guardrail tests |

---

## 6. Guardrail Tests Added

**File:** `tests/domains/regime_detector/test_rd_domain_structural_guardrails.py` — 10 tests

| Test Class | Count | What it guards |
|------------|-------|----------------|
| `TestFailClosed` | 2 | RegimeDetector rejects dict config, missing models raises ConfigContractError |
| `TestDomainDictConsistency` | 4 | ssot_notes present, imports/exports complete, description not garbled |
| `TestSchemaEnumMatchesCode` | 1 | Schema regime enum matches code-emitted labels |
| `TestNoPycacheGhosts` | 1 | No stale __pycache__ entries |
| `TestNoEmptyTestFiles` | 1 | No 0-byte test files |
| `TestInitExportsVersion` | 1 | __init__.py defines __version__ |

---

## 7. Follow-ups

| Priority | Item |
|----------|------|
| P3 | Purge or refresh stale docs in `docs/deprecated/` (6 files) |
| P3 | Fix unconditionally skipped `test_regime_detector_event_flow.py` (needs BAR-ONLY mock payload) |
| P3 | Consider creating a shared RegimeLabel Enum to replace raw string literals |
| P4 | Add `RegimeDetector` re-export to `__init__.py` (currently only `__version__`) |
| P4 | Replace `getattr(sys_md, "bar_ttl_ms", 10000)` with explicit config contract |
