# Latent Vision Report

## Executive Summary

- Verdict: **VAE is likely blind (MR vs HIGH_VOL overlap is too high).**
- Confidence: **high**
- Crucial check (MR vs HIGH_VOL): distance=0.4957, MR RMS radius=1.2765, ratio=0.388, overlap_risk=YES

## Data Scope

- Requested tail lines across `logs/features/*.log`: **200,000**
- Labeling horizon (`horizon_bars`): **5**
- Normalization scope used for encoding: **per_symbol**
- Price feature mode: **log**
- Delta price mode: **pct**
- Settled latent samples: **200,000**
- Dataset CSV: `C:/Users/user/Music/Phenix/docs/forensics/neocortex_latent_dataset_2026-02-25.csv`

### Regime Distribution

| Regime | Count | Share |
|---|---:|---:|
| TREND_UP | 18,641 | 9.32% |
| TREND_DOWN | 19,225 | 9.61% |
| MEAN_REVERSION | 114,363 | 57.18% |
| HIGH_VOLATILITY | 25,293 | 12.65% |
| EXHAUSTION | 22,478 | 11.24% |

## Cluster Radius Stats

| Regime | Count | Mean Radius | Std Radius | RMS Radius |
|---|---:|---:|---:|---:|
| TREND_UP | 18641 | 1.2234 | 0.7355 | 1.4275 |
| TREND_DOWN | 19225 | 1.2125 | 0.6889 | 1.3946 |
| MEAN_REVERSION | 114363 | 1.1183 | 0.6155 | 1.2765 |
| HIGH_VOLATILITY | 25293 | 1.5358 | 0.7497 | 1.7090 |
| EXHAUSTION | 22478 | 1.1262 | 0.5485 | 1.2527 |

## Centroid Distance Matrix (Euclidean)

| Regime | TREND_UP | TREND_DOWN | MEAN_REVERSION | HIGH_VOLATILITY | EXHAUSTION |
|---|---|---|---|---|---|
| TREND_UP | 0.0000 | 0.0197 | 0.1084 | 0.4979 | 3.0256 |
| TREND_DOWN | 0.0197 | 0.0000 | 0.0981 | 0.4983 | 3.0272 |
| MEAN_REVERSION | 0.1084 | 0.0981 | 0.0000 | 0.4957 | 3.0348 |
| HIGH_VOLATILITY | 0.4979 | 0.4983 | 0.4957 | 0.0000 | 2.5547 |
| EXHAUSTION | 3.0256 | 3.0272 | 3.0348 | 2.5547 | 0.0000 |

## Crucial Distance Test

- Question: Is `distance(centroid(MR), centroid(HIGH_VOLATILITY))` significantly larger than within-MR cluster variance?
- Computed: `distance=0.4957`, `mr_rms_radius=1.2765`, `distance/radius=0.388`
- Result: **FAIL (overlap too high)**

## Visual Diagnostics

![Latent PCA](C:/Users/user/Music/Phenix/docs/forensics/neocortex_latent_pca_2026-02-25.png)

![Latent t-SNE](C:/Users/user/Music/Phenix/docs/forensics/neocortex_latent_tsne_2026-02-25.png)

