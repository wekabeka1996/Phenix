# MD_AMR Package D.1 — Matched-Cohort Overlay Analysis

**Date**: 2026-04-16
**Package**: D.1 (Analysis-only — no code changes, no threshold tuning, no promotion)
**Frozen Baseline**: Package A.1 (`max_hold_bars=16`, `target_approach_pct=0.0`)
**Prior Governance**: C.1–C.4 = `ACCEPTED_ADVISORY_ONLY`, `NO PROMOTION YET`

---

## 1. Input Dataset

**Source**: `reports/md_amr_integrated_validation_trades.csv` — per-trade export from the existing integrated-validation tool (`tools/analysis/md_amr_integrated_validation.py`), extended with a `--trades-out` argument for this package.

| Attribute | Value |
|-----------|-------|
| Arm | `integrated_c1234` (overlay-equipped trades only) |
| Total trades | 369 |
| BNBUSDT trades | 123 |
| XRPUSDT trades | 246 |
| Trades with overlay data | 353 (16 trades have no in-position overlay bars — immediate exits) |
| Slow profitable reversions | 19 (8 BNBUSDT, 11 XRPUSDT) |
| Overall win rate | 49.9% |
| Overall net return | -0.2404 (net-negative after fees) |
| Timeframe | 15m bars, ~39–64 trading days per symbol |

**FACT**: The input dataset is the same bounded strategy-core replay that produced the original integrated-validation results. Trade parity with baseline A.1 was previously confirmed at 100%.

**FACT**: 19 slow profitable reversions are identified (holding ≥ 13 bars AND profitable). These account for combined net return of +0.058 — the only reliably positive subset.

---

## 2. Cohort Method

For each overlay variable, the following cohort families were constructed:

1. **Median split**: Below median vs at-or-above median
2. **Quartile split**: Q1 (≤ p25), Q2 (p25–median), Q3 (median–p75), Q4 (≥ p75)
3. **Threshold ladder sweep**: Fixed candidate thresholds testing "filter below threshold" impact

Outcome variables measured per cohort:
- `n` (trade count), `win_rate`, `net_return_sum`, `net_return_mean`, `avg_holding_bars`
- `slow_rev_count` (slow profitable reversions in cohort)
- Exit type counts: `timeout`, `stop_hit`, `scaleout`, `target_hit`

All analyses are shown for BNBUSDT, XRPUSDT, and COMBINED separately.

**Analysis tool**: `tools/analysis/md_amr_d1_cohort_analysis.py`

---

## 3. Setup Quality Analysis

### Correlation with Returns

| Symbol | Pearson r (SQ vs net_return) | Direction |
|--------|------------------------------|-----------|
| BNBUSDT | **-0.0844** | Weakly negative |
| XRPUSDT | **-0.0923** | Weakly negative |
| COMBINED | **-0.0889** | Weakly negative |

**FACT**: Setup quality has a weak *negative* correlation with trade returns across both symbols. Higher SQ at entry is associated with marginally *worse* outcomes, not better.

### Median Split

| Symbol | Cohort | N | Win Rate | Net PnL | Slow Revs |
|--------|--------|---|----------|---------|-----------|
| BNBUSDT | Below median (< 0.554) | 61 | 42.6% | -0.0233 | 5 |
| BNBUSDT | Above median (≥ 0.554) | 62 | 45.2% | -0.0558 | 3 |
| XRPUSDT | Below median (< 0.582) | 123 | 52.8% | -0.0609 | 5 |
| XRPUSDT | Above median (≥ 0.582) | 123 | 52.8% | -0.1004 | 6 |
| COMBINED | Below median (< 0.569) | 184 | 48.9% | -0.1045 | 9 |
| COMBINED | Above median (≥ 0.569) | 185 | 50.8% | -0.1359 | 10 |

**FACT**: Above-median SQ trades have *worse* total PnL than below-median in both symbols and combined.

**FACT**: Win rates are effectively identical between cohorts (no meaningful separation).

**FACT**: Slow profitable reversions are distributed roughly evenly (9 below, 10 above median).

### Quartile Analysis

| Symbol | Quartile | N | Win Rate | Net PnL | Slow Revs |
|--------|----------|---|----------|---------|-----------|
| COMBINED | Q1 (lowest SQ) | 92 | 54.3% | +0.0002 | 6 |
| COMBINED | Q2 | 92 | 43.5% | -0.1046 | 3 |
| COMBINED | Q3 | 92 | 56.5% | -0.0029 | 5 |
| COMBINED | Q4 (highest SQ) | 93 | 45.2% | -0.1330 | 5 |

**FACT**: Q1 (lowest SQ) has the *best* net PnL (+0.0002, near breakeven) and highest win rate (54.3%). Q4 (highest SQ) has the *worst* PnL (-0.133) and lowest win rate (45.2%).

**INFERENCE**: Setup quality has no predictive value for trade outcomes. The relationship is, if anything, inverse — contradicting the intuition that higher entry quality should produce better trades.

### Threshold Sweep (Setup Quality)

| Symbol | Threshold | Trades Removed | PnL Delta | Slow Revs Lost |
|--------|-----------|----------------|-----------|-----------------|
| COMBINED | p25 (0.530) | 92 | -0.0002 | 6/19 (31.6%) |
| COMBINED | median (0.569) | 185 | +0.1041 | 9/19 (47.4%) |
| COMBINED | p75 (0.616) | 277 | +0.1149 | 14/19 (73.7%) |

**FACT**: Filtering low-SQ trades at the p25 threshold actually *worsens* PnL while destroying 31.6% of slow reversions. Higher thresholds improve PnL by removing more trades (effectively reducing exposure), but destroy 47–74% of slow reversions.

**INFERENCE**: SQ-based filtering has no useful threshold. Positive PnL deltas at higher thresholds are driven by removing many net-negative trades indiscriminately — not by SQ having signal.

### Setup Quality Verdict

**CLASSIFICATION**: `NO PREDICTIVE POWER`

- **FACT**: Correlation is weakly negative (r = -0.089)
- **FACT**: Highest-SQ quartile produces worst returns
- **FACT**: No threshold separates good from bad trades without destroying slow reversions
- **INFERENCE**: Setup quality does not predict trade outcome. It should remain advisory-only. No threshold merits further study.

---

## 4. Hold Quality Analysis

### Correlation with Returns

| Symbol | Pearson r (HQ vs net_return) | Direction |
|--------|------------------------------|-----------|
| BNBUSDT | **+0.6195** | Strong positive |
| XRPUSDT | **+0.4292** | Moderate positive |
| COMBINED | **+0.4566** | Moderate positive |

**FACT**: Hold quality shows the strongest return correlation of any overlay — r = 0.46 combined, r = 0.62 on BNBUSDT.

### Median Split

| Symbol | Cohort | N | Win Rate | Net PnL | Slow Revs | Avg Bars |
|--------|--------|---|----------|---------|-----------|----------|
| BNBUSDT | Below median (< 0.094) | 61 | 8.2% | -0.176 | 2 | 7.8 |
| BNBUSDT | Above median (≥ 0.094) | 62 | 79.0% | +0.097 | 6 | 5.7 |
| XRPUSDT | Below median (< 0.289) | 115 | 23.5% | -0.432 | 6 | 8.6 |
| XRPUSDT | Above median (≥ 0.289) | 115 | 80.0% | +0.213 | 5 | 4.9 |
| COMBINED | Below median (< 0.238) | 176 | 17.0% | -0.600 | 7 | 8.3 |
| COMBINED | Above median (≥ 0.238) | 177 | 80.8% | +0.302 | 12 | 5.2 |

**FACT**: The median split produces dramatic separation. Above-median HQ trades have ~81% win rate and positive PnL; below-median have ~17% win rate and deeply negative PnL.

**FACT**: 12 of 19 slow profitable reversions (63%) are above median HQ. 7 (37%) are below median.

**CRITICAL FACT**: The 7 slow reversions below median HQ are real and profitable. They would be killed by a median-based filter.

### Quartile Analysis (COMBINED)

| Quartile | N | Win Rate | Net PnL | Slow Revs | Avg Bars |
|----------|---|----------|---------|-----------|----------|
| Q2 (HQ 0.0–0.238) | 176 | 17.0% | -0.600 | 7 | 8.3 |
| Q3 (HQ 0.238–0.468) | 88 | 65.9% | -0.012 | 6 | 4.6 |
| Q4 (HQ ≥ 0.468) | 89 | 95.5% | +0.314 | 6 | 5.8 |

**FACT**: Q4 (HQ ≥ 0.468) has 95.5% win rate and +0.314 net return. This is the "clean" zone.

**FACT**: Q3 is near breakeven (-0.012) with 65.9% win rate. Marginal zone.

**FACT**: Q2 is deeply negative (-0.600) with 17% win rate. This is where nearly all losses concentrate.

**INFERENCE**: HQ has genuine stratification power. The low-HQ zone is strongly associated with losing trades.

### Threshold Sweep (Hold Quality)

| Symbol | Threshold | Removed | PnL Delta | Bad Removed | Good Removed | Slow Revs Lost | Ratio (bad:good) |
|--------|-----------|---------|-----------|------------|-------------|-----------------|-------------------|
| COMBINED | 0.15 | 163 | +0.568 | 139 | 24 | 7/19 (36.8%) | 5.8:1 |
| COMBINED | 0.20 | 169 | +0.595 | 143 | 26 | 7/19 (36.8%) | 5.5:1 |
| COMBINED | 0.25 | 179 | +0.612 | 147 | 32 | 7/19 (36.8%) | 4.6:1 |
| COMBINED | 0.30 | 188 | +0.627 | 153 | 35 | 9/19 (47.4%) | 4.4:1 |
| COMBINED | 0.35 | 198 | +0.654 | 158 | 40 | 9/19 (47.4%) | 4.0:1 |
| COMBINED | 0.40 | 216 | +0.706 | 166 | 50 | 11/19 (57.9%) | 3.3:1 |

**FACT**: At threshold 0.25, the filter removes 179 trades (147 bad, 32 good) — a 4.6:1 bad-to-good ratio — with PnL improvement of +0.612. This destroys 7/19 slow reversions (36.8%).

**FACT**: At threshold 0.30, the step from 7 to 9 slow reversions lost indicates a cliff — the threshold 0.25–0.30 zone catches 2 additional slow reversions.

**FACT**: No threshold exists that removes zero slow reversions. Even at 0.15, 7 of 19 slow reversions are below this floor.

### By-Symbol Stability

| Threshold | BNBUSDT Slow Revs Lost | XRPUSDT Slow Revs Lost |
|-----------|----------------------|----------------------|
| 0.15 | 2/8 (25.0%) | 5/11 (45.5%) |
| 0.20 | 2/8 (25.0%) | 5/11 (45.5%) |
| 0.25 | 2/8 (25.0%) | 5/11 (45.5%) |
| 0.30 | 3/8 (37.5%) | 6/11 (54.5%) |

**FACT**: XRPUSDT slow reversions are more vulnerable at every threshold — 45.5% lost at HQ ≥ 0.15 vs 25.0% on BNBUSDT. Symbol behavior is divergent.

**INFERENCE**: The slow-reversion risk is real and asymmetric by symbol. XRPUSDT is more exposed.

### Hold Quality Verdict

**CLASSIFICATION**: `MODERATE PREDICTIVE POWER, BUT FAILS SLOW-REVERSION SAFETY TEST`

- **FACT**: r = 0.46 combined — meaningful correlation
- **FACT**: Median split produces 17% vs 81% win rate separation — strong stratification
- **FACT**: Best candidate threshold (0.25) still destroys 36.8% of slow reversions
- **FACT**: 7 of 19 slow reversions have HQ < 0.15 — irreducible floor of slow-reversion casualties
- **INFERENCE**: HQ has real signal but cannot be safely promoted as a hard exit gate without accepting 37%+ slow-reversion destruction
- **UNKNOWN**: Whether a *partial* or *time-conditional* HQ gate (e.g., only after bar 12) could preserve more slow reversions — this was not tested

---

## 5. Context Validity Analysis

### Correlation with Returns

| Symbol | Pearson r (CV vs net_return) | Direction |
|--------|------------------------------|-----------|
| BNBUSDT | **+0.4742** | Moderate positive |
| XRPUSDT | **+0.4095** | Moderate positive |
| COMBINED | **+0.4134** | Moderate positive |

**FACT**: Context validity shows moderate positive correlation, slightly weaker than hold quality but still meaningful.

### Median Split

| Symbol | Cohort | N | Win Rate | Net PnL | Slow Revs |
|--------|--------|---|----------|---------|-----------|
| BNBUSDT | Below median (< 0.291) | 61 | 16.4% | -0.166 | 3 |
| BNBUSDT | Above median (≥ 0.291) | 62 | 71.0% | +0.087 | 5 |
| XRPUSDT | Below median (< 0.308) | 115 | 25.2% | -0.418 | 4 |
| XRPUSDT | Above median (≥ 0.308) | 115 | 78.3% | +0.199 | 7 |
| COMBINED | Below median (< 0.302) | 176 | 22.2% | -0.560 | 6 |
| COMBINED | Above median (≥ 0.302) | 177 | 75.7% | +0.262 | 13 |

**FACT**: Strong median separation: 22% vs 76% win rate. Below-median CV trades produce -0.560 PnL; above-median produce +0.262.

**FACT**: 13 of 19 slow reversions (68%) are above median CV. Better slow-reversion preservation than HQ (63%).

### Quartile Analysis (COMBINED)

| Quartile | N | Win Rate | Net PnL | Slow Revs |
|----------|---|----------|---------|-----------|
| Q1 (CV < 0.244) | 88 | 23.9% | -0.254 | 2 |
| Q2 (CV 0.244–0.302) | 88 | 20.5% | -0.306 | 4 |
| Q3 (CV 0.302–0.381) | 88 | 56.8% | -0.035 | 4 |
| Q4 (CV ≥ 0.381) | 89 | 94.4% | +0.297 | 9 |

**FACT**: Q4 has 94.4% win rate and +0.297 PnL. Nearly as strong as HQ Q4.

**FACT**: Q1 and Q2 are both deeply negative (20–24% win rate). Q3 is marginal.

### Threshold Sweep (Context Validity)

| Symbol | Threshold | Removed | PnL Delta | Bad Removed | Good Removed | Slow Revs Lost | Ratio (bad:good) |
|--------|-----------|---------|-----------|------------|-------------|-----------------|-------------------|
| COMBINED | 0.25 | 95 | +0.294 | 73 | 22 | 2/19 (10.5%) | 3.3:1 |
| COMBINED | 0.30 | 175 | +0.546 | 136 | 39 | 6/19 (31.6%) | 3.5:1 |
| COMBINED | 0.35 | 224 | +0.625 | 164 | 60 | 9/19 (47.4%) | 2.7:1 |
| COMBINED | 0.40 | 289 | +0.525 | 177 | 112 | 11/19 (57.9%) | 1.6:1 |
| COMBINED | 0.45 | 342 | +0.380 | 180 | 162 | 19/19 (100%) | 1.1:1 |
| COMBINED | 0.50 | 351 | +0.314 | 180 | 171 | 19/19 (100%) | 1.1:1 |

**CRITICAL FACT**: At threshold 0.25, only 2 of 19 slow reversions are lost (10.5%), while 73 bad trades and 22 good trades are removed, yielding PnL improvement of +0.294.

**FACT**: This is the best slow-reversion preservation of any overlay at any threshold tested.

**FACT**: At threshold 0.30, slow-reversion losses jump to 6/19 (31.6%) — a steep cliff.

**FACT**: At threshold 0.45+, ALL slow reversions are destroyed.

### By-Symbol at CV threshold 0.25

| Symbol | Removed | Bad Removed | Good Removed | Slow Revs Lost | PnL Delta |
|--------|---------|------------|-------------|-----------------|-----------|
| BNBUSDT | 35 | 28 | 7 | 2/8 (25.0%) | +0.084 |
| XRPUSDT | 60 | 45 | 15 | 0/11 (0.0%) | +0.210 |

**CRITICAL FACT**: On XRPUSDT, threshold CV ≥ 0.25 loses ZERO slow reversions while removing 60 trades (45 bad, 15 good) with PnL improvement of +0.210.

**FACT**: On BNBUSDT, 2 of 8 slow reversions are lost at the same threshold — symbol-divergent behavior.

### Context Validity Verdict

**CLASSIFICATION**: `MODERATE PREDICTIVE POWER WITH ONE CANDIDATE THRESHOLD WORTH FURTHER STUDY`

- **FACT**: r = 0.41 combined — meaningful correlation
- **FACT**: Median split produces 22% vs 76% win rate — strong stratification
- **FACT**: Threshold 0.25 is the only point in the entire analysis that loses ≤ 2 slow reversions while producing meaningful PnL improvement
- **FACT**: On XRPUSDT specifically, threshold 0.25 loses zero slow reversions
- **INFERENCE**: CV at 0.25 is the single most promising candidate for further investigation — but it still kills 2/19 slow reversions and has never been tested live
- **UNKNOWN**: Whether CV 0.25 as a soft signal (not hard close) could add value without any slow-reversion destruction

---

## 6. Threshold Sweep Results

### Summary — Best Candidate Per Overlay (COMBINED)

| Overlay | Best Threshold | Trades Removed | PnL Delta | Slow Revs Lost | Bad:Good Ratio | Verdict |
|---------|----------------|----------------|-----------|-----------------|----------------|---------|
| setup_quality | None viable | — | — | — | — | No signal |
| hold_quality | 0.25 | 179 (50.7%) | +0.612 | 7/19 (36.8%) | 4.6:1 | Signal exists but unacceptable slow-rev cost |
| context_validity | 0.25 | 95 (26.9%) | +0.294 | 2/19 (10.5%) | 3.3:1 | **Least destructive candidate** |

### Key Observations

1. **HQ 0.25 has the best absolute PnL delta (+0.612)** but destroys 7 slow reversions — 36.8% of the safety cohort.
2. **CV 0.25 has a smaller PnL delta (+0.294)** but preserves 17 of 19 slow reversions — the best preservation rate.
3. **No threshold for any overlay preserves all 19 slow reversions** with meaningful PnL improvement.
4. **SQ has no viable threshold** at any level.
5. **Both HQ and CV sweeps show steep cliffs** — PnL improvement plateaus quickly while slow-reversion destruction accelerates.

---

## 7. Slow Reversion Protection Analysis

### Individual Slow Reversion Overlay Scores

The 19 slow profitable reversions span a wide range of overlay scores:

| Statistic | Hold Quality | Context Validity | Min HQ | Min CV |
|-----------|-------------|-----------------|--------|--------|
| Mean | 0.287 | 0.341 | 0.098 | 0.228 |
| Median | 0.266 | 0.326 | 0.046 | 0.249 |
| Min | 0.000 | 0.126 | 0.000 | 0.088 |
| Max | 0.514 | 0.441 | 0.442 | 0.359 |

**FACT**: Some slow reversions have HQ = 0.0 at exit. These are trades that held the full duration with zero overlay-measured quality — but were still profitable.

**FACT**: The lowest CV among slow reversions is 0.126. Any CV threshold above 0.126 will destroy at least one slow reversion.

**FACT**: 7 slow reversions have HQ < 0.15 — these are structurally low-quality holds that happen to be profitable.

### Protection Thresholds

| Threshold Type | Value to Protect ALL 19 | Value to Protect ≥ 17 |
|----------------|------------------------|----------------------|
| HQ minimum | < 0.0 (impossible) | ≤ 0.08 (nearly zero filter power) |
| CV minimum | < 0.126 | ≤ 0.25 (loses 2) |

**INFERENCE**: Full slow-reversion protection is incompatible with any meaningful HQ threshold. CV at 0.25 is the only overlay that can protect 17/19 while still filtering substantial bad trades.

---

## 8. By-Symbol Results

### Correlation Stability

| Overlay | BNBUSDT r | XRPUSDT r | Stable? |
|---------|-----------|-----------|---------|
| setup_quality | -0.084 | -0.092 | YES — consistently no signal |
| hold_quality | +0.620 | +0.429 | PARTIAL — stronger on BNB |
| context_validity | +0.474 | +0.410 | YES — moderate on both |
| progress_deficit | -0.760 | -0.612 | YES — strong negative on both |

**FACT**: HQ correlation varies by symbol (0.62 vs 0.43) — BNBUSDT has stronger HQ signal.

**FACT**: CV correlation is more stable (0.47 vs 0.41).

**FACT**: Progress deficit shows the strongest absolute correlation (-0.76 BNB, -0.61 XRP) — higher deficit strongly associated with worse outcomes. This is expected (deficit = failing to make progress toward mean reversion).

### Win Rate Separation Stability (Median Split)

| Overlay | BNBUSDT Below/Above | XRPUSDT Below/Above | Stable? |
|---------|---------------------|---------------------|---------|
| setup_quality | 43%/45% | 53%/53% | YES — no separation |
| hold_quality | 8%/79% | 23%/80% | YES — strong on both |
| context_validity | 16%/71% | 25%/78% | YES — strong on both |

**FACT**: HQ and CV median-split win-rate separation is stable across symbols. The direction and magnitude are consistent.

### Slow Reversion Risk By Symbol at CV 0.25

**FACT**: XRPUSDT: 0/11 slow reversions lost (perfect preservation)
**FACT**: BNBUSDT: 2/8 slow reversions lost (25% destroyed)

**INFERENCE**: CV 0.25 has asymmetric safety — excellent for XRPUSDT, moderately risky for BNBUSDT. A per-symbol threshold approach might be warranted, but that increases complexity beyond this analysis scope.

---

## 9. What Is Proven

1. **`setup_quality` has no predictive power.** Correlation is weakly negative. Highest-SQ quartile produces worst returns. No usable threshold exists. (FACT: r = -0.089, Q4 PnL = -0.133 worst of all quartiles)

2. **`hold_quality` has genuine predictive power.** (FACT: r = 0.46, median split 17% vs 81% win rate, Q4 = 95.5% win rate) — but cannot be safely promoted because the irreducible slow-reversion floor at any meaningful threshold is 37%+ destruction.

3. **`context_validity` has genuine predictive power.** (FACT: r = 0.41, median split 22% vs 76% win rate, Q4 = 94.4% win rate) — and has one candidate threshold (0.25) that preserves 17/19 slow reversions with +0.294 PnL improvement.

4. **`progress_deficit` has the strongest raw signal.** (FACT: r = -0.62 to -0.76) — below-median deficit (healthy progress) has 87% win rate; above-median (stalled) has 13%. However, this is structurally entangled with hold duration and exit type, making it less useful as an independent gate.

5. **No overlay can be promoted without accepting some slow-reversion destruction.** The absolute minimum across all overlays and thresholds is 2/19 lost (CV at 0.25).

6. **Results are stable by symbol** for all overlays except HQ, which is stronger on BNBUSDT.

---

## 10. What Remains Unproven

1. **Whether CV 0.25 would improve live outcomes.** The +0.294 PnL delta is replay-derived. No live or testnet evidence exists. (UNKNOWN)

2. **Whether the 2 slow reversions lost at CV 0.25 are acceptable collateral.** This is a governance judgment, not an analytical finding. (ASSUMPTION if accepted: 10.5% slow-reversion destruction is tolerable)

3. **Whether time-conditional HQ gating (e.g., "only check HQ after bar 12") could reduce slow-reversion casualties.** Not tested in this package. (UNKNOWN)

4. **Whether overlay distributions in live market conditions match replay.** Replay uses recorder data with known gaps. Live microstructure may produce different overlay scores. (UNKNOWN)

5. **Whether the 369-trade sample is sufficient for robust inference.** The slow-reversion cohort (n=19) is small. 2/19 lost at CV 0.25 could be 0 or 4 under different market regimes. (UNKNOWN — high sensitivity to small-sample instability)

6. **Whether combining HQ and CV (multi-variate gating) could produce better separation.** Not tested. (UNKNOWN)

---

## 11. Promotion Reconsideration Assessment

### Setup Quality: NO reconsideration warranted

- **Cause**: No predictive power
- **Mechanism**: Weak negative correlation means SQ actively misleads
- **Risk avoided**: Filtering based on a non-signal
- **Evidence gap**: None — the evidence is conclusive that SQ does not predict outcomes

### Hold Quality: Reconsideration DEFERRED, further study warranted

- **Cause**: Strong signal but unacceptable slow-reversion cost at all thresholds
- **Mechanism**: HQ 0.25 filter removes 147 bad trades (4.6:1 ratio) but also kills 7 slow reversions
- **Risk avoided by deferral**: Destroying 37%+ of the most profitable trade cohort
- **Evidence gap**: Time-conditional gating not tested; per-symbol threshold not tested; live observation not done
- **Recommended further study**: Test a "late-hold HQ gate" (e.g., only apply HQ < 0.15 filter after bar 12) to see if slow reversions can be protected while still catching stale holds

### Context Validity: Reconsideration CONDITIONALLY OPEN at threshold 0.25 only

- **Cause**: Moderate signal with best-in-class slow-reversion preservation at 0.25
- **Mechanism**: CV 0.25 removes 95 trades (73 bad, 22 good), preserves 17/19 slow revs
- **Risk if promoted**: 2 slow reversions destroyed (10.5%); unknown live distribution behavior
- **Evidence gap**: Live/testnet observation; small-sample sensitivity (n=19); per-symbol asymmetry (XRPUSDT 0/11 lost, BNBUSDT 2/8 lost)
- **Minimum next step**: Live advisory monitoring of CV scores for ≥ 50 trades to confirm replay distributions match live, then re-evaluate

### Progress Deficit: NOT assessed for promotion (not a direct overlay)

- Strongest raw signal but structurally entangled with hold duration
- Could inform a future composite gate but not standalone

---

## 12. Final Verdict

```
+=========================================================+
|                                                         |
|  ONE OVERLAY QUALIFIES FOR FURTHER PROMOTION STUDY      |
|                                                         |
+=========================================================+
```

### Summary

| Overlay | Predictive Power | Slow-Rev Safe? | Qualifies for Further Study? |
|---------|-----------------|----------------|------------------------------|
| `setup_quality` | NONE (r = -0.09) | N/A | **NO** |
| `hold_quality` | STRONG (r = 0.46) | NO (37%+ destroyed) | **DEFERRED** — needs time-conditional study |
| `context_validity` | MODERATE (r = 0.41) | PARTIAL (10.5% lost at 0.25) | **YES** — at threshold 0.25 only |
| `progress_deficit` | STRONG (r = -0.62) | Not tested standalone | **NO** — structurally entangled |

### Formal Disposition

1. **`setup_quality`**: Disqualified from further promotion consideration. Evidence conclusively shows no predictive power. Remains advisory-only with no future gate pathway.

2. **`hold_quality`**: Strong signal confirmed but promotion remains blocked by slow-reversion safety failure. Deferred to a future package that tests time-conditional or per-symbol gating variants.

3. **`context_validity` at threshold 0.25**: This is the single candidate that merits continued investigation. It is the only overlay + threshold combination in the entire analysis that simultaneously shows meaningful PnL improvement (+0.294), preserves ≥ 89% of slow reversions (17/19), and maintains a reasonable bad-to-good removal ratio (3.3:1).

4. **However**: CV 0.25 is NOT promoted in this package. It qualifies for further study only — specifically, a live/testnet advisory observation period to confirm that replay-derived distributions hold under real conditions, followed by a formal promotion proposal with updated slow-reversion sensitivity data.

### Governance Status After D.1

| Package | Prior Status | Status After D.1 |
|---------|-------------|-------------------|
| C.1 | ACCEPTED_ADVISORY_ONLY | ACCEPTED_ADVISORY_ONLY (unchanged) |
| C.2 | ACCEPTED_ADVISORY_ONLY | ACCEPTED_ADVISORY_ONLY — **SQ promotion pathway closed** |
| C.3 | ACCEPTED_ADVISORY_ONLY | ACCEPTED_ADVISORY_ONLY — HQ promotion deferred pending time-conditional study |
| C.4 | ACCEPTED_ADVISORY_ONLY | ACCEPTED_ADVISORY_ONLY — **CV 0.25 qualifies for further study** |
| Baseline | A.1 | A.1 (unchanged) |

### Recommended Next Package: D.2

**D.2: Context Validity 0.25 Live Advisory Observation**

Scope:
- Enable CV score logging at INFO level in live/testnet for all md_amr trades
- Collect ≥ 50 live trades with CV scores
- Compare live CV distribution with replay CV distribution
- Re-assess slow-reversion behavior at threshold 0.25 on live data
- Produce promotion-readiness assessment

This package remains analysis-only. No hard behavioral changes until D.2 confirms replay-live parity.

---

*Report generated: 2026-04-16*
*Analysis tool: `tools/analysis/md_amr_d1_cohort_analysis.py`*
*Input data: `reports/md_amr_integrated_validation_trades.csv` (369 integrated trades)*
*Supporting artifacts: `reports/md_amr_overlay_cohort_analysis.csv`, `reports/md_amr_overlay_threshold_sweep.csv`, `reports/md_amr_overlay_by_symbol.csv`, `reports/md_amr_overlay_slow_reversion_protection.csv`*
