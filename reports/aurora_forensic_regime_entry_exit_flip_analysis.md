# Aurora Forensic Analysis — Regime / Entry / Exit / Flip / Toxicity
**Baseline:** B3 (patched3) | **Data:** R3_CUM, R3_AUG, R4_CUM, R4_SEP (closed)
**Date:** 2026-03-07 | **Analyst:** Principal Trading Forensics

---

## SECTION 0 — Executive Verdict

**Dominant loss mechanism: unfavorable SL/TP payoff ratio with regime-label mismatch.**

Aurora generates roughly equal numbers of SL and TP exits (160 SL vs 164 TP in R4_CUM). The problem is **asymmetry**: SL avg loss = −16.42 USDT, TP avg win = +11.49 USDT → payoff ratio 0.70. At 50/50 SL/TP split you need payoff > 1.0 to break even. This is the structural core of all losses, not signal quality or regime direction.

**Top 3 actionable findings:**

1. **BTC is the primary capital destroyer.** BTC HIGH_VOLATILITY has an 86% SL rate (36 SL vs 6 TP) with −103 USDT total loss. BTC LOW_VOLATILITY has 65% SL rate and −159 USDT loss. In September, BTC is negative in ALL regimes. BTC should be ATTENUATED or its TP/SL ratio inverted for HIGH_VOL.

2. **1000PEPEUSDT is a dual hazard: both a strategy-level toxicity AND a simulation artifact.** In Sep-only there were 155 aurora trades with ev/t = −4.27 USDT and payoff avg = 0.22. PEPE traded in TREND_UP (n=75, ev=−6.03) and TREND_DOWN (n=56, ev=−2.23) — regimes it arguably should not enter. Additionally, a compounding position sizing bug produced a 2.1B-unit unrealized position that inflated Sep metrics by +9027 USDT, invalidating the Sep-only `total_pnl` metric entirely.

3. **ETH TREND_DOWN is the only structurally profitable regime across all windows** (ev=+5.16, n=25, R4_CUM). ETH should be protected from config restrictions or over-tightening. All other ETH regimes are negative or have low sample confidence.

**Before any new patch:** run September-only WITHOUT 1000PEPEUSDT in aurora, to isolate the real September BTC/ETH/BNB performance from the PEPE contamination.

---

## SECTION 1 — Artifact Inventory and Validity

### 1.1 Runs analyzed

| Run ID | Period | File | Closed Trades | Open at End | Validity |
|---|---|---|---|---|---|
| R3_CUM | 2023-06-01..2023-08-31 | `backtest_20260305_045933.json` | 251 | 0 | ✅ VALID |
| R3_AUG | 2023-08-01..2023-08-31 | `backtest_20260306_004729.json` | 72 | 1 (negligible) | ✅ VALID (metrics usable) |
| R4_CUM | 2023-06-01..2023-09-30 | `backtest_20260306_100245.json` | 324 | 1 (BNB, −0.53 USDT) | ✅ VALID (open ~0) |
| R4_SEP | 2023-09-01..2023-09-30 | `backtest_20260307_032221.json` | 218 | 1 (PEPE, +9027 unrealized) | ⚠️ **METRICS INVALID** — closed trades usable |

### 1.2 R4_SEP Contamination Details

- `metrics.total_pnl = 7676.51 USDT` — **DO NOT USE.** Includes unrealized PnL from open 1000PEPEUSDT LONG.
- Open position: 1000PEPEUSDT, entry 2023-09-27 08:55, qty = **2,172,057,984 units** — simulation artifact.
- `fees_usdt = 635.80` on a `entry_value_usdt = 625.57` position — fees > notional, physically impossible. Root cause: mock broker accumulated fills without hard position-size cap, compounding leverage on growing balance.
- **Real closed-trade PnL for R4_SEP = −714.42 USDT.** Use this number only.

### 1.3 Primary analysis dataset

**R4_CUM (Jun-Sep, 324 closed trades)** is the primary dataset — largest valid sample. R3_CUM (Jun-Aug, 251 trades) is used for isolation. R4_SEP closed trades (218) are used for September-specific watchlist analysis.

### 1.4 Missing fields preventing MFE/MAE analysis

The trade records contain: `entry.ts_ms`, `entry.price`, `exit.ts_ms`, `exit.price`, `pnl_usdt_net`, `close_reason`. **The following fields are absent:**
- `mfe_usdt` / `mfe_pct` (maximum favorable excursion)
- `mae_usdt` / `mae_pct` (maximum adverse excursion)
- `peak_unrealized_pnl` during trade lifetime
- `bar_path` or OHLC data joined to trade

Without these, entry/exit quality analysis in Sections 3–5 is limited to holding time, exit reason distribution, and directional inference. Adding per-trade MFE/MAE logging is the single most valuable instrumentation addition for the next run.

---

## SECTION 2 — Regime Quality Audit

### 2.1 R4_CUM — Symbol × Regime (ranked by EV/trade, Jun-Sep, n=324)

| Sym | Regime | n | Total USDT | EV/t | WR% | avg_win | avg_loss | Payoff | Conf | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| BTC | MEAN_REVERSION | 1 | −10.08 | −10.08 | 0% | 0.00 | −10.08 | 0.00 | L | **BLOCK** |
| ETH | MEAN_REVERSION | 4 | −39.26 | −9.81 | 50% | +8.57 | −28.20 | 0.30 | L | **BLOCK** |
| BTC | LOW_VOLATILITY | 54 | −159.43 | −2.95 | 35% | +7.80 | −8.79 | 0.89 | H | **ATTENUATE** |
| ETH | LOW_VOLATILITY | 28 | −73.49 | −2.62 | 75% | +12.38 | −47.63 | 0.26 | M | **ATTENUATE** |
| BTC | HIGH_VOLATILITY | 42 | −103.49 | −2.46 | 19% | +25.08 | −8.95 | 2.80 | H | **ATTENUATE** ¹ |
| BTC | TREND_UP | 26 | −27.24 | −1.05 | 38% | +17.97 | −12.93 | 1.39 | M | **MONITOR** |
| BNB | MEAN_REVERSION | 45 | −28.86 | −0.64 | 78% | +3.80 | −16.19 | 0.23 | H | **ATTENUATE** |
| BNB | LOW_VOLATILITY | 74 | −37.39 | −0.51 | 68% | +6.54 | −15.18 | 0.43 | H | **MONITOR** |
| BTC | TREND_DOWN | 25 | +87.59 | +3.50 | 28% | +49.84 | −14.52 | 3.43 | M | **KEEP** |
| ETH | TREND_DOWN | 25 | +128.99 | +5.16 | 68% | +34.29 | −56.73 | 0.60 | M | **KEEP** ² |

¹ BTC HIGH_VOL: payoff = 2.80 but WR = 19%. You win big rarely. At 14.3% TP rate the expected value is still −2.46. Sizing must be drastically reduced.

² ETH TREND_DOWN: payoff = 0.60 but WR = 68% → positive EV (+5.16). This is the strategy's best regime. However avg_loss = −56.73 is very high, implying single SL events eat 1.6 TP wins. Needs wide stop protection.

### 2.2 R4_SEP closed — Symbol × Regime (September only, n=218)

| Sym | Regime | n | Total | EV/t | WR% | Payoff | Conf | Verdict |
|---|---|---|---|---|---|---|---|---|
| PEPE | MEAN_REVERSION | 9 | −57.95 | −6.44 | 78% | 0.05 | L | **BLOCK + investigate** |
| PEPE | TREND_UP | 75 | −452.23 | −6.03 | 61% | 0.28 | H | **BLOCK** |
| ETH | MEAN_REVERSION | 4 | −16.75 | −4.19 | 50% | 0.31 | L | block / L conf |
| BTC | MEAN_REVERSION | 1 | −3.41 | −3.41 | 0% | 0.00 | L | — |
| PEPE | TREND_DOWN | 56 | −125.11 | −2.23 | 55% | 0.35 | H | **BLOCK** |
| BTC | LOW_VOLATILITY | 9 | −18.66 | −2.07 | 11% | 0.66 | L | ATTENUATE |
| BTC | TREND_UP | 8 | −14.38 | −1.80 | 13% | 1.36 | L | MONITOR |
| PEPE | LOW_VOLATILITY | 15 | −26.77 | −1.78 | 53% | 0.35 | M | BLOCK |
| BTC | HIGH_VOLATILITY | 10 | −17.52 | −1.75 | 10% | 2.03 | M | ATTENUATE |
| BNB | MEAN_REVERSION | 14 | −14.50 | −1.04 | 79% | 0.09 | M | MONITOR |
| BNB | LOW_VOLATILITY | 7 | +8.05 | +1.15 | 86% | 0.56 | L | KEEP |
| ETH | LOW_VOLATILITY | 5 | +11.00 | +2.20 | 100% | inf | L | KEEP (conf low) |
| ETH | TREND_DOWN | 3 | +13.45 | +4.48 | 100% | inf | L | KEEP (conf low) |

### 2.3 Cross-window PnL per symbol (closed trades only)

| Window | Total | BTC | ETH | BNB | PEPE |
|---|---|---|---|---|---|
| R3_CUM (Jun-Aug) | −90.36 | −53.22 | +26.12 | −63.26 | — |
| R4_CUM (Jun-Sep) | −262.64 | −212.64 | +16.24 | −66.24 | — |
| R4_SEP closed | −714.42 | −53.61 | +7.70 | −6.45 | −662.07 |

**Incremental September contribution to R4_CUM** (R4 minus R3):
- BTC: −212.64 − (−53.22) = **−159.42 USDT** — September catastrophic for BTC
- ETH: +16.24 − (+26.12) = **−9.88 USDT** — slight regression
- BNB: −66.24 − (−63.26) = **−2.98 USDT** — flat
- PEPE: 0 in CUM (not traded), but 155 trades in Sep-only standalone

---

## SECTION 3 — Entry Quality Analysis

### 3.1 Available data and limitations

**Fields available for entry analysis:** `entry.ts_ms`, `entry.price`, `entry.side`, `close_reason`, `pnl_usdt_net`, `market_regime` (at entry time), `holding_time` (derived).

**Fields ABSENT:** MFE, MAE, bar path after entry. Entry quality is estimated via holding times and SL/TP outcome patterns.

### 3.2 Holding time by symbol × regime (R4_CUM)

| Sym | Regime | n | Avg hold | Median hold |
|---|---|---|---|---|
| BNB | LOW_VOLATILITY | 74 | 208 min | 45 min |
| BNB | MEAN_REVERSION | 45 | 392 min | 195 min |
| BTC | TREND_UP | 26 | 186 min | 125 min |
| BTC | LOW_VOLATILITY | 54 | 528 min | 330 min |
| ETH | LOW_VOLATILITY | 28 | 499 min | 325 min |
| BTC | MEAN_REVERSION | 1 | 25 min | 25 min |
| ETH | MEAN_REVERSION | 4 | 838 min | 935 min |
| BTC | HIGH_VOLATILITY | 42 | 822 min | 435 min |
| ETH | TREND_DOWN | 25 | 804 min | 450 min |
| BTC | TREND_DOWN | 25 | 846 min | 75 min |

### 3.3 Findings on entry quality

**BTC HIGH_VOLATILITY — late entries almost certain.**
WR = 19%, avg hold = 822 min, SL_n/TP_n = 36/6. In a HIGH_VOLATILITY regime, a trade that takes 13.7 hours on average to resolve is not catching the volatility move — it's entering mid-chop and waiting for resolution. 86% SL rate suggests entries are consistently opening against the short-term momentum.

**BTC TREND_DOWN is the counter-intuitive anomaly.**
Avg hold = 846 min, median hold = 75 min. The bimodal distribution (median 75m vs avg 846m) means: most trades exit quickly (likely TP), while a tail of trades hold 14+ hours. The few TP winners (+49.84 avg) are large-payoff outliers, not systematic winners. With WR = 28%, this regime survives on fat-tail wins.

**BNB LOW_VOLATILITY entries are fast and mediocre.**
Avg hold = 208 min, median 45 min → most trades are entering and exiting fast (68% TP rate). Yet net = −37 USDT because avg_SL = −6.62 while avg_TP = +2.43. The entry captures a move, takes a small TP, then a large SL wipes multiple TPs.

**ETH LOW_VOLATILITY showing SL gap problem.**
avg_SL = −29.46 vs avg_TP = +8.11 → payoff 0.27. Even with 71% TP rate, the SL is 3.6× wider than TP. This means SL levels are miscalibrated for LOW_VOL: stops are designed for higher volatility than the regime actually exhibits.

**Implication:** Entries in most regimes are not the primary problem for BTC/BNB. The entry size, stop sizing, and TP/SL ratio are. Entries appear to find correct direction part of the time (TP win rates 28–78%) but the payoff structure destroys the edge.

---

## SECTION 4 — Exit Quality Analysis

### 4.1 Overall exit distribution (R4_CUM, n=324)

| Exit Reason | n | Total USDT | EV/trade | WR% | avg_win | avg_loss |
|---|---|---|---|---|---|---|
| **SL** | 160 | **−2,064.62** | −12.90 | 6.9% | +34.72 | −16.42 |
| **TP** | 164 | **+1,801.97** | +10.99 | 96.3% | +11.49 | −2.23 |
| Net | 324 | **−262.65** | — | — | — | — |

**Overall SL/TP payoff: 0.70.** Breakeven requires payoff > 1.0 at 50/50 TP/SL split.

### 4.2 SL/TP distribution per symbol × regime (R4_CUM)

| Sym | Regime | SL_n | SL_avg | TP_n | TP_avg | TP% | Net |
|---|---|---|---|---|---|---|---|
| BTC | HIGH_VOLATILITY | 36 | −7.92 | 6 | +30.27 | **14%** | −103.49 |
| BTC | LOW_VOLATILITY | 35 | −8.79 | 19 | +7.80 | **35%** | −159.43 |
| BTC | TREND_UP | 16 | −12.93 | 10 | +17.97 | 38% | −27.24 |
| BTC | TREND_DOWN | 18 | −14.52 | 7 | +49.84 | 28% | +87.59 |
| BNB | LOW_VOLATILITY | 24 | −6.62 | 50 | +2.43 | 68% | −37.39 |
| BNB | MEAN_REVERSION | 11 | −14.66 | 34 | +3.89 | 76% | −28.86 |
| ETH | LOW_VOLATILITY | 8 | −29.46 | 20 | +8.11 | 71% | −73.49 |
| ETH | MEAN_REVERSION | 2 | −28.20 | 2 | +8.57 | 50% | −39.26 |
| ETH | TREND_DOWN | 9 | −42.38 | 16 | +31.90 | 64% | +128.99 |

### 4.3 Exit quality findings

**BTC HIGH_VOLATILITY: exits are the right mechanism, wrong calibration.**
When TP hits (+30.27 avg), it's a meaningful win. But 86% SL rate means the stop is getting triggered before price reaches TP. Either: (a) stop is too tight for the volatility in this regime, or (b) the entry direction is wrong 86% of the time. Given HIGH_VOL regime detection is itself noisy (volatile price action → noisy SMA signals), both are likely simultaneously true.

**BNB MR: high TP rate (76%) with small TP, large SL — structural payoff inversion.**
78% of BNB MR trades hit TP for +3.89. But the 24% SL hits average −14.66 each. You need payoff ≥ 0.24/(1−0.24) × (|SL_avg|/TP_avg) ≈ 3.77 TP wins to cover 1 SL loss. Currently generating 3.4 TPs per SL (34/11 = 3.1). This combination is inherently breakeven-negative. **Root cause: TP is too small relative to SL for MR regime.**

**ETH TREND_DOWN: biggest exits are catastrophic losers, but winners dominate count.**
avg_SL = −42.38 (n=9), avg_TP = +31.90 (n=16). Payoff = 0.75 with 64% TP rate → EV = 0.64×31.90 + 0.36×(−42.38) = +20.42 − 15.26 = +5.16. This matches the observed ev. The large avg_SL is concerning — single SL hits on ETH TREND_DOWN can be −50 to −100+ USDT (very wide stops for trend trades). These must be monitored closely as sample size grows.

**SL holding time = 571 min avg (> TP at 415 min).**
Stops are exiting trades that have been held for a long time and are still losing. This pattern is inconsistent with a sharp adverse move at entry — it suggests the trade opens, drifts slightly adverse or sideways for many hours, then finally hits SL. This is **churn cost**: paying maker fees on entry, then taker fees on SL exit, with a long period of potential regime change between.

---

## SECTION 5 — Flip Logic Forensics

### 5.1 Finding: No flip exits observed

In R4_CUM (324 trades) and all analyzed runs, `close_reason` contains only `SL` and `TP`. **No trades were exited via flip logic.** This means one of:

1. `signal_exit_enabled: true` with `signal_reversal_threshold: -0.10` is **not triggering** — signals are not reaching −0.10 frequently enough in the active trading contexts.
2. Flip logic operates by **adjusting TP/SL levels** (tightening stop via `danger_zone_action: TIGHTEN_STOPS`) rather than issuing a direct close order. The tightened stop subsequently fires as an SL, which gets logged as `close_reason: SL` — making flip-driven exits invisible in current logs.

### 5.2 Implication for exit analysis

If flip tightens stops (via `danger_zone_tighten_factor: 0.5`), it would show as faster SL exits. The 6.9% SL win rate and wide SL avg loss (−16.42) do not suggest stop tightening is destroying value — if anything, tightened stops would reduce SL losses. The dominant pattern (large SL losses) is consistent with normal SL being hit, not flip-tightened stops.

### 5.3 Missing data for counterfactual flip analysis

To assess flip impact counterfactually, we need:
- A flag in trade records: `was_flip_affected: bool`
- `stop_price_at_entry` vs `stop_price_at_exit` to detect tightening
- `signal_score_at_exit` to see if flip threshold was reached

**Recommendation:** add `flip_triggered: bool` and `stop_modified_by_flip: bool` to trade output. Without this, flip forensics cannot be completed.

---

## SECTION 6 — Regime Noise / Churn Audit

### 6.1 Regime churn statistics (from regime_log, last ~3.5 days of R4_CUM)

| Symbol | Events (sample) | Switches | SW/day | Med run | Avg run |
|---|---|---|---|---|---|
| 1000PEPEUSDT | 1000 | 58 | **16.7** | 12 bars (60m) | 17 bars |
| BNBUSDT | 1000 | 44 | **12.7** | 13 bars (65m) | 22 bars |
| BTCUSDT | 1000 | 51 | **14.7** | 10 bars (50m) | 19 bars |
| DOGEUSDT | 1000 | 47 | **13.5** | 17 bars (85m) | 21 bars |
| ETHUSDT | 1000 | 45 | **13.0** | 15 bars (75m) | 22 bars |

Note: `regime_log` is truncated at 5000 entries (1000 per symbol), sampling the last ~3.5 days of R4_CUM. Results reflect September 2023 behavior only.

### 6.2 Regime churn vs trade holding time

| Context | Med regime run | Med trade hold | Ratio |
|---|---|---|---|
| BNB LOW_VOL | 65 min | 45 min | 0.7× (trade exits before next switch) |
| BTC TREND_UP | 50 min | 125 min | 2.5× (2–3 regime changes during trade) |
| BTC LOW_VOL | 50 min | 330 min | **6.6× regime changes during trade** |
| BTC HIGH_VOL | 50 min | 435 min | **8.7× regime changes during trade** |
| ETH TREND_DOWN | 75 min | 450 min | **6× regime changes during trade** |

### 6.3 Findings on regime churn

**The `market_regime` field in trade records reflects the regime at entry time only.** By the time a BTC HIGH_VOL or BTC LOW_VOL trade exits (median 435–330 min), the regime has switched 5–9 times. The trade labeled TREND_UP at entry may currently be sitting in an UNCERTAIN or MEAN_REVERSION regime.

**This has two major implications:**
1. **TP/SL levels calibrated for the entry regime may be wrong** by exit time. A BTC TREND_UP entry (expecting momentum) is sitting in a different regime structure for most of its life.
2. **SL tightening via flip/danger_zone fires based on current-regime signal**, but the trade was entered under different regime assumptions. Regime churn generates false flip signals.

**Regime label distribution (Sep 2023 sample):**
- BNB: 49.5% MEAN_REVERSION, 18% LOW_VOLATILITY, 16.4% UNCERTAIN, 11% TREND_UP
- BTC: 43.2% MEAN_REVERSION, 26.9% LOW_VOLATILITY, 15.6% UNCERTAIN — combined 86% in flat/uncertain
- ETH: 26.1% MR, 25.8% TREND_UP, 23.9% LOW_VOL, 22% UNCERTAIN — near-uniform distribution
- PEPE: 39.1% UNCERTAIN, 24.5% TREND_UP, 17.2% LOW_VOL

**BTC spends 86% of time in MEAN_REVERSION + LOW_VOLATILITY + UNCERTAIN.** Aurora's BTC entries in these regimes are structurally negative. The small % of time BTC is in TREND_DOWN is the profitable window, but regime churn means the system cannot reliably stay in a TREND_DOWN entry.

---

## SECTION 7 — Symbol Toxicity Audit

### 7.1 Symbol ranking (R4_CUM primary, Sep data supplementary)

| Symbol | R4_CUM PnL | EV/t | Worst regime | Payoff (overall) | DD contrib | Verdict |
|---|---|---|---|---|---|---|
| BTCUSDT | −212.64 | −1.44 | HIGH_VOL (−103) | 0.70 | >80% of total | **ATTENUATE** |
| BNBUSDT | −66.24 | −0.56 | MR (−29) | ~0.60 | ~25% | **MONITOR** |
| ETHUSDT | +16.24 | +0.28 | LOW_VOL (−73) | ~1.10 | offsetting | **KEEP** |
| 1000PEPEUSDT | 0 R4_CUM / −662 Sep | −4.27 (Sep) | TREND_UP | 0.22-0.28 | primary Sep | **BLOCK from aurora** |
| DOGEUSDT | 0 trades (aurora) | — | — | — | — | not in aurora (MR-only) |

### 7.2 BTC verdict: ATTENUATE

BTC accumulates −212.64 USDT in R4_CUM (biggest single contributor to all losses). September alone added −159 USDT. BTC is negative in every regime except TREND_DOWN (n=25, +87.59). BTC HIGH_VOLATILITY (86% SL rate) and BTC LOW_VOLATILITY (65% SL rate) together account for 96 trades and −262.92 USDT — they are the dominant destroyers. **Recommended action:** attenuate `regime_sizing` for BTC HIGH_VOL (0.50 → 0.20) and BTC LOW_VOL (remove from `allowed_regimes` or 0.75 → 0.25). Do NOT block BTC entirely — TREND_DOWN is profitable and may improve as sample grows.

### 7.3 BNB MR verdict: MONITOR

BNB MR: n=45, ev/t=−0.64, payoff=0.23, WR=78%. The structural problem is identical to the general BNB payoff issue: TP is too small relative to SL for mean-reversion context. In September (n=14, ev/t=−1.04) the pattern worsened but did not cross escalation threshold. The 78% win rate means signal direction is correct. The problem is exit calibration: TP captures +3.89 (crumb), SL wipes −16.19 (catastrophe). **Action:** tune TP wider for BNB MR context before blocking.

### 7.4 1000PEPEUSDT verdict: BLOCK from aurora

1000PEPEUSDT is not a simulation artifact only. The closed trade forensics from Sep-only show 155 trades with structured performance: TREND_UP (n=75, ev=−6.03, payoff=0.28), TREND_DOWN (n=56, ev=−2.23, payoff=0.35). These are real strategy entries capturing meme-coin moves — but the payoff is systematically below breakeven across all regimes. Prior windows (Jun-Aug) showed zero PEPE aurora trades, suggesting September was a period of unusual PEPE regime activity (TREND_UP 24.5% of time) that activated the strategy at scale. The position sizing artifact (2.1B units) is a separate bug — but even without it, PEPE contributed −662 USDT in closed trades. **Remove PEPE from aurora `assets` or restrict to no regimes (`enabled: false`).**

---

## SECTION 8 — Decision Matrix

| Problem | Evidence | Severity | Likely Root Cause | Next Action |
|---|---|---|---|---|
| BTC HIGH_VOL 86% SL rate | R4_CUM: n=42, −103 USDT, TP%=14 | Critical | TP too tight / SL too wide / late entry in volatile regime | Attenuate regime_sizing HIGH_VOL: 0.50→0.20 |
| BTC LOW_VOL 65% SL rate | R4_CUM: n=54, −159 USDT, TP%=35 | Critical | Entries catching noise in flat regime, long hold time (330m med) | Attenuate or remove BTC LOW_VOL from allowed_regimes |
| 1000PEPEUSDT aurora trades | R4_SEP closed: n=155, −662 USDT, ev/t=−4.27 across all regimes | Critical | PEPE in aurora config with all regimes allowed; bad payoff structure | Block PEPE from aurora (set enabled: false or allow_regimes: []) |
| 1000PEPEUSDT sim artifact | Open position 2.1B units, fees>notional, R4_SEP metrics invalid | Critical | Mock broker lacks hard position-size cap; balance compounding unbounded | Investigate simulation artifact |
| BNB MR payoff inversion | n=45, ev=−0.64, WR=78%, avg_TP=+3.89 vs avg_SL=−16.19 | Moderate | TP level too conservative for MR regime volatility | Investigate TP/SL for BNB MR specifically |
| ETH LOW_VOL SL blowout | n=28, avg_SL=−29.46 vs avg_TP=+8.11, payoff=0.26 | Moderate | SL may be inheriting HIGH_VOL width in LOW_VOL regime | Attenuate ETH LOW_VOL sizing or widen TP |
| Regime churn 13-17/day | Med run 50-85 min vs trade hold 125-822 min | Moderate | SMA 48/192 still generating intra-day regime switches between MR/LOW_VOL/UNCERTAIN | No action now; monitor if SMA widening helps |
| Flip logic not observable | No FLIP in close_reason; stop modifications invisible | Low/Unknown | Flip operates via stop adjustment, not direct close | Add flip_triggered + stop_modified_by_flip fields |
| ETH TREND_DOWN large SL | avg_SL=−42.38 (n=9) — individual events could be −80 to −120 | Low | Wide stops for trend trades; correct overall but tail risk | Monitor; do not tighten until n≥40 |
| BTC TREND_DOWN fat-tail wins | avg_TP=+49.84, WR=28%, overall positive (+87 USDT) | None — opportunity | Infrequent large wins dependent on regime sustaining through trade | Keep; protect from being blocked |

---

## SECTION 9 — Minimal Next-Step Plan

**Three experiments only. In order of priority:**

### Experiment 1 (highest priority): Re-run September-only WITHOUT 1000PEPEUSDT in aurora

**Why:** R4_SEP is contaminated by 667 USDT in PEPE losses + a 2.1B-unit position sizing bug. We cannot trust the September BTC/ETH/BNB watchlist signals because PEPE dominates the variance and inflates trade counts.

**How (config only):** In `config/aurora/strategies/aurora.yaml`, set `1000PEPEUSDT.enabled: false` or add `allowed_regimes: []`. Run `--side B --start 2023-09-01 --end 2023-09-30`. Compare BTC/ETH/BNB performance cleanly.

**What it answers:** Is September truly bad for BTC/ETH/BNB under B3, or is the signal buried under PEPE noise?

---

### Experiment 2: Counterfactual for BTC HIGH_VOL and LOW_VOL — sizing attenuation only

**Why:** BTC HIGH_VOL and LOW_VOL together: 96 trades, −262.92 USDT. These two contexts are the largest single loss source. Both have correct payoff structure (HIGH_VOL payoff=2.80, LOW_VOL payoff=0.89) but catastrophically low TP rates.

**How (config only):** In `config/aurora/strategies/aurora.yaml` for BTCUSDT:
- `regime_sizing.HIGH_VOLATILITY: 0.50 → 0.15`
- Remove `LOW_VOLATILITY` from `allowed_regimes` (or `regime_sizing.LOW_VOLATILITY: 0.75 → 0.20`)

Run Sep-only (after Experiment 1 baseline is clean) to measure isolated BTC impact.

**What it answers:** How much of BTC loss is sizing-driven vs direction-driven? If PnL per trade improves proportionally with sizing, the entries are directionally correct but over-sized for noise.

---

### Experiment 3: BNB MR TP calibration study

**Why:** BNB MR has the most paradoxical profile: 78% win rate but negative EV. The signal is correct (direction right most of the time) but the exit structure destroys the edge. TP = +3.89 avg, SL = −16.19 avg.

**How (analysis only first):** Compute the TP levels that would have been needed for BNB MR trades to break even. From existing data: at 78% WR, breakeven requires `avg_TP ≥ avg_SL × (1-wr)/wr = 16.19 × 0.22/0.78 ≈ 4.56`. Current avg_TP = 3.89 < 4.56 → below breakeven. A TP increase of ~20% would reach breakeven. If `regime_tpsl.tp_mult` for BNB MR is configurable, a small experiment (tp_mult: 1.0 → 1.25 for MEAN_REVERSION) is worth one window validation.

**What it answers:** Is BNB MR salvageable via exit calibration, or is it fundamentally a bad entry context?

---

## Appendix A — Key Missing Instrumentation

For the next backtest, add these fields to trade records to unlock full MFE/MAE and flip forensics:

| Field | Where | Purpose |
|---|---|---|
| `mfe_usdt` | trade record | Maximum favorable excursion during trade lifetime |
| `mae_usdt` | trade record | Maximum adverse excursion during trade lifetime |
| `peak_unrealized_pnl` | trade record | Highest unrealized profit before exit (missed profit detection) |
| `regime_at_exit` | trade record | Regime label at time of exit (vs entry) |
| `flip_triggered` | trade record | Whether exit was influenced by flip/reversal signal |
| `stop_modified_by_flip` | trade record | Whether stop was tightened mid-trade |
| `position_size_cap` | mock broker | Hard cap to prevent runaway compound sizing (sim validity) |

---

*Analysis completed: 2026-03-07 | Phenix/Aurora B3 patched3 forensic audit*
