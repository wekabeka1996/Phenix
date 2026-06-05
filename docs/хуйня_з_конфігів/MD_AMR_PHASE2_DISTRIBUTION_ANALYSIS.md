# MD-AMR Phase 2 Distribution Analysis

**Status:** `PHASE 2 COMPLETE`
**Date:** 2026-04-10
**Baseline:** max_hold_bars=16, target_approach_pct=0.0 (Package A.1)

## Limitations (Mandatory Disclosure)

- XRPUSDT: ~4622 bars / 62 days (2026-02-08 to 2026-04-10)
- BNBUSDT: ~2633 bars / 37 days (2026-02-26 to 2026-04-10)
- **In-sample only** — no out-of-sample validation data available
- Single time window — distributions may not be stationary
- Entry count is limited; quantile estimates have high uncertainty

---

## 1. Entry Distributions

### XRPUSDT
Total entries: 217
  penetration_depth: n=217  mean=1.1262  median=0.8556  p10=0.5430  p25=0.6548  p75=1.3096  p90=2.0000  std=0.7758
  band_width (abs): n=217  mean=0.0057  median=0.0052  p10=0.0030  p25=0.0039  p75=0.0067  p90=0.0090  std=0.0028
  channel_width_pct: n=217  mean=0.4028  median=0.3662  p10=0.2194  p25=0.2810  p75=0.4746  p90=0.6455  std=0.1897
  atr: n=217  mean=0.0058  median=0.0053  p10=0.0030  p25=0.0040  p75=0.0071  p90=0.0096  std=0.0027
  atr_zscore: n=217  mean=-0.0805  median=-0.3712  p10=-1.4289  p25=-0.9757  p75=0.5477  p90=1.7924  std=1.2800
  dir_score_margin_above_thr: n=217  mean=0.3318  median=0.4111  p10=0.0843  p25=0.2415  p75=0.4410  p90=0.4538  std=0.1434
  directional_coherence: n=217  mean=0.1429  median=0.0000  p10=0.0000  p25=0.0000  p75=0.2500  p90=0.2500  std=0.1624
  channel_slope_pct: n=217  mean=0.1772  median=0.1566  p10=0.0916  p25=0.1192  p75=0.2053  p90=0.2885  std=0.0857
  dir_score_at_entry: n=217  mean=-0.0020  median=-0.0120  p10=-0.0855  p25=-0.0485  p75=0.0366  p90=0.0972  std=0.0727
  side_split: total=217  BUY=120 (55.3%)  SELL=97 (44.7%)

### BNBUSDT
Total entries: 126
  penetration_depth: n=126  mean=1.1799  median=0.8273  p10=0.5138  p25=0.6514  p75=1.2300  p90=1.9869  std=1.1164
  band_width (abs): n=126  mean=1.5289  median=1.3992  p10=0.8067  p25=1.1055  p75=1.8298  p90=2.4329  std=0.6243
  channel_width_pct: n=126  mean=0.2438  median=0.2240  p10=0.1342  p25=0.1732  p75=0.2883  p90=0.3873  std=0.0998
  atr: n=126  mean=1.5940  median=1.4434  p10=0.8975  p25=1.1257  p75=1.9413  p90=2.5459  std=0.6468
  atr_zscore: n=126  mean=-0.0984  median=-0.4477  p10=-1.3665  p25=-1.0306  p75=0.6861  p90=1.7713  std=1.2734
  dir_score_margin_above_thr: n=126  mean=0.3270  median=0.4193  p10=0.0578  p25=0.2240  p75=0.4420  p90=0.4491  std=0.1463
  directional_coherence: n=126  mean=0.1726  median=0.2500  p10=0.0000  p25=0.0000  p75=0.2500  p90=0.5000  std=0.1883
  channel_slope_pct: n=126  mean=0.1075  median=0.0975  p10=0.0570  p25=0.0764  p75=0.1304  p90=0.1798  std=0.0462
  dir_score_at_entry: n=126  mean=-0.0018  median=0.0017  p10=-0.0689  p25=-0.0353  p75=0.0282  p90=0.0545  std=0.0522
  side_split: total=126  SELL=68 (54.0%)  BUY=58 (46.0%)

### COMBINED
Total entries: 343
  penetration_depth: n=343  mean=1.1459  median=0.8507  p10=0.5317  p25=0.6547  p75=1.2826  p90=2.0000  std=0.9145
  band_width (abs): n=343  mean=0.5652  median=0.0071  p10=0.0033  p25=0.0046  p75=1.2192  p90=1.7213  std=0.8266
  channel_width_pct: n=343  mean=0.3444  median=0.3103  p10=0.1721  p25=0.2239  p75=0.4181  p90=0.5495  std=0.1796
  atr: n=343  mean=0.5892  median=0.0075  p10=0.0035  p25=0.0048  p75=1.2264  p90=1.8383  std=0.8607
  atr_zscore: n=343  mean=-0.0871  median=-0.4072  p10=-1.4065  p25=-1.0048  p75=0.5888  p90=1.7849  std=1.2758
  dir_score_margin_above_thr: n=343  mean=0.3300  median=0.4124  p10=0.0771  p25=0.2258  p75=0.4412  p90=0.4517  std=0.1443
  directional_coherence: n=343  mean=0.1538  median=0.2500  p10=0.0000  p25=0.0000  p75=0.2500  p90=0.2500  std=0.1727
  channel_slope_pct: n=343  mean=0.1516  median=0.1355  p10=0.0710  p25=0.0963  p75=0.1815  p90=0.2593  std=0.0809
  dir_score_at_entry: n=343  mean=-0.0019  median=-0.0044  p10=-0.0785  p25=-0.0457  p75=0.0322  p90=0.0815  std=0.0659
  side_split: total=343  BUY=178 (51.9%)  SELL=165 (48.1%)

---

## 2. Hold Trajectory Distributions

### XRPUSDT
Total hold-bar observations: 3303
  bars_held_at_observation: n=3303  mean=8.4874  median=8.0000  p10=2.0000  p25=4.0000  p75=13.0000  p90=15.0000  std=4.6215
  progress_pct (0=entry, 1=at_target): n=3303  mean=0.0805  median=0.1138  p10=-1.9984  p25=-0.6819  p75=0.9711  p90=2.1120  std=2.3364
  hold_health: n=3303  mean=-0.0144  median=-0.0109  p10=-0.0993  p25=-0.0569  p75=0.0273  p90=0.0707  std=0.0688
  progress_state_distribution: total=3303  REVERSING_AGAINST=1490 (45.1%)  COMPLETE=806 (24.4%)  PARTIAL_PROGRESS=494 (15.0%)  NOT_STARTED=340 (10.3%)  NEAR_COMPLETION=173 (5.2%)
  atr_zscore_while_held: n=3303  mean=0.0838  median=-0.2513  p10=-1.3642  p25=-0.9423  p75=0.9114  p90=2.0482  std=1.3587

### BNBUSDT
Total hold-bar observations: 1969
  bars_held_at_observation: n=1969  mean=8.4870  median=8.0000  p10=2.0000  p25=4.0000  p75=13.0000  p90=15.0000  std=4.6152
  progress_pct (0=entry, 1=at_target): n=1969  mean=0.0063  median=0.1796  p10=-2.1403  p25=-0.8404  p75=1.0917  p90=2.2636  std=2.9665
  hold_health: n=1969  mean=-0.0112  median=-0.0093  p10=-0.0667  p25=-0.0396  p75=0.0170  p90=0.0491  std=0.0479
  progress_state_distribution: total=1969  REVERSING_AGAINST=863 (43.8%)  COMPLETE=531 (27.0%)  PARTIAL_PROGRESS=304 (15.4%)  NOT_STARTED=172 (8.7%)  NEAR_COMPLETION=99 (5.0%)
  atr_zscore_while_held: n=1969  mean=0.0551  median=-0.2343  p10=-1.3149  p25=-0.9398  p75=0.8823  p90=1.9677  std=1.3010

### COMBINED
Total hold-bar observations: 5272
  bars_held_at_observation: n=5272  mean=8.4873  median=8.0000  p10=2.0000  p25=4.0000  p75=13.0000  p90=15.0000  std=4.6187
  progress_pct (0=entry, 1=at_target): n=5272  mean=0.0527  median=0.1360  p10=-2.0648  p25=-0.7442  p75=1.0196  p90=2.1941  std=2.5897
  hold_health: n=5272  mean=-0.0132  median=-0.0102  p10=-0.0894  p25=-0.0489  p75=0.0229  p90=0.0615  std=0.0618
  progress_state_distribution: total=5272  REVERSING_AGAINST=2353 (44.6%)  COMPLETE=1337 (25.4%)  PARTIAL_PROGRESS=798 (15.1%)  NOT_STARTED=512 (9.7%)  NEAR_COMPLETION=272 (5.2%)
  atr_zscore_while_held: n=5272  mean=0.0731  median=-0.2410  p10=-1.3508  p25=-0.9413  p75=0.8987  p90=2.0288  std=1.3374

---

## 3. Exit Archetype Distributions

### XRPUSDT
Total exit events: 381
  exit_reason: total=381  ZOMBIE_POSITION_TIMEOUT=216 (56.7%)  FEE_AWARE_SCALEOUT=165 (43.3%)
  archetype: total=381  HEALTHY_SCALEOUT=165 (43.3%)  LATE_PROFITABLE_ZOMBIE=116 (30.4%)  STALE_HOLD=69 (18.1%)  NARROW_CHANNEL_FAKE=31 (8.1%)
  bars_held_at_exit: n=381  mean=13.3648  median=17.0000  p10=5.0000  p25=10.0000  p75=17.0000  p90=17.0000  std=5.0509
  gross_pnl_pct: n=381  mean=0.1577  median=0.2395  p10=-1.3793  p25=-0.2976  p75=0.6502  p90=1.7465  std=1.3229
  net_pnl_pct: n=381  mean=0.0777  median=0.1595  p10=-1.4593  p25=-0.3776  p75=0.5702  p90=1.6665  std=1.3229
  -> HEALTHY_SCALEOUT (n=165): avg_gross=0.3756%  avg_bars=8.6
  -> LATE_PROFITABLE_ZOMBIE (n=116): avg_gross=1.0684%  avg_bars=17.0
  -> NARROW_CHANNEL_FAKE (n=31): avg_gross=-0.9953%  avg_bars=17.0
  -> STALE_HOLD (n=69): avg_gross=-1.3763%  avg_bars=17.0

### BNBUSDT
Total exit events: 161
  exit_reason: total=161  ZOMBIE_POSITION_TIMEOUT=125 (77.6%)  FEE_AWARE_SCALEOUT=36 (22.4%)
  archetype: total=161  LATE_PROFITABLE_ZOMBIE=65 (40.4%)  NARROW_CHANNEL_FAKE=48 (29.8%)  HEALTHY_SCALEOUT=36 (22.4%)  STALE_HOLD=12 (7.5%)
  bars_held_at_exit: n=161  mean=15.0870  median=17.0000  p10=8.0000  p25=17.0000  p75=17.0000  p90=17.0000  std=4.1749
  gross_pnl_pct: n=161  mean=0.0811  median=0.1370  p10=-0.9961  p25=-0.4102  p75=0.5037  p90=0.9217  std=0.8932
  net_pnl_pct: n=161  mean=0.0011  median=0.0570  p10=-1.0761  p25=-0.4902  p75=0.4237  p90=0.8417  std=0.8932
  -> HEALTHY_SCALEOUT (n=36): avg_gross=0.2157%  avg_bars=8.4
  -> LATE_PROFITABLE_ZOMBIE (n=65): avg_gross=0.7269%  avg_bars=17.0
  -> NARROW_CHANNEL_FAKE (n=48): avg_gross=-0.6296%  avg_bars=17.0
  -> STALE_HOLD (n=12): avg_gross=-0.9780%  avg_bars=17.0

### COMBINED
Total exit events: 542
  exit_reason: total=542  ZOMBIE_POSITION_TIMEOUT=341 (62.9%)  FEE_AWARE_SCALEOUT=201 (37.1%)
  archetype: total=542  HEALTHY_SCALEOUT=201 (37.1%)  LATE_PROFITABLE_ZOMBIE=181 (33.4%)  STALE_HOLD=81 (14.9%)  NARROW_CHANNEL_FAKE=79 (14.6%)
  bars_held_at_exit: n=542  mean=13.8764  median=17.0000  p10=5.0000  p25=11.0000  p75=17.0000  p90=17.0000  std=4.8677
  gross_pnl_pct: n=542  mean=0.1350  median=0.2293  p10=-1.2768  p25=-0.3324  p75=0.5996  p90=1.4152  std=1.2110
  net_pnl_pct: n=542  mean=0.0550  median=0.1493  p10=-1.3568  p25=-0.4124  p75=0.5196  p90=1.3352  std=1.2110
  -> HEALTHY_SCALEOUT (n=201): avg_gross=0.3470%  avg_bars=8.6
  -> LATE_PROFITABLE_ZOMBIE (n=181): avg_gross=0.9458%  avg_bars=17.0
  -> NARROW_CHANNEL_FAKE (n=79): avg_gross=-0.7731%  avg_bars=17.0
  -> STALE_HOLD (n=81): avg_gross=-1.3173%  avg_bars=17.0

---

## 4. Package C Calibration Insights

Based on Phase 2 distributions:

- Median penetration_depth: **0.8507** (relevant for C.1 target anchor calibration)
- Median directional_coherence: **0.25** (p25=0.00) — relevant for C.2 setup_quality
- Median channel_width_pct: **0.3103%** (relevant for narrow-channel veto threshold)
- Median in-position progress_pct: **0.136** (fraction of trades spending time in reversal: 44.6%)
  -> 44.6% of hold-bars show price moving AGAINST thesis. This validates C.3 Hold Quality design need.
- STALE_HOLD: 81 (14.9%) — primary target for C.3 Hold Quality / Soft Decay
- LATE_PROFITABLE_ZOMBIE: 181 (33.4%) — these must NOT be cut by premature C.3 decay

---

## 5. Artifact Paths

| Artifact | Path |
|:---|:---|
| Entry distributions CSV | `scratch/phase2_entries.csv` |
| Hold trajectory CSV | `scratch/phase2_holds.csv` |
| Exit archetype CSV | `scratch/phase2_exits.csv` |
| Analysis script | `scratch/phase2_distribution_analysis.py` |

---

## 6. Phase 2 Exit Gate Evaluation

| Requirement | Status |
|:---|:---:|
| Script runs on available recorder data | YES |
| XRP and BNB analyzed separately | YES |
| Entry distributions visible | YES |
| Hold trajectory distributions visible | YES |
| Exit archetype classifications exist | YES |
| Limitations explicitly stated | YES |

**Phase 2 exit gate: PASSED.** Package C.1 implementation may begin.