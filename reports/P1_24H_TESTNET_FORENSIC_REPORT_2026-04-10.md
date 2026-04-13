# P0.5+P1 24-HOUR TESTNET FORENSIC REPORT

**Date**: 2026-04-10
**Session**: 2026-04-09 10:10 UTC → 2026-04-10 13:05 UTC (26.9h wall-clock)
**Active window**: 2026-04-09 13:50 UTC → 2026-04-10 12:26 UTC (22.6h effective)
**Config applied**: P0.5 package (9 YAML edits)

---

## 1. Executive Summary

**The 24h P1 testnet session lost -249.64 USDT net across 31 completed trades.**

P0.5 config changes deployed correctly:
- ETH leverage confirmed at 20x (was 41x) ✓
- LOW_VOL TP/SL tightening applied as configured ✓
- DOGE sl_atr_mult=2.0 deployed ✓
- Zero TP/SL fallbacks — all 37 brackets used `source=STRATEGY` ✓

However, the system remains structurally broken:
1. **Win/loss asymmetry** is the primary problem: 51.6% win rate but average loser (-19.71 USDT) is **6.8×** average winner (+2.87 USDT). TP targets are far too tight relative to SL distances.
2. **SHORT dominance persists**: BUY=6 executions (16.2%) vs SELL=31 (83.8%). BTC had **zero** BUY intents.
3. **FLIP_GATE_UNKNOWN** blocked 139 signals across the **entire** 27h session — it is session-wide, not a cold-start transient.
4. **BRACKETS_PENDING ghost states** permanently blocked BTCUSDT and DOGEUSDT re-entry after their initial positions closed.
5. **LOW_VOLATILITY** is the worst regime by net PnL (-141.36 USDT) despite the highest win rate (57.9%).
6. **ETHUSDT** is the worst symbol by net PnL (-101.19 USDT) despite 58.3% win rate.

**Verdict**: P1 improved config correctness (leverage, TP/SL source) but did NOT materially improve profitability. The core problem is **structural TP/SL asymmetry** — wins are capped at ~3 USDT but losses reach 20+ USDT. This is a strategy geometry problem, not a config tuning problem.

---

## 2. Scope and Artifact Inventory

### Run Window
| Metric | Value |
|--------|-------|
| BOOT timestamp | 2026-04-09 10:10:00 UTC |
| First ORDER_FILLED | 2026-04-09 11:01:41 UTC |
| First successful trade execution | 2026-04-09 13:50:04 UTC |
| Last ORDER_FILLED | 2026-04-10 12:26:30 UTC |
| Last order_log entry | 2026-04-10 13:05:03 UTC |
| Wall-clock duration | 26.9 hours |
| Effective active trading | 22.6 hours |
| Burn-in (BOOT → first execution) | 3h40m |

### Artifacts Inspected

| Artifact | Size | Authority |
|----------|------|-----------|
| `logs/order_log_v1.jsonl` | 695 entries, 895 KB | **Runtime truth** — intent/fill/reject pipeline |
| `logs/shadow_critical_event_journal_v1.jsonl` | 41,713 events, 49 MB | **Runtime truth** — FSM events |
| `logs/trade_lifecycle.jsonl` | 133,617 records, 235 MB | **Runtime truth** — full lifecycle |
| `logs/aurora_trades.log` | 314 lines, 37 KB | **Runtime truth** — human-readable summary |
| `logs/aurora_events.jsonl` | 274 events, 92 KB | **Runtime truth** — order state changes |
| `logs/domain_execution_position.log*` | 3 files, 12 MB | **Runtime truth** — TP/SL resolution |
| `logs/domain_decision_making.log*` | 2 files, 14 MB | **Runtime truth** — DM pipeline |
| `logs/regime_confidence_audit_v1.jsonl` | 2,612 records, 3.2 MB | **Runtime truth** — regime detector |
| `ops/restore/execution_position_restore_envelope_v1.json` | 1.2 KB | **Local state** — final position snapshot |
| `ops/wal/2026-04-09.jsonl`, `2026-04-10.jsonl` | 46 MB combined | **Persistent truth** — WAL records |
| `config/aurora/strategies/aurora.yaml` | N/A | **Config SSOT** — verified P0.5 edits present |
| `config/aurora/instruments.yaml` | N/A | **Config SSOT** — ETH leverage=20 confirmed |
| `config/aurora/strategies/mean_reversion.yaml` | N/A | **Config SSOT** — DOGE sl_atr_mult=2.0 confirmed |

---

## 3. Session Validity / Burn-In Assessment

### Burn-In Window: 10:10 → 13:50 UTC (3h40m)

- **10:10**: BOOT event. Config loaded. Warmup and basis hydration begin.
- **11:01**: First ORDER_FILLED events appear (bracket fills from pre-session restored positions, not new entries).
- **13:10**: First TRADE_INTENT_PROPOSED (SOLUSDT SELL) → immediately rejected `NRR-EXECUTION-REJECTED: exposure_fail_closed_directional_ratio_breach`
- **13:50**: First successful execution (ETHUSDT SELL, order_id=8634423167)
- **3h40m burn-in** caused by startup warmup + exposure guard initialization + regime detector warmup

### Pre-Session Legacy Positions
Four positions existed from the prior run and were restored:
- DOGEUSDT: -76,984 qty SHORT (disappeared/reconciled)
- ETHUSDT: -4.597 qty SHORT (disappeared/reconciled)
- SOLUSDT: +76 qty LONG (disappeared/reconciled)
- BTCUSDT: -0.123 qty SHORT (disappeared mid-session)

All four "disappeared" — meaning they were either closed by existing brackets or reconciled away during startup. The 248 ORDER_FILLED events include these bracket fills.

### Conclusion
Analysis uses **both** views:
- **Full 27h** for regime bar counts, blocking rates, and system-level statistics
- **Active 22.6h** for trade performance, since burn-in produces no new entries

---

## 4. Regime Statistics

### 4a. Regime Bar Distribution (Full Session)

| Regime | BTC bars | ETH bars | SOL bars | DOGE bars | Total % |
|--------|----------|----------|----------|-----------|---------|
| LOW_VOLATILITY | 220 (53%) | 181 (44%) | 278 (60%) | 112 (33%) | 48.3% |
| TREND_UP | 92 (22%) | 80 (19%) | 103 (22%) | 84 (25%) | 21.9% |
| UNCERTAIN | 54 (13%) | 74 (18%) | 50 (11%) | 58 (17%) | 14.4% |
| MEAN_REVERSION | 37 (9%) | 55 (13%) | 31 (7%) | 46 (13%) | 10.3% |
| TREND_DOWN | 5 (1%) | 21 (5%) | 1 (0%) | 41 (12%) | 4.2% |
| HIGH_VOLATILITY | 9 (2%) | 2 (0%) | 0 (0%) | 0 (0%) | 0.7% |

**Dominant regime**: LOW_VOLATILITY (48.3%) — the target of our P0.5 tightening.

### 4b. Regime Performance (Completed Trades)

| Regime | Trades | Wins | Losses | Win% | Gross PnL | Fees | **Net PnL** | Avg Net/Trade |
|--------|--------|------|--------|------|-----------|------|-------------|---------------|
| LOW_VOLATILITY | 19 | 11 | 8 | 57.9% | -83.90 | 57.46 | **-141.36** | -7.44 |
| TREND_UP | 6 | 2 | 4 | 33.3% | -65.03 | 19.17 | **-84.20** | -14.03 |
| MEAN_REVERSION | 6 | 3 | 3 | 50.0% | -4.92 | 19.16 | **-24.08** | -4.01 |

### 4c. Regime Rankings

**Rank by Net PnL (worst first)**:
1. LOW_VOLATILITY: **-141.36 USDT** (57.9% WR, 19 trades) — high-frequency, tiny wins overwhelmed by occasional large SL
2. TREND_UP: **-84.20 USDT** (33.3% WR, 6 trades) — shorting into uptrend, structurally wrong-sided
3. MEAN_REVERSION: **-24.08 USDT** (50.0% WR, 6 trades) — mixed, includes DOGE MR -24.24 loss

**Rank by Stop-Out Severity**:
1. LOW_VOLATILITY: 8 SL hits, avg SL loss ~-18 USDT (TP avg ~+2.7 USDT → 6.7× asymmetry)
2. TREND_UP: 4 SL hits out of 6 trades (67% SL rate)
3. MEAN_REVERSION: 3 SL hits out of 6 trades

**Rank by Fee Drag** (fees as % of gross volume):
1. LOW_VOLATILITY: 57.46 USDT fees on 19 trades → 3.02 USDT/trade. Many TP wins < 3 USDT.
2. TREND_UP: 19.17 USDT on 6 trades → 3.20 USDT/trade
3. MEAN_REVERSION: 19.16 USDT on 6 trades → 3.19 USDT/trade

**Rank by Long/Short Imbalance**:
1. LOW_VOLATILITY: ~84% SELL, ~16% BUY — extreme short bias
2. TREND_UP: ~100% SELL — ALL shorts (into an uptrend)
3. MEAN_REVERSION: mixed (DOGE MR has some BUY)

---

## 5. Symbol Statistics

### 5a. Per-Symbol Performance

| Symbol | Strategy | Trades | Wins | Losses | Win% | Gross PnL | Fees | **Net PnL** | Avg Hold |
|--------|----------|--------|------|--------|------|-----------|------|-------------|----------|
| ETHUSDT | Aurora | 12 | 7 | 5 | 58.3% | -63.73 | 37.46 | **-101.19** | 44.3m |
| SOLUSDT | Aurora | 13 | 7 | 6 | 53.8% | -32.57 | 37.46 | **-70.04** | 42.4m |
| BTCUSDT | Aurora | 5 | 2 | 3 | 40.0% | -36.01 | 18.17 | **-54.18** | 47.3m |
| DOGEUSDT | MR | 1 | 0 | 1 | 0.0% | -21.53 | 2.70 | **-24.24** | 47.9m |

### 5b. Symbol × Regime Cross-Table (Net PnL)

| Symbol | LOW_VOL | MEAN_REV | TREND_UP |
|--------|---------|----------|----------|
| ETHUSDT | **-82.04** | +13.97 | -33.12 |
| SOLUSDT | -37.60 | -26.28 | -6.16 |
| BTCUSDT | +2.51 | -11.77 | **-44.92** |
| DOGEUSDT | -24.24 | — | — |

**Worst combination**: ETHUSDT + LOW_VOLATILITY = **-82.04 USDT**
**Best combination**: ETHUSDT + MEAN_REVERSION = **+13.97 USDT**
**Worst secondary**: BTCUSDT + TREND_UP = **-44.92 USDT**

### 5c. Symbol Rankings

**Rank by Net PnL (worst first)**:
1. ETHUSDT: **-101.19 USDT** — worst overall despite 58.3% WR
2. SOLUSDT: **-70.04 USDT** — second worst, high trade frequency
3. BTCUSDT: **-54.18 USDT** — zero BUY intents, entirely SHORT-locked
4. DOGEUSDT: **-24.24 USDT** — single trade, hit SL, lifecycle stuck

**Rank by Fee Drag**:
1. ETHUSDT: 37.46 USDT fees (37% of 101.19 net loss)
2. SOLUSDT: 37.46 USDT fees (53% of 70.04 net loss)
3. BTCUSDT: 18.17 USDT fees (34% of net loss)
4. DOGEUSDT: 2.70 USDT fees

**Rank by Long/Short Imbalance (Aurora symbols)**:
1. BTCUSDT: **100% SELL** (0 BUY intents, 0 BUY executions)
2. ETHUSDT: 87% SELL (2 BUY / 13 SELL executions)
3. SOLUSDT: 80% SELL (3 BUY / 12 SELL executions)

### 5d. SL vs TP Distribution by Symbol

| Symbol | TP Hits | SL Hits | TP% | SL% | Avg TP Gain | Avg SL Loss |
|--------|---------|---------|-----|-----|-------------|-------------|
| BTCUSDT | 2 | 3 | 40% | 60% | +4.80 | -15.20 |
| ETHUSDT | 7 | 5 | 58% | 42% | +2.04 | **-19.60** |
| SOLUSDT | 7 | 6 | 54% | 46% | +2.55 | **-18.56** |
| DOGEUSDT | 0 | 1 | 0% | 100% | — | -21.53 |
| **TOTAL** | **16** | **15** | **52%** | **48%** | **+2.87** | **-19.71** |

---

## 6. Aurora BUY-Path Recovery Findings

### 6a. BUY Intent and Execution Counts

| Symbol | BUY Intents | SELL Intents | BUY Executions | SELL Executions | BUY% (exec) |
|--------|-------------|--------------|----------------|-----------------|-------------|
| BTCUSDT | **0** | 21 | **0** | 6 | **0.0%** |
| ETHUSDT | 2 | 17 | 2 | 13 | 13.3% |
| SOLUSDT | 3 | 35 | 3 | 12 | 20.0% |
| **Aurora Total** | **5** | **73** | **5** | **31** | **13.9%** |

### 6b. BUY Recovery Assessment

**BUY recovery did NOT materially occur.**

- **BTC**: Zero BUY intents across 27 hours. The BUY path remains fully locked for BTC. The strategist produced 21 SELL signals but generated no buy signals at all.
- **ETH**: 2 BUY intents (10.5% of ETH intents), both at confidence >0.70, both executed. Marginal improvement.
- **SOL**: 3 BUY intents (7.9% of SOL intents), all executed. Marginal improvement.
- **Overall Aurora**: 5 BUY / 73 SELL intents = **6.4% BUY** at intent stage. 5/36 = **13.9% BUY** at execution stage.

### 6c. Why BUY Remains Locked

The system-level blocking mechanisms that suppress BUY:
1. **Strategist signal generator** itself rarely produces BUY signals — the bias is in the signal generation layer, not just the gating layer
2. **FLIP_GATE_UNKNOWN**: Blocked 139 signals (mostly SELL, but also some BUY), preventing direction changes
3. **DZ/UNCERTAIN veto**: DZ veto count = 0 in this run (vol_threshold=0.98 effectively disabled DZ). UNCERTAIN bars = 14.4% of session but produced 0 intents (correctly filtered).
4. **NRR-EXECUTION-REJECTED**: 57 rejections, of which 40 = `OPEN_GUARD_FAIL` (lifecycle ghost blocking re-entry) and 17 = `exposure_fail_closed_directional_ratio_breach` (all-SELL portfolio hits directional limits)

**Key finding**: P0's DZ fix (vol_threshold 0.95→0.98) worked — zero DZ vetoes this session. The BUY problem is upstream in the strategist, not in the gates.

### 6d. Comparison to Pre-P0 Baseline

| Metric | Pre-P0 | P1 Run | Change |
|--------|--------|--------|--------|
| DZ veto rate | ~57% of bars | **0%** | ✓ Fixed |
| UNCERTAIN blocking | High (was major veto) | 0 intents in UNCERTAIN | ✓ Correct |
| BUY intents (Aurora) | ~0 | 5 (6.4%) | Marginal ↑ |
| BUY executions (Aurora) | 0 | 5 (13.9%) | Marginal ↑ |
| SHORT bias | ~100% | 86.1% | Slight ↓ |

---

## 7. TP/SL and ETH Leverage Verification

### 7a. TP/SL Distance Verification

All 37 TP/SL_RESOLVED entries show `source=STRATEGY`. Zero fallbacks.

| Symbol | Count | Avg SL (bps) | Expected SL | Avg TP (bps) | Expected TP | Match? |
|--------|-------|-------------|-------------|-------------|-------------|--------|
| BTCUSDT | 6 SELL | 45.7 | ~32.5 (LOW_VOL) | 112.0 | ~40.6 (LOW_VOL) | Mixed |
| ETHUSDT | 15 (13S/2B) | 70.3 | ~52.3 (LOW_VOL) | 19.6 | ~15.7 (LOW_VOL) | ✓ Close |
| SOLUSDT | 15 (12S/3B) | 66.4 | ~50.0 (LOW_VOL) | 17.1 | ~15.1 (LOW_VOL) | ✓ Close |
| DOGEUSDT | 1 BUY | 28.8 | ATR-based | 39.1 | ATR-based | N/A |

**Analysis**: BTC averages are higher than LOW_VOL targets because BTC traded in multiple regimes (LOW_VOL, MEAN_REVERSION, TREND_UP) — the min SL of 32.5 bps matches LOW_VOL expectation while the wider entries are TREND_UP/MEAN_REV regime trades. ETH and SOL averages closely match LOW_VOL expectations (slightly higher due to some non-LOW_VOL regime trades in the mix).

**SOL min_dist_bps guardrail**: SOL TP minimum = 7.1 bps, well below the old min_dist_bps=18 but above new min_dist_bps=14 in most cases. The change from 18→14 was necessary — 7.1 bps reads like a TREND_UP or MEAN_REV trade, not LOW_VOL. LOW_VOL entries show TP ~15-17 bps, confirming the 15.1 bps calculation.

### 7b. ETH Leverage Verification

**All 14 ETHUSDT ExposureGuard ORDER_INTENT entries show `leverage: 20.0`** ✓

| Check | Result |
|-------|--------|
| P0.5 target | 20x |
| Runtime observed | **20.0x** (14/14 entries) |
| Any residual 41x? | **No** |
| instruments.yaml SSOT? | Confirmed |

### 7c. DOGE SL Widening Verification

| Metric | Old (sl_atr_mult=0.75) | New (sl_atr_mult=2.0) |
|--------|------------------------|----------------------|
| Observed SL distance | ~0.25% (prior run) | 28.8 bps = 0.29% |
| SL hit rate | 3/4 = 75% | 1/1 = 100% |
| Time to SL | Immediate (minutes) | 68 minutes |

The wider SL gave DOGE more time (68 min vs immediate), but the trade still hit SL on a -0.32% move. Single sample — inconclusive whether sl_atr_mult=2.0 is sufficient.

### 7d. TP/SL Verification Table

| # | Symbol | Regime | Side | SL bps | TP bps | Source | Fallback? |
|---|--------|--------|------|--------|--------|--------|-----------|
| 1-6 | BTCUSDT | Mixed | SELL | 32.5-53.5 | 39.8-173.7 | STRATEGY | No |
| 7-21 | ETHUSDT | Mostly LOW_VOL | 13S/2B | 53.1-109.1 | 10.5-41.8 | STRATEGY | No |
| 22-36 | SOLUSDT | Mostly LOW_VOL | 12S/3B | 50.7-88.3 | 7.1-33.6 | STRATEGY | No |
| 37 | DOGEUSDT | MEAN_REV | BUY | 28.8 | 39.1 | STRATEGY | No |

---

## 8. Runtime Issue Impact

### 8a. FLIP_GATE_UNKNOWN

| Metric | Value |
|--------|-------|
| Total blocks | **139** |
| Duration | Entire session (14:05 → 15:25+) — **NOT transient** |
| SOLUSDT blocks | 76 |
| ETHUSDT blocks | 38 |
| BTCUSDT blocks | 24 |
| DOGEUSDT blocks | 1 |
| Material impact | **HIGH** — blocked direction changes for all symbols persistently |

**Root cause**: The flip state tracker requires a completed round-trip trade to initialize. Once a symbol has an open position, the gate blocks new same-direction signals on that symbol until the position lifecycle completes. Since the system repeatedly opens SELL → closes → wants to SELL again, the flip state goes to UNKNOWN between cycles.

**Material distortion**: Yes. 139 blocked signals over 27h means >5 signals/hour suppressed. Many of these would have been additional SELL entries, but some could have been BUY attempts that never got a chance.

### 8b. BRACKETS_PENDING / Ghost State

| Symbol | State | Impact |
|--------|-------|--------|
| BTCUSDT | BRACKETS_PENDING / portfolio FLAT | Ghost — permanently blocks BTC re-entry |
| DOGEUSDT | BRACKETS_PENDING / portfolio FLAT | Ghost — permanently blocks DOGE re-entry |
| ETHUSDT | DEFERRED_PENDING_WAL → FLAT | Recovered correctly |
| SOLUSDT | UNKNOWN → FLAT | Recovered correctly |

**BTC impact**: After BTC's last fill at 22:30 Apr 9, the lifecycle got stuck. All subsequent BTC entries would have been blocked. BTC could only trade for ~9h of the 22.6h active window, then became permanently ghost-locked.

**DOGE impact**: After DOGE SL at 17:48 Apr 9, 14 subsequent DOGE intents were all rejected with `OPEN_GUARD_FAIL`. DOGE was effectively disabled after 4h48m of active window.

**Material distortion**: **HIGH** for BTC and DOGE — both symbols were locked out for most of the session.

### 8c. DOGE MR Path

- Safety gates bypassed (by design): `threshold_verdict: "BYPASS"`
- Leverage discrepancy: instruments.yaml=20x, MR config=10x → runtime uses 20x
- sl_atr_mult=2.0 gave 68 min hold before SL (improvement over instant SL at 0.75)
- Post-SL lifecycle ghost prevented any further DOGE trading
- **Single trade sample** — insufficient to evaluate sl_atr_mult=2.0 effectiveness

### 8d. Other Anomalies

| Issue | Count | Impact |
|-------|-------|--------|
| NRR-EXECUTION-REJECTED: OPEN_GUARD_FAIL | 40 | Lifecycle ghosts blocking re-entry |
| NRR-EXECUTION-REJECTED: directional_ratio_breach | 17 | Portfolio too SHORT-heavy, new SELLs blocked |
| ARBITRATION_BLOCKED | 8 | Multi-strategy arbitration rejection |
| ORDER_CANCELLED | 4 | Normal lifecycle |
| ORDER_TIMEOUT | 1 | Single timeout event |
| HARDENING:TRADE_EXECUTED_SUPPRESSED | 540 | Dedup suppression (normal) |
| TERMINAL_IDENTITY_CACHE_MISS | 248 | Close-reason attribution gap |

The 248 TERMINAL_IDENTITY_CACHE_MISS events mean bracket close-reason attribution (SL vs TP) relies on runtime reconstruction rather than proven exchange identity. This is the DEF-005 gap identified in prior audits.

---

## 9. Root Cause Ranking

| Rank | Cause | Mechanism | Effect | Risk | Evidence |
|------|-------|-----------|--------|------|----------|
| **1** | **TP/SL geometric asymmetry** | TP_dist ~15-20 bps, SL_dist ~50-70 bps → wins are 3× smaller than losses | Avg win +2.87, avg loss -19.71 → **6.8× asymmetry** wipes 51.6% WR | **Critical** — system is structurally unprofitable | 31 trades, 16W/15L, net -249.64 |
| **2** | **SHORT-only signal generation** | Strategist kernel generates ~94% SELL signals (Aurora) | Portfolio permanently SHORT-biased, hits directional ratio limits | **High** — no recovery path without kernel change | 5 BUY / 73 SELL intents |
| **3** | **FLIP_GATE_UNKNOWN (session-wide)** | Flip state tracker never initializes → blocks all direction changes | 139 signals suppressed across full session | **High** — code defect, not config-fixable | 139 FLIP_GATE in aurora_trades.log |
| **4** | **BRACKETS_PENDING ghost state** | Lifecycle FSM stuck after position closed → blocks new entries | BTC blocked last ~13h, DOGE blocked last ~18h | **High** — 2/4 symbols effectively disabled | restore_envelope + OPEN_GUARD_FAIL logs |
| **5** | **Fee drag on micro-TP** | TP gains ~2-3 USDT per trade, fees ~3 USDT per trade | Many "winning" trades are net-negative after fees | **Medium** — structurally linked to cause #1 | 95.79 USDT total fees / 31 trades |
| **6** | **TREND_UP shorting** | System shorts in TREND_UP regime (no BUY-side signals) | 4/6 TU trades hit SL, -84.20 net | **Medium** — strategist should not short uptrends | 6 TREND_UP trades, 33% WR |
| **7** | **Regime detector noise** | ETH 28 transitions, XRP 30 transitions in 27h | Regime flickers → position opened in wrong regime | **Low-Medium** — hysteresis_bars=2 insufficient | regime_confidence_audit data |

---

## 10. Proven Facts vs Inferences vs Assumptions vs Unknowns

### FACTS (log-proven, multi-artifact corroborated)
1. 31 completed trades. Win rate 51.6%. Net PnL -249.64 USDT.
2. Average winner +2.87 USDT, average loser -19.71 USDT (6.8× asymmetry).
3. Total commissions: 95.79 USDT (38% of total net loss).
4. Aurora BUY intents: 5/78 = 6.4%. BTC BUY intents: 0.
5. ETH leverage: 20.0x confirmed across all 14 ExposureGuard entries.
6. All 37 TP/SL_RESOLVED: `source=STRATEGY`. Zero fallbacks.
7. FLIP_GATE_UNKNOWN: 139 blocks, session-wide (not cold-start only).
8. BRACKETS_PENDING ghost: BTC and DOGE stuck with portfolio FLAT but FSM active.
9. DOGE sl_atr_mult=2.0: 1 trade, SL hit after 68 min on -0.32% move.
10. LOW_VOLATILITY: worst regime by net PnL (-141.36) despite best win rate (57.9%).
11. ETHUSDT: worst symbol by net PnL (-101.19) despite 58.3% win rate.
12. DZ veto rate: 0% (vol_threshold=0.98 effectively disabled).
13. UNCERTAIN bars: 14.4% of session, zero intents generated.
14. 40 `OPEN_GUARD_FAIL` rejections from ghost lifecycle states.

### INFERENCES (derived from facts + code analysis)
1. TP/SL asymmetry (cause #1) is the primary loss driver — geometry problem, not randomness.
2. Fee drag is structural: at ~3 USDT/trade, any TP gain under 3 USDT is net-negative.
3. FLIP_GATE_UNKNOWN is caused by position lifecycle state tracking failure, likely the same DEF-005 OrderIndex gap identified in prior audits.
4. BUY absence is a strategist-level problem: gates (DZ, UNCERTAIN) are NOT blocking BUY — the strategist simply doesn't generate BUY signals in current market conditions.
5. BRACKETS_PENDING ghost blocks are caused by bracket fill events arriving after portfolio already shows FLAT (race condition between exchange fill WS and portfolio REST).
6. TREND_UP shorting losses would be avoided if the strategist generated BUY signals in uptrends.

### ASSUMPTIONS (reasonable but unverified)
1. A longer sample (>31 trades) would confirm the 6.8× asymmetry is structural, not bad luck.
2. DOGE sl_atr_mult=2.0 would show improvement over 0.75 with more trades (single sample inconclusive).
3. Fixing FLIP_GATE and BRACKETS_PENDING would increase trade frequency but not necessarily improve profitability given the asymmetry.
4. The strategist SHORT bias is related to the signal generation model, not just market conditions.

### UNKNOWNS (cannot determine from available data)
1. Would wider TP targets (higher tp_low_ratio) improve net PnL, or just increase hold time and SL risk?
2. What is the strategist's internal confidence landscape for BUY signals — is BUY threshold unreachable?
3. How much PnL was lost to BRACKETS_PENDING ghost blocking (counterfactual)?
4. Is the 100% DOGE SL rate at sl_atr_mult=2.0 indicative of DOGE unsuitability or just bad timing?
5. What would be the effect of completely disabling TREND_UP trading?
6. How does this 27h window compare to a full 7-day cycle across varying market regimes?

---

## 11. Final Verdict

**P1 improved partially but major structural defects still distort results.**

Specifically:
- **Config deployment**: Fully successful. ETH leverage fixed, TP/SL tightening applied, zero fallbacks.
- **DZ blocking**: Fixed. Zero DZ vetoes — P0 vol_threshold change was effective.
- **BUY recovery**: NOT achieved. Strategist kernel generates <7% BUY signals. This is upstream of gates.
- **Profitability**: NOT improved. Tighter TP/SL narrowed the brackets but did not fix the fundamental asymmetry (6.8× loss/win ratio).
- **Runtime stability**: Two symbols (BTC, DOGE) self-disabled via lifecycle ghost states. FLIP_GATE blocked 139 signals session-wide.

The system is currently not suitable for extended testnet validation in its present form. The wins are too small (capped by tight TP) and the losses too large (wide SL relative to TP) for any win rate below ~87% to be profitable.

---

## 12. Recommended Next Actions

### Immediate (P1.5 — Config + Code)

1. **TP/SL geometry redesign** (CONFIG): The tp_low_ratio values (BTC=1.0, ETH=0.4, SOL=0.36) combined with tp_mult produce TP distances 3-5× smaller than SL distances. Either:
   - Increase tp_low_ratio to bring TP closer to 1× SL (symmetric), OR
   - Reduce SL distances to match current TP tightness, OR
   - Switch to ATR-based TP/SL for Aurora (like MR already uses) for market-adaptive brackets

2. **FLIP_GATE_UNKNOWN fix** (CODE): Must provide initial flip state from portfolio REST snapshot instead of requiring a completed round-trip. This blocks >5 signals/hour and is session-wide.

3. **BRACKETS_PENDING ghost fix** (CODE): FSM must detect portfolio FLAT ≠ local ACTIVE divergence and force-clear the lifecycle. This is the same class as DEF-005.

### Short-Term (P2)

4. **TREND_UP regime handling**: Either generate BUY signals in TREND_UP or disable TREND_UP trading entirely. Shorting into confirmed uptrends lost -84.20 USDT in 6 trades.

5. **Strategist BUY-signal audit**: Investigate why the strategist kernel produces <7% BUY signals. The problem is NOT in the gates anymore (DZ is fixed, UNCERTAIN filtering is correct) — it's in signal generation.

6. **DOGE strategy review**: Separate evaluation needed. Single trade, SL hit, lifecycle ghost. MR at 20x (vs 10x calibration) with bypass gates is not a safe configuration.

### Evaluation Guidance

7. **Aurora and DOGE must be evaluated separately**. DOGE is MR strategy with fundamentally different execution path, bypass gates, and leverage mismatch. Including DOGE in Aurora conclusions is invalid.

8. **Do NOT run another 24h testnet** until TP/SL geometry and lifecycle ghost fixes are in place. The current geometry makes the system structurally unprofitable regardless of market conditions.

9. **Next correct step**: P1.5 code-fix package for FLIP_GATE + BRACKETS_PENDING ghost + TP/SL geometry rebalance. Then re-run testnet with fixed code.

---

## Mandatory Tables Summary

### Table 1: Regime Ranking by Net PnL
| Rank | Regime | Net PnL | Win% | Trades |
|------|--------|---------|------|--------|
| WORST | LOW_VOLATILITY | -141.36 | 57.9% | 19 |
| 2 | TREND_UP | -84.20 | 33.3% | 6 |
| 3 | MEAN_REVERSION | -24.08 | 50.0% | 6 |

### Table 2: Regime Ranking by Stop-Out Severity
| Rank | Regime | SL Hits | SL Rate | Avg SL Loss |
|------|--------|---------|---------|-------------|
| WORST | TREND_UP | 4 | 67% | -16.10 |
| 2 | LOW_VOLATILITY | 8 | 42% | -17.67 |
| 3 | MEAN_REVERSION | 3 | 50% | -8.03 |

### Table 3: Symbol Ranking by Net PnL
| Rank | Symbol | Strategy | Net PnL | Win% | Trades |
|------|--------|----------|---------|------|--------|
| WORST | ETHUSDT | Aurora | -101.19 | 58.3% | 12 |
| 2 | SOLUSDT | Aurora | -70.04 | 53.8% | 13 |
| 3 | BTCUSDT | Aurora | -54.18 | 40.0% | 5 |
| 4 | DOGEUSDT | MR | -24.24 | 0.0% | 1 |

### Table 4: Symbol Ranking by Fee Drag
| Rank | Symbol | Fees | Fees/Trade | Fees % of Net Loss |
|------|--------|------|------------|-------------------|
| 1 | SOLUSDT | 37.46 | 2.88 | 53.5% |
| 2 | ETHUSDT | 37.46 | 3.12 | 37.0% |
| 3 | BTCUSDT | 18.17 | 3.63 | 33.5% |
| 4 | DOGEUSDT | 2.70 | 2.70 | 11.1% |

### Table 5: Aurora BUY/LONG Live Counts
| Symbol | BUY Intents | BUY Exec | SELL Intents | SELL Exec | BUY% (exec) |
|--------|-------------|----------|--------------|-----------|-------------|
| BTCUSDT | 0 | 0 | 21 | 6 | 0.0% |
| ETHUSDT | 2 | 2 | 17 | 13 | 13.3% |
| SOLUSDT | 3 | 3 | 35 | 12 | 20.0% |
| **Total** | **5** | **5** | **73** | **31** | **13.9%** |

### Table 6: TP/SL and Leverage Verification
| Check | Target | Observed | Status |
|-------|--------|----------|--------|
| BTC SL (LOW_VOL) | ~32.5 bps | min=32.5 bps ✓ | Applied |
| BTC TP (LOW_VOL) | ~40.6 bps | min=39.8 bps ✓ | Applied |
| ETH SL (LOW_VOL) | ~52.3 bps | min=53.1 bps ✓ | Applied |
| ETH TP (LOW_VOL, RR clamped) | ~15.7 bps | avg=19.6 bps ✓ | Applied (with clamp) |
| SOL SL (LOW_VOL) | ~50.0 bps | min=50.7 bps ✓ | Applied |
| SOL TP (LOW_VOL) | ~15.1 bps | avg=17.1 bps ✓ | Applied |
| SOL min_dist_bps | 14 bps | TP min=7.1 (non-LOW_VOL) | Working |
| ETH leverage | 20x | 20.0x (14/14) | **Confirmed** |
| DOGE sl_atr_mult | 2.0 | SL=28.8 bps (ATR-based) | Applied |
| TP/SL fallback? | None expected | 0/37 entries | **Zero fallbacks** |

---

*Report generated from live runtime artifacts. All statistics derived from order_log_v1.jsonl (695 events), shadow_critical_event_journal_v1.jsonl (41,713 events), trade_lifecycle.jsonl (133,617 records), aurora_trades.log (314 lines), domain_execution_position.log (37 TP/SL entries), and regime_confidence_audit_v1.jsonl (2,612 records).*
