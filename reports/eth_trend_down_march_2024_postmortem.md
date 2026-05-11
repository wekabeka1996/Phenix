# ETHUSDT x TREND_DOWN - March 2024 Post-Mortem
*Run id: 20260312_010242*
*Method: existing artifacts only; no new backtests, no code changes*

---

## 0. Executive Verdict

March 2024 ETHUSDT x TREND_DOWN is the primary residual failure mode in the clean patched6 Q1 rerun.

The evidence supports this ranking:

1. **Market-phase mismatch / wrong-side exposure** is the strongest explanation.
2. **Negative payoff geometry / stop structure** is the second major contributor.
3. **Mild sizing amplification** exists, but it is secondary.
4. **Regime-confidence lag** is not supported as a primary explanation.
5. **Regime transition during hold** is not proven from available artifacts.
6. **Flip/stop modification bug** is not proven from available artifacts.

The most important factual observation is simple:

- In a TREND_DOWN regime, March produced **71 LONG trades vs 5 SHORT trades**.
- That slice lost **-215.84 USDT** on **76 trades**.
- The win rate was **59.21%**, but the payoff ratio was only **0.61**, so the strategy was structurally fragile once the hit rate slipped.

Break-even win rate from observed March trade geometry:

$$
WR_{BE} = \frac{|avg\_loss|}{avg\_win + |avg\_loss|} = \frac{60.45}{36.85 + 60.45} \approx 62.1\%
$$

Observed March hit rate was only **59.21%**, below break-even.

---

## 1. Scope And Artifacts

Artifacts used:

- reports/backtests/backtest_20260312_010242.json
- reports/backtests/20260312_010242/manifest.json
- reports/backtests/20260312_010242/resolved_config.json
- reports/backtests/20260312_010242/result.json
- logs/backtests/order_log_20260312_010242.jsonl

Constraints respected:

- no new backtests
- no patched7 preparation
- no code/config edits
- only forensic analysis from produced artifacts

---

## 2. March ETH TREND_DOWN Summary

| Metric | Value |
|---|---:|
| trades | 76 |
| pnl_net | -215.84 USDT |
| win_rate | 59.21% |
| TP count | 45 |
| SL count | 31 |
| avg_win | +36.85 USDT |
| avg_loss | -60.45 USDT |
| payoff ratio | 0.61 |
| avg hold | 70.5 min |
| median hold | 47.5 min |
| max hold | 370.0 min |

Time-to-exit split:

| Exit bucket | TP | SL |
|---|---:|---:|
| <= 30 min | 16 | 15 |
| > 120 min | 8 | 3 |
| avg hold | 75.8 min | 62.7 min |
| median hold | 50.0 min | 45.0 min |

Interpretation:

- Stops were not massively slower than TPs.
- Losses were not caused by a few extremely stale holds only.
- The damage came from many medium-size stopouts plus several large ones.

---

## 3. Side Anatomy

| Side | n | pnl_net | WR | TP | SL |
|---|---:|---:|---:|---:|---:|
| LONG | 71 | -154.72 | 59.15% | 42 | 29 |
| SHORT | 5 | -61.12 | 60.00% | 3 | 2 |

This is the strongest directional clue in the whole post-mortem.

In TREND_DOWN, the strategy was overwhelmingly trading **LONG**, not SHORT.

That does not by itself prove a bug. It does prove a market-phase mismatch for March 2024 behavior:

- if TREND_DOWN was expected to monetize continuation/downside, this did not happen;
- if TREND_DOWN was intentionally implemented as dip-buying within a downtrend, then March hit rate/payoff was insufficient for that design.

Either way, the realized March behavior is inconsistent with a robust downtrend exploitation story.

---

## 4. Day-By-Day Breakdown And Equity Path

Daily realized pnl by close date:

| Day | Trades | Day pnl | Equity after close |
|---|---:|---:|---:|
| 2024-03-01 | 1 | +42.66 | 1042.66 |
| 2024-03-05 | 3 | -113.86 | 928.79 |
| 2024-03-06 | 1 | +46.65 | 975.44 |
| 2024-03-07 | 1 | +46.99 | 1022.44 |
| 2024-03-10 | 3 | -99.45 | 922.99 |
| 2024-03-11 | 1 | +35.28 | 958.27 |
| 2024-03-12 | 4 | +200.14 | 1158.41 |
| 2024-03-13 | 1 | +49.52 | 1207.93 |
| 2024-03-14 | 5 | -151.33 | 1056.60 |
| 2024-03-15 | 6 | -127.91 | 928.69 |
| 2024-03-16 | 4 | -183.52 | 745.17 |
| 2024-03-17 | 5 | -39.92 | 705.25 |
| 2024-03-18 | 3 | +114.31 | 819.57 |
| 2024-03-19 | 15 | -84.12 | 735.45 |
| 2024-03-20 | 5 | -48.54 | 686.90 |
| 2024-03-21 | 2 | +83.60 | 770.50 |
| 2024-03-22 | 9 | -114.44 | 656.06 |
| 2024-03-24 | 1 | +32.35 | 688.41 |
| 2024-03-26 | 2 | +62.90 | 751.31 |
| 2024-03-27 | 3 | +0.84 | 752.15 |
| 2024-03-29 | 1 | +32.01 | 784.16 |

The collapse is concentrated, not uniform.

Main damage clusters:

| Cluster | Trades | Net pnl |
|---|---:|---:|
| 2024-03-14 to 2024-03-16 | 15 | -462.76 USDT |
| 2024-03-19 to 2024-03-22 | 31 | -163.51 USDT |

Interpretation:

- March was not lost by one isolated error.
- The system briefly recovered to **1207.93 USDT** by March 13.
- The real breakdown starts **after March 13**, especially the 14-16 March cluster.

---

## 5. Loss Distribution

SL bucket histogram by absolute net loss per trade:

| Loss bucket | Count |
|---|---:|
| 0-25 USDT | 6 |
| 25-50 USDT | 2 |
| 50-75 USDT | 13 |
| 75-100 USDT | 9 |
| 100+ USDT | 1 |

Interpretation:

- The problem is not only tail losses.
- The center of the damage is the repeated **50-100 USDT stopout band**.
- That is consistent with systematic stop geometry under repeated wrong-way entries, not with one accidental liquidation event.

---

## 6. Fast Stop Evidence

Hold bucket counts for all March ETH TREND_DOWN trades:

| Hold bucket | Count |
|---|---:|
| <= 10 min | 15 |
| 10-30 min | 16 |
| 30-120 min | 34 |
| > 120 min | 11 |

Selected quick SL examples:

| Exit time UTC | Side | pnl_net | Hold | Confidence |
|---|---|---:|---:|---:|
| 2024-03-05 16:35 | LONG | -85.29 | 5 min | 0.8286 |
| 2024-03-05 19:40 | LONG | -75.27 | 10 min | 0.8500 |
| 2024-03-14 16:30 | LONG | -86.14 | 30 min | 0.8500 |
| 2024-03-15 06:10 | LONG | -92.05 | 5 min | 0.8500 |
| 2024-03-15 06:35 | SHORT | -78.34 | 20 min | 0.8500 |
| 2024-03-19 01:45 | LONG | -67.10 | 10 min | 0.8500 |
| 2024-03-19 07:15 | LONG | -52.32 | 5 min | 0.8500 |
| 2024-03-20 01:30 | LONG | -62.43 | 25 min | 0.8500 |
| 2024-03-22 11:15 | LONG | -59.96 | 30 min | 0.8500 |

Interpretation:

- A meaningful part of the damage happened almost immediately after entry.
- This is consistent with **entry timing / phase mismatch** and inconsistent with a theory that losses mostly came from late exits after correct entries.

---

## 7. Confidence And Lag Test

Order-log linked regime confidence by the same rid:

| Group | Avg confidence |
|---|---:|
| all March ETH TREND_DOWN entries | 0.8095 |
| TP entries | 0.8042 |
| SL entries | 0.8171 |

Additional fact:

- **22 of 31 SL trades** were entered at confidence **0.85**.
- **32 of 44 TP trades** with linked rid were also entered at confidence **0.85**.

Interpretation:

- Losses were not concentrated in low-confidence entries.
- Confidence is not discriminative enough here to explain the collapse.
- This weakens the hypothesis that March failed mainly because of regime-confidence lag or low-confidence permissiveness.

---

## 8. Top Losses

| Exit time UTC | Side | pnl_net | Hold | Entry | Exit | Confidence | Rejects in prior 60m |
|---|---|---:|---:|---:|---:|---:|---:|
| 2024-03-10 21:50 | LONG | -135.92 | 55 min | 3883.33 | 3789.29 | 0.7038 | 4 |
| 2024-03-14 12:25 | LONG | -96.14 | 60 min | 3911.16 | 3850.56 | 0.6814 | 7 |
| 2024-03-15 06:10 | LONG | -92.05 | 5 min | 3668.03 | 3611.20 | 0.8500 | 4 |
| 2024-03-14 15:45 | LONG | -91.16 | 45 min | 3876.37 | 3816.32 | 0.8500 | 1 |
| 2024-03-14 16:30 | LONG | -86.14 | 30 min | 3811.45 | 3752.40 | 0.8500 | 0 |
| 2024-03-05 16:35 | LONG | -85.29 | 5 min | 3575.64 | 3520.25 | 0.8286 | 1 |
| 2024-03-15 06:35 | SHORT | -78.34 | 20 min | 3611.55 | 3667.56 | 0.8500 | 0 |
| 2024-03-16 15:10 | LONG | -77.32 | 230 min | 3663.91 | 3607.16 | 0.7497 | 8 |

Interpretation:

- The largest losses are mostly LONG trades.
- Some losses follow several rejected intents in the preceding hour, but many do not.
- This does not support a clean story that the engine was merely "late" because of rejects. The later accepted trade still often entered on the wrong side of the move.

---

## 9. Hypothesis Ranking

### 9.1 Market-phase mismatch / wrong entries

**Supported strongly.**

Evidence:

- 71 of 76 trades were LONG inside TREND_DOWN.
- The largest loss cluster is dominated by fast LONG stopouts.
- Many losses happen within 5-30 minutes, which is typical of entering against immediate continuation.

### 9.2 Stop structure / payoff geometry

**Supported strongly.**

Evidence:

- avg_win = +36.85, avg_loss = -60.45, payoff = 0.61.
- Break-even hit rate was ~62.1%, but actual March hit rate was 59.21%.
- Once the edge softened in mid-March, the payoff structure turned the slice negative quickly.

### 9.3 Sizing amplification

**Supported weakly to moderately, but secondary.**

Observed entry notional:

| Group | Avg notional | Median |
|---|---:|---:|
| TP trades | 4178.96 | 3916.27 |
| SL trades | 4276.76 | 4028.20 |

Losing trades were slightly larger on average, but not enough to explain the full collapse by themselves.

### 9.4 Regime lag / low-confidence entries

**Not supported as primary explanation.**

SL entries had slightly **higher** average confidence than TP entries.

### 9.5 Regime transitions during hold

**Not proven.**

The available artifacts preserve entry-side regime and confidence, but they do not provide a reliable full per-position regime-transition trail during the hold period.

### 9.6 Flip/stop modifications

**Not proven.**

The artifacts show fills and closes, but do not prove a dedicated stop mutation bug. The repeated loss shape is already explainable without that assumption.

---

## 10. What Is Not Proven

This post-mortem does **not** prove the following:

- that the regime classifier itself is broken;
- that TREND_DOWN labels were wrong in raw market data;
- that stop placement code mutated brackets incorrectly;
- that positions systematically changed regime during hold and were not re-evaluated;
- that one single patch is sufficient to repair the March behavior.

What is proven is narrower and stronger:

- March ETH TREND_DOWN lost primarily through repeated wrong-way exposure with unfavorable payoff geometry.

---

## 11. Final Conclusion

The March ETHUSDT x TREND_DOWN failure is best explained by a combination of:

1. **Directional mismatch**: the regime traded mostly LONG during a hostile month for that behavior.
2. **Fragile payoff**: average stop cost materially exceeded average TP gain, so the slice needed a higher hit rate than it achieved.
3. **Cluster concentration**: the real collapse is concentrated after March 13, especially March 14-16.

The evidence does **not** support the simpler explanation that low confidence or slow exits were the main issue.

Before any patching, the next thing to verify should be whether TREND_DOWN is intended to be continuation-following or dip-buying. The March trade ledger shows that the actual live backtest behavior was overwhelmingly dip-buying.
