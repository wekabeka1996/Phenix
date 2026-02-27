# Latent Vision Report

## Executive Summary

- Verdict: **VAE is likely blind (MR vs HIGH_VOL overlap is too high).**
- Confidence: **high**
- Crucial check (MR vs HIGH_VOL): distance=0.0212, MR RMS radius=0.1274, ratio=0.166, overlap_risk=YES

## Data Scope

- Requested tail lines across `logs/features/*.log`: **20,000**
- Labeling horizon (`horizon_bars`): **5**
- Normalization scope used for encoding: **per_symbol**
- Price feature mode: **log**
- Delta price mode: **pct**
- Settled latent samples: **20,000**
- Dataset CSV: `C:/Users/user/Music/Phenix/docs/latent_dataset.csv`

### Regime Distribution

| Regime | Count | Share |
|---|---:|---:|
| TREND_UP | 1,955 | 9.78% |
| TREND_DOWN | 2,007 | 10.04% |
| MEAN_REVERSION | 11,108 | 55.54% |
| HIGH_VOLATILITY | 2,628 | 13.14% |
| EXHAUSTION | 2,302 | 11.51% |

## Cluster Radius Stats

| Regime | Count | Mean Radius | Std Radius | RMS Radius |
|---|---:|---:|---:|---:|
| TREND_UP | 1955 | 0.1261 | 0.0819 | 0.1504 |
| TREND_DOWN | 2007 | 0.1221 | 0.0763 | 0.1440 |
| MEAN_REVERSION | 11108 | 0.1126 | 0.0595 | 0.1274 |
| HIGH_VOLATILITY | 2628 | 0.1263 | 0.0633 | 0.1413 |
| EXHAUSTION | 2302 | 0.1683 | 0.0806 | 0.1866 |

## Centroid Distance Matrix (Euclidean)

| Regime | TREND_UP | TREND_DOWN | MEAN_REVERSION | HIGH_VOLATILITY | EXHAUSTION |
|---|---|---|---|---|---|
| TREND_UP | 0.0000 | 0.0060 | 0.0135 | 0.0195 | 0.1462 |
| TREND_DOWN | 0.0060 | 0.0000 | 0.0082 | 0.0173 | 0.1498 |
| MEAN_REVERSION | 0.0135 | 0.0082 | 0.0000 | 0.0212 | 0.1543 |
| HIGH_VOLATILITY | 0.0195 | 0.0173 | 0.0212 | 0.0000 | 0.1448 |
| EXHAUSTION | 0.1462 | 0.1498 | 0.1543 | 0.1448 | 0.0000 |

## Crucial Distance Test

- Question: Is `distance(centroid(MR), centroid(HIGH_VOLATILITY))` significantly larger than within-MR cluster variance?
- Computed: `distance=0.0212`, `mr_rms_radius=0.1274`, `distance/radius=0.166`
- Result: **FAIL (overlap too high)**

## Visual Diagnostics

![Latent PCA](C:/Users/user/Music/Phenix/docs/latent_space_pca.png)

- t-SNE image not generated.

