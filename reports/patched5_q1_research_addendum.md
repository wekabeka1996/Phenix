# Aurora patched5 Q1 Research - Addendum After patched6 Re-run
*Run used for correction: 20260312_010242*
*Scope: correction of the earlier Q1 conclusion, not a new patch proposal*

---

## 1. What Was Invalidated

The earlier working conclusion in the Q1 research was:

> Q1 without DOGE should be approximately +89.77 USDT, therefore DOGE is the full economic root cause.

That conclusion is now disproved by the clean patched6 rerun.

Observed patched6 Q1 result:

| Metric | Value |
|---|---:|
| total_pnl | -101.27 USDT |
| roi_pct | -10.13% |
| max_drawdown | 62.68% |
| total_trades | 333 |
| end_balance | 898.73 USDT |

DOGE was successfully removed from the active universe in this run:

| Check | Value |
|---|---:|
| DOGE in assignments | no |
| DOGE in symbols_to_track | no |
| DOGE closed trades | 0 |

Therefore:

- DOGE was a real config gap and a real contaminant.
- DOGE was not the full reason Q1 failed.
- The prior hypothetical line "Q1 w/o DOGE ~= +89.77" must no longer be treated as valid research output.

---

## 2. Updated Q1 Attribution

The dominant residual loss after DOGE removal is March 2024 ETHUSDT x TREND_DOWN.

| Slice | n | pnl_net |
|---|---:|---:|
| ETHUSDT x TREND_DOWN, March 2024 | 76 | -215.84 USDT |
| ETHUSDT x TREND_DOWN, full Q1 | 114 | -119.07 USDT |
| ETHUSDT x MEAN_REVERSION, March 2024 | 9 | +49.51 USDT |
| BNBUSDT x MEAN_REVERSION, March 2024 | 7 | -25.04 USDT |

March 2024 by itself was the main collapse month:

| Month | n | pnl_net |
|---|---:|---:|
| 2024-01 | 35 | +12.64 USDT |
| 2024-02 | 39 | +77.56 USDT |
| 2024-03 | 92 | -191.36 USDT |

Interpretation:

- patched6 proved the DOGE block worked.
- patched6 also proved that the remaining system still contains a large adverse March ETH TREND_DOWN behavior.
- The Q1 research must be split into two findings instead of one:
  1. DOGE was a registry/config contamination issue.
  2. March ETH TREND_DOWN is the main residual economic failure mode.

---

## 3. Corrected Final Q1 Position

Corrected verdict set:

| Subject | Corrected verdict |
|---|---|
| DOGE in Aurora | BLOCK was correct |
| DOGE as full Q1 root cause | false |
| patched5 baseline after DOGE removal | still economically broken in March |
| Primary residual forensic target | ETHUSDT x TREND_DOWN in March 2024 |

The full detailed forensic write-up is in:

- reports/eth_trend_down_march_2024_postmortem.md
- reports/eth_trend_down_semantics_janfeb_vs_march.md
