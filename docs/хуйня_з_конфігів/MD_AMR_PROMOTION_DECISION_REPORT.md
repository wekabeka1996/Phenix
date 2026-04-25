# MD_AMR Overlay Promotion Decision Report

**Date**: 2026-04-16
**Decision Authority**: Governance review — evidence-first, fail-closed
**Scope**: Packages C.1, C.2, C.3, C.4 — promotion eligibility into hard behavioral influence
**Frozen Baseline**: Package A.1 (`max_hold_bars=16`, `target_approach_pct=0.0`)

---

## 1. Current Evidence Base

### 1.1 Integrated Validation (Bounded Strategy-Core Replay)

| Metric | BNBUSDT | XRPUSDT | COMBINED |
|--------|---------|---------|----------|
| Baseline trades | 118 | 215 | 333 |
| Integrated trades | 118 | 215 | 333 |
| Trade count delta | 0 | 0 | 0 |
| Exact trade match rate | 100% | 100% | 100% |
| Net return ratio delta | 0.0 | 0.0 | 0.0 |
| Win rate delta | 0.0 | 0.0 | 0.0 |
| Avg holding bars delta | 0.0 | 0.0 | 0.0 |
| Economic parity | True | True | True |
| Explainability gain | True | True | True |

**FACT**: Integrated validation confirms strict economic parity. Zero behavioral divergence between baseline A.1 and C.1–C.4 integrated line.

**FACT**: Explainability gain confirmed — overlay trace fields populated on all 333 trades.

**INFERENCE**: Overlays are purely additive observability. They do not touch entry/exit decision paths in the current code.

### 1.2 Cohort Evidence — Profitable Slow Reversions

| Symbol | Count | Net Return | Avg Hold Bars | Exit HQ Mean | Exit CV Mean |
|--------|-------|------------|---------------|-------------|-------------|
| BNBUSDT | 8 | +0.0319 | 14.9 | 0.354 | 0.346 |
| XRPUSDT | 11 | +0.0261 | 16.5 | 0.251 | 0.352 |

**FACT**: Profitable slow reversions exist in both symbols. They hold 14–17 bars (near `max_hold_bars=16` ceiling).

**FACT**: Their exit hold_quality scores are low-moderate (0.25–0.35), meaning any hard hold_quality gate at typical thresholds (e.g., 0.4+) would penalize or kill these trades.

**FACT**: Their context_validity scores are moderate (0.35), meaning a hard context-invalidity close at typical thresholds (e.g., `invalid_score_max=0.35`) would cut exactly these trades.

**INFERENCE**: Hard promotion of C.3 or C.4 at current thresholds carries direct risk of destroying the profitable slow-reversion cohort — the most economically valuable subset.

### 1.3 Overlay Score Distributions

| Metric | BNBUSDT | XRPUSDT |
|--------|---------|---------|
| Entry setup_quality mean | 0.546 | 0.578 |
| Entry setup_quality p25–p75 | 0.520–0.593 | 0.535–0.635 |
| Exit hold_quality mean | 0.217 | 0.261 |
| Exit context_validity mean | 0.299 | 0.317 |
| Weak context exit count | 118 (100%) | 200 (93%) |
| Valid context exit count | 0 (0%) | 0 (0%) |

**FACT**: Zero trades exit in VALID context state. 100% of BNBUSDT and 93% of XRPUSDT trades exit with WEAK context.

**INFERENCE**: The context_validity scoring, at current weights and thresholds, classifies virtually all trade exits as weak-context. This means it has no discriminatory power for hard gating — promoting it would either (a) close every position prematurely, or (b) require threshold changes that are out of scope.

**FACT**: Hold quality scores are low across the board (mean 0.22–0.26), with p25 at 0.0. This reflects the structural reality that most md_amr trades are timeout-dominated (156/333 = 47% timeout exits) and progress is typically incomplete at exit.

### 1.4 Runtime Evidence

**FACT** (from memory): XRPUSDT and BNBUSDT have proven live execution paths through md_amr handler. Strategy is active and trading on the current A.1 baseline.

**FACT**: No post-patch live/testnet data exists for C.1–C.4 as behavioral controllers. The overlays have only been observed as advisory trace fields in replay.

### 1.5 What This Evidence Does NOT Contain

- **UNKNOWN**: No matched-cohort action proof (e.g., "trades with hold_quality > 0.5 had better outcomes than those below 0.5").
- **UNKNOWN**: No end-to-end evidence beyond strategy-core replay (no live execution, no slippage, no real market conditions).
- **UNKNOWN**: No per-trade counterfactual analysis (e.g., "if C.3 had vetoed trade #47, what would the portfolio outcome be").
- **UNKNOWN**: No live overlay distribution under real market microstructure (replay distributions may differ from live).

---

## 2. Package-by-Package Status

### Package C.1 — Anchored Target + Progress Tracking

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Implemented | YES | `md_amr_strategy.py:390–439`, handler anchors at lines 1995–2011 |
| Validated at package boundary | YES | Unit tests in `test_md_amr_package_c1_progress.py` |
| Trace-visible | YES | `progress_pct`, `progress_state`, `entry_price`, `entry_target_price` emitted every hold bar |
| Deterministic | YES | Pure function of frozen entry anchors + bars_held |
| Architecture-safe | YES | No side effects; anchors set at entry, cleared at close; graceful cold-start fallback |

### Package C.2 — Minimal Setup Quality

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Implemented | YES | `md_amr_strategy.py:441–506`, entry trace at lines 924–935, 953–964 |
| Validated at package boundary | YES | Unit tests in `test_md_amr_package_c2_setup_quality.py` |
| Trace-visible | YES | `setup_quality`, `sq_penetration`, `sq_channel_quality`, `sq_coherence`, `sq_volatility` at entry |
| Deterministic | YES | Pure function of signal inputs at entry time |
| Architecture-safe | YES | Entry-only, no state carried, explicit code comment: "observability-only" |

### Package C.3 — Hold Quality / Soft Decay

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Implemented | YES | `md_amr_strategy.py:508–568`, hold trace at lines 1011–1056 |
| Validated at package boundary | YES | Unit tests in `test_md_amr_package_c3_hold_quality.py`, handler contract in `test_md_amr_package_c3_handler_contract.py`, config contract in `test_md_amr_package_c3_config_contract.py` |
| Trace-visible | YES | `hold_quality`, `time_decay`, `progress_deficit`, `hold_quality_penalty` emitted every hold bar |
| Deterministic | YES | Pure function of bars_held, hold_health, progress_pct, config weights |
| Architecture-safe | YES | Explicit advisory design; exit logic remains A.1 (`hold_edge_min`, `max_hold_bars`, fee-aware scaleout) |

### Package C.4 — Lightweight Context Validity

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Implemented | YES | `md_amr_strategy.py:570–803`, hold trace at lines 1058–1073, handler context at lines 896–925 |
| Validated at package boundary | YES | Unit tests in `test_md_amr_package_c4_context_validity.py`, handler contract in `test_md_amr_package_c4_handler_contract.py`, config contract in `test_md_amr_package_c4_config_contract.py` |
| Trace-visible | YES | `context_validity`, `context_validity_state`, `context_penalty_reason`, 4 component scores emitted every hold bar |
| Deterministic | YES | Pure function of regime, ATR z-score, channel width, directional coherence, hold_quality, config weights |
| Architecture-safe | YES | Explicit config comment: "advisory only in this package"; no exit/veto path wired |

---

## 3. Promotion Eligibility Assessment

### Promotion Standard (Restated)

A package may be promoted into hard behavioral influence only if there is evidence for:

1. Economic benefit or at least justified behavioral value
2. No unacceptable damage to valid slow reversions
3. End-to-end relevance beyond strategy-core trace
4. Acceptable blast radius
5. Clear operational semantics

### Assessment Against Each Standard

#### Standard 1 — Economic benefit or behavioral value

**C.1**: No economic benefit (advisory). Behavioral value: anchored progress tracking enables downstream consumers. **Met for advisory; NOT met for hard behavior.**

**C.2**: No economic benefit (advisory). Behavioral value: entry quality scoring enables future entry-gating. **Met for advisory; NOT met for hard behavior** — no evidence that low-SQ trades underperform.

**C.3**: No economic benefit demonstrated. **NOT met.** Hold quality scores inversely correlate with the profitable slow-reversion cohort (their HQ scores are low). Promoting HQ as an exit gate would harm the best trades.

**C.4**: No economic benefit demonstrated. **NOT met.** 100% of BNBUSDT exits and 93% of XRPUSDT exits register as WEAK context. Zero discriminatory power at current thresholds. Promoting CV as a close trigger would either close everything or close nothing.

#### Standard 2 — No damage to slow reversions

**C.3**: **FAILED.** Profitable slow reversions have hold_quality mean 0.25–0.35. Any hard threshold above ~0.20 risks cutting them. These 19 trades (8+11) account for the entire positive-return subset (+0.058 combined net return).

**C.4**: **FAILED.** Same cohort has context_validity ~0.35. The configured `invalid_score_max=0.35` would classify them as borderline INVALID.

#### Standard 3 — End-to-end relevance

**All packages**: **NOT met.** Evidence is strategy-core replay only. No live execution data, no real slippage interaction, no position-sizing influence observed.

#### Standard 4 — Acceptable blast radius

**C.1, C.2**: Blast radius is zero (advisory-only by design, no exit/entry path).

**C.3**: Blast radius HIGH if promoted — would affect 47% of trades (timeout exits) and risk destroying slow-reversion profits.

**C.4**: Blast radius EXTREME if promoted — would affect 93–100% of trade exits (all WEAK context).

#### Standard 5 — Clear operational semantics

**C.1, C.2**: Clear. Trace-only, well-defined field semantics.

**C.3**: Operational semantics as advisory are clear. As a hard exit gate, semantics are ambiguous — what hold_quality threshold constitutes "must close"? No evidence-based answer exists.

**C.4**: Same. As advisory, clear. As a hard close trigger, undefined — current thresholds produce no discrimination.

---

## 4. What Is Accepted Advisory-Only

### C.1 — Anchored Target + Progress Tracking
**Classification**: `ACCEPTED_ADVISORY_ONLY`

Accepted as an observability and explainability layer. Progress tracking provides:
- Frozen-anchor reversion distance measurement
- Progress state taxonomy (REVERSING_AGAINST through COMPLETE)
- Foundation for C.3 expected-progress calculations
- Operator visibility into mean-reversion lifecycle

Not a candidate for hard behavioral promotion in any form (progress itself is not a decision variable).

### C.2 — Minimal Setup Quality
**Classification**: `ACCEPTED_ADVISORY_ONLY`

Accepted as an entry-time quality snapshot. Setup quality provides:
- Composite score from penetration, channel quality, coherence, volatility
- Entry-only trace enrichment
- Foundation for future entry-gate analysis

Not promoted because no evidence exists that low-SQ entries produce worse outcomes than high-SQ entries. The matched-cohort proof is missing.

### C.3 — Hold Quality / Soft Decay
**Classification**: `ACCEPTED_ADVISORY_ONLY`

Accepted as an in-position health overlay. Hold quality provides:
- Time decay signal
- Progress deficit tracking
- Composite hold health score
- Operator visibility into position deterioration dynamics

Not promoted because:
- Profitable slow reversions score LOW on hold_quality (0.25–0.35)
- Any meaningful hard threshold would cut the system's best trades
- No matched-cohort evidence that low-HQ trades are net-harmful

### C.4 — Lightweight Context Validity
**Classification**: `ACCEPTED_ADVISORY_ONLY`

Accepted as a contextual environment overlay. Context validity provides:
- Multi-component environment quality assessment (regime, volatility, structure, progress alignment)
- State classification (VALID/WEAKENING/INVALID)
- Penalty reason attribution
- Foundation for future context-aware decision making

Not promoted because:
- 93–100% of trade exits register as WEAK context — zero discriminatory power
- Current threshold calibration produces no meaningful separation
- Promoting as close trigger would be operationally equivalent to "close everything"

---

## 5. What Is Not Promoted and Why

### No Package Is Promoted

| Package | Promotion Status | Primary Cause | Mechanism | Operational Risk Avoided | Evidence Gap |
|---------|-----------------|---------------|-----------|-------------------------|-------------|
| C.1 | NOT PROMOTED | Not a decision variable | Progress is observational, not actionable | N/A — no promotion path exists by design | N/A |
| C.2 | NOT PROMOTED | No entry-quality→outcome correlation | SQ scores cluster 0.52–0.63 with no proven link to trade P&L | Rejecting valid entries based on unproven SQ threshold | Matched-cohort: do low-SQ entries actually underperform? |
| C.3 | NOT PROMOTED | Inverse correlation with profitable trades | HQ penalizes slow reversions (long holds, incomplete progress) which are the best performers | Cutting the only reliably profitable cohort (19 trades, +0.058 net) | Cohort action proof: what is the P&L of HQ>0.4 vs HQ<0.4 trades? |
| C.4 | NOT PROMOTED | Zero discriminatory power | 93–100% exits classified WEAK; no separation between good and bad trades | Mass premature closure or no-op depending on threshold | Threshold recalibration + discriminant analysis on real distributions |

---

## 6. Evidence Still Missing

### 6.1 Matched-Cohort Action Proof (Required for C.2, C.3)

**What**: Split the 333 validated trades by overlay score thresholds and compare economic outcomes between cohorts.

**Specifically**:
- C.2: Do trades with `setup_quality > median` have better net return than trades with `setup_quality < median`?
- C.3: Do trades with `exit_hold_quality > X` have better net return than those below? At what threshold `X`?
- C.3: For timeout trades specifically (n=156), does hold_quality at exit predict whether the trade was profitable?

**Why this matters**: Without this, we cannot set evidence-based thresholds. Any threshold chosen is arbitrary.

### 6.2 Slow-Reversion Sensitivity Analysis (Required for C.3)

**What**: Simulate C.3 as a hard exit trigger at various thresholds (0.15, 0.20, 0.25, 0.30, 0.35, 0.40) and measure:
- How many of the 19 profitable slow reversions survive at each threshold
- Net portfolio P&L impact at each threshold
- Whether any threshold exists that cuts losing slow holds without cutting profitable ones

**Why this matters**: The profitable slow-reversion cohort is the economic justification for md_amr. Destroying it is unacceptable.

### 6.3 Context Validity Discriminant Recalibration (Required for C.4)

**What**: Analyze the distribution of `context_validity` scores across the 333-trade set. Determine:
- Is there ANY score threshold that separates profitable from unprofitable trades?
- Are the current component weights (regime 0.35, volatility 0.20, structure 0.20, progress_alignment 0.25) producing useful separation?
- Does `context_validity_state` VALID/WEAKENING/INVALID correlate with trade outcome at all?

**Why this matters**: With 93–100% of exits classified WEAK, the current scoring has collapsed into a near-constant. It needs recalibration before it can inform any decision.

### 6.4 Live/Testnet Post-Overlay Observation Period (Required for all)

**What**: Run the current advisory overlay line in live/testnet for a minimum observation period with explicit overlay field logging. Collect:
- Real-time overlay score distributions under live market conditions
- Whether replay-derived distributions match live distributions
- Whether any overlay value clusters predict post-trade outcome

**Why this matters**: Replay is bounded strategy-core. Real execution involves slippage, latency, market microstructure. Overlay scores may behave differently in production.

---

## 7. Recommended Next Evidence Package

### Package D.1: Matched-Cohort Overlay Analysis

**Objective**: Determine whether C.2/C.3/C.4 overlay scores have any predictive power over trade economic outcome.

**Method**:
1. Using the existing 333-trade integrated validation dataset with overlay scores already populated:
   - Split by setup_quality median → compare net return per cohort
   - Split by hold_quality quartiles → compare net return per cohort
   - Split by context_validity quartiles → compare net return per cohort
   - For timeout trades only (n=156): regression of overlay scores against trade P&L
2. Produce a decision matrix: for each overlay, at each candidate threshold, what is the trade-off (trades cut, P&L impact, slow-reversions impacted).

**Deliverable**: `reports/md_amr_overlay_cohort_analysis.csv` + decision summary

**Scope**: Analysis only. No code changes. No threshold changes. No promotion.

**Prerequisite for**: Any future reconsideration of C.2/C.3/C.4 promotion.

---

## 8. Final Promotion Verdict

```
+=========================================================+
|                                                         |
|              VERDICT: NO PROMOTION YET                  |
|                                                         |
+=========================================================+
```

### Classification Summary

| Package | Classification | Rationale |
|---------|---------------|-----------|
| C.1 | `ACCEPTED_ADVISORY_ONLY` | Observability layer by design; not a decision variable |
| C.2 | `ACCEPTED_ADVISORY_ONLY` | Entry quality scoring works; no outcome-correlation proof |
| C.3 | `ACCEPTED_ADVISORY_ONLY` | Hold quality scoring works; inverse correlation with best trades blocks promotion |
| C.4 | `ACCEPTED_ADVISORY_ONLY` | Context validity scoring works; zero discriminatory power at current calibration blocks promotion |

### Formal Disposition

All four overlay packages (C.1–C.4) are **accepted as implemented, validated, trace-visible, deterministic, and architecture-safe advisory overlays**.

No overlay package is promoted into hard behavioral influence (exit veto, close trigger, intent suppressor, entry gate, or capital-allocation gate).

Promotion is blocked by:
1. **Absence of matched-cohort action proof** — no evidence that overlay scores predict trade outcomes
2. **Direct risk to profitable slow reversions** — C.3 scores inversely correlate with the best-performing trade cohort
3. **Zero discriminatory power** in C.4 — current calibration collapses to near-constant WEAK classification
4. **No live/testnet overlay observation** — all evidence is replay-derived

The safe accepted baseline remains **Package A.1** (`max_hold_bars=16`, `target_approach_pct=0.0`). The C.1–C.4 overlays continue to run as advisory trace enrichment with no behavioral impact.

### Next Gate

Promotion may be reconsidered only after **Package D.1 (Matched-Cohort Overlay Analysis)** is completed and demonstrates:
- At least one overlay score with statistically meaningful outcome separation, AND
- A threshold that does not destroy the profitable slow-reversion cohort, AND
- Clear operational semantics for the promoted behavior.

Until then, the overlays remain advisory-only. This is the correct governance posture given the evidence.

---

*Report generated: 2026-04-16*
*Evidence base: `reports/md_amr_integrated_validation_summary.csv`, `reports/md_amr_integrated_validation_cohorts.csv`, `reports/md_amr_integrated_validation_by_symbol.csv`*
*Frozen baseline: Package A.1*
*Decision standard: fail-closed on promotion*
