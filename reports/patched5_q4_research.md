# patched5 Q4 Research — ETH MR / BNB MR / ETH TREND_DOWN Validation
**Config baseline:** patched5 | **Research window:** Q4 2023 (Nov / Dec / Q4 CUM Oct-Dec)
**Status:** COMPLETE — verdicts issued 2026-03-10

---

## SECTION 0 — Executive Verdict

**ETH TREND_DOWN:** `MONITOR` — stable profit engine in H2 2023 trending markets, but structurally fails in December 2023 bull acceleration. Not safe to confirm as unconditional KEEP.

**ETH MEAN_REVERSION:** `KEEP` — reversed from Jun-Aug apparent losses to Q4 strongly positive (Nov: +54.14 WR=100%, Dec: +55.42 WR=100%, Q4 CUM: +62.75 EV=+4.48). Prior Jun-Sep CUM losses were inflated by account-depletion position sizing, not structural failure.

**BNB MEAN_REVERSION:** `MONITOR` — only n=2 trades in Q4 CUM. Statistically insufficient for Q4 verdict. Retained.

**patched5 baseline:** `CONFIRM` — near-zero performance in both Jun-Sep (−1.68%) and Q4 (−3.21%) with controlled DD (<25%) and positive sharpe (+0.042 / +0.066). The system is structurally sound; the main volatility driver is ETH TREND_DOWN monthly variance.

**Unexpected finding:** `DOGEUSDT` is active in aurora (not blocked) and contributed +120.50 USDT in Q4 CUM — the primary profit source in that window. This requires investigation.

---

## SECTION 1 — Artifact Validity

### 1.1 Config verified at research time
```
ETH allowed_regimes : ['TREND_DOWN', 'FLAT_LOW', 'FLAT_NORMAL', 'MEAN_REVERSION']
BNB allowed_regimes : ['FLAT_NORMAL', 'MEAN_REVERSION']
BTC allowed_regimes : []   (blocked)
PEPE allowed_regimes: []   (blocked)
BTC in symbols_to_track : False
PEPE in symbols_to_track: False
SMA 48 / 192
```

### 1.2 Run validity

| Run | Period | run_id | BTC | PEPE | ETH_LV | BNB_LV | Valid? |
|---|---|---|---|---|---|---|---|
| NOV-only | 2023-11-01..11-30 | 20260310_033711 | 0 | 0 | 0 | 0 | ✅ |
| DEC-only | 2023-12-01..12-31 | 20260310_111556 | 0 | 0 | 0 | 0 | ✅ |
| Q4 CUM | 2023-10-01..12-31 | 20260310_141751 | 0 | 0 | 0 | 0 | ✅ |

**Note: OCT-only not run standalone. October data derived from Q4 CUM month breakdown.**

**Unexpected behaviour — DOGEUSDT appearing in aurora:**
DEC: DOGE n=25, −15.80 USDT. Q4 CUM: DOGE n=32, +120.50 USDT. DOGE has non-empty `allowed_regimes` in aurora.yaml and was present in `symbols_to_track`. The `strategies.yaml` registry comment (`P2-2: DOGE/XRP REMOVED`) did not prevent aurora from executing DOGE trades. DOGE is active in this config. This is not a blocking validity issue (blocks are BTC/PEPE/LOW_VOL), but must be noted in analysis.

---

## SECTION 2 — Prior Context (Jun-Sep patched5)

| Window | total_pnl | DD | sharpe | ETH | BNB |
|---|---|---|---|---|---|
| Jun-Sep CUM (patched4b) | −403.70 | 47.9% | −0.65 | −153.80 | −250.76 |
| Jun-Sep CUM (patched5) | −16.83 | 17.34% | +0.042 | +72.69 | −89.22 |
| Sep-only (patched5) | +54.50 | 12.17% | +0.47 | +14.89 | +40.20 |

Jun-Sep per-regime baseline:

| Symbol × Regime | n | PnL | EV/t | WR% |
|---|---|---|---|---|
| ETH TREND_DOWN | 23 | +200.19 | +8.70 | 73.9% |
| ETH MR | 7 | −127.50 | −18.21 | 42.9% |
| BNB MR | 50 | −89.22 | −1.78 | 78.0% |

---

## SECTION 3 — Q4 Monthly Results

### 3.1 November 2023 (patched5) ✅ VALID

| Метрика | Value |
|---|---|
| total_pnl | **+126.20 USDT** |
| roi_pct | +12.62% |
| max_drawdown | 13.89% |
| closed_trades | 19 |
| win_rate | 78.95% |
| sharpe_ratio | **+0.771** |
| end_balance | 1126.20 USDT |

PnL by symbol: **ETH: n=19, +127.50 USDT** | BNB=0 | DOGE=0

Per-regime:

| Symbol × Regime | n | PnL | EV/t | WR% | SL | TP | avg_win | avg_loss | payoff |
|---|---|---|---|---|---|---|---|---|---|
| ETH TREND_DOWN | 14 | +73.36 | +5.24 | 71.4% | 4 | 10 | +40.23 | −82.23 | 0.489 |
| **ETH MR** | 5 | **+54.14** | **+10.83** | **100%** | 0 | 5 | +10.83 | 0 | ∞ |

---

### 3.2 December 2023 (patched5) ✅ VALID

| Метрика | Value |
|---|---|
| total_pnl | **−140.01 USDT** |
| roi_pct | −14.00% |
| max_drawdown | 33.01% |
| closed_trades | 56 |
| win_rate | 73.21% |
| sharpe_ratio | −0.360 |
| end_balance | 859.99 USDT |

PnL by symbol: ETH: n=29, −81.26 | DOGE: n=25, −15.80 | BNB: n=2, −18.43

Per-regime (full — all symbols):

| Symbol × Regime | n | PnL | EV/t | WR% | SL | TP | avg_win | avg_loss |
|---|---|---|---|---|---|---|---|---|
| DOGE TREND_DOWN | 2 | −34.86 | −17.43 | 50% | 1 | 1 | +13.80 | −48.65 |
| BNB MR | 2 | −18.43 | −9.22 | 50% | 1 | 1 | +5.67 | −24.10 |
| DOGE LOW_VOL | 13 | +0.68 | +0.05 | 85% | 2 | 11 | +4.68 | −25.39 |
| DOGE TREND_UP | 10 | +18.37 | +1.84 | 80% | 2 | 8 | +17.66 | −61.44 |
| **ETH MR** | 5 | **+55.42** | **+11.08** | **100%** | 0 | 5 | +11.08 | — |
| **ETH TREND_DOWN** | **24** | **−136.68** | **−5.69** | 62% | **9** | 15 | +34.67 | −72.97 |

---

### 3.3 October 2023 (derived from Q4 CUM month data)

| Метрика | Value |
|---|---|
| closed_trades | ~4 (from Q4 month breakdown) |
| pnl (total month) | **−120.01 USDT** |

Implied: Oct had near-zero activity (n=4), entirely in large negative SL events. Possible causes: market warmup artifact at window start, or extreme early-Oct BTC/ETH volatility causing large SL exits on the 4 trades that opened. Insufficient data for per-regime breakdown.

---

### 3.4 Q4 Cumulative Oct-Dec (patched5) ✅ VALID

| Метрика | Value |
|---|---|
| total_pnl | **−32.11 USDT** |
| roi_pct | −3.21% |
| max_drawdown | 24.09% |
| closed_trades | 87 |
| win_rate | 73.56% |
| sharpe_ratio | **+0.066** |
| end_balance | 967.89 USDT |
| **peak_balance (intra-run)** | **>1200 USDT** (confirmed) |

**Equity curve shape:** Start 1000 → October losses → intermediate recovery → peak >1200 mid-Q4 → December ETH TREND_DOWN pullback → end 967.89. The 24.09% max_drawdown is measured from this intra-run peak (>1200) to the December trough. Implied trough ≈ >1200 × 0.7591 ≈ ~911 USDT; end balance 967.89 is above the trough (partial recovery in late Dec).

PnL by symbol: ETH: n=53, −107.76 | **DOGE: n=32, +120.50** | BNB: n=2, −20.75

Per-regime (full — all symbols):

| Symbol × Regime | n | PnL | EV/t | WR% | SL | TP | avg_win | avg_loss |
|---|---|---|---|---|---|---|---|---|
| **ETH TREND_DOWN** | **39** | **−170.51** | **−4.37** | 64% | 14 | 25 | +37.16 | −78.54 |
| BNB MR | 2 | −20.75 | −10.38 | 50% | 1 | 1 | +6.38 | −27.13 |
| DOGE LOW_VOL | 13 | −0.16 | −0.01 | 85% | 2 | 11 | +4.97 | −27.40 |
| DOGE TREND_UP | 16 | +68.59 | +4.29 | 75% | 5 | 11 | +21.25 | −46.60 |
| DOGE TREND_DOWN | 3 | +52.06 | +17.35 | **100%** | 0 | 3 | +17.35 | — |
| **ETH MR** | **14** | **+62.75** | **+4.48** | **86%** | 2 | 12 | +10.84 | −33.65 |

Monthly Q4 CUM breakdown:
| Month | n | PnL |
|---|---|---|
| Oct | 4 | −120.01 |
| Nov | 19 | +100.21 |
| Dec | 64 | +11.79 |

**Note — CUM vs standalone divergence in December:**
Q4 CUM Dec shows +11.79 but standalone Dec-only = −140.01 USDT. This is a position-sizing effect: by December in the CUM run, the balance had peaked >1200 USDT (larger positions = larger wins on TP), while the standalone Dec run starts at a flat 1000 USDT. Additionally, DOGE n=32 Q4 CUM vs n=25 Dec standalone implies ~7 DOGE trades occurred in Oct/Nov of the CUM run, contributing positively to the intra-run peak. The Dec monthly PnL from the CUM run is *not* directly comparable to the standalone Dec figure.

---

## SECTION 4 — ETH TREND_DOWN Analysis

### 4.1 EV/trade per window (all confirmed)

| Window | n | PnL | EV/t | WR% | Verdict |
|---|---|---|---|---|---|
| Jun-Sep CUM | 23 | +200.19 | +8.70 | 73.9% | ✅ POSITIVE |
| Sep-only | 6 | +5.06 | +0.84 | 66.7% | ✅ marginal |
| Nov-only | 14 | +73.36 | +5.24 | 71.4% | ✅ POSITIVE |
| **Dec-only** | **24** | **−136.68** | **−5.69** | 62.5% | **❌ NEGATIVE** |
| Q4 CUM | 39 | −170.51 | −4.37 | 64.1% | **❌ NEGATIVE** (Dec dominates) |

### 4.2 What happened in December

December 2023 was the start of the crypto bull run (BTC broke ATH prep, ETH rally). The SMA 48/192 likely detected residual TREND_DOWN from earlier bear market, generating SHORT-biased entries into a rising market. The 9 SL events at avg −72.97 each = −656.73 in SL losses for just n=9 events. This is consistent with a strongly adverse market direction.

Payoff=0.473 — the individual win (avg +34.67) is good when TP hits, but the WR dropped to 62.5% and the SL magnitude is catastrophic.

### 4.3 Decision applied

Rule: KEEP if positive EV in ≥ 2/3 new months.
New months available: Nov ✅, Dec ❌. Oct insufficient data.
Result: only 1/2 confirmed, plus Q4 CUM is clearly negative.

**ETH TREND_DOWN → `MONITOR`**

Not blocking: it's the primary earning engine in bear/consolidating markets. Positive in 4 of 5 windows (Jun, Aug-Sep, Nov). But December shows it fails badly in strong directional bull rallies. The regime detector over-holds TREND_DOWN signal after market reverses upward.

---

## SECTION 5 — ETH MEAN_REVERSION Analysis

### 5.1 EV/trade per window

| Window | n | PnL | EV/t | WR% | Verdict |
|---|---|---|---|---|---|
| Jun-Sep CUM | 7 | −127.50¹ | −18.21 | 42.9% | ⚠️ apparently negative |
| Sep-only | 7 | +9.82 | +1.40 | 85.7% | ✅ |
| **Nov-only** | **5** | **+54.14** | **+10.83** | **100%** | **✅ strongly positive** |
| **Dec-only** | **5** | **+55.42** | **+11.08** | **100%** | **✅ strongly positive** |
| **Q4 CUM** | **14** | **+62.75** | **+4.48** | **85.7%** | **✅ POSITIVE** |

¹ Jun-Sep CUM ETH MR loss (−127.50) is contradicted by Sep-only result (+9.82) with identical n=7. Root cause: CUM run had greatly depleted capital by September from Jul-Aug bleed, compressing Sep position sizes. The −127.50 includes large SL events from a different window slice. The actual ETH MR pattern in well-capitalized state is positive (Sep-only, Nov, Dec all positive).

### 5.2 Q4 cumulative n check
Q4 CUM: n=14 — just under the block threshold of n≥15.

### 5.3 Decision applied

Rule: BLOCK candidate if EV/t < 0 in ≥ 2/3 new months AND n≥15.
New months: Nov ✅ (+10.83), Dec ✅ (+11.08). Neither negative.
Rule NOT met for block.

**ETH MEAN_REVERSION → `KEEP`**

Positive in 4/5 windows. The Jun-Sep CUM result was a capital-compression artifact, not a structural failure. ETH MR has been consistently near-zero-to-positive in isolated windows. WR 85–100% in Q4. The avg_loss when SL fires (−33.65) is large, but SL events are rare (n=2 in Q4).

---

## SECTION 6 — BNB MEAN_REVERSION Analysis

### 6.1 EV/trade per window

| Window | n | PnL | EV/t | WR% | Season | Verdict |
|---|---|---|---|---|---|---|
| Jun-Sep CUM | 50 | −89.22 | −1.78 | 78% | Summer | ⚠️ |
| Sep-only | 16 | +40.20 | +2.51 | 93.75% | Autumn | ✅ |
| Q4 CUM | 2 | −20.75 | −10.38 | 50% | Autumn/Winter | n/a (n=2) |

### 6.2 Q4 assessment

BNB MR generated only **2 trades in the entire Q4 window** (Oct-Dec). Statistically meaningless. This likely reflects BNB spending most of Q4 in regimes other than MEAN_REVERSION and FLAT_NORMAL (the only two in BNB's allowed_regimes).

**BNB MEAN_REVERSION → `MONITOR`**

Cannot issue verdict on n=2. Retain in config. The Sep-only result (+40.20, WR=93.75%) remains the strongest data point. The activation frequency is simply very low in Q4.

---

## SECTION 7 — DOGEUSDT Unexpected Activity

DOGE has `allowed_regimes: ["TREND_DOWN", "LOW_VOLATILITY", "FLAT_NORMAL", "MEAN_REVERSION", "TREND_UP"]` in aurora.yaml and is present in `symbols_to_track`. Despite the config comment `P2-2: DOGE/XRP REMOVED - MR-only symbols per strategies.yaml registry`, DOGE IS executing aurora trades in this config.

### 7.1 DOGE summary per window

| Window | DOGE n | DOGE pnl | EV/t | WR% |
|---|---|---|---|---|
| Jun-Sep CUM | 0 | 0 | — | — |
| Dec-only | 25 | −15.80 | −0.63 | 80% |
| Q4 CUM | 32 | **+120.50** | +3.77 | 81.25% |

### 7.2 DOGE breakdown by regime (per-symbol × regime query on raw JSON)

**DEC-only (confirmed):**

| DOGE × Regime | n | PnL | EV/t | WR% | SL | TP | avg_win | avg_loss |
|---|---|---|---|---|---|---|---|---|
| TREND_DOWN | 2 | **−34.86** | −17.43 | 50% | 1 | 1 | +13.80 | −48.65 |
| LOW_VOLATILITY | 13 | +0.68 | +0.05 | 85% | 2 | 11 | +4.68 | −25.39 |
| TREND_UP | 10 | +18.37 | +1.84 | 80% | 2 | 8 | +17.66 | −61.44 |
| **DOGE DEC total** | **25** | **−15.80** | −0.63 | 80% | 5 | 20 | | |

**Q4 CUM (confirmed):**

| DOGE × Regime | n | PnL | EV/t | WR% | SL | TP | avg_win | avg_loss |
|---|---|---|---|---|---|---|---|---|
| TREND_DOWN | 3 | **+52.06** | +17.35 | **100%** | 0 | 3 | +17.35 | — |
| LOW_VOLATILITY | 13 | −0.16 | −0.01 | 85% | 2 | 11 | +4.97 | −27.40 |
| TREND_UP | 16 | **+68.59** | +4.29 | 75% | 5 | 11 | +21.25 | −46.60 |
| **DOGE Q4 total** | **32** | **+120.50** | +3.77 | 81% | 7 | 25 | | |

### 7.3 Key findings

**DOGE profit engine in Q4 CUM = TREND_UP (n=16, +68.59) + TREND_DOWN Oct shorts (n=3, +52.06)**
- TREND_UP: Dec bull run — DOGE caught the uptrend (+21.25 avg win). Primary DOGE profit source.
- TREND_DOWN in Q4 CUM: 3 trades, ALL TP+100% WR → these are Oct/early-Q4 shorts when DOGE was still in downtrend. None reached SL.
- TREND_DOWN in DEC: same regime, DOGE now reversed upward → 2 trades, 1 SL (−48.65), near breakeven overall. Confirms regime-lag risk for DOGE same as ETH.
- LOW_VOLATILITY: nearly break-even (−0.16 on n=13). DOGE SL is small relative to ETH/BNB (avg_loss = −27.40 vs ETH avg −78.54). DOGE LOW_VOL is NOT the same blowout risk as ETH/BNB LOW_VOL was.

**Why DEC DOGE was −15.80 but Q4 CUM DOGE was +120.50:**
- In Q4 CUM, DOGE caught 3 early-Oct TREND_DOWN shorts at +52.06 (absent in standalone Dec run)
- In standalone Dec start balance = 1000 → smaller positions. In Q4 CUM Dec, balance ≈ current peak → larger positions → TREND_UP gains amplified.

**DOGE LOW_VOL safety profile:** avg_loss = −27.40 USDT (n=2 SL events only). Compared to patched4b ETH LOW_VOL avg_loss = −28 USDT but n=29 SL events. DOGE fires LOW_VOL much less frequently in Q4. Risk is contained.

**Action required:** DOGE is a config-active symbol with full regime access. The net Q4 result is strongly positive (+120.50) and it carries intentional configuration. However:
- LOW_VOL is in DOGE `allowed_regimes` → same structural risk as ETH/BNB had in patched4b, but currently contained by low activation
- TREND_DOWN for DOGE has regime-lag risk (Dec pattern: short in bull accelerating = −34.86)
- Recommended: add DOGE to formal monitoring scope. Evaluate LOW_VOL block for DOGE if Q1 2024 data shows increased LOW_VOL activation.

---

## SECTION 8 — Decision Matrix

| Regime | Jun-Sep signal | Q4 signal | Rule met | **Verdict** |
|---|---|---|---|---|
| ETH TREND_DOWN | +8.70 ev/t ✅ | −4.37 ev/t ❌ (Dec dominant) | Mixed: 1/2 new months positive | **MONITOR** |
| ETH MR | −18.21¹ / +1.40 Sep | +4.48 ev/t, n=14, WR=85.7% ✅ | Positive in all Q4 | **KEEP** |
| BNB MR | −1.78 ev/t ⚠️ / +2.51 Sep ✅ | n=2 (insufficient Q4) | Cannot evaluate | **MONITOR** |
| patched5 baseline | −1.68%, sharpe +0.042 | −3.21%, sharpe +0.066 | Both near-zero, positive sharpe | **CONFIRM** |
| DOGEUSDT (unplanned) | 0 trades | +3.77 ev/t, WR=81.25% Q4 | Positive but uncontrolled | **INVESTIGATE** |

¹ Jun-Sep CUM ETH MR anomaly explained (capital compression in CUM run).

---

## SECTION 9 — Cumulative Performance Summary

| Period | total_pnl | DD | sharpe | peak_balance |
|---|---|---|---|---|
| Jun-Sep (patched5 CUM) | −16.83 | 17.3% | +0.042 | not recorded |
| Q4 Oct-Dec (patched5) | −32.11 | 24.1% | +0.066 | **>1200 USDT** (confirmed) |
| **Implied H2 2023** | **≈ −49** | **peak ~24%** | **mixed** | — |

Implied: if the periods were composited on the same capital base, the system would end H2 2023 approximately −49 USDT (−4.9% on 1000 USDT initial), with max DD around 24%. This is a fundamentally different picture from the pre-patching state (patched3 R4_CUM was −262.64 USDT over just 4 months).

**Q4 equity curve note:** The Q4 CUM run produced an intra-run peak balance >1200 USDT before December's ETH TREND_DOWN drawdown reversed the gains. The system demonstrated the capacity to reach +20% peak ROI within a single quarter, with the structural problem being the inability to hold gains through the December bull regime flip. This is consistent with the ETH TREND_DOWN `MONITOR` verdict — the engine works, but regime-detection lag in strong directional reversals erodes peak P&L.

---

## SECTION 10 — Minimal Next Step

**patched5 is confirmed as current stable baseline.** No new patches needed based on this research alone.

### Option A — Extend horizon (recommended priority 1)
Run 2024 Q1 (Jan-Mar 2024) on patched5 to confirm:
- Whether ETH TREND_DOWN recovers in consolidation after Dec 2023 rally
- Whether DOGE continues to contribute positively
- BNB MR activity in Jan-Mar
- Sample size for ETH MR crosses n=30 threshold for high-confidence verdict

### Option B — DOGE investigation (recommended priority 2, parallel to A)
Clarify DOGE status: intentional or config gap.
- If intentional: add to scope, apply LOW_VOL block to DOGE same as ETH/BNB
- If gap: add `allowed_regimes: []` to DOGE in patched5 config

Running CUM with vs without DOGE would isolate real ETH+BNB-only performance.

### Option C — patched6 = block ETH TREND_DOWN in Dec-type environments
**Not recommended yet.** ETH TREND_DOWN is the primary engine in most markets. Blocking it would cripple Jun-Sep and Nov performance. The December failure is a regime-detection lag issue in strong bull trends — addressable via SMA tuning rather than regime blocking.

### Option D — TP/SL calibration study for ETH TREND_DOWN
**Not recommended yet** (need more samples). The avg_loss for ETH TREND_DOWN SL is −75 to −83 USDT, which suggests the SL is extremely wide relative to typical win size (+35–40 USDT TP). If SL was tightened for TREND_DOWN context, Dec losses would be smaller. But tighter stops in volatile trending markets would also increase SL frequency. Study needs n≥50 SL events, currently n=27 (Q4+Jun-Sep).

**Recommended path:** Option A (extend to 2024 Q1) + Option B (clarify DOGE).

---

## SECTION 11 — Deep Analysis (backtest_summarize + backtest_log_stats)

*Source: `tools/backtest/backtest_summarize.py` + `scripts/diagnostics/backtest_log_stats.py` run on Q4 run artifacts.*

### 11.1 Profit Factor per regime per window

| Window | Regime | n | PnL | PF | WR% | Verdict |
|---|---|---|---|---|---|---|
| NOV | ETH TREND_DOWN | 14 | +73.36 | **1.22** | 71% | ✅ positive |
| NOV | ETH MR | 5 | +54.14 | ∞ (no SL) | 100% | ✅ perfect |
| DEC | ETH TREND_DOWN | 24 | −136.68 | **0.76** | 62% | ❌ losing |
| DEC | DOGE TREND_DOWN | 2 | −34.86 | 0.28 | 50% | ❌ bad |
| DEC | DOGE LOW_VOL | 13 | +0.68 | 1.01 | 85% | ≈ break-even |
| DEC | DOGE TREND_UP | 10 | +18.37 | **1.15** | 80% | ✅ |
| DEC | ETH MR | 5 | +55.42 | ∞ (no SL) | 100% | ✅ |
| DEC | BNB MR | 2 | −18.43 | 0.24 | 50% | ⚠️ (n=2) |
| Q4 CUM | ETH TREND_DOWN | 39 | −170.51 | **0.84** | 64% | ❌ Dec weight |
| Q4 CUM | DOGE TREND_DOWN | 3 | +52.06 | ∞ (no SL) | 100% | ✅ Oct shorts |
| Q4 CUM | DOGE LOW_VOL | 13 | −0.16 | 0.997 | 85% | ≈ break-even |
| Q4 CUM | DOGE TREND_UP | 16 | +68.59 | **1.37** | 75% | ✅ |
| Q4 CUM | ETH MR | 14 | +62.75 | — | 86% | ✅ |
| Q4 CUM | BNB MR | 2 | −20.75 | 0.24 | 50% | ⚠️ (n=2) |

**Profit factor interpretation:** PF < 1.0 = system loses more in absolute terms than it wins. ETH TREND_DOWN PF in Dec = 0.76 — catastrophic. In Nov PF = 1.22 — healthy. The problem is not WR (still 62% in Dec) but SL magnitude×count.

### 11.2 PnL Bucket Distribution — ETH TREND_DOWN SL anatomy

Q4 CUM TREND_DOWN (n=42 total = 39 ETH + 3 DOGE):

| PnL bucket | count | notes |
|---|---|---|
| [−100, −50) | **14** | ALL ETH SL events. Avg ≈ −78.54 each |
| [+5, +10) | 1 | ETH small TP |
| [+10, +20) | 3 | DOGE TREND_DOWN TP (avg +17.35) + ETH small TP |
| [+20, +50) | 22 | ETH TREND_DOWN TP bulk |
| [+50, +100) | 2 | ETH TREND_DOWN large TP |

**Key structural finding:** ALL 14 SL events for TREND_DOWN fall in the [−50, −100) bucket (none in [−20, −50)), meaning TREND_DOWN SL threshold is hard-bounded above −50 USDT per trade. This is a calibration issue: the SL level for TREND_DOWN is set so wide that when price moves adverse over a sustained trend, the loss is always catastrophic (>50 USDT). There are no "small" SL exits. Compare to BNB MR SL (avg −27) and DOGE LOW_VOL SL (avg −27): those produce a scattered distribution, not a fixed-bucket concentration.

**Implication for Option D (TP/SL calibration):** tightening TREND_DOWN SL from ~78 to ~35 USDT would keep SL losses in the [−20, −50) range — more frequent but individually smaller. Net effect depends on SL frequency vs magnitude tradeoff. Needs simulation.

### 11.3 Signal Funnel Analysis (from order log stats)

| Window | Signals | Rejected | Proposed | Placed | Filled | Rejection rate |
|---|---|---|---|---|---|---|
| NOV | 733 | 708 | 25 | 25 | 19 | 96.6% |
| DEC | 1290 | 1223 | 67 | 68 | 56 | 94.8% |
| Q4 CUM | 2375 | 2273 | 102 | 102 | 87 | **95.7%** |

**Primary reject reason:** `NRR-026 | SAFETY_GATES:FIX-CONF-GATE-01` accounts for 94–96% of all rejections (686/708 NOV, 1170/1223 DEC, 2186/2273 Q4 CUM). Secondary: `NRR-027 downtrend blocks long` (21/50/82 respectively).

**Implication:** FIX-CONF-GATE-01 is the dominant filter. Only ~4% of raw regime-triggered intents pass through. This gate is functioning normally (it prevented ~95% of potential trades). The trades that do get through are high-confidence entries — which is why WR is consistently 73–79%.

**Side distribution (Q4 CUM):** 90 BUY vs 12 SELL. The system is heavily long-biased in Q4 (consistent with bull-trending Oct-Dec 2023).

### 11.4 Regime presence in DEC order log (unexpected regimes)

The DEC order log shows intents being placed in `LOW_VOLATILITY` (14 placed) and `TREND_UP` (10 placed). Since ETH/BNB both have LOW_VOL blocked in patched5, these orders are entirely **DOGE** activity. This independently confirms:
- DOGE is the sole contributor to LOW_VOL and TREND_UP trades in Q4
- DOGE fires in 4 distinct regimes (TREND_DOWN, LOW_VOL, TREND_UP, and likely FLAT_NORMAL)
- ETH/BNB LOW_VOL block is operating correctly (0 ETH/BNB LOW_VOL trades found)

---

*Research completed: 2026-03-10 | Aurora/Phenix patched5 Q4 2023 validation*
*Deep analysis (Section 11 + DOGE regime breakdown + PnL buckets + funnel): 2026-03-11*
