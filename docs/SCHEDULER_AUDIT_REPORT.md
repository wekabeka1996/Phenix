# Scheduler Audit Report

Generated: 2026-02-24 02:57:13
Data source: `logs/neocortex_metrics_snapshot_20260224_025612.csv`
CSV window: 2026-02-24 02:48:35 -> 2026-02-24 02:56:12
Settlement window: 2026-02-24 02:48:35 -> 2026-02-24 02:56:12

## Run Selection and Integrity

- Analysis uses a fixed snapshot of `logs/neocortex_metrics.csv` to avoid drift while the process is still writing.
- Snapshot row count: 68,590; settlement rows: 22,014; PPO rows: 1,100.
- Step range: 1,164,239 -> 1,232,828; timestamp resets: 0; step resets: 0.
- No in-file timestamp/step resets detected, so the whole snapshot is treated as one latest contiguous run.

## Executive Summary

- Verdict: **Scheduler did NOT fix collapse: dead classes remain below 1% prediction share.**
- Overall accuracy: **55.06%** (12,122/22,014).
- Prediction mix: MR=80.72%, EXH=19.00%, all others combined=0.28%.
- PPO entropy is already near-deterministic in this run (mean=0.0089, first=0.000142, last=0.037410, max spike=0.6304), not near 1.5.

## PPO Health

| Metric | Value | Interpretation |
|---|---:|---|
| `ppo_entropy` first / last | 0.000142 / 0.037410 | Very low at both ends; no high-entropy start in this snapshot |
| `ppo_entropy` mean / min / max | 0.008877 / 0.000000 / 0.630421 | Mostly collapsed with occasional spikes |
| `ppo_loss_pi` abs mean | 0.007727 | Small but non-zero updates |
| `ppo_loss_pi` non-zero rows | 343 / 1,100 | Policy head active intermittently |
| `ppo_loss_v` mean | 1.034845 | Value head clearly active |
| `ppo_loss_v` non-zero rows | 1,100 / 1,100 | Value loss active continuously |

### Entropy and Loss Trajectory (12 buckets)

| Bucket | Time span | n | mean entropy | mean `ppo_loss_pi` | mean `ppo_loss_v` |
|---:|---|---:|---:|---:|---:|
| 1 | 2026-02-24 02:48:36 -> 2026-02-24 02:49:16 | 92 | 0.006130 | -0.003480 | 1.072143 |
| 2 | 2026-02-24 02:49:16 -> 2026-02-24 02:49:58 | 92 | 0.001432 | -0.002981 | 1.079525 |
| 3 | 2026-02-24 02:49:59 -> 2026-02-24 02:50:40 | 92 | 0.053808 | 0.003353 | 0.963263 |
| 4 | 2026-02-24 02:50:40 -> 2026-02-24 02:51:20 | 92 | 0.001756 | 0.008452 | 0.968020 |
| 5 | 2026-02-24 02:51:20 -> 2026-02-24 02:51:58 | 92 | 0.002971 | -0.002551 | 1.064113 |
| 6 | 2026-02-24 02:51:59 -> 2026-02-24 02:52:39 | 92 | 0.003689 | -0.007547 | 1.027002 |
| 7 | 2026-02-24 02:52:39 -> 2026-02-24 02:53:14 | 92 | 0.013279 | -0.005966 | 1.076177 |
| 8 | 2026-02-24 02:53:14 -> 2026-02-24 02:53:50 | 92 | 0.005002 | -0.004608 | 1.023894 |
| 9 | 2026-02-24 02:53:50 -> 2026-02-24 02:54:25 | 92 | 0.002791 | 0.002914 | 1.154093 |
| 10 | 2026-02-24 02:54:26 -> 2026-02-24 02:55:01 | 92 | 0.011952 | -0.005070 | 1.103933 |
| 11 | 2026-02-24 02:55:02 -> 2026-02-24 02:55:36 | 92 | 0.001132 | -0.006041 | 1.008377 |
| 12 | 2026-02-24 02:55:36 -> 2026-02-24 02:56:11 | 88 | 0.002291 | -0.005458 | 0.870449 |

## Confusion Matrix (Predicted vs Realized, entire run)

| Pred \ Real | T_UP | T_DN | MR | H_VOL | EXH | Total | Pred% |
|---|---:|---:|---:|---:|---:|---:|---:|
| **T_UP** | 5 | 0 | 13 | 7 | 4 | 29 | 0.13% |
| **T_DN** | 2 | 1 | 4 | 2 | 1 | 10 | 0.05% |
| **MR** | 2837 | 2889 | 9675 | 2282 | 86 | 17769 | 80.72% |
| **H_VOL** | 2 | 1 | 14 | 4 | 2 | 23 | 0.10% |
| **EXH** | 153 | 170 | 727 | 696 | 2437 | 4183 | 19.00% |
| **Real Total** | 2999 | 3061 | 10433 | 2991 | 2530 | 22014 | 100.00% |
| **Real %** | 13.62% | 13.90% | 47.39% | 13.59% | 11.49% |  |  |

### Per-class Precision/Recall

| Class | Predicted | Realized | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| T_UP | 29 (0.13%) | 2999 (13.62%) | 0.1724 | 0.0017 | 0.0033 |
| T_DN | 10 (0.05%) | 3061 (13.90%) | 0.1000 | 0.0003 | 0.0007 |
| MR | 17769 (80.72%) | 10433 (47.39%) | 0.5445 | 0.9273 | 0.6861 |
| H_VOL | 23 (0.10%) | 2991 (13.59%) | 0.1739 | 0.0013 | 0.0027 |
| EXH | 4183 (19.00%) | 2530 (11.49%) | 0.5826 | 0.9632 | 0.7261 |

## Dead-class Resurrection Check (>1% predicted)

| Class | Predicted count | Predicted % | Above 1%? |
|---|---:|---:|---|
| T_UP | 29 | 0.132% | NO |
| T_DN | 10 | 0.045% | NO |
| H_VOL | 23 | 0.104% | NO |

Result: **FAIL**. All three dead classes resurrected above 1% = False.

## Action Distribution Shift (Early/Middle/Late thirds)

Prediction distribution by chunk (what policy outputs):

| Chunk | Time span | n | Accuracy | T_UP | T_DN | MR | H_VOL | EXH |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Early | 2026-02-24 02:48:35 -> 2026-02-24 02:51:19 | 7338 | 46.35% | 0.05% | 0.01% | 81.53% | 0.00% | 18.40% |
| Middle | 2026-02-24 02:51:19 -> 2026-02-24 02:53:49 | 7338 | 56.68% | 0.23% | 0.08% | 79.83% | 0.30% | 19.56% |
| Late | 2026-02-24 02:53:49 -> 2026-02-24 02:56:12 | 7338 | 62.17% | 0.11% | 0.04% | 80.78% | 0.01% | 19.05% |

Realized distribution by chunk (market labels):

| Chunk | T_UP | T_DN | MR | H_VOL | EXH |
|---|---:|---:|---:|---:|---:|
| Early | 17.42% | 18.59% | 37.37% | 14.55% | 12.07% |
| Middle | 13.15% | 12.69% | 49.48% | 13.42% | 11.26% |
| Late | 10.30% | 10.44% | 55.33% | 12.78% | 11.15% |

Interpretation: policy does not begin near-uniform 20/20/20/20/20 and does not converge to realized mix; it stays dominated by MR+EXH throughout.

## Final Assessment

- The 3 previously dead classes (`TREND_UP`, `TREND_DOWN`, `HIGH_VOLATILITY`) are still effectively dead in this run (all <1% predicted overall).
- Accuracy improved over chunks, but this comes mainly from overpredicting MR/EXH against a market that shifted toward MR.
- This is not a balanced 5-class policy yet.
