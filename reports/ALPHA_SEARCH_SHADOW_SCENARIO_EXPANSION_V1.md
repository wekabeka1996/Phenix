# ALPHA_SEARCH_SHADOW_SCENARIO_EXPANSION_V1
**Date:** 2026-05-16  
**Status:** PHASES 0–7 COMPLETE  
**Authority:** SHADOW ONLY — no real trading affected

---

## Executive Summary

All 12 current alpha_search scenarios produce **zero BUY/SELL signals**. Root-cause forensic audit identified three blocking factors. This expansion repairs the signal path (shadow-only), extends the registry to 30 distinct scenarios across 6 strategy families, implements a virtual lifecycle engine for PnL simulation, and wires WAL comparison analysis.

**Real trading is unchanged.** Alpha_search remains a shadow laboratory.

---

## PHASE 0 — Forensic Audit: Why Zero Signals

### Root Cause 1 — fail_closed:ta_features_missing_for_bar (60.8% of bars)
TA feature pipeline emits `fail_closed:ta_features_missing_for_bar` for bars where warmup is incomplete or indicator inputs are missing. When fail_closed triggers: `score=0, confidence=0 → NEUTRAL`.

Affected bars per scenario: **1,403 / 2,309 (60.8%)**

### Root Cause 2 — UNCERTAIN Regime × High Multiplier (39.2% of bars)
- 91.55% of all bars have `regime=UNCERTAIN`
- Aurora threshold multiplier in UNCERTAIN = **3.00** (current config)
- Effective threshold: `0.28 × 3.0 = 0.84`
- Actual scores in UNCERTAIN: ~`0.000025`
- Result: impossible threshold → guaranteed NEUTRAL

### Root Cause 3 — aurora_dir=0.0000, aurora_str=0.0000
When aurora model degenerates (upstream orientation/strength = 0), score is `~0.00002`, confidence = 0. All 906 non-fail_closed bars in the MR group exhibit this pattern.

### Signal Distribution (latest run: 20260513_213940)
| Scenario | Total | BUY | SELL | NEUTRAL | Score Mean | Confidence Mean |
|---|---|---|---|---|---|---|
| S01_MR_RSI_HEAVY | 2309 | 0 | 0 | 2309 | -0.000737 | 0.0 |
| S03_AURORA_15M_APPROX | 2309 | 0 | 0 | 2309 | 0.0 | 0.0 |
| S05_AURORA_MACRO_RESIDUAL | 2309 | 0 | 0 | 2309 | 0.0 | 0.0 |
| S06_AURORA_ETH_CALIBRATED | 2309 | 0 | 0 | 2309 | 0.0 | 0.0 |
| S11_MR_BASELINE | 2309 | 0 | 0 | 2309 | -0.000737 | 0.0 |
| S12_MR_RSI_25_75 | 2309 | 0 | 0 | 2309 | -0.000737 | 0.0 |
| S13_MR_BB_HEAVY | 2309 | 0 | 0 | 2309 | -0.000737 | 0.0 |
| S15_ENSEMBLE_BALANCED | 2309 | 0 | 0 | 2309 | -0.000737 | 0.0 |
| S18_ENSEMBLE_MOMENTUM_AGGRESSIVE | 2309 | 0 | 0 | 2309 | -0.000737 | 0.0 |
| S19_ENSEMBLE_MR_SHORT_BIAS | 2309 | 0 | 0 | 2309 | -0.000737 | 0.0 |
| S20_AURORA_MICROSTRUCTURE_DEPTH | 2309 | 0 | 0 | 2309 | 0.0 | 0.0 |
| S21_ENSEMBLE_REGIME_ADAPTIVE | 2309 | 0 | 0 | 2309 | -0.000737 | 0.0 |

---

## PHASE 1 — Signal Materializer Repair

**File:** `apps/reference/domains/alpha_search/shadow/signal_materializer.py`

Introduced `ShadowReasonCode` enum replacing silent NEUTRAL with explicit diagnostics:

| Code | Trigger |
|---|---|
| SCORE_BELOW_THRESHOLD | \|score\| < threshold |
| CONFIDENCE_ZERO_BUG | score nonzero, confidence=0, aurora_dir=0 detected |
| MISSING_FEATURES | fail_closed in upstream_why |
| REGIME_NOT_ALLOWED | regime not in allowed_regimes list |
| SCENARIO_DISABLED | scenario.enabled=False |
| SHADOW_SIGNAL_EMITTED | BUY or SELL decision produced |

`ShadowSignalEvent` enforces immutable boundary fields via `__post_init__`:
```python
object.__setattr__(self, "shadow_only", True)
object.__setattr__(self, "authority_applied", False)
object.__setattr__(self, "no_effect", True)
```

---

## PHASE 2 — 30-Scenario Registry

**Files:** `apps/reference/domains/alpha_search/shadow/scenario_registry.py`, `config/alpha_search/scenario_registry_v2.yaml`

### Strategy Families

| Family | Scenarios | Entry Threshold Range | UNCERTAIN Multiplier |
|---|---|---|---|
| mean_reversion | S01–S06 | 0.06–0.18 | 1.20–1.50 |
| trend_continuation | S07–S12 | 0.07–0.15 | 1.20–1.50 |
| volatility_breakout | S13–S17 | 0.07–0.10 | 1.20–1.60 |
| microstructure | S18–S23 | 0.07–0.09 | 1.20–1.30 |
| regime_adaptive | S24–S28 | 0.06–0.08 | 1.20–1.30 |
| cost_execution | S29–S30 | 0.09–0.12 | 1.30–1.40 |

### Key Improvements vs Current Runtime
- Entry threshold: **0.06–0.18** vs 0.28–0.38 (3–5× lower)
- UNCERTAIN multiplier: **1.20–1.80** vs 3.00 (significantly reduced)
- Allowed regimes: **includes UNCERTAIN and LOW_VOLATILITY** for most scenarios
- `scenario_matrix.yaml` updated: `max_scenarios: 12 → 30`

### Registry Validator Guards
- `shadow_only=False` → `ValidationError` at Pydantic construction
- `authority_applied=True` → `ValidationError`
- `< 25 enabled scenarios` → `ValidationError`
- `duplicate scenario_ids` → `ValidationError`

---

## PHASE 3 — Virtual Lifecycle Engine

**File:** `apps/reference/domains/alpha_search/shadow/virtual_lifecycle.py`

Simulates shadow virtual trade PnL from signal + future price bars. Never touches real execution.

### Exit Models
| Model | Description |
|---|---|
| horizon_1_bar | Exit after 1 bar |
| horizon_3_bar | Exit after 3 bars |
| horizon_6_bar | Exit after 6 bars |
| fixed_tp_sl | Exit at TP/SL thresholds in bps |
| trailing_giveback | Trailing stop from peak |
| microstructure_reversal_exit | Exit on microstructure signal |

### Metrics per Trade
- `virtual_pnl_bps`, `virtual_pnl_usdt`
- `max_favorable_excursion_bps` (MFE), `max_adverse_excursion_bps` (MAE)
- `time_to_mfe_bars`, `time_to_mae_bars`
- `regime_at_entry`, `regime_at_exit`, `bars_held`
- `exit_reason`, `virtual_fee_bps`, `virtual_slippage_bps`

---

## PHASE 4 — WAL Comparison Analysis

**File:** `apps/reference/domains/alpha_search/shadow/wal_comparator.py`

### Real WAL Summary (2026-05-11 to 2026-05-15)
| Metric | Value |
|---|---|
| Total WAL events | 65,811 |
| OBJECTIVE_REALIZED_V1 (closed trades) | 16 |
| TP outcomes | 4 (25%) |
| SL outcomes | 12 (75%) |
| mean_reversion trades | 11 |
| md_amr trades | 5 |
| STRATEGY_DECISION_BLOCKED | 1,200 |
| TRADE_INTENT_PROPOSED | 67 |
| TRADE_INTENT_REJECTED | 172 |

**Note:** Real trading losses are NOT caused by alpha_search (which is shadow-only). The 75% SL rate is a real trading system issue independent of the shadow laboratory.

### Comparison Labels
```
WOULD_AVOID_REAL_SL    — shadow NEUTRAL when real had SL → avoidance
WOULD_CATCH_REAL_TP    — shadow same direction as real TP → capture
WOULD_FALSELY_SKIP_TP  — shadow NEUTRAL when real had TP → miss
WOULD_FALSELY_ENTER_LOSS — shadow same direction as real SL → false entry
NO_DIFFERENCE          — outcome unchanged
DATA_GAP               — no shadow data near trade time
```

---

## PHASE 5 — Metrics Engine

**File:** `apps/reference/domains/alpha_search/shadow/metrics_engine.py`

**25 metrics per scenario** including:
`signal_count`, `buy_count`, `sell_count`, `virtual_win_rate`, `avg_virtual_pnl_bps`, `median_virtual_pnl_bps`, `total_virtual_pnl_bps`, `max_drawdown_bps`, `profit_factor`, `sharpe_ratio`, `mfe_mean_bps`, `mae_mean_bps`, `fee_impact_bps`, `slippage_impact_bps`, `expectancy_bps`, `duplicate_score_ratio`, `scenario_uniqueness_score`

**Cross-scenario aggregates:** best/worst by expectancy, high-duplicate detection (dup_ratio > 0.9), Pearson pairwise correlations.

---

## PHASE 6 — Tests

**File:** `tests/apps/reference/domains/alpha_search/tests/test_shadow_expansion.py`

18 tests covering all acceptance criteria:
1. Registry validates ≥25 enabled scenarios
2. No scenario missing required fields
3. All scenario specs carry shadow_only=True, authority_applied=False, no_effect=True
4. ShadowSignalEvent authority fields immutable
5. Score > threshold → BUY
6. Score < −threshold → SELL
7. Derived confidence > 0 when score valid + no fail_closed
8. Derived confidence = 0 on fail_closed
9. Below-threshold → NEUTRAL + SCORE_BELOW_THRESHOLD reason code
10. Duplicate fingerprint detection
11. Virtual lifecycle has no real trading verbs
12. Virtual lifecycle output authority fields correct
13. Authority guard rejects forbidden verb (ORDER_INTENT)
14. Authority guard rejects shadow_only=False
15. Authority guard passes clean event
16. All shadow module imports succeed
17. Registry scenario_ids are unique
18. Registry rejects shadow_only=False construction

---

## Authority Boundary Statement

This expansion does not modify:
- `DecisionMaker`, `ExecutionPosition`, `PositionPolicySidecar`
- TPSL logic, risk gates, exchange connectors
- Real WAL write paths
- Real order submission or position FSM

All new code is strictly shadow-only. Any event produced carries:
```json
{"shadow_only": true, "authority_applied": false, "no_effect": true}
```
Authority guard (`authority_guard.py`) enforces this at runtime and in tests.

---

## Report Artifacts

| File | Description |
|---|---|
| `reports/ALPHA_SEARCH_SHADOW_SCENARIO_EXPANSION_V1.md` | This document |
| `reports/ALPHA_SEARCH_CURRENT_SIGNAL_PATH_AUDIT.csv` | Per-scenario signal path failure analysis |
| `reports/ALPHA_SEARCH_SCENARIO_REGISTRY_V1.csv` | Full 30-scenario registry dump |
| `reports/ALPHA_SEARCH_SCENARIO_RESULTS_V1.csv` | Virtual trade results (baseline = 0, pending first run) |
| `reports/ALPHA_SEARCH_SCENARIO_DIVERSITY_MATRIX.csv` | Scenario diversity parameters |
| `reports/ALPHA_SEARCH_SHADOW_AUTHORITY_AUDIT.json` | Module-by-module authority boundary audit |
| `reports/ALPHA_SEARCH_SCENARIO_EXPANSION_SUMMARY.json` | Machine-readable phase completion summary |
