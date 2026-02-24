# Latent Vision Report

## Executive Summary

- Verdict: **VAE is likely blind (MR vs HIGH_VOL overlap is too high).**
- Confidence: **high**
- Crucial check (MR vs HIGH_VOL): distance=0.0311, MR RMS radius=0.1755, ratio=0.177, overlap_risk=YES

## Data Scope

- Requested tail lines across `logs/features/*.log`: **50,000**
- Labeling horizon (`horizon_bars`): **5**
- Settled latent samples: **50,000**
- Dataset CSV: `C:/Users/user/Music/Phenix/docs/latent_dataset.csv`

### Regime Distribution

| Regime | Count | Share |
|---|---:|---:|
| TREND_UP | 6,012 | 12.02% |
| TREND_DOWN | 6,509 | 13.02% |
| MEAN_REVERSION | 24,997 | 49.99% |
| HIGH_VOLATILITY | 6,692 | 13.38% |
| EXHAUSTION | 5,790 | 11.58% |

## Cluster Radius Stats

| Regime | Count | Mean Radius | Std Radius | RMS Radius |
|---|---:|---:|---:|---:|
| TREND_UP | 6012 | 0.1619 | 0.0737 | 0.1779 |
| TREND_DOWN | 6509 | 0.1643 | 0.0745 | 0.1804 |
| MEAN_REVERSION | 24997 | 0.1635 | 0.0640 | 0.1755 |
| HIGH_VOLATILITY | 6692 | 0.1781 | 0.0808 | 0.1956 |
| EXHAUSTION | 5790 | 0.2031 | 0.1226 | 0.2373 |

## Centroid Distance Matrix (Euclidean)

| Regime | TREND_UP | TREND_DOWN | MEAN_REVERSION | HIGH_VOLATILITY | EXHAUSTION |
|---|---|---|---|---|---|
| TREND_UP | 0.0000 | 0.0047 | 0.0247 | 0.0499 | 0.1294 |
| TREND_DOWN | 0.0047 | 0.0000 | 0.0221 | 0.0468 | 0.1276 |
| MEAN_REVERSION | 0.0247 | 0.0221 | 0.0000 | 0.0311 | 0.1253 |
| HIGH_VOLATILITY | 0.0499 | 0.0468 | 0.0311 | 0.0000 | 0.1028 |
| EXHAUSTION | 0.1294 | 0.1276 | 0.1253 | 0.1028 | 0.0000 |

## Crucial Distance Test

- Question: Is `distance(centroid(MR), centroid(HIGH_VOLATILITY))` significantly larger than within-MR cluster variance?
- Computed: `distance=0.0311`, `mr_rms_radius=0.1755`, `distance/radius=0.177`
- Result: **FAIL (overlap too high)**

## Visual Diagnostics

![Latent PCA](C:/Users/user/Music/Phenix/docs/latent_space_pca.png)

![Latent t-SNE](C:/Users/user/Music/Phenix/docs/latent_space_tsne.png)

