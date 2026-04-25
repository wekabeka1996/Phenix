# MD-AMR Package B.1 — Economic Validation Addendum
**Status:** `COMPLETE`
**Date:** 2026-04-10
**Type:** Analysis-only. No code changes. No YAML changes.

---

## 1. Why Package B Needed B.1

Package B's ablation showed a sharp mechanical improvement:
- Zombie dropped from 62.7% → 11.2%
- Scaleout rose from 37.3% → 88.8%
- Killswitch = 0.0% in all modes

But Package B correctly flagged that `avg_pnl/trade` decreases in COMBINED (from +0.143% to -0.074%), and acknowledged this as a methodological artefact of 3× more trades. This claim required verification.

The question B.1 answers:

> **Is COMBINED (or any single lever) economically better than BASELINE, or only mechanically better in exit-distribution statistics?**

The answer determines whether the YAML defaults should stay at `max_hold_bars=32, target_approach_pct=0.002` (current post-Package-B state) or roll back to `max_hold_bars=16, target_approach_pct=0.0` (Package A.1 baseline).

---

## 2. Methodology

### Replay parameters
- Same data: XRPUSDT (~4619 bars) + BNBUSDT (~2630 bars), 900s timeframe
- Same SSOT config (fee=4bps, slip=2bps, round-trip cost model)
- 4 modes identical to Package B ablation
- Per-trade data captured: entry_bar_idx, exit_bar_idx, holding_bars, pnl, symbol, side

### Metrics framework

Beyond `avg_pnl/trade`, the analysis adds:

| Category | Metrics |
|:---|:---|
| Time-normalized | pnl/bar-in-position, pnl/holding-hour, avg holding duration |
| Turnover-aware | trades/1000 bars, fee drag/1000 bars, net_pnl/1000 bars |
| Matched cohort | 9 cases where same entry opportunity plays out differently across modes |
| Capital efficiency | pnl_per_bar as proxy for capital-time utilization |

### Methodology limits (stated upfront)

- Replay has no intra-bar execution granularity — exit price = bar close
- Replay has no position sizing — all positions treated as unit size
- PARTIAL_CLOSE keeps position open (only FULL_CLOSE resets state). `exposure_pct` metrics may overcount exposure when multiple scaleouts occur before a full close
- Single dataset snapshot; one trading environment does not establish statistical significance
- Objective Engine interaction not captured

---

## 3. Normalized Metrics Table (All symbols, combined)

```
Metric                BASELINE    HOLDBARS   TOLERANCE    COMBINED
-----------------------------------------------------------------------
Trades (n)                 544         467        1659        1724
KS%                        0.0         0.0         0.0         0.0
SC%                       37.3        58.7        79.4        88.8
ZT%                       62.7        41.3        20.6        11.2
avg gross%/trade        +0.1431     -0.0176     +0.0609     -0.0742
avg net%/trade          +0.0631     -0.0976     -0.0191     -0.1542
avg hold (bars)            11.2        17.2         7.4        10.7
avg hold (hours)            2.8         4.3         1.8         2.7
pnl/bar-in-position    +0.0290%    +0.0191%    +0.0272%    +0.0100%
pnl/hour-in-position   +0.1159%    +0.0763%    +0.1090%    +0.0398%
trades/1k bars             74.9        64.4       228.6       237.7
fee drag%/1k bars         9.401       7.981      28.219      29.639
net pnl%/1k bars         +6.416      -0.177      -8.823     -42.364
```

**XRPUSDT alone:**
```
Metric                BASELINE    HOLDBARS   TOLERANCE    COMBINED
-----------------------------------------------------------------------
Trades (n)                 383         346        1021        1061
avg gross%/trade        +0.1566     +0.0497     +0.0765     -0.0599
pnl/bar-in-position    +0.0301%    +0.0239%    +0.0300%    +0.0111%
net pnl%/1k bars         +8.706      +1.893      -1.399     -41.154
```

**BNBUSDT alone:**
```
Metric                BASELINE    HOLDBARS   TOLERANCE    COMBINED
-----------------------------------------------------------------------
Trades (n)                 161         121         638         663
avg gross%/trade        +0.1107     -0.2102     +0.0361     -0.0970
pnl/bar-in-position    +0.0266%    -0.0011%    +0.0237%    +0.0085%
net pnl%/1k bars         +2.736      -3.649     -18.975     -44.650
```

---

## 4. Matched-Cohort Casebook

9 cases where the same entry opportunity appears in multiple modes.
All timestamps are bar close times.

---

**Case 01: XRPUSDT LONG | entry_bar=95 | 2026-02-10 05:59**

| Mode | Exit | Hold(bars) | Gross% | Net% |
|:---|:---|:---:|:---:|:---:|
| BASELINE | FEE_AWARE_SCALEOUT | 3 | +0.6972 | +0.6172 |
| HOLDBARS | FEE_AWARE_SCALEOUT | 3 | +0.6972 | +0.6172 |
| TOLERANCE | FEE_AWARE_SCALEOUT | 3 | +0.6972 | +0.6172 |
| COMBINED | FEE_AWARE_SCALEOUT | 3 | +0.6972 | +0.6172 |

**Interpretation:** Fast clean mean-reversion. All modes identical. Tolerance adds no friction here.

---

**Case 02: XRPUSDT LONG | entry_bar=121 | 2026-02-10 12:44**

| Mode | Exit | Hold(bars) | Gross% | Net% |
|:---|:---|:---:|:---:|:---:|
| BASELINE | ZOMBIE_POSITION_TIMEOUT | 17 | -1.0377 | -1.1177 |
| HOLDBARS | (not in this mode) | — | — | — |
| TOLERANCE | FEE_AWARE_SCALEOUT | 11 | -0.5859 | -0.6659 |
| COMBINED | (not in this mode) | — | — | — |

**Interpretation:** TOLERANCE exits earlier (-0.59% vs -1.04%). Better but still a loss. HOLDBARS extended the hold beyond 16 bars and this entry disappeared from that mode's cohort. This means HOLDBARS re-combined the subsequent entry with a different bar — not a "miss" but a different trajectory.

---

**Case 03: XRPUSDT SHORT | entry_bar=148 | 2026-02-10 19:29**

| Mode | Exit | Hold(bars) | Gross% | Net% |
|:---|:---|:---:|:---:|:---:|
| BASELINE | ZOMBIE_POSITION_TIMEOUT | 17 | +1.9212 | +1.8413 |
| HOLDBARS | (not in this mode) | — | — | — |
| TOLERANCE | FEE_AWARE_SCALEOUT | 3 | +0.3448 | +0.2648 |
| COMBINED | (not in this mode) | — | — | — |

**Interpretation:** Critical case. **BASELINE held 17 bars and collected +1.92% gross.** TOLERANCE exited at bar 3 for only +0.34% gross — 5.6× less. The position was profitable and TOLERANCE left significant gain on the table. This is a direct cost of the tolerance mechanism: early scaleout captures a small gain while the full mean-reversion would have yielded much more.

---

**Case 04: XRPUSDT SHORT | entry_bar=176 | 2026-02-11 02:29**

| Mode | Exit | Hold(bars) | Gross% | Net% |
|:---|:---|:---:|:---:|:---:|
| BASELINE | FEE_AWARE_SCALEOUT | 16 | +2.8772 | +2.7972 |
| HOLDBARS | FEE_AWARE_SCALEOUT | 16 | +2.8772 | +2.7972 |
| TOLERANCE | FEE_AWARE_SCALEOUT | 14 | +2.4356 | +2.3556 |
| COMBINED | FEE_AWARE_SCALEOUT | 14 | +2.4356 | +2.3556 |

**Interpretation:** TOLERANCE exits 2 bars earlier for 0.44% less gross. Same type of "early money-left" dynamic as Case 03.

---

**Case 05: BNBUSDT LONG | entry_bar=99 | 2026-03-07 16:14**

| Mode | Exit | Hold(bars) | Gross% | Net% |
|:---|:---|:---:|:---:|:---:|
| BASELINE | ZOMBIE_POSITION_TIMEOUT | 17 | -0.6281 | -0.7081 |
| HOLDBARS | ZOMBIE_POSITION_TIMEOUT | 33 | -1.1633 | -1.2433 |
| TOLERANCE | FEE_AWARE_SCALEOUT | 7 | +0.1506 | +0.0706 |
| COMBINED | FEE_AWARE_SCALEOUT | 7 | +0.1506 | +0.0706 |

**Interpretation:** Best-case rescue. BASELINE holds 17 bars and loses 0.63%. HOLDBARS holds 33 bars and loses 1.16% — worse. TOLERANCE and COMBINED exit at bar 7 for +0.15% gross. **COMBINED rescued a zombie into a profitable exit.** This is what Package B was designed for.

---

**Case 06: BNBUSDT LONG | entry_bar=126 | 2026-03-08 04:29**

| Mode | Exit | Hold(bars) | Gross% | Net% |
|:---|:---|:---:|:---:|:---:|
| BASELINE | ZOMBIE_POSITION_TIMEOUT | 17 | +0.1294 | +0.0494 |
| HOLDBARS | (not in this mode) | — | — | — |
| TOLERANCE | FEE_AWARE_SCALEOUT | 1 | +0.2330 | +0.1530 |
| COMBINED | (not in this mode) | — | — | — |

**Interpretation:** TOLERANCE exits in 1 bar for slightly better net. Borderline — both outcomes are small gains.

---

**Case 07: BNBUSDT SHORT | entry_bar=144 | 2026-03-08 08:59**

| Mode | Exit | Hold(bars) | Gross% | Net% |
|:---|:---|:---:|:---:|:---:|
| BASELINE | ZOMBIE_POSITION_TIMEOUT | 17 | +0.4879 | +0.4079 |
| HOLDBARS | (not in this mode) | — | — | — |
| TOLERANCE | FEE_AWARE_SCALEOUT | 4 | -0.1551 | -0.2351 |
| COMBINED | (not in this mode) | — | — | — |

**Interpretation:** Adverse case. BASELINE zombie ends at +0.49% (still profitable). TOLERANCE exits early at -0.16% gross. Tolerance triggered in a position that was heading toward a positive outcome.

---

**Case 08: BNBUSDT LONG | entry_bar=164 | 2026-03-08 18:44**

| Mode | Exit | Hold(bars) | Gross% | Net% |
|:---|:---|:---:|:---:|:---:|
| BASELINE | ZOMBIE_POSITION_TIMEOUT | 17 | +0.6816 | +0.6016 |
| HOLDBARS | (not in this mode) | — | — | — |
| TOLERANCE | FEE_AWARE_SCALEOUT | 7 | -0.0033 | -0.0833 |
| COMBINED | (not in this mode) | — | — | — |

**Interpretation:** Another adverse case. BASELINE zombie = +0.68%. TOLERANCE exits at -0.003%. The position was mid-reversion and TOLERANCE cut it near breakeven while baseline held to full capture.

---

**Case 09: XRPUSDT SHORT | entry_bar=4412 | 2026-04-08 07:29**

| Mode | Exit | Hold(bars) | Gross% | Net% |
|:---|:---|:---:|:---:|:---:|
| BASELINE | FEE_AWARE_SCALEOUT | 10 | -0.2835 | -0.3635 |
| HOLDBARS | FEE_AWARE_SCALEOUT | 10 | -0.2835 | -0.3635 |
| TOLERANCE | FEE_AWARE_SCALEOUT | 9 | -0.3489 | -0.4289 |
| COMBINED | FEE_AWARE_SCALEOUT | 9 | -0.3489 | -0.4289 |

**Interpretation:** All modes scaleout. Tolerance exits 1 bar earlier for marginally worse result. Noise-level difference.

---

### Rescue Summary

- **43 unique entries** where BASELINE=ZOMBIE → COMBINED=SCALEOUT
- Average gross for these "rescued" exits via COMBINED: **-0.195%**
- Average gross for the same entries in BASELINE (zombie): **+0.010%**

> **The majority of zombie rescues in COMBINED are economically worse than the baseline zombie outcomes.** COMBINED converts 43 ZOMBIE exits into FEE_AWARE_SCALEOUT exits, but those exits leave the market with a **-0.195% avg gross** while the zombie they replaced had **+0.010% avg gross**.

This does not mean Package A was wrong — zombie exits with any PnL are not indicative of a healthy strategy. The issue is that `target_approach_pct=0.002` is triggering scaleout in the early part of the mean-reversion move (before full price recovery), converting a slow-profitable position into a fast mediocre one.

---

## 5. Turnover and Capital-Time Interpretation

### Fee Drag

| Mode | Fee drag%/1k bars |
|:---|:---:|
| BASELINE | 9.40% |
| HOLDBARS | 7.98% |
| TOLERANCE | 28.22% |
| COMBINED | 29.64% |

TOLERANCE/COMBINED produce **3× the fee drag** per 1000 bars. This is consistent with trade count increase (~3×), so there is no disproportionate cost per trade — the cost is proportional to the number of trades, not worse per trade. However, the total drag on the strategy's net PnL is materially higher.

### pnl/bar-in-position (Capital Efficiency)

This is the most honest time-normalized metric: gross pnl per bar the strategy was holding a position.

| Mode | pnl/bar |
|:---|:---:|
| BASELINE | +0.02897% |
| HOLDBARS | +0.01914% |
| TOLERANCE | +0.02723% |
| COMBINED | +0.00996% |

- **TOLERANCE** preserves capital efficiency (0.027% ≈ 0.029% — within 6% of BASELINE)
- **HOLDBARS** alone drops to 0.019% (-34% vs BASELINE) — holding longer dilutes returns
- **COMBINED** drops to 0.010% (-66% vs BASELINE) — compounding of both effects

### net_pnl/1k-bars (Strategy Production Rate)

| Mode | net pnl%/1k bars |
|:---|:---:|
| BASELINE | +6.42% |
| HOLDBARS | -0.18% |
| TOLERANCE | -8.82% |
| COMBINED | -42.36% |

All non-baseline modes are **negative net per 1000 bars** in this dataset. This is the most alarming finding and the key driver of the deployment verdict.

### Why COMBINED has negative net/bar

1. **Higher trade count × cost-per-trade = high fee drag** (29.64%/1k bars)
2. **Early exits via tolerance capture incomplete mean-reversion** (cases 03, 07, 08)
3. **HOLDBARS extends poor positions past their organic timeout** (case 05 HOLDBARS variant was worse)
4. **Tolerance triggers on approach zone even when the full reversion was pending**

The net effect: TOLERANCE converts many zombie exits (which had variable but sometimes positive PnL) into low-quality scaleouts (which exit at the first touch of the target zone, not the full target).

---

## 6. Is Package B Mechanically Better or Economically Better?

### Direct answer

**COMBINED is mechanically better, not economically better — in this dataset.**

| Claim | Evidence |
|:---|:---|
| Zombie distribution improved | TRUE — ZT 62.7% → 11.2% |
| Scaleout distribution improved | TRUE — SC 37.3% → 88.8% |
| Capital efficiency preserved | FALSE — pnl/bar drops from 0.029% to 0.010% (-66%) |
| Total strategy production improved | FALSE — net pnl/1k bars: +6.42% → -42.36% |
| Rescue of genuinely losing zombies | PARTIALLY — 43 rescues, but avg rescued gross (-0.195%) < avg zombie gross (+0.010%) |

**TOLERANCE-only verdict:** Closer to economically neutral. pnl_per_bar = 0.027% (vs 0.029% baseline — within 6%). However, net_pnl/1k bars becomes negative (-8.82%) due to fee drag from 3× more trades.

**HOLDBARS-only verdict:** Decreases trade count but net_pnl/1k bars goes to -0.18% (near zero). HOLDBARS alone does not save BNB positions (BNB HOLDBARS: -0.21% gross/trade).

### The precise failure mode of COMBINED

> The tolerance zone fires at `avg_close * (1.0 - 0.002)` — within 0.2% of the target. When a mean-reversion move is slow (taking 10–17 bars), the price passes through the 0.2% zone on its way to full recovery. TOLERANCE captures that 0.2% early and exits. If the price had continued to full target, it would have captured the remaining reversion.

> In Case 03: baseline held 17 bars for +1.92%. TOLERANCE exited at bar 3 for +0.34%. The tolerance zone was hit at bar 3 but the full move delivered 5.6× more over the next 14 bars.

This is not a fatal flaw — in an adverse environment, the early exit at +0.34% is better than holding to a reversal. But in this dataset's environment, the extended moves completed profitably in baseline. Tolerance "over-monetizes" the early phase at the cost of the later phase.

---

## 7. Deployment Decision

### Options

| Option | Economic Evidence | Risk |
|:---|:---|:---|
| Accept COMBINED as default | **REJECTED** — net/1k bars negative, capital efficiency -66% | High |
| Accept TOLERANCE-only only | **CONDITIONAL** — pnl/bar acceptable, but net/1k negative | Medium |
| Accept HOLDBARS-only only | **REJECTED** — negative on BNB, marginal on XRP | High |
| Revert to Package A.1 baseline | **Neutral** — keeps positive net/1k bars | Low |
| Retain code, revert YAML defaults | **RECOMMENDED** — code stays, metrics observed in live | Lowest |

### Recommended Decision

> **RETAIN Package B code support. REVERT YAML defaults to Package A.1 state:**
> - `max_hold_bars: 16` (from 32)
> - `target_approach_pct: 0.0` (strict equality, baseline behavior)
>
> **Exception:** If per-symbol live data shows BNB zombie rate consistently > 70% over 30+ days, a conditional TOLERANCE-only increase to `target_approach_pct: 0.001` (half the current value) can be considered in Package C with a proper live-data economic test.

### Rationale

1. A single-day replay dataset is insufficient to override positive `net_pnl/1k-bars` with a mode that shows **-42%/1k bars**
2. The matched-cohort shows that many "rescued" positions were in profitable mean-reversions that TOLERANCE cut early
3. `pnl_per_bar` is a better metric than `avg_pnl_per_trade` but 0.010% (COMBINED) vs 0.029% (BASELINE) is a -66% drop with no compensating volume benefit
4. The Package B lever that is safe is `target_approach_pct=0.0` (no change to the tolerance condition) — the code path exists, the YAML default = 0.0 is safe
5. `max_hold_bars=16` is aggressive but creates clean zombie exits rather than the ambiguous early-exit problem

---

## 8. What Remains Uncertain

| Uncertainty | Impact |
|:---|:---|
| Dataset is 1.5 months; longer window needed | HIGH — mean-reversion edge varies with market regime |
| Intra-bar execution not modeled | MEDIUM — partial close fills may differ at tolerance zone vs exact target |
| Optimal `target_approach_pct` value | MEDIUM — 0.002 may be too wide; 0.0005 might preserve more upside |
| Per-symbol YAML overrides not implemented | LOW — BNB and XRP may benefit from different defaults |
| Interaction with Objective Engine | LOW — score multiplier could attenuate some early exits |

---

## 9. Final Verdict

**Package B is mechanically correct but economically premature at current parameter values.**

Evidence level:

- Exit distribution improvement: **CONFIRMED**
- Zombie root cause correctly identified: **CONFIRMED**
- `target_approach_pct=0.002` economically sound: **NOT CONFIRMED** (negative net/1k-bars)
- `max_hold_bars=32` alone economically sound: **NOT CONFIRMED** (negative on BNB)
- COMBINED as default: **REJECTED BY ECONOMIC NORMALIZATION**

**The Package B code changes are correct and should be merged.** The YAML defaults should revert to Package A.1 state until live economic data supports the tolerance parameters. The ablation machinery exists in `scratch/pkg_b_ablation.py` and `scratch/pkg_b1_economic_validation.py` to re-run with live data.

---

## Self-Check

| Check | Result |
|:---|:---|
| Did not turn this into a redesign? | YES — analysis only, no code changes |
| Went beyond avg_pnl/trade? | YES — pnl/bar, pnl/hour, net/1k-bars |
| Accounted for holding duration and exposure? | YES |
| Checked turnover effect? | YES — fee drag/1k bars |
| Did matched-cohort comparison (not just aggregate)? | YES — 9 cases |
| Concrete deployment verdict? | YES — revert YAML defaults |
| Honestly separated mechanically vs economically better? | YES — mechanically better, economically NOT supported |
