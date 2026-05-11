# MARCH STRATEGY A/B REPORT

## Experiment Label

MARCH / SIDE B / DEGRADED PARTIAL-UNIVERSE.

## Runs

| Variant | Run ID | Config surface |
| --- | --- | --- |
| Baseline | `20260314_041537` | Current side B SSOT |
| Candidate v1 | `20260314_041758` | Side B SSOT + `config/overlays/march_candidate_v1_block_eth_trend_down.yaml` |

## Headline Metrics

| Metric | Baseline | Candidate v1 | Delta |
| --- | ---: | ---: | ---: |
| Total PnL USDT | -364.33 | 22.84 | +387.17 |
| ROI % | -36.43 | 2.28 | +38.72 pp |
| Max drawdown % | 56.19 | 6.99 | -49.20 pp |
| Win rate | 0.6000 | 0.8125 | +0.2125 |
| Reported total trades | 182 | 32 | -150 |
| Closed trades in `result.json` | 90 | 16 | -74 |
| End balance USDT | 635.67 | 1022.84 | +387.17 |

## Trade Slice Comparison

### Baseline `20260314_041537`

| Slice | Closed trades | Net PnL USDT |
| --- | ---: | ---: |
| BNBUSDT / MEAN_REVERSION / LONG / SL | 2 | -37.82 |
| BNBUSDT / MEAN_REVERSION / LONG / TP | 5 | 18.87 |
| ETHUSDT / MEAN_REVERSION / LONG / SL | 1 | -23.29 |
| ETHUSDT / MEAN_REVERSION / LONG / TP | 8 | 65.40 |
| ETHUSDT / TREND_DOWN / LONG / SL | 31 | -1488.07 |
| ETHUSDT / TREND_DOWN / LONG / TP | 38 | 1275.60 |
| ETHUSDT / TREND_DOWN / SHORT / SL | 3 | -222.85 |
| ETHUSDT / TREND_DOWN / SHORT / TP | 2 | 47.90 |

### Candidate v1 `20260314_041758`

| Slice | Closed trades | Net PnL USDT |
| --- | ---: | ---: |
| BNBUSDT / MEAN_REVERSION / LONG / SL | 2 | -47.51 |
| BNBUSDT / MEAN_REVERSION / LONG / TP | 5 | 21.53 |
| ETHUSDT / MEAN_REVERSION / LONG / SL | 1 | -38.78 |
| ETHUSDT / MEAN_REVERSION / LONG / TP | 8 | 87.73 |

## Interpretation

1. The candidate worked exactly in the way the evidence matrix predicted: it removed the ETH TREND_DOWN cluster and left only ETH MEAN_REVERSION plus BNB MEAN_REVERSION.
2. The PnL improvement of about `+387 USDT` is almost entirely explained by deleting the negative ETH TREND_DOWN slice observed in the baseline.
3. Drawdown compression is the strongest practical result: about `56.2%` down to `7.0%` on the same March surface.
4. The candidate is intentionally coarse. It proves that the root problem on this reproducible surface is ETH TREND_DOWN participation, not BNB or ETH MEAN_REVERSION.

## Verdict

Candidate v1 passes as the first evidence-bound March research candidate.

Pass criteria met:

- Positive March PnL.
- Large drawdown reduction.
- No new runtime surface invented.
- Clear causal tie to the dominant repeated failure cluster.

Not proven:

- Jan-Feb retention.
- Full-universe robustness.
- Q2 / Mar-Jun behavior.
- Whether a finer code-based ETH TREND_DOWN filter could retain upside better than a coarse block.